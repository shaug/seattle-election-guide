from __future__ import annotations

import hashlib
from fractions import Fraction
from pathlib import Path

import pytest

from election_guide.normalization.models import CanonicalDataset
from election_guide.scoring import score_dataset
from election_guide.scoring.sensitivity import build_sensitivity_report, validate_sensitivity_report
from election_guide.scoring.sensitivity_models import SensitivityPolicy, SensitivityReport
from election_guide.serialization import canonical_json_bytes
from tests.sensitivity_fixtures import synthetic_dataset
from tests.test_scoring import (
    COMPARISON_SOURCE_ID,
    CONSENSUS_SOURCE_IDS,
    NOW,
    RACE_ID,
    _candidate_ids,  # pyright: ignore[reportPrivateUsage]
    _configuration,  # pyright: ignore[reportPrivateUsage]
    _dataset,  # pyright: ignore[reportPrivateUsage]
)


@pytest.mark.parametrize(
    ("categories", "grouped", "classification", "share", "scenario_count"),
    [
        ([(15, 5)] * 4, 0, "stable", Fraction(3, 4), 84),
        ([(11, 9)] * 4, 0, "narrow_but_stable", Fraction(11, 20), 84),
        ([(2, 1)], 0, "source_sensitive", Fraction(2, 3), 3),
        ([(8, 2), (4, 6)], 0, "category_sensitive", Fraction(3, 5), 22),
        ([(3, 2)] * 4, 2, "overlap_sensitive", Fraction(3, 5), 25),
    ],
)
def test_preregistered_examples_retain_exact_results(
    tmp_path: Path,
    categories: list[tuple[int, int]],
    grouped: int,
    classification: str,
    share: Fraction,
    scenario_count: int,
) -> None:
    dataset = synthetic_dataset(tmp_path, categories, grouped_a_per_category=grouped)
    baseline = score_dataset(dataset, _configuration(), computed_at=NOW)
    baseline_bytes = canonical_json_bytes(baseline.model_dump(mode="json"))

    report = build_sensitivity_report(dataset, baseline, git_commit="fixture")
    race = report.races[0]

    assert race.classification == classification
    assert race.baseline.score.winner_share == share
    assert len(race.scenarios) == scenario_count
    assert report.consensus_hash == hashlib.sha256(baseline_bytes).hexdigest()
    assert canonical_json_bytes(baseline.model_dump(mode="json")) == baseline_bytes
    if classification in {"stable", "narrow_but_stable"}:
        assert race.material_scenario_ids == []
    else:
        assert race.material_scenario_ids
    if classification == "narrow_but_stable":
        assert race.baseline.leading_margin == "1/10"
    assert validate_sensitivity_report(report, dataset, baseline) == report


def test_empty_suite_retains_insufficient_evidence_and_null_shares(tmp_path: Path) -> None:
    dataset = synthetic_dataset(tmp_path, [], missing_sources=1)
    baseline = score_dataset(dataset, _configuration(), computed_at=NOW)

    race = build_sensitivity_report(dataset, baseline, git_commit="fixture").races[0]

    assert race.classification == "insufficient"
    assert race.scenarios == []
    assert race.baseline.score.winner_share is None
    assert race.baseline.recommendation_candidate_ids == []
    assert all(choice.share is None for choice in race.baseline.choices)


def test_category_excludes_resolved_and_missing_members_without_relabeling(tmp_path: Path) -> None:
    dataset = synthetic_dataset(tmp_path, [(2, 0), (0, 2)], no_endorsements=2, missing_sources=1)
    consensus = score_dataset(dataset, _configuration(), computed_at=NOW)
    race = build_sensitivity_report(dataset, consensus, git_commit="fixture").races[0]
    scenario = next(s for s in race.scenarios if s.id == "category:synthetic_0")
    assert len(scenario.excluded_source_ids) == 5
    assert scenario.after.score.eligible_source_count == 2
    assert scenario.after.score.explicit_endorsement_count == 2
    assert scenario.after.score.no_endorsement_count == 0
    assert scenario.after.score.missing_source_count == 0
    assert scenario.delta.counts["source_coverage_count"] == -4
    assert scenario.delta.counts["missing_source_count"] == -1
    assert scenario.after.choices[0].support_points == 0
    assert scenario.after.choices[0].share == 0
    assert len([s for s in race.scenarios if s.kind == "source"]) == 4


