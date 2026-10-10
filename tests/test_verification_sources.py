"""The public runner checks the six current-election factual fixtures."""

import base64
import json
from pathlib import Path

import pytest
import yaml
from typer.testing import CliRunner

from election_guide.cli import app

ROOT = Path(__file__).parents[1]
runner = CliRunner()


def test_six_general_sources_match_reviewed_facts_and_cover_all_eligible_sources(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ENDORSEMENT_EVIDENCE_KEY", base64.b64encode(bytes(range(32))).decode())
    result = runner.invoke(
        app,
        [
            "verification",
            "run",
            "config/verification.yaml",
            "--fixtures",
            "tests/fixtures/verification",
            "--state-root",
            str(tmp_path / "state"),
            "--checked-at",
            "2026-10-05T18:00:00Z",
        ],
    )
    assert result.exit_code == 0, result.output
    report = json.loads(result.output)
    expected = yaml.safe_load(
        (ROOT / "data/releases/wa-2026-general/source-decisions.yaml").read_text()
    )
    assert len(report["automatic"]) == 6
    for event in report["automatic"]:
        assert event["status"] == "created", event
        assert event["baseline_reviewed"] is False
        ledger = next(s for s in expected["sources"] if s["source_id"] == event["source_id"])
        assert {d["race_id"]: set(d["after"]["candidate_ids"]) for d in event["diff"]} == {
            d["race_id"]: set(d["candidate_ids"]) for d in ledger["decisions"]
        }
    coverage = report["coverage"]["elections"][0]["coverage"]
    assert len(coverage) == 43
    assert {s["source_id"] for s in coverage if s["lane"] == "manual"} == {
        s["source_id"] for s in report["manual"]
    }
