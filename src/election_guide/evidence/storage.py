"""Immutable, content-addressed local evidence storage."""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from contextlib import suppress
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from election_guide.evidence.models import (
    CAPTURE_MANIFEST_ADAPTER,
    CapturedManifest,
    CaptureManifest,
    CaptureRequest,
    UnavailableManifest,
    UnavailableRequest,
)
from election_guide.serialization import canonical_json_bytes, read_json

CHUNK_SIZE = 1024 * 1024


class ImmutableRecordError(ValueError):
    """Raised when an operation would overwrite historical evidence metadata."""


def record_capture(
    request: CaptureRequest,
    input_path: Path,
    storage_root: Path,
    manifest_dir: Path,
) -> Path:
    """Store an artifact by hash and write its immutable public manifest."""
    if not input_path.is_file():
        raise ValueError(f"capture input is not a file: {input_path}")
    digest, byte_length, storage_reference = _store_artifact(input_path, storage_root)
    manifest = CapturedManifest(
        **request.model_dump(),
        id=_capture_id(request.source_id, request.retrieved_at, digest),
        content_sha256=digest,
        byte_length=byte_length,
        storage_reference=storage_reference,
    )
    return write_manifest(manifest, manifest_dir)


def record_unavailable(request: UnavailableRequest, manifest_dir: Path) -> Path:
    """Write an auditable immutable record when no artifact can be captured."""
    fingerprint = hashlib.sha256(canonical_json_bytes(request.model_dump(mode="json"))).hexdigest()
    manifest = UnavailableManifest(
        **request.model_dump(),
        id=_capture_id(request.source_id, request.retrieved_at, fingerprint),
    )
    return write_manifest(manifest, manifest_dir)


def write_manifest(manifest: CaptureManifest, manifest_dir: Path) -> Path:
    """Create a manifest without ever replacing a prior record."""
    output = manifest_dir / f"{manifest.id}.json"
    payload = canonical_json_bytes(manifest.model_dump(mode="json"))
    write_immutable_record(output, payload)
    return output


def read_capture_manifest(path: Path) -> CaptureManifest:
    """Read and validate a capture manifest."""
    try:
        raw: Any = read_json(path)
        return CAPTURE_MANIFEST_ADAPTER.validate_python(raw)
    except (OSError, UnicodeError, json.JSONDecodeError, ValidationError, ValueError) as error:
        raise ValueError(str(error)) from error


def verify_capture(manifest: CaptureManifest, storage_root: Path) -> None:
    """Verify stored bytes against a capture manifest."""
    if isinstance(manifest, UnavailableManifest):
        return
    artifact = _resolve_storage_reference(storage_root, manifest.storage_reference)
    if not artifact.is_file():
        raise ValueError(f"captured evidence is missing: {manifest.storage_reference}")
    digest, byte_length = _hash_file(artifact)
    if digest != manifest.content_sha256:
        raise ValueError(f"capture hash mismatch: expected {manifest.content_sha256}, got {digest}")
    if byte_length != manifest.byte_length:
        raise ValueError(
            f"capture length mismatch: expected {manifest.byte_length}, got {byte_length}"
        )


def _store_artifact(input_path: Path, storage_root: Path) -> tuple[str, int, str]:
    staging_dir = storage_root / ".staging"
    staging_dir.mkdir(parents=True, exist_ok=True)
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(dir=staging_dir, delete=False) as temporary:
            temporary_path = Path(temporary.name)
            digest = hashlib.sha256()
            byte_length = 0
            with input_path.open("rb") as source:
                while chunk := source.read(CHUNK_SIZE):
                    digest.update(chunk)
                    byte_length += len(chunk)
                    temporary.write(chunk)
            temporary.flush()
            os.fsync(temporary.fileno())
        if byte_length == 0:
            raise ValueError("captured evidence cannot be empty")

        content_sha256 = digest.hexdigest()
        storage_reference = f"sha256/{content_sha256[:2]}/{content_sha256}"
        destination = _resolve_storage_reference(storage_root, storage_reference)
        destination.parent.mkdir(parents=True, exist_ok=True)
        try:
            os.link(temporary_path, destination)
        except FileExistsError:
            existing_digest, existing_length = _hash_file(destination)
            if existing_digest != content_sha256 or existing_length != byte_length:
                raise ImmutableRecordError(
                    f"content address already contains different bytes: {storage_reference}"
                ) from None
        return content_sha256, byte_length, storage_reference
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)
        with suppress(OSError):
            staging_dir.rmdir()


def write_immutable_record(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as temporary:
            temporary_path = Path(temporary.name)
            temporary.write(payload)
            temporary.flush()
            os.fsync(temporary.fileno())
        try:
            os.link(temporary_path, path)
        except FileExistsError as error:
            if path.read_bytes() != payload:
                raise ImmutableRecordError(
                    f"refusing to overwrite immutable record: {path}"
                ) from error
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)


def _capture_id(source_id: str, retrieved_at: datetime, fingerprint: str) -> str:
    timestamp = retrieved_at.astimezone(UTC).strftime("%Y%m%dT%H%M%SZ")
    return f"capture-{source_id}-{timestamp}-{fingerprint[:12]}"


def _resolve_storage_reference(storage_root: Path, storage_reference: str) -> Path:
    root = storage_root.resolve()
    candidate = (root / storage_reference).resolve()
    if not candidate.is_relative_to(root):
        raise ValueError(f"storage reference escapes local evidence root: {storage_reference}")
    return candidate


def _hash_file(path: Path) -> tuple[str, int]:
    digest = hashlib.sha256()
    byte_length = 0
    with path.open("rb") as source:
        while chunk := source.read(CHUNK_SIZE):
            digest.update(chunk)
            byte_length += len(chunk)
    return digest.hexdigest(), byte_length
