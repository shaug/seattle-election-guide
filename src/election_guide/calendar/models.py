"""Strict schema for the declared election operations calendar.

The calendar is a planning artifact, not a site feature. It declares election
identity, dates, and milestone offsets, and deliberately declares no display
strings, banner semantics, or copy, so a renderer can key on this data later
without that being a commitment now (`docs/SITE_OPERATIONS_PLAN.md`, D5).
"""

from __future__ import annotations

from datetime import date, timedelta
from pathlib import PurePosixPath
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

ID_PATTERN = r"^[a-z0-9]+(?:-[a-z0-9]+)*$"
WORKFLOW_PATTERN = r"^[a-z0-9]+(?:-[a-z0-9]+)*(?: [a-z0-9]+(?:-[a-z0-9]+)*)*$"

MilestonePhase = Literal["before", "on", "after"]
MilestoneKind = Literal[
    "initialize_election",
    "filing_closes",
    "official_inventory_import",
    "source_panel_freeze",
    "collection_opens",
    "ballots_mail",
    "guide_publishes",
    "refresh",
    "election_day",
    "results_capture_election_night",
    "certification",
    "results_capture_post_certification",
    "retrospective",
]

# Which side of election day each kind must fall on. This is what makes an
# offset "invalid" rather than merely surprising: a certification dated before
# its own election is a typo the calendar must reject, not plan around.
MILESTONE_PHASES: dict[MilestoneKind, MilestonePhase] = {
    "initialize_election": "before",
    "filing_closes": "before",
    "official_inventory_import": "before",
    "source_panel_freeze": "before",
    "collection_opens": "before",
    "ballots_mail": "before",
    "guide_publishes": "before",
    "refresh": "before",
    "election_day": "on",
    "results_capture_election_night": "on",
    "certification": "after",
    "results_capture_post_certification": "after",
    "retrospective": "after",
}

# The two windows that cannot be reopened once missed, so every declared
# election must schedule both (`docs/SITE_OPERATIONS_PLAN.md`, O11).
REQUIRED_MILESTONE_KINDS: tuple[MilestoneKind, ...] = (
    "results_capture_election_night",
    "results_capture_post_certification",
)


def _repeated(values: list[str]) -> list[str]:
    seen: set[str] = set()
    repeated: set[str] = set()
    for value in values:
        if value in seen:
            repeated.add(value)
        seen.add(value)
    return sorted(repeated)


class CalendarModel(BaseModel):
    """Reject undeclared fields so calendar drift fails loudly."""

    model_config = ConfigDict(extra="forbid")


class CalendarElection(CalendarModel):
    """One upcoming election, identified without any presentation copy."""

    id: str = Field(pattern=ID_PATTERN)
    election_type: Literal["primary", "general", "special"]
    election_scope: Literal["municipal", "county", "statewide", "mixed"]
    election_date: date
    state: str = Field(pattern=r"^[A-Z]{2}$")


class CalendarMilestone(CalendarModel):
    """One working-backward checkpoint anchored to its election's date."""

    election_id: str = Field(pattern=ID_PATTERN)
    id: str = Field(pattern=ID_PATTERN)
    kind: MilestoneKind
    offset_days: int = Field(ge=-730, le=365)
    workflow: str | None = Field(default=None, pattern=WORKFLOW_PATTERN)
    reference: str | None = Field(default=None, min_length=1)

    @field_validator("reference")
    @classmethod
    def validate_reference(cls, value: str | None) -> str | None:
        if value is None:
            return value
        path = PurePosixPath(value)
        if path.is_absolute() or ".." in path.parts or "\\" in value or value != path.as_posix():
            raise ValueError(f"milestone reference {value!r} must be a repository-relative path")
        return value

    @model_validator(mode="after")
    def validate_offset_phase(self) -> CalendarMilestone:
        phase = MILESTONE_PHASES[self.kind]
        if phase == "before" and self.offset_days >= 0:
            raise ValueError(f"milestone {self.id!r} must fall before election day")
        if phase == "on" and self.offset_days != 0:
            raise ValueError(f"milestone {self.id!r} must fall on election day")
        if phase == "after" and self.offset_days <= 0:
            raise ValueError(f"milestone {self.id!r} must fall after election day")
        return self


class ElectionCalendar(CalendarModel):
    """Versioned declaration of upcoming elections and the work each implies."""

    schema_version: Literal["1.0"] = "1.0"
    elections: list[CalendarElection] = Field(min_length=1)
    milestones: list[CalendarMilestone] = Field(min_length=1)

    def election(self, election_id: str) -> CalendarElection:
        """Resolve one declared election by ID."""
        for election in self.elections:
            if election.id == election_id:
                return election
        raise KeyError(election_id)

    def election_milestones(self, election_id: str) -> list[CalendarMilestone]:
        """List one election's milestones in declaration order."""
        return [item for item in self.milestones if item.election_id == election_id]

    def scheduled_date(self, milestone: CalendarMilestone) -> date:
        """Resolve the calendar date a milestone's offset implies."""
        anchor = self.election(milestone.election_id).election_date
        return anchor + timedelta(days=milestone.offset_days)

    @model_validator(mode="after")
    def validate_calendar(self) -> ElectionCalendar:
        repeated_elections = _repeated([election.id for election in self.elections])
        if repeated_elections:
            raise ValueError(f"calendar repeats election IDs: {repeated_elections}")
        declared = {election.id for election in self.elections}
        unknown = sorted({item.election_id for item in self.milestones} - declared)
        if unknown:
            raise ValueError(f"calendar milestones name unknown election IDs: {unknown}")
        repeated_milestones = _repeated(
            [f"{item.election_id}/{item.id}" for item in self.milestones]
        )
        if repeated_milestones:
            raise ValueError(f"calendar repeats milestones: {repeated_milestones}")
        for election in self.elections:
            self._validate_election_milestones(election)
        return self

    def _validate_election_milestones(self, election: CalendarElection) -> None:
        milestones = self.election_milestones(election.id)
        kinds = [item.kind for item in milestones]
        if kinds.count("election_day") != 1:
            raise ValueError(
                f"election {election.id!r} must declare exactly one election-day milestone"
            )
        missing = [kind for kind in REQUIRED_MILESTONE_KINDS if kind not in kinds]
        if missing:
            raise ValueError(f"election {election.id!r} declares no {', '.join(missing)} milestone")
        certified = [item.offset_days for item in milestones if item.kind == "certification"]
        captured = [
            item.offset_days
            for item in milestones
            if item.kind == "results_capture_post_certification"
        ]
        if certified and min(captured) < max(certified):
            raise ValueError(
                f"election {election.id!r} captures certified results before certification"
            )
