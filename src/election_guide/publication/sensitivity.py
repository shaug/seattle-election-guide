"""Compact voter wording and lossless CSV projection of the exclusion audit."""

from __future__ import annotations

import csv
import io
from fractions import Fraction

from pydantic import BaseModel, ConfigDict, Field

from election_guide.normalization.models import CanonicalDataset
from election_guide.scoring.sensitivity import COUNT_FIELDS
from election_guide.scoring.sensitivity_models import (
    Classification,
    ScenarioKind,
    SensitivityPolicy,
    SensitivityReport,
    SensitivitySnapshot,
)
from election_guide.serialization import canonical_json_bytes


class DisplayModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class SensitivityScenarioDisplay(DisplayModel):
    id: str
    kind: ScenarioKind
    target_label: str
    target_code: str | None
    result_label: str
    leading_share: str
    explicit_source_count: int = Field(ge=0, strict=True)
    material: bool = Field(strict=True)
    changes: list[str]


class SensitivitySkipDisplay(DisplayModel):
    id: str
    target_label: str
    reason: str


class SensitivityDisplay(DisplayModel):
    policy_id: str
    classification: Classification
    summary: str
    warning: str | None
    baseline_result: str
    baseline_share: str
    baseline_source_count: int = Field(ge=0, strict=True)
    tested_count: int = Field(ge=0, strict=True)
    material_count: int = Field(ge=0, strict=True)
    affected_kinds: list[ScenarioKind]
    scenarios: list[SensitivityScenarioDisplay]
    skipped: list[SensitivitySkipDisplay]


def _result_label(snapshot: SensitivitySnapshot, choices: dict[str, str]) -> str:
    labels = " / ".join(choices[c] for c in snapshot.score.winner_candidate_ids)
    if snapshot.recommendation_state == "insufficient":
        return (
            f"Too few endorsements; measured leader: {labels}"
            if labels
            else "Too few endorsements; no measured leader"
        )
    return f"Tied: {labels}" if snapshot.recommendation_state == "tied" else labels


def sensitivity_display(
    dataset: CanonicalDataset, report: SensitivityReport
) -> dict[str, SensitivityDisplay]:
    races = {r.id: r for r in dataset.inventory.races}
    source_codes = {s.id: s.code for s in dataset.source_registry.sources}
    category_codes = {c.id: c.code for c in dataset.source_registry.categories}
    skip_reasons = {
        "fewer_than_two_contributing_categories": "Only one category contributes endorsements.",
        "fewer_than_two_eligible_members": "Fewer than two eligible sources in this group.",
        "no_contributing_members": "No contributing endorsements to exclude.",
    }
    reason_labels = {
        "leaders_changed": "Measured leading choices change.",
        "recommendation_state_changed": "Recommendation state changes.",
        "recommendation_choices_changed": "Recommended choices change.",
        "majority_boundary_crossed": "Crosses the majority boundary.",
        "leading_share_changed_materially": "Agreement changes by at least 10 percentage points.",
    }
    return {
        race.race_id: SensitivityDisplay(
            policy_id=report.policy.id,
            classification=race.classification,
            summary=race.summary,
            warning=race.warning,
            baseline_result=_result_label(
                race.baseline, {c.id: c.display_name for c in races[race.race_id].choices}
            ),
            baseline_share="Unavailable"
            if race.baseline.score.winner_share is None
            else f"{float(race.baseline.score.winner_share * 100):.1f}%",
            baseline_source_count=race.baseline.score.explicit_endorsement_count,
            tested_count=len(race.scenarios),
            material_count=len(race.material_scenario_ids),
            affected_kinds=race.affected_scenario_kinds,
            scenarios=[
                SensitivityScenarioDisplay(
                    id=s.id,
                    kind=s.kind,
                    target_label=s.target_label,
                    target_code=source_codes[s.target_id]
                    if s.kind == "source"
                    else category_codes[s.target_id]
                    if s.kind == "category"
                    else None,
                    result_label=_result_label(
                        s.after, {c.id: c.display_name for c in races[race.race_id].choices}
                    ),
                    leading_share="Unavailable"
                    if s.after.score.winner_share is None
                    else f"{float(s.after.score.winner_share * 100):.1f}%",
                    explicit_source_count=s.after.score.explicit_endorsement_count,
                    material=bool(s.delta.material_reasons),
                    changes=[reason_labels[reason] for reason in s.delta.material_reasons],
                )
                for s in race.scenarios
            ],
            skipped=[
                SensitivitySkipDisplay(
                    id=s.id, target_label=s.target_label, reason=skip_reasons[s.reason]
                )
                for s in race.skipped_scenarios
            ],
        )
        for race in report.races
    }


SCENARIO_CSV_FIELDS = (
    "race_id",
    "policy_id",
    "scenario_id",
    "kind",
    "target_id",
    "excluded_source_ids",
    "before_leading_support",
    "after_leading_support",
    "leading_support_delta",
    "before_leading_share",
    "after_leading_share",
    "leading_share_delta",
    *(f"{prefix}_{field}" for field in COUNT_FIELDS for prefix in ("before", "after", "delta")),
    "baseline",
    "after",
    "delta",
)


def _scalar(value: Fraction | None) -> str:
    return "" if value is None else str(value)


def sensitivity_scenarios_csv(report: SensitivityReport) -> bytes:
    """Fixed scalar columns plus complete canonical snapshots and deltas per scenario."""
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=SCENARIO_CSV_FIELDS, lineterminator="\n")
    writer.writeheader()
    for race in report.races:
        for scenario in race.scenarios:
            before, after, delta = race.baseline, scenario.after, scenario.delta
            row = {
                "race_id": race.race_id,
                "policy_id": report.policy.id,
                "scenario_id": scenario.id,
                "kind": scenario.kind,
                "target_id": scenario.target_id,
                "excluded_source_ids": canonical_json_bytes(scenario.excluded_source_ids)
                .decode()
                .strip(),
                "before_leading_support": _scalar(before.score.winner_support_points),
                "after_leading_support": _scalar(after.score.winner_support_points),
                "leading_support_delta": _scalar(delta.leading_support_points),
                "before_leading_share": _scalar(before.score.winner_share),
                "after_leading_share": _scalar(after.score.winner_share),
                "leading_share_delta": _scalar(delta.leading_share),
                "baseline": canonical_json_bytes(before.model_dump(mode="json")).decode().strip(),
                "after": canonical_json_bytes(after.model_dump(mode="json")).decode().strip(),
                "delta": canonical_json_bytes(delta.model_dump(mode="json")).decode().strip(),
            }
            for field in COUNT_FIELDS:
                row[f"before_{field}"] = str(getattr(before.score, field))
                row[f"after_{field}"] = str(getattr(after.score, field))
                row[f"delta_{field}"] = str(delta.counts[field])
            writer.writerow(row)
    return stream.getvalue().encode("utf-8")


__all__ = [
    "SensitivityDisplay",
    "SensitivityPolicy",
    "SensitivityScenarioDisplay",
    "sensitivity_display",
    "sensitivity_scenarios_csv",
]
