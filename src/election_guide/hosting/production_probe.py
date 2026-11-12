"""Live, single-hop HTTP requests against the deployed production host.

Deliberately does not follow redirects: the O14 route contract checks need
each hop's own status code and `Location` header — `/` returning exactly
`307` versus a retired PDF path returning exactly `301` — not the page a
browser eventually lands on. `election_guide.collection.http.fetch_http`
chases redirects to their destination for source collection and is not a fit
here for the same reason.
"""

from __future__ import annotations

import hashlib
import http.client
import urllib.error
import urllib.request
from datetime import UTC, datetime
from email.message import Message
from time import monotonic
from typing import Literal
from urllib.parse import urljoin, urlsplit

from election_guide.hosting.models import DeploymentManifest, SiteManifest
from election_guide.hosting.presentation import (
    verify_copied_release_status,
    verify_page_presentation,
    verify_presentation_identity,
)
from election_guide.hosting.production_check import (
    MANIFEST_PATH,
    CommitCheck,
    DataFreshnessCheck,
    Observation,
    PresentationAssetCheck,
    ProductionCheckReport,
    RequestDiagnostics,
    RouteCheck,
    RouteCheckResult,
    evaluate_archive_index,
    evaluate_deployment_contract,
    evaluate_manifest,
    evaluate_release_manifest,
    plan_presentation_assets,
    plan_publication_route_checks,
    plan_route_checks,
    presentation_request_path,
    release_manifest_check,
)
from election_guide.hosting.supplement_pages import verify_page_supplement
from election_guide.hosting.supplements import (
    HistoricalPrecinctSupplement,
    verify_served_precinct_supplement,
)
from election_guide.release.models import ReleaseManifest, ReleaseStatus

USER_AGENT = (
    "SeattleElectionGuide-ProductionCheck/1 (+https://github.com/shaug/seattle-election-guide)"
)


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(  # type: ignore[override]
        self, req: object, fp: object, code: int, msg: str, headers: object, newurl: str
    ) -> None:
        return None


_OPENER = urllib.request.build_opener(_NoRedirect)

# Every way a request can fail short of a response with a status to report.
# `http.client.HTTPException` subclasses neither `OSError` nor `URLError`, so
# it has to be named explicitly: `IncompleteRead` when a body stops short of
# its declared `Content-Length`, and `BadStatusLine` when the reply does not
# open with a parseable status line — which every request here is exposed to,
# body-reading or not, since the status line is parsed first.
_TRANSPORT_ERRORS = (urllib.error.URLError, TimeoutError, OSError, http.client.HTTPException)


def _request(url: str) -> urllib.request.Request:
    return urllib.request.Request(url, headers={"User-Agent": USER_AGENT})


def _location_path(location: str | None) -> str | None:
    """Reduce a `Location` header to its path, absolute or relative alike.

    The deployed Pages worker always redirects with an absolute URL
    (`_pages_worker`'s `redirectPath` calls `target.toString()`), confirmed
    live against production — `curl -I https://seattleelections.guide/`
    returns `location: https://seattleelections.guide/e/.../`, never a bare
    path. `RouteCheck.expected_location` is path-only, so comparing the raw
    header would fail every redirect check unconditionally.
    """
    if location is None:
        return None
    return urlsplit(location).path


def _request_timeout(timeout: float, deadline: float | None) -> float:
    if deadline is None:
        return timeout
    remaining = deadline - monotonic()
    if remaining <= 0:
        raise TimeoutError("production confirmation deadline exceeded")
    return min(timeout, 15.0, remaining)


def probe(
    base_url: str, check: RouteCheck, *, timeout: float, deadline: float | None = None
) -> Observation:
    """Make one unfollowed request and report exactly what came back."""
    return _fetch_body(base_url, check.path, timeout=timeout, deadline=deadline, read_body=False)[0]


