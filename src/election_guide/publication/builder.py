"""Build deterministic exports and one shared publication view model."""

from __future__ import annotations

import csv
import hashlib
import io
import os
import shutil
import tempfile
from dataclasses import dataclass
from fractions import Fraction
from pathlib import Path
from typing import Literal, cast

from pydantic import BaseModel

from election_guide.evidence.models import CapturedManifest, CaptureManifest
from election_guide.evidence.storage import verify_capture
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
from election_guide.publication.models import (
    BuildManifest,
    CellState,
    GradeLegendItem,
    ProvenanceManifest,
    PublicationAlternative,
    PublicationCategoryAnalysis,
    PublicationCategoryCandidateSupport,
    PublicationChoiceEndorsements,
    PublicationComparison,
    PublicationEndorser,
    PublicationMetadata,
    PublicationMethodology,
    PublicationRace,
    PublicationSection,
    PublicationSource,
    PublicationViewModel,
    SourceCategoryGroup,
    SourceCell,
    SourceOverlapGroup,
    ValidationCheck,
    ValidationReport,
)
from election_guide.scoring.models import ConsensusReport, RaceConsensus
from election_guide.serialization import canonical_json_bytes
from election_guide.sources.models import Source

ARTIFACT_NAMES = (
    "consensus.json",
    "publication_view_model.json",
    "race_summary.csv",
    "endorsement_records.csv",
    "source_metadata.csv",
    "unresolved_review_items.csv",
    "source_matrix.csv",
    "validation_report.json",
    "provenance_manifest.json",
    "build_manifest.json",
)

CATEGORY_LABELS = {
    "progressive_general": "Progressive editorial and general",
    "democratic_party": "Democratic Party",
    "transportation_urbanism": "Transportation and urbanism",
    "environmental": "Environment",
    "labor": "Labor",
    "rights_representation": "Rights and representation",
    "comparison": "Centrist comparison",
}

SECTION_ORDER = (
    ("federal", "Federal"),
    ("statewide", "Statewide"),
    ("state-legislature", "State Legislature"),
    ("king-county", "King County"),
    ("judicial", "Judicial"),
    ("seattle", "Seattle"),
    ("other", "Other"),
)


@dataclass(frozen=True)
class PublicationBundle:
    """A fully computed bundle whose bytes can be written without further policy logic."""

    artifacts: dict[str, bytes]
    view_model: PublicationViewModel
    validation_report: ValidationReport
    provenance_manifest: ProvenanceManifest
    build_manifest: BuildManifest


def build_publication_bundle(
    dataset: CanonicalDataset,
    consensus: ConsensusReport,
    *,
    git_commit: str,
    snapshot_root: Path,
) -> PublicationBundle:
    """Compute every issue-7 artifact from canonical data and one consensus report."""
    stripped_commit = git_commit.strip()
    if not stripped_commit:
        raise ValueError("git_commit must not be blank")
    for capture in dataset.captures:
        verify_capture(capture, snapshot_root)
    validated_consensus = ConsensusReport.model_validate(
        consensus.model_dump(mode="json"),
        context={"canonical_dataset": dataset},
    )
    effective = dataset.effective_records()
    unresolved = _unresolved_reviews(dataset, effective)
    view_model = _build_view_model(
        dataset,
        validated_consensus,
        effective,
        unresolved,
        stripped_commit,
    )
    checks = _validate_publication(dataset, validated_consensus, view_model)
    validation_report = ValidationReport(
        election_id=dataset.inventory.election.id,
        generated_at=validated_consensus.computed_at,
        passed=all(check.passed for check in checks),
        checks=checks,
    )
    if not validation_report.passed:
        failures = ", ".join(check.id for check in checks if not check.passed)
        raise ValueError(f"publication validation failed: {failures}")

    consensus_bytes = canonical_json_bytes(validated_consensus.model_dump(mode="json"))
    configuration_hashes = {
        "election_inventory": _hash_model(dataset.inventory),
        "source_registry": _hash_model(dataset.source_registry),
        "scoring": _hash_model(validated_consensus.scoring_configuration),
    }
    snapshot_hashes = _snapshot_hashes(dataset)
    normalized_hash = _normalized_hash(dataset, effective)
    provenance_manifest = ProvenanceManifest(
        election_id=dataset.inventory.election.id,
        generated_at=validated_consensus.computed_at,
        configuration_hashes=configuration_hashes,
        input_snapshot_hashes=snapshot_hashes,
        normalized_data_hash=normalized_hash,
        consensus_output_hash=_sha256(consensus_bytes),
        dataset_hash=validated_consensus.dataset_hash,
    )

    artifacts = {
        "consensus.json": consensus_bytes,
        "publication_view_model.json": canonical_json_bytes(view_model.model_dump(mode="json")),
        "race_summary.csv": _race_summary_csv(dataset, validated_consensus, view_model),
        "endorsement_records.csv": _endorsement_csv(dataset, effective),
        "source_metadata.csv": _source_csv(dataset),
        "unresolved_review_items.csv": _review_csv(unresolved),
        "source_matrix.csv": _matrix_csv(view_model),
        "validation_report.json": canonical_json_bytes(validation_report.model_dump(mode="json")),
        "provenance_manifest.json": canonical_json_bytes(
            provenance_manifest.model_dump(mode="json")
        ),
    }
    active_sources = [
        source for source in dataset.source_registry.sources if source.panel_role != "excluded"
    ]
    build_manifest = BuildManifest(
        election_id=dataset.inventory.election.id,
        generated_at=validated_consensus.computed_at,
        git_commit=stripped_commit,
        configuration_hash=_sha256(canonical_json_bytes(configuration_hashes)),
        input_snapshot_hashes=snapshot_hashes,
        normalized_data_hash=normalized_hash,
        consensus_output_hash=_sha256(consensus_bytes),
        artifact_hashes={name: _sha256(content) for name, content in sorted(artifacts.items())},
        source_count=len(active_sources),
        race_count=len(dataset.inventory.races),
        published_race_count=len(validated_consensus.races),
        unresolved_review_count=len(unresolved),
        warnings=sorted(
            {warning.code for race in validated_consensus.races for warning in race.warnings}
        ),
    )
    artifacts["build_manifest.json"] = canonical_json_bytes(build_manifest.model_dump(mode="json"))
    if set(artifacts) != set(ARTIFACT_NAMES):
        raise ValueError("publication artifact set does not match the canonical bundle")
    return PublicationBundle(
        artifacts=artifacts,
        view_model=view_model,
        validation_report=validation_report,
        provenance_manifest=provenance_manifest,
        build_manifest=build_manifest,
    )


