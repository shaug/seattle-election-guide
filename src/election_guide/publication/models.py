"""Strict publication, validation, and provenance artifact models."""

from __future__ import annotations

from fractions import Fraction
from typing import Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator

from election_guide.scoring.models import ComparisonStatus, Grade

HASH_PATTERN = r"^[0-9a-f]{64}$"
CellState = Literal[
    "endorsement",
    "multi_endorsement",
    "no_endorsement",
    "not_covered",
    "unavailable",
    "unverified",
    "not_applicable",
]
COMPARISON_BADGES: dict[ComparisonStatus, str] = {
    "agrees": "AGREES",
    "differs": "DIFFERENT PICK",
    "no_endorsement": "NO PICK",
    "not_covered": "NOT COVERED",
    "no_consensus": "NO PROGRESSIVE CONSENSUS",
}


class PublicationModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class PublicationSource(PublicationModel):
    id: str
    name: str
    category: str
    panel_role: Literal["consensus", "comparison"]
    organization_url: str
    evidence_url: str
    overlap_group_ids: list[str]
    endorsement_count: int = Field(ge=0, strict=True)
    split_endorsement_count: int = Field(ge=0, strict=True)
    contribution_status: Literal["contributing", "coverage_gap"]
    coverage_gap_status: Literal["not_found", "access_restricted"] | None = None
    coverage_gap_note: str | None = None

    @model_validator(mode="after")
    def validate_overlap_groups(self) -> PublicationSource:
        if self.overlap_group_ids != sorted(set(self.overlap_group_ids)):
            raise ValueError("publication source overlap group IDs must be unique and sorted")
        if self.split_endorsement_count > self.endorsement_count:
            raise ValueError("split endorsement count cannot exceed endorsement count")
        if self.contribution_status == "coverage_gap":
            if self.coverage_gap_status is None or not self.coverage_gap_note:
                raise ValueError("coverage-gap sources require a discovery status and note")
            if self.endorsement_count != 0 or self.split_endorsement_count != 0:
                raise ValueError("coverage-gap sources cannot carry participation counts")
        elif self.coverage_gap_status is not None or self.coverage_gap_note is not None:
            raise ValueError("contributing sources cannot carry coverage-gap details")
        return self


class SourceCell(PublicationModel):
    source_id: str
    state: CellState
    candidate_ids: list[str]
    candidate_labels: list[str]
    allocation: dict[str, str]
    evidence_url: str | None
    evidence_locator: str | None
    confidence_warning: bool = Field(strict=True)

    @model_validator(mode="after")
    def validate_state(self) -> SourceCell:
        candidate_count = len(self.candidate_ids)
        if len(set(self.candidate_ids)) != candidate_count:
            raise ValueError("cell candidate IDs must be unique")
        if self.state == "endorsement" and candidate_count != 1:
            raise ValueError("endorsement cell requires exactly one candidate")
        if self.state == "multi_endorsement" and candidate_count < 2:
            raise ValueError("multi-endorsement cell requires at least two candidates")
        if self.state not in {"endorsement", "multi_endorsement"} and candidate_count:
            raise ValueError(f"{self.state} cell cannot carry candidates")
        if len(self.candidate_ids) != len(self.candidate_labels):
            raise ValueError("cell candidate IDs and labels must align")
        if set(self.allocation) != set(self.candidate_ids):
            raise ValueError("cell allocation must match its candidates")
        try:
            allocations = [Fraction(value) for value in self.allocation.values()]
        except (ValueError, ZeroDivisionError) as error:
            raise ValueError("cell allocations must be exact rational strings") from error
        if any(
            str(value) != raw
            for value, raw in zip(allocations, self.allocation.values(), strict=True)
        ):
            raise ValueError("cell allocations must use canonical rational strings")
        if allocations and (any(value <= 0 for value in allocations) or sum(allocations) != 1):
            raise ValueError("cell allocations must be positive and sum exactly to one")
        if allocations and any(value != Fraction(1, candidate_count) for value in allocations):
            raise ValueError("cell allocations must use the exact equal split")
        if (self.evidence_url is None) != (self.evidence_locator is None):
            raise ValueError("cell evidence URL and locator must appear together")
        if (
            self.state
            in {
                "endorsement",
                "multi_endorsement",
                "no_endorsement",
                "unavailable",
                "unverified",
            }
            and self.evidence_url is None
        ):
            raise ValueError(f"{self.state} cell requires evidence")
        return self


