"""Resolve and admit repository-owned, reviewed release declarations."""

from __future__ import annotations

import hashlib
import os
import re
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path

import yaml

from election_guide.hosting.models import (
    InputHashes,
    PublicationRequest,
    PublishedElection,
    SiteManifest,
)
from election_guide.hosting.pages import read_site_manifest
from election_guide.inventory.importer import read_inventory
from election_guide.normalization.models import CanonicalDataset
from election_guide.release.compiler import read_release_ledger
from election_guide.release.models import release_archive_name
from election_guide.serialization import read_json, read_yaml
from election_guide.sources.models import SourceRegistry
from election_guide.sources.panel import build_panel_snapshot
from election_guide.sources.registry import read_source_registry, source_registry_hash


@dataclass(frozen=True)
class ReleaseInputs:
    ledger: Path
    inventory: Path
    registry: Path
    dataset: Path
    snapshots: Path
    manifests: Path


@dataclass(frozen=True)
class ResolvedRelease:
    site: SiteManifest
    current: PublishedElection
    inputs: ReleaseInputs
    archive_name: str


def _load_release(
    site_manifest_path: Path,
    *,
    repository: Path,
) -> tuple[ResolvedRelease, SourceRegistry]:
    """Load the standard input set without trusting stale derived declaration pins."""
    repository = repository.resolve()
    site = read_site_manifest(repository / site_manifest_path)
    current = site.elections[0]
    election_id = current.election_id
    release_root = repository / "data/releases" / election_id
    primary = election_id == "wa-2026-primary"
    inputs = ReleaseInputs(
        ledger=release_root / "source-decisions.yaml",
        inventory=repository / f"data/normalized/{election_id}-inventory.json",
        registry=repository / f"config/sources/{'default' if primary else election_id}.yaml",
        dataset=repository
        / (
            "data/normalized/canonical-dataset.json"
            if primary
            else f"data/normalized/{election_id}-canonical-dataset.json"
        ),
        snapshots=release_root / "snapshots",
        manifests=release_root / "manifests",
    )
    ledger = read_release_ledger(inputs.ledger)
    inventory = read_inventory(inputs.inventory)
    registry = read_source_registry(inputs.registry)
    dataset = CanonicalDataset.model_validate(read_json(inputs.dataset))
    identities = (
        ledger.election_id,
        inventory.election.id,
        registry.election_id,
        dataset.inventory.election.id,
    )
    if any(identity != election_id for identity in identities):
        raise ValueError("release input election identity differs from current election")
    for directory in (inputs.snapshots, inputs.manifests):
        if not directory.is_dir():
            raise ValueError(f"release input directory is missing: {directory}")
    if current.bundle_id != f"{election_id}-{current.release_version}":
        raise ValueError("current bundle identity differs from election and release version")
    return (
        ResolvedRelease(site, current, inputs, release_archive_name(current.release_version)),
        registry,
    )


def resolve_release(site_manifest_path: Path, *, repository: Path) -> ResolvedRelease:
    """Resolve standard inputs and verify their election and semantic identities."""
    resolved, registry = _load_release(site_manifest_path, repository=repository)
    current = resolved.current
    panel = build_panel_snapshot(registry)
    if (current.source_panel_id, current.source_panel_hash) != (panel.panel_id, panel.panel_hash):
        raise ValueError("release panel identity differs from current declaration")
    if (
        current.source_registry_hash is not None
        and current.source_registry_hash != source_registry_hash(registry)
    ):
        raise ValueError("release registry semantic identity differs from current declaration")
    return resolved


def hash_release_inputs(inputs: ReleaseInputs) -> InputHashes:
    """Bind exact reviewed bytes, including formatting and comments."""
    return InputHashes(
        ledger_sha256=hashlib.sha256(inputs.ledger.read_bytes()).hexdigest(),
        dataset_sha256=hashlib.sha256(inputs.dataset.read_bytes()).hexdigest(),
        registry_sha256=hashlib.sha256(inputs.registry.read_bytes()).hexdigest(),
    )


def _version_number(version: str, election_id: str) -> int:
    prefix = election_id.removeprefix("wa-")
    match = re.fullmatch(re.escape(prefix) + r"\.([0-9]+)", version)
    if match is None:
        raise ValueError(f"release version is not numeric and election-scoped: {version!r}")
    return int(match[1])