def write_publication_bundle(bundle: PublicationBundle, output_dir: Path) -> list[Path]:
    """Stage and replace one dedicated output directory as a complete generation."""
    parent = output_dir.parent
    parent.mkdir(parents=True, exist_ok=True)
    if output_dir.is_symlink():
        raise ValueError("publication output path cannot be a symbolic link")
    if output_dir.exists():
        if not output_dir.is_dir():
            raise ValueError("publication output path must be a directory")
        unexpected = sorted(
            path.name for path in output_dir.iterdir() if path.name not in ARTIFACT_NAMES
        )
        if unexpected:
            raise ValueError(
                "publication output directory contains non-bundle entries: " + ", ".join(unexpected)
            )

    stage: Path | None = Path(tempfile.mkdtemp(prefix=f".{output_dir.name}.staging-", dir=parent))
    backup: Path | None = None
    if os.name != "nt":
        stage.chmod(0o755)
    try:
        for name in ARTIFACT_NAMES:
            _atomic_write(stage / name, bundle.artifacts[name])
        if output_dir.exists():
            backup = Path(tempfile.mkdtemp(prefix=f".{output_dir.name}.previous-", dir=parent))
            backup.rmdir()
            os.replace(output_dir, backup)
        try:
            os.replace(stage, output_dir)
            stage = None
        except OSError:
            if backup is not None:
                os.replace(backup, output_dir)
                backup = None
            raise
        if backup is not None:
            shutil.rmtree(backup, ignore_errors=True)
            backup = None
    finally:
        if stage is not None and stage.exists():
            shutil.rmtree(stage, ignore_errors=True)
        if backup is not None and backup.exists() and not output_dir.exists():
            os.replace(backup, output_dir)
    return [output_dir / name for name in ARTIFACT_NAMES]


