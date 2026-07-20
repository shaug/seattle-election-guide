"""Strict scoring configuration and canonical consensus result models."""

from __future__ import annotations

import hashlib
from collections.abc import Mapping
from fractions import Fraction
from itertools import pairwise
from typing import Literal, cast

from pydantic import (
    AwareDatetime,
    BaseModel,
    ConfigDict,
    Field,
    ValidationInfo,
    field_validator,
    model_validator,
)

from election_guide.normalization.models import CanonicalDataset
from election_guide.serialization import canonical_json_bytes

ID_PATTERN = r"^[a-z0-9]+(?:-[a-z0-9]+)*$"
Grade = Literal["TIED", "Insufficient", "A+", "A", "B", "C", "D"]
ComparisonStatus = Literal[
    "agrees",
    "differs",
    "no_endorsement",
    "not_covered",
    "no_consensus",
]


class ScoreModel(BaseModel):
    """Reject undeclared scoring fields so policy changes remain explicit."""

    model_config = ConfigDict(extra="forbid")


class GradeRule(ScoreModel):
    grade: Literal["A+", "A", "B", "C", "D"]
    minimum_share: Fraction
    minimum_explicit_sources: int | None = Field(default=None, ge=1, strict=True)

    @field_validator("minimum_share", mode="before")
    @classmethod
    def reject_inexact_share(cls, value: object) -> object:
        if isinstance(value, (float, bool)):
            raise ValueError("minimum_share must be an exact integer or rational string")
        return value

    @field_validator("minimum_share")
    @classmethod
    def validate_share(cls, value: Fraction) -> Fraction:
        if value < 0 or value > 1:
            raise ValueError("minimum_share must be between zero and one")
        return value


class ScoringConfiguration(ScoreModel):
    id: str = Field(pattern=ID_PATTERN)
    allocation: Literal["exact_equal_split"]
    comparison_source_ids: list[str] = Field(min_length=1)
    minimum_explicit_sources: int = Field(ge=1, strict=True)
    grades: list[GradeRule] = Field(min_length=5, max_length=5)
    tie_precedes_grade: bool = Field(strict=True)
    insufficient_precedes_ordinary_grade: bool = Field(strict=True)
    missing_coverage_enters_denominator: bool = Field(strict=True)
    no_endorsement_enters_denominator: bool = Field(strict=True)

    @model_validator(mode="after")
    def validate_policy(self) -> ScoringConfiguration:
        if len(self.comparison_source_ids) != len(set(self.comparison_source_ids)):
            raise ValueError("comparison_source_ids contains duplicates")
        if not self.tie_precedes_grade or not self.insufficient_precedes_ordinary_grade:
            raise ValueError("ties and insufficient coverage must precede ordinary grades")
        if self.missing_coverage_enters_denominator:
            raise ValueError("missing coverage cannot enter the denominator")
        if self.no_endorsement_enters_denominator:
            raise ValueError("no-endorsement decisions cannot enter the denominator")
        expected_grades = ["A+", "A", "B", "C", "D"]
        if [rule.grade for rule in self.grades] != expected_grades:
            raise ValueError(f"grades must appear in policy order: {expected_grades}")
        thresholds = [rule.minimum_share for rule in self.grades]
        if any(left <= right for left, right in pairwise(thresholds)):
            raise ValueError("grade thresholds must be strictly descending")
        if thresholds[-1] != 0:
            raise ValueError("the D grade must have a zero minimum_share")
        d_required = self.grades[-1].minimum_explicit_sources or self.minimum_explicit_sources
        if d_required > self.minimum_explicit_sources:
            raise ValueError("the D grade must apply at the global minimum source count")
        return self

    def grade_for(
        self,
        explicit_count: int,
        winner_share: Fraction | None,
        *,
        is_tied: bool,
    ) -> Grade:
        """Resolve a grade in the frozen policy order using an exact share."""
        if is_tied:
            return "TIED"
        if explicit_count < self.minimum_explicit_sources or winner_share is None:
            return "Insufficient"
        for rule in self.grades:
            required = rule.minimum_explicit_sources or self.minimum_explicit_sources
            if explicit_count >= required and winner_share >= rule.minimum_share:
                return rule.grade
        raise ValueError("scoring configuration has no applicable grade")


class ScoreWarning(ScoreModel):
    code: Literal[
        "low_coverage",
        "missing_coverage",
        "low_category_coverage",
        "no_endorsement",
        "pending_review",
        "low_confidence",
        "source_overlap",
        "unresolved_high_severity",
    ]
    message: str = Field(min_length=1)
    source_ids: list[str] = Field(default_factory=list)
    review_item_ids: list[str] = Field(default_factory=list)