class PublicationEndorser(PublicationModel):
    source_id: str = Field(min_length=1)
    source_name: str = Field(min_length=1)
    evidence_url: str = Field(min_length=1)
    evidence_locator: str = Field(min_length=1)
    co_endorsement: bool = Field(strict=True)
    confidence_warning: bool = Field(strict=True)


class PublicationChoiceEndorsements(PublicationModel):
    candidate_id: str = Field(min_length=1)
    candidate_label: str = Field(min_length=1)
    support_points: str
    source_count: int = Field(ge=1, strict=True)
    endorsers: list[PublicationEndorser] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_endorsements(self) -> PublicationChoiceEndorsements:
        if _fraction(self.support_points, "choice support") <= 0:
            raise ValueError("choice support must be positive")
        source_ids = [item.source_id for item in self.endorsers]
        if len(set(source_ids)) != len(source_ids):
            raise ValueError("choice endorsers must be unique")
        if self.source_count != len(self.endorsers):
            raise ValueError("choice source count must match endorsers")
        return self


class PublicationComparison(PublicationModel):
    source_id: str
    status: ComparisonStatus
    badge_label: str
    candidate_ids: list[str]
    candidate_labels: list[str]

    @model_validator(mode="after")
    def validate_comparison(self) -> PublicationComparison:
        if len(set(self.candidate_ids)) != len(self.candidate_ids):
            raise ValueError("comparison candidate IDs must be unique")
        if len(self.candidate_ids) != len(self.candidate_labels):
            raise ValueError("comparison candidate IDs and labels must align")
        has_candidates = bool(self.candidate_ids)
        if self.status in {"agrees", "differs", "no_consensus"} and not has_candidates:
            raise ValueError(f"{self.status} comparison requires candidates")
        if self.status in {"no_endorsement", "not_covered"} and has_candidates:
            raise ValueError(f"{self.status} comparison cannot carry candidates")
        if self.badge_label != COMPARISON_BADGES[self.status]:
            raise ValueError("comparison badge does not match its status")
        return self

    @property
    def voter_label(self) -> str:
        if self.candidate_labels:
            return " / ".join(self.candidate_labels)
        return "NOT COVERED"

    @property
    def voter_tone(self) -> Literal["agrees", "differs", "not_covered", "neutral"]:
        if self.status == "agrees":
            return "agrees"
        if self.status == "differs":
            return "differs"
        if self.status in {"no_endorsement", "not_covered"}:
            return "not_covered"
        return "neutral"

    @property
    def print_label(self) -> str:
        return f"{self.print_status_label} · {self.print_choice_label}"

    @property
    def print_status_label(self) -> str:
        if self.status == "agrees":
            return "Times agrees"
        if self.status == "differs":
            return "Times differs"
        return "Times"

    @property
    def print_choice_label(self) -> str:
        if self.candidate_labels:
            return self.voter_label
        return "not covered"

    @property
    def voter_accessible_label(self) -> str:
        if self.status == "agrees":
            return f"Seattle Times agrees with consensus: {self.voter_label}"
        if self.status == "differs":
            return f"Seattle Times endorses a different choice: {self.voter_label}"
        if self.status == "no_consensus":
            return (
                f"Seattle Times endorses {self.voter_label}; progressive sources have no consensus"
            )
        if self.status == "no_endorsement":
            return "Seattle Times made no endorsement"
        return "Seattle Times: not covered"


class PublicationAlternative(PublicationModel):
    candidate_id: str
    candidate_label: str
    support_points: str
    share: str
    percentage_label: str

    @model_validator(mode="after")
    def validate_values(self) -> PublicationAlternative:
        support = _fraction(self.support_points, "alternative support")
        share = _fraction(self.share, "alternative share")
        if support <= 0 or share <= 0 or share > 1:
            raise ValueError("alternative support and share must be positive")
        if self.percentage_label != f"{_percentage_whole(share)}%":
            raise ValueError("alternative percentage does not match its exact share")
        return self


class PublicationCategoryCandidateSupport(PublicationModel):
    candidate_id: str = Field(min_length=1)
    candidate_label: str = Field(min_length=1)
    support_points: str

    @model_validator(mode="after")
    def validate_support(self) -> PublicationCategoryCandidateSupport:
        if _fraction(self.support_points, "category candidate support") <= 0:
            raise ValueError("category candidate support must be positive")
        return self


