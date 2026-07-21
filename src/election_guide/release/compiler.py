"""Compile reviewed, permitted source extracts into the canonical dataset."""

from __future__ import annotations

import hashlib
import os
import shutil
import tempfile
from fractions import Fraction
from pathlib import Path

import yaml
from pydantic import ValidationError

from election_guide.evidence.models import CaptureManifest, CaptureRequest
from election_guide.evidence.storage import read_capture_manifest, record_capture
from election_guide.inventory.importer import read_inventory
from election_guide.inventory.models import Inventory
from election_guide.normalization.matching import eligible_race_ids
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
    new_review_decision,
    new_review_item,
)
from election_guide.normalization.semantics import EndorsementStatus
from election_guide.release.models import ReleaseDecision, ReleaseLedger
from election_guide.serialization import canonical_json_bytes, read_yaml
from election_guide.sources.models import SourceRegistry
from election_guide.sources.registry import read_source_registry, validate_registry_inventory


def read_release_ledger(path: Path) -> ReleaseLedger:
    try:
        return ReleaseLedger.model_validate(read_yaml(path))
    except (OSError, yaml.YAMLError, ValidationError, ValueError) as error:
        raise ValueError(str(error)) from error


def compile_release_dataset(
    ledger_path: Path,
    inventory_path: Path,
    registry_path: Path,
    output_path: Path,
    snapshot_root: Path,
    manifest_dir: Path,
) -> CanonicalDataset:
    """Compile one audited ledger and atomically replace its generated evidence."""
    ledger = read_release_ledger(ledger_path)
    inventory = read_inventory(inventory_path)
    registry = read_source_registry(registry_path)
    validate_registry_inventory(registry, inventory)
    if ledger.election_id != inventory.election.id:
        raise ValueError("release ledger and inventory target different elections")

    _validate_ledger_references(ledger, inventory, registry)
    stage_parent = output_path.parent
    stage_parent.mkdir(parents=True, exist_ok=True)
    stage = Path(tempfile.mkdtemp(prefix=".release-compile-", dir=stage_parent))
    stage_snapshots = stage / "snapshots"
    stage_manifests = stage / "manifests"
    try:
        captures: list[CaptureManifest] = []
        claims: list[ExtractedClaim] = []
        endorsements: list[NormalizedEndorsement] = []
        review_items: list[ReviewItem] = []
        review_decisions: list[ReviewDecision] = []
        source_by_id = {source.id: source for source in registry.sources}
        race_by_id = {race.id: race for race in inventory.races}

        for source_extract in ledger.sources:
            source = source_by_id[source_extract.source_id]
            snapshot_payload = canonical_json_bytes(
                source_extract.model_dump(mode="json", exclude={"reviewed_at"})
            )
            snapshot_input = stage / f"{source.id}.json"
            snapshot_input.write_bytes(snapshot_payload)
            discovery = source.discovery
            request = CaptureRequest(
                source_id=source.id,
                requested_url=discovery.requested_url,
                canonical_url=discovery.canonical_url,
                redirect_chain=discovery.redirect_chain,
                retrieved_at=source_extract.captured_at,
                http_status=None,
                media_type="application/json",
                title=f"Permitted 2026 endorsement decision extract: {source.name}",
                published_at=discovery.published_at,
                updated_at=discovery.updated_at,
                capture_method="manual_upload",
                browser_required=False,
                redistribution="permitted",
                redistribution_note=(
                    "Structured factual decisions and short verification excerpts may be "
                    "redistributed; full third-party page content is excluded."
                ),
            )
            manifest_path = record_capture(
                request,
                snapshot_input,
                stage_snapshots,
                stage_manifests,
            )
            capture = read_capture_manifest(manifest_path)
            captures.append(capture)
            reviewed_at = source_extract.reviewed_at

            for decision in source_extract.decisions:
                race = race_by_id[decision.race_id]
                status = _normalized_status(decision)
                candidate_names = [
                    next(
                        choice.display_name for choice in race.choices if choice.id == candidate_id
                    )
                    for candidate_id in decision.candidate_ids
                ]
                raw_candidate_text = " and ".join(candidate_names) or None
                raw_status_text = _raw_status(decision)
                requires_review = len(decision.candidate_ids) > 1
                evidence_locator = decision.evidence_locator or source_extract.evidence_locator
                evidence_excerpt = decision.evidence_excerpt
                claim = new_extracted_claim(
                    capture_id=capture.id,
                    source_id=source.id,
                    raw_race_text=race.display_name,
                    raw_candidate_text=raw_candidate_text,
                    raw_status_text=raw_status_text,
                    raw_notes=ledger.review_note,
                    evidence_excerpt=evidence_excerpt,
                    evidence_locator=evidence_locator,
                    extractor="manual-release-ledger",
                    extractor_version="1.0",
                    extraction_confidence=Fraction(1),
                    requires_review=requires_review,
                )
                claims.append(claim)

                review_item_id = None
                if requires_review:
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
                    review_item = new_review_item(
                        claim_id=claim.id,
                        severity="high",
                        reason="extraction_requires_review",
                        summary="Verified multi-candidate decision from the permitted extract.",
                        race_match=race_match,
                        candidate_match=None,
                        capture_id=capture.id,
                        raw_race_text=claim.raw_race_text,
                        raw_candidate_text=claim.raw_candidate_text,
                        raw_status_text=claim.raw_status_text,
                        evidence_excerpt=claim.evidence_excerpt,
                        evidence_locator=claim.evidence_locator,
                        created_at=source_extract.captured_at,
                    )
                    decision_record = new_review_decision(
                        review_item_id=review_item.id,
                        action="approve",
                        author=ledger.reviewer,
                        reason=ledger.review_note,
                        evidence=evidence_locator,
                        created_at=reviewed_at,
                        resolution={
                            "race_id": race.id,
                            "status": status,
                            "candidate_ids": decision.candidate_ids,
                            "allocation": _allocation(decision.candidate_ids),
                        },
                    )
                    review_items.append(review_item)
                    review_decisions.append(decision_record)
                    review_item_id = review_item.id

                endorsements.append(
                    new_normalized_endorsement(
                        election_id=ledger.election_id,
                        race_id=race.id,
                        source_id=source.id,
                        status=status,
                        candidate_ids=decision.candidate_ids,
                        allocation=_allocation(decision.candidate_ids),
                        published_at=capture.published_at,
                        source_capture_id=capture.id,
                        extracted_claim_id=claim.id,
                        normalization_confidence=Fraction(1),
                        manually_verified=True,
                        reviewer=ledger.reviewer,
                        reviewed_at=reviewed_at,
                        review_item_id=review_item_id,
                        notes=ledger.review_note,
                    )
                )

        dataset = CanonicalDataset(
            inventory=inventory,
            source_registry=registry,
            captures=captures,
            claims=claims,
            endorsements=endorsements,
            review_items=review_items,
            review_decisions=review_decisions,
        )
        dataset_stage = stage / output_path.name
        dataset_stage.write_bytes(canonical_json_bytes(dataset.model_dump(mode="json")))
        _replace_outputs_atomically(
            [
                (stage_snapshots, snapshot_root),
                (stage_manifests, manifest_dir),
                (dataset_stage, output_path),
            ]
        )
        return dataset
    finally:
        shutil.rmtree(stage, ignore_errors=True)


