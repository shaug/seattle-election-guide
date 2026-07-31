"""Display-only contract for the election-scoped source comparisons page.

The personalization contract remains the sole source of stance, eligibility, and
scoring truth. This companion contract publishes only labels, rendered ordering,
the audited baseline, and the release switch needed by comparison consumers.
"""

from __future__ import annotations

from fractions import Fraction
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

COMPARISONS_SCHEMA_VERSION = "1.0"


class ComparisonsModel(BaseModel):
    """Reject undeclared fields so a drifting display contract fails publication."""

    model_config = ConfigDict(extra="forbid")


class ComparisonsPolicy(ComparisonsModel):
    """The release switch governing publication of the comparisons page."""

    enabled: bool = Field(default=False, strict=True)


class ComparisonBaseline(ComparisonsModel):
    """The audited all-sources result copied verbatim from published consensus."""

    leading_pick_ids: list[str]
    share: str | None
    explicit_source_count: int = Field(ge=0, strict=True)

    @model_validator(mode="after")
    def validate_baseline(self) -> ComparisonBaseline:
        if len(set(self.leading_pick_ids)) != len(self.leading_pick_ids):
            raise ValueError("comparison baseline leading picks must be unique")
        if self.share is None:
            if self.leading_pick_ids:
                raise ValueError("comparison baseline leading picks require an exact share")
        else:
            try:
                parsed = Fraction(self.share)
            except (ValueError, ZeroDivisionError) as error:
                raise ValueError(
                    "comparison baseline share must be an exact rational string"
                ) from error
            if str(parsed) != self.share:
                raise ValueError("comparison baseline share must use a canonical rational string")
            if parsed <= 0 or parsed > 1:
                raise ValueError("comparison baseline share must be positive and at most one")
            if not self.leading_pick_ids:
                raise ValueError("comparison baseline share requires at least one leading pick")
        return self


class ComparisonDisplayRace(ComparisonsModel):
    """One race's stable labels, rendered position, and audited baseline."""

    race_id: str = Field(min_length=1)
    race_label: str = Field(min_length=1)
    race_type: Literal["candidate", "measure", "party_office"]
    section_id: str = Field(min_length=1)
    section_label: str = Field(min_length=1)
    section_order: int = Field(ge=0, strict=True)
    race_order: int = Field(ge=0, strict=True)
    candidate_names: dict[str, str]
    measure_response_labels: dict[str, str]
    baseline: ComparisonBaseline

    @model_validator(mode="after")
    def validate_labels(self) -> ComparisonDisplayRace:
        candidate_ids = set(self.candidate_names)
        response_ids = set(self.measure_response_labels)
        if candidate_ids & response_ids:
            raise ValueError("comparison display labels cannot repeat a choice id")
        if self.race_type == "measure":
            if self.candidate_names or not self.measure_response_labels:
                raise ValueError("measure races must publish response labels only")
        elif self.measure_response_labels or not self.candidate_names:
            raise ValueError("candidate races must publish candidate names only")
        if any(
            not label.strip()
            for label in [*self.candidate_names.values(), *self.measure_response_labels.values()]
        ):
            raise ValueError("comparison display labels must not be blank")
        if not set(self.baseline.leading_pick_ids) <= candidate_ids | response_ids:
            raise ValueError("comparison baseline leading picks must resolve to display labels")
        return self


class ComparisonsContract(ComparisonsModel):
    """The versioned, display-only payload consumed by comparison features."""

    schema_version: Literal["1.0"] = COMPARISONS_SCHEMA_VERSION
    policy: ComparisonsPolicy
    display_index: list[ComparisonDisplayRace] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_display_index(self) -> ComparisonsContract:
        race_ids = [race.race_id for race in self.display_index]
        if len(set(race_ids)) != len(race_ids):
            raise ValueError("comparison display index race ids must be unique")

        positions = [(race.section_order, race.race_order) for race in self.display_index]
        if positions != sorted(positions) or len(set(positions)) != len(positions):
            raise ValueError("comparison display index must follow section and race order")

        sections: dict[int, tuple[str, str, list[int]]] = {}
        for race in self.display_index:
            section = sections.setdefault(
                race.section_order,
                (race.section_id, race.section_label, []),
            )
            if section[:2] != (race.section_id, race.section_label):
                raise ValueError("comparison section identity must be consistent")
            section[2].append(race.race_order)
        if list(sections) != list(range(len(sections))):
            raise ValueError("comparison section order must be contiguous")
        if any(
            race_orders != list(range(len(race_orders))) for _, _, race_orders in sections.values()
        ):
            raise ValueError("comparison race order must be contiguous within each section")
        return self
