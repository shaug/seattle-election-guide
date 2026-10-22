"""TRU WordPress discovery observes full publications through the public runner."""

import base64
import hashlib
import json
import shutil
from datetime import datetime
from io import BytesIO
from pathlib import Path
from typing import Any, cast

import pytest
import yaml
from PIL import Image
from typer.testing import CliRunner

from election_guide.cli import app
from election_guide.collection.http import HttpArtifact
from election_guide.collection.verification_review import approve_baseline
from election_guide.evidence.models import evidence_fingerprint

ROOT = Path(__file__).parents[1]
HOME = "https://transitriders.org/"
CURRENT = HOME + "2026-general-election-endorsements/"
OLD = HOME + "transit-riders-union-2026-general-election-endorsements/"
NEW = HOME + "2026-general-election-endorsements-update/"
IMAGE = (
    "https://transitriders.sfo3.digitaloceanspaces.com/transitriders.org/wp-content/uploads/"
    "2026/10/17022007/TRU_November_2026_General_Endorsements-1024x581.jpg"
)
TITLE = "2026 General Election endorsements"


def entry(url: str, title: str = TITLE, category: str = "endorsements") -> str:
    return (
        f'<article class="post category-{category}"><header><h2 class="entry-title">'
        f'<a href="{url}" rel="bookmark">{title}</a></h2></header></article>'
    )


def archive(*, extra: str = "", boundary: bool = True, next_link: str = "") -> bytes:
    return (
        entry(CURRENT)
        + extra
        + (
            entry(OLD, "Transit Riders Union 2026 General Election Endorsements")
            if boundary
            else ""
        )
        + '<nav class="paging-navigation">'
        + next_link
        + "</nav>"
    ).encode()


def article(body: str = "An authored correction.", *, image: bool = False) -> bytes:
    return (
        '<article class="category-endorsements"><header><h1 class="entry-title">'
        + TITLE
        + '</h1></header><div class="entry-content">'
        + (f'<figure><img src="{IMAGE}" alt=""></figure>' if image else "")
        + body
        + "</div></article>"
    ).encode()


