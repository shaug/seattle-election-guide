from pathlib import Path

import pytest
from pydantic import ValidationError

from election_guide.inventory.importer import import_inventory
from election_guide.inventory.models import Inventory

FIXTURES = Path(__file__).parent / "fixtures" / "inventory"
INPUTS = {
    "candidates": FIXTURES / "candidates.csv",
    "pco_democrats": FIXTURES / "pco-democrats.csv",
    "pco_republicans": FIXTURES / "pco-republicans.csv",
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
