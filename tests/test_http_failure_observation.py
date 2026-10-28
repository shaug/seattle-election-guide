"""Tiny fake-wire regressions for bounded, nonsecret failure observations."""

import socket
import ssl
import subprocess
from datetime import UTC, datetime
from io import BytesIO
from pathlib import Path
from types import SimpleNamespace

import pytest

import election_guide.collection.http as transport
import election_guide.collection.verification_runtime as runtime
from election_guide.collection.verification import (
    AutomaticResult,
    CoverageRecord,
    ElectionPlan,
    ElectionPolicy,
    SourcePolicy,
    VerificationPlan,
    VerificationPolicy,
)
from election_guide.sources.link_check import LinkCheckResult, LinkCheckTarget
from election_guide.sources.link_check_state import LinkCheckState
from election_guide.sources.link_rot_alert import confirmed_failures

PRIVATE = "PRIVATE_PATH_QUERY_HEADER_BODY"
URL = f"https://example.com/{PRIVATE}?ordinary={PRIVATE}#{PRIVATE}"


class _HeadersOnly(BytesIO):
    def read(self, size: int | None = -1) -> bytes:
        raise AssertionError("an HTTP error body must not be read")

    def read1(self, size: int | None = -1) -> bytes:
        raise AssertionError("an HTTP error body must not be read")


class _Peer:
    def __init__(self, response: bytes) -> None:
        self.response = response
        self.sent = bytearray()
        self.closed = False

    def settimeout(self, timeout: float) -> None:
        pass

    def connect(self, address: object) -> None:
        pass

    def getpeername(self) -> tuple[str, int]:
        return "93.184.216.34", 443

    def do_handshake(self) -> None:
        pass

    def sendall(self, data: bytes) -> None:
        self.sent.extend(data)

    def makefile(self, mode: str) -> BytesIO:
        assert mode == "rb"
        return _HeadersOnly(self.response)

    def close(self) -> None:
        self.closed = True


class _TLS:
    def wrap_socket(self, peer: _Peer, **kwargs: object) -> _Peer:
        return peer


def _wire(monkeypatch: pytest.MonkeyPatch, responses: list[bytes]) -> list[_Peer]:
    peers = [_Peer(response) for response in responses]
    remaining = iter(peers)

    def open_socket(*args: object) -> _Peer:
        return next(remaining)

    monkeypatch.setattr(transport.socket, "socket", open_socket)

    def resolve(host: str, *args: object, **kwargs: object) -> list[object]:
        address = "127.0.0.1" if host == "127.0.0.1" else "93.184.216.34"
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (address, 443))]

    monkeypatch.setattr(transport.socket, "getaddrinfo", resolve)
    monkeypatch.setattr(transport.ssl, "create_default_context", _TLS)
    return peers


def _response(status: int = 403, location: str | None = None) -> bytes:
    headers = f"Location: {location}\r\n" if location else ""
    return (
        f"HTTP/1.1 {status} Fixture\r\n{headers}"
        f"Set-Cookie: {PRIVATE}\r\nServer: {PRIVATE}\r\n"
        f"Content-Type: text/{PRIVATE}\r\n\r\n{PRIVATE}"
    ).encode()


def _error() -> ValueError:
    with pytest.raises(ValueError) as caught:
        transport.fetch_http(URL)
    return caught.value


