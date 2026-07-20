"""Validated manual transcription adapter."""

from __future__ import annotations

import hashlib
from datetime import UTC
from pathlib import Path
from typing import Any

import yaml
from pydantic import ValidationError

from election_guide.evidence.models import (
    ManualEntry,
    ManualEntryDraft,
    UnavailableManifest,
)
from election_guide.evidence.storage import (
    read_capture_manifest,
    verify_capture,
    write_immutable_record,
)
from election_guide.serialization import canonical_json_bytes, read_yaml
from election_guide.validation import media_type_essence


def read_manual_draft(path: Path) -> ManualEntryDraft:
    """Read a strict YAML manual-entry draft."""
    try:
        raw: Any = read_yaml(path)
        return ManualEntryDraft.model_validate(raw)
    except (OSError, yaml.YAMLError, ValidationError) as error:
        raise ValueError(str(error)) from error


def validate_manual_draft(
    draft: ManualEntryDraft,
    manifest_dir: Path,
    storage_root: Path,
) -> ManualEntry:
    """Cross-check a manual entry against immutable captured evidence."""
    manifest_path = manifest_dir / f"{draft.capture_id}.json"
    manifest = read_capture_manifest(manifest_path)
    if manifest.id != draft.capture_id:
        raise ValueError(
            f"manual entry capture ID {draft.capture_id!r} does not match manifest "
            f"identity {manifest.id!r}"
        )
    if isinstance(manifest, UnavailableManifest):
        raise ValueError("manual transcription requires captured evidence, not unavailable status")
    if manifest.source_id != draft.source_id:
        raise ValueError(
            f"manual entry source {draft.source_id!r} does not match capture "
            f"source {manifest.source_id!r}"
        )
    if draft.entered_at < manifest.retrieved_at:
        raise ValueError("manual entry cannot predate its evidence capture")
    verify_capture(manifest, storage_root)
    media_type = manifest.media_type
    if media_type is None:
        raise ValueError("captured evidence is missing its validated media type")
    essence = media_type_essence(media_type)
    if draft.evidence_type in {"screenshot", "image"} and not essence.startswith("image/"):
        raise ValueError(f"{draft.evidence_type} manual evidence requires an image capture")
    if draft.evidence_type == "pdf" and essence != "application/pdf":
        raise ValueError("pdf manual evidence requires a PDF capture")
    if draft.evidence_type == "scanned_material" and not (
        essence.startswith("image/") or essence == "application/pdf"
    ):
        raise ValueError("scanned manual evidence requires an image or PDF capture")
    fingerprint = hashlib.sha256(canonical_json_bytes(draft.model_dump(mode="json"))).hexdigest()
    timestamp = draft.entered_at.astimezone(UTC).strftime("%Y%m%dT%H%M%SZ")
    return ManualEntry(
        **draft.model_dump(),
        id=f"manual-{draft.source_id}-{timestamp}-{fingerprint[:12]}",
    )


def import_manual_entry(
    draft_path: Path,
    manifest_dir: Path,
    storage_root: Path,
    output_dir: Path,
) -> Path:
    """Validate and immutably import a manual transcription as canonical JSON."""
    return import_manual_draft(
        read_manual_draft(draft_path),
        manifest_dir,
        storage_root,
        output_dir,
    )


def import_manual_draft(
    draft: ManualEntryDraft,
    manifest_dir: Path,
    storage_root: Path,
    output_dir: Path,
) -> Path:
    """Validate and immutably import an already parsed manual draft."""
    entry = validate_manual_draft(draft, manifest_dir, storage_root)
    output = output_dir / f"{entry.id}.json"
    write_immutable_record(output, canonical_json_bytes(entry.model_dump(mode="json")))
    return output
