"""Exact, deterministic source-level consensus scoring."""

from __future__ import annotations

import hashlib
from collections import defaultdict
from datetime import datetime
from fractions import Fraction
from typing import cast

from pydantic import BaseModel

from election_guide.inventory.models import Race
from election_guide.normalization.matching import eligible_race_ids
from election_guide.normalization.models import (
    CanonicalDataset,
    ExtractedClaim,
    NormalizedEndorsement,
    ReviewDecision,
    ReviewItem,
)
from election_guide.normalization.semantics import EXPLICIT_STATUSES
from election_guide.scoring.models import (
    CandidateStanding,
    CategoryConsensus,
    ComparisonResult,
    ConsensusReport,
    RaceConsensus,
    ScoreWarning,
    ScoringConfiguration,
)
from election_guide.serialization import canonical_json_bytes
from election_guide.sources.models import Source

NO_ENDORSEMENT_STATUSES = {"no_endorsement", "declined_to_endorse"}


class PublicationBlockedError(ValueError):
    """Raised when unresolved high-severity review work makes publication unsafe."""

    def __init__(self, review_item_ids: list[str]) -> None:
        self.review_item_ids = review_item_ids
        super().__init__(
            "publication blocked by unresolved high-severity review items: "
            + ", ".join(review_item_ids)
        )


def score_dataset(
    dataset: CanonicalDataset,
    configuration: ScoringConfiguration,
    *,
    computed_at: datetime,
    allow_unresolved: bool = False,
) -> ConsensusReport:
    """Score every publication-eligible race from validated canonical inputs."""
    if computed_at.tzinfo is None or computed_at.utcoffset() is None:
        raise ValueError("computed_at must include a UTC offset")
    effective = dataset.effective_records()
    latest_input_at = _latest_input_timestamp(dataset, effective)
    if computed_at < latest_input_at:
        raise ValueError(
            f"computed_at {computed_at.isoformat()} predates scoring input "
            f"{latest_input_at.isoformat()}"
        )
    source_by_id = {source.id: source for source in dataset.source_registry.sources}
    _validate_comparison_sources(configuration, source_by_id)

    endorsements = sorted(
        (cast(NormalizedEndorsement, effective[item.id]) for item in dataset.endorsements),
        key=lambda item: (item.race_id, item.source_id, item.id),
    )
    claims = {item.id: cast(ExtractedClaim, effective[item.id]) for item in dataset.claims}
    review_items = {item.id: cast(ReviewItem, effective[item.id]) for item in dataset.review_items}
    decisions = [cast(ReviewDecision, effective[item.id]) for item in dataset.review_decisions]
    decided_review_ids = {decision.review_item_id for decision in decisions}
    unresolved = sorted(
        (item for item in review_items.values() if item.id not in decided_review_ids),
        key=lambda item: item.id,
    )
    relevant_review_races = {
        item.id: _relevant_review_race_ids(
            item,
            claims[item.claim_id].source_id,
            dataset,
            configuration,
        )
        for item in unresolved
    }
    relevant_unresolved = [item for item in unresolved if relevant_review_races[item.id]]
    unresolved_high = [item for item in relevant_unresolved if item.severity == "high"]
    if unresolved_high and not allow_unresolved:
        raise PublicationBlockedError([item.id for item in unresolved_high])

    races = [race for race in dataset.inventory.races if race.publication_eligible]
    publication_race_ids = [race.id for race in races]
    dataset_hash, publication_scope_hash, input_hash = _input_hashes(
        dataset,
        configuration,
        publication_race_ids,
    )
    endorsements_by_race: dict[str, list[NormalizedEndorsement]] = defaultdict(list)
    for endorsement in endorsements:
        endorsements_by_race[endorsement.race_id].append(endorsement)

    results = [
        _score_race(
            race,
            dataset,
            configuration,
            endorsements_by_race.get(race.id, []),
            claims,
            relevant_unresolved,
            unresolved_high,
            relevant_review_races,
            input_hash,
            computed_at,
        )
        for race in races
    ]
    return ConsensusReport.model_validate(
        {
            "election_id": dataset.inventory.election.id,
            "configuration_id": configuration.id,
            "scoring_configuration": configuration,
            "computed_at": computed_at,
            "dataset_hash": dataset_hash,
            "publication_scope_hash": publication_scope_hash,
            "input_hash": input_hash,
            "publication_race_ids": publication_race_ids,
            "publication_has_unresolved_high_severity": bool(unresolved_high),
            "races": results,
        },
        context={
            "canonical_dataset": dataset,
            "skip_derived_validation": True,
        },
    )


