"""Verify and compare the deterministic contract of release bundles."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path

from election_guide.release.models import ReleaseManifest, ReleaseStatus
from election_guide.serialization import read_json


@dataclass(frozen=True)
class VerifiedReleaseBundle:
    directory: Path
    status: ReleaseStatus
    manifest: ReleaseManifest


def verify_release_bundle_artifacts(
    bundle_dir: Path,
    *,
    status: ReleaseStatus | None = None,
    manifest: ReleaseManifest | None = None,
) -> VerifiedReleaseBundle:
    """Verify one bundle's manifest partition and every declared artifact."""
    bundle_dir = bundle_dir.resolve()
    if not bundle_dir.is_dir():
        raise ValueError(f"release bundle directory does not exist: {bundle_dir}")
    status = status or ReleaseStatus.model_validate(read_json(bundle_dir / "release-status.json"))
    manifest = manifest or ReleaseManifest.model_validate(
        read_json(bundle_dir / "release-manifest.json")
    )

    if manifest.release_version != status.release_version:
        raise ValueError("release manifest and release status versions differ")
    if manifest.generated_at != status.generated_at:
        raise ValueError("release manifest and release status timestamps differ")
    if (
        manifest.source_panel_id != status.source_panel_id
        or manifest.source_panel_hash != status.source_panel_hash
    ):
        raise ValueError("release manifest and release status source panels differ")

    expected = set(status.included_artifacts) - {"release-manifest.json"}
    hashed = set(manifest.artifact_hashes)
    unhashed = set(manifest.unhashed_artifacts)
    overlap = hashed & unhashed
    if overlap:
        raise ValueError(f"release artifacts are both hashed and unhashed: {sorted(overlap)}")
    undeclared = expected - hashed - unhashed
    if undeclared:
        raise ValueError(
            f"release artifacts are not declared in the manifest: {sorted(undeclared)}"
        )
    unexpected = (hashed | unhashed) - expected
    if unexpected:
        raise ValueError(
            f"release manifest declares artifacts absent from release status: {sorted(unexpected)}"
        )

    for relative, expected_hash in sorted(manifest.artifact_hashes.items()):
        path = bundle_dir / relative
        if not path.is_file():
            raise ValueError(f"release artifact is missing: {relative}")
        actual_hash = hashlib.sha256(path.read_bytes()).hexdigest()
        if actual_hash != expected_hash:
            raise ValueError(f"release artifact hash mismatch: {relative}")
    for relative in sorted(manifest.unhashed_artifacts):
        if not (bundle_dir / relative).is_file():
            raise ValueError(f"release artifact is missing: {relative}")

    return VerifiedReleaseBundle(bundle_dir, status, manifest)


def compare_release_bundles(first_dir: Path, second_dir: Path) -> None:
    """Fail with an artifact path when deterministic release output differs."""
    first = verify_release_bundle_artifacts(first_dir)
    second = verify_release_bundle_artifacts(second_dir)

    first_hashes = first.manifest.artifact_hashes
    second_hashes = second.manifest.artifact_hashes
    all_hashed_paths = sorted(set(first_hashes) | set(second_hashes))
    for relative in all_hashed_paths:
        if first_hashes.get(relative) != second_hashes.get(relative):
            raise ValueError(f"deterministic release artifact differs: {relative}")

    first_manifest_path = first.directory / "release-manifest.json"
    second_manifest_path = second.directory / "release-manifest.json"
    if first_manifest_path.read_bytes() != second_manifest_path.read_bytes():
        raise ValueError("deterministic release artifact differs: release-manifest.json")
