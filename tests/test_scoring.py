from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from fractions import Fraction
from pathlib import Path
from typing import Literal

import pytest
from pydantic import ValidationError
from typer.testing import CliRunner

from election_guide.cli import app
from election_guide.evidence.models import CaptureManifest, CaptureRequest
from election_guide.evidence.storage import read_capture_manifest, record_capture
from election_guide.inventory.importer import read_inventory
from election_guide.normalization.models import (
    CanonicalDataset,
    ExtractedClaim,
    MatchCandidate,
    MatchResult,
    NormalizedEndorsement,
    ReviewDecision,
    ReviewItem,
)
from election_guide.normalization.records import (
    new_extracted_claim,
    new_normalized_endorsement,
    new_override,
    new_review_decision,
    new_review_item,
)
from election_guide.normalization.semantics import EndorsementStatus
from election_guide.scoring import (
    PublicationBlockedError,
    read_scoring_configuration,
    score_dataset,
)
from election_guide.scoring.models import (
    ConsensusReport,
    Grade,
    RaceConsensus,
    ScoringConfiguration,
)
from election_guide.serialization import canonical_json_bytes, read_json
from election_guide.sources.models import SourceRegistry
from election_guide.sources.registry import read_source_registry

PROJECT_ROOT = Path(__file__).parent.parent
NOW = datetime(2026, 7, 20, 1, tzinfo=UTC)
RACE_ID = "king-county-assessor"
CONSENSUS_SOURCE_IDS = [
    "the-stranger",
    "the-urbanist",
    "washington-working-families-party",
    "washington-bus",
    "sage-leaders",
]
COMPARISON_SOURCE_ID = "seattle-times-editorial-board"
EndorsementSpec = tuple[str, EndorsementStatus, list[str]]
ScoreCase = tuple[str, list[EndorsementSpec], Grade, Fraction | None, bool]


def test_singular_dual_multiple_missing_tied_and_insufficient_results(tmp_path: Path) -> None:
    candidate_ids = _candidate_ids()
    cases: list[ScoreCase] = [
        (
            "singular",
            [
                (CONSENSUS_SOURCE_IDS[0], "endorsed", candidate_ids[:1]),
                (CONSENSUS_SOURCE_IDS[1], "endorsed", candidate_ids[:1]),
            ],
            "A",
            Fraction(1),
            False,
        ),
        (
            "dual",
            [
                (CONSENSUS_SOURCE_IDS[0], "dual_endorsement", candidate_ids[:2]),
                (CONSENSUS_SOURCE_IDS[1], "endorsed", candidate_ids[:1]),
            ],
            "A",
            Fraction(3, 4),
            False,
        ),
        (
            "multiple",
            [
                (CONSENSUS_SOURCE_IDS[0], "multiple_endorsement", candidate_ids[:3]),
                (CONSENSUS_SOURCE_IDS[1], "endorsed", candidate_ids[:1]),
            ],
            "B",
            Fraction(2, 3),
            False,
        ),
        (
            "no-endorsement",
            [(CONSENSUS_SOURCE_IDS[0], "no_endorsement", list[str]())],
            "Insufficient",
            None,
            False,
        ),
        ("missing", list[EndorsementSpec](), "Insufficient", None, False),
        (
            "tied",
            [
                (CONSENSUS_SOURCE_IDS[0], "endorsed", candidate_ids[:1]),
                (CONSENSUS_SOURCE_IDS[1], "endorsed", candidate_ids[1:2]),
                (COMPARISON_SOURCE_ID, "endorsed", candidate_ids[:1]),
            ],
            "TIED",
            Fraction(1, 2),
            True,
        ),
        (
            "insufficient",
            [
                (CONSENSUS_SOURCE_IDS[0], "endorsed", candidate_ids[:1]),
                (COMPARISON_SOURCE_ID, "endorsed", candidate_ids[:1]),
            ],
            "Insufficient",
            Fraction(1),
            False,
        ),
    ]

    for index, (label, specs, grade, share, tied) in enumerate(cases):
        dataset = _dataset(tmp_path / f"case-{index}", specs)
        result = _race_result(dataset)
        assert result.grade == grade, label
        assert result.winner_share == share, label
        assert result.is_tied is tied, label
        if label == "dual":
            assert result.candidate_support == {
                candidate_ids[0]: Fraction(3, 2),
                candidate_ids[1]: Fraction(1, 2),
            }
        if label == "multiple":
            assert result.candidate_support[candidate_ids[0]] == Fraction(4, 3)
        if label == "no-endorsement":
            assert result.no_endorsement_count == 1
            assert result.explicit_endorsement_count == 0
        if label == "missing":
            assert result.missing_source_count == len(CONSENSUS_SOURCE_IDS)
        if label in {"tied", "insufficient"}:
            assert result.comparison_results[0].status == "no_consensus"