def _score_race(
    race: Race,
    dataset: CanonicalDataset,
    configuration: ScoringConfiguration,
    race_endorsements: list[NormalizedEndorsement],
    claims: dict[str, ExtractedClaim],
    unresolved: list[ReviewItem],
    unresolved_high: list[ReviewItem],
    relevant_review_races: dict[str, set[str]],
    input_hash: str,
    computed_at: datetime,
) -> RaceConsensus:
    endorsement_by_source = {item.source_id: item for item in race_endorsements}
    for endorsement in race_endorsements:
        if endorsement.status in EXPLICIT_STATUSES:
            _validate_exact_equal_split(endorsement)
    eligible_sources = sorted(
        (
            source
            for source in dataset.source_registry.sources
            if source.panel_role == "consensus"
            and race.id in eligible_race_ids(source.id, dataset.inventory, dataset.source_registry)
        ),
        key=lambda source: source.id,
    )
    explicit = [
        endorsement_by_source[source.id]
        for source in eligible_sources
        if source.id in endorsement_by_source
        and endorsement_by_source[source.id].status in EXPLICIT_STATUSES
    ]
    no_endorsements = [
        endorsement_by_source[source.id]
        for source in eligible_sources
        if source.id in endorsement_by_source
        and endorsement_by_source[source.id].status in NO_ENDORSEMENT_STATUSES
    ]
    covered_source_ids = {item.source_id for item in (*explicit, *no_endorsements)}
    missing_source_ids = [
        source.id for source in eligible_sources if source.id not in covered_source_ids
    ]

    support: dict[str, Fraction] = defaultdict(Fraction)
    for endorsement in explicit:
        for candidate_id, points in endorsement.allocation.items():
            support[candidate_id] += points
    ordered_support = _ordered_support(race, support)
    total_points = sum(ordered_support.values(), Fraction())
    maximum = max(ordered_support.values(), default=None)
    winner_ids = (
        [candidate_id for candidate_id, points in ordered_support.items() if points == maximum]
        if maximum is not None
        else []
    )
    is_tied = len(winner_ids) > 1
    winner_id = winner_ids[0] if len(winner_ids) == 1 else None
    winner_share = None if maximum is None or total_points == 0 else maximum / total_points
    grade = configuration.grade_for(len(explicit), winner_share, is_tied=is_tied)

    alternatives = [
        CandidateStanding(
            candidate_id=candidate_id,
            support_points=points,
            share=points / total_points,
        )
        for candidate_id, points in sorted(
            ordered_support.items(),
            key=lambda item: (-item[1], _ballot_order(race, item[0])),
        )
        if candidate_id not in winner_ids and total_points > 0
    ]
    categories = _category_breakdown(eligible_sources, endorsement_by_source, race)
    represented_categories = {
        source.category for source in eligible_sources if source.id in covered_source_ids
    }
    eligible_categories = {source.category for source in eligible_sources}
    race_pending = [item for item in unresolved if race.id in relevant_review_races[item.id]]
    race_high = [item for item in unresolved_high if race.id in relevant_review_races[item.id]]
    displayed_endorsements = [
        item
        for item in race_endorsements
        if (
            item.source_id in {source.id for source in eligible_sources}
            or item.source_id in configuration.comparison_source_ids
        )
    ]
    low_confidence_sources = sorted(
        {
            item.source_id
            for item in displayed_endorsements
            if item.normalization_confidence < 1
            or claims[item.extracted_claim_id].extraction_confidence < 1
            or claims[item.extracted_claim_id].requires_review
        }
    )
    overlap_source_ids = _overlap_sources(eligible_sources, dataset)
    high_review_item_ids = sorted(item.id for item in race_high)
    warnings = _warnings(
        configuration,
        len(explicit),
        no_endorsements,
        missing_source_ids,
        represented_categories,
        eligible_categories,
        race_pending,
        race_high,
        low_confidence_sources,
        overlap_source_ids,
    )
    comparisons = [
        _comparison_result(
            source_id,
            endorsement_by_source.get(source_id),
            winner_id if grade not in {"TIED", "Insufficient"} else None,
        )
        for source_id in configuration.comparison_source_ids
    ]
    return RaceConsensus(
        race_id=race.id,
        configuration_id=configuration.id,
        eligible_source_count=len(eligible_sources),
        source_coverage_count=len(covered_source_ids),
        category_coverage_count=len(represented_categories),
        explicit_endorsement_count=len(explicit),
        no_endorsement_count=len(no_endorsements),
        missing_source_count=len(missing_source_ids),
        pending_review_count=len(race_pending),
        low_confidence_source_ids=low_confidence_sources,
        overlap_source_ids=overlap_source_ids,
        unresolved_high_severity_review_item_ids=high_review_item_ids,
        candidate_support=ordered_support,
        winner_candidate_ids=winner_ids,
        winner_candidate_id=winner_id,
        winner_support_points=maximum,
        winner_share=winner_share,
        grade=grade,
        is_tied=is_tied,
        notable_alternatives=alternatives,
        category_breakdown=categories,
        comparison_results=comparisons,
        warnings=warnings,
        computed_at=computed_at,
        input_hash=input_hash,
    )


