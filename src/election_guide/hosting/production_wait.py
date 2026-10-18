"""Read-only strict production confirmations bounded by one monotonic deadline."""

from __future__ import annotations

import json
import math
import multiprocessing
import re
import select
import signal
import socket
import sys
import threading
from dataclasses import dataclass
from datetime import UTC, datetime
from time import monotonic, sleep
from types import FrameType
from typing import Literal

from election_guide.hosting.models import SiteManifest
from election_guide.hosting.production_check import (
    MANIFEST_CHECK,
    Observation,
    ProductionCheckReport,
    RouteCheckResult,
    plan_publication_route_checks,
)
from election_guide.hosting.production_probe import run_production_check

WAIT_SECONDS = 120.0
ATTEMPT_INTERVAL = 5.0
MAX_RESULT_BYTES = 4 * 1024 * 1024


@dataclass(frozen=True)
class ProductionWaitReport:
    attempts: tuple[ProductionCheckReport, ...]
    successful_indices: tuple[int, ...]
    timed_out: bool

    @property
    def ok(self) -> bool:
        if self.timed_out or len(self.successful_indices) != 2:
            return False
        first, second = self.successful_indices
        return (
            0 <= first < second < len(self.attempts)
            and second == first + 1
            and all(self.attempts[index].ok for index in self.successful_indices)
        )

    def model_dump(self, *, mode: Literal["json"] = "json") -> dict[str, object]:
        return {
            "attempts": [attempt.model_dump(mode=mode) for attempt in self.attempts],
            "successful_indices": list(self.successful_indices),
            "timed_out": self.timed_out,
        }

    def model_dump_json(self) -> str:
        return json.dumps(self.model_dump(), sort_keys=True, separators=(",", ":"))


def _failed_probe(base_url: str, error: str) -> ProductionCheckReport:
    return ProductionCheckReport(
        base_url=base_url,
        checked_at=datetime.now(UTC),
        manifest=RouteCheckResult(check=MANIFEST_CHECK, observed=Observation(error=error)),
    )


def _probe_worker(
    channel: socket.socket,
    base_url: str,
    site_manifest: SiteManifest,
    expected_git_commit: str,
    active_window: bool,
    timeout: float,
    deadline: float,
) -> None:
    """The child owns DNS, body reads, serialization, and all blocking writes."""
    with channel:
        try:
            report = run_production_check(
                base_url,
                site_manifest=site_manifest,
                expected_git_commit=expected_git_commit,
                active_window=active_window,
                timeout=timeout,
                deadline=deadline,
            )
        except Exception as error:
            report = _failed_probe(base_url, f"production probe worker failed: {error}")
        channel.sendall(report.model_dump_json().encode("utf-8"))


class _DeadlineExceeded(BaseException):
    """Escape validators without being converted into a validation failure."""


def _deadline_runtime_error() -> str | None:
    if sys.platform not in {"linux", "darwin"}:
        return "wait requires a Linux or macOS POSIX interval timer"
    if threading.current_thread() is not threading.main_thread():
        return "wait requires the main thread"
    if not all(
        hasattr(signal, name) for name in ("SIGALRM", "ITIMER_REAL", "SIG_BLOCK", "SIG_SETMASK")
    ) or not all(
        callable(getattr(signal, name, None))
        for name in ("setitimer", "getitimer", "pthread_sigmask", "sigpending", "sigwait")
    ):
        return "POSIX interval deadline enforcement is unavailable"
    try:
        if signal.SIGALRM in signal.pthread_sigmask(signal.SIG_BLOCK, []):
            return "SIGALRM is blocked in the caller's signal mask"
        if signal.SIGALRM in signal.sigpending():
            return "an existing pending alarm cannot be safely preserved"
        if signal.getitimer(signal.ITIMER_REAL) != (0.0, 0.0):
            return "an existing interval timer cannot be safely preserved"
        handler = signal.getsignal(signal.SIGALRM)
        if handler not in (signal.SIG_DFL, signal.SIG_IGN) and not callable(handler):
            return "the existing alarm handler cannot be safely preserved"
    except (OSError, ValueError) as error:
        return f"POSIX interval deadline enforcement is unavailable: {error}"
    return None


