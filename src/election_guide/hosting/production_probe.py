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
from urllib.parse import urljoin, urlsplit

from election_guide.hosting.production_check import (
    MANIFEST_PATH,
    CommitCheck,
    Observation,
    ProductionCheckReport,
    RouteCheck,
    RouteCheckResult,
    evaluate_manifest,
    plan_route_checks,
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
            return Observation(
                status=response.status, location=_location_path(response.headers.get("Location"))
            )
    except urllib.error.HTTPError as error:
        return Observation(
            status=error.code, location=_location_path(error.headers.get("Location"))
        )
    except _TRANSPORT_ERRORS as error:
        return Observation(error=str(error))


def fetch_manifest_body(base_url: str, *, timeout: float) -> tuple[Observation, bytes | None]:
    """Fetch `/deployment-manifest.json`, returning its body only on a 200."""
    url = urljoin(base_url, MANIFEST_PATH)
    try:
        with _OPENER.open(_request(url), timeout=timeout) as response:
            body = response.read()
            observation = Observation(
                status=response.status, location=_location_path(response.headers.get("Location"))
            )
            return observation, body
    except urllib.error.HTTPError as error:
        return Observation(
            status=error.code, location=_location_path(error.headers.get("Location"))
        ), None
    except _TRANSPORT_ERRORS as error:
        return Observation(error=str(error)), None


def run_production_check(
    base_url: str, *, expected_git_commit: str, timeout: float
) -> ProductionCheckReport:
    """Fetch the deployment manifest, then check the routes and commit it implies.

    Route checks and the commit comparison only run once the manifest itself
    is confirmed healthy and parseable — there is no current election to
    check routes for otherwise, and reporting a live-and-serving-something
    site as commit-mismatched would blame the wrong check.
    """
    manifest_observation, manifest_body = fetch_manifest_body(base_url, timeout=timeout)
    manifest_result, manifest, manifest_parse_error = evaluate_manifest(
        manifest_observation, manifest_body
    )
    if manifest is None:
        return ProductionCheckReport(
            manifest=manifest_result, manifest_parse_error=manifest_parse_error
        )

    current = next(
        election
        for election in manifest.elections
        if election.election_id == manifest.current_election_id
    )
    route_results = tuple(
        RouteCheckResult(check=check, observed=probe(base_url, check, timeout=timeout))
        for check in plan_route_checks(manifest.current_election_id)
    )
    return ProductionCheckReport(
        manifest=manifest_result,
        current_election_id=manifest.current_election_id,
        route_results=route_results,
        commit=CommitCheck(expected=expected_git_commit, observed=current.git_commit),
    )
