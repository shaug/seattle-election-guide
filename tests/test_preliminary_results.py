"""Offline preliminary admission; all counts and source IDs below are synthetic."""

import json
from copy import deepcopy
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
import yaml
from typer.testing import CliRunner

from election_guide.calendar.watch import read_repository_artifacts
from election_guide.cli import app
from election_guide.evidence.models import CaptureRequest
from election_guide.evidence.storage import record_capture
from election_guide.inventory.importer import read_inventory
from election_guide.publication.models import PublicationViewModel
from election_guide.rendering.config import read_rendering_configuration
from election_guide.rendering.documents import render_comparison_document, render_html_document
from election_guide.results.loader import read_results, reject_committed_counting_status
from election_guide.results.validation import validate_results_inventory
from tests.test_precinct_rendering import general_view as general_view
from tests.test_rendering import _client_payload, _race_card_html  # pyright: ignore[reportPrivateUsage]

ROOT = Path(__file__).parents[1]
INVENTORY = ROOT / "data/normalized/wa-2026-general-inventory.json"


def preliminary_document() -> dict[str, Any]:
    """Whole synthetic inventory, not a production source/coverage admission."""
    inventory = read_inventory(INVENTORY)
    reference = "data/manifests/evidence/synthetic-preliminary.json"
    return {
        "schema_version": "1.1",
        "election_id": inventory.election.id,
        "status": "preliminary",
        "captures": [
            {
                "kind": "preliminary",
                "authority_id": "wa-secretary-of-state",
                "captured_at": "2026-11-04T05:00:00Z",
                "evidence": reference,
            }
        ],
        "races": [
            {
                "race_id": race.id,
                "jurisdiction_id": race.jurisdiction_id,
                "source_contest_id": f"synthetic-{race.id}",
                "coverage": "whole_jurisdiction",
                "coverage_evidence": reference,
                "authority_id": "wa-secretary-of-state",
                "authority": "Washington Secretary of State",
                "capture_evidence": reference,
                "reported_at": "2026-11-04T04:00:00Z",
                "reporting_complete": False,
                "ballots_counted": 100 * len(race.choices) + 20,
                "write_in_votes": 10,
                "outcomes": [{"choice_id": choice.id, "votes": 100} for choice in race.choices],
            }
            for race in inventory.races
        ],
    }


def read_document(tmp_path: Path, document: dict[str, Any]):
    path = tmp_path / "results.yaml"
    path.write_text(yaml.safe_dump(document))
    return read_results(path)


def test_whole_jurisdiction_count_so_far_is_admitted_without_certification(tmp_path: Path) -> None:
    results = read_document(tmp_path, preliminary_document())
    validate_results_inventory(results, read_inventory(INVENTORY))
    reject_committed_counting_status(results)
    assert results.status == "preliminary"
    assert len(results.races) == 52
    dumped = results.model_dump(mode="json")
    assert "certified_on" not in dumped
    assert "advanced" not in dumped["races"][0]["outcomes"][0]
    assert dumped["races"][0]["reporting_complete"] is False


@pytest.mark.parametrize(
    "field,value,match",
    [
        ("coverage", "county_subset", "whole_jurisdiction"),
        ("reported_at", "2026-11-04T06:00:00Z", "count timestamp"),
        ("reported_at", "2026-11-04T04:00:00", "timezone"),
        ("authority_id", "king-county-elections", "authority"),
    ],
)
def test_unproved_scope_or_clock_cannot_become_preliminary_results(
    tmp_path: Path, field: str, value: str, match: str
) -> None:
    document = preliminary_document()
    document["races"][0][field] = value
    with pytest.raises(ValueError, match=match):
        read_document(tmp_path, document)


def test_missing_race_or_named_choice_cannot_masquerade_as_complete_results(tmp_path: Path) -> None:
    document = preliminary_document()
    missing_race = deepcopy(document)
    missing_race["races"].pop()
    with pytest.raises(ValueError, match="every inventory race"):
        validate_results_inventory(read_document(tmp_path, missing_race), read_inventory(INVENTORY))
    contested = next(race for race in document["races"] if len(race["outcomes"]) > 1)
    contested["outcomes"].pop()
    with pytest.raises(ValueError, match="every named ballot choice"):
        validate_results_inventory(read_document(tmp_path, document), read_inventory(INVENTORY))


def test_duplicate_or_winner_fields_are_not_preliminary_input(tmp_path: Path) -> None:
    document = preliminary_document()
    document["races"][0]["outcomes"][0]["advanced"] = True
    with pytest.raises(ValueError, match="Extra inputs"):
        read_document(tmp_path, document)


def test_preliminary_zero_count_and_write_ins_remain_separate(tmp_path: Path) -> None:
    document = preliminary_document()
    race = document["races"][0]
    race["ballots_counted"] = 0
    race["write_in_votes"] = 0
    for outcome in race["outcomes"]:
        outcome["votes"] = 0
    results = read_document(tmp_path, document)
    assert results.races[0].outcomes[0].votes == 0
    # Shares are derived from named counts; zero is not a fabricated 100%.
    assert "share" not in results.model_dump(mode="json")["races"][0]["outcomes"][0]


