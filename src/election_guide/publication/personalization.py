"""The deterministic personalization payload published for client-side lenses.

The audited consensus stays the published baseline. This contract exposes the
inputs a client needs to recompute an equal-weight score over a chosen subset of
the panel without reading evidence. The release policy controls whether the
client lens is active; see `builder._personalization` for the current setting.
"""

from __future__ import annotations

from fractions import Fraction
from itertools import pairwise
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from election_guide.sources.models import (
    CATEGORY_CODE_PATTERN,
    SOURCE_CODE_PATTERN,
    TRANSPORT_CODE_PATTERN,
    validated_retired_code,
    validated_source_code,
)

PERSONALIZATION_SCHEMA_VERSION = "1.0"
URL_SCHEMA_VERSION = "1"
MAXIMUM_URL_CHARACTERS = 4096
"""The sharing-size target issue 83 fixes for the fragment codec."""
LensCellState = Literal[
    "endorsement",
    "multi_endorsement",
    "no_endorsement",
    "not_covered",
    "unavailable",
    "unverified",
]
SCORED_CELL_STATES: frozenset[str] = frozenset({"endorsement", "multi_endorsement"})


class PersonalizationModel(BaseModel):
    """Reject undeclared fields so a drifting payload fails publication.

    A published contract is always serialized whole, so a field with a default
    is still present in the JSON a client reads. `rendering/payload.py`
    generates the client's TypeScript declarations from this contract's
    serialization schema, and without the flag below every defaulted field
    would be declared optional there — forcing client code to guard against an
    absence that cannot occur.
    """

    model_config = ConfigDict(extra="forbid", json_schema_serialization_defaults_required=True)


def _exact_fraction(value: str, label: str) -> Fraction:
    try:
        parsed = Fraction(value)
    except (ValueError, ZeroDivisionError) as error:
        raise ValueError(f"{label} must be an exact rational string") from error
    if str(parsed) != value:
        raise ValueError(f"{label} must use canonical rational strings")
    return parsed


class PersonalizationPolicy(PersonalizationModel):
    """The release policy governing whether and how a lens may run."""

    enabled: bool = Field(strict=True)
    url_schema_version: Literal["1"] = URL_SCHEMA_VERSION
    default_mode: Literal["audited"] = "audited"
    modes: list[Literal["audited", "sources"]]
    selection_combination: Literal["additive_union"] = "additive_union"
    weighting: Literal["equal"] = "equal"
    minimum_explicit_sources: int = Field(ge=1, strict=True)
    comparison_source_codes: list[str] = Field(min_length=1)
    maximum_url_characters: int = Field(ge=1, strict=True)

    @model_validator(mode="after")
    def validate_policy(self) -> PersonalizationPolicy:
        if self.modes != ["audited", "sources"]:
            raise ValueError("personalization must offer the audited and sources modes in order")
        if self.comparison_source_codes != sorted(set(self.comparison_source_codes)):
            raise ValueError("comparison source codes must be unique and sorted")
        return self


class PersonalizationRetiredCode(PersonalizationModel):
    """A tombstone a client migration resolver uses to identify a withdrawn code.

    The registry accumulates every retirement across every panel a lens has
    ever been enabled for, so the current release's list is sufficient to
    resolve a code retired in any earlier panel version.
    """

    code: str = Field(pattern=TRANSPORT_CODE_PATTERN)
    kind: Literal["source", "category"]
    former_id: str = Field(min_length=1)
    reason: str = Field(min_length=1)

    @model_validator(mode="after")
    def validate_code_family(self) -> PersonalizationRetiredCode:
        validated_retired_code(self.code, self.kind)
        return self


class PersonalizationCategory(PersonalizationModel):
    """A selectable grouping resolved against current panel membership."""

    id: str = Field(min_length=1)
    code: str = Field(pattern=CATEGORY_CODE_PATTERN)
    label: str = Field(min_length=1)
    selectable: bool = Field(strict=True)
    panel_role: Literal["tallying", "comparison"] = "tallying"
    member_source_codes: list[str]

    @model_validator(mode="after")
    def validate_members(self) -> PersonalizationCategory:
        if self.member_source_codes != sorted(set(self.member_source_codes)):
            raise ValueError(f"category {self.id!r} members must be unique and sorted")
        if not self.selectable and self.member_source_codes:
            raise ValueError(f"nonselectable category {self.id!r} cannot publish members")
        return self