def test_grade_boundaries_use_unrounded_exact_shares(tmp_path: Path) -> None:
    candidates = _candidate_ids()
    cases: list[tuple[str, list[EndorsementSpec], Fraction, Grade]] = [
        (
            "three-quarters",
            [
                (CONSENSUS_SOURCE_IDS[0], "dual_endorsement", candidates[:2]),
                (CONSENSUS_SOURCE_IDS[1], "endorsed", candidates[:1]),
            ],
            Fraction(3, 4),
            "A",
        ),
        (
            "three-fifths",
            [
                *[
                    (source_id, "endorsed", candidates[:1])
                    for source_id in CONSENSUS_SOURCE_IDS[:3]
                ],
                *[
                    (source_id, "endorsed", candidates[1:2])
                    for source_id in CONSENSUS_SOURCE_IDS[3:]
                ],
            ],
            Fraction(3, 5),
            "B",
        ),
        (
            "nine-twentieths",
            [
                (CONSENSUS_SOURCE_IDS[0], "endorsed", candidates[:1]),
                (CONSENSUS_SOURCE_IDS[1], "endorsed", candidates[:1]),
                (CONSENSUS_SOURCE_IDS[2], "multiple_endorsement", candidates),
                (CONSENSUS_SOURCE_IDS[3], "endorsed", candidates[1:2]),
                (CONSENSUS_SOURCE_IDS[4], "endorsed", candidates[2:3]),
            ],
            Fraction(9, 20),
            "C",
        ),
        (
            "two-fifths",
            [
                (CONSENSUS_SOURCE_IDS[0], "endorsed", candidates[:1]),
                (CONSENSUS_SOURCE_IDS[1], "endorsed", candidates[:1]),
                (CONSENSUS_SOURCE_IDS[2], "endorsed", candidates[1:2]),
                (CONSENSUS_SOURCE_IDS[3], "endorsed", candidates[2:3]),
                (CONSENSUS_SOURCE_IDS[4], "dual_endorsement", candidates[1:3]),
            ],
            Fraction(2, 5),
            "D",
        ),
    ]

    for index, (label, specs, share, grade) in enumerate(cases):
        result = _race_result(_dataset(tmp_path / f"boundary-{index}", specs))
        assert result.winner_share == share, label
        assert result.grade == grade, label


@pytest.mark.parametrize(
    ("status", "candidate_count", "allocation"),
    [
        ("dual_endorsement", 2, ["3/4", "1/4"]),
        ("multiple_endorsement", 3, ["1/2", "1/4", "1/4"]),
    ],
)
def test_scoring_rejects_unequal_explicit_allocations(
    tmp_path: Path,
    status: Literal["dual_endorsement", "multiple_endorsement"],
    candidate_count: int,
    allocation: list[str],
) -> None:
    candidates = _candidate_ids()[:candidate_count]
    source_id = CONSENSUS_SOURCE_IDS[0]
    unequal = dict(zip(candidates, allocation, strict=True))
    dataset = _dataset(
        tmp_path,
        [(source_id, status, candidates)],
        allocation_overrides={source_id: unequal},
    )

    with pytest.raises(ValueError, match="violates configured exact_equal_split"):
        score_dataset(dataset, _configuration(), computed_at=NOW)


