from __future__ import annotations

import csv
import hashlib
import io
import json
import os
from pathlib import Path

import pytest
from pydantic import ValidationError
from typer.testing import CliRunner

from election_guide.cli import app
from election_guide.evidence.models import (
    CapturedManifest,
    UnavailableManifest,
    UnavailableRequest,
)
from election_guide.evidence.storage import read_capture_manifest, record_unavailable
from election_guide.normalization.models import CanonicalDataset
from election_guide.normalization.records import (
    new_extracted_claim,
    new_normalized_endorsement,
)
from election_guide.publication import build_publication_bundle, write_publication_bundle
from election_guide.publication import builder as publication_builder
from election_guide.publication.builder import ARTIFACT_NAMES
from election_guide.publication.models import (
    PublicationComparison,
    PublicationViewModel,
    SourceCell,
)
from election_guide.scoring import score_dataset
from election_guide.serialization import canonical_json_bytes
from tests.test_scoring import (
    COMPARISON_SOURCE_ID,
    CONSENSUS_SOURCE_IDS,
    NOW,
    RACE_ID,
    _candidate_ids,  # pyright: ignore[reportPrivateUsage]
    _configuration,  # pyright: ignore[reportPrivateUsage]
    _dataset,  # pyright: ignore[reportPrivateUsage]
)