def _framing_headers(headers: Message | None) -> dict[str, str]:
    """Only normalized known framing values; no arbitrary headers or parameters."""
    result: dict[str, str] = {}
    for name in ("Content-Length", "Content-Type", "Content-Encoding", "Transfer-Encoding"):
        try:
            value = headers.get(name) if headers is not None else None
        except Exception:
            continue
        if not isinstance(value, str) or len(value) > 256:
            continue
        value = value.strip().lower()
        if name == "Content-Length":
            if value.isascii() and value.isdigit() and len(value) <= 20:
                result[name.lower()] = str(int(value))
        elif name == "Content-Type":
            media_type = value.split(";", 1)[0].strip()
            if media_type in {
                "application/json",
                "text/html",
                "text/plain",
                "application/octet-stream",
            }:
                result[name.lower()] = media_type
        else:
            codings = [coding.strip() for coding in value.split(",")]
            if codings and all(
                c in {"identity", "gzip", "br", "deflate", "zstd", "chunked"} for c in codings
            ):
                result[name.lower()] = ", ".join(codings)
    return result


def _request_diagnostics(
    started_at: datetime,
    start: float,
    phase: Literal["open", "body", "complete"],
    response_status: int | None,
    headers: Message | None,
    headers_at: float | None,
    body_start: float | None,
    body: bytes | None = None,
    error: BaseException | None = None,
) -> RequestDiagnostics | None:
    """Diagnostic failures never replace the existing transport outcome."""
    try:
        end = monotonic()
        safe_headers = _framing_headers(headers)
        partial = getattr(error, "partial", None)
        types: list[str] = []
        seen: set[int] = set()
        cause = error
        while isinstance(cause, BaseException) and id(cause) not in seen and len(types) < 4:
            seen.add(id(cause))
            types.append(type(cause).__name__[:80])
            cause = cause.__cause__ or cause.__context__ or getattr(cause, "reason", None)
        return RequestDiagnostics(
            started_at=started_at,
            elapsed_seconds=max(0, end - start),
            headers_seconds=None if headers_at is None else max(0, headers_at - start),
            body_seconds=None if body_start is None else max(0, end - body_start),
            phase=phase,
            response_status=response_status,
            response_headers=safe_headers,
            expected_bytes=int(safe_headers["content-length"])
            if "content-length" in safe_headers
            else None,
            received_bytes=len(body)
            if body is not None
            else len(partial)
            if isinstance(partial, bytes)
            else None,
            partial_sha256=hashlib.sha256(partial).hexdigest()
            if isinstance(partial, bytes)
            else None,
            exception_types=tuple(types),
        )
    except Exception:
        return None


def fetch_manifest_body(
    base_url: str, *, timeout: float, deadline: float | None = None
) -> tuple[Observation, bytes | None]:
    """Fetch `/deployment-manifest.json`, returning its body only on a 200."""
    return _fetch_body(base_url, MANIFEST_PATH, timeout=timeout, deadline=deadline)


def _fetch_body(
    base_url: str,
    path: str,
    *,
    timeout: float,
    deadline: float | None = None,
    read_body: bool = True,
) -> tuple[Observation, bytes | None]:
    url = urljoin(base_url, path)
    started_at, start = datetime.now(UTC), monotonic()
    phase: Literal["open", "body", "complete"] = "open"
    response_status: int | None = None
    headers: Message | None = None
    headers_at: float | None = None
    body_start: float | None = None
    try:
        with _OPENER.open(_request(url), timeout=_request_timeout(timeout, deadline)) as response:
            headers_at = monotonic()
            response_status, headers = response.status, response.headers
            body = None
            if read_body:
                phase, body_start = "body", monotonic()
                body = response.read()
            raw_location = response.headers.get("Location")
            observation = Observation(
                status=response.status,
                location=_location_path(raw_location),
                raw_location=raw_location,
                diagnostics=_request_diagnostics(
                    started_at,
                    start,
                    "complete",
                    response_status,
                    headers,
                    headers_at,
                    body_start,
                    body,
                ),
            )
            return observation, body
    except urllib.error.HTTPError as error:
        raw_location = error.headers.get("Location")
        return Observation(
            status=error.code,
            location=_location_path(raw_location),
            raw_location=raw_location,
            diagnostics=_request_diagnostics(
                started_at, start, "open", error.code, error.headers, monotonic(), None, error=error
            ),
        ), None
    except _TRANSPORT_ERRORS as error:
        return Observation(
            error=str(error),
            diagnostics=_request_diagnostics(
                started_at,
                start,
                phase,
                response_status,
                headers,
                headers_at,
                body_start,
                error=error,
            ),
        ), None