def test_coverage_warnings_and_comparison_are_separate_from_consensus(tmp_path: Path) -> None:
    candidates = _candidate_ids()
    specs: list[EndorsementSpec] = [
        *[(source_id, "endorsed", candidates[:1]) for source_id in CONSENSUS_SOURCE_IDS[:4]],
        (CONSENSUS_SOURCE_IDS[4], "no_endorsement", list[str]()),
        (COMPARISON_SOURCE_ID, "endorsed", candidates[1:2]),
    ]
    result = _race_result(
        _dataset(
            tmp_path,
            specs,
            low_confidence_sources={CONSENSUS_SOURCE_IDS[4], COMPARISON_SOURCE_ID},
        )
    )

    assert result.eligible_source_count == 5
    assert result.source_coverage_count == 5
    assert result.explicit_endorsement_count == 4
    assert result.no_endorsement_count == 1
    assert result.missing_source_count == 0
    assert result.candidate_support == {candidates[0]: Fraction(4)}
    assert result.grade == "A+"
    assert result.comparison_results[0].status == "differs"
    assert [warning.code for warning in result.warnings] == ["no_endorsement", "low_confidence"]
    assert result.warnings[-1].source_ids == sorted([COMPARISON_SOURCE_ID, CONSENSUS_SOURCE_IDS[4]])


def test_categories_and_possible_overlap_remain_separate_disclosures(tmp_path: Path) -> None:
    candidates = _candidate_ids()
    overlapping = (CONSENSUS_SOURCE_IDS[0], CONSENSUS_SOURCE_IDS[1])
    independent = CONSENSUS_SOURCE_IDS[2]
    result = _race_result(
        _dataset(
            tmp_path,
            [
                (overlapping[0], "endorsed", candidates[:1]),
                (overlapping[1], "endorsed", candidates[:1]),
                (independent, "endorsed", candidates[1:2]),
            ],
            overlap_group_source_ids=overlapping,
        )
    )

    assert result.candidate_support == {
        candidates[0]: Fraction(2),
        candidates[1]: Fraction(1),
    }
    category = next(
        item for item in result.category_breakdown if item.category == "progressive_general"
    )
    assert category.eligible_source_count == len(CONSENSUS_SOURCE_IDS)
    assert category.source_coverage_count == 3
    assert category.explicit_endorsement_count == 3
    assert category.candidate_support == result.candidate_support
    assert result.overlap_source_ids == sorted(overlapping)
    assert [group.model_dump(mode="json") for group in result.overlap_groups] == [
        {
            "group_id": "fixture-possible-overlap",
            "label": "Fixture possible overlap",
            "description": "The relationship may overlap, but independent decisions are unknown.",
            "relationship": "possible_overlap",
            "eligible_source_ids": sorted(overlapping),
            "covered_source_ids": sorted(overlapping),
            "explicit_source_ids": sorted(overlapping),
        }
    ]
    assert independent not in result.overlap_source_ids
    assert next(
        warning for warning in result.warnings if warning.code == "source_overlap"
    ).source_ids == sorted(overlapping)


def test_geographic_eligibility_changes_only_the_registered_district(tmp_path: Path) -> None:
    inventory = read_inventory(PROJECT_ROOT / "data/normalized/wa-2026-primary-inventory.json")
    registry = read_source_registry(PROJECT_ROOT / "config/sources/default.yaml")
    dataset = CanonicalDataset(
        inventory=inventory,
        source_registry=registry,
        captures=[],
        claims=[],
        endorsements=[],
    )
    report = score_dataset(dataset, _configuration(), computed_at=NOW)
    by_race = {result.race_id: result for result in report.races}

    assert by_race["ld-11-state-representative-1"].eligible_source_count == (
        by_race[RACE_ID].eligible_source_count + 1
    )
    assert by_race["ld-32-state-representative-1"].eligible_source_count == (
        by_race[RACE_ID].eligible_source_count + 1
    )
    assert (
        by_race["king-county-council-2"].eligible_source_count
        == by_race[RACE_ID].eligible_source_count
    )