def _build_view_model(
    dataset: CanonicalDataset,
    consensus: ConsensusReport,
    effective: dict[str, BaseModel],
    unresolved: list[ReviewItem],
    git_commit: str,
) -> PublicationViewModel:
    active_sources = [
        source for source in dataset.source_registry.sources if source.panel_role != "excluded"
    ]
    active_source_ids = {source.id for source in active_sources}
    captured_source_ids = {
        capture.source_id for capture in dataset.captures if capture.source_id in active_source_ids
    }
    published_overlap_group_ids = {
        group.id
        for group in dataset.source_registry.overlap_groups
        if len(set(group.member_ids) & active_source_ids) > 1
    }
    result_by_race = {result.race_id: result for result in consensus.races}
    effective_endorsements = [
        cast(NormalizedEndorsement, effective[item.id]) for item in dataset.endorsements
    ]
    endorsements = {(item.source_id, item.race_id): item for item in effective_endorsements}
    claims = {item.id: cast(ExtractedClaim, effective[item.id]) for item in dataset.claims}
    capture_by_id = {capture.id: capture for capture in dataset.captures}
    jurisdiction_by_id = {
        jurisdiction.id: jurisdiction for jurisdiction in dataset.inventory.jurisdictions
    }
    section_races: dict[str, list[PublicationRace]] = {
        section_id: [] for section_id, _ in SECTION_ORDER
    }
    for race in dataset.inventory.races:
        if not race.publication_eligible:
            continue
        result = result_by_race[race.id]
        section_id, section_label = _section(race, jurisdiction_by_id[race.jurisdiction_id].kind)
        choices = {choice.id: choice.display_name for choice in race.choices}
        leader_labels = [choices[candidate_id] for candidate_id in result.winner_candidate_ids]
        has_recommendation = result.grade != "Insufficient"
        recommendation_ids = result.winner_candidate_ids if has_recommendation else []
        recommendation_labels = leader_labels if has_recommendation else []
        cells = [
            _source_cell(
                source,
                race,
                endorsements.get((source.id, race.id)),
                claims,
                capture_by_id,
                choices,
                dataset,
            )
            for source in active_sources
        ]
        percentage_whole = _percentage_whole(result.winner_share)
        publication_race = PublicationRace(
            id=race.id,
            section_id=section_id,
            section_label=section_label,
            jurisdiction_id=race.jurisdiction_id,
            race_label=race.display_name,
            filter_tokens=sorted(
                {
                    section_id,
                    race.jurisdiction_id,
                    jurisdiction_by_id[race.jurisdiction_id].kind,
                    race.district,
                }
            ),
            support_leader_candidate_ids=result.winner_candidate_ids,
            support_leader_candidate_labels=leader_labels,
            support_leader_label=(" / ".join(leader_labels) if leader_labels else "No leader"),
            recommendation_candidate_ids=recommendation_ids,
            recommendation_candidate_labels=recommendation_labels,
            recommendation_label=(
                "Too few endorsements"
                if not has_recommendation
                else "No consensus"
                if not recommendation_labels
                else " / ".join(recommendation_labels)
                if result.is_tied
                else recommendation_labels[0]
            ),
            grade=result.grade,
            winner_share=None if result.winner_share is None else str(result.winner_share),
            percentage_label=("—" if percentage_whole is None else f"{percentage_whole}%"),
            percentage_whole=percentage_whole,
            support_summary=_support_summary(result.explicit_endorsement_count),
            explicit_endorsement_count=result.explicit_endorsement_count,
            eligible_source_count=result.eligible_source_count,
            source_coverage_count=result.source_coverage_count,
            category_coverage_count=result.category_coverage_count,
            no_endorsement_count=result.no_endorsement_count,
            missing_source_count=result.missing_source_count,
            endorsement_groups=_endorsement_groups(cells, active_sources),
            category_breakdown=[
                PublicationCategoryAnalysis(
                    category=item.category,
                    label=CATEGORY_LABELS[item.category],
                    eligible_source_count=item.eligible_source_count,
                    source_coverage_count=item.source_coverage_count,
                    explicit_endorsement_count=item.explicit_endorsement_count,
                    candidate_support=[
                        PublicationCategoryCandidateSupport(
                            candidate_id=candidate_id,
                            candidate_label=choices[candidate_id],
                            support_points=str(points),
                        )
                        for candidate_id, points in sorted(item.candidate_support.items())
                    ],
                )
                for item in result.category_breakdown
            ],
            alternatives=[
                PublicationAlternative(
                    candidate_id=item.candidate_id,
                    candidate_label=choices[item.candidate_id],
                    support_points=str(item.support_points),
                    share=str(item.share),
                    percentage_label=f"{_percentage_whole(item.share)}%",
                )
                for item in result.notable_alternatives
            ],
            comparisons=[
                PublicationComparison(
                    source_id=item.source_id,
                    status=item.status,
                    badge_label=_comparison_badge(item.status),
                    candidate_ids=item.candidate_ids,
                    candidate_labels=[choices[candidate_id] for candidate_id in item.candidate_ids],
                )
                for item in result.comparison_results
            ],
            warning_codes=[warning.code for warning in result.warnings],
            warning_messages=[warning.message for warning in result.warnings],
            source_cells=cells,
        )
        section_races[section_id].append(publication_race)
    sections = [
        PublicationSection(id=section_id, label=label, races=section_races[section_id])
        for section_id, label in SECTION_ORDER
        if section_races[section_id]
    ]
    published_cells = [
        cell for section in sections for race in section.races for cell in race.source_cells
    ]
    sources = [
        PublicationSource(
            id=source.id,
            name=source.name,
            category=source.category,
            panel_role=cast(Literal["consensus", "comparison"], source.panel_role),
            organization_url=source.organization_url,
            evidence_url=source.discovery.canonical_url or source.discovery.requested_url,
            overlap_group_ids=sorted(set(source.overlap_group_ids) & published_overlap_group_ids),
            endorsement_count=sum(
                cell.source_id == source.id and cell.state in {"endorsement", "multi_endorsement"}
                for cell in published_cells
            ),
            split_endorsement_count=sum(
                cell.source_id == source.id and cell.state == "multi_endorsement"
                for cell in published_cells
            ),
        )
        for source in active_sources
    ]
    return PublicationViewModel(
        metadata=PublicationMetadata(
            election_id=dataset.inventory.election.id,
            election_name=dataset.inventory.election.name,
            election_date=dataset.inventory.election.election_date.isoformat(),
            generated_at=consensus.computed_at,
            data_version=consensus.input_hash[:12],
            git_commit=git_commit,
            source_count=len(active_sources),
            captured_source_count=len(captured_source_ids),
            unavailable_source_count=len(active_source_ids - captured_source_ids),
            race_count=len(dataset.inventory.races),
            published_race_count=len(consensus.races),
            unresolved_review_count=len(unresolved),
        ),
        sources=sources,
        sections=sections,
        methodology=_methodology(dataset, consensus),
    )