class CandidateStanding(ScoreModel):
    candidate_id: str = Field(min_length=1)
    support_points: Fraction
    share: Fraction

    @field_validator("support_points", "share", mode="before")
    @classmethod
    def reject_inexact_values(cls, value: object, info: ValidationInfo) -> object:
        return _reject_inexact_fraction(value, info.field_name or "candidate value")

    @model_validator(mode="after")
    def validate_values(self) -> CandidateStanding:
        if self.support_points <= 0:
            raise ValueError("candidate support must be positive")
        if self.share < 0 or self.share > 1:
            raise ValueError("candidate share must be between zero and one")
        return self


class CategoryConsensus(ScoreModel):
    category: str = Field(min_length=1)
    eligible_source_count: int = Field(ge=0, strict=True)
    source_coverage_count: int = Field(ge=0, strict=True)
    explicit_endorsement_count: int = Field(ge=0, strict=True)
    candidate_support: dict[str, Fraction]

    @field_validator("candidate_support", mode="before")
    @classmethod
    def reject_inexact_support(cls, value: object) -> object:
        return _reject_inexact_mapping(value, "category candidate support")

    @model_validator(mode="after")
    def validate_counts(self) -> CategoryConsensus:
        if self.source_coverage_count > self.eligible_source_count:
            raise ValueError("category coverage cannot exceed eligible sources")
        if self.explicit_endorsement_count > self.source_coverage_count:
            raise ValueError("category explicit endorsements cannot exceed coverage")
        if any(value <= 0 for value in self.candidate_support.values()):
            raise ValueError("category candidate support must be positive")
        if sum(self.candidate_support.values(), Fraction()) != self.explicit_endorsement_count:
            raise ValueError("category candidate support must sum to explicit endorsements")
        return self


class OverlapGroupConsensus(ScoreModel):
    group_id: str = Field(pattern=ID_PATTERN)
    label: str = Field(min_length=1)
    description: str = Field(min_length=1)
    relationship: Literal["possible_overlap"] = "possible_overlap"
    eligible_source_ids: list[str] = Field(min_length=2)
    covered_source_ids: list[str]
    explicit_source_ids: list[str]

    @model_validator(mode="after")
    def validate_members(self) -> OverlapGroupConsensus:
        lists = (self.eligible_source_ids, self.covered_source_ids, self.explicit_source_ids)
        if any(items != sorted(set(items)) for items in lists):
            raise ValueError("overlap group source IDs must be unique and sorted")
        eligible = set(self.eligible_source_ids)
        covered = set(self.covered_source_ids)
        explicit = set(self.explicit_source_ids)
        if not explicit <= covered <= eligible:
            raise ValueError("overlap group source scopes must nest within eligibility")
        return self


class ComparisonResult(ScoreModel):
    source_id: str = Field(pattern=ID_PATTERN)
    status: ComparisonStatus
    candidate_ids: list[str]

    @model_validator(mode="after")
    def validate_candidates(self) -> ComparisonResult:
        if len(self.candidate_ids) != len(set(self.candidate_ids)):
            raise ValueError("comparison candidate_ids contains duplicates")
        if self.status in {"agrees", "differs", "no_consensus"} and not self.candidate_ids:
            raise ValueError(f"{self.status} comparison requires candidates")
        if self.status in {"no_endorsement", "not_covered"} and self.candidate_ids:
            raise ValueError(f"{self.status} comparison cannot carry candidates")
        return self


