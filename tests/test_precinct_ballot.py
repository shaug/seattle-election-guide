"""Admission of the reviewed general-only precinct catalog, independent of UI."""

import copy
import json
from pathlib import Path

import pytest

from election_guide.inventory.importer import read_inventory
from election_guide.inventory.models import Inventory
from election_guide.inventory.precinct_ballot import ReviewedPrecinctCatalog

ROOT = Path(__file__).resolve().parents[1]
CATALOG = ROOT / "config/elections/wa-2026-general-precinct-ballots.json"
INVENTORY = ROOT / "data/normalized/wa-2026-general-inventory.json"
FIXTURES = ROOT / "tests/fixtures/ballot/wa-2026-general-official-precinct-sets.json"


def load(path: Path = CATALOG, inventory: Inventory | None = None) -> ReviewedPrecinctCatalog:
    from election_guide.inventory.precinct_ballot import read_precinct_catalog

    return read_precinct_catalog(path, inventory or read_inventory(INVENTORY))


def test_admits_complete_current_general_catalog_and_all_official_fixture_areas() -> None:
    catalog = load()
    assert catalog.election_id == "wa-2026-general"
    assert catalog.election_date.isoformat() == "2026-11-03"
    assert len(catalog.precincts) == 1020
    by_code = {p.code: p for p in catalog.precincts}
    fixtures = json.loads(FIXTURES.read_text())["fixtures"]
    assert len(fixtures) == 31
    for fixture in fixtures:
        area = by_code[fixture["representative"]["code"]]
        assert area.name == fixture["representative"]["name"]
        assert f"congressional-district-{fixture['cd']}" in area.jurisdiction_ids
        assert f"legislative-district-{fixture['ld']}" in area.jurisdiction_ids
        assert f"county-council-district-{fixture['county']}" in area.jurisdiction_ids
        assert f"seattle-city-council-district-{fixture['city']}" in area.jurisdiction_ids
    assert "county-council-district-1" in by_code["2153"].jurisdiction_ids


@pytest.mark.parametrize(
    "mutation",
    [
        "duplicate_code",
        "conflicting_name",
        "missing_precinct",
        "wrong_election",
        "wrong_date",
        "unknown_jurisdiction",
        "missing_shared",
        "stale_hash",
        "missing_source",
        "outside_path",
    ],
)
def test_rejects_incomplete_or_unreviewed_mapping(tmp_path: Path, mutation: str) -> None:
    data = json.loads(CATALOG.read_text())
    if mutation == "duplicate_code":
        data["precincts"].append(copy.deepcopy(data["precincts"][0]))
    elif mutation == "conflicting_name":
        data["precincts"][0]["name"] = "SEA 99-0000"
    elif mutation == "missing_precinct":
        data["precincts"].pop()
    elif mutation == "wrong_election":
        data["election_id"] = "wa-2026-primary"
    elif mutation == "wrong_date":
        data["election_date"] = "2027-11-02"
    elif mutation == "unknown_jurisdiction":
        data["precincts"][0]["jurisdiction_ids"].append("invented-district")
    elif mutation == "missing_shared":
        data["precincts"][0]["jurisdiction_ids"].remove("city-of-seattle")
    elif mutation == "stale_hash":
        data["sources"][0]["storage_sha256"] = "0" * 64
    elif mutation == "missing_source":
        data["sources"].pop()
    elif mutation == "outside_path":
        data["sources"][0]["storage_reference"] = "/etc/passwd"
    path = tmp_path / "catalog.json"
    path.write_text(json.dumps(data))
    with pytest.raises(ValueError):
        load(path)


def test_rejects_new_unmapped_covered_jurisdiction() -> None:
    inventory = read_inventory(INVENTORY)
    inventory = inventory.model_copy(deep=True)
    inventory.races[0].jurisdiction_id = "new-special-district"
    with pytest.raises(ValueError, match="unmapped"):
        load(inventory=inventory)


def test_published_precinct_sets_match_every_independent_official_fixture() -> None:
    from election_guide.publication.precinct_ballot import build_precinct_ballot

    inventory = read_inventory(INVENTORY)
    covered_ids = {r.id for r in inventory.races if r.publication_eligible}
    contract = build_precinct_ballot(inventory, load(), covered_ids)
    assert contract is not None
    actual = {p.code: set(p.contest_ids) for p in contract.precincts}
    for fixture in json.loads(FIXTURES.read_text())["fixtures"]:
        assert actual[fixture["representative"]["code"]] == set(
            fixture["official_applicable_SEG_covered_ids"]
        )
    assert len(contract.mapping_hash) == 64
    # Publication coverage is an intersection, never a new contest.
    limited = build_precinct_ballot(inventory, load(), {"initiative-26-001"})
    assert limited is not None
    assert all(p.contest_ids == ["initiative-26-001"] for p in limited.precincts)


def test_primary_has_no_precinct_contract() -> None:
    from election_guide.publication.precinct_ballot import build_precinct_ballot

    inventory = read_inventory(ROOT / "data/normalized/wa-2026-primary-inventory.json")
    assert build_precinct_ballot(inventory, None, set()) is None


def test_actual_published_primary9_view_model_remains_readable_without_precinct_contract() -> None:
    import gzip

    from election_guide.publication.models import PublicationViewModel

    path = ROOT / "tests/fixtures/ballot/primary9-view-model.json.gz"
    legacy = json.loads(gzip.decompress(path.read_bytes()))
    assert "precinct_ballot" not in legacy
    model = PublicationViewModel.model_validate(legacy)
    assert model.precinct_ballot is None
    assert model.metadata.election_id == "wa-2026-primary"
    assert model.metadata.git_commit == "cd378c44a3dedd1059dba786725d1d022cc1403e"
