"""Behavior tests for the live HTTP transport behind the production check (O14).

Runs a real loopback HTTP server so these exercise actual socket and header
behavior rather than mocking `urllib` internals — in particular, that a
redirect response is observed at its own hop rather than silently followed.
"""

from __future__ import annotations

import threading
from collections.abc import Iterator
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from election_guide.hosting.production_check import RouteCheck
from election_guide.hosting.production_probe import fetch_manifest_body, probe, run_production_check

COMMIT = "a" * 40
MANIFEST_BODY = (
    b'{"schema_version": "2.0", "canonical_origin": "https://seattleelections.guide", '
    b'"current_election_id": "wa-2026-primary", "elections": [{"election_id": '
    b'"wa-2026-primary", "bundle_id": "wa-2026-primary-1", "release_version": "primary.1", '
    b'"git_commit": "' + COMMIT.encode() + b'", "source_panel_id": "panel", '
    b'"source_panel_hash": "' + (b"b" * 64) + b'", '
    b'"release_manifest_sha256": "' + (b"c" * 64) + b'"}], '
    b'"assets": {"e/index.html": "' + (b"d" * 64) + b'"}}'
)


class _Handler(BaseHTTPRequestHandler):
    """Redirects with an absolute URL, matching the deployed Pages worker.

    `_pages_worker`'s `redirectPath` calls `Response.redirect(target.toString(), status)`,
    which always emits an absolute URL — confirmed live against production.
    A fixture that sent a bare path here previously masked
    `production_probe`'s comparison bug (issue #222 review).
    """

    def log_message(self, format: str, *args: object) -> None:
        pass

    def _absolute(self, path: str) -> str:
        return f"http://{self.headers.get('Host')}{path}"

    def do_GET(self) -> None:
        if self.path == "/":
            self.send_response(307)
            self.send_header("Location", self._absolute("/e/wa-2026-primary/"))
            self.end_headers()
        elif self.path == "/e/wa-2026-primary/":
            self.send_response(200)
            self.end_headers()
        elif self.path == "/e/wa-2026-primary/voter-guide.pdf":
            self.send_response(301)
            self.send_header("Location", self._absolute("/e/wa-2026-primary/"))
            self.end_headers()
        elif self.path == "/deployment-manifest.json":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(MANIFEST_BODY)
        else:
            self.send_response(404)
            self.end_headers()


class _BrokenManifestHandler(BaseHTTPRequestHandler):
    def log_message(self, format: str, *args: object) -> None:
        pass

    def do_GET(self) -> None:
        self.send_response(500)
        self.end_headers()


class _TruncatedManifestHandler(BaseHTTPRequestHandler):
    """Declares a body longer than it sends, then drops the connection."""

    def log_message(self, format: str, *args: object) -> None:
        pass

    def do_GET(self) -> None:
        self.send_response(200)
        self.send_header("Content-Length", "1000")
        self.end_headers()
        self.wfile.write(b"short")
        self.close_connection = True


def _start(handler: type[BaseHTTPRequestHandler]) -> Iterator[str]:
    httpd = HTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{httpd.server_port}"
    finally:
        httpd.shutdown()
        thread.join()


@pytest.fixture
def server() -> Iterator[str]:
    yield from _start(_Handler)


@pytest.fixture
def broken_manifest_server() -> Iterator[str]:
    yield from _start(_BrokenManifestHandler)


@pytest.fixture
def truncated_manifest_server() -> Iterator[str]:
    yield from _start(_TruncatedManifestHandler)


def test_probe_observes_a_redirect_without_following_it(server: str) -> None:
    check = RouteCheck(
        name="home redirect", path="/", expected_status=307, expected_location="/e/wa-2026-primary/"
    )

    observed = probe(server, check, timeout=5)

    assert observed.status == 307
    assert observed.location == "/e/wa-2026-primary/"
    assert observed.error is None


def test_probe_normalizes_an_absolute_location_to_a_bare_path(server: str) -> None:
    """The deployed worker always redirects with an absolute URL; a route
    check's `expected_location` is path-only, so the observed location must
    be reduced to a path before either side can be compared."""
    check = RouteCheck(
        name="home redirect", path="/", expected_status=307, expected_location="/e/wa-2026-primary/"
    )

    observed = probe(server, check, timeout=5)

    assert observed.location is not None
    assert not observed.location.startswith("http")
    assert observed.location == "/e/wa-2026-primary/"


