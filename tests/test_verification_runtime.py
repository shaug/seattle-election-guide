"""Scheduled runs demonstrate durable baselines, failure retention, and honest coverage."""

import base64
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
    monkeypatch.setenv("ENDORSEMENT_EVIDENCE_KEY", base64.b64encode(bytes(range(32))).decode())
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