def _refresh(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> AutomaticResult:
    policy = SourcePolicy(source_id="seiu-775", adapter=tmp_path / "adapter.yaml")
    election = ElectionPolicy(
        election_id="wa-2026-general",
        registry=tmp_path / "registry.yaml",
        inventory=tmp_path / "inventory.json",
        sources=[policy],
    )
    source = SimpleNamespace(id="seiu-775", discovery=SimpleNamespace(requested_url=URL))

    def panel(_: ElectionPolicy) -> tuple[SimpleNamespace, None]:
        return SimpleNamespace(sources=[source]), None

    checked_at = datetime(2026, 10, 28, 18, tzinfo=UTC)
    plan = VerificationPlan(
        as_of=checked_at.date(),
        elections=[
            ElectionPlan(
                election_id=election.election_id,
                cadence="daily",
                coverage=[
                    CoverageRecord(
                        source_id=policy.source_id,
                        lane="automatic",
                        cadence="daily",
                        last_successful_check=None,
                        next_due=checked_at.date(),
                        due=True,
                        limitation="Controlled one-source unit observation.",
                    )
                ],
            )
        ],
        missed=[],
    )

    def due_plan(*args: object, **kwargs: object) -> VerificationPlan:
        assert kwargs == {"as_of_at": checked_at}
        return plan

    def git(args: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        if args[-2:] == ["rev-parse", "HEAD"]:
            return subprocess.CompletedProcess(args, 0, "1" * 40 + "\n")
        assert "status" in args
        return subprocess.CompletedProcess(args, 0, "")

    monkeypatch.setattr(runtime, "read_panel", panel)
    monkeypatch.setattr(runtime, "plan_verification", due_plan)
    monkeypatch.setattr(runtime.subprocess, "run", git)
    monkeypatch.setattr(runtime, "fetch_http", transport.fetch_http)
    report = runtime.run_verification(
        VerificationPolicy(calendar=tmp_path / "calendar.yaml", elections=[election]),
        tmp_path / "state",
        checked_at,
        live=True,
        fixtures=None,
    )
    return AutomaticResult.model_validate(report["automatic"][0])


@pytest.mark.parametrize("status,rot", [(403, False), (404, True), (410, True)])
def test_transport_context_preserves_shared_error_strings_and_does_not_read_body(
    monkeypatch: pytest.MonkeyPatch, status: int, rot: bool
) -> None:
    peers = _wire(monkeypatch, [_response(status)])
    error = _error()
    assert str(error) == f"live collection failed: live collection returned HTTP {status}"
    assert error.__cause__ is not None
    assert str(error.__cause__) == f"live collection returned HTTP {status}"
    result = LinkCheckResult(
        target=LinkCheckTarget(source_id="fixture", source_name="Fixture", url=URL),
        ok=False,
        error=str(error),
    )
    previous = LinkCheckState(failing_urls=(URL,), rot_confirming_urls=(URL,))
    assert bool(confirmed_failures([result], previous)) is rot
    assert peers[0].closed
    assert type(error).__name__ == "HttpFetchFailure"
    assert vars(error) == {
        "response_status": status,
        "followed_redirects": 0,
        "redirect_class": "SAME_ORIGIN",
    }


@pytest.mark.parametrize(
    "location,expected_class,followed,status",
    [
        ("/other", "SAME_ORIGIN", 1, 403),
        ("https://other.example/other", "CROSS_ORIGIN", 1, 403),
        ("http://example.com/other", "REFUSED", 0, 302),
        ("https://127.0.0.1/other", "REFUSED", 0, None),
        (None, "REFUSED", 0, 302),
        ("https://user:password@other.example/", "REFUSED", 0, 302),
    ],
)
def test_direct_failure_reports_actual_followed_redirects_without_urls(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    location: str | None,
    expected_class: str,
    followed: int,
    status: int | None,
) -> None:
    peers = _wire(monkeypatch, [_response(302, location), _response()])
    event = _refresh(tmp_path, monkeypatch)
    assert event.error is not None
    response = f"HTTP_{status}" if status is not None else "NONE"
    assert (
        f"response={response}; followed_redirects={followed}; redirect_class={expected_class}"
        in event.error
    )
    assert "challenge=UNKNOWN" in event.error
    assert len(event.error.encode("ascii")) <= 512
    assert (
        PRIVATE not in event.error and "example" not in event.error and "https:" not in event.error
    )
    assert sum(bool(peer.sent) for peer in peers) == followed + 1
    assert event.status == "failed" and event.snapshot_id is event.capture_id is None


@pytest.mark.parametrize(
    "failure,category",
    [
        (socket.gaierror(PRIVATE), "dns"),
        (ssl.SSLError(PRIVATE), "tls"),
        (OSError(PRIVATE), "network"),
        (TimeoutError(PRIVATE), "deadline"),
    ],
)
def test_no_response_is_not_published_as_an_http_status(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, failure: OSError, category: str
) -> None:
    def fail(*args: object, **kwargs: object) -> None:
        raise failure

    if category == "dns":
        monkeypatch.setattr(transport.socket, "getaddrinfo", fail)
    else:
        _wire(monkeypatch, [])
        monkeypatch.setattr(transport, "_open_public_connection", fail)
    event = _refresh(tmp_path, monkeypatch)
    assert event.error is not None
    assert f"category={category}" in event.error
    assert "response=NONE; followed_redirects=0; redirect_class=SAME_ORIGIN" in event.error
    assert PRIVATE not in event.error and len(event.error.encode("ascii")) <= 512


def test_redirect_limit_counts_requests_followed_and_preserves_the_original_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    peers = _wire(monkeypatch, [_response(302, "/again")] * 11)
    event = _refresh(tmp_path, monkeypatch)
    assert event.error is not None
    assert "category=redirect" in event.error
    assert "response=HTTP_302; followed_redirects=10; redirect_class=REFUSED" in event.error
    assert all(peer.sent and peer.closed for peer in peers)


@pytest.mark.parametrize(
    "field,value",
    [
        ("response_status", PRIVATE),
        ("followed_redirects", 10**9),
        ("redirect_class", PRIVATE),
    ],
)
def test_invalid_transport_metadata_falls_back_to_the_fixed_safe_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, field: str, value: object
) -> None:
    _wire(monkeypatch, [_response()])
    error = _error()
    setattr(error, field, value)

    def fail(url: str) -> None:
        raise error

    event_fetch = transport.fetch_http
    monkeypatch.setattr(transport, "fetch_http", fail)
    event = _refresh(tmp_path, monkeypatch)
    monkeypatch.setattr(transport, "fetch_http", event_fetch)
    assert (
        event.error == "Source check failed (stage=http_fetch; category=http_status; status=403)."
    )
    assert PRIVATE not in event.error


def test_post_fetch_failure_cannot_gain_a_transport_note_or_access_admission(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _wire(monkeypatch, [_response()])
    error = _error()

    def fail(path: Path) -> None:
        raise error

    def complete(url: str) -> transport.HttpArtifact:
        return transport.HttpArtifact(b"tiny", 200, url, [], "text/html")

    monkeypatch.setattr(transport, "fetch_http", complete)
    monkeypatch.setattr(runtime, "read_adapter_spec", fail)
    event = _refresh(tmp_path, monkeypatch)
    assert event.error == "Source check failed (stage=post_fetch_preparation; category=unknown)."
    assert event.access_failure is None
