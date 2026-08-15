"""Structural tests for the scheduled production-verification workflow (O14)."""

from __future__ import annotations

from pathlib import Path
from typing import Any, cast

import yaml

PROJECT_ROOT = Path(__file__).parents[1]
WORKFLOW_PATH = PROJECT_ROOT / ".github" / "workflows" / "verify-production.yml"


def _workflow() -> dict[str, Any]:
    return cast(dict[str, Any], yaml.safe_load(WORKFLOW_PATH.read_text(encoding="utf-8")))


def _steps(workflow: dict[str, Any]) -> list[dict[str, Any]]:
    return cast(list[dict[str, Any]], workflow["jobs"]["verify"]["steps"])


def test_the_schedule_is_fine_grained_enough_for_the_pre_election_cadence() -> None:
    text = WORKFLOW_PATH.read_text(encoding="utf-8")
    schedule = [line.strip() for line in text.splitlines() if "cron:" in line]

    assert len(schedule) == 1
    cron = schedule[0].split('"')[1]
    minute, rest = cron.split()[0], cron.split()[1:]

    # Fine enough that the hourly fallback below and the always-on window
    # both land within it; coarser and the "raise the cadence" acceptance
    # criterion would have no room to raise into.
    assert minute == "*/15"
    assert rest == ["*", "*", "*", "*"]


def test_the_verify_step_gates_on_cadence_only_for_scheduled_runs() -> None:
    workflow = _workflow()
    steps = _steps(workflow)
    cadence_step = next(step for step in steps if step.get("id") == "cadence")
    verify_step = next(step for step in steps if "check-production" in step.get("run", ""))

    # A manual dispatch always runs the check; a scheduled tick only runs it
    # when the cadence step (calendar in-window, or the hourly fallback) says
    # so — never both unconditionally, or the acceptance criterion that
    # cadence rises in the pre-election window would be a no-op.
    assert cadence_step["if"] == "github.event_name == 'schedule'"
    assert "steps.cadence.outputs.due" in verify_step["if"]
    assert "github.event_name != 'schedule'" in verify_step["if"]


def test_the_cadence_step_consults_the_pre_election_window() -> None:
    workflow = _workflow()
    steps = _steps(workflow)
    cadence_step = next(step for step in steps if step.get("id") == "cadence")

    assert "calendar in-window" in cadence_step["run"]
    assert "config/calendar/elections.yaml" in cadence_step["run"]


def test_the_verify_step_compares_against_the_current_main_commit() -> None:
    workflow = _workflow()
    steps = _steps(workflow)
    verify_step = next(step for step in steps if "check-production" in step.get("run", ""))

    assert "--expected-git-commit" in verify_step["run"]
    assert "git rev-parse HEAD" in verify_step["run"]
    assert "hosting check-production" in verify_step["run"]


def test_the_workflow_can_open_and_update_alert_issues() -> None:
    workflow = _workflow()

    assert workflow["permissions"]["issues"] == "write"


def test_concurrent_runs_are_serialized_not_canceled() -> None:
    workflow = _workflow()

    assert workflow["concurrency"]["cancel-in-progress"] is False
