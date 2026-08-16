"""Structural tests for the scheduled link-rot check workflow (O17)."""

from __future__ import annotations

from pathlib import Path
from typing import Any, cast

import yaml

PROJECT_ROOT = Path(__file__).parents[1]
WORKFLOW_PATH = PROJECT_ROOT / ".github" / "workflows" / "check-links.yml"

STATE_PATH = ".cache/link-check-state.json"


def _workflow() -> dict[str, Any]:
    return cast(dict[str, Any], yaml.safe_load(WORKFLOW_PATH.read_text(encoding="utf-8")))


def _steps(workflow: dict[str, Any]) -> list[dict[str, Any]]:
    return cast(list[dict[str, Any]], workflow["jobs"]["check"]["steps"])


def test_the_workflow_is_scheduled_daily() -> None:
    text = WORKFLOW_PATH.read_text(encoding="utf-8")
    schedule = [line.strip() for line in text.splitlines() if "cron:" in line]

    assert len(schedule) == 1
    cron = schedule[0].split('"')[1]
    minute, hour, rest = cron.split()[0], cron.split()[1], cron.split()[2:]
    assert minute.isdigit()
    assert hour.isdigit()
    assert rest == ["*", "*", "*"]


def test_the_workflow_can_open_and_close_alert_issues() -> None:
    workflow = _workflow()

    assert workflow["permissions"]["issues"] == "write"


def test_concurrent_runs_are_serialized_not_canceled() -> None:
    workflow = _workflow()

    assert workflow["concurrency"]["cancel-in-progress"] is False


def test_the_check_step_invokes_sources_check_links_with_the_repository() -> None:
    workflow = _workflow()
    steps = _steps(workflow)
    check_step = next(step for step in steps if "sources check-links" in step.get("run", ""))

    assert "--repository" in check_step["run"]
    assert "GITHUB_REPOSITORY" in check_step["run"]
    assert check_step["env"]["GH_TOKEN"] == "${{ github.token }}"


def test_state_is_restored_before_the_check_and_saved_after() -> None:
    workflow = _workflow()
    steps = _steps(workflow)
    check_index = next(
        index for index, step in enumerate(steps) if "sources check-links" in step.get("run", "")
    )
    restore_index = next(
        index
        for index, step in enumerate(steps)
        if step.get("uses", "").startswith("actions/cache/restore")
    )
    save_index = next(
        index
        for index, step in enumerate(steps)
        if step.get("uses", "").startswith("actions/cache/save")
    )

    assert restore_index < check_index < save_index
    assert steps[restore_index]["with"]["path"] == STATE_PATH
    assert steps[save_index]["with"]["path"] == STATE_PATH


def test_the_cache_key_is_unique_per_run_so_save_never_conflicts() -> None:
    workflow = _workflow()
    steps = _steps(workflow)
    save_step = next(
        step for step in steps if step.get("uses", "").startswith("actions/cache/save")
    )

    assert "github.run_id" in save_step["with"]["key"]


def test_the_cache_restore_falls_back_to_the_most_recent_prior_state() -> None:
    workflow = _workflow()
    steps = _steps(workflow)
    restore_step = next(
        step for step in steps if step.get("uses", "").startswith("actions/cache/restore")
    )

    assert "restore-keys" in restore_step["with"]


def test_the_save_step_always_runs_even_after_a_confirmed_failure_exit() -> None:
    """A confirmed link-rot failure exits the check step nonzero (O17's own
    alert-worthy outcome); the save step must still run so next run's
    comparison sees this run's failing set."""
    workflow = _workflow()
    steps = _steps(workflow)
    save_step = next(
        step for step in steps if step.get("uses", "").startswith("actions/cache/save")
    )

    assert "always()" in save_step["if"]


def test_a_dry_run_skips_saving_state() -> None:
    workflow = _workflow()
    steps = _steps(workflow)
    save_step = next(
        step for step in steps if step.get("uses", "").startswith("actions/cache/save")
    )

    assert "dry_run" in save_step["if"]


def test_workflow_dispatch_accepts_a_dry_run_input() -> None:
    workflow = _workflow()

    # PyYAML's default resolver reads the bare `on:` key as boolean True
    # (the YAML 1.1 on/off/yes/no quirk), so it is looked up as such here
    # rather than by the string "on".
    on_section = cast(dict[Any, Any], workflow)[True]
    dispatch_inputs = on_section["workflow_dispatch"]["inputs"]
    assert dispatch_inputs["dry_run"]["type"] == "boolean"
