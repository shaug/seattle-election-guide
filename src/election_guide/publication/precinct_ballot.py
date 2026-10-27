"""General-only covered contest sets; no scoring, section or ordering policy."""

import hashlib
from typing import Literal

from election_guide.inventory.models import Inventory, InventoryModel
from election_guide.inventory.precinct_ballot import ReviewedPrecinctCatalog


class PrecinctContests(InventoryModel):
    code: str
    name: str
    contest_ids: list[str]


class PrecinctBallotContract(InventoryModel):
    schema_version: Literal["1.0"] = "1.0"
    election_id: str
    mapping_hash: str
    endorsements_path: str | None
    comparisons_path: str | None
    sources_path: str | None
    precincts: list[PrecinctContests]


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
    return PrecinctBallotContract(
        election_id=inventory.election.id,
        endorsements_path=None,
        comparisons_path=None,
        sources_path=None,
        mapping_hash=hashlib.sha256(catalog.model_dump_json().encode()).hexdigest(),
        precincts=[
            PrecinctContests(
                code=p.code,
                name=p.name,
                contest_ids=[r.id for r in races if r.jurisdiction_id in p.jurisdiction_ids],
            )
            for p in catalog.precincts
        ],
    )
