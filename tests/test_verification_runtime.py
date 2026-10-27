"""Scheduled runs demonstrate durable baselines, failure retention, and honest coverage."""

import json
import socket
import ssl
from datetime import datetime
from pathlib import Path
from typing import Any, cast

import pytest
import yaml
from typer.testing import CliRunner

from election_guide.cli import app
from election_guide.collection.http import DEADLINE_EXCEEDED, TOTAL_TIMEOUT_EXCEEDED

ROOT = Path(__file__).parents[1]
runner = CliRunner()


def setup_verification_fixture(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, source_id: str = "transit-riders-union"
) -> tuple[Path, Path, Path]:
    monkeypatch.delenv("ENDORSEMENT_EVIDENCE_KEY", raising=False)
    adapter = tmp_path / "adapter.yaml"
    adapter.write_text(
        yaml.safe_dump(
            {
                "source_id": source_id,
                "adapter_kind": "static_html",
                "extractor_version": "1.0.0",
                "complete": True,
                "decision_pattern": r"(?m)^Seattle City Council District 5: [^\n]+$",
                "rules": [
                    {
                        "race_id": "seattle-city-council-5",
                        "pattern": "Seattle City Council District 5: Nilu Jenks",
                        "candidate_ids": ["seattle-city-council-5--nilu-jenks"],
                        "evidence_locator": "Fixture endorsement list.",
                    }
                ],
            }
        )
    )
    policy = tmp_path / "policy.yaml"
    policy.write_text(
        yaml.safe_dump(
            {
                "schema_version": "1.0",
                "calendar": str(ROOT / "config/calendar/elections.yaml"),
                "elections": [
                    {
                        "election_id": "wa-2026-general",
                        "registry": str(ROOT / "config/sources/wa-2026-general.yaml"),
                        "inventory": str(ROOT / "data/normalized/wa-2026-general-inventory.json"),
                        "sources": [
                            {
                                "source_id": source_id,
                                "adapter": str(adapter),
                                "limitation": "Initial baseline requires a human spot-check.",
                            }
                        ],
                    }
                ],
            }
        )
    )
    fixtures = tmp_path / "fixtures"
    fixtures.mkdir()
    (fixtures / f"{source_id}.html").write_text(
        "<p>Seattle City Council District 5: Nilu Jenks</p>"
    )
    return policy, tmp_path / "state", fixtures


def run_fixture(policy: Path, state: Path, fixtures: Path, day: str) -> dict[str, Any]:
    result = runner.invoke(
        app,
        [
            "verification",
            "run",
            str(policy),
            "--state-root",
            str(state),
            "--fixtures",
            str(fixtures),
            "--checked-at",
            day + "T18:00:00Z",
        ],
    )
    assert result.exit_code == 0, result.output
    return cast(dict[str, Any], json.loads(result.output))