def test_single_split_tie_precedes_insufficient_and_zero_support_is_not_tied(
    tmp_path: Path,
) -> None:
    choices = _candidate_ids()
    dataset = _dataset(tmp_path, [(CONSENSUS_SOURCE_IDS[0], "dual_endorsement", choices[:2])])
    consensus = score_dataset(dataset, _configuration(), computed_at=NOW)
    race = next(
        r
        for r in build_sensitivity_report(dataset, consensus, git_commit="fixture").races
        if r.race_id == RACE_ID
    )
    assert race.baseline.recommendation_state == "tied"
    assert race.baseline.recommendation_candidate_ids == choices[:2]
    assert race.baseline.leading_margin == "0"
    scenario = race.scenarios[0]
    assert scenario.after.recommendation_state == "insufficient"
    assert scenario.after.score.winner_candidate_ids == []
    assert scenario.after.score.winner_share is None
    assert scenario.delta.leading_share is None
    assert scenario.delta.choices[0].support_points == Fraction(-1, 2)
    assert scenario.delta.choices[0].share is None
    assert (
        scenario.after.populations["missing_source_ids"]
        == race.baseline.populations["missing_source_ids"]
    )


def test_insufficient_measured_leader_has_no_recommendation(tmp_path: Path) -> None:
    dataset = synthetic_dataset(tmp_path, [(1, 0)])
    consensus = score_dataset(dataset, _configuration(), computed_at=NOW)
    race = build_sensitivity_report(dataset, consensus, git_commit="fixture").races[0]
    assert race.baseline.score.winner_candidate_id == _candidate_ids()[0]
    assert race.baseline.recommendation_candidate_ids == []
    assert race.baseline.leading_margin == "1"
    assert race.scenarios[0].after.leading_margin is None


@pytest.mark.parametrize(("a", "expected"), [(9, True), (10, False)])
def test_share_change_threshold_is_inclusive_and_grade_only_is_audit(
    tmp_path: Path, a: int, expected: bool
) -> None:
    dataset = synthetic_dataset(tmp_path, [(a, 1)])
    consensus = score_dataset(dataset, _configuration(), computed_at=NOW)
    race = build_sensitivity_report(dataset, consensus, git_commit="fixture").races[0]
    remove_b = race.scenarios[-1]
    assert ("leading_share_changed_materially" in remove_b.delta.material_reasons) == expected
    assert remove_b.delta.leading_share == Fraction(1, a + 1)
    if a == 9:
        remove_a = race.scenarios[0]
        assert remove_a.delta.grade_changed
        assert remove_a.delta.material_reasons == []


def test_direct_groups_keep_duplicate_sets_and_do_not_expand_transitively(tmp_path: Path) -> None:
    dataset = synthetic_dataset(tmp_path, [(3, 0)], missing_sources=1)
    payload = dataset.model_dump(mode="json")
    groups = [
        ("first", [0, 1]),
        ("duplicate", [0, 1]),
        ("second", [1, 2]),
        ("all", [0, 1, 2]),
        ("small", [3]),
    ]
    payload["source_registry"]["overlap_groups"] = [
        {
            "id": name,
            "label": name,
            "description": "Disclosed fixture relationship.",
            "member_ids": [f"synthetic-source-{i:03d}" for i in members]
            + ([COMPARISON_SOURCE_ID] if name == "small" else []),
        }
        for name, members in groups
    ]
    for source in payload["source_registry"]["sources"]:
        source["overlap_group_ids"] = [
            g["id"]
            for g in payload["source_registry"]["overlap_groups"]
            if source["id"] in g["member_ids"]
        ]
    dataset = CanonicalDataset.model_validate(payload)
    consensus = score_dataset(dataset, _configuration(), computed_at=NOW)
    race = build_sensitivity_report(dataset, consensus, git_commit="fixture").races[0]
    scenarios = {s.id: s for s in race.scenarios}
    assert (
        scenarios["overlap:first"].excluded_source_ids
        == scenarios["overlap:duplicate"].excluded_source_ids
    )
    assert scenarios["overlap:first"].after.score.explicit_endorsement_count == 1
    assert scenarios["overlap:all"].after.score.explicit_endorsement_count == 0
    assert scenarios["overlap:all"].after.score.winner_share is None
    assert [(s.id, s.reason) for s in race.skipped_scenarios] == [
        ("category:synthetic_0", "fewer_than_two_contributing_categories"),
        ("overlap:small", "fewer_than_two_eligible_members"),
    ]