def _source_cell(
    source: Source,
    race: Race,
    endorsement: NormalizedEndorsement | None,
    claims: dict[str, ExtractedClaim],
    captures: dict[str, CaptureManifest],
    choices: dict[str, str],
    dataset: CanonicalDataset,
) -> SourceCell:
    if race.id not in eligible_race_ids(source.id, dataset.inventory, dataset.source_registry):
        return SourceCell(
            source_id=source.id,
            state="not_applicable",
            candidate_ids=[],
            candidate_labels=[],
            allocation={},
            evidence_url=None,
            evidence_locator=None,
            confidence_warning=False,
        )
    if endorsement is None:
        return SourceCell(
            source_id=source.id,
            state="not_covered",
            candidate_ids=[],
            candidate_labels=[],
            allocation={},
            evidence_url=None,
            evidence_locator=None,
            confidence_warning=False,
        )
    claim = claims[endorsement.extracted_claim_id]
    capture = captures[endorsement.source_capture_id]
    canonical_url = capture.canonical_url
    requested_url = capture.requested_url
    state = _cell_state(endorsement.status)
    candidate_ids = endorsement.candidate_ids if endorsement.status in EXPLICIT_STATUSES else []
    return SourceCell(
        source_id=source.id,
        state=state,
        candidate_ids=candidate_ids,
        candidate_labels=[choices[candidate_id] for candidate_id in candidate_ids],
        allocation={
            candidate_id: str(points) for candidate_id, points in endorsement.allocation.items()
        },
        evidence_url=canonical_url or requested_url,
        evidence_locator=claim.evidence_locator,
        confidence_warning=(
            endorsement.normalization_confidence < 1
            or claim.extraction_confidence < 1
            or claim.requires_review
        ),
    )


def _support_summary(explicit_endorsement_count: int) -> str:
    noun = "source" if explicit_endorsement_count == 1 else "sources"
    return f"Based on {explicit_endorsement_count} explicitly endorsing {noun}"


def _endorsement_groups(
    cells: list[SourceCell], sources: list[PublicationSource] | list[Source]
) -> list[PublicationChoiceEndorsements]:
    source_by_id = {source.id: source for source in sources}
    support: dict[str, Fraction] = {}
    labels: dict[str, str] = {}
    endorsers: dict[str, list[PublicationEndorser]] = {}
    for cell in cells:
        source = source_by_id[cell.source_id]
        if source.panel_role != "consensus" or cell.state not in {
            "endorsement",
            "multi_endorsement",
        }:
            continue
        if cell.evidence_url is None or cell.evidence_locator is None:
            raise ValueError("affirmative endorsement cells require evidence")
        for candidate_id, candidate_label in zip(
            cell.candidate_ids, cell.candidate_labels, strict=True
        ):
            labels[candidate_id] = candidate_label
            support[candidate_id] = support.get(candidate_id, Fraction()) + Fraction(
                cell.allocation[candidate_id]
            )
            endorsers.setdefault(candidate_id, []).append(
                PublicationEndorser(
                    source_id=cell.source_id,
                    source_name=source.name,
                    evidence_url=cell.evidence_url,
                    evidence_locator=cell.evidence_locator,
                    co_endorsement=cell.state == "multi_endorsement",
                    confidence_warning=cell.confidence_warning,
                )
            )
    return [
        PublicationChoiceEndorsements(
            candidate_id=candidate_id,
            candidate_label=labels[candidate_id],
            support_points=str(support[candidate_id]),
            source_count=len(endorsers[candidate_id]),
            endorsers=endorsers[candidate_id],
        )
        for candidate_id in sorted(support, key=lambda item: (-support[item], item))
    ]


