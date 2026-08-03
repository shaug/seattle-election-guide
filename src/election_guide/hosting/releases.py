"""Resolve declared election releases against their published GitHub Releases.

The site manifest names a `release_version` for every election it serves, and the
archive for that version is expected to exist as a published GitHub Release. The
two drift silently otherwise: a version can be declared, built, and deployed
without its archive ever being published.

That published archive is also the only way to obtain a historical election's
bundle. Only the current election is built from source; older ones cannot be
rebuilt, because their pinned artifact hashes were produced by the rendering code
of their own time. So they are downloaded from their release and checked against
the hash the manifest pins.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import zipfile
from collections.abc import Iterable
from pathlib import Path, PurePosixPath
from typing import Any, cast

from election_guide.hosting.models import PublishedElection, SiteManifest
from election_guide.release.models import ARCHIVE_ROOT_DIR, release_archive_name

READ_CHUNK_SIZE = 1024 * 1024

# The repository publishes one release per election version, so this ceiling sits
# far above any real history while still bounding the query.
RELEASE_QUERY_LIMIT = 1000


def published_release_tags() -> frozenset[str]:
    """Tags of every published GitHub Release, read through the GitHub CLI.

    Drafts are excluded: a draft carries a tag name but publishes no archive.
    """
    command = [
        "gh",
        "release",
        "list",
        "--limit",
        str(RELEASE_QUERY_LIMIT),
        "--json",
        "tagName,isDraft",
    ]
    try:
        completed = subprocess.run(command, capture_output=True, text=True, check=False)
    except OSError as error:
        raise ValueError(
            "the GitHub CLI is required to list published releases: install `gh` "
            "(https://cli.github.com) and authenticate it"
        ) from error
    if completed.returncode != 0:
        detail = completed.stderr.strip() or completed.stdout.strip()
        raise ValueError(f"could not list published GitHub Releases: {detail}")
    return _published_tags(completed.stdout)


def _published_tags(payload: str) -> frozenset[str]:
    """Parse `gh release list --json tagName,isDraft` output into published tags."""
    releases: Any = json.loads(payload)
    if not isinstance(releases, list):
        raise ValueError("GitHub CLI returned a release list that is not an array")
    tags: set[str] = set()
    for entry in cast(list[Any], releases):
        if not isinstance(entry, dict):
            raise ValueError("GitHub CLI returned a release that is not an object")
        release = cast(dict[str, Any], entry)
        if "tagName" not in release:
            raise ValueError("GitHub CLI returned a release without a tag name")
        if release.get("isDraft"):
            continue
        tags.add(str(release["tagName"]))
    return frozenset(tags)


def verify_declared_releases_published(
    manifest: SiteManifest,
    published_tags: Iterable[str],
) -> None:
    """Reject a manifest declaring a release version with no published Release."""
    available = frozenset(published_tags)
    missing = [
        f"election {election.election_id!r} declares release version "
        f"{election.release_version!r}, but no published GitHub Release has that tag"
        for election in manifest.elections
        if election.release_version not in available
    ]
    if missing:
        raise ValueError("; ".join(missing))


def download_release_archive(declaration: PublishedElection, destination: Path) -> Path:
    """Download one published release's versioned ZIP into `destination`."""
    archive_name = release_archive_name(declaration.release_version)
    destination.mkdir(parents=True, exist_ok=True)
    archive_path = destination / archive_name
    if archive_path.exists():
        archive_path.unlink()
    command = [
        "gh",
        "release",
        "download",
        declaration.release_version,
        "--pattern",
        archive_name,
        "--dir",
        str(destination),
    ]
    try:
        completed = subprocess.run(command, capture_output=True, text=True, check=False)
    except OSError as error:
        raise ValueError(
            "the GitHub CLI is required to download a published release archive: install "
            "`gh` (https://cli.github.com) and authenticate it"
        ) from error
    if completed.returncode != 0:
        detail = completed.stderr.strip() or completed.stdout.strip()
        raise ValueError(
            f"could not download archive {archive_name!r} from release "
            f"{declaration.release_version!r}: {detail}"
        )
    if not archive_path.is_file():
        raise ValueError(
            f"release {declaration.release_version!r} published no archive named {archive_name!r}"
        )
    return archive_path


def materialize_released_bundle(declaration: PublishedElection, work_dir: Path) -> Path:
    """Download and unpack one election's published bundle.

    `bundle_sha256` is mandatory here rather than optional as it is elsewhere. A
    downloaded archive is remote input, and its own release manifest cannot vouch
    for it: whatever could replace the artifacts could replace their recorded
    hashes too. Staging verifies the unpacked tree against that pin, so an
    unpinned historical election must not resolve at all.
    """
    if declaration.bundle_sha256 is None:
        raise ValueError(
            f"election {declaration.election_id!r} must declare bundle_sha256 before its "
            "bundle can be resolved from a published release"
        )
    bundle_dir = work_dir / declaration.bundle_id
    if bundle_dir.exists():
        shutil.rmtree(bundle_dir)
    archive_path = download_release_archive(declaration, work_dir)
    _extract_bundle(archive_path, bundle_dir, declaration)
    return bundle_dir


def _extract_bundle(archive_path: Path, bundle_dir: Path, declaration: PublishedElection) -> None:
    """Extract the archive's single bundle root, rejecting unsafe member paths."""
    prefix = f"{ARCHIVE_ROOT_DIR}/"
    # A replaced, truncated, or CRC-corrupt download raises BadZipFile, which is
    # not a ValueError and would escape the command's error handling as a
    # traceback. Every archive-level rejection reads the same way instead.
    try:
        with zipfile.ZipFile(archive_path) as archive:
            members = [name for name in archive.namelist() if not name.endswith("/")]
            if not members:
                raise ValueError(f"release archive {archive_path.name!r} contains no files")
            outside = sorted(name for name in members if not name.startswith(prefix))
            if outside:
                raise ValueError(
                    f"release archive {archive_path.name!r} contains entries outside "
                    f"{ARCHIVE_ROOT_DIR!r}: {outside[:5]}"
                )
            for name in members:
                relative = PurePosixPath(name[len(prefix) :])
                if not relative.parts or relative.is_absolute() or ".." in relative.parts:
                    raise ValueError(
                        f"release archive {archive_path.name!r} contains an unsafe entry: {name!r}"
                    )
                target = bundle_dir / Path(*relative.parts)
                target.parent.mkdir(parents=True, exist_ok=True)
                with archive.open(name) as source, target.open("wb") as sink:
                    shutil.copyfileobj(source, sink, READ_CHUNK_SIZE)
    except zipfile.BadZipFile as error:
        raise ValueError(
            f"release archive {archive_path.name!r} for bundle {declaration.bundle_id!r} "
            f"is not a readable ZIP archive: {error}"
        ) from error
    if not (bundle_dir / "release-status.json").is_file():
        raise ValueError(
            f"bundle {declaration.bundle_id!r} archive has no release-status.json; "
            "it does not look like a release bundle"
        )
