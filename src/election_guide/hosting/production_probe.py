"""Live, single-hop HTTP requests against the deployed production host.

Deliberately does not follow redirects: the O14 route contract checks need
each hop's own status code and `Location` header — `/` returning exactly
`307` versus a retired PDF path returning exactly `301` — not the page a
browser eventually lands on. `election_guide.collection.http.fetch_http`
chases redirects to their destination for source collection and is not a fit
here for the same reason.
"""

from __future__ import annotations

import http.client
import urllib.error
import urllib.request
from datetime import UTC, datetime
from urllib.parse import urljoin, urlsplit

from election_guide.hosting.models import SiteManifest
from election_guide.hosting.production_check import (
    MANIFEST_PATH,
    CommitCheck,
    DataFreshnessCheck,
    Observation,
    ProductionCheckReport,
    RouteCheck,
    RouteCheckResult,
    evaluate_archive_index,
    evaluate_deployment_contract,
    evaluate_manifest,
    evaluate_release_manifest,
    plan_publication_route_checks,
    plan_route_checks,
    release_manifest_check,
)

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


def probe(base_url: str, check: RouteCheck, *, timeout: float) -> Observation:
    """Make one unfollowed request and report exactly what came back."""
    url = urljoin(base_url, check.path)
    try:
        with _OPENER.open(_request(url), timeout=timeout) as response:
            raw_location = response.headers.get("Location")
            return Observation(
                status=response.status,
                location=_location_path(raw_location),
                raw_location=raw_location,
            )
    except urllib.error.HTTPError as error:
        raw_location = error.headers.get("Location")
        return Observation(
            status=error.code,
            location=_location_path(raw_location),
            raw_location=raw_location,
        )
    except _TRANSPORT_ERRORS as error:
        return Observation(error=str(error))


def fetch_manifest_body(base_url: str, *, timeout: float) -> tuple[Observation, bytes | None]:
    """Fetch `/deployment-manifest.json`, returning its body only on a 200."""
    return _fetch_body(base_url, MANIFEST_PATH, timeout=timeout)


def _fetch_body(base_url: str, path: str, *, timeout: float) -> tuple[Observation, bytes | None]:
    url = urljoin(base_url, path)
    try:
        with _OPENER.open(_request(url), timeout=timeout) as response:
            body = response.read()
            raw_location = response.headers.get("Location")
            observation = Observation(
                status=response.status,
                location=_location_path(raw_location),
                raw_location=raw_location,
            )
            return observation, body
    except urllib.error.HTTPError as error:
        raw_location = error.headers.get("Location")
        return Observation(
            status=error.code,
            location=_location_path(raw_location),
            raw_location=raw_location,
        ), None
    except _TRANSPORT_ERRORS as error:
        return Observation(error=str(error)), None


def run_production_check(
    base_url: str,
    *,
    expected_git_commit: str,
    timeout: float,
    active_window: bool = False,
    checked_at: datetime | None = None,
    site_manifest: SiteManifest | None = None,
) -> ProductionCheckReport:
    """Fetch the deployment manifest, then check the routes and commit it implies.

    Route checks and the commit comparison only run once the manifest itself
    is confirmed healthy and parseable — there is no current election to
    check routes for otherwise, and reporting a live-and-serving-something
    site as commit-mismatched would blame the wrong check.
    """
    observed_at = checked_at or datetime.now(UTC)
    manifest_observation, manifest_body = fetch_manifest_body(base_url, timeout=timeout)
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
        if site_manifest is None
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
            base_url, release_check.path, timeout=timeout
        )
        release_result, release_manifest, release_parse_error = evaluate_release_manifest(
            release_check, release_observation, release_body
        )
    archive_index = None
    if site_manifest is None:
        route_checks = plan_route_checks(manifest.current_election_id)
        route_results = tuple(
            RouteCheckResult(check=check, observed=probe(base_url, check, timeout=timeout))
            for check in route_checks
        )
    elif (
        deployment_contract is not None and deployment_contract.representative_race_path is not None
    ):
        route_checks = plan_publication_route_checks(
            site_manifest,
            representative_race_path=deployment_contract.representative_race_path,
        )
        archive_observation, archive_body = _fetch_body(base_url, "/e/", timeout=timeout)
        archive_index = evaluate_archive_index(site_manifest, archive_observation, archive_body)
        route_results = tuple(
            archive_index.route
            if check.path == "/e/"
            else RouteCheckResult(
                check=check,
                observed=probe(base_url, check, timeout=timeout),
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
        commit=CommitCheck(expected=expected_git_commit, observed=current.git_commit),
        data_freshness=(
            None
            if release_manifest is None
            else DataFreshnessCheck(
                published_at=release_manifest.generated_at,
                checked_at=observed_at,
            )
        ),
    )