class PublicationCategoryAnalysis(PublicationModel):
    category: str = Field(min_length=1)
    label: str = Field(min_length=1)
    eligible_source_count: int = Field(ge=0, strict=True)
    source_coverage_count: int = Field(ge=0, strict=True)
    explicit_endorsement_count: int = Field(ge=0, strict=True)
    candidate_support: list[PublicationCategoryCandidateSupport]

    @model_validator(mode="after")
    def validate_analysis(self) -> PublicationCategoryAnalysis:
        if self.source_coverage_count > self.eligible_source_count:
            raise ValueError("category coverage cannot exceed eligible sources")
        if self.explicit_endorsement_count > self.source_coverage_count:
            raise ValueError("category explicit endorsements cannot exceed coverage")
        candidate_ids = [item.candidate_id for item in self.candidate_support]
        if candidate_ids != sorted(set(candidate_ids)):
            raise ValueError("category candidate support must be unique and sorted")
        total_support = sum(
            (
                _fraction(item.support_points, "category candidate support")
                for item in self.candidate_support
            ),
            Fraction(),
        )
        if total_support != self.explicit_endorsement_count:
            raise ValueError("category candidate support must sum to explicit endorsements")
        return self


class PublicationRace(PublicationModel):
    id: str
    section_id: str
    section_label: str
    jurisdiction_id: str
    race_label: str
    filter_tokens: list[str]
    support_leader_candidate_ids: list[str]
    support_leader_candidate_labels: list[str]
    support_leader_label: str
    recommendation_candidate_ids: list[str]
    recommendation_candidate_labels: list[str]
    recommendation_label: str
    grade: Grade
    winner_share: str | None
    percentage_label: str
    percentage_whole: int | None = Field(default=None, ge=0, le=100, strict=True)
    support_summary: str
    explicit_endorsement_count: int = Field(ge=0, strict=True)
    eligible_source_count: int = Field(ge=0, strict=True)
    source_coverage_count: int = Field(ge=0, strict=True)
    category_coverage_count: int = Field(ge=0, strict=True)
    no_endorsement_count: int = Field(ge=0, strict=True)
    missing_source_count: int = Field(ge=0, strict=True)
    endorsement_groups: list[PublicationChoiceEndorsements]
    category_breakdown: list[PublicationCategoryAnalysis]
    alternatives: list[PublicationAlternative]
    comparisons: list[PublicationComparison]
    warning_codes: list[str]
    warning_messages: list[str]
    source_cells: list[SourceCell]

    @model_validator(mode="after")
    def validate_display_semantics(self) -> PublicationRace:
        if len(set(self.support_leader_candidate_ids)) != len(self.support_leader_candidate_ids):
            raise ValueError("support leader candidate IDs must be unique")
        if len(self.support_leader_candidate_ids) != len(self.support_leader_candidate_labels):
            raise ValueError("support leader IDs and labels must align")
        if len(self.recommendation_candidate_ids) != len(self.recommendation_candidate_labels):
            raise ValueError("recommendation IDs and labels must align")
        expected_leader_label = (
            " / ".join(self.support_leader_candidate_labels)
            if self.support_leader_candidate_labels
            else "No leader"
        )
        if self.support_leader_label != expected_leader_label:
            raise ValueError("support leader label does not match its candidates")
        if self.grade == "Insufficient":
            if len(self.support_leader_candidate_ids) > 1:
                raise ValueError("insufficient coverage cannot have multiple support leaders")
            if self.recommendation_candidate_ids or self.recommendation_candidate_labels:
                raise ValueError("insufficient coverage cannot carry a recommendation")
            if self.recommendation_label != "Too few endorsements":
                raise ValueError("insufficient recommendation label is invalid")
        else:
            if self.grade == "TIED" and len(self.support_leader_candidate_ids) < 2:
                raise ValueError("tied grade requires multiple support leaders")
            if self.grade != "TIED" and len(self.support_leader_candidate_ids) != 1:
                raise ValueError("ordinary grade requires exactly one support leader")
            if self.recommendation_candidate_ids != self.support_leader_candidate_ids:
                raise ValueError("recommendation candidates must equal the support leaders")
            if self.recommendation_candidate_labels != self.support_leader_candidate_labels:
                raise ValueError("recommendation labels must equal the support leader labels")
            expected_recommendation_label = (
                " / ".join(self.recommendation_candidate_labels)
                if self.grade == "TIED"
                else self.recommendation_candidate_labels[0]
                if self.recommendation_candidate_labels
                else "No consensus"
            )
            if self.recommendation_label != expected_recommendation_label:
                raise ValueError("recommendation label does not match its candidates")
        if len(self.warning_codes) != len(self.warning_messages):
            raise ValueError("warning codes and messages must align")
        if len({item.source_id for item in self.comparisons}) != len(self.comparisons):
            raise ValueError("race comparison sources must be unique")
        if len({item.source_id for item in self.source_cells}) != len(self.source_cells):
            raise ValueError("race source cells must be unique")
        if len({item.candidate_id for item in self.alternatives}) != len(self.alternatives):
            raise ValueError("alternative candidates must be unique")
        if {item.candidate_id for item in self.alternatives} & set(
            self.support_leader_candidate_ids
        ):
            raise ValueError("support leaders cannot also be notable alternatives")
        if self.source_coverage_count != (
            self.explicit_endorsement_count + self.no_endorsement_count
        ):
            raise ValueError("source coverage counts do not reconcile")
        if self.missing_source_count != self.eligible_source_count - self.source_coverage_count:
            raise ValueError("missing and eligible source counts do not reconcile")
        categories = [item.category for item in self.category_breakdown]
        if categories != sorted(set(categories)):
            raise ValueError("race category breakdown must be unique and sorted")
        if (
            sum(item.eligible_source_count for item in self.category_breakdown)
            != self.eligible_source_count
        ):
            raise ValueError("category eligibility must reconcile to the race")
        if (
            sum(item.source_coverage_count for item in self.category_breakdown)
            != self.source_coverage_count
        ):
            raise ValueError("category coverage must reconcile to the race")
        if (
            sum(item.explicit_endorsement_count for item in self.category_breakdown)
            != self.explicit_endorsement_count
        ):
            raise ValueError("category explicit endorsements must reconcile to the race")
        if (
            sum(item.source_coverage_count > 0 for item in self.category_breakdown)
            != self.category_coverage_count
        ):
            raise ValueError("represented category count must reconcile to the race")
        if self.winner_share is None:
            if self.support_leader_candidate_ids:
                raise ValueError("support leaders require an exact winner share")
            if self.percentage_whole is not None or self.percentage_label != "—":
                raise ValueError("missing share requires an unavailable percentage")
        else:
            if not self.support_leader_candidate_ids:
                raise ValueError("winner share requires at least one support leader")
            share = _fraction(self.winner_share, "winner share")
            if share <= 0 or share > 1:
                raise ValueError("winner share must be positive and at most one")
            percentage = _percentage_whole(share)
            if self.percentage_whole != percentage or self.percentage_label != f"{percentage}%":
                raise ValueError("winner percentage does not match its exact share")
        return self


