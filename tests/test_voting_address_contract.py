"""Election/catalog binding for the optional address capability; no live GIS."""

from pathlib import Path

from election_guide.inventory.models import Inventory
from election_guide.inventory.precinct_ballot import CATALOG_PATH, read_precinct_catalog
from election_guide.publication.precinct_ballot import build_precinct_ballot

ROOT = Path(__file__).resolve().parents[1]


def test_address_capability_binds_reviewed_general_catalog_without_changing_membership() -> None:
    inventory = Inventory.model_validate_json(
        (ROOT / "data/normalized/wa-2026-general-inventory.json").read_bytes()
    )
    catalog = read_precinct_catalog(CATALOG_PATH, inventory)
    contract = build_precinct_ballot(inventory, catalog, {r.id for r in inventory.races})
    assert contract is not None
    assert contract.address_lookup is not None
    assert contract.address_lookup.mapping_hash == contract.mapping_hash
    assert contract.address_lookup.election_id == contract.election_id
    assert contract.address_lookup.precinct.data == 1772636566276
    assert contract.address_lookup.city.data == 1792005925455
    civic = next(p for p in contract.precincts if p.code == "3230")
    assert (
        civic.jurisdiction_ids
        == next(p for p in catalog.precincts if p.code == "3230").jurisdiction_ids
    )