def _category_breakdown(
    eligible_sources: list[Source],
    endorsement_by_source: dict[str, NormalizedEndorsement],
    race: Race,
) -> list[CategoryConsensus]:
    categories = sorted({source.category for source in eligible_sources})
    results: list[CategoryConsensus] = []
    for category in categories:
        sources = [source for source in eligible_sources if source.category == category]
        endorsements = [
            endorsement_by_source[source.id]
            for source in sources
            if source.id in endorsement_by_source
        ]
        explicit = [item for item in endorsements if item.status in EXPLICIT_STATUSES]
        covered = [
            item
            for item in endorsements
            if item.status in EXPLICIT_STATUSES or item.status in NO_ENDORSEMENT_STATUSES
        ]
        support: dict[str, Fraction] = defaultdict(Fraction)
        for endorsement in explicit:
            for candidate_id, points in endorsement.allocation.items():
                support[candidate_id] += points
        results.append(
            CategoryConsensus(
                category=category,
                eligible_source_count=len(sources),
                source_coverage_count=len(covered),
                explicit_endorsement_count=len(explicit),
                candidate_support=_ordered_support(race, support),
            )
        )
    return results


def _comparison_result(
    source_id: str,
    endorsement: NormalizedEndorsement | None,
    winner_id: str | None,
) -> ComparisonResult:
    if endorsement is None or endorsement.status not in EXPLICIT_STATUSES | NO_ENDORSEMENT_STATUSES:
        status = "not_covered"
        candidate_ids: list[str] = []
    elif endorsement.status in NO_ENDORSEMENT_STATUSES:
        status = "no_endorsement"
        candidate_ids = []
    elif winner_id is None:
        status = "no_consensus"
        candidate_ids = endorsement.candidate_ids
    elif winner_id in endorsement.candidate_ids:
        status = "agrees"
        candidate_ids = endorsement.candidate_ids
    else:
        status = "differs"
        candidate_ids = endorsement.candidate_ids
    return ComparisonResult(source_id=source_id, status=status, candidate_ids=candidate_ids)


def _warnings(
    configuration: ScoringConfiguration,
    explicit_count: int,
    no_endorsements: list[NormalizedEndorsement],
    missing_source_ids: list[str],
    represented_categories: set[str],
    eligible_categories: set[str],
    pending: list[ReviewItem],
    high: list[ReviewItem],
    low_confidence_source_ids: list[str],
    overlap_source_ids: list[str],
) -> list[ScoreWarning]:
    warnings: list[ScoreWarning] = []
    if explicit_count < configuration.minimum_explicit_sources:
        warnings.append(
            ScoreWarning(
                code="low_coverage",
                message=(
                    f"Only {explicit_count} eligible sources make an explicit endorsement; "
                    f"{configuration.minimum_explicit_sources} are required for an ordinary grade."
                ),
            )
        )
    if missing_source_ids:
        warnings.append(
            ScoreWarning(
                code="missing_coverage",
                message=f"{len(missing_source_ids)} eligible sources lack a resolved decision.",
                source_ids=missing_source_ids,
            )
        )
    if represented_categories != eligible_categories:
        warnings.append(
            ScoreWarning(
                code="low_category_coverage",
                message=(
                    f"Resolved decisions cover {len(represented_categories)} of "
                    f"{len(eligible_categories)} eligible source categories."
                ),
            )
        )
    if no_endorsements:
        warnings.append(
            ScoreWarning(
                code="no_endorsement",
                message=f"{len(no_endorsements)} eligible sources explicitly endorse no one.",
                source_ids=sorted(item.source_id for item in no_endorsements),
            )
        )
    if pending:
        warnings.append(
            ScoreWarning(
                code="pending_review",
                message=f"{len(pending)} normalization review items remain unresolved.",
                review_item_ids=sorted(item.id for item in pending),
            )
        )
    if low_confidence_source_ids:
        warnings.append(
            ScoreWarning(
                code="low_confidence",
                message="One or more scored endorsements carry a confidence warning.",
                source_ids=low_confidence_source_ids,
            )
        )
    if overlap_source_ids:
        warnings.append(
            ScoreWarning(
                code="source_overlap",
                message="Eligible sources have disclosed organizational overlap.",
                source_ids=overlap_source_ids,
            )
        )
    if high:
        warnings.append(
            ScoreWarning(
                code="unresolved_high_severity",
                message="Publication was explicitly allowed despite high-severity review items.",
                review_item_ids=sorted(item.id for item in high),
            )
        )
    return warnings