def test_bundle_is_deterministic_reconstructable_and_complete(tmp_path: Path) -> None:
    dataset = _publication_dataset(tmp_path)
    snapshot_root = _snapshot_store(tmp_path, dataset)
    report = score_dataset(
        dataset,
        _configuration(),
        computed_at=NOW,
        allow_unresolved=True,
    )

    first = build_publication_bundle(
        dataset, report, git_commit="abc123", snapshot_root=snapshot_root
    )
    second = build_publication_bundle(
        dataset, report, git_commit="abc123", snapshot_root=snapshot_root
    )

    assert first.artifacts == second.artifacts
    assert tuple(first.artifacts) == ARTIFACT_NAMES
    assert first.validation_report.passed
    assert (
        PublicationViewModel.model_validate(
            _read_json_bytes(first.artifacts["publication_view_model.json"])
        )
        == first.view_model
    )

    target = next(
        race
        for section in first.view_model.sections
        for race in section.races
        if race.id == RACE_ID
    )
    states = {cell.source_id: cell.state for cell in target.source_cells}
    assert states == {
        CONSENSUS_SOURCE_IDS[0]: "unverified",
        CONSENSUS_SOURCE_IDS[1]: "endorsement",
        CONSENSUS_SOURCE_IDS[2]: "multi_endorsement",
        CONSENSUS_SOURCE_IDS[3]: "no_endorsement",
        CONSENSUS_SOURCE_IDS[4]: "unavailable",
        COMPARISON_SOURCE_ID: "endorsement",
    }
    assert any(
        cell.state == "not_covered"
        for section in first.view_model.sections
        for race in section.races
        for cell in race.source_cells
    )
    candidates = _candidate_ids()
    assert [group.candidate_id for group in target.endorsement_groups] == candidates[:2]
    assert [
        (endorser.source_id, endorser.co_endorsement)
        for endorser in target.endorsement_groups[0].endorsers
    ] == [
        (CONSENSUS_SOURCE_IDS[1], False),
        (CONSENSUS_SOURCE_IDS[2], True),
    ]
    assert [
        (endorser.source_id, endorser.co_endorsement)
        for endorser in target.endorsement_groups[1].endorsers
    ] == [(CONSENSUS_SOURCE_IDS[2], True)]
    assert all(
        endorser.source_id != COMPARISON_SOURCE_ID
        for group in target.endorsement_groups
        for endorser in group.endorsers
    )
    assert target.support_summary == "Based on 2 explicitly endorsing sources"

    summary_rows = _csv_rows(first.artifacts["race_summary.csv"])
    summary = next(row for row in summary_rows if row["race_id"] == RACE_ID)
    result = next(item for item in report.races if item.race_id == RACE_ID)
    assert summary["support_leader_candidate_ids"] == "|".join(result.winner_candidate_ids)
    assert summary["grade"] == result.grade
    assert summary["winner_share"] == str(result.winner_share)

    manifest = first.build_manifest
    assert set(manifest.artifact_hashes) == set(ARTIFACT_NAMES) - {"build_manifest.json"}
    for name, digest in manifest.artifact_hashes.items():
        assert digest == hashlib.sha256(first.artifacts[name]).hexdigest()
    assert (
        first.provenance_manifest.consensus_output_hash
        == hashlib.sha256(first.artifacts["consensus.json"]).hexdigest()
    )

    mutated = first.view_model.model_copy(deep=True)
    mutated_target = next(
        race for section in mutated.sections for race in section.races if race.id == RACE_ID
    )
    mutated_target.recommendation_candidate_ids = ["fabricated-candidate"]
    mutated_target.recommendation_candidate_labels = ["Fabricated Candidate"]
    mutated_target.recommendation_label = "Fabricated Candidate"
    with pytest.raises(ValidationError, match="support leaders"):
        PublicationViewModel.model_validate(mutated.model_dump(mode="json"))

    mutated = first.view_model.model_copy(deep=True)
    mutated_target = next(
        race for section in mutated.sections for race in section.races if race.id == RACE_ID
    )
    mutated_target.warning_messages = []
    with pytest.raises(ValidationError, match="warning codes and messages must align"):
        PublicationViewModel.model_validate(mutated.model_dump(mode="json"))

    mutated = first.view_model.model_copy(deep=True)
    mutated_target = next(
        race for section in mutated.sections for race in section.races if race.id == RACE_ID
    )
    mutated_target.comparisons[0].badge_label = "AGREES"
    with pytest.raises(ValidationError, match="badge"):
        PublicationViewModel.model_validate(mutated.model_dump(mode="json"))

    mutated = first.view_model.model_copy(deep=True)
    mutated_target = next(
        race for section in mutated.sections for race in section.races if race.id == RACE_ID
    )
    unavailable = next(cell for cell in mutated_target.source_cells if cell.state == "unavailable")
    unavailable.evidence_url = None
    unavailable.evidence_locator = None
    with pytest.raises(ValidationError, match="requires evidence"):
        PublicationViewModel.model_validate(mutated.model_dump(mode="json"))

    mutated = first.view_model.model_copy(deep=True)
    mutated_target = next(
        race for section in mutated.sections for race in section.races if race.id == RACE_ID
    )
    mutated_target.grade = "FABRICATED"  # type: ignore[assignment]
    with pytest.raises(ValidationError, match="literal_error"):
        PublicationViewModel.model_validate(mutated.model_dump(mode="json"))

    mutated = first.view_model.model_copy(deep=True)
    mutated_target = next(
        race for section in mutated.sections for race in section.races if race.id == RACE_ID
    )
    mutated_target.grade = "TIED"
    with pytest.raises(ValidationError, match="multiple support leaders"):
        PublicationViewModel.model_validate(mutated.model_dump(mode="json"))

    mutated = first.view_model.model_copy(deep=True)
    mutated_target = next(
        race for section in mutated.sections for race in section.races if race.id == RACE_ID
    )
    mutated_target.comparisons = []
    with pytest.raises(ValidationError, match="ordered comparison sources"):
        PublicationViewModel.model_validate(mutated.model_dump(mode="json"))

    mutated = first.view_model.model_copy(deep=True)
    mutated_target = next(
        race for section in mutated.sections for race in section.races if race.id == RACE_ID
    )
    mutated_target.endorsement_groups[0].endorsers[0].source_name = "Fabricated source"
    with pytest.raises(ValidationError, match="affirmative source cells"):
        PublicationViewModel.model_validate(mutated.model_dump(mode="json"))

    mutated = first.view_model.model_copy(deep=True)
    mutated_target = next(
        race for section in mutated.sections for race in section.races if race.id == RACE_ID
    )
    group = mutated_target.endorsement_groups[0]
    endorser = group.endorsers[0]
    cell = next(
        cell for cell in mutated_target.source_cells if cell.source_id == endorser.source_id
    )
    cell.evidence_url = "https://example.com/coordinated-fabrication"
    endorser.evidence_url = cell.evidence_url
    internally_consistent = PublicationViewModel.model_validate(mutated.model_dump(mode="json"))
    canonical_check = next(
        check
        for check in publication_builder._validate_publication(  # pyright: ignore[reportPrivateUsage]
            dataset, report, internally_consistent
        )
        if check.id == "canonical-evidence"
    )
    assert not canonical_check.passed

    mutated = first.view_model.model_copy(deep=True)
    mutated_target = next(
        race for section in mutated.sections for race in section.races if race.id == RACE_ID
    )
    endorsement = next(
        cell
        for cell in mutated_target.source_cells
        if cell.state == "endorsement" and cell.source_id != COMPARISON_SOURCE_ID
    )
    endorsement.state = "not_covered"
    endorsement.candidate_ids = []
    endorsement.candidate_labels = []
    endorsement.allocation = {}
    endorsement.evidence_url = None
    endorsement.evidence_locator = None
    with pytest.raises(ValidationError, match="explicit endorsement count"):
        PublicationViewModel.model_validate(mutated.model_dump(mode="json"))


