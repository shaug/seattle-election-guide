"""Canonical, provenance-bearing election inventory models."""

from __future__ import annotations

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class InventoryModel(BaseModel):
    """Reject undeclared fields so schema drift fails loudly."""

    model_config = ConfigDict(extra="forbid")


class SourceReference(InventoryModel):
    id: str
    authority: str
    url: str
    media_type: str
    retrieved_at: datetime
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    description: str


class Election(InventoryModel):
    id: str
    name: str
    election_type: Literal["primary", "general", "special"]
    election_date: date
    state: str
    official_url: str
    source_ids: list[str]


class SeattleApplicability(InventoryModel):
    relationship: Literal["contains_city", "citywide", "intersects_city", "within_city"]
    explanation: str
    source_ids: list[str]


class Jurisdiction(InventoryModel):
    id: str
    name: str
    kind: Literal[
        "state",
        "county",
        "city",
        "congressional_district",
        "legislative_district",
        "county_council_district",
        "city_council_district",
        "precinct",
    ]
    parent_id: str | None
    aliases: list[str]
    seattle_applicability: SeattleApplicability
    source_ids: list[str]


class BallotChoice(InventoryModel):
    id: str
    race_id: str
    choice_type: Literal["candidate", "ballot_option"]
    official_name: str
    display_name: str
    aliases: list[str]
    ballot_order: int
    party_preference: str | None = None
    source_ids: list[str]


class Race(InventoryModel):
    id: str
    election_id: str
    jurisdiction_id: str
    race_type: Literal["candidate", "measure", "party_office"]
    district: str
    office: str
    position: str | None
    display_name: str
    aliases: list[str]
    publication_eligible: bool
    source_ids: list[str]
    choices: list[BallotChoice]


class CoverageCheck(InventoryModel):
    source_id: str
    rule: str
    matched_races: int
    matched_choices: int


class SelectionMethod(InventoryModel):
    target: str
    rule: str
    exclusions: list[str]
    source_ids: list[str]


class Inventory(InventoryModel):
    schema_version: Literal["1.0"] = "1.0"
    election: Election
    sources: list[SourceReference]
    jurisdictions: list[Jurisdiction]
    races: list[Race]
    coverage_checks: list[CoverageCheck]
    selection_method: SelectionMethod

    @model_validator(mode="after")
    def validate_references(self) -> Inventory:
        source_ids = _unique_ids(self.sources, "source")
        jurisdiction_ids = _unique_ids(self.jurisdictions, "jurisdiction")
        race_ids = _unique_ids(self.races, "race")

        _require_sources("election", self.election.id, self.election.source_ids, source_ids)
        _require_sources(
            "selection method",
            self.selection_method.target,
            self.selection_method.source_ids,
            source_ids,
        )

        for jurisdiction in self.jurisdictions:
            if (
                jurisdiction.parent_id is not None
                and jurisdiction.parent_id not in jurisdiction_ids
            ):
                raise ValueError(
                    f"jurisdiction {jurisdiction.id!r} has unknown parent "
                    f"{jurisdiction.parent_id!r}"
                )
            if jurisdiction.parent_id == jurisdiction.id:
                raise ValueError(f"jurisdiction {jurisdiction.id!r} cannot parent itself")
            _require_sources("jurisdiction", jurisdiction.id, jurisdiction.source_ids, source_ids)
            _require_sources(
                "jurisdiction applicability",
                jurisdiction.id,
                jurisdiction.seattle_applicability.source_ids,
                source_ids,
            )

        _reject_jurisdiction_cycles(self.jurisdictions)

        choice_ids: set[str] = set()
        for race in self.races:
            if race.election_id != self.election.id:
                raise ValueError(
                    f"race {race.id!r} belongs to {race.election_id!r}, not {self.election.id!r}"
                )
            if race.jurisdiction_id not in jurisdiction_ids:
                raise ValueError(
                    f"race {race.id!r} has unknown jurisdiction {race.jurisdiction_id!r}"
                )
            _require_sources("race", race.id, race.source_ids, source_ids)
            ballot_orders: set[int] = set()
            for choice in race.choices:
                if choice.id in choice_ids:
                    raise ValueError(f"duplicate ballot choice id {choice.id!r}")
                choice_ids.add(choice.id)
                if choice.race_id != race.id:
                    raise ValueError(
                        f"choice {choice.id!r} belongs to {choice.race_id!r}, not {race.id!r}"
                    )
                if choice.ballot_order in ballot_orders:
                    raise ValueError(f"race {race.id!r} repeats ballot order {choice.ballot_order}")
                ballot_orders.add(choice.ballot_order)
                _require_sources("ballot choice", choice.id, choice.source_ids, source_ids)

        for check in self.coverage_checks:
            if check.source_id not in source_ids:
                raise ValueError(f"coverage check has unknown source {check.source_id!r}")
        if not race_ids:
            raise ValueError("inventory must contain at least one race")
        return self


def _unique_ids(
    records: list[SourceReference] | list[Jurisdiction] | list[Race], label: str
) -> set[str]:
    ids = [record.id for record in records]
    if len(ids) != len(set(ids)):
        raise ValueError(f"duplicate {label} id")
    return set(ids)


def _require_sources(label: str, record_id: str, references: list[str], known: set[str]) -> None:
    if not references:
        raise ValueError(f"{label} {record_id!r} must cite at least one source")
    unknown = set(references) - known
    if unknown:
        raise ValueError(f"{label} {record_id!r} cites unknown sources: {sorted(unknown)}")


def _reject_jurisdiction_cycles(jurisdictions: list[Jurisdiction]) -> None:
    parents = {jurisdiction.id: jurisdiction.parent_id for jurisdiction in jurisdictions}
    for start in parents:
        seen: set[str] = set()
        current: str | None = start
        while current is not None:
            if current in seen:
                raise ValueError(f"jurisdiction hierarchy contains a cycle at {current!r}")
            seen.add(current)
            current = parents.get(current)
