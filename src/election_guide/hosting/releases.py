"""Check that every declared election release has a published GitHub Release.

The site manifest names a `release_version` for every election it serves, and the
archive for that version is expected to exist as a published GitHub Release. The
two drift silently otherwise: a version can be declared, built, and deployed
without its archive ever being published.
"""

from __future__ import annotations

import json
import subprocess
from collections.abc import Iterable
from typing import Any, cast

from election_guide.hosting.models import SiteManifest

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