def require_ancestor(
    previous_release_sha: str, *, repository: Path, source_sha: str | None = None
) -> None:
    """Reject shorthand, absent objects, and unrelated release boundaries."""
    if re.fullmatch(r"[0-9a-f]{40}", previous_release_sha) is None:
        raise ValueError("previous release commit must be a full lowercase Git SHA")
    if source_sha is not None and re.fullmatch(r"[0-9a-f]{40}", source_sha) is None:
        raise ValueError("ancestor boundary must be a full lowercase Git SHA")
    result = subprocess.run(
        ["git", "merge-base", "--is-ancestor", previous_release_sha, source_sha or "HEAD"],
        cwd=repository,
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        raise ValueError("previous release commit must be an ancestor of the selected source")


def validate_unpublished_predecessor(base: SiteManifest, previous: SiteManifest) -> None:
    """The recorded source must declare an earlier release of the same election."""
    selected, predecessor = base.elections[0], previous.elections[0]
    if selected.election_id != predecessor.election_id:
        raise ValueError("unpublished base predecessor belongs to a different election")
    if _version_number(predecessor.release_version, selected.election_id) >= _version_number(
        selected.release_version, selected.election_id
    ):
        raise ValueError("unpublished base predecessor requires a lower release version")


def prepare_release(
    site_manifest_path: Path,
    *,
    repository: Path,
    issue_number: int,
    main_manifest: SiteManifest,
    occupied_versions: frozenset[str],
    previous_release_sha: str,
) -> ResolvedRelease:
    """Atomically refresh only the current proposal after inspecting published identities."""
    resolved, registry = _load_release(site_manifest_path, repository=repository)
    require_ancestor(previous_release_sha, repository=repository)
    current = resolved.current
    base = next(
        (entry for entry in main_manifest.elections if entry.election_id == current.election_id),
        None,
    )
    if base is None:
        raise ValueError("main has no published release for the selected election")
    baseline = _version_number(base.release_version, current.election_id)
    proposed = _version_number(current.release_version, current.election_id)
    request = current.publication_request
    retain = (
        request is not None
        and request.issue_number == issue_number
        and request.previous_release_sha == previous_release_sha
        and proposed > baseline
        and current.release_version not in occupied_versions
    )
    occupied_numbers = [
        int(match[1])
        for version in occupied_versions
        if (
            match := re.fullmatch(
                re.escape(current.election_id.removeprefix("wa-")) + r"\.([0-9]+)", version
            )
        )
    ]
    number = proposed if retain else max([baseline, *occupied_numbers]) + 1
    version = f"{current.election_id.removeprefix('wa-')}.{number}"
    declaration = current.model_copy(
        update={
            "source_panel_id": registry.id,
            "source_panel_hash": build_panel_snapshot(registry).panel_hash,
            "source_registry_hash": source_registry_hash(registry),
            "release_version": version,
            "bundle_id": f"{current.election_id}-{version}",
            "publication_request": PublicationRequest(
                issue_number=issue_number,
                previous_release_sha=previous_release_sha,
                inputs=hash_release_inputs(resolved.inputs),
            ),
        }
    )
    if version != current.release_version:
        declaration = declaration.model_copy(
            update={"git_commit": None, "release_manifest_sha256": None, "bundle_sha256": None}
        )
    site = resolved.site.model_copy(
        update={"elections": [declaration, *resolved.site.elections[1:]]}
    )
    path = repository / site_manifest_path
    # Preserve all archive declaration values and optional pins.
    raw = read_yaml(path)
    raw["elections"][0] = declaration.model_dump(mode="json", exclude_unset=True)
    descriptor, temporary = tempfile.mkstemp(prefix=".site-", dir=path.parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            stream.write(yaml.safe_dump(raw, sort_keys=False))
        os.replace(temporary, path)
    finally:
        Path(temporary).unlink(missing_ok=True)
    return ResolvedRelease(site, declaration, resolved.inputs, release_archive_name(version))


_RELEASE_PREFIXES = ("src/", "data/", "config/", "scripts/", ".github/workflows/")
_RELEASE_FILES = frozenset(
    {
        "Makefile",
        "cliff.toml",
        "pyproject.toml",
        "uv.lock",
        "package.json",
        "package-lock.json",
        "wrangler.jsonc",
        "wrangler.toml",
    }
)


def validate_release_request(
    current: ResolvedRelease,
    *,
    base: SiteManifest,
    changed_paths: tuple[str, ...],
    verified_unpublished_base_sha: str | None = None,
) -> bool:
    """Fail closed on stale byte bindings and unreviewed release-affecting changes."""
    request = current.current.publication_request
    if request is not None and request.inputs != hash_release_inputs(current.inputs):
        raise ValueError("publication request has stale input bindings; prepare it again")
    base_current = base.elections[0]
    changed = current.site != base
    affects_release = any(
        path.startswith(_RELEASE_PREFIXES) or path in _RELEASE_FILES for path in changed_paths
    )
    if not changed and not affects_release:
        return False
    if request is None:
        raise ValueError("release-affecting changes require a fresh publication request")
    if current.current.election_id != base_current.election_id:
        raise ValueError("publication request cannot change the selected election")
    if _version_number(
        current.current.release_version, current.current.election_id
    ) <= _version_number(base_current.release_version, base_current.election_id):
        raise ValueError(
            "publication request requires a release version increment; prepare it again"
        )
    if verified_unpublished_base_sha is not None:
        prior_request = base_current.publication_request
        if (
            prior_request is None
            or prior_request.issue_number != request.issue_number
            or prior_request.previous_release_sha != verified_unpublished_base_sha
            or request.previous_release_sha != verified_unpublished_base_sha
        ):
            raise ValueError(
                "unpublished base recovery requires the same owner and published boundary"
            )
    if base_current.publication_request == request and verified_unpublished_base_sha is None:
        raise ValueError("release-affecting changes require a fresh publication request")
    if (
        base_current.git_commit is not None
        and request.previous_release_sha != base_current.git_commit
    ):
        raise ValueError("publication request previous release boundary is stale")
    return True
