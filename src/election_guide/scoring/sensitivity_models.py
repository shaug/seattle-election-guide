"""Exact audit contracts for the preregistered source exclusion policy."""

from __future__ import annotations

from fractions import Fraction
from typing import Literal

from pydantic import AwareDatetime, ConfigDict, Field, StrictInt, field_validator

from election_guide.scoring.models import RaceConsensus, ScoreModel, ScoringConfiguration

ScenarioKind = Literal["source", "category", "overlap"]
Classification = Literal[
    "source_sensitive",
    "category_sensitive",
    "overlap_sensitive",
    "tied",
    "insufficient",
    "narrow_but_stable",
    "stable",
]
RecommendationState = Literal["tied", "insufficient", "recommended"]
MaterialReason = Literal[
    "leaders_changed",
    "recommendation_state_changed",
    "recommendation_choices_changed",
    "majority_boundary_crossed",
    "leading_share_changed_materially",
]


class SensitivityPolicy(ScoreModel):
    """The reviewed v1 policy, not a threshold customization interface."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    id: Literal["source-panel-sensitivity-v1"] = "source-panel-sensitivity-v1"
    individual_rule: Literal["every_eligible_affirmative_source"] = (
        "every_eligible_affirmative_source"
    )
    category_rule: Literal["all_eligible_members_when_two_contributing_reporting_categories"] = (
        "all_eligible_members_when_two_contributing_reporting_categories"
    )
    overlap_rule: Literal["direct_eligible_members_at_least_two_and_one_contributor"] = (
        "direct_eligible_members_at_least_two_and_one_contributor"
    )
    skip_rules: tuple[str, ...] = (
        "category:no_contributors_then_fewer_than_two_contributing_categories",
        "overlap:fewer_than_two_eligible_members_then_no_contributors",
    )
    scoring_rule: Literal["canonical_unweighted_scoring_from_original_inputs"] = (
        "canonical_unweighted_scoring_from_original_inputs"
    )
    material_share_change: Literal["1/10"] = "1/10"
    narrow_margin: Literal["1/10"] = "1/10"
    majority_rule: Literal["strictly_greater_than_1/2"] = "strictly_greater_than_1/2"
    material_reasons: tuple[MaterialReason, ...] = (
        "leaders_changed",
        "recommendation_state_changed",
        "recommendation_choices_changed",
        "majority_boundary_crossed",
        "leading_share_changed_materially",
    )
    classification_priority: tuple[Classification, ...] = (
        "source_sensitive",
        "category_sensitive",
        "overlap_sensitive",
        "tied",
        "insufficient",
        "narrow_but_stable",
        "stable",
    )
    illustration_priority: tuple[MaterialReason, ...] = (
        "recommendation_state_changed",
        "recommendation_choices_changed",
        "leaders_changed",
        "majority_boundary_crossed",
        "leading_share_changed_materially",
    )
    scenario_order: tuple[ScenarioKind, ...] = ("source", "category", "overlap")


class ExactValues(ScoreModel):
    @field_validator(
        "support_points",
        "share",
        "leading_support_points",
        "leading_share",
        "leading_margin",
        mode="before",
        check_fields=False,
    )
    @classmethod
    def reject_inexact(cls, value: object) -> object:
        if isinstance(value, (float, bool)):
            raise ValueError("audit values require exact rational numbers")
        return value


class ChoiceSensitivity(ExactValues):
    candidate_id: str
    support_points: Fraction
    share: Fraction | None


class SensitivitySnapshot(ScoreModel):
    score: RaceConsensus
    recommendation_state: RecommendationState
    recommendation_candidate_ids: list[str]
    populations: dict[str, list[str]]
    choices: list[ChoiceSensitivity]
    leading_margin: str | None


class IdDelta(ScoreModel):
    added: list[str]
    removed: list[str]


class SensitivityDelta(ExactValues):
    changed_fields: list[str]
    counts: dict[str, StrictInt]
    leading_support_points: Fraction | None
    leading_share: Fraction | None
    leading_margin: Fraction | None
    choices: list[ChoiceSensitivity]
    identifiers: dict[str, IdDelta]
    grade_changed: bool = Field(strict=True)
    material_reasons: list[MaterialReason]


class SensitivityScenario(ScoreModel):
    id: str
    kind: ScenarioKind
    target_id: str
    target_label: str
    excluded_source_ids: list[str]
    after: SensitivitySnapshot
    delta: SensitivityDelta


class SkippedScenario(ScoreModel):
    id: str
    kind: Literal["category", "overlap"]
    target_id: str
    target_label: str
    eligible_source_ids: list[str]
    reason: Literal[
        "fewer_than_two_contributing_categories",
        "fewer_than_two_eligible_members",
        "no_contributing_members",
    ]


class RaceSensitivity(ScoreModel):
    race_id: str
    baseline: SensitivitySnapshot
    scenarios: list[SensitivityScenario]
    skipped_scenarios: list[SkippedScenario]
    classification: Classification
    material_scenario_ids: list[str]
    affected_scenario_kinds: list[ScenarioKind]
    illustrative_scenario_id: str | None
    summary: str
    warning: str | None


class SensitivityReport(ScoreModel):
    schema_version: Literal["1.0"] = "1.0"
    election_id: str
    dataset_hash: str
    source_registry_hash: str
    source_panel_id: str
    source_panel_hash: str
    publication_scope_hash: str
    scoring_configuration: ScoringConfiguration
    consensus_hash: str
    policy: SensitivityPolicy
    policy_hash: str
    computed_at: AwareDatetime
    git_commit: str = Field(min_length=1)
    publication_has_unresolved_high_severity: bool = Field(strict=True)
    races: list[RaceSensitivity]