def _decode_result(chunks: list[bytes], base_url: str, deadline: float) -> ProductionCheckReport:
    """Bound input size and interrupt Python work during parent reconstruction.

    Native work on the finite result and OS scheduling/reaping add practical
    cleanup overhead; an unrestricted native-parser hard-return guarantee is
    not possible in this process. Never accept a result after its deadline.
    """
    runtime_error = _deadline_runtime_error()
    if runtime_error is not None:
        return _failed_probe(
            base_url, f"production confirmation deadline enforcement: {runtime_error}"
        )
    remaining = deadline - monotonic()
    if remaining <= 0:
        return _failed_probe(base_url, "production confirmation deadline exceeded")
    previous_handler = signal.getsignal(signal.SIGALRM)
    previous_timer = signal.getitimer(signal.ITIMER_REAL)
    previous_mask = signal.pthread_sigmask(signal.SIG_BLOCK, [])
    decoding = True

    def expired(signum: int, frame: FrameType | None) -> None:
        if decoding:
            raise _DeadlineExceeded

    try:
        signal.signal(signal.SIGALRM, expired)
        remaining = deadline - monotonic()
        if remaining <= 0:
            raise _DeadlineExceeded
        signal.setitimer(signal.ITIMER_REAL, remaining)
        try:
            report = ProductionCheckReport.model_validate_json(b"".join(chunks))
        except ValueError as error:
            report = _failed_probe(base_url, f"invalid production probe worker result: {error}")
        decoding = False
        if monotonic() >= deadline:
            raise _DeadlineExceeded
        return report
    except _DeadlineExceeded:
        decoding = False
        return _failed_probe(base_url, "production confirmation deadline exceeded")
    except (OSError, ValueError) as error:
        decoding = False
        return _failed_probe(base_url, f"production confirmation deadline enforcement: {error}")
    finally:
        decoding = False
        # Block delivery before disarming, then consume our pending alarm so
        # restoring the old handler cannot deliver it to unrelated caller code.
        signal.pthread_sigmask(signal.SIG_BLOCK, {signal.SIGALRM})
        try:
            signal.setitimer(signal.ITIMER_REAL, 0)
            if signal.SIGALRM in signal.sigpending():
                signal.sigwait({signal.SIGALRM})
            signal.signal(signal.SIGALRM, previous_handler)
            signal.setitimer(signal.ITIMER_REAL, *previous_timer)
        finally:
            signal.pthread_sigmask(signal.SIG_SETMASK, previous_mask)


def run_deadline_probe(
    base_url: str,
    *,
    site_manifest: SiteManifest,
    expected_git_commit: str,
    active_window: bool,
    timeout: float,
    deadline: float,
) -> ProductionCheckReport:
    """Terminate a complete probe, including DNS and result transfer, at deadline.

    Read nonblocking chunks rather than `Connection.recv()` after `poll()`:
    the latter can block indefinitely after only a message header arrives.
    """
    if monotonic() >= deadline:
        return _failed_probe(base_url, "production confirmation deadline exceeded")
    runtime_error = _deadline_runtime_error()
    if runtime_error is not None:
        return _failed_probe(
            base_url, f"production confirmation deadline enforcement: {runtime_error}"
        )
    receiver, sender = socket.socketpair()
    worker = multiprocessing.get_context("spawn").Process(
        target=_probe_worker,
        args=(
            sender,
            base_url,
            site_manifest,
            expected_git_commit,
            active_window,
            timeout,
            deadline,
        ),
        daemon=True,
    )
    chunks: list[bytes] = []
    received_size = 0
    try:
        worker.start()
        sender.close()
        receiver.setblocking(False)
        while (remaining := deadline - monotonic()) > 0:
            ready, _, _ = select.select([receiver], [], [], remaining)
            if not ready:
                break
            chunk = receiver.recv(65536)
            if not chunk:
                if monotonic() >= deadline:
                    break
                return _decode_result(chunks, base_url, deadline)
            received_size += len(chunk)
            if received_size > MAX_RESULT_BYTES:
                return _failed_probe(
                    base_url,
                    f"production probe worker result exceeds {MAX_RESULT_BYTES}-byte limit",
                )
            chunks.append(chunk)
        return _failed_probe(base_url, "production confirmation deadline exceeded")
    finally:
        sender.close()
        receiver.close()
        if worker.pid is not None:
            # kill also handles a child stuck in DNS, a body read, or sendall.
            # No blocking join of a live child or feeder thread precedes it.
            if worker.is_alive():
                worker.kill()
            worker.join()
            worker.close()


