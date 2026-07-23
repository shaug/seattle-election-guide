"""Deterministic before/after reports for consensus scoring changes."""

from __future__ import annotations

from typing import Any

from pydantic import AwareDatetime, BaseModel, ConfigDict

from election_guide.scoring.models import ConsensusReport, RaceConsensus


class ImpactModel(BaseModel):
    """Reject undeclared report fields so checked artifacts cannot drift silently."""

    model_config = ConfigDict(extra="forbid")


class WarningSnapshot(ImpactModel):
    code: str
    message: str
    source_ids: list[str]
    review_item_ids: list[str]


class RaceImpactSnapshot(ImpactModel):
    race_id: str
    winner_candidate_ids: list[str]
    winner_share: str | None
    winner_support_points: str | None
    grade: str
    is_tied: bool
    explicit_endorsement_count: int
    source_coverage_count: int
    eligible_source_count: int
    missing_source_count: int
    category_coverage_count: int
    warnings: list[WarningSnapshot]


class ConsensusImpactSnapshot(ImpactModel):
    election_id: str
    configuration_id: str
    computed_at: AwareDatetime
    dataset_hash: str
    publication_scope_hash: str
    input_hash: str
    races: list[RaceImpactSnapshot]


class RaceImpactChange(ImpactModel):
    race_id: str
    changed_fields: list[str]


class ConsensusImpactReport(ImpactModel):
    schema_version: str = "1.0"
    before: ConsensusImpactSnapshot
    after: ConsensusImpactSnapshot
    changes: list[RaceImpactChange]


def summarize_consensus(report: ConsensusReport) -> ConsensusImpactSnapshot:
    """Reduce a full report to the fields required by the source-panel impact audit."""
    return ConsensusImpactSnapshot(
        election_id=report.election_id,
        configuration_id=report.configuration_id,
        computed_at=report.computed_at,
        dataset_hash=report.dataset_hash,
        publication_scope_hash=report.publication_scope_hash,
        input_hash=report.input_hash,
        races=[_race_snapshot(race) for race in report.races],
    )


def summarize_consensus_payload(payload: Any) -> ConsensusImpactSnapshot:
    """Validate the impact fields from a serialized consensus report."""
    try:
        races = [
            {
                "race_id": race["race_id"],
                "winner_candidate_ids": race["winner_candidate_ids"],
                "winner_share": race["winner_share"],
                "winner_support_points": race["winner_support_points"],
                "grade": race["grade"],
                "is_tied": race["is_tied"],
                "explicit_endorsement_count": race["explicit_endorsement_count"],
                "source_coverage_count": race["source_coverage_count"],
                "eligible_source_count": race["eligible_source_count"],
                "missing_source_count": race["missing_source_count"],
                "category_coverage_count": race["category_coverage_count"],
                "warnings": race["warnings"],
            }
            for race in payload["races"]
        ]
        return ConsensusImpactSnapshot.model_validate(
            {
                "election_id": payload["election_id"],
                "configuration_id": payload["configuration_id"],
                "computed_at": payload["computed_at"],
                "dataset_hash": payload["dataset_hash"],
                "publication_scope_hash": payload["publication_scope_hash"],
                "input_hash": payload["input_hash"],
                "races": races,
            }
        )
    except (KeyError, TypeError) as error:
        raise ValueError(f"invalid serialized consensus report: {error}") from error


def compare_consensus(
    before: ConsensusReport,
    after: ConsensusReport,
) -> ConsensusImpactReport:
    """Build an exact deterministic comparison from two validated scoring reports."""
    return compare_consensus_snapshots(
        summarize_consensus(before),
        summarize_consensus(after),
    )


def compare_consensus_snapshots(
    before: ConsensusImpactSnapshot,
    after: ConsensusImpactSnapshot,
) -> ConsensusImpactReport:
    """Compare compact snapshots, supporting validation of a checked report."""
    if before.election_id != after.election_id:
        raise ValueError("impact snapshots target different elections")
    if before.configuration_id != after.configuration_id:
        raise ValueError("impact snapshots use different scoring configurations")

    before_by_id = {race.race_id: race for race in before.races}
    after_by_id = {race.race_id: race for race in after.races}
    if len(before_by_id) != len(before.races) or len(after_by_id) != len(after.races):
        raise ValueError("impact snapshot repeats a race")
    if before_by_id.keys() != after_by_id.keys():
        raise ValueError("impact snapshots contain different race sets")

    changes: list[RaceImpactChange] = []
    for before_race in before.races:
        after_race = after_by_id[before_race.race_id]
        before_values = before_race.model_dump(mode="json")
        after_values = after_race.model_dump(mode="json")
        changed_fields = sorted(
            field
            for field in before_values
            if field != "race_id" and before_values[field] != after_values[field]
        )
        if changed_fields:
            changes.append(
                RaceImpactChange(
                    race_id=before_race.race_id,
                    changed_fields=changed_fields,
                )
            )

    return ConsensusImpactReport(before=before, after=after, changes=changes)


def _race_snapshot(race: RaceConsensus) -> RaceImpactSnapshot:
    return RaceImpactSnapshot(
        race_id=race.race_id,
        winner_candidate_ids=race.winner_candidate_ids,
        winner_share=None if race.winner_share is None else str(race.winner_share),
        winner_support_points=(
            None if race.winner_support_points is None else str(race.winner_support_points)
        ),
        grade=race.grade,
        is_tied=race.is_tied,
        explicit_endorsement_count=race.explicit_endorsement_count,
        source_coverage_count=race.source_coverage_count,
        eligible_source_count=race.eligible_source_count,
        missing_source_count=race.missing_source_count,
        category_coverage_count=race.category_coverage_count,
        warnings=[
            WarningSnapshot(
                code=warning.code,
                message=warning.message,
                source_ids=warning.source_ids,
                review_item_ids=warning.review_item_ids,
            )
            for warning in race.warnings
        ],
    )