def test_preliminary_general_result_reuses_tally_without_calling_outcomes(
    tmp_path: Path, general_view: PublicationViewModel
) -> None:
    results = read_document(tmp_path, preliminary_document())
    view = general_view.model_copy(update={"results": results})
    html = render_html_document(
        view, read_rendering_configuration(ROOT / "config/rendering/guide.yaml")
    )
    card = _race_card_html(html, "king-county-assessor")
    assert "Unofficial · Nov 3, 8:00:00 p.m. PST" in card
    assert card.count('class="race-results-row"') == 2
    assert card.count('style="width:50.0%"') == 2
    assert "220 ballots" in card
    assert "race-results-row-trailing" not in card
    assert "race-detail-result-chip" not in card
    assert "Unofficial results · counting continues" in html
    # County's scheduled certification date is not a proved statewide promise.
    assert "Results certify November 24" not in html


def test_preliminary_results_never_enable_the_certified_comparison_column(
    tmp_path: Path, general_view: PublicationViewModel
) -> None:
    view = general_view.model_copy(
        update={"results": read_document(tmp_path, preliminary_document())}
    )
    html = render_comparison_document(view, public_site_url="https://seattleelections.guide")
    payload = _client_payload(html)
    assert payload["results_available"] is False
    assert payload["race_results"] == {}


def test_preliminary_file_does_not_satisfy_future_certified_ingestion(tmp_path: Path) -> None:
    directory = tmp_path / "results"
    directory.mkdir()
    (directory / "wa-2026-general.yaml").write_text(yaml.safe_dump(preliminary_document()))
    artifacts = read_repository_artifacts(
        manifest_dir=tmp_path / "manifests",
        refresh_dir=tmp_path / "refreshes",
        results_dir=directory,
    )
    assert "wa-2026-general" not in artifacts.ingested_election_ids


def captured_document(tmp_path: Path) -> dict[str, Any]:
    document = preliminary_document()
    artifact = tmp_path / "synthetic-official.json"
    artifact.write_text('{"fixture":"synthetic offline evidence"}')
    manifest = record_capture(
        CaptureRequest(
            source_id="wa-secretary-of-state",
            requested_url="https://example.org/synthetic-results",
            canonical_url="https://example.org/synthetic-results",
            retrieved_at=datetime(2026, 11, 4, 5, tzinfo=UTC),
            media_type="application/json",
            title="Synthetic test only",
            http_status=200,
            capture_method="manual_upload",
            redistribution="permitted",
            redistribution_note="Synthetic fixture, no official count claim.",
        ),
        artifact,
        tmp_path / "data/evidence/official",
        tmp_path / "data/manifests/evidence",
        repository_storage_root=tmp_path / "data/evidence/official",
    )
    reference = manifest.relative_to(tmp_path).as_posix()
    document["captures"][0]["evidence"] = reference
    for race in document["races"]:
        race["capture_evidence"] = reference
        race["coverage_evidence"] = reference
    registry = tmp_path / "config/authorities/default.yaml"
    registry.parent.mkdir(parents=True)
    registry.write_bytes((ROOT / "config/authorities/default.yaml").read_bytes())
    return document


def test_cli_selects_general_inventory_and_validates_real_capture_clock(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    document = captured_document(tmp_path)
    inventory = tmp_path / "data/normalized/wa-2026-general-inventory.json"
    inventory.parent.mkdir(parents=True)
    inventory.write_bytes(INVENTORY.read_bytes())
    results_path = tmp_path / "results.yaml"
    results_path.write_text(yaml.safe_dump(document))
    monkeypatch.chdir(tmp_path)
    result = CliRunner().invoke(app, ["results", "validate", str(results_path)])
    assert result.exit_code == 0, result.output
    assert "wa-2026-general, preliminary, 52 races" in result.output
    document["captures"][0]["captured_at"] = "2026-11-04T05:01:00Z"
    results_path.write_text(yaml.safe_dump(document))
    result = CliRunner().invoke(app, ["results", "validate", str(results_path)])
    assert result.exit_code != 0
    assert "actual capture clock" in result.output


def test_preliminary_admission_requires_original_bytes_and_registered_authority(
    tmp_path: Path,
) -> None:
    from election_guide.results.validation import validate_results_evidence

    document = captured_document(tmp_path)
    results = read_document(tmp_path, document)
    manifest = json.loads((tmp_path / document["captures"][0]["evidence"]).read_text())
    original = tmp_path / "data/evidence/official" / manifest["storage_reference"]
    original.write_text("corrupted synthetic original")
    with pytest.raises(ValueError, match="hash mismatch"):
        validate_results_evidence(results, repository_root=tmp_path)