def complete_strict_report(
    report: ProductionCheckReport, site: SiteManifest, expected_git_commit: str, active_window: bool
) -> bool:
    """Validate complete strict probe evidence for live waits and retained receipts."""
    contract = report.deployment_contract
    if (
        not report.ok
        or report.base_url is None
        or report.base_url.rstrip("/") != site.canonical_origin
        or contract is None
        or contract.expected_site != site
        or contract.expected_git_commit != expected_git_commit
        or contract.representative_race_path is None
        or report.archive_index is None
        or report.commit is None
        or report.commit.expected != expected_git_commit
        or report.current_election_id != site.current_election_id
    ):
        return False
    expected_routes = plan_publication_route_checks(
        site, representative_race_path=contract.representative_race_path
    )
    return [result.check for result in report.route_results] == expected_routes and (
        not active_window
        or (report.release_manifest is not None and report.data_freshness is not None)
    )


def wait_for_production(
    base_url: str,
    *,
    site_manifest: SiteManifest,
    expected_git_commit: str,
    active_window: bool,
    timeout: float = 15.0,
) -> ProductionWaitReport:
    """Require two consecutive complete strict passes within 120 seconds."""
    if base_url.rstrip("/") != site_manifest.canonical_origin:
        raise ValueError("base URL must equal site manifest canonical origin")
    if re.fullmatch(r"[0-9a-f]{40}", expected_git_commit) is None:
        raise ValueError("expected Git commit must be a full 40-character lowercase SHA")
    if not math.isfinite(timeout) or timeout <= 0:
        raise ValueError("request timeout must be positive and finite")
    deadline = monotonic() + WAIT_SECONDS
    attempts: list[ProductionCheckReport] = []
    successful: tuple[int, ...] = ()
    while monotonic() < deadline:
        started_at = monotonic()
        if started_at >= deadline:
            break
        report = run_deadline_probe(
            base_url,
            site_manifest=site_manifest,
            expected_git_commit=expected_git_commit,
            active_window=active_window,
            timeout=min(timeout, 15.0, deadline - started_at),
            deadline=deadline,
        )
        attempts.append(report)
        if monotonic() >= deadline:
            break
        if complete_strict_report(report, site_manifest, expected_git_commit, active_window):
            if successful and (
                attempts[successful[-1]].deployment_contract != report.deployment_contract
            ):
                successful = ()
            successful = (*successful, len(attempts) - 1)
            if len(successful) == 2:
                return ProductionWaitReport(tuple(attempts), successful, timed_out=False)
        else:
            successful = ()
        sleep(max(0, min(started_at + ATTEMPT_INTERVAL, deadline) - monotonic()))
    if not attempts or attempts[-1].manifest.observed.error != (
        "production confirmation deadline exceeded"
    ):
        attempts.append(_failed_probe(base_url, "production confirmation deadline exceeded"))
    return ProductionWaitReport(tuple(attempts), (), timed_out=True)