@pytest.mark.parametrize(
    (
        "status",
        "badge_label",
        "candidate_labels",
        "voter_label",
        "voter_tone",
        "print_label",
        "accessible_label",
    ),
    [
        (
            "agrees",
            "AGREES",
            ["Candidate A"],
            "Candidate A",
            "agrees",
            "Times agrees: Candidate A",
            "Seattle Times agrees with consensus: Candidate A",
        ),
        (
            "differs",
            "DIFFERENT PICK",
            ["Candidate B"],
            "Candidate B",
            "differs",
            "Times differs: Candidate B",
            "Seattle Times endorses a different choice: Candidate B",
        ),
        (
            "no_endorsement",
            "NO PICK",
            [],
            "NOT COVERED",
            "not_covered",
            "Times: not covered",
            "Seattle Times made no endorsement",
        ),
        (
            "not_covered",
            "NOT COVERED",
            [],
            "NOT COVERED",
            "not_covered",
            "Times: not covered",
            "Seattle Times: not covered",
        ),
        (
            "no_consensus",
            "NO PROGRESSIVE CONSENSUS",
            ["Candidate C"],
            "Candidate C",
            "neutral",
            "Times: Candidate C",
            "Seattle Times endorses Candidate C; progressive sources have no consensus",
        ),
    ],
)
def test_comparison_has_concise_voter_presentation(
    status: str,
    badge_label: str,
    candidate_labels: list[str],
    voter_label: str,
    voter_tone: str,
    print_label: str,
    accessible_label: str,
) -> None:
    comparison = PublicationComparison.model_validate(
        {
            "source_id": COMPARISON_SOURCE_ID,
            "status": status,
            "badge_label": badge_label,
            "candidate_ids": [f"candidate-{index}" for index, _ in enumerate(candidate_labels)],
            "candidate_labels": candidate_labels,
        }
    )

    assert comparison.voter_label == voter_label
    assert comparison.voter_tone == voter_tone
    assert comparison.print_label == print_label
    assert comparison.voter_accessible_label == accessible_label


