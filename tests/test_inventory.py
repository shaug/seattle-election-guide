import copy
import hashlib
from pathlib import Path
from typing import Any

import pytest
import yaml
from pydantic import ValidationError

from election_guide.inventory.importer import import_inventory, read_inventory
from election_guide.inventory.models import Inventory

FIXTURES = Path(__file__).parent / "fixtures" / "inventory"
PROJECT_ROOT = Path(__file__).parent.parent
INPUTS = {
    "candidates": FIXTURES / "candidates.csv",
    "pco_democrats": FIXTURES / "pco-democrats.csv",
    "pco_republicans": FIXTURES / "pco-republicans.csv",
    "precinct_crosswalk": FIXTURES / "precinct-crosswalk.csv",
}


def test_fixture_import_is_deterministic_and_scoped_to_seattle() -> None:
    first = import_inventory(FIXTURES / "config.yaml", INPUTS)
    second = import_inventory(FIXTURES / "config.yaml", INPUTS)

    assert first.model_dump_json() == second.model_dump_json()
    assert [race.id for race in first.races] == ["municipal-court-5", "pco-democratic-sea-43-0001"]
    assert sum(len(race.choices) for race in first.races) == 4
    assert first.coverage_checks[-1].matched_races == 0
    assert all(
        "Mailing" not in choice.model_dump_json() for race in first.races for choice in race.choices
    )


def test_import_rejects_unexpected_source_content(tmp_path: Path) -> None:
    changed_candidates = tmp_path / "candidates.csv"
    changed_candidates.write_text((FIXTURES / "candidates.csv").read_text() + "\n")
    changed_inputs = {**INPUTS, "candidates": changed_candidates}

    with pytest.raises(ValueError, match="SHA-256 mismatch"):
        import_inventory(FIXTURES / "config.yaml", changed_inputs)


def test_import_rejects_duplicate_source_bindings(tmp_path: Path) -> None:
    config = _fixture_config()
    duplicate = copy.deepcopy(config["sources"][0])
    duplicate["reference"]["id"] = "shadow-candidates"
    config["sources"].append(duplicate)

    with pytest.raises(ValueError, match="input source keys must be unique"):
        import_inventory(_write_config(tmp_path, config), INPUTS)


def test_import_rejects_misbound_pco_source(tmp_path: Path) -> None:
    config = _fixture_config()
    config["pco_imports"][0]["source_id"] = "candidates"

    with pytest.raises(ValueError, match="is bound to 'pco-democrats', not 'candidates'"):
        import_inventory(_write_config(tmp_path, config), INPUTS)


def test_import_rejects_duplicate_source_contest(tmp_path: Path) -> None:
    config = _fixture_config()
    duplicate = copy.deepcopy(config["race_selectors"][0])
    duplicate["id"] = "municipal-court-5-copy"
    config["race_selectors"].append(duplicate)
    config["sample_ballot_pages"]["municipal-court-5-copy"] = 1

    with pytest.raises(ValueError, match="unique source jurisdiction and office pairs"):
        import_inventory(_write_config(tmp_path, config), INPUTS)


def test_import_rejects_pco_precinct_outside_official_crosswalk(tmp_path: Path) -> None:
    config = _fixture_config()
    empty_crosswalk = tmp_path / "precinct-crosswalk.csv"
    empty_crosswalk.write_text("PrecinctName,CityName,SeattleCouncilDistrict\n", encoding="utf-8")
    config["sources"][3]["reference"]["sha256"] = hashlib.sha256(
        empty_crosswalk.read_bytes()
    ).hexdigest()
    inputs = {**INPUTS, "precinct_crosswalk": empty_crosswalk}

    with pytest.raises(ValueError, match="absent from the official Seattle crosswalk"):
        import_inventory(_write_config(tmp_path, config), inputs)