def test_pending_review_warns_and_high_severity_blocks_publication(tmp_path: Path) -> None:
    medium_dataset = _dataset(tmp_path / "medium", [], unresolved_severity="medium")
    medium_result = _race_result(medium_dataset)
    assert medium_result.pending_review_count == 1
    assert "pending_review" in {warning.code for warning in medium_result.warnings}

    high_dataset = _dataset(tmp_path / "high", [], unresolved_severity="high")
    with pytest.raises(PublicationBlockedError, match="publication blocked"):
        score_dataset(high_dataset, _configuration(), computed_at=NOW)

    allowed = score_dataset(
        high_dataset,
        _configuration(),
        computed_at=NOW,
        allow_unresolved=True,
    )
    allowed_result = next(result for result in allowed.races if result.race_id == RACE_ID)
    assert allowed.publication_has_unresolved_high_severity is True
    assert "unresolved_high_severity" in {warning.code for warning in allowed_result.warnings}

    nonpublication = _dataset(
        tmp_path / "nonpublication",
        [],
        unresolved_severity="high",
        unresolved_race_id="pco-democratic-sea-34-1247",
    )
    off_page = score_dataset(nonpublication, _configuration(), computed_at=NOW)
    assert off_page.publication_has_unresolved_high_severity is False
    assert all(result.pending_review_count == 0 for result in off_page.races)


def test_identical_inputs_produce_identical_canonical_output_and_hash(tmp_path: Path) -> None:
    candidates = _candidate_ids()
    dataset = _dataset(
        tmp_path,
        [
            (CONSENSUS_SOURCE_IDS[0], "endorsed", candidates[:1]),
            (CONSENSUS_SOURCE_IDS[1], "endorsed", candidates[:1]),
        ],
    )

    first = score_dataset(dataset, _configuration(), computed_at=NOW)
    second = score_dataset(dataset, _configuration(), computed_at=NOW)

    assert first.input_hash == second.input_hash
    assert canonical_json_bytes(first.model_dump(mode="json")) == canonical_json_bytes(
        second.model_dump(mode="json")
    )


def test_configuration_rejects_inexact_or_noncomparison_policy() -> None:
    payload = _configuration().model_dump(mode="json")
    payload["grades"][0]["minimum_share"] = 0.9
    with pytest.raises(ValidationError, match="exact integer or rational string"):
        ScoringConfiguration.model_validate(payload)

    payload = _configuration().model_dump(mode="json")
    payload["minimum_explicit_sources"] = True
    with pytest.raises(ValidationError, match="valid integer"):
        ScoringConfiguration.model_validate(payload)

    payload = _configuration().model_dump(mode="json")
    payload["tie_precedes_grade"] = 1
    with pytest.raises(ValidationError, match="valid boolean"):
        ScoringConfiguration.model_validate(payload)

    payload = _configuration().model_dump(mode="json")
    payload["grades"][-1]["minimum_explicit_sources"] = 999
    with pytest.raises(ValidationError, match="D grade must apply"):
        ScoringConfiguration.model_validate(payload)

    payload = _configuration().model_dump(mode="json")
    payload["comparison_source_ids"] = [CONSENSUS_SOURCE_IDS[0]]
    configuration = ScoringConfiguration.model_validate(payload)
    dataset = CanonicalDataset(
        inventory=read_inventory(PROJECT_ROOT / "data/normalized/wa-2026-primary-inventory.json"),
        source_registry=_source_registry(),
        captures=[],
        claims=[],
        endorsements=[],
    )
    with pytest.raises(ValueError, match="not comparison-only"):
        score_dataset(dataset, configuration, computed_at=NOW)


