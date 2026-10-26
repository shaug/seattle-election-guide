import socket
import threading
import time
from collections.abc import Generator
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from io import BytesIO
from typing import cast

import pytest

import election_guide.collection.http as collection_http


@pytest.mark.parametrize(
    ("url", "host_header"),
    [
        ("http://example.com/endorsements/", b"Host: example.com"),
        ("http://example.com:80/endorsements/", b"Host: example.com"),
        ("https://example.com/endorsements/", b"Host: example.com"),
        ("https://example.com:443/endorsements/", b"Host: example.com"),
        ("http://example.com:8080/endorsements/", b"Host: example.com:8080"),
        ("https://example.com:8443/endorsements/", b"Host: example.com:8443"),
    ],
)
def test_live_fetch_serializes_host_with_the_scheme_default_port(
    monkeypatch: pytest.MonkeyPatch, url: str, host_header: bytes
) -> None:
    peer = _RecordingPublicSocket()

    def open_socket(*args: object) -> _RecordingPublicSocket:
        del args
        return peer

    def resolve(
        *args: object, **kwargs: object
    ) -> list[tuple[int, int, int, str, tuple[str, int]]]:
        del args, kwargs
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 0))]

    monkeypatch.setattr(collection_http.socket, "socket", open_socket)
    monkeypatch.setattr(collection_http.socket, "getaddrinfo", resolve)
    monkeypatch.setattr(collection_http.ssl, "create_default_context", _OfflineTLSContext)

    artifact = collection_http.fetch_http(url)

    assert artifact.content == b"ok"
    assert peer.sent.startswith(b"GET /endorsements/ HTTP/1.1\r\n")
    assert [line for line in peer.sent.split(b"\r\n") if line.startswith(b"Host:")] == [host_header]


@pytest.mark.parametrize("form", [None, {"action": "public"}])
def test_live_fetch_rejects_non_public_initial_address(form: dict[str, str] | None) -> None:
    with pytest.raises(ValueError, match="refuses non-public address"):
        collection_http.fetch_http("http://127.0.0.1/example", form=form)