def test_probe_observes_a_permanent_redirect(server: str) -> None:
    check = RouteCheck(
        name="legacy PDF redirect",
        path="/e/wa-2026-primary/voter-guide.pdf",
        expected_status=301,
        expected_location="/e/wa-2026-primary/",
    )

    observed = probe(server, check, timeout=5)

    assert observed.status == 301
    assert observed.location == "/e/wa-2026-primary/"


def test_probe_observes_a_plain_200(server: str) -> None:
    check = RouteCheck(
        name="current election guide", path="/e/wa-2026-primary/", expected_status=200
    )

    observed = probe(server, check, timeout=5)

    assert observed.status == 200
    assert observed.location is None


def test_probe_observes_a_404(server: str) -> None:
    check = RouteCheck(name="anything", path="/does-not-exist", expected_status=200)

    observed = probe(server, check, timeout=5)

    assert observed.status == 404


def test_probe_reports_a_connection_failure_without_raising() -> None:
    check = RouteCheck(name="current election guide", path="/e/x/", expected_status=200)

    observed = probe("http://127.0.0.1:1", check, timeout=1)

    assert observed.status is None
    assert observed.error is not None


def test_fetch_manifest_body_returns_the_status_and_bytes(server: str) -> None:
    observation, body = fetch_manifest_body(server, timeout=5)

    assert observation.status == 200
    assert body == MANIFEST_BODY


def test_fetch_manifest_body_reports_a_non_200_without_a_body(broken_manifest_server: str) -> None:
    observation, body = fetch_manifest_body(broken_manifest_server, timeout=5)

    assert observation.status == 500
    assert body is None


def test_fetch_manifest_body_reports_a_connection_failure() -> None:
    observation, body = fetch_manifest_body("http://127.0.0.1:1", timeout=1)

    assert observation.status is None
    assert observation.error is not None
    assert body is None


def test_fetch_manifest_body_reports_a_truncated_response_instead_of_crashing(
    truncated_manifest_server: str,
) -> None:
    """A response shorter than its own declared Content-Length raises
    http.client.IncompleteRead — not an OSError or URLError — and must
    still come back as a reported failure rather than an uncaught raise."""
    observation, body = fetch_manifest_body(truncated_manifest_server, timeout=5)

    assert observation.status is None
    assert observation.error is not None
    assert body is None


def test_run_production_check_against_a_fully_healthy_deployment_is_ok(server: str) -> None:
    report = run_production_check(server, expected_git_commit=COMMIT, timeout=5)

    assert report.ok
    assert report.current_election_id == "wa-2026-primary"
    assert len(report.route_results) == 3


def test_run_production_check_catches_a_commit_mismatch(server: str) -> None:
    report = run_production_check(server, expected_git_commit="f" * 40, timeout=5)

    assert not report.ok
    assert report.commit is not None
    assert report.commit.observed == COMMIT


def test_run_production_check_catches_a_404_on_a_route(server: str) -> None:
    class _MissingGuideHandler(_Handler):
        def do_GET(self) -> None:
            if self.path == "/e/wa-2026-primary/":
                self.send_response(404)
                self.end_headers()
            else:
                super().do_GET()

    httpd = HTTPServer(("127.0.0.1", 0), _MissingGuideHandler)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    try:
        base_url = f"http://127.0.0.1:{httpd.server_port}"
        report = run_production_check(base_url, expected_git_commit=COMMIT, timeout=5)
    finally:
        httpd.shutdown()
        thread.join()

    assert not report.ok
    failing = [result for result in report.route_results if not result.ok]
    assert len(failing) == 1
    assert failing[0].check.name == "current election guide"


def test_run_production_check_stops_at_a_failed_manifest_fetch() -> None:
    report = run_production_check("http://127.0.0.1:1", expected_git_commit=COMMIT, timeout=1)

    assert not report.ok
    assert report.route_results == ()
    assert report.commit is None
