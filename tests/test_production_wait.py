"""Bounded read-only confirmations using fixture clocks and loopback transport."""

from __future__ import annotations

import json
import multiprocessing
import signal
import socket
import subprocess
import time
from dataclasses import FrozenInstanceError
from itertools import pairwise
from typing import Any

import pytest

from election_guide.hosting import production_wait as wait
from election_guide.hosting.production_check import (
    CommitCheck,
    Observation,
    ProductionCheckReport,
    RouteCheckResult,
)
from tests.test_hosting_check_production_cli import (
    _attachment_report,  # pyright: ignore[reportPrivateUsage]
)
from tests.test_production_check import (
    COMMIT,
    _site_manifest,  # pyright: ignore[reportPrivateUsage]
)
from tests.test_production_probe import blocked_body_server as blocked_body_server
from tests.test_production_probe import publication_server as publication_server

ORIGIN = "https://seattleelections.guide"


class Clock:
    now = 0.0

    def monotonic(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.now += seconds


def _report() -> ProductionCheckReport:
    return _attachment_report().model_copy(update={"base_url": ORIGIN})


def _run(
    monkeypatch: pytest.MonkeyPatch, reports: list[ProductionCheckReport]
) -> tuple[wait.ProductionWaitReport, list[float], Clock]:
    clock = Clock()
    starts: list[float] = []
    monkeypatch.setattr(wait, "monotonic", clock.monotonic)
    monkeypatch.setattr(wait, "sleep", clock.sleep)

    def worker(base_url: str, **kwargs: Any) -> ProductionCheckReport:
        assert base_url == ORIGIN
        assert kwargs["site_manifest"] == _site_manifest()
        assert kwargs["expected_git_commit"] == COMMIT
        assert kwargs["active_window"] is False
        assert kwargs["deadline"] == 120
        starts.append(clock.now)
        return reports[min(len(starts) - 1, len(reports) - 1)]

    def no_upload(*args: Any, **kwargs: Any) -> None:
        raise AssertionError("verification must not upload")

    monkeypatch.setattr(wait, "run_deadline_probe", worker)
    monkeypatch.setattr(subprocess, "run", no_upload)
    report = wait.wait_for_production(
        ORIGIN, site_manifest=_site_manifest(), expected_git_commit=COMMIT, active_window=False
    )
    assert all(b - a >= 5 for a, b in pairwise(starts))
    assert clock.now <= 120
    assert all(start < 120 for start in starts)
    return report, starts, clock


def test_previous_release_then_two_complete_passes(monkeypatch: pytest.MonkeyPatch) -> None:
    previous = _report().model_copy(
        update={"commit": CommitCheck(expected=COMMIT, observed="f" * 40)}
    )
    report, starts, _ = _run(monkeypatch, [previous, _report(), _report()])
    assert report.ok
    assert report.attempts[0] == previous
    assert report.successful_indices == (1, 2)
    assert starts == [0, 5, 10]
    assert not report.timed_out


def test_failure_resets_success_streak(monkeypatch: pytest.MonkeyPatch) -> None:
    broken = _report().model_copy(update={"manifest_parse_error": "invalid JSON"})
    report, _, _ = _run(monkeypatch, [_report(), broken, _report(), _report()])
    assert report.ok
    assert report.successful_indices == (2, 3)


@pytest.mark.parametrize("failure", ["sha", "manifest", "route", "redirect", "transport"])
def test_persistent_failures_time_out_preserving_observations(
    monkeypatch: pytest.MonkeyPatch, failure: str
) -> None:
    bad = _report()
    if failure == "sha":
        bad = bad.model_copy(update={"commit": CommitCheck(expected=COMMIT, observed="f" * 40)})
    elif failure == "manifest":
        bad = bad.model_copy(update={"manifest_parse_error": "broken manifest"})
    elif failure in {"route", "redirect"}:
        routes = list(bad.route_results)
        routes[0] = RouteCheckResult(
            check=routes[0].check,
            observed=Observation(status=404 if failure == "route" else 307, raw_location="/wrong"),
        )
        bad = bad.model_copy(update={"route_results": tuple(routes)})
    else:
        bad = bad.model_copy(
            update={
                "manifest": RouteCheckResult(
                    check=bad.manifest.check, observed=Observation(error="connection failed")
                )
            }
        )
    report, starts, clock = _run(monkeypatch, [bad])
    assert not report.ok
    assert report.timed_out
    assert report.successful_indices == ()
    assert len(starts) == 24
    assert report.attempts[:24] == (bad,) * 24
    assert clock.now == 120
    assert "deadline" in (report.attempts[-1].manifest.observed.error or "")


@pytest.mark.parametrize("missing", ["deployment_contract", "archive_index", "commit"])
def test_availability_reports_cannot_confirm_a_release(
    monkeypatch: pytest.MonkeyPatch, missing: str
) -> None:
    report, _, _ = _run(monkeypatch, [_report().model_copy(update={missing: None})])
    assert not report.ok


def test_wait_report_is_frozen_and_serializes_all_observations_deterministically(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    report, _, _ = _run(monkeypatch, [_report()])
    with pytest.raises(FrozenInstanceError):
        report.__setattr__("timed_out", True)
    document = report.model_dump(mode="json")
    assert document["successful_indices"] == [0, 1]
    assert document["attempts"] == [attempt.model_dump(mode="json") for attempt in report.attempts]
    assert json.loads(report.model_dump_json()) == document
    assert report.model_dump_json() == report.model_dump_json()


@pytest.mark.parametrize("origin,sha", [("https://preview.example", COMMIT), (ORIGIN, "abc")])
def test_invalid_identity_is_rejected_before_a_worker(
    monkeypatch: pytest.MonkeyPatch, origin: str, sha: str
) -> None:
    def never(*args: Any, **kwargs: Any) -> None:
        raise AssertionError("invalid identity must fail before worker start")

    monkeypatch.setattr(wait, "run_deadline_probe", never)
    with pytest.raises(ValueError):
        wait.wait_for_production(
            origin, site_manifest=_site_manifest(), expected_git_commit=sha, active_window=False
        )


def test_deadline_worker_returns_a_complete_structured_report(publication_server: str) -> None:
    report = wait.run_deadline_probe(
        publication_server,
        site_manifest=_site_manifest(),
        expected_git_commit=COMMIT,
        active_window=False,
        timeout=2,
        deadline=time.monotonic() + 5,
    )
    assert report.ok
    assert report.base_url == publication_server
    assert len(report.route_results) == 8


def test_blocked_body_worker_is_terminated_before_its_socket_timeout(
    blocked_body_server: str,
) -> None:
    before = {child.pid for child in multiprocessing.active_children()}
    started = time.monotonic()
    report = wait.run_deadline_probe(
        blocked_body_server,
        site_manifest=_site_manifest(),
        expected_git_commit=COMMIT,
        active_window=False,
        timeout=15,
        deadline=started + 0.7,
    )
    assert time.monotonic() - started < 1.7
    assert not report.ok
    assert "deadline" in (report.manifest.observed.error or "")
    assert {child.pid for child in multiprocessing.active_children()} == before


def _stalled_result_worker(channel: socket.socket, *args: object) -> None:
    with channel:
        channel.sendall(b'{"base_url":')
        time.sleep(10)


def test_partial_structured_result_cannot_block_past_deadline(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(wait, "_probe_worker", _stalled_result_worker)
    started = time.monotonic()
    report = wait.run_deadline_probe(
        ORIGIN,
        site_manifest=_site_manifest(),
        expected_git_commit=COMMIT,
        active_window=False,
        timeout=15,
        deadline=started + 0.7,
    )
    assert time.monotonic() - started < 1.7
    assert not report.ok
    assert "deadline" in (report.manifest.observed.error or "")


@pytest.mark.parametrize("seconds", [0, -1, float("inf"), float("nan")])
def test_invalid_request_timeout_fails_before_probing(seconds: float) -> None:
    with pytest.raises(ValueError, match="positive and finite"):
        wait.wait_for_production(
            ORIGIN,
            site_manifest=_site_manifest(),
            expected_git_commit=COMMIT,
            active_window=False,
            timeout=seconds,
        )


def test_two_successful_probes_must_observe_the_same_immutable_release(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    initial = _report()
    assert initial.deployment_contract is not None
    deployment = initial.deployment_contract.observed
    changed_current = deployment.elections[0].model_copy(
        update={"release_manifest_sha256": "e" * 64}
    )
    changed = initial.model_copy(
        update={
            "deployment_contract": initial.deployment_contract.model_copy(
                update={
                    "observed": deployment.model_copy(
                        update={"elections": (changed_current, *deployment.elections[1:])}
                    )
                }
            )
        }
    )
    report, _, _ = _run(monkeypatch, [initial, changed, changed])
    assert report.ok
    assert report.successful_indices == (1, 2)


def test_a_complete_result_arriving_at_deadline_cannot_confirm_production(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    clock = Clock()
    starts: list[float] = []
    monkeypatch.setattr(wait, "monotonic", clock.monotonic)
    monkeypatch.setattr(wait, "sleep", clock.sleep)

    def slow_worker(base_url: str, **kwargs: Any) -> ProductionCheckReport:
        starts.append(clock.now)
        clock.now = min(clock.now + 70, kwargs["deadline"])
        return _report()

    monkeypatch.setattr(wait, "run_deadline_probe", slow_worker)
    report = wait.wait_for_production(
        ORIGIN,
        site_manifest=_site_manifest(),
        expected_git_commit=COMMIT,
        active_window=False,
    )
    assert not report.ok
    assert report.timed_out
    assert clock.now == 120
    assert starts == [0, 70]
    assert report.attempts[:2] == (_report(), _report())
    assert "deadline" in (report.attempts[-1].manifest.observed.error or "")


def _large_result_worker(channel: socket.socket, *args: object) -> None:
    report = _report().model_copy(update={"manifest_parse_error": "x" * 1_000_000})
    with channel:
        channel.sendall(report.model_dump_json().encode())


def test_structured_result_larger_than_socket_buffer_is_drained_before_join(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(wait, "_probe_worker", _large_result_worker)
    report = wait.run_deadline_probe(
        ORIGIN,
        site_manifest=_site_manifest(),
        expected_git_commit=COMMIT,
        active_window=False,
        timeout=15,
        deadline=time.monotonic() + 5,
    )
    assert report.manifest_parse_error == "x" * 1_000_000


def test_clock_reaching_deadline_between_loop_check_and_start_does_not_start_worker(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    readings = iter([0.0, 119.999, 120.0])
    monkeypatch.setattr(wait, "monotonic", lambda: next(readings))

    def never(*args: Any, **kwargs: Any) -> ProductionCheckReport:
        raise AssertionError("no worker may start at the deadline")

    monkeypatch.setattr(wait, "run_deadline_probe", never)
    report = wait.wait_for_production(
        ORIGIN,
        site_manifest=_site_manifest(),
        expected_git_commit=COMMIT,
        active_window=False,
    )
    assert report.timed_out
    assert len(report.attempts) == 1


def test_expensive_result_decoding_is_terminated_at_the_shared_deadline(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    real_decode = ProductionCheckReport.model_validate_json

    def expensive_decode(document: str | bytes | bytearray) -> ProductionCheckReport:
        time.sleep(2)
        return real_decode(document)

    monkeypatch.setattr(wait, "_probe_worker", _large_result_worker)
    monkeypatch.setattr(ProductionCheckReport, "model_validate_json", expensive_decode)
    previous_handler = signal.getsignal(signal.SIGALRM)
    previous_timer = signal.getitimer(signal.ITIMER_REAL)
    started = time.monotonic()
    report = wait.run_deadline_probe(
        ORIGIN,
        site_manifest=_site_manifest(),
        expected_git_commit=COMMIT,
        active_window=False,
        timeout=15,
        deadline=started + 0.7,
    )
    assert time.monotonic() - started < 1.7
    assert not report.ok
    assert "deadline" in (report.manifest.observed.error or "")
    assert signal.getsignal(signal.SIGALRM) == previous_handler
    assert signal.getitimer(signal.ITIMER_REAL) == previous_timer


def _oversized_result_worker(channel: socket.socket, *args: object) -> None:
    report = _report().model_copy(update={"manifest_parse_error": "x" * wait.MAX_RESULT_BYTES})
    with channel:
        channel.sendall(report.model_dump_json().encode())


def test_oversized_worker_result_is_rejected_without_truncation_or_a_surviving_worker(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    before = {child.pid for child in multiprocessing.active_children()}
    monkeypatch.setattr(wait, "_probe_worker", _oversized_result_worker)
    report = wait.run_deadline_probe(
        ORIGIN,
        site_manifest=_site_manifest(),
        expected_git_commit=COMMIT,
        active_window=False,
        timeout=15,
        deadline=time.monotonic() + 5,
    )
    assert not report.ok
    assert "4194304-byte limit" in (report.manifest.observed.error or "")
    assert {child.pid for child in multiprocessing.active_children()} == before


@pytest.mark.parametrize("valid", [True, False])
def test_result_decoding_restores_idle_alarm_handler_and_timer(valid: bool) -> None:
    previous_handler = signal.getsignal(signal.SIGALRM)
    previous_timer = signal.getitimer(signal.ITIMER_REAL)
    assert previous_timer == (0.0, 0.0)

    def handler(signum: int, frame: object) -> None:
        raise AssertionError("restored alarm should not fire during this test")

    signal.signal(signal.SIGALRM, handler)
    try:
        body = _report().model_dump_json().encode() if valid else b"{"
        report = wait._decode_result(  # pyright: ignore[reportPrivateUsage]
            [body], ORIGIN, time.monotonic() + 3
        )
        assert report.ok is valid
        assert signal.getsignal(signal.SIGALRM) is handler
        assert signal.getitimer(signal.ITIMER_REAL) == previous_timer
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, previous_handler)
        signal.setitimer(signal.ITIMER_REAL, *previous_timer)


def test_late_decoded_result_is_never_accepted(monkeypatch: pytest.MonkeyPatch) -> None:
    clock = Clock()
    monkeypatch.setattr(wait, "monotonic", clock.monotonic)

    def late_decode(document: str | bytes | bytearray) -> ProductionCheckReport:
        clock.now = 2
        return _report()

    monkeypatch.setattr(ProductionCheckReport, "model_validate_json", late_decode)
    report = wait._decode_result([b"{}"], ORIGIN, 1)  # pyright: ignore[reportPrivateUsage]
    assert not report.ok
    assert "deadline" in (report.manifest.observed.error or "")


@pytest.mark.parametrize(
    "unsupported", ["platform", "timer_api", "thread", "active_timer", "blocked_mask"]
)
def test_unavailable_deadline_enforcement_fails_closed_without_changing_signal_state(
    monkeypatch: pytest.MonkeyPatch,
    unsupported: str,
) -> None:
    previous_handler = signal.getsignal(signal.SIGALRM)
    previous_timer = signal.getitimer(signal.ITIMER_REAL)
    assert previous_timer == (0.0, 0.0)
    previous_mask = signal.pthread_sigmask(signal.SIG_BLOCK, [])
    if unsupported == "platform":
        monkeypatch.setattr(wait.sys, "platform", "win32")
    elif unsupported == "timer_api":
        monkeypatch.delattr(signal, "setitimer")
    elif unsupported == "thread":
        monkeypatch.setattr(wait.threading, "current_thread", lambda: object())
    elif unsupported == "blocked_mask":
        signal.pthread_sigmask(signal.SIG_BLOCK, {signal.SIGALRM})
    else:
        signal.setitimer(signal.ITIMER_REAL, 10, 10)

    def never(*args: Any, **kwargs: Any) -> None:
        raise AssertionError("unsupported enforcement must fail before worker creation")

    monkeypatch.setattr(wait.socket, "socketpair", never)
    try:
        report = wait.run_deadline_probe(
            ORIGIN,
            site_manifest=_site_manifest(),
            expected_git_commit=COMMIT,
            active_window=False,
            timeout=15,
            deadline=time.monotonic() + 5,
        )
        assert not report.ok
        assert "deadline enforcement" in (report.manifest.observed.error or "")
        assert signal.getsignal(signal.SIGALRM) == previous_handler
        assert signal.pthread_sigmask(signal.SIG_BLOCK, []) == (
            previous_mask | {signal.SIGALRM} if unsupported == "blocked_mask" else previous_mask
        )
        timer = signal.getitimer(signal.ITIMER_REAL)
        if unsupported == "active_timer":
            assert 9 < timer[0] <= 10
            assert timer[1] == 10
        else:
            assert timer == previous_timer
    finally:
        if unsupported == "active_timer":
            signal.setitimer(signal.ITIMER_REAL, 0)
        signal.pthread_sigmask(signal.SIG_SETMASK, previous_mask)


def test_pending_own_alarm_is_consumed_before_restoring_the_caller_handler(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    previous_handler = signal.getsignal(signal.SIGALRM)
    previous_mask = signal.pthread_sigmask(signal.SIG_BLOCK, [])
    previous_timer = signal.getitimer(signal.ITIMER_REAL)

    def handler(signum: int, frame: object) -> None:
        raise AssertionError("a pending probe alarm escaped into caller code")

    def pending_decode(document: str | bytes | bytearray) -> ProductionCheckReport:
        signal.pthread_sigmask(signal.SIG_BLOCK, {signal.SIGALRM})
        signal.raise_signal(signal.SIGALRM)
        assert signal.SIGALRM in signal.sigpending()
        return _report()

    signal.signal(signal.SIGALRM, handler)
    monkeypatch.setattr(ProductionCheckReport, "model_validate_json", pending_decode)
    try:
        report = wait._decode_result(  # pyright: ignore[reportPrivateUsage]
            [b"{}"], ORIGIN, time.monotonic() + 3
        )
        assert report.ok
        assert signal.SIGALRM not in signal.sigpending()
        assert signal.getsignal(signal.SIGALRM) is handler
        assert signal.pthread_sigmask(signal.SIG_BLOCK, []) == previous_mask
        assert signal.getitimer(signal.ITIMER_REAL) == previous_timer
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, previous_handler)
        signal.pthread_sigmask(signal.SIG_SETMASK, previous_mask)


def test_expensive_asset_validation_is_interrupted_within_finite_result_budget() -> None:
    report = _report()
    assert report.deployment_contract is not None
    contract = report.deployment_contract
    assets = {
        f"e/wa-2026-general/races/fixture-{index}/index.html": "d" * 64 for index in range(20_000)
    }
    large = report.model_copy(
        update={
            "deployment_contract": contract.model_copy(
                update={"observed": contract.observed.model_copy(update={"assets": assets})}
            )
        }
    )
    body = large.model_dump_json().encode()
    assert 2_000_000 < len(body) < wait.MAX_RESULT_BYTES
    started = time.monotonic()
    result = wait._decode_result(  # pyright: ignore[reportPrivateUsage]
        [body], ORIGIN, started + 0.01
    )
    assert not result.ok
    assert "deadline" in (result.manifest.observed.error or "")
    assert time.monotonic() - started < 0.5


def test_public_strict_report_predicate_accepts_complete_and_rejects_partial_evidence() -> None:
    predicate = getattr(wait, "complete_strict_report", None)
    assert callable(predicate), "shared strict-report validation must be a public API"
    report = _report()
    assert predicate(report, _site_manifest(), COMMIT, False)
    partial = report.model_copy(update={"route_results": report.route_results[:1]})
    assert not predicate(partial, _site_manifest(), COMMIT, False)
    assert not predicate(report, _site_manifest(), "f" * 40, False)
    assert not predicate(report, _site_manifest(), COMMIT, True)
