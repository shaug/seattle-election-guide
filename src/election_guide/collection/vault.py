"""Immutable, authenticated encrypted captures that travel with Git history."""

from __future__ import annotations

import base64
import binascii
import hashlib
import os
import subprocess
from pathlib import Path
from typing import Literal

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from pydantic import BaseModel, ConfigDict, Field

from election_guide.evidence.models import SHA256_PATTERN
from election_guide.evidence.storage import write_immutable_record
from election_guide.serialization import canonical_json_bytes, read_json

KEY_VARIABLE = "ENDORSEMENT_EVIDENCE_KEY"
MAX_CAPTURE_BYTES = 25 * 1024 * 1024


class SealedCapture(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["1.0"] = "1.0"
    algorithm: Literal["AES-256-GCM"] = "AES-256-GCM"
    content_sha256: str = Field(pattern=SHA256_PATTERN)
    byte_length: int = Field(gt=0, le=MAX_CAPTURE_BYTES)
    key_id: str = Field(pattern=r"^[a-f0-9]{16}$")
    encrypted: str = Field(min_length=1, max_length=(MAX_CAPTURE_BYTES + 28) * 4 // 3 + 4)


def read_key() -> bytes:
    """Load a random 256-bit key without echoing it in errors or reports."""
    try:
        key = base64.b64decode(os.environ.get(KEY_VARIABLE, ""), validate=True)
    except (binascii.Error, ValueError) as error:
        raise ValueError(f"{KEY_VARIABLE} must contain a base64-encoded 256-bit key") from error
    if len(key) != 32:
        raise ValueError(f"{KEY_VARIABLE} must contain a base64-encoded 256-bit key")
    return key


def _unseal(path: Path, key: bytes) -> tuple[str, bytes]:
    if path.is_symlink():
        raise ValueError("sealed evidence must not be a symbolic link")
    if path.stat().st_size > (MAX_CAPTURE_BYTES + 28) * 4 // 3 + 2_000:
        raise ValueError("sealed evidence exceeds the capture bound")
    record = SealedCapture.model_validate(read_json(path))
    expected_path = Path("sha256") / record.content_sha256[:2] / f"{record.content_sha256}.json"
    if Path(*path.parts[-3:]) != expected_path:
        raise ValueError("sealed evidence path does not match its content address")
    if record.key_id != hashlib.sha256(key).hexdigest()[:16]:
        raise ValueError("evidence key does not match the committed capture")
    try:
        encrypted = base64.b64decode(record.encrypted, validate=True)
        raw = AESGCM(key).decrypt(
            encrypted[:12], encrypted[12:], record.content_sha256.encode("ascii")
        )
    except (binascii.Error, InvalidTag, ValueError) as error:
        raise ValueError("sealed evidence authentication failed") from error
    if len(raw) != record.byte_length or hashlib.sha256(raw).hexdigest() != record.content_sha256:
        raise ValueError("sealed evidence does not match its declared content")
    return record.content_sha256, raw


def seal_store(storage_root: Path, vault_root: Path, key: bytes) -> int:
    """Reuse existing ciphertext; never replace a historical encrypted capture."""
    count = 0
    for path in sorted(storage_root.glob("sha256/*/*")):
        if not path.is_file() or path.is_symlink():
            raise ValueError("capture store contains a non-regular artifact")
        if not 0 < path.stat().st_size <= MAX_CAPTURE_BYTES:
            raise ValueError("capture store contains an empty or oversized artifact")
        raw = path.read_bytes()
        digest = hashlib.sha256(raw).hexdigest()
        if path.name != digest or path.parent.name != digest[:2]:
            raise ValueError("capture bytes do not match their content address")
        destination = vault_root / "sha256" / digest[:2] / f"{digest}.json"
        if destination.exists():
            if _unseal(destination, key) != (digest, raw):
                raise ValueError("committed sealed capture does not match the original")
        else:
            nonce = os.urandom(12)
            encrypted = nonce + AESGCM(key).encrypt(nonce, raw, digest.encode("ascii"))
            record = SealedCapture(
                content_sha256=digest,
                byte_length=len(raw),
                key_id=hashlib.sha256(key).hexdigest()[:16],
                encrypted=base64.b64encode(encrypted).decode("ascii"),
            )
            write_immutable_record(
                destination, canonical_json_bytes(record.model_dump(mode="json"))
            )
        count += 1
    return count


def restore_store(vault_root: Path, storage_root: Path, key: bytes) -> int:
    """Verify and restore original bytes only to a local, unpublished directory."""
    _require_private_output(storage_root)
    records = sorted(vault_root.glob("sha256/*/*.json"))
    # Authenticate the whole set before writing anything from a corrupt store.
    for path in records:
        if path.is_symlink():
            raise ValueError("sealed evidence must not be a symbolic link")
        _unseal(path, key)
        digest = path.stem
        _require_private_output(storage_root / "sha256" / digest[:2] / digest)
        if (
            not (storage_root / "sha256" / digest[:2] / digest)
            .resolve()
            .is_relative_to(storage_root.resolve())
        ):
            raise ValueError("decrypted evidence path escapes its private directory")
    for path in records:
        digest, raw = _unseal(path, key)
        destination = storage_root / "sha256" / digest[:2] / digest
        write_immutable_record(destination, raw)
    return len(records)


def _require_private_output(storage_root: Path) -> None:
    parent = storage_root.resolve()
    while not parent.exists():
        parent = parent.parent
    repository = subprocess.run(
        ["git", "-C", str(parent), "rev-parse", "--show-toplevel"],
        capture_output=True,
        text=True,
        check=False,
    )
    if repository.returncode != 0:
        return
    root = Path(repository.stdout.strip()).resolve()
    destination = storage_root.resolve()
    if destination.is_relative_to(root):
        ignored = subprocess.run(
            ["git", "-C", str(root), "check-ignore", "-q", str(destination)],
            capture_output=True,
            check=False,
        )
        if ignored.returncode != 0:
            raise ValueError("decrypted evidence inside the repository must be Git-ignored")
