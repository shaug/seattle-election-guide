"""Probe every cited source URL in the registry for link rot (O17).

Reuses `election_guide.collection.http.fetch_http` for the request itself: it
already tolerates redirects and enforces the public-DNS/HTTPS-safety rules
live collection relies on, so this check does not reinvent a second, laxer
HTTP client for reasoning about hostile or malformed responses.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass

from election_guide.collection.http import fetch_http
from election_guide.sources.models import SourceRegistry

DEFAULT_TIMEOUT_SECONDS = 15.0
DEFAULT_DELAY_SECONDS = 1.0


@dataclass(frozen=True)
class LinkCheckTarget:
    """One cited source URL, identified back to the source that cites it."""

    source_id: str
    source_name: str
    url: str


@dataclass(frozen=True)
class LinkCheckResult:
    target: LinkCheckTarget
    ok: bool
    error: str | None = None


def link_check_targets(registry: SourceRegistry) -> list[LinkCheckTarget]:
    """The one cited URL per source that stands for its evidence.

    A restricted source has no `canonical_url` --
    `Discovery.validate_publication_metadata` only requires one for a
    non-`access_restricted` status -- and is not fetchable by an
    unauthenticated check, so it is skipped rather than reported as rot.
    """
    targets = [
        LinkCheckTarget(
            source_id=source.id, source_name=source.name, url=source.discovery.canonical_url
        )
        for source in registry.sources
        if source.discovery.canonical_url is not None
    ]
    return sorted(targets, key=lambda target: target.source_id)


def check_link(url: str, *, timeout_seconds: float) -> tuple[bool, str | None]:
    """Fetch one URL, reporting success or the collection failure reason."""
    try:
        fetch_http(url, timeout_seconds=timeout_seconds)
    except ValueError as error:
        return False, str(error)
    return True, None


def run_link_check(
    registry: SourceRegistry,
    *,
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
    delay_seconds: float = DEFAULT_DELAY_SECONDS,
    sleep: Callable[[float], None] = time.sleep,
) -> list[LinkCheckResult]:
    """Check every cited URL one at a time, pausing between requests to stay polite."""
    targets = link_check_targets(registry)
    results: list[LinkCheckResult] = []
    for index, target in enumerate(targets):
        if index > 0 and delay_seconds > 0:
            sleep(delay_seconds)
        ok, error = check_link(target.url, timeout_seconds=timeout_seconds)
        results.append(LinkCheckResult(target=target, ok=ok, error=error))
    return results
