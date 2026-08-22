"""Behavior tests for the `sources check-links` CLI (O17)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from typer.testing import CliRunner

from election_guide import cli
from election_guide.sources.link_check import LinkCheckResult, LinkCheckTarget
from election_guide.sources.link_check_state import (
    LinkCheckState,
    read_link_check_state,
    write_link_check_state,
)
from election_guide.sources.link_rot_alert import LinkRotAlertTracker, next_state

# The strings `check_link` records, in the shape `fetch_http` raises them.
GONE_404 = "live collection failed: live collection returned HTTP 404"
GUARDED_403 = "live collection failed: live collection returned HTTP 403"


def _result(source_id: str, url: str, *, ok: bool, error: str | None = None) -> LinkCheckResult:
    return LinkCheckResult(
        target=LinkCheckTarget(source_id=source_id, source_name=source_id, url=url),
        ok=ok,
        error=error,
    )


def _invoke(*extra_args: str) -> Any:
    return CliRunner().invoke(cli.app, ["sources", "check-links", *extra_args])


def test_a_healthy_run_exits_zero_and_reconciles_the_alert(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    recorded: dict[str, Any] = {}

    def _check(
        registry: Any, *, timeout_seconds: float, delay_seconds: float
    ) -> list[LinkCheckResult]:
        return [_result("a", "https://a.example", ok=True)]

    def _reconcile(
        tracker: LinkRotAlertTracker, confirmed: list[LinkCheckResult], *, checked_at: str
    ) -> str:
        recorded["confirmed"] = confirmed
        return "healthy; no open alert"

    monkeypatch.setattr(cli, "run_link_check", _check)
    monkeypatch.setattr(cli, "reconcile_link_rot_alert", _reconcile)

    result = _invoke("--state-path", str(tmp_path / "state.json"), "--repository", "owner/repo")

    assert result.exit_code == 0
    assert recorded["confirmed"] == []
    assert "healthy; no open alert" in result.output


def test_a_first_time_failure_is_reported_but_not_confirmed_or_alerted(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    state_path = tmp_path / "state.json"  # no prior state: nothing to confirm against yet

    def _check(
        registry: Any, *, timeout_seconds: float, delay_seconds: float
    ) -> list[LinkCheckResult]:
        return [_result("a", "https://a.example", ok=False, error=GONE_404)]

    def _reconcile(
        tracker: LinkRotAlertTracker, confirmed: list[LinkCheckResult], *, checked_at: str
    ) -> str:
        assert confirmed == []
        return "healthy; no open alert"

    monkeypatch.setattr(cli, "run_link_check", _check)
    monkeypatch.setattr(cli, "reconcile_link_rot_alert", _reconcile)

    result = _invoke("--state-path", str(state_path), "--repository", "owner/repo")

    assert result.exit_code == 0
    assert f"FAIL a (https://a.example): {GONE_404}" in result.output
    assert read_link_check_state(state_path) == LinkCheckState(
        failing_urls=("https://a.example",), rot_confirming_urls=("https://a.example",)
    )


def test_a_failure_repeating_from_the_saved_state_is_confirmed_and_exits_nonzero(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    state_path = tmp_path / "state.json"
    write_link_check_state(
        state_path, next_state([_result("a", "https://a.example", ok=False, error=GONE_404)])
    )

    def _check(
        registry: Any, *, timeout_seconds: float, delay_seconds: float
    ) -> list[LinkCheckResult]:
        return [_result("a", "https://a.example", ok=False, error=GONE_404)]

    def _reconcile(
        tracker: LinkRotAlertTracker, confirmed: list[LinkCheckResult], *, checked_at: str
    ) -> str:
        assert len(confirmed) == 1
        return "opened alert issue: https://x/9"

    monkeypatch.setattr(cli, "run_link_check", _check)
    monkeypatch.setattr(cli, "reconcile_link_rot_alert", _reconcile)

    result = _invoke("--state-path", str(state_path), "--repository", "owner/repo")

    assert result.exit_code == 1
    assert "FAIL" in result.output
    assert "opened alert issue" in result.output


def test_a_guarded_url_failing_every_run_is_reported_but_never_confirmed(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Issue #399's shape end to end: a 403 that repeats forever still prints
    its `FAIL` line every run, and still exits 0 with nothing to alert on."""
    state_path = tmp_path / "state.json"
    guarded = [_result("a", "https://a.example", ok=False, error=GUARDED_403)]
    write_link_check_state(state_path, next_state(guarded))

    def _check(
        registry: Any, *, timeout_seconds: float, delay_seconds: float
    ) -> list[LinkCheckResult]:
        return guarded

    def _reconcile(
        tracker: LinkRotAlertTracker, confirmed: list[LinkCheckResult], *, checked_at: str
    ) -> str:
        assert confirmed == []
        return "healthy; closed alert issue 9"

    monkeypatch.setattr(cli, "run_link_check", _check)
    monkeypatch.setattr(cli, "reconcile_link_rot_alert", _reconcile)

    result = _invoke("--state-path", str(state_path), "--repository", "owner/repo")

    assert result.exit_code == 0
    assert f"FAIL a (https://a.example): {GUARDED_403}" in result.output
    assert "1 unreachable this run, 0 confirmed across consecutive runs" in result.output
    assert "closed alert issue 9" in result.output


def test_a_dry_run_never_touches_the_alert_tracker_or_writes_state(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    state_path = tmp_path / "state.json"
    write_link_check_state(
        state_path, next_state([_result("a", "https://a.example", ok=False, error=GONE_404)])
    )
    before = state_path.read_text(encoding="utf-8")

    def _check(
        registry: Any, *, timeout_seconds: float, delay_seconds: float
    ) -> list[LinkCheckResult]:
        return [_result("a", "https://a.example", ok=False, error=GONE_404)]

    def _never(*args: Any, **kwargs: Any) -> str:
        raise AssertionError("a dry run must not reconcile the alert issue")

    monkeypatch.setattr(cli, "run_link_check", _check)
    monkeypatch.setattr(cli, "reconcile_link_rot_alert", _never)

    result = _invoke("--state-path", str(state_path), "--repository", "owner/repo", "--dry-run")

    assert result.exit_code == 1  # this URL is still confirmed against the pre-seeded state
    assert "dry run" in result.output
    assert state_path.read_text(encoding="utf-8") == before


def test_a_reconciliation_failure_is_reported_without_a_traceback(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    state_path = tmp_path / "state.json"
    write_link_check_state(
        state_path, next_state([_result("a", "https://a.example", ok=False, error=GONE_404)])
    )

    def _check(
        registry: Any, *, timeout_seconds: float, delay_seconds: float
    ) -> list[LinkCheckResult]:
        return [_result("a", "https://a.example", ok=False, error=GONE_404)]

    def _broken(*args: Any, **kwargs: Any) -> str:
        raise ValueError("gh: not authenticated")

    monkeypatch.setattr(cli, "run_link_check", _check)
    monkeypatch.setattr(cli, "reconcile_link_rot_alert", _broken)

    result = _invoke("--state-path", str(state_path), "--repository", "owner/repo")

    assert result.exit_code == 1
    assert "sources check-links failed" in result.output
    assert "gh: not authenticated" in result.output


def test_an_invalid_registry_is_reported_without_a_traceback(tmp_path: Path) -> None:
    bad_registry = tmp_path / "registry.yaml"
    bad_registry.write_text("not: a valid registry\n", encoding="utf-8")

    result = _invoke(str(bad_registry))

    assert result.exit_code == 1
    assert "sources check-links failed" in result.output