def verify_release_compilation(
    ledger_path: Path,
    inventory_path: Path,
    registry_path: Path,
    expected_dataset_path: Path,
    expected_snapshot_root: Path,
    expected_manifest_dir: Path,
) -> CanonicalDataset:
    """Recompile in temporary storage and compare every tracked byte."""
    with tempfile.TemporaryDirectory(prefix="election-guide-release-verify-") as temporary:
        root = Path(temporary)
        dataset = compile_release_dataset(
            ledger_path,
            inventory_path,
            registry_path,
            root / "canonical-dataset.json",
            root / "snapshots",
            root / "manifests",
        )
        _require_same_file(root / "canonical-dataset.json", expected_dataset_path)
        _require_same_tree(root / "snapshots", expected_snapshot_root)
        _require_same_tree(root / "manifests", expected_manifest_dir)
        return dataset


def _validate_ledger_references(
    ledger: ReleaseLedger,
    inventory: Inventory,
    registry: SourceRegistry,
) -> None:
    inventory_races = {race.id: race for race in inventory.races}
    registry_sources = {source.id: source for source in registry.sources}
    for source_extract in ledger.sources:
        source = registry_sources.get(source_extract.source_id)
        if source is None:
            raise ValueError(
                f"release ledger references unknown source {source_extract.source_id!r}"
            )
        if source.panel_role == "excluded":
            raise ValueError(f"release ledger cannot include excluded source {source.id!r}")
        if source.discovery.status != "published":
            raise ValueError(f"release source {source.id!r} has no discovered publication")
        if source_extract.captured_at < source.discovery.checked_at:
            raise ValueError(f"release source {source.id!r} predates its discovery check")
        eligible = eligible_race_ids(source.id, inventory, registry)
        for decision in source_extract.decisions:
            race = inventory_races.get(decision.race_id)
            if race is None:
                raise ValueError(f"release ledger references unknown race {decision.race_id!r}")
            if decision.race_id not in eligible:
                raise ValueError(
                    f"release decision {source.id!r}/{decision.race_id!r} is outside eligibility"
                )
            known_candidates = {choice.id for choice in race.choices}
            unknown = set(decision.candidate_ids) - known_candidates
            if unknown:
                raise ValueError(
                    f"release decision {source.id!r}/{decision.race_id!r} has unknown "
                    f"candidates: {sorted(unknown)}"
                )