class RaceConsensus(ScoreModel):
    race_id: str = Field(pattern=ID_PATTERN)
    configuration_id: str = Field(pattern=ID_PATTERN)
    eligible_source_count: int = Field(ge=0, strict=True)
    source_coverage_count: int = Field(ge=0, strict=True)
    category_coverage_count: int = Field(ge=0, strict=True)
    explicit_endorsement_count: int = Field(ge=0, strict=True)
    no_endorsement_count: int = Field(ge=0, strict=True)
    missing_source_count: int = Field(ge=0, strict=True)
    pending_review_count: int = Field(ge=0, strict=True)
    low_confidence_source_ids: list[str]
    overlap_source_ids: list[str]
    unresolved_high_severity_review_item_ids: list[str]
    candidate_support: dict[str, Fraction]
    winner_candidate_ids: list[str]
    winner_candidate_id: str | None
    winner_support_points: Fraction | None
    winner_share: Fraction | None
    grade: Grade
    is_tied: bool = Field(strict=True)
    notable_alternatives: list[CandidateStanding]
    category_breakdown: list[CategoryConsensus]
    overlap_groups: list[OverlapGroupConsensus]
    comparison_results: list[ComparisonResult]
    warnings: list[ScoreWarning]
    computed_at: AwareDatetime
    input_hash: str = Field(pattern=r"^[0-9a-f]{64}$")

    @field_validator("candidate_support", mode="before")
    @classmethod
    def reject_inexact_candidate_support(cls, value: object) -> object:
        return _reject_inexact_mapping(value, "candidate support")

    @field_validator("winner_support_points", "winner_share", mode="before")
    @classmethod
    def reject_inexact_winner_values(cls, value: object, info: ValidationInfo) -> object:
        return (
            None
            if value is None
            else _reject_inexact_fraction(value, info.field_name or "winner value")
        )

    @model_validator(mode="after")
    def validate_result(self) -> RaceConsensus:
        signal_lists = (
            self.low_confidence_source_ids,
            self.overlap_source_ids,
            self.unresolved_high_severity_review_item_ids,
        )
        if any(items != sorted(set(items)) for items in signal_lists):
            raise ValueError("race signal identifiers must be unique and sorted")
        if self.source_coverage_count + self.missing_source_count != self.eligible_source_count:
            raise ValueError("source coverage and missing counts must reconcile to eligibility")
        if self.explicit_endorsement_count + self.no_endorsement_count != (
            self.source_coverage_count
        ):
            raise ValueError("covered sources must be explicit endorsements or no-endorsements")
        expected_category_coverage = sum(
            item.source_coverage_count > 0 for item in self.category_breakdown
        )
        if self.category_coverage_count != expected_category_coverage:
            raise ValueError("category coverage must match the category breakdown")
        if len({item.category for item in self.category_breakdown}) != len(self.category_breakdown):
            raise ValueError("category breakdown contains duplicates")
        if [item.group_id for item in self.overlap_groups] != sorted(
            {item.group_id for item in self.overlap_groups}
        ):
            raise ValueError("overlap groups must be unique and sorted")
        expected_overlap_sources = sorted(
            {source_id for group in self.overlap_groups for source_id in group.eligible_source_ids}
        )
        if self.overlap_source_ids != expected_overlap_sources:
            raise ValueError("overlap source IDs must match possible overlap groups")
        if len({item.source_id for item in self.comparison_results}) != len(
            self.comparison_results
        ):
            raise ValueError("comparison results contain duplicate sources")
        for comparison in self.comparison_results:
            if comparison.status in {"no_endorsement", "not_covered"}:
                continue
            if self.grade in {"TIED", "Insufficient"}:
                if comparison.status != "no_consensus":
                    raise ValueError(
                        "comparison must report no_consensus without an ordinary grade"
                    )
                continue
            if self.winner_candidate_id is None:
                raise ValueError("ordinary grade requires a singular winner")
            expected_status = (
                "agrees" if self.winner_candidate_id in comparison.candidate_ids else "differs"
            )
            if comparison.status != expected_status:
                raise ValueError("comparison status contradicts the singular winner")
        if any(value <= 0 for value in self.candidate_support.values()):
            raise ValueError("candidate support must be positive")
        if sum(item.eligible_source_count for item in self.category_breakdown) != (
            self.eligible_source_count
        ):
            raise ValueError("category eligibility must reconcile to race eligibility")
        if sum(item.source_coverage_count for item in self.category_breakdown) != (
            self.source_coverage_count
        ):
            raise ValueError("category coverage must reconcile to race coverage")
        if sum(item.explicit_endorsement_count for item in self.category_breakdown) != (
            self.explicit_endorsement_count
        ):
            raise ValueError("category endorsements must reconcile to race endorsements")
        category_support: dict[str, Fraction] = {}
        for category in self.category_breakdown:
            for candidate_id, support in category.candidate_support.items():
                category_support[candidate_id] = (
                    category_support.get(candidate_id, Fraction()) + support
                )
        if category_support != self.candidate_support:
            raise ValueError("category support must reconcile to race candidate support")
        total_support = sum(self.candidate_support.values(), Fraction())
        if total_support != self.explicit_endorsement_count:
            raise ValueError("candidate support must sum to explicit endorsements")
        maximum = max(self.candidate_support.values(), default=None)
        expected_winners = (
            {
                candidate_id
                for candidate_id, support in self.candidate_support.items()
                if support == maximum
            }
            if maximum is not None
            else set[str]()
        )
        if len(self.winner_candidate_ids) != len(set(self.winner_candidate_ids)):
            raise ValueError("winner_candidate_ids contains duplicates")
        if set(self.winner_candidate_ids) != expected_winners:
            raise ValueError("winner set must match maximum candidate support")
        if self.winner_support_points != maximum:
            raise ValueError("winner support must match maximum candidate support")
        expected_share = None if maximum is None else maximum / total_support
        if self.winner_share != expected_share:
            raise ValueError("winner share must match exact support totals")
        if self.is_tied != (len(self.winner_candidate_ids) > 1):
            raise ValueError("tie flag must match the winner set")
        if self.is_tied and (self.grade != "TIED" or self.winner_candidate_id is not None):
            raise ValueError("a tie cannot carry an ordinary grade or singular winner")
        if not self.is_tied and len(self.winner_candidate_ids) == 1:
            if self.winner_candidate_id != self.winner_candidate_ids[0]:
                raise ValueError("singular winner must match the winner set")
        elif not self.is_tied and self.winner_candidate_id is not None:
            raise ValueError("a result without a winner set cannot name a winner")
        if not self.is_tied and self.grade == "TIED":
            raise ValueError("a non-tied result cannot use the TIED grade")
        alternative_ids = [item.candidate_id for item in self.notable_alternatives]
        expected_alternatives = set(self.candidate_support) - expected_winners
        if (
            len(alternative_ids) != len(set(alternative_ids))
            or set(alternative_ids) != expected_alternatives
        ):
            raise ValueError("notable alternatives must contain every non-winning candidate once")
        for alternative in self.notable_alternatives:
            support = self.candidate_support[alternative.candidate_id]
            if (
                alternative.support_points != support
                or alternative.share != support / total_support
            ):
                raise ValueError("notable alternative values must match candidate support")
        self._validate_warning_consistency()
        return self

    def _validate_warning_consistency(self) -> None:
        warning_by_code = {warning.code: warning for warning in self.warnings}
        if len(warning_by_code) != len(self.warnings):
            raise ValueError("race warnings contain duplicate codes")
        for warning in self.warnings:
            if len(warning.source_ids) != len(set(warning.source_ids)):
                raise ValueError("warning source_ids contains duplicates")
            if len(warning.review_item_ids) != len(set(warning.review_item_ids)):
                raise ValueError("warning review_item_ids contains duplicates")

        expected = {
            "missing_coverage": self.missing_source_count > 0,
            "low_category_coverage": self.category_coverage_count < len(self.category_breakdown),
            "no_endorsement": self.no_endorsement_count > 0,
            "pending_review": self.pending_review_count > 0,
            "low_confidence": bool(self.low_confidence_source_ids),
            "source_overlap": bool(self.overlap_source_ids),
            "unresolved_high_severity": bool(self.unresolved_high_severity_review_item_ids),
        }
        for code, required in expected.items():
            if (code in warning_by_code) != required:
                raise ValueError(f"{code} warning does not match its race signals")

        missing = warning_by_code.get("missing_coverage")
        if missing is not None and len(missing.source_ids) != self.missing_source_count:
            raise ValueError("missing coverage warning does not match missing source count")
        no_endorsement = warning_by_code.get("no_endorsement")
        if no_endorsement is not None and len(no_endorsement.source_ids) != (
            self.no_endorsement_count
        ):
            raise ValueError("no-endorsement warning does not match its source count")
        pending = warning_by_code.get("pending_review")
        if pending is not None and len(pending.review_item_ids) != self.pending_review_count:
            raise ValueError("pending-review warning does not match its review count")
        low_confidence = warning_by_code.get("low_confidence")
        if low_confidence is not None and low_confidence.source_ids != (
            self.low_confidence_source_ids
        ):
            raise ValueError("confidence warning does not match confidence signals")
        overlap = warning_by_code.get("source_overlap")
        if overlap is not None and overlap.source_ids != self.overlap_source_ids:
            raise ValueError("overlap warning does not match overlap signals")
        high = warning_by_code.get("unresolved_high_severity")
        if high is not None and high.review_item_ids != (
            self.unresolved_high_severity_review_item_ids
        ):
            raise ValueError("high-severity warning does not match unresolved review signals")