def test_live_fetch_revalidates_redirect_destinations(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with _server(_RedirectHandler) as port:
        monkeypatch.setattr(collection_http, "_validate_connected_peer", _skip_peer)

        def validate_redirect(host: str, target_port: int, *, deadline: float) -> set[str]:
            del target_port, deadline
            if host == "localhost":
                return {"127.0.0.1"}
            raise ValueError(f"live collection refuses non-public address {host!r}")

        monkeypatch.setattr(collection_http, "_validate_public_dns", validate_redirect)
        with pytest.raises(ValueError, match="refuses non-public address"):
            collection_http.fetch_http(f"http://localhost:{port}/start")


@pytest.mark.parametrize("form", [None, {"action": "public"}])
def test_live_fetch_timeout_is_a_total_deadline(
    monkeypatch: pytest.MonkeyPatch, form: dict[str, str] | None
) -> None:
    monkeypatch.setattr(collection_http, "_validate_public_dns", _skip_dns)
    monkeypatch.setattr(collection_http, "_validate_connected_peer", _skip_peer)
    with _server(_SlowDripHandler) as port:
        started = time.monotonic()
        with pytest.raises(ValueError, match="live collection failed"):
            collection_http.fetch_http(
                f"http://127.0.0.1:{port}/slow",
                timeout_seconds=0.1,
                form=form,
            )
        assert time.monotonic() - started < 0.5


@pytest.mark.parametrize("form", [None, {"action": "public"}])
def test_live_fetch_deadline_includes_dns(
    monkeypatch: pytest.MonkeyPatch, form: dict[str, str] | None
) -> None:
    def slow_dns(*args: object, **kwargs: object) -> list[object]:
        del args, kwargs
        time.sleep(0.2)
        return []

    monkeypatch.setattr(collection_http.socket, "getaddrinfo", slow_dns)
    started = time.monotonic()

    with pytest.raises(ValueError, match="total timeout"):
        collection_http.fetch_http("https://example.com/", timeout_seconds=0.05, form=form)

    assert time.monotonic() - started < 0.15


def test_connection_reuses_validated_dns_result(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(collection_http, "_validate_public_dns", _skip_dns)
    monkeypatch.setattr(collection_http, "_validate_connected_peer", _skip_peer)

    def reject_second_lookup(*args: object, **kwargs: object) -> list[object]:
        del args, kwargs
        raise AssertionError("connection repeated DNS resolution")

    monkeypatch.setattr(collection_http.socket, "getaddrinfo", reject_second_lookup)
    with _server(_SimpleHandler) as port:
        artifact = collection_http.fetch_http(f"http://localhost:{port}/")

    assert artifact.content == b"ok"


def test_live_fetch_rejects_a_truncated_declared_body(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(collection_http, "_validate_public_dns", _skip_dns)
    monkeypatch.setattr(collection_http, "_validate_connected_peer", _skip_peer)
    with (
        _server(_TruncatedHandler) as port,
        pytest.raises(ValueError, match="artifact was truncated"),
    ):
        collection_http.fetch_http(f"http://127.0.0.1:{port}/")


def test_live_fetch_accepts_complete_declared_body_when_connection_closes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(collection_http, "_validate_public_dns", _skip_dns)
    monkeypatch.setattr(collection_http, "_validate_connected_peer", _skip_peer)
    with _server(_CompleteClosingHandler) as port:
        artifact = collection_http.fetch_http(f"http://127.0.0.1:{port}/")

    assert artifact.status == 200
    assert artifact.content == b"<p>complete</p>"


@contextmanager
def _server(handler: type[BaseHTTPRequestHandler]) -> Generator[int]:
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    server.daemon_threads = True
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield server.server_port
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=1)


class _QuietHandler(BaseHTTPRequestHandler):
    def log_message(self, format: str, *args: object) -> None:
        del format, args


class _RedirectHandler(_QuietHandler):
    def do_GET(self) -> None:
        server = cast(ThreadingHTTPServer, self.server)
        self.send_response(302)
        self.send_header("Location", f"http://127.0.0.1:{server.server_port}/private")
        self.end_headers()


class _SlowDripHandler(_QuietHandler):
    def do_POST(self) -> None:
        self.do_GET()

    def do_GET(self) -> None:
        self.send_response(200)
        self.send_header("Content-Type", "text/plain")
        self.end_headers()
        try:
            for _ in range(20):
                self.wfile.write(b"x")
                self.wfile.flush()
                time.sleep(0.04)
        except (BrokenPipeError, ConnectionResetError):
            return


class _SimpleHandler(_QuietHandler):
    def do_GET(self) -> None:
        self.send_response(200)
        self.send_header("Content-Type", "text/plain")
        self.end_headers()
        self.wfile.write(b"ok")


class _TruncatedHandler(_QuietHandler):
    def do_GET(self) -> None:
        self.send_response(200)
        self.send_header("Content-Type", "text/html")
        self.send_header("Content-Length", "100")
        self.end_headers()
        self.wfile.write(b"<p>partial</p>")


class _CompleteClosingHandler(_QuietHandler):
    def do_GET(self) -> None:
        self.send_response(200)
        self.send_header("Content-Type", "text/html")
        self.send_header("Content-Length", "15")
        self.send_header("Connection", "close")
        self.end_headers()
        self.wfile.write(b"<p>complete</p>")


def _skip_dns(host: str, port: int, *, deadline: float) -> set[str]:
    del host, port, deadline
    return {"127.0.0.1"}


def _skip_peer(peer: socket.socket) -> None:
    del peer


class _RecordingPublicSocket:
    def __init__(self) -> None:
        self.sent = bytearray()

    def settimeout(self, timeout: float) -> None:
        del timeout

    def connect(self, address: tuple[str, int]) -> None:
        if address[0] != "93.184.216.34":
            raise OSError("fixture only accepts the validated public address")

    def getpeername(self) -> tuple[str, int]:
        return ("93.184.216.34", 443)

    def do_handshake(self) -> None:
        pass

    def sendall(self, data: bytes) -> None:
        self.sent.extend(data)

    def makefile(self, mode: str) -> BytesIO:
        if mode != "rb":
            raise ValueError("fixture only serves a binary HTTP response")
        return BytesIO(
            b"HTTP/1.1 200 OK\r\nContent-Type: text/plain\r\nContent-Length: 2\r\n\r\nok"
        )

    def close(self) -> None:
        pass


class _OfflineTLSContext:
    def wrap_socket(
        self,
        peer: _RecordingPublicSocket,
        *,
        server_hostname: str,
        do_handshake_on_connect: bool,
    ) -> _RecordingPublicSocket:
        del server_hostname, do_handshake_on_connect
        return peer


def test_public_form_post_serializes_reviewed_fields(monkeypatch: pytest.MonkeyPatch) -> None:
    peer = _install_public_socket(monkeypatch)
    artifact = collection_http.fetch_http(
        "https://workingfamilies.org/wp-admin/admin-ajax.php",
        form={"action": "more_candidates", "state": "25", "count": "0"},
    )
    headers, body = bytes(peer.sent).split(b"\r\n\r\n", 1)
    assert headers.startswith(b"POST /wp-admin/admin-ajax.php HTTP/1.1\r\n")
    assert b"Content-Type: application/x-www-form-urlencoded" in headers
    assert body == b"action=more_candidates&state=25&count=0"
    assert artifact.content == b"ok"


@pytest.mark.parametrize("status", [301, 302, 303, 307, 308])
def test_public_form_post_refuses_redirect_without_replaying(
    monkeypatch: pytest.MonkeyPatch, status: int
) -> None:
    peer = _RecordingPublicSocket()
    response = f"HTTP/1.1 {status} Redirect\r\nLocation: https://example.com/other\r\n\r\n".encode()
    peer = _install_public_socket(monkeypatch, response)
    with pytest.raises(ValueError, match="POST redirect"):
        collection_http.fetch_http("https://example.com/form", form={"action": "public"})
    assert bytes(peer.sent).count(b"POST ") == 1


@pytest.mark.parametrize(
    "response,reason",
    [
        (b"HTTP/1.1 200 OK\r\nContent-Length: 26214401\r\n\r\n", "25 MiB"),
        (b"HTTP/1.1 200 OK\r\nContent-Length: 0\r\n\r\n", "empty"),
    ],
)
def test_public_form_post_preserves_response_bounds(
    monkeypatch: pytest.MonkeyPatch, response: bytes, reason: str
) -> None:
    _install_public_socket(monkeypatch, response)
    with pytest.raises(ValueError, match=reason):
        collection_http.fetch_http("https://example.com/form", form={"action": "public"})


def test_public_form_post_rejects_private_connected_peer(monkeypatch: pytest.MonkeyPatch) -> None:
    peer = _install_public_socket(monkeypatch)
    monkeypatch.setattr(peer, "getpeername", lambda: ("127.0.0.1", 443))
    with pytest.raises(ValueError, match="non-public address"):
        collection_http.fetch_http("https://example.com/form", form={"action": "public"})
    assert not peer.sent


def _install_public_socket(
    monkeypatch: pytest.MonkeyPatch,
    response: bytes = b"HTTP/1.1 200 OK\r\nContent-Type: text/plain\r\nContent-Length: 2\r\n\r\nok",
) -> _RecordingPublicSocket:
    peer = _RecordingPublicSocket()

    def open_socket(*args: object) -> _RecordingPublicSocket:
        return peer

    def resolve(
        *args: object, **kwargs: object
    ) -> list[tuple[int, int, int, str, tuple[str, int]]]:
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 0))]

    def makefile(mode: str) -> BytesIO:
        assert mode == "rb"
        return BytesIO(response)

    monkeypatch.setattr(peer, "makefile", makefile)
    monkeypatch.setattr(collection_http.socket, "socket", open_socket)
    monkeypatch.setattr(collection_http.socket, "getaddrinfo", resolve)
    monkeypatch.setattr(collection_http.ssl, "create_default_context", _OfflineTLSContext)
    return peer