class PublicationSection(PublicationModel):
    id: str
    label: str
    races: list[PublicationRace]


class GradeLegendItem(PublicationModel):
    grade: str
    rule: str


class SourceCategoryGroup(PublicationModel):
    category: str
    label: str
    source_ids: list[str]


class SourceOverlapGroup(PublicationModel):
    id: str = Field(pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
    label: str = Field(min_length=1)
    description: str = Field(min_length=1)
    relationship: Literal["possible_overlap"] = "possible_overlap"
    source_ids: list[str] = Field(min_length=2)

    @model_validator(mode="after")
    def validate_sources(self) -> SourceOverlapGroup:
        if self.source_ids != sorted(set(self.source_ids)):
            raise ValueError("overlap group source IDs must be unique and sorted")
        return self


class PublicationMethodology(PublicationModel):
    process_steps: list[str]
    grade_legend: list[GradeLegendItem]
    source_categories: list[SourceCategoryGroup]
    source_overlap_groups: list[SourceOverlapGroup]
    default_aggregation_view: Literal["source_level"] = "source_level"
    deduplicated_view: Literal["not_computed"] = "not_computed"
    interpretation_notes: list[str]
    limitations: list[str]
    verification_instructions: str


class PublicationMetadata(PublicationModel):
    election_id: str
    election_name: str
    election_date: str
    generated_at: AwareDatetime
    data_version: str
    git_commit: str = Field(min_length=1)
    source_count: int = Field(ge=0, strict=True)
    captured_source_count: int = Field(ge=0, strict=True)
    unavailable_source_count: int = Field(ge=0, strict=True)
    contributing_source_count: int = Field(ge=0, strict=True)
    coverage_gap_count: int = Field(ge=0, strict=True)
    race_count: int = Field(ge=0, strict=True)
    published_race_count: int = Field(ge=0, strict=True)
    unresolved_review_count: int = Field(ge=0, strict=True)

    @model_validator(mode="after")
    def validate_source_counts(self) -> PublicationMetadata:
        if self.captured_source_count + self.unavailable_source_count != self.source_count:
            raise ValueError("captured and unavailable source counts must equal active sources")
        if self.contributing_source_count + self.coverage_gap_count != self.source_count:
            raise ValueError("contributing and coverage-gap counts must equal active sources")
        return self


class PublicationViewModel(PublicationModel):
    schema_version: Literal["1.4"] = "1.4"
    metadata: PublicationMetadata
    sources: list[PublicationSource]
    sections: list[PublicationSection]
    methodology: PublicationMethodology

    @model_validator(mode="after")
    def validate_topology(self) -> PublicationViewModel:
        source_ids = [source.id for source in self.sources]
        if len(set(source_ids)) != len(source_ids):
            raise ValueError("publication source IDs must be unique")
        if len({section.id for section in self.sections}) != len(self.sections):
            raise ValueError("publication section IDs must be unique")
        races = [race for section in self.sections for race in section.races]
        if len({race.id for race in races}) != len(races):
            raise ValueError("publication race IDs must be unique")
        ordered_comparison_ids = [
            source.id for source in self.sources if source.panel_role == "comparison"
        ]
        source_by_id = {source.id: source for source in self.sources}
        category_labels = {
            category.category: category.label for category in self.methodology.source_categories
        }
        expected_category_order = list(dict.fromkeys(source.category for source in self.sources))
        if [category.category for category in self.methodology.source_categories] != (
            expected_category_order
        ):
            raise ValueError("methodology source categories must follow publication source order")
        for category in self.methodology.source_categories:
            if category.source_ids != [
                source.id for source in self.sources if source.category == category.category
            ]:
                raise ValueError("methodology source categories must match publication sources")
        overlap_groups = self.methodology.source_overlap_groups
        expected_endorsement_counts = {source.id: 0 for source in self.sources}
        expected_split_counts = {source.id: 0 for source in self.sources}
        if [group.id for group in overlap_groups] != sorted({group.id for group in overlap_groups}):
            raise ValueError("methodology overlap groups must be unique and sorted")
        declared_overlap_members: dict[str, set[str]] = {}
        for source in self.sources:
            for group_id in source.overlap_group_ids:
                declared_overlap_members.setdefault(group_id, set()).add(source.id)
        expected_overlap_members = declared_overlap_members
        actual_overlap_members = {group.id: set(group.source_ids) for group in overlap_groups}
        if actual_overlap_members != expected_overlap_members:
            raise ValueError("methodology overlap groups must match active source metadata")
        for group in overlap_groups:
            unknown_source_ids = set(group.source_ids) - set(source_ids)
            if unknown_source_ids:
                raise ValueError(
                    "methodology overlap group contains unknown sources: "
                    f"{sorted(unknown_source_ids)}"
                )
        for section in self.sections:
            for race in section.races:
                if race.section_id != section.id or race.section_label != section.label:
                    raise ValueError("race section metadata does not match its container")
                if [cell.source_id for cell in race.source_cells] != source_ids:
                    raise ValueError("race source cells must match the ordered source registry")
                if [item.source_id for item in race.comparisons] != ordered_comparison_ids:
                    raise ValueError("race comparisons must match the ordered comparison sources")
                for cell in race.source_cells:
                    if cell.state in {"endorsement", "multi_endorsement"}:
                        expected_endorsement_counts[cell.source_id] += 1
                    if cell.state == "multi_endorsement":
                        expected_split_counts[cell.source_id] += 1
                consensus_cells = [
                    cell
                    for cell in race.source_cells
                    if source_by_id[cell.source_id].panel_role == "consensus"
                ]
                eligible_cells = [
                    cell for cell in consensus_cells if cell.state != "not_applicable"
                ]
                explicit_cells = [
                    cell
                    for cell in eligible_cells
                    if cell.state in {"endorsement", "multi_endorsement"}
                ]
                no_endorsement_cells = [
                    cell for cell in eligible_cells if cell.state == "no_endorsement"
                ]
                represented_categories = {
                    source_by_id[cell.source_id].category
                    for cell in [*explicit_cells, *no_endorsement_cells]
                }
                if race.eligible_source_count != len(eligible_cells):
                    raise ValueError("eligible source count does not match source cells")
                if race.explicit_endorsement_count != len(explicit_cells):
                    raise ValueError("explicit endorsement count does not match source cells")
                if race.no_endorsement_count != len(no_endorsement_cells):
                    raise ValueError("no-endorsement count does not match source cells")
                if race.source_coverage_count != len(explicit_cells) + len(no_endorsement_cells):
                    raise ValueError("source coverage count does not match source cells")
                if race.missing_source_count != len(eligible_cells) - race.source_coverage_count:
                    raise ValueError("missing source count does not match source cells")
                if race.category_coverage_count != len(represented_categories):
                    raise ValueError("category coverage count does not match source cells")
                support_by_candidate: dict[str, Fraction] = {}
                cells_by_candidate: dict[str, list[SourceCell]] = {}
                labels_by_candidate: dict[str, str] = {}
                for cell in explicit_cells:
                    for candidate_id, candidate_label in zip(
                        cell.candidate_ids, cell.candidate_labels, strict=True
                    ):
                        previous_label = labels_by_candidate.setdefault(
                            candidate_id, candidate_label
                        )
                        if previous_label != candidate_label:
                            raise ValueError("candidate labels conflict across source cells")
                        support_by_candidate[candidate_id] = support_by_candidate.get(
                            candidate_id, Fraction()
                        ) + _fraction(cell.allocation[candidate_id], "cell allocation")
                        cells_by_candidate.setdefault(candidate_id, []).append(cell)
                expected_group_ids = sorted(
                    support_by_candidate,
                    key=lambda candidate_id: (-support_by_candidate[candidate_id], candidate_id),
                )
                if [group.candidate_id for group in race.endorsement_groups] != expected_group_ids:
                    raise ValueError("race endorsement groups must match affirmative support order")
                for group in race.endorsement_groups:
                    expected_cells = cells_by_candidate[group.candidate_id]
                    expected_endorsers = [
                        (
                            cell.source_id,
                            source_by_id[cell.source_id].name,
                            cell.evidence_url,
                            cell.evidence_locator,
                            cell.state == "multi_endorsement",
                            cell.confidence_warning,
                        )
                        for cell in expected_cells
                    ]
                    actual_endorsers = [
                        (
                            endorser.source_id,
                            endorser.source_name,
                            endorser.evidence_url,
                            endorser.evidence_locator,
                            endorser.co_endorsement,
                            endorser.confidence_warning,
                        )
                        for endorser in group.endorsers
                    ]
                    if (
                        group.candidate_label != labels_by_candidate[group.candidate_id]
                        or _fraction(group.support_points, "choice support")
                        != support_by_candidate[group.candidate_id]
                        or group.source_count != len(expected_cells)
                        or actual_endorsers != expected_endorsers
                    ):
                        raise ValueError(
                            "race endorsement groups must match affirmative source cells"
                        )
                candidate_labels: dict[str, str] = {}
                eligible_by_category: dict[str, int] = {}
                covered_by_category: dict[str, int] = {}
                explicit_by_category: dict[str, int] = {}
                support_by_category: dict[str, dict[str, Fraction]] = {}
                for cell in eligible_cells:
                    category = source_by_id[cell.source_id].category
                    eligible_by_category[category] = eligible_by_category.get(category, 0) + 1
                    if cell.state in {"endorsement", "multi_endorsement", "no_endorsement"}:
                        covered_by_category[category] = covered_by_category.get(category, 0) + 1
                    if cell.state in {"endorsement", "multi_endorsement"}:
                        explicit_by_category[category] = explicit_by_category.get(category, 0) + 1
                        support = support_by_category.setdefault(category, {})
                        for candidate_id, label in zip(
                            cell.candidate_ids, cell.candidate_labels, strict=True
                        ):
                            previous_label = candidate_labels.setdefault(candidate_id, label)
                            if previous_label != label:
                                raise ValueError("candidate labels conflict across source cells")
                            support[candidate_id] = support.get(
                                candidate_id, Fraction()
                            ) + _fraction(cell.allocation[candidate_id], "cell allocation")
                actual_categories = {item.category: item for item in race.category_breakdown}
                if set(actual_categories) != set(eligible_by_category):
                    raise ValueError("race category breakdown does not match eligible source cells")
                for category, eligible_count in eligible_by_category.items():
                    actual = actual_categories[category]
                    if actual.label != category_labels.get(category):
                        raise ValueError("race category label does not match methodology")
                    actual_support = {
                        item.candidate_id: _fraction(
                            item.support_points, "category candidate support"
                        )
                        for item in actual.candidate_support
                    }
                    actual_labels = {
                        item.candidate_id: item.candidate_label for item in actual.candidate_support
                    }
                    if (
                        actual.eligible_source_count != eligible_count
                        or actual.source_coverage_count != covered_by_category.get(category, 0)
                        or actual.explicit_endorsement_count
                        != explicit_by_category.get(category, 0)
                        or actual_support != support_by_category.get(category, {})
                        or actual_labels
                        != {
                            candidate_id: candidate_labels[candidate_id]
                            for candidate_id in support_by_category.get(category, {})
                        }
                    ):
                        raise ValueError("race category analysis does not match source cells")
        for source in self.sources:
            if (
                source.endorsement_count != expected_endorsement_counts[source.id]
                or source.split_endorsement_count != expected_split_counts[source.id]
            ):
                raise ValueError("source participation counts do not match published source cells")
        contributing_source_count = sum(
            source.contribution_status == "contributing" for source in self.sources
        )
        coverage_gap_count = sum(
            source.contribution_status == "coverage_gap" for source in self.sources
        )
        if self.metadata.source_count != len(self.sources):
            raise ValueError("metadata source count does not match the view model")
        if (
            self.metadata.contributing_source_count != contributing_source_count
            or self.metadata.coverage_gap_count != coverage_gap_count
        ):
            raise ValueError("metadata contribution counts do not match publication sources")
        if self.metadata.published_race_count != len(races):
            raise ValueError("metadata published race count does not match the view model")
        if self.metadata.race_count < self.metadata.published_race_count:
            raise ValueError("metadata race count cannot be below the published count")
        return self


class ValidationCheck(PublicationModel):
    id: str
    passed: bool = Field(strict=True)
    message: str


class ValidationReport(PublicationModel):
    schema_version: Literal["1.0"] = "1.0"
    election_id: str
    generated_at: AwareDatetime
    passed: bool = Field(strict=True)
    checks: list[ValidationCheck]


class ProvenanceManifest(PublicationModel):
    schema_version: Literal["1.0"] = "1.0"
    election_id: str
    generated_at: AwareDatetime
    configuration_hashes: dict[str, str]
    input_snapshot_hashes: dict[str, str]
    normalized_data_hash: str = Field(pattern=HASH_PATTERN)
    consensus_output_hash: str = Field(pattern=HASH_PATTERN)
    dataset_hash: str = Field(pattern=HASH_PATTERN)


class BuildManifest(PublicationModel):
    schema_version: Literal["1.0"] = "1.0"
    election_id: str
    generated_at: AwareDatetime
    git_commit: str = Field(min_length=1)
    configuration_hash: str = Field(pattern=HASH_PATTERN)
    input_snapshot_hashes: dict[str, str]
    normalized_data_hash: str = Field(pattern=HASH_PATTERN)
    consensus_output_hash: str = Field(pattern=HASH_PATTERN)
    artifact_hashes: dict[str, str]
    source_count: int = Field(ge=0, strict=True)
    race_count: int = Field(ge=0, strict=True)
    published_race_count: int = Field(ge=0, strict=True)
    unresolved_review_count: int = Field(ge=0, strict=True)
    warnings: list[str]


def _fraction(raw: str, label: str) -> Fraction:
    try:
        value = Fraction(raw)
    except (ValueError, ZeroDivisionError) as error:
        raise ValueError(f"{label} must be an exact rational string") from error
    if str(value) != raw:
        raise ValueError(f"{label} must use a canonical rational string")
    return value


def _percentage_whole(share: Fraction) -> int:
    scaled = share * 100
    return (scaled.numerator * 2 + scaled.denominator) // (2 * scaled.denominator)