class PersonalizationSource(PersonalizationModel):
    """One panel source addressed by its immutable transport code."""

    id: str = Field(min_length=1)
    code: str = Field(pattern=SOURCE_CODE_PATTERN)
    """`G` and `g` stay reserved for categories so a URL token is unambiguous."""
    panel_role: Literal["consensus", "comparison"]
    selectable: bool = Field(strict=True)
    reporting_category_id: str = Field(min_length=1)
    selection_category_ids: list[str] = Field(min_length=1)
    overlap_group_ids: list[str]

    @model_validator(mode="after")
    def validate_source(self) -> PersonalizationSource:
        validated_source_code(self.code)
        if self.selection_category_ids != sorted(set(self.selection_category_ids)):
            raise ValueError(f"source {self.id!r} categories must be unique and sorted")
        if self.reporting_category_id not in self.selection_category_ids:
            raise ValueError(f"source {self.id!r} reporting category must be a selection category")
        if self.overlap_group_ids != sorted(set(self.overlap_group_ids)):
            raise ValueError(f"source {self.id!r} overlap groups must be unique and sorted")
        if not self.selectable:
            raise ValueError(f"published source {self.id!r} must be selectable")
        return self


class PersonalizationCell(PersonalizationModel):
    """One eligible source's exact contribution to one race."""

    source_code: str = Field(pattern=SOURCE_CODE_PATTERN)
    state: LensCellState
    allocation: dict[str, str]
    confidence_warning: bool = Field(strict=True)

    @model_validator(mode="after")
    def validate_cell(self) -> PersonalizationCell:
        allocations = [
            _exact_fraction(value, "cell allocation") for value in self.allocation.values()
        ]
        if self.state in SCORED_CELL_STATES:
            if not allocations:
                raise ValueError(f"{self.state} cell requires an allocation")
            if any(value <= 0 for value in allocations) or sum(allocations) != 1:
                raise ValueError("cell allocations must be positive and sum exactly to one")
            if self.state == "endorsement" and len(allocations) != 1:
                raise ValueError("endorsement cell requires exactly one candidate")
            if self.state == "multi_endorsement" and len(allocations) < 2:
                raise ValueError("multi-endorsement cell requires at least two candidates")
        elif allocations:
            raise ValueError(f"{self.state} cell cannot carry an allocation")
        return self


class PersonalizationRace(PersonalizationModel):
    """Everything a client needs to rescore one race over a chosen subset."""

    race_id: str = Field(min_length=1)
    eligible_source_codes: list[str] = Field(min_length=1)
    cells: list[PersonalizationCell]
    candidate_order: list[str] = Field(min_length=1)
    """Every candidate on the ballot, in the race's canonical (ballot) order.

    UI polish issue 132 (H30): the audited engine resolves a tie in this same
    order (`_ordered_support` in `scoring/engine.py`), so a client lens must
    order its own tied labels identically rather than sorting candidate ids
    alphabetically — otherwise the same tie renders as "A / B" server-side and
    "B / A" client-side. Published once per race rather than re-derived from
    cell allocations, which carry only the candidates an individual source
    actually endorsed.
    """

    @model_validator(mode="after")
    def validate_race(self) -> PersonalizationRace:
        if self.eligible_source_codes != sorted(set(self.eligible_source_codes)):
            raise ValueError(f"race {self.race_id!r} eligible codes must be unique and sorted")
        cell_codes = [cell.source_code for cell in self.cells]
        if cell_codes != sorted(set(cell_codes)):
            raise ValueError(f"race {self.race_id!r} cells must be unique and sorted by code")
        if cell_codes != self.eligible_source_codes:
            raise ValueError(f"race {self.race_id!r} must publish one cell per eligible source")
        if len(set(self.candidate_order)) != len(self.candidate_order):
            raise ValueError(f"race {self.race_id!r} candidate order must not repeat a candidate")
        allocated_candidate_ids = {
            candidate_id for cell in self.cells for candidate_id in cell.allocation
        }
        unordered = allocated_candidate_ids - set(self.candidate_order)
        if unordered:
            raise ValueError(
                f"race {self.race_id!r} candidate order omits scored candidates {sorted(unordered)}"
            )
        return self


class PersonalizationGrade(PersonalizationModel):
    grade: Literal["A+", "A", "B", "C", "D"]
    minimum_share: str
    minimum_explicit_sources: int | None = Field(default=None, ge=1, strict=True)

    @model_validator(mode="after")
    def validate_grade(self) -> PersonalizationGrade:
        _exact_fraction(self.minimum_share, "grade minimum share")
        return self