def _overlap_sources(eligible_sources: list[Source], dataset: CanonicalDataset) -> list[str]:
    eligible_ids = {source.id for source in eligible_sources}
    overlapping: set[str] = set()
    for group in dataset.source_registry.overlap_groups:
        members = eligible_ids & set(group.member_ids)
        if len(members) > 1:
            overlapping.update(members)
    return sorted(overlapping)


def _review_race_ids(item: ReviewItem) -> set[str]:
    race_match = item.race_match
    if race_match is None:
        return set()
    race_ids = {candidate.record_id for candidate in race_match.candidates}
    if race_match.selected_id is not None:
        race_ids.add(race_match.selected_id)
    return race_ids


def _relevant_review_race_ids(
    item: ReviewItem,
    source_id: str,
    dataset: CanonicalDataset,
    configuration: ScoringConfiguration,
) -> set[str]:
    source = next(source for source in dataset.source_registry.sources if source.id == source_id)
    if source.panel_role == "consensus" or (
        source.panel_role == "comparison" and source_id in configuration.comparison_source_ids
    ):
        eligible = eligible_race_ids(source_id, dataset.inventory, dataset.source_registry)
    else:
        return set()
    matched = _review_race_ids(item)
    return eligible if not matched else eligible & matched


def _ordered_support(race: Race, support: dict[str, Fraction]) -> dict[str, Fraction]:
    return {
        choice.id: support[choice.id]
        for choice in sorted(race.choices, key=lambda item: item.ballot_order)
        if choice.id in support
    }


def _ballot_order(race: Race, candidate_id: str) -> int:
    return next(choice.ballot_order for choice in race.choices if choice.id == candidate_id)


def _validate_comparison_sources(
    configuration: ScoringConfiguration,
    source_by_id: dict[str, Source],
) -> None:
    for source_id in configuration.comparison_source_ids:
        source = source_by_id.get(source_id)
        if source is None:
            raise ValueError(
                f"scoring configuration references unknown comparison source {source_id!r}"
            )
        if source.panel_role != "comparison":
            raise ValueError(f"configured comparison source {source_id!r} is not comparison-only")


def _input_hashes(
    dataset: CanonicalDataset,
    configuration: ScoringConfiguration,
    publication_race_ids: list[str],
) -> tuple[str, str, str]:
    dataset_hash = hashlib.sha256(canonical_json_bytes(dataset.model_dump(mode="json"))).hexdigest()
    publication_scope_hash = hashlib.sha256(canonical_json_bytes(publication_race_ids)).hexdigest()
    payload = {
        "dataset_hash": dataset_hash,
        "publication_scope_hash": publication_scope_hash,
        "scoring_configuration": configuration.model_dump(mode="json"),
    }
    return (
        dataset_hash,
        publication_scope_hash,
        hashlib.sha256(canonical_json_bytes(payload)).hexdigest(),
    )


def _validate_exact_equal_split(endorsement: NormalizedEndorsement) -> None:
    expected_share = Fraction(1, len(endorsement.candidate_ids))
    expected = {candidate_id: expected_share for candidate_id in endorsement.candidate_ids}
    if endorsement.allocation != expected:
        raise ValueError(
            f"endorsement {endorsement.id!r} violates configured exact_equal_split allocation"
        )


def _latest_input_timestamp(
    dataset: CanonicalDataset,
    effective: dict[str, BaseModel],
) -> datetime:
    effective_endorsements = [
        cast(NormalizedEndorsement, effective[item.id]) for item in dataset.endorsements
    ]
    timestamps = [
        dataset.source_registry.frozen_at,
        dataset.source_registry.research_cutoff,
        *(source.retrieved_at for source in dataset.inventory.sources),
        *(capture.retrieved_at for capture in dataset.captures),
        *(cast(ReviewItem, effective[item.id]).created_at for item in dataset.review_items),
        *(cast(ReviewDecision, effective[item.id]).created_at for item in dataset.review_decisions),
        *(item.created_at for item in dataset.overrides),
        *(item.reviewed_at for item in effective_endorsements if item.reviewed_at is not None),
    ]
    for timestamp in timestamps:
        if timestamp.tzinfo is None or timestamp.utcoffset() is None:
            raise ValueError("all scoring input timestamps must include a UTC offset")
    return max(timestamps)