@pytest.fixture
def publication(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[Path, dict[str, Any]]:
    monkeypatch.setenv("ENDORSEMENT_EVIDENCE_KEY", base64.b64encode(bytes(range(32))).decode())
    policy = cast(dict[str, Any], yaml.safe_load((ROOT / "config/verification.yaml").read_text()))
    policy["elections"][0]["sources"] = [
        item
        for item in policy["elections"][0]["sources"]
        if item["source_id"] == "transit-riders-union"
    ]
    path = tmp_path / "policy.yaml"
    path.write_text(yaml.safe_dump(policy))
    facts = (ROOT / "tests/fixtures/verification/transit-riders-union.html").read_text()
    measures = (
        "<ul><li>Yes on City of Seattle Proposition 1 (Seattle Transit Measure renewal)</li>"
        "<li>No on/Reject IP26-645 (repeal of Millionaires Tax)</li>"
        "<li>No on IP26-001 (Force schools to out trans children)</li>"
        "<li>No on IP26-638 (Force women into genital exams to play sports)</li></ul>"
    )
    image_bytes = BytesIO()
    Image.new("RGB", (2, 2), "red").save(image_bytes, format="JPEG")
    pages: dict[str, Any] = {
        HOME: archive(
            extra=(
                entry(
                    HOME + "2026-primary-election-endorsements/",
                    "2026 Primary Election Endorsements",
                )
                + entry(
                    HOME + "2025-general-election-endorsements/",
                    "2025 General Election Endorsements",
                )
                + entry("https://example.org/donate", "Donate", "news")
            )
        ),
        CURRENT: article(
            measures + facts + "<p>We also recommend candidates who did not go through "
            "our endorsement process.</p><p>Cindy Ryu; Teresa Mosqueda</p>",
            image=True,
        ),
        OLD: article(facts),
        IMAGE: image_bytes.getvalue(),
    }

    def fetch(url: str, *, timeout_seconds: float = 30) -> HttpArtifact:
        value = pages[url]
        if isinstance(value, Exception):
            raise value
        if isinstance(value, HttpArtifact):
            return value
        return HttpArtifact(
            content=value,
            status=200,
            canonical_url=url,
            redirect_chain=[],
            media_type="image/jpeg" if url == IMAGE else "text/html",
        )

    monkeypatch.setattr("election_guide.collection.discovery.fetch_http", fetch)
    monkeypatch.setattr("election_guide.collection.verification_runtime.fetch_http", fetch)
    return path, pages


def run(policy: Path, state: Path, day: int) -> dict[str, Any]:
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


def validate(policy: Path, state: Path) -> None:
    result = CliRunner().invoke(
        app, ["verification", "validate", str(policy), "--state-root", str(state)]
    )
    assert result.exit_code == 0, result.output


def test_tru_full_publication_custody_and_twelve_facts_once(
    tmp_path: Path,
    publication: tuple[Path, dict[str, Any]],
) -> None:
    policy, pages = publication
    state = tmp_path / "state"
    first = run(policy, state, 19)
    assert first["status"] == "created"
    snapshot = json.loads(next(state.rglob("extractions/*.json")).read_text())
    assert len(snapshot["decisions"]) == 12
    assert len({item["race_id"] for item in snapshot["decisions"]}) == 12
    council = next(
        item for item in snapshot["decisions"] if item["race_id"] == "king-county-council-2"
    )
    assert council["status"] == "dual_endorsement" and len(council["candidate_ids"]) == 2
    assert not any(
        item["race_id"] in {"ld-32-state-senator", "king-county-council-8"}
        for item in snapshot["decisions"]
    )
    manifests = [json.loads(p.read_text()) for p in state.rglob("manifests/*.json")]
    originals = [m for m in manifests if m["capture_method"] != "manual_upload"]
    assert {m["requested_url"] for m in originals} == {HOME, CURRENT, OLD, IMAGE}
    for manifest in originals:
        assert manifest["http_status"] == 200
        assert (
            manifest["content_sha256"]
            == hashlib.sha256(pages[manifest["requested_url"]]).hexdigest()
        )
        assert list(state.rglob(f"vault/sha256/*/{manifest['content_sha256']}.json"))
    image = next(m for m in originals if m["requested_url"] == IMAGE)
    assert image["capture_method"] == "image"
    composite = next(m for m in manifests if m["id"] == first["capture_id"])
    assert composite["capture_method"] == "manual_upload" and composite["http_status"] is None
    assert not any(b"Cindy Ryu; Teresa Mosqueda" in p.read_bytes() for p in state.rglob("*.json"))
    validate(policy, state)
    independent = tmp_path / "independent"
    shutil.copytree(state, independent)
    second = run(policy, independent, 20)
    assert second["status"] == "unchanged" and second["snapshot_id"] == first["snapshot_id"]


@pytest.mark.parametrize("changed_url", [CURRENT, OLD, IMAGE, NEW])
def test_tru_full_bytes_including_held_and_image_only_changes_route_review(
    tmp_path: Path,
    publication: tuple[Path, dict[str, Any]],
    changed_url: str,
) -> None:
    policy, pages = publication
    pages[HOME] = archive(extra=entry(NEW))
    pages[NEW] = article()
    state = tmp_path / "state"
    first = run(policy, state, 19)
    if changed_url == CURRENT:
        pages[CURRENT] = pages[CURRENT].replace(
            b"Cindy Ryu; Teresa Mosqueda", b"Changed qualified candidate recommendation context"
        )
    else:
        pages[changed_url] += b"<!-- Changed unknown correction -->"
    changed = run(policy, state, 20)
    assert changed["status"] == "updated" and changed["content_changed"] is True
    assert changed["previous_snapshot_id"] == first["snapshot_id"] and changed["diff"] == []
    assert changed["baseline_reviewed"] is False
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
            "2026-10-20",
            "--dry-run",
        ],
    )
    assert result.exit_code == 0, result.output
    assert changed["id"] in result.output and "unrecognized wording" in result.output