def test_import_rejects_conflicting_precinct_crosswalk_rows(tmp_path: Path) -> None:
    config = _fixture_config()
    conflicting_crosswalk = tmp_path / "precinct-crosswalk.csv"
    conflicting_crosswalk.write_text(
        "PrecinctName,CityName,SeattleCouncilDistrict\n"
        "SEA 43-0001,Seattle,3\n"
        "SEA 43-0001,Bellevue,\n",
        encoding="utf-8",
    )
    config["sources"][3]["reference"]["sha256"] = hashlib.sha256(
        conflicting_crosswalk.read_bytes()
    ).hexdigest()
    inputs = {**INPUTS, "precinct_crosswalk": conflicting_crosswalk}

    with pytest.raises(ValueError, match="precinct crosswalk repeats 'SEA 43-0001'"):
        import_inventory(_write_config(tmp_path, config), inputs)


def test_validation_rejects_choice_outside_its_race() -> None:
    payload = import_inventory(FIXTURES / "config.yaml", INPUTS).model_dump(mode="json")
    payload["races"][0]["choices"][0]["race_id"] = "another-race"

    with pytest.raises(ValidationError, match="belongs to 'another-race'"):
        Inventory.model_validate(payload)


def test_validation_rejects_race_outside_election() -> None:
    payload = import_inventory(FIXTURES / "config.yaml", INPUTS).model_dump(mode="json")
    payload["races"][0]["election_id"] = "another-election"

    with pytest.raises(ValidationError, match="belongs to 'another-election'"):
        Inventory.model_validate(payload)


def test_validation_rejects_impossible_race_choice_type() -> None:
    payload = import_inventory(FIXTURES / "config.yaml", INPUTS).model_dump(mode="json")
    payload["races"][0]["choices"][0]["choice_type"] = "ballot_option"

    with pytest.raises(ValidationError, match="requires 'candidate' choices"):
        Inventory.model_validate(payload)


def test_validation_rejects_empty_race_and_nonpositive_ballot_order() -> None:
    payload = import_inventory(FIXTURES / "config.yaml", INPUTS).model_dump(mode="json")
    empty_payload = copy.deepcopy(payload)
    empty_payload["races"][0]["choices"] = []
    with pytest.raises(ValidationError, match="must contain at least one ballot choice"):
        Inventory.model_validate(empty_payload)

    payload["races"][0]["choices"][0]["ballot_order"] = 0
    with pytest.raises(ValidationError, match="non-positive ballot order"):
        Inventory.model_validate(payload)


def test_validation_reconciles_coverage_counts() -> None:
    payload = import_inventory(FIXTURES / "config.yaml", INPUTS).model_dump(mode="json")
    payload["coverage_checks"][0]["matched_races"] = 9999

    with pytest.raises(ValidationError, match="reports 9999 races"):
        Inventory.model_validate(payload)


def test_committed_inventory_matches_retained_safe_inputs() -> None:
    extracted = PROJECT_ROOT / "data" / "extracted" / "official"
    inventory = import_inventory(
        PROJECT_ROOT / "config" / "elections" / "wa-2026-primary-inventory.yaml",
        {
            "candidates": extracted / "king-county-2026-primary-candidates.csv",
            "pco_democrats": extracted / "king-county-2026-primary-pco-democrats.csv",
            "pco_republicans": extracted / "king-county-2026-primary-pco-republicans.csv",
            "precinct_crosswalk": (extracted / "king-county-2026-seattle-precinct-crosswalk.csv"),
        },
    )
    committed = read_inventory(
        PROJECT_ROOT / "data" / "normalized" / "wa-2026-primary-inventory.json"
    )

    assert inventory == committed


def _fixture_config() -> dict[str, Any]:
    return yaml.safe_load((FIXTURES / "config.yaml").read_text(encoding="utf-8"))


def _write_config(tmp_path: Path, config: dict[str, Any]) -> Path:
    path = tmp_path / "config.yaml"
    path.write_text(yaml.safe_dump(config, sort_keys=False), encoding="utf-8")
    return path
