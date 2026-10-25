"""Full UFCW publications remain observable through durable scheduled checks."""

import hashlib
import json
import shutil
from datetime import datetime
from pathlib import Path
from typing import Any, cast

import pytest
import yaml
from typer.testing import CliRunner

from election_guide.cli import app
from election_guide.collection.http import HttpArtifact
from election_guide.collection.verification_review import approve_baseline
from election_guide.evidence.models import evidence_fingerprint

ROOT = Path(__file__).parents[1]
INDEX = "https://ufcw3000.org/endorsements"
KNOWN = (
    "https://ufcw3000.org/news/2026/10/15/ufcw-3000-executive-board-unanimously-rejects-i-638-and-i-001-endorses-no-hate-campaign",
    "https://ufcw3000.org/news/2026/10/15/ufcw-3000-executive-board-unanimously-rejects-i-645-endorses-no-vote",
)
NEW = "https://ufcw3000.org/news/2026/10/20/new-endorsements"


def article(body: str = "Authored fixture position.") -> bytes:
    return (
        '<h1 class="page-title">News</h1><article class="hentry category-endorsement">'
        '<h1 class="entry-title">UFCW endorsement publication</h1>'
        f'<div class="sqs-html-content"><p>{body}</p></div></article>'
    ).encode()


@pytest.fixture
def publication(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[Path, dict[str, Any]]:
    monkeypatch.delenv("ENDORSEMENT_EVIDENCE_KEY", raising=False)
    policy = cast(dict[str, Any], yaml.safe_load((ROOT / "config/verification.yaml").read_text()))
    policy["elections"][0]["sources"] = [
        item for item in policy["elections"][0]["sources"] if item["source_id"] == "ufcw-3000"
    ]
    path = tmp_path / "policy.yaml"
    path.write_text(yaml.safe_dump(policy))
    pages: dict[str, Any] = {
        INDEX: (ROOT / "tests/fixtures/verification/ufcw-3000.html").read_bytes(),
        **dict.fromkeys(KNOWN, article()),
    }

    def fetch(url: str, *, timeout_seconds: float = 30) -> HttpArtifact:
        value = pages[url]  # Unexpected or unrelated fetches fail this fixture.
        if isinstance(value, Exception):
            raise value
        if isinstance(value, HttpArtifact):
            return value
        return HttpArtifact(
            content=value, status=200, canonical_url=url, redirect_chain=[], media_type="text/html"
        )

    monkeypatch.setattr("election_guide.collection.discovery.fetch_http", fetch)
    monkeypatch.setattr("election_guide.collection.verification_runtime.fetch_http", fetch)
    return path, pages


def run(policy: Path, state: Path, day: int) -> dict[str, Any]:
    # Each invocation constructs a new runner and rereads policy and persisted state.
    result = CliRunner().invoke(
        app,
        [
            "verification",
            "run",
            str(policy),
            "--state-root",
            str(state),
            "--live",
            "--checked-at",
            f"2026-10-{day:02d}T18:00:00Z",
        ],
    )
    assert result.exit_code == 0, result.output
    return json.loads(result.output)["automatic"][0]


def test_ufcw_body_edit_and_independent_persisted_reuse_reach_review_tasks(
    tmp_path: Path, publication: tuple[Path, dict[str, Any]]
) -> None:
    policy, pages = publication
    first_state = tmp_path / "first-state"
    first = run(policy, first_state, 19)
    assert first["status"] == "created"
    state = tmp_path / "independent-state"
    shutil.copytree(first_state, state)
    second = run(policy, state, 20)
    assert second["status"] == "unchanged"
    assert second["snapshot_id"] == first["snapshot_id"]
    pages[KNOWN[0]] = article("Changed or withdrawn authored fixture position.")
    changed = run(policy, state, 21)
    assert changed["status"] == "updated" and changed["content_changed"] is True
    assert changed["diff"] == []
    result = CliRunner().invoke(
        app,
        [
            "verification",
            "reconcile",
            str(policy),
            "--state-root",
            str(state),
            "--repository",
            "example/guide",
            "--revision",
            "a" * 40,
            "--as-of",
            "2026-10-21",
            "--dry-run",
        ],
    )
    assert result.exit_code == 0, result.output
    assert changed["id"] in result.output and "unrecognized wording" in result.output
    manifests = [json.loads(path.read_text()) for path in state.rglob("manifests/*.json")]
    original = next(item for item in manifests if item["requested_url"] == KNOWN[0])
    assert original["capture_method"] == "static_html" and original["http_status"] == 200
    assert any(
        item["content_sha256"] == hashlib.sha256(pages[KNOWN[0]]).hexdigest() for item in manifests
    )
    assert all(item["availability"] == "observed" for item in manifests)
    assert not list(state.rglob("vault/**/*.json"))
    comparison = next(item for item in manifests if item["id"] == changed["capture_id"])
    assert comparison["capture_method"] == "manual_upload" and comparison["http_status"] is None
    assert not any(b"Changed or withdrawn" in path.read_bytes() for path in state.rglob("*.*"))
    validation = CliRunner().invoke(
        app, ["verification", "validate", str(policy), "--state-root", str(state)]
    )
    assert validation.exit_code == 0, validation.output


def test_ufcw_new_article_is_retained_after_landing_link_rotates_away(
    tmp_path: Path, publication: tuple[Path, dict[str, Any]]
) -> None:
    policy, pages = publication
    state = tmp_path / "state"
    run(policy, state, 19)
    original_landing = pages[INDEX]
    pages[INDEX] += (
        f'<a href="{NEW}">New endorsements</a>'
        '<a href="/news/2026/10/20/unrelated">Office hours</a>'
        '<a href="/news/2025/10/20/past-endorsements">Past endorsements</a>'
    ).encode()
    pages[NEW] = article()
    run(policy, state, 20)
    pages[INDEX] = original_landing
    before_rotation = run(policy, state, 21)
    pages[NEW] = article("Correction after link rotated away.")
    changed = run(policy, state, 22)
    assert changed["status"] == "updated" and changed["content_changed"] is True
    assert changed["previous_snapshot_id"] == before_rotation["snapshot_id"]
    assert any(
        NEW in json.loads(path.read_text())["articles"] for path in state.rglob("discovery/*.json")
    )


@pytest.mark.parametrize(
    "failure", [OSError("fixture unavailable"), b"<html>Parser changed</html>", b"\xff"]
)
def test_ufcw_required_article_failure_preserves_baseline(
    tmp_path: Path, publication: tuple[Path, dict[str, Any]], failure: Any
) -> None:
    policy, pages = publication
    state = tmp_path / "state"
    baseline = run(policy, state, 19)
    pages[KNOWN[1]] = failure
    failed = run(policy, state, 20)
    assert failed["status"] == "failed"
    assert failed["previous_snapshot_id"] == baseline["snapshot_id"]
    assert len(list(state.rglob("extractions/*.json"))) == 1


@pytest.mark.parametrize(
    ("original_size", "expected_status"),
    [
        pytest.param(25 * 1024 * 1024 - 71, "updated", id="comparison-at-limit"),
        pytest.param(25 * 1024 * 1024 - 70, "failed", id="comparison-one-byte-over"),
        pytest.param(25 * 1024 * 1024, "failed", id="original-at-limit"),
    ],
)
def test_ufcw_derived_size_boundary_preserves_recoverable_archive(
    tmp_path: Path,
    publication: tuple[Path, dict[str, Any]],
    original_size: int,
    expected_status: str,
) -> None:
    policy, pages = publication
    state = tmp_path / "state"
    baseline = run(policy, state, 19)
    approve_baseline(
        state / "wa-2026-general",
        baseline["snapshot_id"],
        "Fixture reviewer",
        datetime.fromisoformat("2026-10-19T19:00:00+00:00"),
        "Authored HTTP fixture only; no live adoption or actual source approval.",
    )
    history = {p.relative_to(state): p.read_bytes() for p in state.rglob("*.json")}
    original_landing = pages[INDEX]
    landing = original_landing + f'<a href="{NEW}">New endorsements</a>'.encode()
    # A 64-digit digest inside the seven-byte HTML comment adds exactly 71 bytes.
    pages[INDEX] = landing + b"<!--" + b"x" * (original_size - len(landing) - 7) + b"-->"
    pages[NEW] = article()
    assert len(pages[INDEX]) == original_size
    observed = run(policy, state, 20)
    assert observed["status"] == expected_status
    assert observed["previous_snapshot_id"] == baseline["snapshot_id"]
    assert any(
        json.loads(p.read_text())["articles"] == [NEW]
        for p in state.rglob("discovery-obligations/*.json")
    )
    manifests = [json.loads(p.read_text()) for p in state.rglob("manifests/*.json")]
    originals = [
        m
        for m in manifests
        if m["retrieved_at"].startswith("2026-10-20") and m["capture_method"] == "static_html"
    ]
    assert {m["requested_url"] for m in originals} == {INDEX, *KNOWN, NEW}
    for manifest in originals:
        assert manifest["http_status"] == 200
        assert (
            manifest["content_sha256"]
            == hashlib.sha256(pages[manifest["requested_url"]]).hexdigest()
        )
    assert all(m["availability"] == "observed" and "storage_reference" not in m for m in manifests)
    validation = CliRunner().invoke(
        app, ["verification", "validate", str(policy), "--state-root", str(state)]
    )
    assert validation.exit_code == 0, validation.output
    if expected_status == "failed":
        assert observed["snapshot_id"] is None and observed["capture_id"] is None
        assert observed["consecutive_failures"] == 1 and observed["escalated"] is False
        assert len(list(state.rglob("extractions/*.json"))) == 1
        assert len(list(state.rglob("discovery/*.json"))) == 1
        assert not any(
            m["retrieved_at"].startswith("2026-10-20") and m["capture_method"] == "manual_upload"
            for m in manifests
        )
        previous_snapshot = baseline["snapshot_id"]
    else:
        comparison = next(m for m in manifests if m["id"] == observed["capture_id"])
        assert comparison["byte_length"] == 25 * 1024 * 1024
        assert comparison["capture_method"] == "manual_upload" and comparison["http_status"] is None
        previous_snapshot = observed["snapshot_id"]

    # Restore only public records on a fresh runner, with no retained originals or key.
    assert all(p.suffix == ".json" for p in state.rglob("*") if p.is_file())
    assert not list(state.rglob("vault/**/*.json"))
    independent = tmp_path / "independent"
    for path in state.rglob("*.json"):
        target = independent / path.relative_to(state)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(path.read_bytes())
    pages[INDEX] = original_landing
    pages[NEW] = OSError("learned article unavailable after landing link rotates")
    retry = run(policy, independent, 21)
    assert retry["status"] == "failed" and retry["previous_snapshot_id"] == previous_snapshot
    assert retry["consecutive_failures"] == (2 if expected_status == "failed" else 1)
    pages[NEW] = article("Publication recovered after link rotation.")
    recovered = run(policy, independent, 22)
    assert recovered["status"] == "updated" and recovered["baseline_reviewed"] is False
    assert recovered["previous_snapshot_id"] == previous_snapshot
    assert recovered["consecutive_failures"] == 0 and recovered["escalated"] is False
    assert run(policy, independent, 23)["status"] == "unchanged"
    for relative, raw in history.items():
        assert (independent / relative).read_bytes() == raw
    validation = CliRunner().invoke(
        app, ["verification", "validate", str(policy), "--state-root", str(independent)]
    )
    assert validation.exit_code == 0, validation.output
    reconciliation = CliRunner().invoke(
        app,
        [
            "verification",
            "reconcile",
            str(policy),
            "--state-root",
            str(independent),
            "--repository",
            "example/guide",
            "--revision",
            "a" * 40,
            "--as-of",
            "2026-10-23",
            "--dry-run",
        ],
    )
    assert reconciliation.exit_code == 0, reconciliation.output
    assert retry["id"] in reconciliation.output and "**failed**" in reconciliation.output
    assert observed["id"] in reconciliation.output and recovered["id"] in reconciliation.output


@pytest.mark.parametrize(
    "url",
    [
        "http://ufcw3000.org/news/2026/10/20/new-endorsements",
        "https://evil.example/news/2026/10/20/new-endorsements",
        NEW + "?unsafe=yes",
        NEW + "#fragment",
        "https://ufcw3000.org/news/2026/99/20/new-endorsements",
        "https://ufcw3000.org/news/2026/10/20/%2e%2e-endorsements",
    ],
)
def test_ufcw_invalid_relevant_links_fail_without_replacing_baseline(
    tmp_path: Path, publication: tuple[Path, dict[str, Any]], url: str
) -> None:
    policy, pages = publication
    state = tmp_path / "state"
    baseline = run(policy, state, 19)
    pages[INDEX] += f'<a href="{url}">New endorsements</a>'.encode()
    failed = run(policy, state, 20)
    assert failed["status"] == "failed"
    assert failed["previous_snapshot_id"] == baseline["snapshot_id"]


@pytest.mark.parametrize("canonical", [KNOWN[0] + "?unsafe=yes", INDEX])
def test_ufcw_article_redirect_requires_an_official_article_identity(
    tmp_path: Path, publication: tuple[Path, dict[str, Any]], canonical: str
) -> None:
    policy, pages = publication
    state = tmp_path / "state"
    baseline = run(policy, state, 19)
    pages[KNOWN[0]] = HttpArtifact(
        content=article(),
        status=200,
        canonical_url=canonical,
        redirect_chain=[KNOWN[0], canonical],
        media_type="text/html",
    )
    failed = run(policy, state, 20)
    assert failed["status"] == "failed"
    assert failed["previous_snapshot_id"] == baseline["snapshot_id"]


@pytest.mark.parametrize(
    "failed_url", [NEW, KNOWN[0]], ids=["new-article", "earlier-known-article"]
)
@pytest.mark.parametrize(
    "failure",
    [OSError("fixture unavailable"), b"<html>Parser changed</html>"],
    ids=["fetch", "parser"],
)
def test_ufcw_failed_discovery_survives_rotation_and_independent_runner(
    tmp_path: Path,
    publication: tuple[Path, dict[str, Any]],
    failed_url: str,
    failure: Any,
) -> None:
    policy, pages = publication
    state = tmp_path / "state"
    baseline = run(policy, state, 19)
    election = state / "wa-2026-general"
    approve_baseline(
        election,
        baseline["snapshot_id"],
        "Fixture reviewer",
        datetime.fromisoformat("2026-10-19T19:00:00+00:00"),
        "Authored HTTP fixture only; no live adoption or actual source approval.",
    )
    snapshot_path = election / "extractions" / f"{baseline['snapshot_id']}.json"
    original_snapshot = snapshot_path.read_bytes()
    original_landing = pages[INDEX]
    pages[INDEX] += f'<a href="{NEW}">New endorsements</a>'.encode()
    pages[NEW] = article()
    pages[failed_url] = failure
    failed = run(policy, state, 20)
    assert failed["status"] == "failed"
    assert failed["previous_snapshot_id"] == baseline["snapshot_id"]
    assert failed["snapshot_id"] is None
    assert snapshot_path.read_bytes() == original_snapshot
    assert len(list(election.glob("extractions/*.json"))) == 1
    assert len(list(election.glob("discovery/*.json"))) == 1
    validation = CliRunner().invoke(
        app, ["verification", "validate", str(policy), "--state-root", str(state)]
    )
    assert validation.exit_code == 0, validation.output

    # Restore the old index and known articles: only retained learned membership
    # can make this independent runner require the still-unavailable new article.
    pages[INDEX] = original_landing
    pages[KNOWN[0]] = article()
    pages[NEW] = OSError("new fixture article still unavailable after rotation")
    independent = tmp_path / "independent-state"
    shutil.copytree(state, independent)
    retry = run(policy, independent, 21)
    assert retry["status"] == "failed"
    assert retry["previous_snapshot_id"] == baseline["snapshot_id"]
    assert retry["snapshot_id"] is None
    assert len(list(independent.rglob("extractions/*.json"))) == 1

    pages[NEW] = article("Publication recovered after link rotation.")
    recovered = run(policy, independent, 22)
    assert recovered["status"] == "updated" and recovered["content_changed"] is True
    assert recovered["previous_snapshot_id"] == baseline["snapshot_id"]
    assert recovered["baseline_reviewed"] is False
    assert run(policy, independent, 23)["status"] == "unchanged"
    pages[NEW] = article("Body-only correction after recovery.")
    corrected = run(policy, independent, 24)
    assert corrected["status"] == "updated" and corrected["content_changed"] is True
    assert corrected["previous_snapshot_id"] == recovered["snapshot_id"]
    assert corrected["diff"] == []
    assert snapshot_path.read_bytes() == original_snapshot
    assert not any(
        b"Body-only correction" in path.read_bytes() for path in independent.rglob("*.json")
    )
    validation = CliRunner().invoke(
        app, ["verification", "validate", str(policy), "--state-root", str(independent)]
    )
    assert validation.exit_code == 0, validation.output


@pytest.mark.parametrize(
    "corruption",
    [
        "source",
        "unsafe-url",
        "duplicate",
        "bound",
        "year",
        "missing-capture",
        "article-capture",
        "capture-time",
        "identity",
        "comparison-field",
    ],
)
def test_ufcw_retained_obligations_reject_invalid_archive_and_runtime_state(
    tmp_path: Path, publication: tuple[Path, dict[str, Any]], corruption: str
) -> None:
    policy, pages = publication
    state = tmp_path / "state"
    baseline = run(policy, state, 19)
    pages[INDEX] += f'<a href="{NEW}">New endorsements</a>'.encode()
    pages[NEW] = OSError("fixture unavailable")
    assert run(policy, state, 20)["status"] == "failed"
    paths = list(state.rglob("discovery-obligations/*.json"))
    assert len(paths) == 1
    path = paths[0]
    record = json.loads(path.read_text())
    assert record["articles"] == [NEW]
    if corruption == "source":
        record["source_id"] = "seattle-gay-news"
    elif corruption == "unsafe-url":
        record["articles"] = ["https://evil.example/news/2026/10/20/new-endorsements"]
    elif corruption == "duplicate":
        record["articles"] = [NEW, NEW]
    elif corruption == "bound":
        record["articles"] = [
            f"https://ufcw3000.org/news/2026/10/20/endorsement-{i}" for i in range(101)
        ]
    elif corruption == "year":
        record["articles"] = [NEW.replace("/2026/", "/2025/")]
    elif corruption == "missing-capture":
        record["capture_id"] = "capture-ufcw-3000-20261020T180000Z-000000000000"
    elif corruption == "article-capture":
        record["capture_id"] = next(
            item["id"]
            for manifest in state.rglob("manifests/*.json")
            if (item := json.loads(manifest.read_text()))["requested_url"] == KNOWN[0]
            and item["retrieved_at"].startswith("2026-10-20")
        )
    elif corruption == "capture-time":
        record["checked_at"] = "2026-10-21T18:00:00Z"
    elif corruption == "comparison-field":
        record["comparison_sha256"] = "0" * 64
    path.unlink()
    identity = "0" * 64 if corruption == "identity" else evidence_fingerprint(record)
    path.with_name(f"{identity}.json").write_text(json.dumps(record))
    validation = CliRunner().invoke(
        app, ["verification", "validate", str(policy), "--state-root", str(state)]
    )
    assert validation.exit_code != 0, validation.output
    pages[INDEX] = (ROOT / "tests/fixtures/verification/ufcw-3000.html").read_bytes()
    pages[NEW] = article()
    before = {path: path.read_bytes() for path in state.rglob("*.json")}
    # The public runner validates archives before fetching or recording a check.
    result = CliRunner().invoke(
        app,
        [
            "verification",
            "run",
            str(policy),
            "--state-root",
            str(state),
            "--live",
            "--checked-at",
            "2026-10-21T18:00:00Z",
        ],
    )
    assert result.exit_code != 0, result.output
    assert {path: path.read_bytes() for path in state.rglob("*.json")} == before
    assert len(list(state.rglob("extractions/*.json"))) == 1
    assert next(state.rglob("extractions/*.json")).stem == baseline["snapshot_id"]


@pytest.mark.parametrize("corruption", ["source", "time", "composite", "missing-article", "hash"])
def test_ufcw_discovery_binds_public_inputs_and_comparison(
    tmp_path: Path, publication: tuple[Path, dict[str, Any]], corruption: str
) -> None:
    from election_guide.evidence.models import CaptureRequest
    from election_guide.evidence.storage import record_observation

    policy, _ = publication
    state = tmp_path / "state"
    first = run(policy, state, 19)
    path = next(state.rglob("discovery/*.json"))
    audit = json.loads(path.read_text())
    root = path.parent.parent
    if corruption in {"source", "time"}:
        manifest = json.loads((root / "manifests" / f"{audit['captures'][0]}.json").read_text())
        request = CaptureRequest.model_validate(
            {
                k: v
                for k, v in manifest.items()
                if k not in {"id", "availability", "content_sha256", "byte_length"}
            }
        )
        request = request.model_copy(
            update={
                "source_id": "sage-leaders" if corruption == "source" else request.source_id,
                "retrieved_at": datetime.fromisoformat("2026-10-18T18:00:00+00:00")
                if corruption == "time"
                else request.retrieved_at,
            }
        )
        raw = tmp_path / "authored.html"
        raw.write_bytes(b"<p>Authored input with different attribution.</p>")
        observed = record_observation(request, raw, root / "manifests")
        audit["captures"][0] = observed.stem
    elif corruption == "composite":
        audit["captures"][0] = first["capture_id"]
    elif corruption == "missing-article":
        audit["captures"].pop()
    else:
        audit["comparison_sha256"] = "0" * 64
    path.unlink()
    path.with_name(f"{evidence_fingerprint(audit)}.json").write_text(json.dumps(audit))
    result = CliRunner().invoke(
        app, ["verification", "validate", str(policy), "--state-root", str(state)]
    )
    assert result.exit_code != 0, result.output


def test_ufcw_current_publication_extracts_all_33_verified_decisions() -> None:
    from election_guide.collection.adapters import extract_decisions, validate_adapter
    from election_guide.collection.refresh import read_adapter_spec
    from election_guide.inventory.importer import read_inventory
    from election_guide.sources.registry import read_source_registry

    spec = read_adapter_spec(ROOT / "config/adapters/wa-2026-general/ufcw-3000.yaml")
    validate_adapter(
        spec,
        read_inventory(ROOT / "data/normalized/wa-2026-general-inventory.json"),
        read_source_registry(ROOT / "config/sources/wa-2026-general.yaml"),
    )
    decisions = extract_decisions(
        spec,
        (ROOT / "tests/fixtures/verification/ufcw-3000-current-layout.html").read_bytes(),
        media_type="text/html",
    )
    expected = yaml.safe_load(
        (ROOT / "tests/fixtures/verification/ufcw-3000-current-decisions.yaml").read_text()
    )["decisions"]
    # The authored fixture includes all 88 current candidate rows, including
    # 56 outside the frozen ballot, plus Tacoma's distinct measure.
    assert len(decisions) == 33
    assert {d.race_id: (d.status, d.candidate_ids) for d in decisions} == {
        d["race_id"]: (d["status"], d["candidate_ids"]) for d in expected
    }
    assert "ld-11-state-representative-1" not in {d.race_id for d in decisions}
    assert {d.race_id for d in decisions if d.status == "dual_endorsement"} == {
        "ld-32-state-representative-2",
        "ld-37-state-representative-1",
    }


def test_ufcw_current_factual_fixture_reaches_public_runner_without_approval(
    tmp_path: Path, publication: tuple[Path, dict[str, Any]]
) -> None:
    policy, pages = publication
    pages[INDEX] = (ROOT / "tests/fixtures/verification/ufcw-3000-current-layout.html").read_bytes()
    state = tmp_path / "state"
    result = run(policy, state, 24)
    assert result["status"] == "created"
    assert result["baseline_reviewed"] is False
    expected = yaml.safe_load(
        (ROOT / "tests/fixtures/verification/ufcw-3000-current-decisions.yaml").read_text()
    )["decisions"]
    assert {d["race_id"]: d["after"]["candidate_ids"] for d in result["diff"]} == {
        d["race_id"]: d["candidate_ids"] for d in expected
    }
    assert not list(state.rglob("approvals/*.json"))