def _methodology(dataset: CanonicalDataset, consensus: ConsensusReport) -> PublicationMethodology:
    grade_legend: list[GradeLegendItem] = []
    for rule in consensus.scoring_configuration.grades:
        minimum = _percentage_whole(rule.minimum_share)
        source_rule = (
            f" and at least {rule.minimum_explicit_sources} explicit sources"
            if rule.minimum_explicit_sources is not None
            else ""
        )
        grade_legend.append(
            GradeLegendItem(
                grade=rule.grade,
                rule=f"At least {minimum}%{source_rule}",
            )
        )
    active_sources = [
        source for source in dataset.source_registry.sources if source.panel_role != "excluded"
    ]
    active_source_ids = {source.id for source in active_sources}
    categories = list(dict.fromkeys(source.category for source in active_sources))
    return PublicationMethodology(
        process_steps=[
            "Collect official endorsements",
            "Preserve source evidence",
            "Normalize races and candidates",
            "Split multi-candidate endorsements exactly",
            "Compute progressive consensus",
            "Compare separately with the Seattle Times",
        ],
        grade_legend=[
            GradeLegendItem(
                grade="TIED",
                rule="Multiple choices share the greatest exact support",
            ),
            GradeLegendItem(
                grade="Insufficient",
                rule=(
                    f"Fewer than {consensus.scoring_configuration.minimum_explicit_sources} "
                    "explicit progressive sources"
                ),
            ),
            *grade_legend,
        ],
        source_categories=[
            SourceCategoryGroup(
                category=category,
                label=CATEGORY_LABELS[category],
                source_ids=[source.id for source in active_sources if source.category == category],
            )
            for category in categories
        ],
        source_overlap_groups=[
            SourceOverlapGroup(
                id=group.id,
                label=group.label,
                description=group.description,
                relationship="possible_overlap",
                source_ids=sorted(
                    source_id for source_id in group.member_ids if source_id in active_source_ids
                ),
            )
            for group in sorted(dataset.source_registry.overlap_groups, key=lambda item: item.id)
            if len(set(group.member_ids) & active_source_ids) > 1
        ],
        default_aggregation_view="source_level",
        deduplicated_view="not_computed",
        interpretation_notes=[
            "Agreement is measured only among explicitly endorsing eligible sources.",
            "No endorsement and missing coverage remain visible but do not enter the denominator.",
            (
                "Each legislative-district organization counts independently on broader "
                "Seattle-ballot races it explicitly covers, but only on its own district's "
                "legislative contests. Their shared party network remains disclosed."
            ),
            "The Seattle Times is a separate comparison, never an extra progressive vote.",
            "Category representation and category support remain available in audit exports.",
        ],
        limitations=[
            "This guide aggregates endorsements; it is not independent candidate vetting.",
            "Some organizations have disclosed overlap, but raw source totals are preserved.",
            (
                "Possible overlap is not deduplicated because the registry does not establish "
                "statistical dependence or a shared decision process."
            ),
            "Organizations may update endorsements after the captured evidence date.",
            "The exact ballot available to a voter depends on their registration address.",
        ],
        verification_instructions=(
            "Verify any displayed value against consensus.json, endorsement_records.csv, "
            "and the evidence URL and locator in the source cell."
        ),
    )


def _validate_publication(
    dataset: CanonicalDataset,
    consensus: ConsensusReport,
    view_model: PublicationViewModel,
) -> list[ValidationCheck]:
    view_races = [race for section in view_model.sections for race in section.races]
    view_by_id = {race.id: race for race in view_races}
    consensus_by_id = {race.race_id: race for race in consensus.races}
    inventory_by_id = {race.id: race for race in dataset.inventory.races}
    active_sources = [
        source for source in dataset.source_registry.sources if source.panel_role != "excluded"
    ]
    active_source_ids = [source.id for source in active_sources]
    captured_source_ids = {
        capture.source_id for capture in dataset.captures if capture.source_id in active_source_ids
    }
    values_match = all(
        _view_race_matches(view_by_id[race_id], result, inventory_by_id[race_id])
        for race_id, result in consensus_by_id.items()
    )
    cell_sources_match = all(
        [cell.source_id for cell in race.source_cells] == active_source_ids for race in view_races
    )
    effective = dataset.effective_records()
    endorsements = {
        (item.source_id, item.race_id): item
        for item in (
            cast(NormalizedEndorsement, effective[record.id]) for record in dataset.endorsements
        )
    }
    claims = {item.id: cast(ExtractedClaim, effective[item.id]) for item in dataset.claims}
    capture_by_id = {capture.id: capture for capture in dataset.captures}
    canonical_evidence_match = True
    for view_race in view_races:
        inventory_race = inventory_by_id[view_race.id]
        choices = {choice.id: choice.display_name for choice in inventory_race.choices}
        expected_cells = [
            _source_cell(
                source,
                inventory_race,
                endorsements.get((source.id, inventory_race.id)),
                claims,
                capture_by_id,
                choices,
                dataset,
            )
            for source in active_sources
        ]
        if (
            view_race.source_cells != expected_cells
            or view_race.endorsement_groups != _endorsement_groups(expected_cells, active_sources)
        ):
            canonical_evidence_match = False
            break
    metadata_match = (
        view_model.metadata.election_id == dataset.inventory.election.id
        and view_model.metadata.election_name == dataset.inventory.election.name
        and view_model.metadata.election_date
        == dataset.inventory.election.election_date.isoformat()
        and view_model.metadata.generated_at == consensus.computed_at
        and view_model.metadata.data_version == consensus.input_hash[:12]
        and view_model.metadata.source_count == len(active_source_ids)
        and view_model.metadata.captured_source_count == len(captured_source_ids)
        and view_model.metadata.unavailable_source_count
        == len(active_source_ids) - len(captured_source_ids)
        and view_model.metadata.race_count == len(dataset.inventory.races)
        and view_model.metadata.published_race_count == len(consensus.races)
    )
    checks = [
        ValidationCheck(
            id="authoritative-consensus",
            passed=True,
            message="Consensus report revalidated by full recomputation from canonical data.",
        ),
        ValidationCheck(
            id="publication-scope",
            passed=set(view_by_id) == set(consensus_by_id)
            and len(view_races) == len(consensus.races),
            message="View model contains every publication-eligible consensus race exactly once.",
        ),
        ValidationCheck(
            id="display-values",
            passed=values_match,
            message=(
                "View-model grades, shares, winners, counts, comparisons, and warnings "
                "match consensus."
            ),
        ),
        ValidationCheck(
            id="source-matrix",
            passed=cell_sources_match,
            message="Every race contains one ordered cell for every active source.",
        ),
        ValidationCheck(
            id="canonical-evidence",
            passed=canonical_evidence_match,
            message=(
                "Source cells and candidate endorsement groups match canonical records exactly."
            ),
        ),
        ValidationCheck(
            id="publication-metadata",
            passed=metadata_match,
            message="Publication metadata matches canonical election and consensus inputs.",
        ),
    ]
    return checks