class PersonalizationScoring(PersonalizationModel):
    """The audited scoring identity a client lens must reproduce exactly."""

    configuration_id: str = Field(min_length=1)
    allocation: Literal["exact_equal_split"]
    minimum_explicit_sources: int = Field(ge=1, strict=True)
    grades: list[PersonalizationGrade] = Field(min_length=5, max_length=5)
    tie_precedes_grade: bool = Field(strict=True)
    insufficient_precedes_ordinary_grade: bool = Field(strict=True)
    missing_coverage_enters_denominator: bool = Field(strict=True)
    no_endorsement_enters_denominator: bool = Field(strict=True)

    @model_validator(mode="after")
    def validate_scoring(self) -> PersonalizationScoring:
        if [item.grade for item in self.grades] != ["A+", "A", "B", "C", "D"]:
            raise ValueError("published grades must follow audited policy order")
        shares = [
            _exact_fraction(item.minimum_share, "grade minimum share") for item in self.grades
        ]
        if any(left <= right for left, right in pairwise(shares)):
            raise ValueError("published grade thresholds must be strictly descending")
        if not self.tie_precedes_grade or not self.insufficient_precedes_ordinary_grade:
            raise ValueError("published resolution order must match the audited scoring policy")
        if self.missing_coverage_enters_denominator or self.no_endorsement_enters_denominator:
            raise ValueError("published denominators must match the audited scoring policy")
        return self


class PersonalizationContract(PersonalizationModel):
    """The complete versioned payload consumed by the client lens modules."""

    schema_version: Literal["1.0"] = PERSONALIZATION_SCHEMA_VERSION
    policy: PersonalizationPolicy
    panel_id: str = Field(min_length=1)
    panel_version: str = Field(min_length=1)
    panel_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    scoring: PersonalizationScoring
    categories: list[PersonalizationCategory] = Field(min_length=1)
    sources: list[PersonalizationSource] = Field(min_length=1)
    retired_codes: list[PersonalizationRetiredCode] = Field(
        default_factory=list[PersonalizationRetiredCode]
    )
    races: list[PersonalizationRace] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_contract(self) -> PersonalizationContract:
        category_ids = [category.id for category in self.categories]
        if len(set(category_ids)) != len(category_ids):
            raise ValueError("personalization category ids must be unique")
        category_codes = [category.code for category in self.categories]
        if len(set(category_codes)) != len(category_codes):
            raise ValueError("personalization category codes must be unique")
        known_categories = set(category_ids)

        source_codes = [source.code for source in self.sources]
        if len(set(source_codes)) != len(source_codes):
            raise ValueError("personalization source codes must be unique")
        source_by_code = {source.code: source for source in self.sources}
        selectable_codes = {source.code for source in self.sources if source.selectable}

        retired_codes = [retired.code for retired in self.retired_codes]
        if len(set(retired_codes)) != len(retired_codes):
            raise ValueError("personalization retired codes must be unique")
        live_codes = set(category_codes) | set(source_codes)
        reused = live_codes & set(retired_codes)
        if reused:
            raise ValueError(f"retired codes {sorted(reused)} are still live")

        for source in self.sources:
            unknown = set(source.selection_category_ids) - known_categories
            if unknown:
                raise ValueError(f"source {source.id!r} references unknown {sorted(unknown)}")

        for category in self.categories:
            expected = sorted(
                source.code
                for source in self.sources
                if source.selectable and category.id in source.selection_category_ids
            )
            if category.selectable and category.member_source_codes != expected:
                raise ValueError(f"category {category.id!r} members must follow current membership")

        comparison_codes = sorted(
            source.code for source in self.sources if source.panel_role == "comparison"
        )
        if self.policy.comparison_source_codes != comparison_codes:
            raise ValueError("policy comparison codes must match the published comparison sources")
        if not set(comparison_codes) <= selectable_codes:
            raise ValueError("comparison sources must be selectable for display")
        comparison_category_ids = {
            category.id for category in self.categories if category.panel_role == "comparison"
        }
        for source in self.sources:
            joined_comparison_categories = comparison_category_ids & set(
                source.selection_category_ids
            )
            if source.panel_role == "comparison":
                if joined_comparison_categories != comparison_category_ids:
                    raise ValueError(
                        f"comparison source {source.id!r} must join every comparison category"
                    )
            elif joined_comparison_categories:
                raise ValueError(f"source {source.id!r} cannot join a comparison category")
        if self.policy.minimum_explicit_sources != self.scoring.minimum_explicit_sources:
            raise ValueError("policy and scoring must agree on the explicit-source threshold")

        race_ids = [race.race_id for race in self.races]
        if len(set(race_ids)) != len(race_ids):
            raise ValueError("personalization race ids must be unique")
        for race in self.races:
            unknown_codes = set(race.eligible_source_codes) - set(source_by_code)
            if unknown_codes:
                raise ValueError(
                    f"race {race.race_id!r} references unknown source codes {sorted(unknown_codes)}"
                )
        return self