def test_methodology_publishes_possible_overlap_without_deduplicating(tmp_path: Path) -> None:
    candidates = _candidate_ids()
    overlapping = (CONSENSUS_SOURCE_IDS[0], CONSENSUS_SOURCE_IDS[1])
    dataset = _dataset(
        tmp_path / "fixture",
        [
            (overlapping[0], "endorsed", candidates[:1]),
            (overlapping[1], "endorsed", candidates[:1]),
            (CONSENSUS_SOURCE_IDS[2], "endorsed", candidates[1:2]),
        ],
        overlap_group_source_ids=overlapping,
    )
    snapshot_root = _snapshot_store(tmp_path, dataset)
    report = score_dataset(dataset, _configuration(), computed_at=NOW)
    bundle = build_publication_bundle(
        dataset,
        report,
        git_commit="abc123",
        snapshot_root=snapshot_root,
    )

    methodology = bundle.view_model.methodology
    assert bundle.view_model.schema_version == "1.2"
    assert methodology.default_aggregation_view == "source_level"
    assert methodology.deduplicated_view == "not_computed"
    assert [group.model_dump(mode="json") for group in methodology.source_overlap_groups] == [
        {
            "id": "fixture-possible-overlap",
            "label": "Fixture possible overlap",
            "description": "The relationship may overlap, but independent decisions are unknown.",
            "relationship": "possible_overlap",
            "source_ids": sorted(overlapping),
        }
    ]
    race = next(
        item
        for section in bundle.view_model.sections
        for item in section.races
        if item.id == RACE_ID
    )
    assert race.winner_share == "2/3"
    assert race.explicit_endorsement_count == 3
    progressive = next(
        item for item in race.category_breakdown if item.category == "progressive_general"
    )
    assert progressive.source_coverage_count == 3
    assert progressive.eligible_source_count == len(CONSENSUS_SOURCE_IDS)
    assert {item.candidate_id: item.support_points for item in progressive.candidate_support} == {
        candidates[0]: "2",
        candidates[1]: "1",
    }
    assert [item.candidate_id for item in progressive.candidate_support] == sorted(candidates[:2])

    mutated = bundle.view_model.model_copy(deep=True)
    mutated.methodology.source_overlap_groups = []
    with pytest.raises(ValidationError, match="must match active source metadata"):
        PublicationViewModel.model_validate(mutated.model_dump(mode="json"))

    mutated = bundle.view_model.model_copy(deep=True)
    mutated_source = mutated.sources[2]
    mutated_source.overlap_group_ids = sorted(
        {*mutated_source.overlap_group_ids, "fabricated-group"}
    )
    with pytest.raises(ValidationError, match="must match active source metadata"):
        PublicationViewModel.model_validate(mutated.model_dump(mode="json"))

    mutated = bundle.view_model.model_copy(deep=True)
    mutated_race = next(
        item for section in mutated.sections for item in section.races if item.id == RACE_ID
    )
    mutated_category = next(
        item for item in mutated_race.category_breakdown if item.category == "progressive_general"
    )
    mutated_support = next(
        item for item in mutated_category.candidate_support if item.candidate_id == candidates[0]
    )
    mutated_support.support_points = "1"
    with pytest.raises(ValidationError, match="category candidate support"):
        PublicationViewModel.model_validate(mutated.model_dump(mode="json"))


def test_writer_and_cli_emit_the_same_canonical_bundle(tmp_path: Path) -> None:
    dataset = _publication_dataset(tmp_path / "fixture")
    snapshot_root = _snapshot_store(tmp_path, dataset)
    report = score_dataset(
        dataset,
        _configuration(),
        computed_at=NOW,
        allow_unresolved=True,
    )
    expected = build_publication_bundle(
        dataset, report, git_commit="test-sha", snapshot_root=snapshot_root
    )
    direct_dir = tmp_path / "direct"
    assert len(write_publication_bundle(expected, direct_dir)) == len(ARTIFACT_NAMES)

    dataset_path = tmp_path / "dataset.json"
    report_path = tmp_path / "consensus.json"
    dataset_path.write_bytes(canonical_json_bytes(dataset.model_dump(mode="json")))
    report_path.write_bytes(canonical_json_bytes(report.model_dump(mode="json")))
    cli_dir = tmp_path / "cli"
    result = CliRunner().invoke(
        app,
        [
            "export",
            "build",
            "--dataset-path",
            str(dataset_path),
            "--consensus-path",
            str(report_path),
            "--output-dir",
            str(cli_dir),
            "--snapshot-root",
            str(snapshot_root),
            "--git-commit",
            "test-sha",
        ],
    )

    assert result.exit_code == 0, result.output
    assert "10 artifacts" in result.output
    for name in ARTIFACT_NAMES:
        assert (direct_dir / name).read_bytes() == (cli_dir / name).read_bytes()