def test_result_schema_rejects_inexact_values_and_report_provenance_drift(
    tmp_path: Path,
) -> None:
    candidates = _candidate_ids()
    dataset = _dataset(
        tmp_path,
        [
            (CONSENSUS_SOURCE_IDS[0], "endorsed", candidates[:1]),
            (CONSENSUS_SOURCE_IDS[1], "endorsed", candidates[:1]),
            (COMPARISON_SOURCE_ID, "endorsed", candidates[:1]),
        ],
    )
    report = score_dataset(
        dataset,
        _configuration(),
        computed_at=NOW,
    )
    with pytest.raises(ValidationError, match="requires the canonical dataset"):
        ConsensusReport.model_validate(report.model_dump(mode="json"))

    payload = report.model_dump(mode="json")
    race = next(item for item in payload["races"] if item["race_id"] == RACE_ID)
    race["winner_share"] = 0.9
    with pytest.raises(ValidationError, match="exact integer or rational string"):
        _validate_report(payload, dataset)

    payload = report.model_dump(mode="json")
    race = next(item for item in payload["races"] if item["race_id"] == RACE_ID)
    race["winner_support_points"] = True
    with pytest.raises(ValidationError, match="exact integer or rational string"):
        _validate_report(payload, dataset)

    payload = report.model_dump(mode="json")
    race = next(item for item in payload["races"] if item["race_id"] == RACE_ID)
    race["grade"] = "D"
    with pytest.raises(ValidationError, match="grade does not match"):
        _validate_report(payload, dataset)

    payload = report.model_dump(mode="json")
    race = next(item for item in payload["races"] if item["race_id"] == RACE_ID)
    race["comparison_results"][0]["status"] = "differs"
    with pytest.raises(ValidationError, match="comparison status contradicts"):
        _validate_report(payload, dataset)

    payload = report.model_dump(mode="json")
    race = next(item for item in payload["races"] if item["race_id"] == RACE_ID)
    false_winner = candidates[1]
    race["candidate_support"] = {false_winner: "2"}
    race["winner_candidate_ids"] = [false_winner]
    race["winner_candidate_id"] = false_winner
    race["category_breakdown"][0]["candidate_support"] = {false_winner: "2"}
    race["comparison_results"][0]["status"] = "differs"
    with pytest.raises(ValidationError, match="values do not match the canonical dataset"):
        _validate_report(payload, dataset)

    payload = report.model_dump(mode="json")
    payload["races"][0]["comparison_results"] = []
    with pytest.raises(ValidationError, match="comparison sources do not match"):
        _validate_report(payload, dataset)

    payload = report.model_dump(mode="json")
    race = next(item for item in payload["races"] if item["race_id"] == RACE_ID)
    race["warnings"] = []
    with pytest.raises(ValidationError, match="warning does not match"):
        _validate_report(payload, dataset)

    payload = report.model_dump(mode="json")
    payload["races"].append(payload["races"][0])
    with pytest.raises(ValidationError, match="duplicate races"):
        _validate_report(payload, dataset)

    payload = report.model_dump(mode="json")
    payload["races"][0]["input_hash"] = "0" * 64
    with pytest.raises(ValidationError, match="input hash does not match"):
        _validate_report(payload, dataset)

    payload = report.model_dump(mode="json")
    payload["races"] = payload["races"][:1]
    payload["publication_race_ids"] = payload["publication_race_ids"][:1]
    payload["publication_scope_hash"] = hashlib.sha256(
        canonical_json_bytes(payload["publication_race_ids"])
    ).hexdigest()
    payload["input_hash"] = hashlib.sha256(
        canonical_json_bytes(
            {
                "dataset_hash": payload["dataset_hash"],
                "publication_scope_hash": payload["publication_scope_hash"],
                "scoring_configuration": payload["scoring_configuration"],
            }
        )
    ).hexdigest()
    payload["races"][0]["input_hash"] = payload["input_hash"]
    with pytest.raises(ValidationError, match="do not match the canonical dataset"):
        _validate_report(payload, dataset)

    payload = report.model_dump(mode="json")
    payload["publication_has_unresolved_high_severity"] = 0
    with pytest.raises(ValidationError, match="valid boolean"):
        _validate_report(payload, dataset)

    payload = report.model_dump(mode="json")
    payload["computed_at"] = "2020-01-01T00:00:00Z"
    for race in payload["races"]:
        race["computed_at"] = "2020-01-01T00:00:00Z"
    with pytest.raises(ValidationError, match=r"cannot be derived.*predates scoring input"):
        _validate_report(payload, dataset)


