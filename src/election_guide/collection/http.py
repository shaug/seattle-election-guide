"""Explicit, bounded live HTTP collection used only by the refresh command."""

from __future__ import annotations

import ipaddress
import socket
import ssl
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from functools import partial
from http.client import HTTPConnection, HTTPResponse
from urllib.parse import urljoin, urlsplit, urlunsplit

from election_guide.validation import validated_http_url, validated_media_type

MAX_DOWNLOAD_BYTES = 25 * 1024 * 1024
MAX_REDIRECTS = 10
READ_CHUNK_SIZE = 64 * 1024
REDIRECT_STATUSES = {301, 302, 303, 307, 308}


@dataclass(frozen=True)
class HttpArtifact:
    content: bytes
    status: int
    canonical_url: str
    redirect_chain: list[str]
    media_type: str


def fetch_http(url: str, *, timeout_seconds: float = 30) -> HttpArtifact:
    """Fetch one public artifact within a total deadline and strict size cap."""
    if timeout_seconds <= 0:
        raise ValueError("live collection timeout must be positive")
    requested_url = validated_http_url(url)
    current_url = requested_url
    redirects: list[str] = []
    deadline = time.monotonic() + timeout_seconds

    try:
        for _ in range(MAX_REDIRECTS + 1):
            remaining = _remaining_seconds(deadline)
            split = urlsplit(current_url)
            host = split.hostname
            if host is None:
                raise ValueError("live collection URL has no host")
            port = split.port or (443 if split.scheme == "https" else 80)
            addresses = _validate_public_dns(host, port, deadline=deadline)
            connection, peer = _open_public_connection(
                host,
                port,
                addresses,
                use_tls=split.scheme == "https",
                deadline=deadline,
            )
            remaining = _remaining_seconds(deadline)
            deadline_timer = threading.Timer(remaining, peer.close)
            deadline_timer.daemon = True
            deadline_timer.start()
            try:
                target = urlunsplit(("", "", split.path or "/", split.query, ""))
                connection.request(
                    "GET",
                    target,
                    headers={
                        "Accept": (
                            "text/html,application/xhtml+xml,application/pdf,"
                            "image/*;q=0.9,*/*;q=0.1"
                        ),
                        "User-Agent": (
                            "SeattleElectionGuide/0.1 "
                            "(+https://github.com/shaug/seattle-election-guide)"
                        ),
                    },
                )
                response = connection.getresponse()
                if response.status in REDIRECT_STATUSES:
                    location = response.getheader("Location")
                    if location is None:
                        raise ValueError("redirect response has no Location header")
                    redirected = validated_http_url(urljoin(current_url, location))
                    if split.scheme == "https" and urlsplit(redirected).scheme != "https":
                        raise ValueError("live collection refuses an HTTPS downgrade redirect")
                    redirects.append(redirected)
                    current_url = redirected
                    continue
                if not 200 <= response.status < 300:
                    raise ValueError(f"live collection returned HTTP {response.status}")
                content = _read_response(response, peer, deadline)
                media_type = validated_media_type(
                    response.getheader("Content-Type", "application/octet-stream")
                )
                chain = [requested_url, *redirects] if redirects else []
                return HttpArtifact(
                    content=content,
                    status=response.status,
                    canonical_url=current_url,
                    redirect_chain=chain,
                    media_type=media_type,
                )
            finally:
                deadline_timer.cancel()
                connection.close()
                peer.close()
        raise ValueError(f"live collection exceeded {MAX_REDIRECTS} redirects")
    except (OSError, TimeoutError, ValueError) as error:
        if time.monotonic() >= deadline:
            raise ValueError("live collection failed: total timeout exceeded") from error
        raise ValueError(f"live collection failed: {error}") from error