def fetch_asset_body(
    base_url: str, path: str, *, timeout: float
) -> tuple[Observation, bytes | None]:
    """Read a first-party asset using the same unfollowed production probe transport."""
    return _fetch_body(base_url, path, timeout=timeout)


def _check_presentation_assets(
    base_url: str, manifest: DeploymentManifest, *, timeout: float, deadline: float | None
) -> tuple[PresentationAssetCheck, ...]:
    planned = plan_presentation_assets(manifest)
    bodies: dict[str, bytes] = {}
    checks: dict[str, PresentationAssetCheck] = {}
    for path in planned:
        request_path = presentation_request_path(path)
        observation, body = _fetch_body(base_url, request_path, timeout=timeout, deadline=deadline)
        digest = hashlib.sha256(body).hexdigest() if body is not None else None
        expected = manifest.assets.get(path)
        errors: list[str] = []
        if observation.status != 200 or body is None:
            errors.append(f"presentation asset is unavailable: {path}")
        elif expected is None or digest != expected:
            errors.append(f"presentation asset hash differs: {path}")
        else:
            bodies[path] = body
        checks[path] = PresentationAssetCheck(
            path=path,
            request_path=request_path,
            expected_sha256=expected,
            observed_sha256=digest,
            observation=observation,
            errors=tuple(errors),
        )

    def add_error(path: str, error: ValueError) -> None:
        checks[path] = checks[path].model_copy(
            update={"errors": (*checks[path].errors, str(error))}
        )

    authenticated: dict[str, tuple[ReleaseStatus, ReleaseManifest]] = {}
    for election in manifest.elections:
        path = f"e/{election.election_id}/release-manifest.json"
        status_path = f"e/{election.election_id}/release-status.json"
        if path not in bodies or status_path not in bodies:
            continue
        try:
            if checks[path].observed_sha256 != election.release_manifest_sha256:
                raise ValueError("presentation release manifest differs from archive identity")
            release_manifest = ReleaseManifest.model_validate_json(bodies[path])
        except ValueError as error:
            add_error(path, error)
            continue
        try:
            status = verify_copied_release_status(bodies[status_path], release_manifest)
            if (
                status.election_id != election.election_id
                or status.git_commit != election.git_commit
                or status.release_version != election.release_version
                or status.source_panel_id != election.source_panel_id
                or status.source_panel_hash != election.source_panel_hash
                or status.source_registry_hash != election.source_registry_hash
            ):
                raise ValueError("presentation release status differs from deployment")
            authenticated[election.election_id] = status, release_manifest
        except ValueError as error:
            add_error(status_path, error)
    if manifest.current_election_id in authenticated:
        current_status = authenticated[manifest.current_election_id][0]
        for election in manifest.elections:
            if election.election_id not in authenticated:
                continue
            try:
                verify_presentation_identity(
                    election, authenticated[election.election_id][1], current_status
                )
            except ValueError as error:
                add_error(f"e/{election.election_id}/release-manifest.json", error)
    supplements: dict[str, HistoricalPrecinctSupplement] = {}
    if manifest.current_election_id in authenticated:
        source_git_commit = authenticated[manifest.current_election_id][0].git_commit
        for election in manifest.elections:
            provenance = election.precinct_supplement
            if provenance is None or election.election_id not in authenticated:
                continue
            path = provenance.artifact_path
            if path not in bodies:
                continue
            try:
                supplements[election.election_id] = verify_served_precinct_supplement(
                    bodies[path],
                    expected_sha256=provenance.artifact_sha256,
                    provenance=provenance,
                    archive_manifest=authenticated[election.election_id][1],
                    archive_git_commit=election.git_commit,
                    source_git_commit=source_git_commit,
                )
            except ValueError as error:
                add_error(path, error)
    for path, presentation in planned.items():
        if presentation is not None and path in bodies:
            try:
                document = bodies[path].decode("utf-8")
                verify_page_presentation(document, presentation)
                election = next(
                    e for e in manifest.elections if path.startswith(f"e/{e.election_id}/")
                )
                root = f"e/{election.election_id}/"
                verify_page_supplement(
                    document,
                    election.precinct_supplement,
                    supplements.get(election.election_id),
                    require_contract=(
                        election.precinct_supplement is not None
                        and path in {root + "index.html", root + "comparisons/index.html"}
                    ),
                )
            except ValueError as error:
                add_error(path, error)
    return tuple(checks.values())


