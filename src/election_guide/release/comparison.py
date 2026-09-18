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


def _inspect_release_bundle_artifacts(
    bundle_dir: Path,
    *,
    status: ReleaseStatus | None = None,
    manifest: ReleaseManifest | None = None,
) -> tuple[VerifiedReleaseBundle, tuple[str, ...]]:
    """Load one trustworthy manifest partition and inspect its artifact files."""
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
    if (
        manifest.schema_version == "1.3" or status.schema_version == "1.3"
    ) and manifest.source_registry_hash != status.source_registry_hash:
        raise ValueError(
            "release manifest and release status complete source registry hashes differ"
        )

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

    artifact_errors: list[str] = []
    for relative, expected_hash in sorted(manifest.artifact_hashes.items()):
        path = bundle_dir / relative
        if not path.is_file():
            artifact_errors.append(f"release artifact is missing: {relative}")
            continue
        actual_hash = hashlib.sha256(path.read_bytes()).hexdigest()
        if actual_hash != expected_hash:
            artifact_errors.append(f"release artifact hash mismatch: {relative}")
    for relative in sorted(manifest.unhashed_artifacts):
        if not (bundle_dir / relative).is_file():
            artifact_errors.append(f"release artifact is missing: {relative}")
    return VerifiedReleaseBundle(bundle_dir, status, manifest), tuple(artifact_errors)


def verify_release_bundle_artifacts(
    bundle_dir: Path,
    *,
    status: ReleaseStatus | None = None,
    manifest: ReleaseManifest | None = None,
) -> VerifiedReleaseBundle:
    """Verify one bundle's manifest partition and every declared artifact."""
    verified, artifact_errors = _inspect_release_bundle_artifacts(
        bundle_dir,
        status=status,
        manifest=manifest,
    )
    if artifact_errors:
        raise ValueError("; ".join(artifact_errors))
    return verified


def compare_release_bundles(first_dir: Path, second_dir: Path) -> None:
    """Fail with every affected path when deterministic release output differs."""
    verified_bundles: list[VerifiedReleaseBundle] = []
    verification_errors: list[str] = []
    for label, bundle_dir in (("first", first_dir), ("second", second_dir)):
        try:
            verified, artifact_errors = _inspect_release_bundle_artifacts(bundle_dir)
        except (OSError, ValueError) as error:
            verification_errors.append(f"{label} bundle: {error}")
            continue
        verified_bundles.append(verified)
        verification_errors.extend(f"{label} bundle: {error}" for error in artifact_errors)

    if len(verified_bundles) != 2:
        raise ValueError("release bundle verification failed: " + "; ".join(verification_errors))

    first, second = verified_bundles

    first_hashes = first.manifest.artifact_hashes
    second_hashes = second.manifest.artifact_hashes
    all_hashed_paths = sorted(set(first_hashes) | set(second_hashes))
    differences = [
        relative
        for relative in all_hashed_paths
        if first_hashes.get(relative) != second_hashes.get(relative)
    ]

    first_manifest_path = first.directory / "release-manifest.json"
    second_manifest_path = second.directory / "release-manifest.json"
    if first_manifest_path.read_bytes() != second_manifest_path.read_bytes():
        differences.append("release-manifest.json")
    if differences:
        noun = "artifact differs" if len(differences) == 1 else "artifacts differ"
        verification_errors.append(f"deterministic release {noun}: {', '.join(differences)}")
    if verification_errors:
        raise ValueError("release comparison failed: " + "; ".join(verification_errors))
