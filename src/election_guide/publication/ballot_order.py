"""Reviewed election-specific contest presentation; independent of ballot membership."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from election_guide.inventory.models import Inventory

BALLOT_ORDER_FILES = {
    "wa-2026-general": Path(__file__).with_name("ballot_orders") / "wa-2026-general.v1.json",
}


class OrderModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class BallotEvidence(OrderModel):
    url: str = Field(pattern=r"^https://")
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    custody: str = Field(min_length=1)
    reviewed_at: datetime
    reviewer: str = Field(min_length=1)


class ContestPlacement(OrderModel):
    race_id: str = Field(min_length=1)
    page: int = Field(ge=1)
    column: int = Field(ge=1, le=3)
    box: int = Field(ge=1)
    printed_heading: str = Field(min_length=1)


class BallotSection(OrderModel):
    id: str = Field(min_length=1)
    label: str = Field(min_length=1)
    contests: list[ContestPlacement] = Field(min_length=1)


class BallotOrder(OrderModel):
    schema_version: Literal["1"]
    election_id: str
    evidence: BallotEvidence
    sections: list[BallotSection] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_unique_placements(self) -> Self:
        section_ids = [section.id for section in self.sections]
        race_ids = [contest.race_id for section in self.sections for contest in section.contests]
        if len(section_ids) != len(set(section_ids)):
            raise ValueError("duplicate ballot section ID")
        if len(race_ids) != len(set(race_ids)):
            raise ValueError("duplicate ballot contest ID")
        positions = [
            (contest.page, contest.column, contest.box)
            for section in self.sections
            for contest in section.contests
        ]
        if positions != sorted(set(positions)):
            raise ValueError("ballot placements must follow unique page/column/box reading order")
        return self

    def validate_inventory(self, inventory: Inventory) -> None:
        if self.election_id != inventory.election.id:
            raise ValueError("ballot order election does not match inventory")
        expected = {race.id for race in inventory.races}
        mapped = {contest.race_id for section in self.sections for contest in section.contests}
        if mapped != expected:
            raise ValueError(
                f"ballot order must cover the complete inventory: "
                f"missing={sorted(expected - mapped)}, unknown={sorted(mapped - expected)}"
            )


def load_ballot_order(inventory: Inventory) -> BallotOrder | None:
    """Fail closed for mapped elections; leave unmapped elections' legacy rendering alone."""
    path = BALLOT_ORDER_FILES.get(inventory.election.id)
    if path is None:
        return None
    order = BallotOrder.model_validate_json(path.read_bytes())
    order.validate_inventory(inventory)
    return order