def test_bundle_rejects_a_consensus_report_that_drifted_from_inputs(tmp_path: Path) -> None:
    dataset = _publication_dataset(tmp_path)
    snapshot_root = _snapshot_store(tmp_path, dataset)
    report = score_dataset(
        dataset,
        _configuration(),
        computed_at=NOW,
        allow_unresolved=True,
    )
    tampered = report.model_copy(deep=True)
    target = next(race for race in tampered.races if race.race_id == RACE_ID)
    target.warnings[0].message += " Tampered."

    with pytest.raises(ValidationError, match="canonical dataset"):
        build_publication_bundle(
            dataset, tampered, git_commit="abc123", snapshot_root=snapshot_root
        )


def test_bundle_rejects_missing_or_corrupt_snapshot_bytes(tmp_path: Path) -> None:
    dataset = _publication_dataset(tmp_path)
    snapshot_root = _snapshot_store(tmp_path, dataset)
    report = score_dataset(
        dataset,
        _configuration(),
        computed_at=NOW,
        allow_unresolved=True,
    )
    captured = next(item for item in dataset.captures if isinstance(item, CapturedManifest))
    artifact = snapshot_root / captured.storage_reference
    artifact.write_bytes(b"tampered snapshot bytes")

    with pytest.raises(ValueError, match="capture hash mismatch"):
        build_publication_bundle(dataset, report, git_commit="abc123", snapshot_root=snapshot_root)
    artifact.unlink()
    with pytest.raises(ValueError, match="captured evidence is missing"):
        build_publication_bundle(dataset, report, git_commit="abc123", snapshot_root=snapshot_root)


def test_insufficient_support_leader_is_not_a_recommendation(tmp_path: Path) -> None:
    candidates = _candidate_ids()
    dataset = _dataset(
        tmp_path,
        [(CONSENSUS_SOURCE_IDS[0], "endorsed", candidates[:1])],
    )
    snapshot_root = _snapshot_store(tmp_path, dataset)
    report = score_dataset(dataset, _configuration(), computed_at=NOW)
    bundle = build_publication_bundle(
        dataset, report, git_commit="abc123", snapshot_root=snapshot_root
    )
    target = next(
        race
        for section in bundle.view_model.sections
        for race in section.races
        if race.id == RACE_ID
    )

    assert target.grade == "Insufficient"
    assert target.support_leader_candidate_ids == candidates[:1]
    assert target.recommendation_candidate_ids == []
    assert target.recommendation_label == "Too few endorsements"


def test_no_endorsement_cell_counts_toward_category_coverage(tmp_path: Path) -> None:
    candidates = _candidate_ids()
    base = _dataset(
        tmp_path,
        [
            (CONSENSUS_SOURCE_IDS[0], "endorsed", candidates[:1]),
            (CONSENSUS_SOURCE_IDS[3], "no_endorsement", []),
        ],
    )
    registry_payload = base.source_registry.model_dump(mode="json")
    for source in registry_payload["sources"]:
        if source["id"] == CONSENSUS_SOURCE_IDS[3]:
            source["category"] = "labor"
    registry = type(base.source_registry).model_validate(registry_payload)
    dataset = CanonicalDataset(
        inventory=base.inventory,
        source_registry=registry,
        captures=base.captures,
        claims=base.claims,
        endorsements=base.endorsements,
        review_items=base.review_items,
        review_decisions=base.review_decisions,
    )
    snapshot_root = _snapshot_store(tmp_path, dataset)
    report = score_dataset(dataset, _configuration(), computed_at=NOW)

    result = next(item for item in report.races if item.race_id == RACE_ID)
    assert result.category_coverage_count == 2
    bundle = build_publication_bundle(
        dataset, report, git_commit="abc123", snapshot_root=snapshot_root
    )
    assert bundle.validation_report.passed


