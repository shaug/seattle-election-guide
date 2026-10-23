"""Scheduled runs demonstrate durable baselines, failure retention, and honest coverage."""

import json
from pathlib import Path
from typing import Any, cast

import pytest
import yaml
from typer.testing import CliRunner

from election_guide.cli import app

ROOT = Path(__file__).parents[1]
runner = CliRunner()


def setup_verification_fixture(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> tuple[Path, Path, Path]:
    monkeypatch.delenv("ENDORSEMENT_EVIDENCE_KEY", raising=False)
    adapter = tmp_path / "adapter.yaml"
    adapter.write_text(
        yaml.safe_dump(
            {
                "source_id": "transit-riders-union",
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
                                "source_id": "transit-riders-union",
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
    (fixtures / "transit-riders-union.html").write_text(
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
    assert report["automatic"][0]["consecutive_failures"] == 3
    assert report["automatic"][0]["escalated"] is True


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
