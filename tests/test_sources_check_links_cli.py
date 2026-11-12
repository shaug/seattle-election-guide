"""Behavior tests for the `sources check-links` CLI (O17)."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

import pytest
import yaml
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


def _set_check_time(monkeypatch: pytest.MonkeyPatch, value: str) -> None:
    instant = datetime.fromisoformat(value)

    class FrozenDatetime(datetime):
        @classmethod
        def now(cls, tz: Any = None) -> datetime:
            return instant.astimezone(tz)

    monkeypatch.setattr(cli, "datetime", FrozenDatetime)


@pytest.fixture(autouse=True)
def _voting_period_clock(monkeypatch: pytest.MonkeyPatch) -> None:
    _set_check_time(monkeypatch, "2026-11-03T20:00:00+00:00")


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


@pytest.mark.parametrize("instant", ["2026-11-02T20:00:00+00:00", "2026-11-04T07:59:59+00:00"])
def test_voting_period_requests_the_current_elections_links(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, instant: str
) -> None:
    _set_check_time(monkeypatch, instant)
    elections = []

    def check(registry: Any, **kwargs: Any) -> list[LinkCheckResult]:
        elections.append(registry.election_id)
        return [_result("a", "https://a.example", ok=True)]

    monkeypatch.setattr(cli, "run_link_check", check)
    monkeypatch.setattr(cli, "reconcile_link_rot_alert", lambda *args, **kwargs: "healthy")
    result = _invoke("--state-path", str(tmp_path / "state.json"))
    assert result.exit_code == 0, result.output
    assert elections == ["wa-2026-general"]
    assert "checked 1 cited link" in result.output


@pytest.mark.parametrize("instant", ["2026-11-04T08:00:00+00:00", "2026-11-12T20:00:00+00:00"])
@pytest.mark.parametrize("dry_run", [False, True])
def test_closed_voting_skips_fetch_and_alerts_without_rewriting_failures(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, instant: str, dry_run: bool
) -> None:
    _set_check_time(monkeypatch, instant)
    state = tmp_path / "state.json"
    write_link_check_state(
        state, next_state([_result("a", "https://a.example", ok=False, error=GONE_404)])
    )
    original = state.read_bytes()

    def forbidden(*args: Any, **kwargs: Any) -> Any:
        raise AssertionError("closed voting must not fetch, read state or reconcile alerts")

    monkeypatch.setattr(cli, "run_link_check", forbidden)
    monkeypatch.setattr(cli, "read_link_check_state", forbidden)
    monkeypatch.setattr(cli, "reconcile_link_rot_alert", forbidden)
    extra = ("--dry-run",) if dry_run else ()
    for _ in range(2):
        result = _invoke("--state-path", str(state), *extra)
        assert result.exit_code == 0, result.output
        assert "skipped" in result.output
        assert "2026-11-03" in result.output
        assert "Recovered" not in result.output
        assert state.read_bytes() == original


def test_default_registry_follows_a_site_current_election_change(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _set_check_time(monkeypatch, "2026-08-04T20:00:00+00:00")
    site = yaml.safe_load(Path("config/hosting/site.yaml").read_text())
    site["schema_version"] = "1.0"
    site.pop("historical_capabilities")
    site["current_election_id"] = "wa-2026-primary"
    site["elections"] = [e for e in site["elections"] if e["election_id"] == "wa-2026-primary"]
    site_path = tmp_path / "site.yaml"
    site_path.write_text(yaml.safe_dump(site))
    seen = []

    def check(registry: Any, **kwargs: Any) -> list[LinkCheckResult]:
        seen.append(registry.election_id)
        return [_result("a", "https://a.example", ok=True)]

    monkeypatch.setattr(cli, "run_link_check", check)
    monkeypatch.setattr(cli, "reconcile_link_rot_alert", lambda *args, **kwargs: "healthy")
    result = _invoke(
        "--site-manifest", str(site_path), "--state-path", str(tmp_path / "state.json")
    )
    assert result.exit_code == 0, result.output
    assert seen == ["wa-2026-primary"]


@pytest.mark.parametrize("bad_calendar", ["not: a calendar\n", "unknown-election"])
def test_bad_calendar_fails_before_source_requests(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, bad_calendar: str
) -> None:
    calendar_path = tmp_path / "calendar.yaml"
    if bad_calendar == "unknown-election":
        data = yaml.safe_load(Path("config/calendar/elections.yaml").read_text())
        data["elections"] = [e for e in data["elections"] if e["id"] != "wa-2026-general"]
        data["milestones"] = [
            m for m in data["milestones"] if m["election_id"] != "wa-2026-general"
        ]
        calendar_path.write_text(yaml.safe_dump(data))
    else:
        calendar_path.write_text(bad_calendar)

    def forbidden(*args: Any, **kwargs: Any) -> Any:
        raise AssertionError("invalid calendar must not fetch")

    monkeypatch.setattr(cli, "run_link_check", forbidden)
    result = _invoke("--calendar", str(calendar_path))
    assert result.exit_code == 1, result.output
    assert "sources check-links failed" in result.output


@pytest.mark.parametrize(
    "instant,dry_run,expected",
    [
        ("2026-11-03T20:00:00+00:00", False, "state_written=true\n"),
        ("2026-11-03T20:00:00+00:00", True, ""),
        ("2026-11-04T08:00:00+00:00", False, ""),
    ],
)
def test_workflow_cache_receipt_requires_an_actual_state_write(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, instant: str, dry_run: bool, expected: str
) -> None:
    _set_check_time(monkeypatch, instant)
    state = tmp_path / "state.json"
    write_link_check_state(
        state, next_state([_result("a", "https://a.example", ok=False, error=GONE_404)])
    )
    output = tmp_path / "github-output"
    output.touch()
    monkeypatch.setattr(
        cli,
        "run_link_check",
        lambda *args, **kwargs: [_result("a", "https://a.example", ok=False, error=GONE_404)],
    )
    monkeypatch.setattr(
        cli, "reconcile_link_rot_alert", lambda *args, **kwargs: "confirmed failure retained"
    )
    extra = ("--dry-run",) if dry_run else ()
    result = _invoke("--state-path", str(state), "--github-output", str(output), *extra)
    assert result.exit_code == (0 if "11-04" in instant else 1), result.output
    assert output.read_text() == expected


@pytest.mark.parametrize("identity", ["wa-unknown-election", "wa-2026-primary"])
def test_selected_registry_identity_errors_fail_before_fetching(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, identity: str
) -> None:
    root = Path.cwd()
    registry = yaml.safe_load((root / "config/sources/wa-2026-general.yaml").read_text())
    registry["election_id"] = identity
    registry_path = tmp_path / "config/sources/wa-2026-general.yaml"
    registry_path.parent.mkdir(parents=True)
    registry_path.write_text(yaml.safe_dump(registry))

    def forbidden(*args: Any, **kwargs: Any) -> Any:
        raise AssertionError("mismatched identity must not fetch")

    monkeypatch.setattr(cli, "run_link_check", forbidden)
    monkeypatch.chdir(tmp_path)
    extra = [str(registry_path)] if identity == "wa-unknown-election" else []
    result = _invoke(
        *extra,
        "--site-manifest",
        str(root / "config/hosting/site.yaml"),
        "--calendar",
        str(root / "config/calendar/elections.yaml"),
    )
    assert result.exit_code == 1, result.output
    assert "sources check-links failed" in result.output
    assert (
        "calendar declares no election" in result.output
        if extra
        else "does not match" in result.output
    )


@pytest.mark.parametrize("bad_input", ["missing-calendar", "invalid-site"])
def test_missing_calendar_or_invalid_site_never_requests_sources(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, bad_input: str
) -> None:
    def forbidden(*args: Any, **kwargs: Any) -> Any:
        raise AssertionError("invalid lifecycle input must not fetch")

    monkeypatch.setattr(cli, "run_link_check", forbidden)
    if bad_input == "missing-calendar":
        result = _invoke("--calendar", str(tmp_path / "missing.yaml"))
        assert result.exit_code == 2
    else:
        site = tmp_path / "site.yaml"
        site.write_text("schema_version: '1.0'\n")
        result = _invoke("--site-manifest", str(site))
        assert result.exit_code == 1
        assert "sources check-links failed" in result.output