@pytest.mark.parametrize("failed_url", [NEW, OLD, HOME + "page/2/"])
def test_tru_learned_membership_survives_failure_rotation_and_independent_recovery(
    tmp_path: Path,
    publication: tuple[Path, dict[str, Any]],
    failed_url: str,
) -> None:
    policy, pages = publication
    state = tmp_path / "state"
    baseline = run(policy, state, 19)
    approve_baseline(
        state / "wa-2026-general",
        baseline["snapshot_id"],
        "Fixture reviewer",
        datetime.fromisoformat("2026-10-19T19:00:00+00:00"),
        "Authored fixture only.",
    )
    history = {p.relative_to(state): p.read_bytes() for p in state.rglob("*.json")}
    pages[HOME] = archive(
        extra=entry(NEW),
        boundary=failed_url != HOME + "page/2/",
        next_link='<a class="next page-numbers" href="/page/2/">Next</a>',
    )
    pages[NEW] = article()
    pages[failed_url] = OSError("authored unavailable input")
    failed = run(policy, state, 20)
    assert (
        failed["status"] == "failed" and failed["previous_snapshot_id"] == baseline["snapshot_id"]
    )
    assert any(
        NEW in json.loads(p.read_text())["articles"]
        for p in state.rglob("discovery-obligations/*.json")
    )
    validate(policy, state)
    pages[HOME] = archive()
    pages[OLD] = article()
    pages[NEW] = OSError("still unavailable after rotation")
    independent = tmp_path / "independent"
    shutil.copytree(state, independent)
    assert run(policy, independent, 21)["status"] == "failed"
    pages[NEW] = article("Recovered publication")
    recovered = run(policy, independent, 22)
    assert recovered["status"] == "updated" and recovered["baseline_reviewed"] is False
    assert recovered["previous_snapshot_id"] == baseline["snapshot_id"]
    assert run(policy, independent, 23)["status"] == "unchanged"
    for relative, raw in history.items():
        assert (independent / relative).read_bytes() == raw
    validate(policy, independent)


@pytest.mark.parametrize(
    "bad_url",
    [
        "http://transitriders.org/2026-general-election-endorsements-update/",
        "https://evil.example/2026-general-election-endorsements-update/",
        NEW + "?x=y",
        NEW + "#x",
        NEW.replace(".org/", ".org:443/"),
        NEW.replace(".org/", "@transitriders.org/"),
        HOME + "%2e%2e/2026-general-election-endorsements-update/",
    ],
)
def test_tru_unsafe_relevant_links_fail(
    tmp_path: Path,
    publication: tuple[Path, dict[str, Any]],
    bad_url: str,
) -> None:
    policy, pages = publication
    state = tmp_path / "state"
    first = run(policy, state, 19)
    pages[HOME] = archive(extra=entry(bad_url))
    failed = run(policy, state, 20)
    assert failed["status"] == "failed" and failed["previous_snapshot_id"] == first["snapshot_id"]


@pytest.mark.parametrize(
    "case",
    [
        "maintenance",
        "empty",
        "utf8",
        "not-html",
        "no-boundary",
        "ambiguous-next",
        "loop",
        "article-empty",
        "article-maintenance",
        "article-utf8",
        "article-canonical",
        "archive-canonical",
        "image-missing",
        "image-replaced",
        "image-canonical",
        "image-media",
        "articles-bound",
        "pages-bound",
    ],
)
def test_tru_incomplete_publications_preserve_previous_snapshot(
    tmp_path: Path,
    publication: tuple[Path, dict[str, Any]],
    case: str,
) -> None:
    policy, pages = publication
    state = tmp_path / "state"
    first = run(policy, state, 19)
    if case in {"maintenance", "empty", "utf8"}:
        pages[HOME] = {"maintenance": b"<html>Maintenance</html>", "empty": b"", "utf8": b"\xff"}[
            case
        ]
    elif case == "not-html":
        pages[HOME] = HttpArtifact(
            content=pages[HOME],
            canonical_url=HOME,
            status=200,
            redirect_chain=[],
            media_type="application/json",
        )
    elif case == "no-boundary":
        pages[HOME] = archive(boundary=False)
    elif case == "ambiguous-next":
        pages[HOME] = archive(
            boundary=False,
            next_link=(
                '<a class="next page-numbers" href="/page/2/">Next</a>'
                '<a class="next page-numbers" href="/page/3/">Next</a>'
            ),
        )
    elif case == "loop":
        pages[HOME] = archive(
            boundary=False, next_link='<a class="next page-numbers" href="/">Next</a>'
        )
    elif case.startswith("article-"):
        pages[OLD] = {
            "article-empty": article(""),
            "article-maintenance": b"<h1>Maintenance</h1>",
            "article-utf8": b"\xff",
            "article-canonical": HttpArtifact(
                content=article(),
                canonical_url=CURRENT,
                status=200,
                redirect_chain=[OLD, CURRENT],
                media_type="text/html",
            ),
        }[case]
    elif case == "archive-canonical":
        pages[HOME] = HttpArtifact(
            content=pages[HOME],
            canonical_url=HOME + "about/",
            status=200,
            redirect_chain=[HOME, HOME + "about/"],
            media_type="text/html",
        )
    elif case in {"image-missing", "image-replaced"}:
        pages[CURRENT] = pages[CURRENT].replace(
            IMAGE.encode(), b"" if case == "image-missing" else (IMAGE + "?new=1").encode()
        )
    elif case in {"image-canonical", "image-media"}:
        pages[IMAGE] = HttpArtifact(
            content=b"image",
            status=200,
            canonical_url=IMAGE + "?new=1" if case == "image-canonical" else IMAGE,
            redirect_chain=[],
            media_type="text/html" if case == "image-media" else "image/jpeg",
        )
    elif case == "articles-bound":
        pages[HOME] = archive(
            extra="".join(
                entry(HOME + f"2026-general-election-endorsements-{i}/") for i in range(101)
            )
        )
    elif case == "pages-bound":
        for number in range(1, 42):
            url = HOME if number == 1 else HOME + f"page/{number}/"
            pages[url] = archive(
                boundary=False,
                next_link=(f'<a class="next page-numbers" href="/page/{number + 1}/">Next</a>'),
            )
    failed = run(policy, state, 20)
    assert failed["status"] == "failed" and failed["previous_snapshot_id"] == first["snapshot_id"]
    assert len(list(state.rglob("extractions/*.json"))) == 1
    validate(policy, state)