def _view_race_matches(view: PublicationRace, result: RaceConsensus, race: Race) -> bool:
    choices = {choice.id: choice.display_name for choice in race.choices}
    expected_recommendation = [] if result.grade == "Insufficient" else result.winner_candidate_ids
    leader_labels = [choices[candidate_id] for candidate_id in result.winner_candidate_ids]
    recommendation_labels = [choices[candidate_id] for candidate_id in expected_recommendation]
    expected_recommendation_label = (
        "Too few endorsements"
        if result.grade == "Insufficient"
        else "No consensus"
        if not recommendation_labels
        else " / ".join(recommendation_labels)
        if result.is_tied
        else recommendation_labels[0]
    )
    percentage_whole = _percentage_whole(result.winner_share)
    return (
        view.race_label == race.display_name
        and view.jurisdiction_id == race.jurisdiction_id
        and view.support_leader_candidate_ids == result.winner_candidate_ids
        and view.support_leader_candidate_labels == leader_labels
        and view.support_leader_label
        == (" / ".join(leader_labels) if leader_labels else "No leader")
        and view.recommendation_candidate_ids == expected_recommendation
        and view.recommendation_candidate_labels == recommendation_labels
        and view.recommendation_label == expected_recommendation_label
        and view.grade == result.grade
        and view.winner_share == (None if result.winner_share is None else str(result.winner_share))
        and view.percentage_whole == percentage_whole
        and view.percentage_label == ("—" if percentage_whole is None else f"{percentage_whole}%")
        and view.support_summary == _support_summary(result.explicit_endorsement_count)
        and view.explicit_endorsement_count == result.explicit_endorsement_count
        and view.eligible_source_count == result.eligible_source_count
        and view.source_coverage_count == result.source_coverage_count
        and view.category_coverage_count == result.category_coverage_count
        and view.no_endorsement_count == result.no_endorsement_count
        and view.missing_source_count == result.missing_source_count
        and [
            (
                item.source_id,
                item.status,
                item.candidate_ids,
                item.candidate_labels,
                item.badge_label,
            )
            for item in view.comparisons
        ]
        == [
            (
                item.source_id,
                item.status,
                item.candidate_ids,
                [choices[candidate_id] for candidate_id in item.candidate_ids],
                _comparison_badge(item.status),
            )
            for item in result.comparison_results
        ]
        and [
            (
                item.candidate_id,
                item.candidate_label,
                item.support_points,
                item.share,
                item.percentage_label,
            )
            for item in view.alternatives
        ]
        == [
            (
                item.candidate_id,
                choices[item.candidate_id],
                str(item.support_points),
                str(item.share),
                f"{_percentage_whole(item.share)}%",
            )
            for item in result.notable_alternatives
        ]
        and view.warning_codes == [item.code for item in result.warnings]
        and view.warning_messages == [item.message for item in result.warnings]
    )


def _race_summary_csv(
    dataset: CanonicalDataset,
    consensus: ConsensusReport,
    view_model: PublicationViewModel,
) -> bytes:
    rows: list[dict[str, str]] = []
    for section in view_model.sections:
        for race in section.races:
            result = next(item for item in consensus.races if item.race_id == race.id)
            rows.append(
                {
                    "race_id": race.id,
                    "section": section.label,
                    "race_name": race.race_label,
                    "jurisdiction_id": race.jurisdiction_id,
                    "support_leader_candidate_ids": "|".join(race.support_leader_candidate_ids),
                    "support_leader_names": "|".join(
                        _choice_labels(dataset, race.id, race.support_leader_candidate_ids)
                    ),
                    "recommendation_candidate_ids": "|".join(race.recommendation_candidate_ids),
                    "recommendation_names": "|".join(
                        _choice_labels(dataset, race.id, race.recommendation_candidate_ids)
                    ),
                    "grade": race.grade,
                    "winner_share": race.winner_share or "",
                    "percentage_label": race.percentage_label,
                    "eligible_source_count": str(race.eligible_source_count),
                    "explicit_endorsement_count": str(race.explicit_endorsement_count),
                    "no_endorsement_count": str(race.no_endorsement_count),
                    "missing_source_count": str(race.missing_source_count),
                    "comparison_status": "|".join(item.status for item in race.comparisons),
                    "comparison_candidate_ids": "|".join(
                        candidate_id
                        for item in result.comparison_results
                        for candidate_id in item.candidate_ids
                    ),
                    "warning_codes": "|".join(race.warning_codes),
                    "input_hash": consensus.input_hash,
                }
            )
    return _csv_bytes(rows)


