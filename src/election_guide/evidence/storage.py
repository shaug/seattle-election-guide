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
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal
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

#: Tracked store for redistributable official-authority bytes (issue #357).
#: Kept here rather than beside the CLI defaults because the durability rule
#: and the root it points at are one decision (`docs/COLLECTION.md`).
REPOSITORY_STORAGE_ROOT = Path("data/evidence/official")

StorageScope = Literal["local_only", "repository"]
PresenceStatus = Literal["present", "missing", "corrupt", "expected-absent", "no-artifact"]


class ImmutableRecordError(ValueError):
    """Raised when an operation would overwrite historical evidence metadata."""


@dataclass(frozen=True)
class BytePresence:
    """One manifest's verdict from a byte-presence sweep."""

    capture_id: str
    status: PresenceStatus
    detail: str | None = None


def record_capture(
    request: CaptureRequest,
    input_path: Path,
    storage_root: Path,
    manifest_dir: Path,
    *,
    repository_storage_root: Path = REPOSITORY_STORAGE_ROOT,
) -> Path:
    """Store an artifact by hash and write its immutable public manifest."""
    if not input_path.is_file():
        raise ValueError(f"capture input is not a file: {input_path}")
    _validate_storage_boundary(request, input_path, storage_root, manifest_dir)
    storage_scope = _resolve_storage_scope(storage_root, repository_storage_root)
    _validate_storage_durability(storage_root)
    digest, byte_length, storage_reference = _store_artifact(input_path, storage_root, request)
    manifest_payload = {
        **request.model_dump(mode="json"),
        "content_sha256": digest,
        "byte_length": byte_length,
        "storage_scope": storage_scope,
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


def verify_capture(
    manifest: CaptureManifest,
    storage_root: Path,
    *,
    repository_storage_root: Path = REPOSITORY_STORAGE_ROOT,
) -> None:
    """Verify stored bytes against a capture manifest.

    Chooses the root from the manifest's own scope, so a caller passes only the
    local root it already knows about. Selecting the root here rather than at
    each call site is what keeps a `repository`-scope manifest from being
    looked up in the wrong store by any caller that has not heard of the
    official store yet (issue #357).
    """
    if isinstance(manifest, UnavailableManifest):
        return
    root = storage_root_for(manifest, storage_root, repository_storage_root)
    artifact = _resolve_storage_reference(root, manifest.storage_reference)
    if not artifact.is_file():
        raise ValueError(f"captured evidence is missing: {manifest.storage_reference}")
    digest, byte_length = _hash_file(artifact)
    if digest != manifest.content_sha256:
        raise ValueError(f"capture hash mismatch: expected {manifest.content_sha256}, got {digest}")
    if byte_length != manifest.byte_length:
        raise ValueError(
            f"capture length mismatch: expected {manifest.byte_length}, got {byte_length}"
        )


def storage_root_for(
    manifest: CapturedManifest,
    local_storage_root: Path,
    repository_storage_root: Path = REPOSITORY_STORAGE_ROOT,
) -> Path:
    """Pick the root that holds one manifest's bytes, by its recorded scope."""
    return repository_storage_root if manifest.storage_scope == "repository" else local_storage_root


def survey_byte_presence(
    manifest_dir: Path,
    *,
    local_storage_root: Path,
    repository_storage_root: Path = REPOSITORY_STORAGE_ROOT,
    require_local: bool = False,
) -> list[BytePresence]:
    """Verify every manifest's bytes, reporting each one's presence.

    A `repository`-scope artifact must always be present: its bytes travel with
    history, so anywhere the repository is, they must be, and absence is a real
    loss. A `local_only` artifact's bytes are exempt when absent, because no
    environment but the capturing machine ever holds them — CI never does, and
    neither does a second checkout. `require_local` drops that exemption for an
    operator auditing a machine that is supposed to hold everything.

    The exemption is decided per artifact rather than by probing for the store
    directory. Probing looked equivalent and is not: the first local capture
    creates `data/snapshots/`, which the endorsement sweep runbook has an
    operator do routinely, and from then on a store-shaped test reports every
    artifact that machine never held as a loss — turning `make check`, the
    mandated gate, red on evidence nothing is actually wrong with.

    Bytes that are present but do not match their manifest are `corrupt` under
    either scope, and never exempt.
    """
    survey: list[BytePresence] = []
    for manifest_path in sorted(manifest_dir.glob("*.json")):
        manifest = read_capture_manifest(manifest_path)
        if not isinstance(manifest, CapturedManifest):
            survey.append(BytePresence(manifest.id, "no-artifact"))
            continue
        root = storage_root_for(manifest, local_storage_root, repository_storage_root)
        artifact = _resolve_storage_reference(root, manifest.storage_reference)
        if not artifact.is_file():
            exempt = manifest.storage_scope == "local_only" and not require_local
            survey.append(
                BytePresence(
                    manifest.id,
                    "expected-absent" if exempt else "missing",
                    f"no bytes at {artifact}",
                )
            )
            continue
        try:
            verify_capture(manifest, root, repository_storage_root=repository_storage_root)
        except (OSError, ValueError) as error:
            survey.append(BytePresence(manifest.id, "corrupt", str(error)))
            continue
        survey.append(BytePresence(manifest.id, "present"))
    return survey


def _resolve_storage_scope(storage_root: Path, repository_storage_root: Path) -> StorageScope:
    """Derive scope from the one designated official store.

    Deliberately keyed on that store rather than on "inside the repository and
    not Git-ignored". A trackedness rule would sweep in every other unignored
    in-repository root a caller passes — `release compile` stages its captures
    under `output_path.parent`, `data/normalized/` by default — and because
    this value feeds the capture-ID fingerprint, that would hand those captures
    new IDs and silently rewrite the identity of all 41 release manifests
    already committed.
    """
    official = repository_storage_root.resolve()
    root = storage_root.resolve()
    return "repository" if root == official or root.is_relative_to(official) else "local_only"


def _validate_storage_durability(storage_root: Path) -> None:
    """Refuse a capture whose bytes would die with the working tree that wrote them.

    Bytes written to a Git-ignored path inside a linked worktree are held by
    nothing: no commit references them, no other checkout has them, and
    removing the worktree deletes them. That is exactly how the 2026-08-04
    election-night capture was lost — it verified at capture time and was gone
    once the worktree went (issue #357). Ignoredness is asked here directly
    rather than read off the storage scope: the two answer different questions,
    and only this one is about durability.

    Only the ignored case is refused, because Git itself already guards the
    other one. `git worktree remove` deletes a worktree holding nothing but
    ignored files silently, taking those bytes with it; the moment an unignored
    file is present it refuses with "contains modified or untracked files, use
    --force". So bytes at an unignored path — committed or merely staged for
    commit — cannot vanish without the operator overriding a warning, while
    ignored bytes vanish without one. A root outside the repository is likewise
    the operator's own durable store.
    """
    repository = _find_repository_root(storage_root)
    if repository is None or not _git_is_linked_worktree(repository):
        return
    if not _git_path_is_ignored(repository, storage_root.resolve()):
        return
    raise ValueError(
        f"Git-ignored artifact storage inside a linked worktree does not outlive it: "
        f"{storage_root}; capture from the primary checkout, store the bytes at a tracked "
        f"path such as {REPOSITORY_STORAGE_ROOT}, or use a storage root outside the repository"
    )


def _git_is_linked_worktree(repository: Path) -> bool:
    git_dir = _git_output(repository, ["rev-parse", "--absolute-git-dir"])
    common_dir = _git_output(
        repository, ["rev-parse", "--path-format=absolute", "--git-common-dir"]
    )
    if git_dir is None or common_dir is None:
        return False
    return Path(git_dir).resolve() != Path(common_dir).resolve()


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