@pytest.mark.parametrize(
    "corruption",
    [
        "source",
        "election",
        "year",
        "duplicate",
        "url",
        "count",
        "identity",
        "capture",
        "method",
        "time",
        "vault",
    ],
)
def test_tru_corrupt_obligations_rejected_before_state_mutation(
    tmp_path: Path,
    publication: tuple[Path, dict[str, Any]],
    corruption: str,
) -> None:
    policy, pages = publication
    state = tmp_path / "state"
    run(policy, state, 19)
    pages[HOME] = archive(extra=entry(NEW))
    pages[NEW] = OSError("unavailable")
    assert run(policy, state, 20)["status"] == "failed"
    path = next(state.rglob("discovery-obligations/*.json"))
    record = json.loads(path.read_text())
    if corruption == "source":
        record["source_id"] = "sage-leaders"
    elif corruption == "election":
        record["election_id"] = "wa-2026-primary"
    elif corruption == "year":
        record["articles"] = [NEW.replace("2026", "2025")]
    elif corruption == "duplicate":
        record["articles"] = [NEW, NEW]
    elif corruption == "url":
        record["articles"] = ["https://evil.example/2026-general-election-endorsements/"]
    elif corruption == "count":
        record["articles"] = [HOME + f"2026-general-election-endorsements-{i}/" for i in range(101)]
    elif corruption == "capture":
        record["capture_id"] = "capture-transit-riders-union-20261020T180000Z-000000000000"
    elif corruption == "time":
        record["checked_at"] = "2026-10-21T18:00:00Z"
    elif corruption in {"method", "vault"}:
        capture = next(p for p in state.rglob("manifests/*.json") if p.stem == record["capture_id"])
        manifest = json.loads(capture.read_text())
        if corruption == "method":
            manifest["capture_method"] = "manual_upload"
            manifest["http_status"] = None
            capture.write_text(json.dumps(manifest))
        else:
            next(state.rglob(f"vault/sha256/*/{manifest['content_sha256']}.json")).unlink()
    path.unlink()
    path.with_name(
        ("0" * 64 if corruption == "identity" else evidence_fingerprint(record)) + ".json"
    ).write_text(json.dumps(record))
    result = CliRunner().invoke(
        app, ["verification", "validate", str(policy), "--state-root", str(state)]
    )
    assert result.exit_code != 0
    before = {p: p.read_bytes() for p in state.rglob("*.json")}
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
    assert result.exit_code != 0
    assert {p: p.read_bytes() for p in state.rglob("*.json")} == before


def test_tru_new_article_retained_when_successful_link_rotates(
    tmp_path: Path,
    publication: tuple[Path, dict[str, Any]],
) -> None:
    policy, pages = publication
    state = tmp_path / "state"
    run(policy, state, 19)
    pages[HOME] = archive(extra=entry(NEW))
    pages[NEW] = article()
    added = run(policy, state, 20)
    assert added["status"] == "updated" and added["diff"] == []
    pages[HOME] = archive()
    before = run(policy, state, 21)
    pages[NEW] = article("Correction after successful discovery rotated away")
    changed = run(policy, state, 22)
    assert (
        changed["status"] == "updated" and changed["previous_snapshot_id"] == before["snapshot_id"]
    )
    validate(policy, state)