def test_bundle_directory_replacement_rolls_back_before_commit(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    dataset = _publication_dataset(tmp_path / "fixture")
    snapshot_root = _snapshot_store(tmp_path, dataset)
    report = score_dataset(
        dataset,
        _configuration(),
        computed_at=NOW,
        allow_unresolved=True,
    )
    old_bundle = build_publication_bundle(
        dataset, report, git_commit="old", snapshot_root=snapshot_root
    )
    new_bundle = build_publication_bundle(
        dataset, report, git_commit="new", snapshot_root=snapshot_root
    )
    output_dir = tmp_path / "published"
    write_publication_bundle(old_bundle, output_dir)
    old_bytes = {name: (output_dir / name).read_bytes() for name in ARTIFACT_NAMES}
    original_write = publication_builder._atomic_write  # pyright: ignore[reportPrivateUsage]
    calls = 0

    def fail_during_staging(path: Path, content: bytes) -> None:
        nonlocal calls
        calls += 1
        if calls == 3:
            raise OSError("injected staging failure")
        original_write(path, content)

    monkeypatch.setattr(publication_builder, "_atomic_write", fail_during_staging)
    with pytest.raises(OSError, match="injected staging failure"):
        write_publication_bundle(new_bundle, output_dir)

    assert {name: (output_dir / name).read_bytes() for name in ARTIFACT_NAMES} == old_bytes


@pytest.mark.skipif(os.name == "nt", reason="POSIX permission bits")
def test_publication_files_are_world_readable(tmp_path: Path) -> None:
    dataset = _publication_dataset(tmp_path / "fixture")
    snapshot_root = _snapshot_store(tmp_path, dataset)
    report = score_dataset(
        dataset,
        _configuration(),
        computed_at=NOW,
        allow_unresolved=True,
    )
    bundle = build_publication_bundle(
        dataset, report, git_commit="abc123", snapshot_root=snapshot_root
    )
    dangling = tmp_path / "dangling"
    dangling.symlink_to(tmp_path / "missing-target", target_is_directory=True)
    with pytest.raises(ValueError, match="cannot be a symbolic link"):
        write_publication_bundle(bundle, dangling)
    output_dir = tmp_path / "published"
    write_publication_bundle(bundle, output_dir)

    assert output_dir.stat().st_mode & 0o777 == 0o755
    assert all((output_dir / name).stat().st_mode & 0o777 == 0o644 for name in ARTIFACT_NAMES)


def test_source_cells_enforce_exact_state_semantics() -> None:
    with pytest.raises(ValidationError, match="exactly one"):
        SourceCell(
            source_id="fixture-source",
            state="endorsement",
            candidate_ids=["one", "two"],
            candidate_labels=["One", "Two"],
            allocation={"one": "1/2", "two": "1/2"},
            evidence_url="https://example.com/evidence",
            evidence_locator="Fixture line 1",
            confidence_warning=False,
        )
    with pytest.raises(ValidationError, match="at least two"):
        SourceCell(
            source_id="fixture-source",
            state="multi_endorsement",
            candidate_ids=["one"],
            candidate_labels=["One"],
            allocation={"one": "1"},
            evidence_url="https://example.com/evidence",
            evidence_locator="Fixture line 1",
            confidence_warning=False,
        )
    with pytest.raises(ValidationError, match="must be unique"):
        SourceCell(
            source_id="fixture-source",
            state="multi_endorsement",
            candidate_ids=["one", "one"],
            candidate_labels=["One", "One"],
            allocation={"one": "1"},
            evidence_url="https://example.com/evidence",
            evidence_locator="Fixture line 1",
            confidence_warning=False,
        )
    with pytest.raises(ValidationError, match="exact rational"):
        SourceCell(
            source_id="fixture-source",
            state="endorsement",
            candidate_ids=["one"],
            candidate_labels=["One"],
            allocation={"one": "garbage"},
            evidence_url="https://example.com/evidence",
            evidence_locator="Fixture line 1",
            confidence_warning=False,
        )
    with pytest.raises(ValidationError, match="exact equal split"):
        SourceCell(
            source_id="fixture-source",
            state="multi_endorsement",
            candidate_ids=["one", "two"],
            candidate_labels=["One", "Two"],
            allocation={"one": "3/4", "two": "1/4"},
            evidence_url="https://example.com/evidence",
            evidence_locator="Fixture line 1",
            confidence_warning=False,
        )
    with pytest.raises(ValidationError, match="requires evidence"):
        SourceCell(
            source_id="fixture-source",
            state="unavailable",
            candidate_ids=[],
            candidate_labels=[],
            allocation={},
            evidence_url=None,
            evidence_locator=None,
            confidence_warning=False,
        )


def _publication_dataset(root: Path) -> CanonicalDataset:
    candidates = _candidate_ids()
    base = _dataset(
        root,
        [
            (CONSENSUS_SOURCE_IDS[1], "endorsed", candidates[:1]),
            (CONSENSUS_SOURCE_IDS[2], "dual_endorsement", candidates[:2]),
            (CONSENSUS_SOURCE_IDS[3], "no_endorsement", []),
            (COMPARISON_SOURCE_ID, "endorsed", candidates[1:2]),
        ],
        unresolved_severity="medium",
    )
    review = base.review_items[-1]
    claim = base.claims[-1]
    capture = base.captures[-1]
    unverified = new_normalized_endorsement(
        election_id=base.inventory.election.id,
        race_id=RACE_ID,
        source_id=CONSENSUS_SOURCE_IDS[0],
        status="unverified",
        candidate_ids=[],
        allocation={},
        published_at=capture.published_at,
        source_capture_id=capture.id,
        extracted_claim_id=claim.id,
        normalization_confidence="1/2",
        manually_verified=False,
        reviewer=None,
        reviewed_at=None,
        review_item_id=review.id,
        notes="Pending fixture review.",
    )

    unavailable_path = record_unavailable(
        UnavailableRequest.model_validate(
            {
                "source_id": CONSENSUS_SOURCE_IDS[4],
                "requested_url": "https://example.com/unavailable",
                "retrieved_at": "2026-07-19T12:00:00Z",
                "http_status": 403,
                "media_type": "text/html",
                "capture_method": "unavailable",
                "browser_required": False,
                "redistribution": "restricted",
                "redistribution_note": "Synthetic publication fixture.",
                "unavailable_reason": "Fixture access denied.",
            }
        ),
        root / "unavailable-manifests",
    )
    unavailable_capture = read_capture_manifest(unavailable_path)
    assert isinstance(unavailable_capture, UnavailableManifest)
    unavailable_claim = new_extracted_claim(
        capture_id=unavailable_capture.id,
        source_id=unavailable_capture.source_id,
        raw_race_text="King County Assessor",
        raw_candidate_text=None,
        raw_status_text="Source unavailable",
        raw_notes=None,
        evidence_excerpt=unavailable_capture.unavailable_reason,
        evidence_locator="Unavailable capture metadata",
        extractor="publication-fixture",
        extractor_version="1.0",
        extraction_confidence="1",
        requires_review=False,
    )
    unavailable = new_normalized_endorsement(
        election_id=base.inventory.election.id,
        race_id=RACE_ID,
        source_id=CONSENSUS_SOURCE_IDS[4],
        status="source_unavailable",
        candidate_ids=[],
        allocation={},
        published_at=unavailable_capture.published_at,
        source_capture_id=unavailable_capture.id,
        extracted_claim_id=unavailable_claim.id,
        normalization_confidence="1",
        manually_verified=False,
        reviewer=None,
        reviewed_at=None,
        review_item_id=None,
        notes="Fixture unavailable state.",
    )
    return CanonicalDataset(
        inventory=base.inventory,
        source_registry=base.source_registry,
        captures=[*base.captures, unavailable_capture],
        claims=[*base.claims, unavailable_claim],
        endorsements=[*base.endorsements, unverified, unavailable],
        review_items=base.review_items,
        review_decisions=base.review_decisions,
    )


def _csv_rows(content: bytes) -> list[dict[str, str]]:
    return list(csv.DictReader(io.StringIO(content.decode("utf-8"))))


def _read_json_bytes(content: bytes) -> object:
    return json.loads(content)


def _snapshot_store(root: Path, dataset: CanonicalDataset) -> Path:
    storage_root = root / "snapshot-store"
    content = (Path(__file__).parent / "fixtures/evidence/static.html").read_bytes()
    digest = hashlib.sha256(content).hexdigest()
    for capture in dataset.captures:
        if not isinstance(capture, CapturedManifest):
            continue
        assert capture.content_sha256 == digest
        artifact = storage_root / capture.storage_reference
        artifact.parent.mkdir(parents=True, exist_ok=True)
        artifact.write_bytes(content)
    return storage_root