def _endorsement_csv(dataset: CanonicalDataset, effective: dict[str, BaseModel]) -> bytes:
    race_order = {race.id: index for index, race in enumerate(dataset.inventory.races)}
    source_order = {
        source.id: index for index, source in enumerate(dataset.source_registry.sources)
    }
    rows: list[dict[str, str]] = []
    endorsements = sorted(
        (cast(NormalizedEndorsement, effective[item.id]) for item in dataset.endorsements),
        key=lambda item: (race_order[item.race_id], source_order[item.source_id]),
    )
    for item in endorsements:
        claim = cast(ExtractedClaim, effective[item.extracted_claim_id])
        capture = next(
            capture for capture in dataset.captures if capture.id == item.source_capture_id
        )
        rows.append(
            {
                "endorsement_id": item.id,
                "race_id": item.race_id,
                "source_id": item.source_id,
                "status": item.status,
                "cell_state": _cell_state(item.status),
                "candidate_ids": "|".join(item.candidate_ids),
                "allocation": "|".join(
                    f"{candidate_id}={item.allocation[candidate_id]}"
                    for candidate_id in item.candidate_ids
                ),
                "published_at": "" if item.published_at is None else item.published_at.isoformat(),
                "capture_id": item.source_capture_id,
                "claim_id": item.extracted_claim_id,
                "evidence_url": capture.canonical_url or capture.requested_url,
                "evidence_locator": claim.evidence_locator,
                "extraction_confidence": str(claim.extraction_confidence),
                "normalization_confidence": str(item.normalization_confidence),
                "manually_verified": str(item.manually_verified).lower(),
                "review_item_id": item.review_item_id or "",
            }
        )
    return _csv_bytes(rows, fieldnames=_endorsement_fields())


def _source_csv(dataset: CanonicalDataset) -> bytes:
    rows = [
        {
            "source_id": source.id,
            "name": source.name,
            "category": source.category,
            "panel_role": source.panel_role,
            "panel_reason": source.panel_reason,
            "organization_url": source.organization_url,
            "evidence_url": source.discovery.canonical_url or source.discovery.requested_url,
            "discovery_status": source.discovery.status,
            "checked_at": source.discovery.checked_at.isoformat(),
            "eligibility_kind": source.eligibility.kind,
            "jurisdiction_ids": "|".join(source.eligibility.jurisdiction_ids),
            "overlap_group_ids": "|".join(source.overlap_group_ids),
            "publisher_id": source.publisher_id or "",
        }
        for source in dataset.source_registry.sources
    ]
    return _csv_bytes(rows)


def _review_csv(unresolved: list[ReviewItem]) -> bytes:
    rows = [
        {
            "review_item_id": item.id,
            "claim_id": item.claim_id,
            "severity": item.severity,
            "reason": item.reason,
            "summary": item.summary,
            "race_status": "" if item.race_match is None else item.race_match.status,
            "race_ids": ""
            if item.race_match is None
            else "|".join(candidate.record_id for candidate in item.race_match.candidates),
            "candidate_status": "" if item.candidate_match is None else item.candidate_match.status,
            "candidate_ids": ""
            if item.candidate_match is None
            else "|".join(candidate.record_id for candidate in item.candidate_match.candidates),
            "capture_id": item.capture_id,
            "evidence_locator": item.evidence_locator,
            "created_at": item.created_at.isoformat(),
        }
        for item in unresolved
    ]
    return _csv_bytes(rows, fieldnames=_review_fields())


def _matrix_csv(view_model: PublicationViewModel) -> bytes:
    source_ids = [source.id for source in view_model.sources]
    fieldnames = ["race_id", "race_name", *source_ids]
    rows: list[dict[str, str]] = []
    for section in view_model.sections:
        for race in section.races:
            cell_by_source = {cell.source_id: cell for cell in race.source_cells}
            row = {"race_id": race.id, "race_name": race.race_label}
            row.update(
                {source_id: _matrix_cell(cell_by_source[source_id]) for source_id in source_ids}
            )
            rows.append(row)
    return _csv_bytes(rows, fieldnames=fieldnames)


def _unresolved_reviews(
    dataset: CanonicalDataset,
    effective: dict[str, BaseModel],
) -> list[ReviewItem]:
    decided = {
        cast(ReviewDecision, effective[item.id]).review_item_id for item in dataset.review_decisions
    }
    return sorted(
        (
            cast(ReviewItem, effective[item.id])
            for item in dataset.review_items
            if item.id not in decided
        ),
        key=lambda item: item.id,
    )


