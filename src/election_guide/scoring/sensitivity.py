"""Deterministic exclusion analysis, separate from authoritative consensus."""

from __future__ import annotations

import hashlib
from fractions import Fraction

from election_guide.inventory.models import Race
from election_guide.normalization.models import CanonicalDataset
from election_guide.scoring.engine import (
    EXPLICIT_STATUSES,
    NO_ENDORSEMENT_STATUSES,
    ScoringContext,
    prepare_scoring,
    score_race,
)
from election_guide.scoring.models import ConsensusReport, RaceConsensus
from election_guide.scoring.sensitivity_models import (
    ChoiceSensitivity,
    Classification,
    IdDelta,
    MaterialReason,
    RaceSensitivity,
    ScenarioKind,
    SensitivityDelta,
    SensitivityPolicy,
    SensitivityReport,
    SensitivityScenario,
    SensitivitySnapshot,
    SkippedScenario,
)
from election_guide.serialization import canonical_json_bytes
from election_guide.sources.panel import build_panel_snapshot, source_registry_hash

COUNT_FIELDS = (
    "eligible_source_count",
    "source_coverage_count",
    "category_coverage_count",
    "explicit_endorsement_count",
    "no_endorsement_count",
    "missing_source_count",
    "pending_review_count",
)


def _hash(value: object) -> str:
    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def _policy(policy: SensitivityPolicy | None) -> SensitivityPolicy:
    approved = SensitivityPolicy()
    if policy is not None and policy != approved:
        raise ValueError("sensitivity policy must match the approved source-panel-sensitivity-v1")
    return approved


def build_sensitivity_report(
    dataset: CanonicalDataset,
    consensus: ConsensusReport,
    *,
    git_commit: str,
    policy: SensitivityPolicy | None = None,
) -> SensitivityReport:
    """Enumerate exclusions from the original reviewed inputs and canonical baseline."""
    approved = _policy(policy)
    ConsensusReport.model_validate(
        consensus.model_dump(mode="json"), context={"canonical_dataset": dataset}
    )
    context = prepare_scoring(
        dataset,
        consensus.scoring_configuration,
        computed_at=consensus.computed_at,
        allow_unresolved=consensus.publication_has_unresolved_high_severity,
    )
    panel = build_panel_snapshot(dataset.source_registry)
    return SensitivityReport(
        election_id=consensus.election_id,
        dataset_hash=consensus.dataset_hash,
        source_registry_hash=source_registry_hash(dataset.source_registry),
        source_panel_id=panel.panel_id,
        source_panel_hash=panel.panel_hash,
        publication_scope_hash=consensus.publication_scope_hash,
        scoring_configuration=consensus.scoring_configuration,
        consensus_hash=_hash(consensus.model_dump(mode="json")),
        policy=approved,
        policy_hash=_hash(approved.model_dump(mode="json")),
        computed_at=consensus.computed_at,
        git_commit=git_commit,
        publication_has_unresolved_high_severity=consensus.publication_has_unresolved_high_severity,
        races=[
            _race_sensitivity(context, race, baseline, approved)
            for race, baseline in zip(context.races, consensus.races, strict=True)
        ],
    )


def validate_sensitivity_report(
    report: SensitivityReport,
    dataset: CanonicalDataset,
    consensus: ConsensusReport,
    *,
    policy: SensitivityPolicy | None = None,
) -> SensitivityReport:
    """Recompute every field; self-consistent edits and skips cannot authorize results."""
    expected = build_sensitivity_report(
        dataset, consensus, git_commit=report.git_commit, policy=policy
    )
    if report != expected:
        raise ValueError("sensitivity report does not match canonical inputs and approved policy")
    return report