@pytest.mark.parametrize(
    "corruption", ["source-input", "time", "duplicate", "missing-image", "derived-input"]
)
def test_tru_audit_requires_actual_current_original_inputs(
    tmp_path: Path,
    publication: tuple[Path, dict[str, Any]],
    corruption: str,
) -> None:
    policy, _ = publication
    state = tmp_path / "state"
    first = run(policy, state, 19)
    path = next(state.rglob("discovery/*.json"))
    record = json.loads(path.read_text())
    manifests = [json.loads(p.read_text()) for p in state.rglob("manifests/*.json")]
    if corruption == "time":
        record["checked_at"] = "2026-10-20T18:00:00Z"
    elif corruption == "duplicate":
        record["captures"].append(record["captures"][0])
    elif corruption == "missing-image":
        identifier = next(m["id"] for m in manifests if m["requested_url"] == IMAGE)
        record["captures"].remove(identifier)
    elif corruption == "derived-input":
        record["captures"][0] = first["capture_id"]
    elif corruption == "source-input":
        # An authentic other-source capture is not a TRU publication input.
        from election_guide.collection.vault import seal_store
        from election_guide.evidence.models import CaptureRequest
        from election_guide.evidence.storage import record_capture

        private = tmp_path / "private"
        private.mkdir()
        raw = private / "input.html"
        raw.write_bytes(b"<p>other source</p>")
        election = state / "wa-2026-general"
        manifest_path = record_capture(
            CaptureRequest(
                source_id="sage-leaders",
                requested_url="https://sageleaders.org/",
                canonical_url="https://sageleaders.org/",
                title="Authored fixture",
                retrieved_at=datetime.fromisoformat("2026-10-19T18:00:00+00:00"),
                media_type="text/html",
                capture_method="static_html",
                http_status=200,
                redistribution="restricted",
                redistribution_note="Authored fixture",
            ),
            raw,
            private / "captures",
            election / "manifests",
        )
        seal_store(private / "captures", election / "vault", bytes(range(32)))
        record["captures"][0] = json.loads(manifest_path.read_text())["id"]
    path.unlink()
    path.with_name(evidence_fingerprint(record) + ".json").write_text(json.dumps(record))
    validation = CliRunner().invoke(
        app, ["verification", "validate", str(policy), "--state-root", str(state)]
    )
    assert validation.exit_code != 0
    before = {p: p.read_bytes() for p in state.rglob("*.json")}
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
            "2026-10-20T18:00:00Z",
        ],
    )
    assert result.exit_code != 0
    assert {p: p.read_bytes() for p in state.rglob("*.json")} == before


