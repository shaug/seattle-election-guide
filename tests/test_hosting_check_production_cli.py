"""Behavior tests for the `hosting check-production` and `calendar in-window` CLI (O14)."""

from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Any

import pytest
import yaml
from typer.testing import CliRunner

from election_guide import cli
from election_guide.hosting.production_alert import ProductionAlertTracker
from election_guide.hosting.production_check import ProductionCheckReport
from tests.test_production_check import (
    COMMIT,
    _failing_report,  # pyright: ignore[reportPrivateUsage]
    _healthy_report,  # pyright: ignore[reportPrivateUsage]
)


def _stub_failing_check(monkeypatch: pytest.MonkeyPatch) -> None:
    def _check(base_url: str, *, expected_git_commit: str, timeout: float) -> ProductionCheckReport:
        return _failing_report()

    monkeypatch.setattr(cli, "run_production_check", _check)


def test_a_healthy_run_exits_zero_and_reconciles_the_alert(monkeypatch: pytest.MonkeyPatch) -> None:
    recorded: dict[str, Any] = {}

    def _check(base_url: str, *, expected_git_commit: str, timeout: float) -> ProductionCheckReport:
        recorded["base_url"] = base_url
        recorded["expected_git_commit"] = expected_git_commit
        return _healthy_report()

    def _reconcile(
        tracker: ProductionAlertTracker,
        report: ProductionCheckReport,
        *,
        base_url: str,
        checked_at: str,
    ) -> str:
        recorded["reconciled"] = True
        return "healthy; no open alert"

    monkeypatch.setattr(cli, "run_production_check", _check)
    monkeypatch.setattr(cli, "reconcile_alert", _reconcile)

    result = CliRunner().invoke(
        cli.app,
        [
            "hosting",
            "check-production",
            "https://seattleelections.guide",
            "--expected-git-commit",
            COMMIT,
        ],
    )

    assert result.exit_code == 0
    assert recorded["base_url"] == "https://seattleelections.guide"
    assert recorded["expected_git_commit"] == COMMIT
    assert recorded["reconciled"] is True
    assert "PASS" in result.output


def test_a_failing_run_exits_nonzero_after_reconciling(monkeypatch: pytest.MonkeyPatch) -> None:
    _stub_failing_check(monkeypatch)

    def _reconcile(
        tracker: ProductionAlertTracker,
        report: ProductionCheckReport,
        *,
        base_url: str,
        checked_at: str,
    ) -> str:
        return "opened alert issue: https://x/9"

    monkeypatch.setattr(cli, "reconcile_alert", _reconcile)

    result = CliRunner().invoke(
        cli.app,
        [
            "hosting",
            "check-production",
            "https://seattleelections.guide",
            "--expected-git-commit",
            COMMIT,
        ],
    )

    assert result.exit_code == 1
    assert "FAIL" in result.output
    assert "opened alert issue" in result.output


def test_a_dry_run_never_touches_the_alert_tracker(monkeypatch: pytest.MonkeyPatch) -> None:
    _stub_failing_check(monkeypatch)

    def _never(*args: Any, **kwargs: Any) -> str:
        raise AssertionError("a dry run must not reconcile the alert issue")

    monkeypatch.setattr(cli, "reconcile_alert", _never)

    result = CliRunner().invoke(
        cli.app,
        [
            "hosting",
            "check-production",
            "https://seattleelections.guide",
            "--expected-git-commit",
            COMMIT,
            "--dry-run",
        ],
    )

    assert result.exit_code == 1
    assert "dry run" in result.output


def test_a_reconciliation_failure_is_reported_without_a_traceback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _stub_failing_check(monkeypatch)

    def _broken(*args: Any, **kwargs: Any) -> str:
        raise ValueError("gh: not authenticated")

    monkeypatch.setattr(cli, "reconcile_alert", _broken)

    result = CliRunner().invoke(
        cli.app,
        [
            "hosting",
            "check-production",
            "https://seattleelections.guide",
            "--expected-git-commit",
            COMMIT,
        ],
    )

    assert result.exit_code == 1
    assert "hosting check-production failed" in result.output
    assert "gh: not authenticated" in result.output


def _write_calendar(path: Path, *, election_date: date) -> Path:
    calendar_path = path / "elections.yaml"
    calendar_path.write_text(
        yaml.safe_dump(
            {
                "schema_version": "1.0",
                "elections": [
                    {
                        "id": "wa-2027-general",
                        "election_type": "general",
                        "election_scope": "municipal",
                        "election_date": election_date.isoformat(),
                        "state": "WA",
                    }
                ],
                "milestones": [
                    {
                        "election_id": "wa-2027-general",
                        "id": "election-day",
                        "kind": "election_day",
                        "offset_days": 0,
                    },
                    {
                        "election_id": "wa-2027-general",
                        "id": "results-capture-election-night",
                        "kind": "results_capture_election_night",
                        "offset_days": 0,
                    },
                    {
                        "election_id": "wa-2027-general",
                        "id": "results-capture-post-certification",
                        "kind": "results_capture_post_certification",
                        "offset_days": 22,
                    },
                ],
            }
        ),
        encoding="utf-8",
    )
    return calendar_path


def test_in_window_is_true_inside_the_pre_election_window(tmp_path: Path) -> None:
    calendar_path = _write_calendar(tmp_path, election_date=date(2027, 11, 2))

    result = CliRunner().invoke(
        cli.app,
        [
            "calendar",
            "in-window",
            str(calendar_path),
            "--before-days",
            "7",
            "--as-of",
            "2027-10-28",
        ],
    )

    assert result.exit_code == 0
    assert result.output.strip() == "true"


def test_in_window_is_false_outside_the_pre_election_window(tmp_path: Path) -> None:
    calendar_path = _write_calendar(tmp_path, election_date=date(2027, 11, 2))

    result = CliRunner().invoke(
        cli.app,
        [
            "calendar",
            "in-window",
            str(calendar_path),
            "--before-days",
            "7",
            "--as-of",
            "2027-10-01",
        ],
    )

    assert result.exit_code == 1
    assert result.output.strip() == "false"


def test_in_window_is_true_on_election_day_itself(tmp_path: Path) -> None:
    calendar_path = _write_calendar(tmp_path, election_date=date(2027, 11, 2))

    result = CliRunner().invoke(
        cli.app,
        [
            "calendar",
            "in-window",
            str(calendar_path),
            "--before-days",
            "7",
            "--as-of",
            "2027-11-02",
        ],
    )

    assert result.exit_code == 0
    assert result.output.strip() == "true"


def test_in_window_is_false_the_day_after_election_day(tmp_path: Path) -> None:
    calendar_path = _write_calendar(tmp_path, election_date=date(2027, 11, 2))

    result = CliRunner().invoke(
        cli.app,
        [
            "calendar",
            "in-window",
            str(calendar_path),
            "--before-days",
            "7",
            "--as-of",
            "2027-11-03",
        ],
    )

    assert result.exit_code == 1
    assert result.output.strip() == "false"