def _raw_status(decision: ReleaseDecision) -> str:
    if decision.status != "endorsed":
        return decision.status.replace("_", " ")
    if len(decision.candidate_ids) == 1:
        return "endorsed"
    if len(decision.candidate_ids) == 2:
        return "dual endorsement"
    return "multiple endorsement"


def _normalized_status(decision: ReleaseDecision) -> EndorsementStatus:
    if decision.status != "endorsed":
        return decision.status
    if len(decision.candidate_ids) == 1:
        return "endorsed"
    if len(decision.candidate_ids) == 2:
        return "dual_endorsement"
    return "multiple_endorsement"


def _allocation(candidate_ids: list[str]) -> dict[str, Fraction]:
    if not candidate_ids:
        return {}
    share = Fraction(1, len(candidate_ids))
    return {candidate_id: share for candidate_id in candidate_ids}


def _replace_outputs_atomically(replacements: list[tuple[Path, Path]]) -> None:
    """Publish one generated release-input set, rolling every target back on failure."""
    prepared = [
        (
            staged,
            destination,
            destination.with_name(
                f".{destination.name}.previous-"
                f"{hashlib.sha256(str(destination).encode()).hexdigest()[:8]}"
            ),
        )
        for staged, destination in replacements
    ]
    stale_backups = [backup for _, _, backup in prepared if backup.exists()]
    if stale_backups:
        raise OSError(
            "release input publication found unrecovered backups: "
            + ", ".join(str(path) for path in stale_backups)
        )
    committed: list[tuple[Path, Path, bool]] = []
    for staged, destination, backup in prepared:
        had_original = False
        try:
            destination.parent.mkdir(parents=True, exist_ok=True)
            had_original = destination.exists()
            if had_original:
                os.replace(destination, backup)
            os.replace(staged, destination)
        except OSError as publish_error:
            recovery_errors: list[OSError] = []
            try:
                _rollback_outputs(committed)
            except OSError as error:
                recovery_errors.append(error)
            if had_original and backup.exists() and not destination.exists():
                try:
                    os.replace(backup, destination)
                except OSError as error:
                    recovery_errors.append(error)
            if recovery_errors:
                details = "; ".join(str(error) for error in recovery_errors)
                raise OSError(
                    f"release input publication failed and recovery was incomplete: {details}"
                ) from publish_error
            raise
        committed.append((destination, backup, had_original))

    for _, backup, _ in committed:
        _remove_path(backup)


def _rollback_outputs(committed: list[tuple[Path, Path, bool]]) -> None:
    errors: list[OSError] = []
    for destination, backup, had_original in reversed(committed):
        try:
            _remove_path(destination)
        except OSError as error:
            errors.append(error)
        if had_original:
            try:
                os.replace(backup, destination)
            except OSError as error:
                errors.append(error)
    if errors:
        details = "; ".join(str(error) for error in errors)
        raise OSError(f"release input rollback was incomplete: {details}")


def _remove_path(path: Path) -> None:
    if path.is_dir():
        shutil.rmtree(path)
    elif path.exists():
        path.unlink()


def _require_same_file(generated: Path, expected: Path) -> None:
    if not expected.is_file():
        raise ValueError(f"tracked release artifact is missing: {expected}")
    if generated.read_bytes() != expected.read_bytes():
        raise ValueError(f"tracked release artifact differs from compilation: {expected}")


def _require_same_tree(generated: Path, expected: Path) -> None:
    generated_files = {
        path.relative_to(generated): path for path in generated.rglob("*") if path.is_file()
    }
    expected_files = {
        path.relative_to(expected): path for path in expected.rglob("*") if path.is_file()
    }
    if set(generated_files) != set(expected_files):
        missing = sorted(str(path) for path in set(generated_files) - set(expected_files))
        unexpected = sorted(str(path) for path in set(expected_files) - set(generated_files))
        raise ValueError(
            "tracked release tree differs from compilation: "
            f"missing={missing}, unexpected={unexpected}"
        )
    for relative, generated_path in generated_files.items():
        if generated_path.read_bytes() != expected_files[relative].read_bytes():
            raise ValueError(
                f"tracked release artifact differs from compilation: {expected / relative}"
            )
