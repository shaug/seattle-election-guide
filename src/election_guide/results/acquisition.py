"""Explicit official acquisition; capture never implies tally admission or publication."""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, date, datetime
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Literal

from election_guide.authorities.registry import read_authority_registry
from election_guide.collection.http import HttpArtifact, HttpFetchFailure, fetch_results_http
from election_guide.evidence.models import CaptureRequest, UnavailableManifest, UnavailableRequest
from election_guide.evidence.storage import (
    read_capture_manifest,
    record_capture,
    record_unavailable,
)
from election_guide.results.preliminary import parse_preliminary_feed

# Exact offered resources retained in #535 and independently rechecked for
# #696. This is not endpoint discovery, a URL template or a client fallback.
FEEDS: dict[str, tuple[str, str, Literal["county", "statewide"]]] = {
    "county": (
        "king-county-elections",
        "https://results.votewa.gov/results/public/api/elections/king-county-wa/20261103/data",
        "county",
    ),
    "statewide": (
        "wa-secretary-of-state",
        "https://results.votewa.gov/cdn/results/washington/export-20261103.json",
        "statewide",
    ),
}


class PreliminaryAcquisitionError(ValueError):
    """A real failed attempt with its normal immutable unavailable manifest."""

    def __init__(self, message: str, *, manifest_path: Path) -> None:
        super().__init__(message)
        self.manifest_path = manifest_path


def check_preliminary_access(source: str, *, repository_root: Path) -> None:
    if source not in FEEDS:
        raise ValueError("preliminary source must be county or statewide")
    authority_id, url, _ = FEEDS[source]
    _check_access_hold(
        repository_root / "data/manifests/evidence", authority_id=authority_id, url=url
    )


def acquire_preliminary(
    source: str,
    *,
    repository_root: Path,
    fetcher: Callable[[str], HttpArtifact] | None = None,
    clock: Callable[[], datetime] | None = None,
) -> Path:
    """Fetch one declared source once and retain a capture or actual failure.

    No automatic retry, alternate HTTP client, credentials or status inference.
    This interface is suitable for an explicitly enabled scheduler; admission,
    exact mappings and normal protected publication are separate operations.
    """
    if source not in FEEDS:
        raise ValueError("preliminary source must be county or statewide")
    authority_id, url, format = FEEDS[source]
    registry = read_authority_registry(repository_root / "config/authorities/default.yaml")
    if authority_id not in registry.authority_ids():
        raise ValueError("preliminary source authority is not registered")
    fetch = fetch_results_http if fetcher is None else fetcher
    now = (lambda: datetime.now(UTC)) if clock is None else clock
    manifest_dir = repository_root / "data/manifests/evidence"
    _check_access_hold(manifest_dir, authority_id=authority_id, url=url)
    artifact: HttpArtifact | None = None
    retrieved_at: datetime | None = None
    try:
        artifact = fetch(url)
        retrieved_at = now()
        if artifact.canonical_url != url or artifact.redirect_chain:
            raise ValueError("preliminary source returned an unreviewed redirect")
        feed = parse_preliminary_feed(artifact.content, format=format)
        if feed.election_date != date(2026, 11, 3):
            raise ValueError("preliminary source belongs to a different election")
    except ValueError as error:
        status = error.response_status if isinstance(error, HttpFetchFailure) else None
        if artifact is not None:
            status = artifact.status
        failure = record_unavailable(
            UnavailableRequest(
                source_id=authority_id,
                requested_url=url,
                canonical_url=url if artifact is not None else None,
                retrieved_at=now() if retrieved_at is None else retrieved_at,
                http_status=status,
                media_type=None if artifact is None else artifact.media_type,
                redistribution="permitted",
                redistribution_note="Official public election-results export; no voter records.",
                unavailable_reason=str(error),
            ),
            manifest_dir,
        )
        raise PreliminaryAcquisitionError(
            f"preliminary acquisition stopped: {error}; evidence: {failure}",
            manifest_path=failure,
        ) from error

    storage_root = repository_root / "data/evidence/official"
    with TemporaryDirectory(prefix="seg-preliminary-") as temporary:
        body = Path(temporary) / "results.json"
        body.write_bytes(artifact.content)
        return record_capture(
            CaptureRequest(
                source_id=authority_id,
                requested_url=url,
                canonical_url=artifact.canonical_url,
                retrieved_at=retrieved_at,
                http_status=artifact.status,
                media_type=artifact.media_type,
                title=f"wa-2026-general preliminary results ({source} JSON export)",
                capture_method="json",
                redistribution="permitted",
                redistribution_note="Official public election-results export; no voter records.",
            ),
            body,
            storage_root,
            manifest_dir,
            repository_storage_root=storage_root,
        )


def _check_access_hold(manifest_dir: Path, *, authority_id: str, url: str) -> None:
    """A later autonomous tick cannot silently retry a held operation."""
    observations = [(read_capture_manifest(path), path) for path in manifest_dir.glob("*.json")]
    matching = [
        (item, path)
        for item, path in observations
        if item.source_id == authority_id and item.requested_url == url
    ]
    if not matching:
        return
    latest, path = max(
        matching,
        key=lambda pair: (pair[0].retrieved_at, isinstance(pair[0], UnavailableManifest)),
    )
    status = latest.http_status
    if (
        isinstance(latest, UnavailableManifest)
        and status is not None
        and (status in {401, 403} or 300 <= status < 400)
    ):
        raise ValueError(
            f"preliminary acquisition held after HTTP {status}: {path}; "
            "requires a legitimate reviewed access disposition, not another tick or client"
        )
