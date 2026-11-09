"""Election-specific covered contest sets; no scoring, section or ordering policy."""

import hashlib
from pathlib import Path
from typing import Literal

from pydantic import Field

from election_guide.inventory.models import Inventory, InventoryModel
from election_guide.inventory.precinct_ballot import ReviewedPrecinctCatalog


class AddressSourceIdentity(InventoryModel):
    item: str
    data: int
    schema_edit: int


class AddressLookupContext(InventoryModel):
    election_id: Literal["wa-2026-general"]
    mapping_hash: str
    city: AddressSourceIdentity
    precinct: AddressSourceIdentity
    address: AddressSourceIdentity


class PrecinctContests(InventoryModel):
    code: str
    name: str
    contest_ids: list[str]
    jurisdiction_ids: list[str] = Field(default_factory=list)


class HistoricalPrecinctProvenance(InventoryModel):
    """Current supplement authority; never an archive result or capture clock."""

    schema_version: Literal["1.0"] = "1.0"
    election_id: Literal["wa-2026-primary"]
    source_git_commit: str = Field(pattern=r"^[0-9a-f]{40}$")
    artifact_path: str = Field(pattern=r"^e/wa-2026-primary/precinct-supplement\.json$")
    artifact_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    archive_view_model_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    archive_inventory_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    mapping_hash: str = Field(pattern=r"^[0-9a-f]{64}$")


class PrecinctBallotContract(InventoryModel):
    schema_version: Literal["1.0"] = "1.0"
    election_id: str
    mapping_hash: str
    endorsements_path: str | None
    comparisons_path: str | None
    sources_path: str | None
    precincts: list[PrecinctContests]
    address_lookup: AddressLookupContext | None = None
    supplement: HistoricalPrecinctProvenance | None = Field(
        default=None, exclude_if=lambda value: value is None
    )


def build_precinct_ballot(
    inventory: Inventory,
    catalog: ReviewedPrecinctCatalog | None,
    published_race_ids: set[str],
) -> PrecinctBallotContract | None:
    if inventory.election.id != "wa-2026-general":
        return None
    if catalog is None or catalog.election_id != inventory.election.id:
        raise ValueError("general precinct publication requires its reviewed catalog")
    races = [
        race
        for race in inventory.races
        if race.publication_eligible and race.id in published_race_ids
    ]
    mapping_hash = hashlib.sha256(catalog.model_dump_json().encode()).hexdigest()
    lookup = AddressLookupContext.model_validate_json(
        (
            Path(__file__).resolve().parents[3]
            / "config/elections/wa-2026-general-address-lookup.json"
        ).read_bytes()
    )
    if lookup.mapping_hash != mapping_hash:
        raise ValueError("address lookup belongs to another reviewed precinct catalog")
    return PrecinctBallotContract(
        election_id=inventory.election.id,
        endorsements_path=None,
        comparisons_path=None,
        sources_path=None,
        mapping_hash=mapping_hash,
        address_lookup=lookup,
        precincts=[
            PrecinctContests(
                code=p.code,
                name=p.name,
                jurisdiction_ids=p.jurisdiction_ids,
                contest_ids=[r.id for r in races if r.jurisdiction_id in p.jurisdiction_ids],
            )
            for p in catalog.precincts
        ],
    )