def test_scoring_rejects_build_timestamp_before_frozen_inputs(tmp_path: Path) -> None:
    dataset = _dataset(tmp_path, [])
    with pytest.raises(ValueError, match="predates scoring input"):
        score_dataset(
            dataset,
            _configuration(),
            computed_at=datetime(2020, 1, 1, tzinfo=UTC),
        )

    review_dataset = _dataset(
        tmp_path / "effective-review",
        [],
        unresolved_severity="medium",
    )
    review = review_dataset.review_items[0]
    old_created_at = review.model_dump(mode="json")["created_at"]
    override = new_override(
        target_record_id=review.id,
        field="created_at",
        old_value=old_created_at,
        new_value="2030-01-01T00:00:00Z",
        reason="Exercise effective timestamp causality.",
        evidence="Scoring fixture",
        author="fixture-reviewer",
        created_at=NOW,
    )
    payload = review_dataset.model_dump(mode="json")
    payload["overrides"] = [override.model_dump(mode="json")]
    overridden = CanonicalDataset.model_validate(payload)
    with pytest.raises(ValueError, match="predates scoring input"):
        score_dataset(overridden, _configuration(), computed_at=NOW)


def test_score_cli_writes_valid_canonical_report(tmp_path: Path) -> None:
    candidates = _candidate_ids()
    dataset = _dataset(
        tmp_path / "records",
        [
            (CONSENSUS_SOURCE_IDS[0], "endorsed", candidates[:1]),
            (CONSENSUS_SOURCE_IDS[1], "endorsed", candidates[:1]),
        ],
    )
    dataset_path = tmp_path / "dataset.json"
    output_path = tmp_path / "consensus.json"
    dataset_path.write_bytes(canonical_json_bytes(dataset.model_dump(mode="json")))

    result = CliRunner().invoke(
        app,
        [
            "score",
            "--dataset-path",
            str(dataset_path),
            "--config",
            str(PROJECT_ROOT / "config/scoring/default.yaml"),
            "--output-path",
            str(output_path),
            "--computed-at",
            NOW.isoformat(),
        ],
    )

    assert result.exit_code == 0, result.output
    assert "consensus:" in result.output
    assert read_json(output_path)["configuration_id"] == "unweighted-progressive-v1"

    epoch_output = tmp_path / "consensus-from-epoch.json"
    epoch_result = CliRunner().invoke(
        app,
        [
            "score",
            "--dataset-path",
            str(dataset_path),
            "--config",
            str(PROJECT_ROOT / "config/scoring/default.yaml"),
            "--output-path",
            str(epoch_output),
        ],
        env={"SOURCE_DATE_EPOCH": str(int(NOW.timestamp()))},
    )
    assert epoch_result.exit_code == 0, epoch_result.output
    assert output_path.read_bytes() == epoch_output.read_bytes()


def _race_result(dataset: CanonicalDataset) -> RaceConsensus:
    report = score_dataset(dataset, _configuration(), computed_at=NOW)
    return next(result for result in report.races if result.race_id == RACE_ID)


def _validate_report(payload: object, dataset: CanonicalDataset) -> ConsensusReport:
    return ConsensusReport.model_validate(
        payload,
        context={"canonical_dataset": dataset},
    )


def _configuration() -> ScoringConfiguration:
    return read_scoring_configuration(PROJECT_ROOT / "config/scoring/default.yaml")


def _candidate_ids() -> list[str]:
    inventory = read_inventory(PROJECT_ROOT / "data/normalized/wa-2026-primary-inventory.json")
    race = next(race for race in inventory.races if race.id == RACE_ID)
    return [choice.id for choice in race.choices]