def test_independentrun_fixtures_reuse_committed_baseline_and_same_day_retry_is_idempotent(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    policy, state, fixtures = setup_verification_fixture(tmp_path, monkeypatch)
    first = run_fixture(policy, state, fixtures, "2026-10-05")
    assert first["automatic"][0]["status"] == "created"
    root = state / "wa-2026-general"
    previous = next((root / "extractions").glob("*.json")).read_bytes()
    assert not list(state.rglob("*.html"))
    second = run_fixture(policy, state, fixtures, "2026-10-06")
    assert second["automatic"][0]["status"] == "unchanged"
    assert second["automatic"][0]["previous_snapshot_id"] == first["automatic"][0]["snapshot_id"]
    assert next((root / "extractions").glob("*.json")).read_bytes() == previous
    before = {p: p.read_bytes() for p in root.rglob("*.json")}
    repeat = run_fixture(policy, state, fixtures, "2026-10-06")
    assert repeat["automatic"] == []
    assert {p: p.read_bytes() for p in root.rglob("*.json")} == before
    assert first["manual"]


def test_parser_break_preserves_prior_baseline_and_three_scheduled_failures_escalate(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    policy, state, fixtures = setup_verification_fixture(tmp_path, monkeypatch)
    first = run_fixture(policy, state, fixtures, "2026-10-05")
    snapshot = first["automatic"][0]["snapshot_id"]
    (fixtures / "transit-riders-union.html").write_text(
        "<p>The parser no longer sees the decisions.</p>"
    )
    for day in ("2026-10-06", "2026-10-07", "2026-10-08"):
        report = run_fixture(policy, state, fixtures, day)
        assert report["automatic"][0]["status"] == "failed"
        assert report["automatic"][0]["previous_snapshot_id"] == snapshot
        assert report["automatic"][0]["capture_id"] is not None
        assert report["automatic"][0]["error"] == "complete adapter detected no decision lines"
    assert report["automatic"][0]["consecutive_failures"] == 3
    assert report["automatic"][0]["escalated"] is True


@pytest.mark.parametrize("problem", ["denied", "network", "timeout", "empty", "incomplete"])
def test_failed_retrieval_keeps_verified_facts_and_later_review_can_add_endorsements(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, problem: str
) -> None:
    from election_guide.collection.http import HttpArtifact
    from election_guide.collection.verification import plan_verification, read_policy
    from election_guide.collection.verification_review import approve_baseline
    from election_guide.collection.verification_runtime import run_verification
    from election_guide.release import compile_release_dataset, verify_release_compilation

    # All responses/reviews here are controlled fixtures, not publisher access or adoption.
    source = "seiu-775"
    policy_path, state, _ = setup_verification_fixture(tmp_path, monkeypatch, source)
    policy = read_policy(policy_path)
    root = state / "wa-2026-general"
    response = b"<p>Seattle City Council District 5: Nilu Jenks</p>"
    calls: list[str] = []

    def fetch(url: str) -> HttpArtifact:
        calls.append(url)
        if len(calls) == 2 and problem == "denied":
            raise ValueError("live collection returned HTTP 403")
        if len(calls) == 2 and problem == "timeout":
            raise TimeoutError("Controlled fixture timeout")
        if len(calls) == 2 and problem == "network":
            raise ConnectionResetError("Controlled fixture connection reset")
        return HttpArtifact(response, 200, url, [], "text/html")

    monkeypatch.setattr("election_guide.collection.verification_runtime.fetch_http", fetch)

    def run(day: int) -> dict[str, Any]:
        return run_verification(
            policy,
            state,
            datetime.fromisoformat(f"2026-10-{day}T18:00:00+00:00"),
            live=True,
            fixtures=None,
        )

    baseline = run(26)["automatic"][0]
    approve_baseline(
        root,
        baseline["snapshot_id"],
        "Fixture original reviewer",
        datetime.fromisoformat("2026-10-26T19:00:00+00:00"),
        "Complete fixture publication/mappings.",
    )
    archive_before = {p: p.read_bytes() for p in root.rglob("*.json")}
    registry = ROOT / "config/sources/wa-2026-general.yaml"
    inventory = ROOT / "data/normalized/wa-2026-general-inventory.json"
    ledger = tmp_path / "release-ledger.yaml"
    payload: dict[str, Any] = {
        "schema_version": "1.0",
        "election_id": "wa-2026-general",
        "data_as_of": "2026-10-28T20:00:00Z",
        "reviewer": "Fixture reviewer",
        "review_note": "Controlled complete-publication fixture, no publisher request.",
        "sources": [
            {
                "source_id": source,
                "captured_at": "2026-10-26T18:00:00Z",
                "reviewed_at": "2026-10-26T19:00:00Z",
                "evidence_locator": "Fixture full list.",
                "decisions": [
                    {
                        "race_id": "seattle-city-council-5",
                        "candidate_ids": ["seattle-city-council-5--nilu-jenks"],
                    }
                ],
            }
        ],
    }
    ledger.write_text(yaml.safe_dump(payload))
    canonical = tmp_path / "canonical.json"
    snapshots, manifests = tmp_path / "snapshots", tmp_path / "manifests"
    accepted = compile_release_dataset(ledger, inventory, registry, canonical, snapshots, manifests)
    canonical_before = canonical.read_bytes()
    if problem == "empty":
        response = b""
    elif problem == "incomplete":
        response += b"<p>Seattle City Council District 5: Unmapped Choice</p>"
    failed = run(27)["automatic"][0]
    assert failed["status"] == "failed" and failed["snapshot_id"] is None
    assert failed["previous_snapshot_id"] == baseline["snapshot_id"]
    assert failed["consecutive_failures"] == 1 and failed["escalated"] is False
    assert all(p.read_bytes() == raw for p, raw in archive_before.items())
    lane = next(
        c
        for c in plan_verification(policy, state, datetime(2026, 10, 27).date())
        .elections[0]
        .coverage
        if c.source_id == source
    )
    assert lane.last_successful_check == datetime.fromisoformat("2026-10-26T18:00:00+00:00")
    assert lane.latest_attempt is not None and lane.latest_attempt.status == "failed"
    assert lane.next_due.isoformat() == "2026-10-28"
    assert (
        verify_release_compilation(ledger, inventory, registry, canonical, snapshots, manifests)
        == accepted
    )
    assert canonical.read_bytes() == canonical_before
    assert run(27)["automatic"] == [] and len(calls) == 2

    # A later complete fixture adds a reviewed mapping; missing input never removed the old one.
    adapter_path = tmp_path / "adapter.yaml"
    adapter = yaml.safe_load(adapter_path.read_text())
    adapter["decision_pattern"] = (
        r"(?m)^(?:Seattle City Council District 5|King County Assessor): [^\n]+$"
    )
    adapter["rules"].append(
        {
            "race_id": "king-county-assessor",
            "pattern": "King County Assessor: Rob Foxcurran",
            "candidate_ids": ["king-county-assessor--rob-foxcurran"],
            "evidence_locator": "Later complete fixture publication.",
        }
    )
    adapter_path.write_text(yaml.safe_dump(adapter))
    response = (
        b"<p>Seattle City Council District 5: Nilu Jenks</p>"
        b"<p>King County Assessor: Rob Foxcurran</p>"
    )
    later = run(28)["automatic"][0]
    assert later["status"] == "updated" and later["baseline_reviewed"] is False
    assert [(d["kind"], d["race_id"]) for d in later["diff"]] == [("added", "king-county-assessor")]
    assert (
        canonical.read_bytes() == canonical_before
    )  # Extraction alone changes no canonical facts.
    approve_baseline(
        root,
        later["snapshot_id"],
        "Fixture later reviewer",
        datetime.fromisoformat("2026-10-28T19:00:00+00:00"),
        "Complete added-mapping fixture review.",
    )
    payload["sources"][0]["decisions"].append(
        {
            "race_id": "king-county-assessor",
            "candidate_ids": ["king-county-assessor--rob-foxcurran"],
            "captured_at": "2026-10-28T18:00:00Z",
            "reviewed_at": "2026-10-28T19:00:00Z",
            "reviewer": "Fixture later reviewer",
            "review_note": "Reviewed added fixture endorsement.",
            "evidence_url": "https://seiu775.org/endorsements/",
            "evidence_locator": "Later complete fixture publication, named office.",
        }
    )
    ledger.write_text(yaml.safe_dump(payload))
    updated = compile_release_dataset(ledger, inventory, registry, canonical, snapshots, manifests)
    assert len(updated.endorsements) == 2 and accepted.endorsements[0] in updated.endorsements
    assert all(p.read_bytes() == raw for p, raw in archive_before.items())


def test_missing_scheduled_events_are_visible_even_without_a_source_job_record(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    policy, state, fixtures = setup_verification_fixture(tmp_path, monkeypatch)
    run_fixture(policy, state, fixtures, "2026-10-05")
    result = runner.invoke(
        app,
        ["verification", "plan", str(policy), "--state-root", str(state), "--as-of", "2026-10-07"],
    )
    assert result.exit_code == 0, result.output
    report = json.loads(result.output)
    assert {item["scheduled_for"] for item in report["missed"]} == {"2026-10-06"}
    assert "transit-riders-union" in {item["source_id"] for item in report["missed"]}


def test_fixture_baseline_cannot_be_human_approved_and_manual_review_is_explicit(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    policy, state, fixtures = setup_verification_fixture(tmp_path, monkeypatch)
    report = run_fixture(policy, state, fixtures, "2026-10-05")
    snapshot = report["automatic"][0]["snapshot_id"]
    root = state / "wa-2026-general"
    result = runner.invoke(
        app,
        [
            "verification",
            "approve-baseline",
            str(root),
            "--snapshot-id",
            snapshot,
            "--reviewer",
            "fixture-human",
            "--reviewed-at",
            "2026-10-05T19:00:00Z",
            "--evidence",
            "https://example.test/review",
        ],
    )
    assert result.exit_code != 0 and "only an executed live baseline" in result.output
    assert not (root / "approvals").exists()
    source = report["manual"][0]["source_id"]
    result = runner.invoke(
        app,
        [
            "verification",
            "acknowledge-manual",
            str(root),
            "--source-id",
            source,
            "--scheduled-for",
            "2026-10-05",
            "--reviewer",
            "fixture-human",
            "--reviewed-at",
            "2026-10-05T19:00:00Z",
            "--evidence",
            "https://example.test/review",
        ],
    )
    assert result.exit_code == 0, result.output
    result = runner.invoke(
        app,
        ["verification", "plan", str(policy), "--state-root", str(state), "--as-of", "2026-10-05"],
    )
    assert result.exit_code == 0, result.output
    coverage = json.loads(result.output)["elections"][0]["coverage"]
    assert (
        next(item for item in coverage if item["source_id"] == source)["last_successful_check"]
        == "2026-10-05T19:00:00Z"
    )
    assert (
        next(item for item in coverage if item["source_id"] == "transit-riders-union")[
            "last_successful_check"
        ]
        is None
    )


def test_legacy_mixed_history_reuses_exact_review_without_restored_pages(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import shutil
    from datetime import date, datetime

    from election_guide.collection.refresh import read_adapter_spec, refresh_source
    from election_guide.collection.vault import seal_store
    from election_guide.collection.verification import CheckRecord, read_policy
    from election_guide.collection.verification_review import approve_baseline
    from election_guide.collection.verification_runtime import record_check
    from election_guide.collection.verification_state import validate_state
    from election_guide.evidence.models import CaptureRequest

    policy_path, state, fixtures = setup_verification_fixture(tmp_path, monkeypatch)
    policy = read_policy(policy_path)
    root = state / "wa-2026-general"
    storage = tmp_path / "legacy-private"
    event = refresh_source(
        read_adapter_spec(tmp_path / "adapter.yaml"),
        CaptureRequest(
            source_id="transit-riders-union",
            requested_url="https://transitriders.org/",
            canonical_url="https://transitriders.org/",
            title="Authored legacy fixture",
            retrieved_at=datetime.fromisoformat("2026-10-05T18:00:00+00:00"),
            media_type="text/html",
            capture_method="static_html",
            http_status=200,
            redistribution="restricted",
            redistribution_note="Synthetic legacy ciphertext.",
        ),
        fixtures / "transit-riders-union.html",
        storage_root=storage,
        manifest_dir=root / "manifests",
        extraction_dir=root / "extractions",
        refresh_dir=root / "refreshes",
    )
    seal_store(storage, root / "vault", bytes(range(32)))
    record_check(
        root,
        CheckRecord(
            source_id=event.source_id,
            scheduled_for=date(2026, 10, 5),
            checked_at=event.checked_at,
            status=event.status,
            event_id=event.id,
            mode="live",
        ),
    )
    assert event.snapshot_id is not None
    approve_baseline(
        root,
        event.snapshot_id,
        "Named fixture reviewer",
        datetime.fromisoformat("2026-10-05T19:00:00+00:00"),
        "Authored HTTP fixture only; not actual official-source approval.",
    )
    history = {p.relative_to(state): p.read_bytes() for p in state.rglob("*.json")}
    approval = json.loads((root / "approvals" / f"{event.snapshot_id}.json").read_text())
    assert approval["reviewer"] == "Named fixture reviewer"
    assert approval["reviewed_at"] == "2026-10-05T19:00:00Z"
    shutil.rmtree(storage)
    independent = tmp_path / "independent"
    shutil.copytree(state, independent)
    second = run_fixture(policy_path, independent, fixtures, "2026-10-06")["automatic"][0]
    assert second["status"] == "unchanged" and second["baseline_reviewed"] is True
    assert second["snapshot_id"] == event.snapshot_id and second["capture_id"] != event.capture_id
    assert len(list(independent.rglob("approvals/*.json"))) == 1
    for relative, raw in history.items():
        assert (independent / relative).read_bytes() == raw
    assert set(p.relative_to(independent) for p in independent.rglob("vault/**/*.json")) == {
        p for p in history if "vault" in p.parts
    }
    validate_state(policy, independent)
    (fixtures / "transit-riders-union.html").write_text(
        "<p>Seattle City Council District 5: Nilu Jenks</p><p>Authored new wording.</p>"
    )
    changed = run_fixture(policy_path, independent, fixtures, "2026-10-07")["automatic"][0]
    assert changed["status"] == "updated" and changed["baseline_reviewed"] is False
    unchanged = run_fixture(policy_path, independent, fixtures, "2026-10-08")["automatic"][0]
    assert unchanged["status"] == "unchanged" and unchanged["baseline_reviewed"] is False
    assert unchanged["snapshot_id"] == changed["snapshot_id"]
    assert len(list(independent.rglob("approvals/*.json"))) == 1
    validate_state(policy, independent)


@pytest.mark.parametrize("corruption", ["source", "hash", "time"])
def test_current_observation_must_match_successful_event_and_reused_facts(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, corruption: str
) -> None:
    from datetime import datetime

    from election_guide.collection.verification import read_policy
    from election_guide.collection.verification_state import validate_state
    from election_guide.evidence.models import CaptureRequest, evidence_fingerprint
    from election_guide.evidence.storage import record_observation

    policy, state, fixtures = setup_verification_fixture(tmp_path, monkeypatch)
    run_fixture(policy, state, fixtures, "2026-10-05")
    event = run_fixture(policy, state, fixtures, "2026-10-06")["automatic"][0]
    root = state / "wa-2026-general"
    observed = json.loads((root / "manifests" / f"{event['capture_id']}.json").read_text())
    request = CaptureRequest.model_validate(
        {
            k: v
            for k, v in observed.items()
            if k not in {"id", "availability", "content_sha256", "byte_length"}
        }
    )
    if corruption == "source":
        request = request.model_copy(update={"source_id": "sage-leaders"})
    elif corruption == "time":
        request = request.model_copy(
            update={"retrieved_at": datetime.fromisoformat("2026-10-07T18:00:00+00:00")}
        )
    body = tmp_path / "input.html"
    body.write_bytes(
        b"<p>Different authored content.</p>"
        if corruption == "hash"
        else (fixtures / "transit-riders-union.html").read_bytes()
    )
    observation = record_observation(request, body, root / "manifests")
    path = root / "refreshes" / f"{event['id']}.json"
    record = json.loads(path.read_text())
    record["capture_id"] = observation.stem
    payload = {k: v for k, v in record.items() if k != "id"}
    record["id"] = record["id"].rsplit("-", 1)[0] + "-" + evidence_fingerprint(payload)[:12]
    path.unlink()
    path.with_name(f"{record['id']}.json").write_text(json.dumps(record))
    message = {
        "source": "observation belongs to another source",
        "hash": "matching observation",
        "time": "observation time",
    }[corruption]
    with pytest.raises(ValueError, match=message):
        validate_state(read_policy(policy), state)


_SENSITIVE_FAILURE = "PRIVATE_BODY /private/input.html token=secret https://user:pass@example.test/"


def _wrapped_http_failure(cause: Exception) -> ValueError:
    from election_guide.collection.http import FAILURE_PREFIX

    error = ValueError(FAILURE_PREFIX + str(cause))
    error.__cause__ = cause
    return error


@pytest.mark.parametrize(
    ("error", "diagnostic"),
    [
        (
            ValueError("live collection failed: live collection returned HTTP 403"),
            "category=http_status; status=403",
        ),
        (
            ValueError("live collection failed: live collection returned HTTP 503"),
            "category=http_status; status=503",
        ),
        (
            ValueError("live collection failed: " + DEADLINE_EXCEEDED),
            "category=deadline",
        ),
        (ValueError(TOTAL_TIMEOUT_EXCEEDED), "category=deadline"),
        (_wrapped_http_failure(TimeoutError(_SENSITIVE_FAILURE)), "category=deadline"),
        (_wrapped_http_failure(socket.gaierror(-2, _SENSITIVE_FAILURE)), "category=dns"),
        (_wrapped_http_failure(ssl.SSLError(_SENSITIVE_FAILURE)), "category=tls"),
        (_wrapped_http_failure(ConnectionResetError(_SENSITIVE_FAILURE)), "category=network"),
        (
            ValueError("live collection failed: live collection exceeded 10 redirects"),
            "category=redirect",
        ),
        (
            ValueError(
                "live collection failed: live collection refuses an HTTPS downgrade redirect"
            ),
            "category=redirect",
        ),
        (
            ValueError("live collection failed: live collection refuses a POST redirect"),
            "category=redirect",
        ),
        (
            ValueError("live collection failed: redirect response has no Location header"),
            "category=redirect",
        ),
        (
            ValueError("live collection failed: live artifact has an invalid Content-Length"),
            "category=response_integrity",
        ),
        (
            ValueError("live collection failed: live artifact exceeds the 25 MiB limit"),
            "category=response_integrity",
        ),
        (
            ValueError("live collection failed: live artifact is empty"),
            "category=response_integrity",
        ),
        (
            ValueError(
                "live collection failed: live artifact was truncated: expected 42 bytes, got 7"
            ),
            "category=response_integrity",
        ),
        (
            ValueError(
                "live collection failed: live collection refuses non-public address '127.0.0.1'"
            ),
            "category=public_peer",
        ),
        (
            ValueError(
                "live collection failed: live collection peer has invalid address 'PRIVATE_BODY'"
            ),
            "category=public_peer",
        ),
        (
            ValueError(
                "live collection failed: live collection DNS resolution returned no addresses "
                "for 'PRIVATE_BODY'"
            ),
            "category=dns",
        ),
        (ValueError(_SENSITIVE_FAILURE), "category=unknown"),
        (ValueError("live collection returned HTTP 403 " + _SENSITIVE_FAILURE), "category=unknown"),
        (ValueError("live collection returned HTTP 0403"), "category=unknown"),
        (ValueError("live collection returned HTTP 999"), "category=unknown"),
        (ValueError("live collection returned HTTP \uff14\uff10\uff13"), "category=unknown"),
    ],
)
def test_direct_http_failure_retains_only_allowlisted_diagnostic_and_prior_baseline(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, error: Exception, diagnostic: str
) -> None:
    from election_guide.collection.verification import read_policy
    from election_guide.collection.verification_runtime import run_verification

    policy_path, state, fixtures = setup_verification_fixture(tmp_path, monkeypatch, "seiu-775")
    baseline = run_fixture(policy_path, state, fixtures, "2026-10-05")["automatic"][0]
    history = {p: p.read_bytes() for p in state.rglob("*.json")}

    def fetch(url: str) -> None:
        raise error

    monkeypatch.setattr("election_guide.collection.verification_runtime.fetch_http", fetch)
    for day in (6, 7, 8):
        report = run_verification(
            read_policy(policy_path),
            state,
            datetime.fromisoformat(f"2026-10-{day:02}T18:00:00+00:00"),
            live=True,
            fixtures=None,
        )
        failed = report["automatic"][0]
        assert failed["error"] == f"Source check failed (stage=http_fetch; {diagnostic})."
        assert failed["status"] == "failed"
        assert failed["previous_snapshot_id"] == baseline["snapshot_id"]
        assert failed["capture_id"] is None and failed["snapshot_id"] is None
        assert failed["content_changed"] is None and failed["diff"] == []
        assert failed["consecutive_failures"] == day - 5
        assert failed["escalated"] is (day == 8)
    for path, original in history.items():
        assert path.read_bytes() == original
    persisted = "".join(p.read_text() for p in state.rglob("*.json"))
    assert _SENSITIVE_FAILURE not in persisted and "PRIVATE_BODY" not in persisted


@pytest.mark.parametrize("stage", ["post_fetch_preparation", "refresh", "other"])
def test_non_fetch_failures_do_not_claim_http_failure_or_leak_exception(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, stage: str
) -> None:
    from election_guide.collection.http import HttpArtifact
    from election_guide.collection.verification import read_policy
    from election_guide.collection.verification_runtime import run_verification

    policy_path, state, fixtures = setup_verification_fixture(tmp_path, monkeypatch, "seiu-775")
    baseline = run_fixture(policy_path, state, fixtures, "2026-10-05")["automatic"][0]
    body = (fixtures / "seiu-775.html").read_bytes()

    def fetch(url: str) -> HttpArtifact:
        return HttpArtifact(body, 200, url, [], "text/html")

    def fail(*args: Any, **kwargs: Any) -> None:
        raise ValueError("live collection returned HTTP 403") from ValueError(_SENSITIVE_FAILURE)

    monkeypatch.setattr("election_guide.collection.verification_runtime.fetch_http", fetch)
    if stage == "post_fetch_preparation":
        monkeypatch.setattr(
            "election_guide.collection.verification_runtime.read_adapter_spec", fail
        )
    elif stage == "refresh":
        monkeypatch.setattr("election_guide.collection.verification_runtime.refresh_source", fail)
    else:
        (fixtures / "seiu-775.html").unlink()
    report = run_verification(
        read_policy(policy_path),
        state,
        datetime.fromisoformat("2026-10-06T18:00:00+00:00"),
        live=stage != "other",
        fixtures=fixtures if stage == "other" else None,
    )
    failed = report["automatic"][0]
    assert failed["error"] == f"Source check failed (stage={stage}; category=unknown)."
    assert failed["status"] == "failed"
    assert failed["previous_snapshot_id"] == baseline["snapshot_id"]
    # Null capture does not assert that fetching failed: two cases fetched above.
    assert failed["capture_id"] is None and failed["content_changed"] is None
    assert _SENSITIVE_FAILURE not in json.dumps(report)