@pytest.mark.parametrize(
    ("original_size", "expected_status"),
    [
        pytest.param(25 * 1024 * 1024 - 71, "updated", id="comparison-at-limit"),
        pytest.param(25 * 1024 * 1024 - 70, "failed", id="comparison-one-byte-over"),
        pytest.param(25 * 1024 * 1024, "failed", id="original-at-limit"),
    ],
)
def test_tru_derived_size_boundary_preserves_recoverable_archive(
    tmp_path: Path,
    publication: tuple[Path, dict[str, Any]],
    original_size: int,
    expected_status: str,
) -> None:
    policy, pages = publication
    state = tmp_path / "state"
    baseline = run(policy, state, 19)
    history = {p.relative_to(state): p.read_bytes() for p in state.rglob("*.json")}
    designated = pages[CURRENT]
    pages[HOME] = archive(extra=entry(NEW))
    pages[NEW] = article()
    # The derived comparison adds a 64-digit hash inside a seven-byte HTML comment.
    pages[CURRENT] = designated + b"<!--" + b"x" * (original_size - len(designated) - 7) + b"-->"
    assert len(pages[CURRENT]) == original_size
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
        if m["retrieved_at"].startswith("2026-10-20") and m["capture_method"] != "manual_upload"
    ]
    assert {m["requested_url"] for m in originals} == {HOME, CURRENT, OLD, NEW, IMAGE}
    for manifest in originals:
        assert manifest["http_status"] == 200
        assert (
            manifest["content_sha256"]
            == hashlib.sha256(pages[manifest["requested_url"]]).hexdigest()
        )
        assert list(state.rglob(f"vault/sha256/*/{manifest['content_sha256']}.json"))
    validate(policy, state)
    if expected_status == "failed":
        assert len(list(state.rglob("extractions/*.json"))) == 1
        assert len(list(state.rglob("discovery/*.json"))) == 1
        assert not any(
            m["retrieved_at"].startswith("2026-10-20") and m["capture_method"] == "manual_upload"
            for m in manifests
        )
        previous_snapshot = baseline["snapshot_id"]
    else:
        composite = next(m for m in manifests if m["id"] == observed["capture_id"])
        assert composite["byte_length"] == 25 * 1024 * 1024
        assert composite["capture_method"] == "manual_upload"
        assert composite["http_status"] is None
        previous_snapshot = observed["snapshot_id"]

    independent = tmp_path / "independent"
    shutil.copytree(state, independent)
    pages[CURRENT] = designated
    pages[HOME] = archive()
    pages[NEW] = OSError("learned article unavailable after archive link rotates")
    assert run(policy, independent, 21)["status"] == "failed"
    validate(policy, independent)
    pages[NEW] = article("Recovered publication")
    recovered = run(policy, independent, 22)
    assert recovered["status"] == "updated" and recovered["baseline_reviewed"] is False
    assert recovered["previous_snapshot_id"] == previous_snapshot
    assert run(policy, independent, 23)["status"] == "unchanged"
    for relative, raw in history.items():
        assert (independent / relative).read_bytes() == raw
    validate(policy, independent)


def test_tru_total_original_byte_bound_preserves_previous_snapshot(
    tmp_path: Path,
    publication: tuple[Path, dict[str, Any]],
) -> None:
    policy, pages = publication
    state = tmp_path / "state"
    first = run(policy, state, 19)
    padding = b"<!--" + b"x" * (22 * 1024 * 1024) + b"-->"
    for url in (HOME, CURRENT, OLD):
        pages[url] += padding
    failed = run(policy, state, 20)
    assert failed["status"] == "failed" and failed["previous_snapshot_id"] == first["snapshot_id"]
    assert len(list(state.rglob("extractions/*.json"))) == 1
    validate(policy, state)


def test_tru_combined_capture_bound_includes_required_image(
    tmp_path: Path,
    publication: tuple[Path, dict[str, Any]],
) -> None:
    policy, pages = publication
    state = tmp_path / "state"
    baseline = run(policy, state, 19)
    extras = "".join(entry(HOME + f"2026-general-election-endorsements-{i}/") for i in range(98))
    for number in range(1, 41):
        url = HOME if number == 1 else HOME + f"page/{number}/"
        pages[url] = archive(
            extra=extras if number == 1 else "",
            boundary=number == 40,
            next_link=f'<a class="next page-numbers" href="/page/{number + 1}/">Next</a>',
        )
    for i in range(98):
        pages[HOME + f"2026-general-election-endorsements-{i}/"] = article()
    failed = run(policy, state, 20)
    assert (
        failed["status"] == "failed" and failed["previous_snapshot_id"] == baseline["snapshot_id"]
    )
    # Forty archives and one hundred articles leave no room for the required image.
    originals = [json.loads(p.read_text()) for p in state.rglob("manifests/*.json")]
    assert len([m for m in originals if m["retrieved_at"].startswith("2026-10-20")]) == 140
    validate(policy, state)


@pytest.mark.parametrize("url", [HOME, CURRENT, IMAGE])
def test_tru_unexpected_success_status_is_incomplete_not_invalid_persisted_obligation(
    tmp_path: Path,
    publication: tuple[Path, dict[str, Any]],
    url: str,
) -> None:
    policy, pages = publication
    state = tmp_path / "state"
    first = run(policy, state, 19)
    content = pages[url]
    if url == HOME:
        content = archive(extra=entry(NEW))
        pages[NEW] = article()
    pages[url] = HttpArtifact(
        content=content,
        status=201,
        canonical_url=url,
        redirect_chain=[],
        media_type="image/jpeg" if url == IMAGE else "text/html",
    )
    failed = run(policy, state, 20)
    assert failed["status"] == "failed" and failed["previous_snapshot_id"] == first["snapshot_id"]
    validate(policy, state)
