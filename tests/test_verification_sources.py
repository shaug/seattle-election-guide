"""The public runner checks the six current-election factual fixtures."""

import base64
import json
import shutil
from pathlib import Path

import pytest
import yaml
from typer.testing import CliRunner

from election_guide.cli import app

ROOT = Path(__file__).parents[1]
runner = CliRunner()


@pytest.mark.parametrize("source_id", ["washington-working-families-party", "seiu-775"])
def test_current_publication_layout_preserves_reviewed_decisions(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    source_id: str,
) -> None:
    monkeypatch.setenv("ENDORSEMENT_EVIDENCE_KEY", base64.b64encode(bytes(range(32))).decode())
    fixtures = tmp_path / "fixtures"
    shutil.copytree(ROOT / "tests/fixtures/verification", fixtures)
    (fixtures / f"{source_id}.html").write_bytes(
        (fixtures / f"{source_id}-current-layout.html").read_bytes()
    )
    result = runner.invoke(
        app,
        [
            "verification",
            "run",
            "config/verification.yaml",
            "--fixtures",
            str(fixtures),
            "--state-root",
            str(tmp_path / "state"),
            "--checked-at",
            "2026-10-15T18:00:00Z",
        ],
    )
    assert result.exit_code == 0, result.output
    event = next(e for e in json.loads(result.output)["automatic"] if e["source_id"] == source_id)
    assert event["status"] == "created", event
    expected = yaml.safe_load((fixtures / "reviewed-decisions.yaml").read_text())
    reviewed = next(s for s in expected["sources"] if s["source_id"] == source_id)
    assert {d["race_id"]: set(d["after"]["candidate_ids"]) for d in event["diff"]} == {
        d["race_id"]: set(d["candidate_ids"]) for d in reviewed["decisions"]
    }
    assert event["baseline_reviewed"] is False


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
        (ROOT / "tests/fixtures/verification/reviewed-decisions.yaml").read_text()
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
    assert len(coverage) == 46
    assert {
        "young-democrats-of-washington",
        "nondriver-action",
        "citizens-against-aipac-corruption",
    } <= {s["source_id"] for s in coverage if s["lane"] == "manual"}
    assert {s["source_id"] for s in coverage if s["lane"] == "manual"} == {
        s["source_id"] for s in report["manual"]
    }


def test_wfp_complete_publication_extracts_all_ten_reviewed_choices() -> None:
    from election_guide.collection.adapters import extract_decisions
    from election_guide.collection.refresh import read_adapter_spec

    spec = read_adapter_spec(
        ROOT / "config/adapters/wa-2026-general/washington-working-families-party.yaml"
    )
    decisions = extract_decisions(
        spec,
        (ROOT / "tests/fixtures/verification/washington-working-families-party.html").read_bytes(),
        media_type="text/html",
    )
    assert {d.race_id: d.candidate_ids for d in decisions} == {
        "us-house-7": ["us-house-7--pramila-jayapal"],
        "king-county-council-4": ["king-county-council-4--jorge-l-baron"],
        "king-county-council-8": ["king-county-council-8--teresa-mosqueda"],
        "seattle-city-council-5": ["seattle-city-council-5--nilu-jenks"],
        "ld-37-state-representative-1": ["ld-37-state-representative-1--kelabe-tewolde"],
        "ld-37-state-representative-2": ["ld-37-state-representative-2--jaelynn-scott"],
        "ld-43-state-representative-2": ["ld-43-state-representative-2--shaun-scott"],
        "ld-46-state-representative-2": ["ld-46-state-representative-2--darya-farivar"],
        "ld-36-state-senator": ["ld-36-state-senator--noel-c-frame"],
        "ld-43-state-senator": ["ld-43-state-senator--hannah-sabio-howell"],
    }