class ConsensusReport(ScoreModel):
    schema_version: Literal["1.1"] = "1.1"
    election_id: str = Field(pattern=ID_PATTERN)
    configuration_id: str = Field(pattern=ID_PATTERN)
    scoring_configuration: ScoringConfiguration
    computed_at: AwareDatetime
    dataset_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    publication_scope_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    input_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    publication_race_ids: list[str] = Field(min_length=1)
    publication_has_unresolved_high_severity: bool = Field(strict=True)
    races: list[RaceConsensus]

    @model_validator(mode="after")
    def validate_races(self, info: ValidationInfo) -> ConsensusReport:
        context = cast(Mapping[str, object] | None, info.context)
        dataset = None if context is None else context.get("canonical_dataset")
        if not isinstance(dataset, CanonicalDataset):
            raise ValueError("consensus report validation requires the canonical dataset")
        expected_dataset_hash = hashlib.sha256(
            canonical_json_bytes(dataset.model_dump(mode="json"))
        ).hexdigest()
        if self.dataset_hash != expected_dataset_hash:
            raise ValueError("dataset hash does not match the canonical dataset")
        if self.election_id != dataset.inventory.election.id:
            raise ValueError("report election does not match the canonical dataset")
        expected_publication_race_ids = [
            race.id for race in dataset.inventory.races if race.publication_eligible
        ]
        if self.publication_race_ids != expected_publication_race_ids:
            raise ValueError("publication_race_ids do not match the canonical dataset")
        if self.scoring_configuration.id != self.configuration_id:
            raise ValueError("embedded scoring configuration does not match its report")
        if len(self.publication_race_ids) != len(set(self.publication_race_ids)):
            raise ValueError("publication_race_ids contains duplicates")
        expected_scope_hash = hashlib.sha256(
            canonical_json_bytes(self.publication_race_ids)
        ).hexdigest()
        if self.publication_scope_hash != expected_scope_hash:
            raise ValueError("publication scope hash does not match publication_race_ids")
        expected_input_hash = hashlib.sha256(
            canonical_json_bytes(
                {
                    "dataset_hash": self.dataset_hash,
                    "publication_scope_hash": self.publication_scope_hash,
                    "scoring_configuration": self.scoring_configuration.model_dump(mode="json"),
                }
            )
        ).hexdigest()
        if self.input_hash != expected_input_hash:
            raise ValueError("input hash does not match its component hashes")
        race_ids = [race.race_id for race in self.races]
        if len(race_ids) != len(set(race_ids)):
            raise ValueError("consensus report contains duplicate races")
        if race_ids != self.publication_race_ids:
            raise ValueError("consensus races do not match publication_race_ids")
        for race in self.races:
            if race.configuration_id != self.configuration_id:
                raise ValueError("race configuration does not match its report")
            if race.input_hash != self.input_hash:
                raise ValueError("race input hash does not match its report")
            if race.computed_at != self.computed_at:
                raise ValueError("race timestamp does not match its report")
            comparison_source_ids = [comparison.source_id for comparison in race.comparison_results]
            if comparison_source_ids != self.scoring_configuration.comparison_source_ids:
                raise ValueError("race comparison sources do not match the scoring configuration")
            expected_grade = self.scoring_configuration.grade_for(
                race.explicit_endorsement_count,
                race.winner_share,
                is_tied=race.is_tied,
            )
            if race.grade != expected_grade:
                raise ValueError("race grade does not match the scoring configuration")
            has_low_coverage = any(warning.code == "low_coverage" for warning in race.warnings)
            if has_low_coverage != (
                race.explicit_endorsement_count
                < self.scoring_configuration.minimum_explicit_sources
            ):
                raise ValueError("low_coverage warning does not match the scoring configuration")
        high_review_count = sum(
            len(race.unresolved_high_severity_review_item_ids) for race in self.races
        )
        if self.publication_has_unresolved_high_severity != (high_review_count > 0):
            raise ValueError("publication high-severity flag does not match race warnings")
        skip_derived_validation = bool(
            context is not None and context.get("skip_derived_validation") is True
        )
        if not skip_derived_validation:
            from election_guide.scoring.engine import score_dataset

            try:
                expected_report = score_dataset(
                    dataset,
                    self.scoring_configuration,
                    computed_at=self.computed_at,
                    allow_unresolved=self.publication_has_unresolved_high_severity,
                )
            except ValueError as error:
                raise ValueError(
                    f"consensus report cannot be derived from the canonical dataset: {error}"
                ) from error
            if canonical_json_bytes(self.model_dump(mode="json")) != canonical_json_bytes(
                expected_report.model_dump(mode="json")
            ):
                raise ValueError("consensus report values do not match the canonical dataset")
        return self


def _reject_inexact_fraction(value: object, label: str) -> object:
    if isinstance(value, (float, bool)):
        raise ValueError(f"{label} must be an exact integer or rational string")
    return value


def _reject_inexact_mapping(value: object, label: str) -> object:
    if not isinstance(value, dict):
        return value
    mapping = cast(dict[object, object], value)
    for item in mapping.values():
        _reject_inexact_fraction(item, label)
    return mapping