def _snapshot(
    context: ScoringContext, race: Race, score: RaceConsensus, excluded: frozenset[str]
) -> SensitivitySnapshot:
    eligible = [s for s in context.eligible_sources_by_race[race.id] if s.id not in excluded]
    records = {e.source_id: e for e in context.endorsements_by_race.get(race.id, [])}
    affirmative = sorted(
        s.id for s in eligible if s.id in records and records[s.id].status in EXPLICIT_STATUSES
    )
    no_endorsement = sorted(
        s.id
        for s in eligible
        if s.id in records and records[s.id].status in NO_ENDORSEMENT_STATUSES
    )
    resolved = set(affirmative + no_endorsement)
    state = (
        "tied"
        if score.grade == "TIED"
        else "insufficient"
        if score.grade == "Insufficient"
        else "recommended"
    )
    points = sorted(score.candidate_support.values(), reverse=True)
    margin = (
        None
        if not points
        else (points[0] - (points[1] if len(points) > 1 else 0)) / score.explicit_endorsement_count
    )
    return SensitivitySnapshot(
        score=score,
        recommendation_state=state,
        recommendation_candidate_ids=[] if state == "insufficient" else score.winner_candidate_ids,
        populations={
            "eligible_source_ids": sorted(s.id for s in eligible),
            "resolved_source_ids": sorted(resolved),
            "affirmative_source_ids": affirmative,
            "no_endorsement_source_ids": no_endorsement,
            "missing_source_ids": sorted(s.id for s in eligible if s.id not in resolved),
            "represented_category_ids": sorted(
                {s.reporting_category_id for s in eligible if s.id in resolved}
            ),
            "pending_review_item_ids": sorted(
                i.id for i in context.unresolved if race.id in context.relevant_review_races[i.id]
            ),
        },
        choices=[
            ChoiceSensitivity(
                candidate_id=c.id,
                support_points=score.candidate_support.get(c.id, Fraction()),
                share=score.candidate_support.get(c.id, Fraction())
                / score.explicit_endorsement_count
                if points
                else None,
            )
            for c in sorted(race.choices, key=lambda c: c.ballot_order)
        ],
        leading_margin=None if margin is None else str(margin),
    )


def _subtract(after: Fraction | None, before: Fraction | None) -> Fraction | None:
    return None if after is None or before is None else after - before


def _delta(before: SensitivitySnapshot, after: SensitivitySnapshot) -> SensitivityDelta:
    a, b = after.score, before.score
    reasons: list[MaterialReason] = []
    if a.winner_candidate_ids != b.winner_candidate_ids:
        reasons.append("leaders_changed")
    if after.recommendation_state != before.recommendation_state:
        reasons.append("recommendation_state_changed")
    if after.recommendation_candidate_ids != before.recommendation_candidate_ids:
        reasons.append("recommendation_choices_changed")
    if a.winner_share is not None and b.winner_share is not None:
        if (a.winner_share > Fraction(1, 2)) != (b.winner_share > Fraction(1, 2)):
            reasons.append("majority_boundary_crossed")
        if abs(a.winner_share - b.winner_share) >= Fraction(1, 10):
            reasons.append("leading_share_changed_materially")
    before_fields = before.model_dump(mode="json")
    after_fields = after.model_dump(mode="json")
    changed = [k for k in before_fields if k != "score" and before_fields[k] != after_fields[k]]
    changed.extend(
        f"score.{k}"
        for k in before_fields["score"]
        if before_fields["score"][k] != after_fields["score"][k]
    )
    before_ids = {
        **before.populations,
        "leader_candidate_ids": b.winner_candidate_ids,
        "recommendation_candidate_ids": before.recommendation_candidate_ids,
        "low_confidence_source_ids": b.low_confidence_source_ids,
        "overlap_source_ids": b.overlap_source_ids,
        "unresolved_high_severity_review_item_ids": b.unresolved_high_severity_review_item_ids,
    }
    after_ids = {
        **after.populations,
        "leader_candidate_ids": a.winner_candidate_ids,
        "recommendation_candidate_ids": after.recommendation_candidate_ids,
        "low_confidence_source_ids": a.low_confidence_source_ids,
        "overlap_source_ids": a.overlap_source_ids,
        "unresolved_high_severity_review_item_ids": a.unresolved_high_severity_review_item_ids,
    }
    return SensitivityDelta(
        changed_fields=sorted(changed),
        counts={k: getattr(a, k) - getattr(b, k) for k in COUNT_FIELDS},
        leading_support_points=_subtract(a.winner_support_points, b.winner_support_points),
        leading_share=_subtract(a.winner_share, b.winner_share),
        leading_margin=_subtract(
            None if after.leading_margin is None else Fraction(after.leading_margin),
            None if before.leading_margin is None else Fraction(before.leading_margin),
        ),
        choices=[
            ChoiceSensitivity(
                candidate_id=x.candidate_id,
                support_points=x.support_points - y.support_points,
                share=_subtract(x.share, y.share),
            )
            for y, x in zip(before.choices, after.choices, strict=True)
        ],
        identifiers={
            k: IdDelta(
                added=[identifier for identifier in after_ids[k] if identifier not in v],
                removed=[identifier for identifier in v if identifier not in after_ids[k]],
            )
            for k, v in sorted(before_ids.items())
        },
        grade_changed=a.grade != b.grade,
        material_reasons=sorted(reasons),
    )


