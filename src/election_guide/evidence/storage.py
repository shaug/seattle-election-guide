"""Immutable, content-addressed local evidence storage."""

from __future__ import annotations

import errno
import hashlib
import json
import os
import shutil
import subprocess
import tempfile
from contextlib import suppress
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from xml.etree import ElementTree

from pydantic import ValidationError

from election_guide.evidence.models import (
    CAPTURE_MANIFEST_ADAPTER,
    CapturedManifest,
    CaptureManifest,
    CaptureRequest,
    UnavailableManifest,
    UnavailableRequest,
    evidence_fingerprint,
)
from election_guide.serialization import canonical_json_bytes, read_json
from election_guide.validation import media_type_essence

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
    _validate_storage_boundary(request, input_path, storage_root, manifest_dir)
    digest, byte_length, storage_reference = _store_artifact(input_path, storage_root, request)
    manifest_payload = {
        **request.model_dump(mode="json"),
        "content_sha256": digest,
        "byte_length": byte_length,
        "storage_scope": "local_only",
        "storage_reference": storage_reference,
    }
    manifest = CapturedManifest.model_validate(
        {
            **manifest_payload,
            "id": _capture_id(
                request.source_id,
                request.retrieved_at,
                evidence_fingerprint(manifest_payload),
            ),
        }
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
        manifest = CAPTURE_MANIFEST_ADAPTER.validate_python(raw)
        if path.name != f"{manifest.id}.json":
            raise ValueError(
                f"capture manifest filename does not match its identity: {manifest.id!r}"
            )
        return manifest
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


def _store_artifact(
    input_path: Path, storage_root: Path, request: CaptureRequest
) -> tuple[str, int, str]:
    root = storage_root.resolve()
    root.mkdir(parents=True, exist_ok=True)
    staging_dir = Path(tempfile.mkdtemp(prefix=".staging-", dir=root))
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
        _validate_staged_artifact(request, temporary_path)

        content_sha256 = digest.hexdigest()
        storage_reference = f"sha256/{content_sha256[:2]}/{content_sha256}"
        destination = _resolve_storage_reference(storage_root, storage_reference)
        destination.parent.mkdir(parents=True, exist_ok=True)
        if not _install_exclusive(temporary_path, destination):
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


def _validate_staged_artifact(request: CaptureRequest, artifact_path: Path) -> None:
    """Reject method-constrained artifacts whose bytes contradict their declared type."""
    if request.media_type is None:
        return
    essence = media_type_essence(request.media_type)
    with artifact_path.open("rb") as artifact:
        header = artifact.read(4096)
    if essence == "application/pdf" and not header.startswith(b"%PDF-"):
        raise ValueError("PDF capture bytes do not begin with a PDF signature")
    if essence.startswith("image/") and not _matches_image_signature(
        essence, header, artifact_path
    ):
        raise ValueError(f"image capture bytes do not match declared media type {essence!r}")


def _matches_image_signature(media_type: str, header: bytes, artifact_path: Path) -> bool:
    signatures = {
        "image/bmp": (b"BM",),
        "image/gif": (b"GIF87a", b"GIF89a"),
        "image/jpeg": (b"\xff\xd8\xff",),
        "image/png": (b"\x89PNG\r\n\x1a\n",),
        "image/tiff": (b"II*\x00", b"MM\x00*"),
    }
    if media_type == "image/svg+xml":
        try:
            _, root = next(ElementTree.iterparse(artifact_path, events=("start",)))
        except (ElementTree.ParseError, StopIteration):
            return False
        return root.tag == "svg" or root.tag.endswith("}svg")
    if media_type == "image/webp":
        return len(header) >= 12 and header.startswith(b"RIFF") and header[8:12] == b"WEBP"
    if media_type in {"image/avif", "image/heic", "image/heif"}:
        return _matches_iso_bmff_image_brand(media_type, header)
    expected = signatures.get(media_type)
    return expected is not None and header.startswith(expected)


def _matches_iso_bmff_image_brand(media_type: str, header: bytes) -> bool:
    if len(header) < 16 or header[4:8] != b"ftyp":
        return False
    box_size = int.from_bytes(header[:4], byteorder="big")
    if box_size < 16 or box_size > len(header):
        return False
    brands = {header[8:12]}
    brands.update(header[offset : offset + 4] for offset in range(16, box_size, 4))
    allowed = {
        "image/avif": {b"avif", b"avis"},
        "image/heic": {b"heic", b"heix", b"hevc", b"hevx"},
        "image/heif": {b"mif1", b"msf1", b"heic", b"heix", b"hevc", b"hevx"},
    }
    return bool(brands & allowed[media_type])


def _validate_storage_boundary(
    request: CaptureRequest,
    input_path: Path,
    storage_root: Path,
    manifest_dir: Path,
) -> None:
    storage = storage_root.resolve()
    manifests = manifest_dir.resolve()
    if (
        storage == manifests
        or storage.is_relative_to(manifests)
        or manifests.is_relative_to(storage)
    ):
        raise ValueError("artifact storage and public manifest directories must not overlap")
    if request.redistribution != "restricted":
        return

    repository = _find_repository_root(storage_root)
    if (
        repository is not None
        and storage.is_relative_to(repository)
        and not _git_path_is_ignored(repository, storage)
    ):
        raise ValueError("restricted artifact storage inside the repository must be Git-ignored")

    input_repository = _find_repository_root(input_path)
    resolved_input = input_path.resolve()
    if (
        input_repository is not None
        and resolved_input.is_relative_to(input_repository)
        and not _git_path_matches_head(input_repository, resolved_input)
        and not _git_path_is_ignored(input_repository, resolved_input)
    ):
        raise ValueError(
            "restricted capture input inside the repository must already be committed or "
            "Git-ignored"
        )


def _find_repository_root(path: Path) -> Path | None:
    candidate = path.resolve()
    if not candidate.is_dir():
        candidate = candidate.parent
    while not candidate.exists() and candidate != candidate.parent:
        candidate = candidate.parent
    for directory in (candidate, *candidate.parents):
        if (directory / ".git").exists():
            return directory
    return None


def _git_path_is_ignored(repository: Path, path: Path) -> bool:
    result = subprocess.run(
        [
            "git",
            "-C",
            str(repository),
            "check-ignore",
            "--quiet",
            "--no-index",
            str(path / ".git-ignore-probe"),
        ],
        check=False,
        capture_output=True,
    )
    return result.returncode == 0


def _git_path_matches_head(repository: Path, path: Path) -> bool:
    relative_path = path.relative_to(repository).as_posix()
    head_blob = _git_output(repository, ["rev-parse", f"HEAD:{relative_path}"])
    index_blob = _git_output(repository, ["rev-parse", f":{relative_path}"])
    working_blob = _git_output(
        repository,
        ["hash-object", f"--path={relative_path}", "--filters", relative_path],
    )
    return head_blob is not None and head_blob == index_blob == working_blob


def _git_output(repository: Path, arguments: list[str]) -> str | None:
    result = subprocess.run(
        ["git", "-C", str(repository), *arguments],
        check=False,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip() if result.returncode == 0 else None


def _install_exclusive(source: Path, destination: Path) -> bool:
    """Install a file without replacement, falling back when hard links are unsupported."""
    try:
        os.link(source, destination)
        return True
    except FileExistsError:
        return False
    except OSError as error:
        unsupported = {errno.EXDEV, errno.ENOTSUP, errno.EOPNOTSUPP, errno.EPERM}
        if error.errno not in unsupported:
            raise

    descriptor: int | None = None
    try:
        descriptor = os.open(destination, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError:
        return False
    try:
        with os.fdopen(descriptor, "wb") as output, source.open("rb") as input_file:
            descriptor = None
            shutil.copyfileobj(input_file, output)
            output.flush()
            os.fsync(output.fileno())
    except BaseException:
        destination.unlink(missing_ok=True)
        raise
    finally:
        if descriptor is not None:
            os.close(descriptor)
    return True


def write_immutable_record(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as temporary:
            temporary_path = Path(temporary.name)
            temporary.write(payload)
            temporary.flush()
            os.fsync(temporary.fileno())
        if not _install_exclusive(temporary_path, path) and path.read_bytes() != payload:
            raise ImmutableRecordError(f"refusing to overwrite immutable record: {path}")
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