def _snapshot_hashes(dataset: CanonicalDataset) -> dict[str, str]:
    return {
        capture.id: (
            capture.content_sha256
            if isinstance(capture, CapturedManifest)
            else _hash_model(capture)
        )
        for capture in sorted(dataset.captures, key=lambda item: item.id)
    }


def _normalized_hash(dataset: CanonicalDataset, effective: dict[str, BaseModel]) -> str:
    payload = {
        "claims": [effective[item.id].model_dump(mode="json") for item in dataset.claims],
        "endorsements": [
            effective[item.id].model_dump(mode="json") for item in dataset.endorsements
        ],
        "review_items": [
            effective[item.id].model_dump(mode="json") for item in dataset.review_items
        ],
        "review_decisions": [
            effective[item.id].model_dump(mode="json") for item in dataset.review_decisions
        ],
        "overrides": [item.model_dump(mode="json") for item in dataset.overrides],
    }
    return _sha256(canonical_json_bytes(payload))


def _section(race: Race, jurisdiction_kind: str) -> tuple[str, str]:
    office = race.office.casefold()
    if "judge" in office or "justice" in office or "court" in office:
        return "judicial", "Judicial"
    if jurisdiction_kind == "congressional_district":
        return "federal", "Federal"
    if jurisdiction_kind == "state":
        return "statewide", "Statewide"
    if jurisdiction_kind == "legislative_district":
        return "state-legislature", "State Legislature"
    if jurisdiction_kind in {"county", "county_council_district"}:
        return "king-county", "King County"
    if jurisdiction_kind in {"city", "city_council_district"}:
        return "seattle", "Seattle"
    return "other", "Other"


def _cell_state(status: str) -> CellState:
    states: dict[str, CellState] = {
        "endorsed": "endorsement",
        "dual_endorsement": "multi_endorsement",
        "multiple_endorsement": "multi_endorsement",
        "no_endorsement": "no_endorsement",
        "declined_to_endorse": "no_endorsement",
        "not_covered": "not_covered",
        "not_published": "not_covered",
        "source_unavailable": "unavailable",
        "unverified": "unverified",
        "ambiguous": "unverified",
    }
    return states[status]


def _comparison_badge(status: str) -> str:
    return {
        "agrees": "AGREES",
        "differs": "DIFFERENT PICK",
        "no_endorsement": "NO PICK",
        "not_covered": "NOT COVERED",
        "no_consensus": "NO PROGRESSIVE CONSENSUS",
    }[status]


def _matrix_cell(cell: SourceCell) -> str:
    if cell.candidate_ids:
        return f"{cell.state}:{'|'.join(cell.candidate_ids)}"
    return cell.state


def _percentage_whole(share: Fraction | None) -> int | None:
    if share is None:
        return None
    scaled = share * 100
    return (scaled.numerator * 2 + scaled.denominator) // (2 * scaled.denominator)


def _choice_labels(dataset: CanonicalDataset, race_id: str, candidate_ids: list[str]) -> list[str]:
    race = next(item for item in dataset.inventory.races if item.id == race_id)
    labels = {choice.id: choice.display_name for choice in race.choices}
    return [labels[candidate_id] for candidate_id in candidate_ids]


def _csv_bytes(
    rows: list[dict[str, str]],
    *,
    fieldnames: list[str] | None = None,
) -> bytes:
    selected_fields = fieldnames or (list(rows[0]) if rows else [])
    if not selected_fields:
        raise ValueError("empty CSV export requires explicit field names")
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(
        stream,
        fieldnames=selected_fields,
        extrasaction="raise",
        lineterminator="\n",
    )
    writer.writeheader()
    writer.writerows(rows)
    return stream.getvalue().encode("utf-8")


def _endorsement_fields() -> list[str]:
    return [
        "endorsement_id",
        "race_id",
        "source_id",
        "status",
        "cell_state",
        "candidate_ids",
        "allocation",
        "published_at",
        "capture_id",
        "claim_id",
        "evidence_url",
        "evidence_locator",
        "extraction_confidence",
        "normalization_confidence",
        "manually_verified",
        "review_item_id",
    ]


def _review_fields() -> list[str]:
    return [
        "review_item_id",
        "claim_id",
        "severity",
        "reason",
        "summary",
        "race_status",
        "race_ids",
        "candidate_status",
        "candidate_ids",
        "capture_id",
        "evidence_locator",
        "created_at",
    ]


def _hash_model(model: BaseModel) -> str:
    return _sha256(canonical_json_bytes(model.model_dump(mode="json")))


def _sha256(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def _atomic_write(path: Path, content: bytes) -> None:
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as temporary:
            temporary_path = Path(temporary.name)
            temporary.write(content)
            temporary.flush()
            os.fsync(temporary.fileno())
        if os.name != "nt":
            temporary_path.chmod(0o644)
        os.replace(temporary_path, path)
        temporary_path = None
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)