@pytest.mark.parametrize(
    "tamper", ["scenario", "skip", "race", "delta", "classification", "policy", "members"]
)
def test_recomputation_rejects_coherent_tampering(tmp_path: Path, tamper: str) -> None:
    dataset = synthetic_dataset(tmp_path, [(2, 1)])
    consensus = score_dataset(dataset, _configuration(), computed_at=NOW)
    report = build_sensitivity_report(dataset, consensus, git_commit="fixture")
    payload = report.model_dump(mode="json")
    race = payload["races"][0]
    if tamper == "scenario":
        race["scenarios"].pop()
    elif tamper == "skip":
        race["skipped_scenarios"] = []
    elif tamper == "race":
        payload["races"] = []
    elif tamper == "delta":
        race["scenarios"][0]["delta"]["leading_share"] = "0"
    elif tamper == "classification":
        race["classification"] = "stable"
        race["material_scenario_ids"] = []
        race["warning"] = None
        race["summary"] = "Same leading choice in all tested exclusions."
    elif tamper == "members":
        race["scenarios"][0]["excluded_source_ids"] = [COMPARISON_SOURCE_ID]
    else:
        payload["policy"]["classification_priority"] = list(
            reversed(payload["policy"]["classification_priority"])
        )
        payload["policy_hash"] = hashlib.sha256(canonical_json_bytes(payload["policy"])).hexdigest()
    with pytest.raises(ValueError, match="canonical inputs and approved policy"):
        validate_sensitivity_report(SensitivityReport.model_validate(payload), dataset, consensus)


def test_approved_policy_and_repeatable_bytes_are_independent_of_embedded_hash(
    tmp_path: Path,
) -> None:
    dataset = synthetic_dataset(tmp_path, [(2, 1)])
    consensus = score_dataset(dataset, _configuration(), computed_at=NOW)
    first = build_sensitivity_report(dataset, consensus, git_commit="fixture")
    assert canonical_json_bytes(first.model_dump(mode="json")) == canonical_json_bytes(
        build_sensitivity_report(dataset, consensus, git_commit="fixture").model_dump(mode="json")
    )
    changed = SensitivityPolicy().model_copy(update={"skip_rules": ()})
    with pytest.raises(ValueError, match="approved"):
        build_sensitivity_report(dataset, consensus, git_commit="fixture", policy=changed)


def test_exceptional_review_state_survives_excluding_the_flagged_source(tmp_path: Path) -> None:
    dataset = _dataset(
        tmp_path,
        [(CONSENSUS_SOURCE_IDS[0], "endorsed", _candidate_ids()[:1])],
        unresolved_severity="high",
    )
    consensus = score_dataset(dataset, _configuration(), computed_at=NOW, allow_unresolved=True)
    report = build_sensitivity_report(dataset, consensus, git_commit="fixture")
    race = next(r for r in report.races if r.race_id == RACE_ID)
    assert report.publication_has_unresolved_high_severity
    assert (
        race.scenarios[0].after.score.unresolved_high_severity_review_item_ids
        == race.baseline.score.unresolved_high_severity_review_item_ids
    )
    assert "unresolved_high_severity" in [w.code for w in race.scenarios[0].after.score.warnings]


def test_district_eligibility_and_comparison_role_cannot_expand_in_scenarios(
    tmp_path: Path,
) -> None:
    source = CONSENSUS_SOURCE_IDS[0]
    dataset = _dataset(
        tmp_path,
        [
            (source, "endorsed", _candidate_ids()[:1]),
            (COMPARISON_SOURCE_ID, "endorsed", _candidate_ids()[1:2]),
        ],
        overlap_group_source_ids=(source, CONSENSUS_SOURCE_IDS[1]),
    )
    payload = dataset.model_dump(mode="json")
    item = next(s for s in payload["source_registry"]["sources"] if s["id"] == source)
    item["geographic_kind"] = "legislative_district"
    item["eligibility"] = {
        "kind": "seattle_ballot_races_except_other_legislative_districts",
        "jurisdiction_ids": ["legislative-district-32"],
        "rationale": "Fixture district scope.",
    }
    dataset = CanonicalDataset.model_validate(payload)
    consensus = score_dataset(dataset, _configuration(), computed_at=NOW)
    report = build_sensitivity_report(dataset, consensus, git_commit="fixture")
    assessor = next(r for r in report.races if r.race_id == RACE_ID)
    assert source in assessor.baseline.populations["eligible_source_ids"]
    other = next(r for r in report.races if r.race_id == "ld-43-state-representative-1")
    assert source not in other.baseline.populations["eligible_source_ids"]
    assert (
        next(s for s in other.skipped_scenarios if s.kind == "overlap").reason
        == "fewer_than_two_eligible_members"
    )
    assert all(
        COMPARISON_SOURCE_ID not in s.excluded_source_ids for r in report.races for s in r.scenarios
    )