def _race_sensitivity(
    context: ScoringContext, race: Race, score: RaceConsensus, policy: SensitivityPolicy
) -> RaceSensitivity:
    baseline = _snapshot(context, race, score, frozenset())
    eligible = context.eligible_sources_by_race[race.id]
    contributors = set(baseline.populations["affirmative_source_ids"])
    categories = {s.reporting_category_id for s in eligible if s.id in contributors}
    registry = context.dataset.source_registry
    category_labels = {c.id: c.label for c in registry.categories}
    scenarios: list[SensitivityScenario] = []
    skipped: list[SkippedScenario] = []

    def add(kind: ScenarioKind, target: str, label: str, members: list[str]) -> None:
        after = _snapshot(
            context,
            race,
            score_race(context, race, excluded_source_ids=frozenset(members)),
            frozenset(members),
        )
        scenarios.append(
            SensitivityScenario(
                id=f"{kind}:{target}",
                kind=kind,
                target_id=target,
                target_label=label,
                excluded_source_ids=members,
                after=after,
                delta=_delta(baseline, after),
            )
        )

    for source in eligible:
        if source.id in contributors:
            add("source", source.id, source.name, [source.id])
    for category in sorted({s.reporting_category_id for s in eligible}):
        members = sorted(s.id for s in eligible if s.reporting_category_id == category)
        reason = (
            "no_contributing_members"
            if category not in categories
            else "fewer_than_two_contributing_categories"
            if len(categories) < 2
            else None
        )
        if reason is None:
            add("category", category, category_labels[category], members)
        else:
            skipped.append(
                SkippedScenario(
                    id=f"category:{category}",
                    kind="category",
                    target_id=category,
                    target_label=category_labels[category],
                    eligible_source_ids=members,
                    reason=reason,
                )
            )
    for group in sorted(registry.overlap_groups, key=lambda g: g.id):
        members = sorted(s.id for s in eligible if s.id in group.member_ids)
        reason = (
            "fewer_than_two_eligible_members"
            if len(members) < 2
            else "no_contributing_members"
            if not contributors.intersection(members)
            else None
        )
        if reason is None:
            add("overlap", group.id, group.label, members)
        else:
            skipped.append(
                SkippedScenario(
                    id=f"overlap:{group.id}",
                    kind="overlap",
                    target_id=group.id,
                    target_label=group.label,
                    eligible_source_ids=members,
                    reason=reason,
                )
            )
    material = [s for s in scenarios if s.delta.material_reasons]
    kinds: list[ScenarioKind] = [
        k for k in policy.scenario_order if any(s.kind == k for s in material)
    ]
    classification: Classification
    if kinds:
        classification = {
            "source": "source_sensitive",
            "category": "category_sensitive",
            "overlap": "overlap_sensitive",
        }[kinds[0]]  # type: ignore[assignment]
    elif baseline.recommendation_state == "tied":
        classification = "tied"
    elif baseline.recommendation_state == "insufficient":
        classification = "insufficient"
    elif baseline.leading_margin is not None and Fraction(baseline.leading_margin) <= Fraction(
        policy.narrow_margin
    ):
        classification = "narrow_but_stable"
    else:
        classification = "stable"
    illustration = next(
        (
            s
            for reason in policy.illustration_priority
            for s in material
            if reason in s.delta.material_reasons
        ),
        None,
    )
    warning = None if illustration is None else _warning(baseline, illustration)
    summary = warning or {
        "stable": "Same leading choice in all tested exclusions.",
        "narrow_but_stable": "Close lead; same choice in all tested exclusions.",
        "tied": "Tied across tested exclusions.",
        "insufficient": "Too few endorsements.",
    }.get(classification, "")
    return RaceSensitivity(
        race_id=race.id,
        baseline=baseline,
        scenarios=scenarios,
        skipped_scenarios=skipped,
        classification=classification,
        material_scenario_ids=[s.id for s in material],
        affected_scenario_kinds=kinds,
        illustrative_scenario_id=None if illustration is None else illustration.id,
        summary=summary,
        warning=warning,
    )


def _warning(baseline: SensitivitySnapshot, scenario: SensitivityScenario) -> str:
    after = scenario.after
    target = scenario.target_label + (" sources" if scenario.kind == "category" else "")
    reasons = scenario.delta.material_reasons
    if "recommendation_state_changed" in reasons:
        text = {
            "tied": "Tied",
            "insufficient": "Too few endorsements",
            "recommended": "A single choice is recommended",
        }[after.recommendation_state]
    elif "recommendation_choices_changed" in reasons or "leaders_changed" in reasons:
        text = (
            "Leading choice changes"
            if after.score.winner_candidate_ids
            else "No measured leading choice"
        )
    elif "majority_boundary_crossed" in reasons:
        text = (
            "No majority"
            if after.score.winner_share is not None and after.score.winner_share <= Fraction(1, 2)
            else "Majority agreement"
        )
    else:
        change = abs(after.score.winner_share - baseline.score.winner_share) * 100  # type: ignore[operator]
        text = f"Agreement changes by {float(change):.1f} percentage points"
    return f"{text} without {target}."