def _read_response(response: HTTPResponse, peer: socket.socket, deadline: float) -> bytes:
    declared_length = response.getheader("Content-Length")
    expected_length: int | None = None
    if declared_length is not None:
        try:
            expected_length = int(declared_length)
        except ValueError as error:
            raise ValueError("live artifact has an invalid Content-Length") from error
        if expected_length < 0 or expected_length > MAX_DOWNLOAD_BYTES:
            raise ValueError("live artifact exceeds the 25 MiB limit")
    content = bytearray()
    while True:
        remaining = _remaining_seconds(deadline)
        peer.settimeout(remaining)
        chunk = response.read1(min(READ_CHUNK_SIZE, MAX_DOWNLOAD_BYTES + 1 - len(content)))
        if not chunk:
            break
        content.extend(chunk)
        if len(content) > MAX_DOWNLOAD_BYTES:
            raise ValueError("live artifact exceeds the 25 MiB limit")
    if not content:
        raise ValueError("live artifact is empty")
    if expected_length is not None and len(content) != expected_length:
        raise ValueError(
            f"live artifact was truncated: expected {expected_length} bytes, got {len(content)}"
        )
    return bytes(content)


def _validate_public_dns(host: str, port: int, *, deadline: float) -> set[str]:
    result: list[set[str] | BaseException] = []

    def resolve() -> None:
        try:
            result.append(
                {
                    str(item[4][0])
                    for item in socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
                }
            )
        except BaseException as error:
            result.append(error)

    resolver = threading.Thread(target=resolve, daemon=True)
    resolver.start()
    resolver.join(_remaining_seconds(deadline))
    if resolver.is_alive():
        raise TimeoutError("live collection exceeded its total timeout during DNS resolution")
    resolved = result[0]
    if isinstance(resolved, BaseException):
        raise ValueError(f"live collection DNS resolution failed for {host!r}") from resolved
    addresses = resolved
    if not addresses:
        raise ValueError(f"live collection DNS resolution returned no addresses for {host!r}")
    for address in addresses:
        _require_global_address(address)
    return addresses


def _open_public_connection(
    host: str,
    port: int,
    addresses: set[str],
    *,
    use_tls: bool,
    deadline: float,
) -> tuple[HTTPConnection, socket.socket]:
    errors: list[OSError] = []
    for address in sorted(addresses):
        raw: socket.socket | None = None
        try:
            parsed = ipaddress.ip_address(address)
            family = socket.AF_INET6 if parsed.version == 6 else socket.AF_INET
            raw = socket.socket(family, socket.SOCK_STREAM)
            raw.settimeout(_remaining_seconds(deadline))
            target: tuple[str, int] | tuple[str, int, int, int]
            target = (address, port, 0, 0) if parsed.version == 6 else (address, port)
            _run_with_socket_deadline(raw, deadline, partial(raw.connect, target))
            _validate_connected_peer(raw)
            connected: socket.socket = raw
            if use_tls:
                context = ssl.create_default_context()
                tls = context.wrap_socket(raw, server_hostname=host, do_handshake_on_connect=False)
                raw = None
                _run_with_socket_deadline(tls, deadline, tls.do_handshake)
                _validate_connected_peer(tls)
                connected = tls
            connection = HTTPConnection(host, port, timeout=_remaining_seconds(deadline))
            connection.sock = connected
            return connection, connected
        except OSError as error:
            errors.append(error)
            if raw is not None:
                raw.close()
    if errors:
        raise errors[-1]
    raise ValueError("live collection has no validated address to connect to")


def _run_with_socket_deadline(
    peer: socket.socket, deadline: float, operation: Callable[[], object]
) -> None:
    timer = threading.Timer(_remaining_seconds(deadline), peer.close)
    timer.daemon = True
    timer.start()
    try:
        operation()
    finally:
        timer.cancel()


def _validate_connected_peer(peer: socket.socket) -> None:
    address = str(peer.getpeername()[0])
    _require_global_address(address)


def _require_global_address(address: str) -> None:
    try:
        parsed = ipaddress.ip_address(address)
    except ValueError as error:
        raise ValueError(f"live collection peer has invalid address {address!r}") from error
    if not parsed.is_global:
        raise ValueError(f"live collection refuses non-public address {address!r}")


def _remaining_seconds(deadline: float) -> float:
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        raise TimeoutError("live collection exceeded its total timeout")
    return remaining