def run_production_check(
    base_url: str,
    *,
    expected_git_commit: str | None,
    timeout: float,
    active_window: bool = False,
    checked_at: datetime | None = None,
    site_manifest: SiteManifest | None = None,
    deadline: float | None = None,
) -> ProductionCheckReport:
    """Check served routes, optionally against an explicitly expected release.

    Route checks and the commit comparison only run once the manifest itself
    is confirmed healthy and parseable — there is no current election to
    check routes for otherwise, and reporting a live-and-serving-something
    site as commit-mismatched would blame the wrong check.
    """
    if site_manifest is not None and expected_git_commit is None:
        raise ValueError("a publication contract requires an expected Git commit")
    observed_at = checked_at or datetime.now(UTC)
    manifest_observation, manifest_body = fetch_manifest_body(
        base_url, timeout=timeout, deadline=deadline
    )
    manifest_result, manifest, manifest_parse_error = evaluate_manifest(
        manifest_observation, manifest_body
    )
    if manifest is None:
        return ProductionCheckReport(
            base_url=base_url,
            checked_at=observed_at,
            manifest=manifest_result,
            manifest_parse_error=manifest_parse_error,
        )

    deployment_contract = (
        None
        if site_manifest is None or expected_git_commit is None
        else evaluate_deployment_contract(
            site_manifest,
            manifest,
            expected_git_commit=expected_git_commit,
        )
    )

    current = next(
        election
        for election in manifest.elections
        if election.election_id == manifest.current_election_id
    )
    release_result = None
    release_manifest = None
    release_parse_error = None
    if active_window:
        release_check = release_manifest_check(manifest.current_election_id)
        release_observation, release_body = _fetch_body(
            base_url, release_check.path, timeout=timeout, deadline=deadline
        )
        release_result, release_manifest, release_parse_error = evaluate_release_manifest(
            release_check, release_observation, release_body
        )
    archive_index = None
    if site_manifest is None:
        route_checks = plan_route_checks(
            manifest.current_election_id, canonical_origin=base_url.rstrip("/")
        )
        route_results = tuple(
            RouteCheckResult(
                check=check, observed=probe(base_url, check, timeout=timeout, deadline=deadline)
            )
            for check in route_checks
        )
    elif (
        deployment_contract is not None and deployment_contract.representative_race_path is not None
    ):
        route_checks = plan_publication_route_checks(
            site_manifest,
            representative_race_path=deployment_contract.representative_race_path,
        )
        archive_observation, archive_body = _fetch_body(
            base_url, "/e/", timeout=timeout, deadline=deadline
        )
        archive_index = evaluate_archive_index(site_manifest, archive_observation, archive_body)
        route_results = tuple(
            archive_index.route
            if check.path == "/e/"
            else RouteCheckResult(
                check=check,
                observed=probe(base_url, check, timeout=timeout, deadline=deadline),
            )
            for check in route_checks
        )
    else:
        route_results = ()
    return ProductionCheckReport(
        base_url=base_url,
        checked_at=observed_at,
        manifest=manifest_result,
        deployment_contract=deployment_contract,
        archive_index=archive_index,
        current_election_id=manifest.current_election_id,
        release_manifest=release_result,
        release_manifest_parse_error=release_parse_error,
        route_results=route_results,
        commit=(
            None
            if expected_git_commit is None
            else CommitCheck(expected=expected_git_commit, observed=current.git_commit)
        ),
        data_freshness=(
            None
            if release_manifest is None
            else DataFreshnessCheck(
                published_at=release_manifest.generated_at,
                checked_at=observed_at,
            )
        ),
        presentation_assets=(
            _check_presentation_assets(base_url, manifest, timeout=timeout, deadline=deadline)
            if site_manifest is not None
            and site_manifest.current_presentation
            and deployment_contract is not None
            and deployment_contract.ok
            else ()
        ),
    )