def _source_registry() -> SourceRegistry:
    registry = read_source_registry(PROJECT_ROOT / "config/sources/default.yaml")
    selected = {*CONSENSUS_SOURCE_IDS, COMPARISON_SOURCE_ID}
    payload = registry.model_dump(mode="json")
    payload["sources"] = [source for source in payload["sources"] if source["id"] in selected]
    payload["overlap_groups"] = []
    return SourceRegistry.model_validate(payload)


def _dataset(
    root: Path,
    specs: list[EndorsementSpec],
    *,
    low_confidence_sources: set[str] | None = None,
    allocation_overrides: dict[str, dict[str, str]] | None = None,
    unresolved_severity: Literal["high", "medium", "low"] | None = None,
    unresolved_race_id: str = RACE_ID,
    overlap_group_source_ids: tuple[str, str] | None = None,
) -> CanonicalDataset:
    inventory = read_inventory(PROJECT_ROOT / "data/normalized/wa-2026-primary-inventory.json")
    registry = _source_registry()
    if overlap_group_source_ids is not None:
        registry_payload = registry.model_dump(mode="json")
        for source in registry_payload["sources"]:
            if source["id"] in overlap_group_source_ids:
                source["overlap_group_ids"] = ["fixture-possible-overlap"]
        registry_payload["overlap_groups"] = [
            {
                "id": "fixture-possible-overlap",
                "label": "Fixture possible overlap",
                "description": (
                    "The relationship may overlap, but independent decisions are unknown."
                ),
                "member_ids": list(overlap_group_source_ids),
            }
        ]
        registry = SourceRegistry.model_validate(registry_payload)
    race = next(item for item in inventory.races if item.id == RACE_ID)
    choice_by_id = {choice.id: choice for choice in race.choices}
    captures: list[CaptureManifest] = []
    claims: list[ExtractedClaim] = []
    endorsements: list[NormalizedEndorsement] = []
    review_items: list[ReviewItem] = []
    review_decisions: list[ReviewDecision] = []
    low_confidence_sources = low_confidence_sources or set()
    allocation_overrides = allocation_overrides or {}

    for index, (source_id, status, candidate_ids) in enumerate(specs):
        capture = _capture(root / f"source-{index}", source_id)
        raw_status = {
            "endorsed": "Endorsed",
            "dual_endorsement": "Dual endorsement",
            "multiple_endorsement": "Multiple endorsement",
            "no_endorsement": "No endorsement",
            "declined_to_endorse": "Declined to endorse",
        }[status]
        raw_candidate = (
            choice_by_id[candidate_ids[0]].official_name if status == "endorsed" else None
        )
        confidence = "1/2" if source_id in low_confidence_sources else "1"
        claim = new_extracted_claim(
            capture_id=capture.id,
            source_id=source_id,
            raw_race_text=race.display_name,
            raw_candidate_text=raw_candidate,
            raw_status_text=raw_status,
            raw_notes=None,
            evidence_excerpt=f"Fixture decision for {source_id}.",
            evidence_locator="Fixture line 1",
            extractor="scoring-fixture",
            extractor_version="1.0",
            extraction_confidence=confidence,
            requires_review=False,
        )
        review_item_id = None
        manually_verified = False
        allocation = allocation_overrides.get(
            source_id,
            (
                {
                    candidate_id: str(Fraction(1, len(candidate_ids)))
                    for candidate_id in candidate_ids
                }
                if candidate_ids
                else {}
            ),
        )
        if status in {"dual_endorsement", "multiple_endorsement"}:
            race_match = MatchResult(
                status="matched",
                selected_id=race.id,
                candidates=[
                    MatchCandidate(
                        record_id=race.id,
                        label=race.display_name,
                        score=Fraction(1),
                        match_kind="exact",
                    )
                ],
            )
            review = new_review_item(
                claim_id=claim.id,
                severity="medium",
                reason="semantics_ambiguous",
                summary="Fixture multi-candidate decision requires structured allocation.",
                race_match=race_match,
                candidate_match=None,
                capture_id=capture.id,
                raw_race_text=claim.raw_race_text,
                raw_candidate_text=claim.raw_candidate_text,
                raw_status_text=claim.raw_status_text,
                evidence_excerpt=claim.evidence_excerpt,
                evidence_locator=claim.evidence_locator,
                created_at=NOW,
            )
            decision = new_review_decision(
                review_item_id=review.id,
                action="approve",
                author="fixture-reviewer",
                reason="The fixture explicitly identifies all co-endorsed candidates.",
                evidence="Fixture line 1",
                created_at=NOW,
                resolution={
                    "race_id": race.id,
                    "status": status,
                    "candidate_ids": candidate_ids,
                    "allocation": allocation,
                },
            )
            review_items.append(review)
            review_decisions.append(decision)
            review_item_id = review.id
            manually_verified = True
        endorsement = new_normalized_endorsement(
            election_id=inventory.election.id,
            race_id=race.id,
            source_id=source_id,
            status=status,
            candidate_ids=candidate_ids,
            allocation=allocation,
            published_at=capture.published_at,
            source_capture_id=capture.id,
            extracted_claim_id=claim.id,
            normalization_confidence=confidence,
            manually_verified=manually_verified,
            reviewer="fixture-reviewer" if manually_verified else None,
            reviewed_at=NOW if manually_verified else None,
            review_item_id=review_item_id,
            notes=None,
        )
        captures.append(capture)
        claims.append(claim)
        endorsements.append(endorsement)

    if unresolved_severity is not None:
        review_race = next(item for item in inventory.races if item.id == unresolved_race_id)
        source_id = CONSENSUS_SOURCE_IDS[0]
        capture = _capture(root / "unresolved", source_id)
        claim = new_extracted_claim(
            capture_id=capture.id,
            source_id=source_id,
            raw_race_text=review_race.display_name,
            raw_candidate_text="Unknown Candidate",
            raw_status_text="Endorsed",
            raw_notes=None,
            evidence_excerpt="Fixture ambiguous endorsement.",
            evidence_locator="Fixture line 2",
            extractor="scoring-fixture",
            extractor_version="1.0",
            extraction_confidence="1/2",
            requires_review=True,
        )
        review = new_review_item(
            claim_id=claim.id,
            severity=unresolved_severity,
            reason="candidate_unmatched",
            summary="Fixture candidate could not be matched.",
            race_match=MatchResult(
                status="matched",
                selected_id=review_race.id,
                candidates=[
                    MatchCandidate(
                        record_id=review_race.id,
                        label=review_race.display_name,
                        score=Fraction(1),
                        match_kind="exact",
                    )
                ],
            ),
            candidate_match=MatchResult(status="unmatched", candidates=[]),
            capture_id=capture.id,
            raw_race_text=claim.raw_race_text,
            raw_candidate_text=claim.raw_candidate_text,
            raw_status_text=claim.raw_status_text,
            evidence_excerpt=claim.evidence_excerpt,
            evidence_locator=claim.evidence_locator,
            created_at=NOW,
        )
        captures.append(capture)
        claims.append(claim)
        review_items.append(review)

    return CanonicalDataset(
        inventory=inventory,
        source_registry=registry,
        captures=captures,
        claims=claims,
        endorsements=endorsements,
        review_items=review_items,
        review_decisions=review_decisions,
    )


def _capture(root: Path, source_id: str) -> CaptureManifest:
    root.mkdir(parents=True, exist_ok=True)
    input_path = PROJECT_ROOT / "tests/fixtures/evidence/static.html"
    manifest_path = record_capture(
        CaptureRequest.model_validate(
            {
                "source_id": source_id,
                "requested_url": f"https://example.com/{source_id}",
                "canonical_url": f"https://example.com/{source_id}",
                "retrieved_at": "2026-07-19T12:00:00Z",
                "http_status": 200,
                "media_type": "text/html",
                "title": f"Fixture for {source_id}",
                "published_at": "2026-07-02",
                "capture_method": "static_html",
                "browser_required": False,
                "redistribution": "permitted",
                "redistribution_note": "Synthetic scoring fixture.",
            }
        ),
        input_path,
        root / "snapshots",
        root / "manifests",
    )
    return read_capture_manifest(manifest_path)
