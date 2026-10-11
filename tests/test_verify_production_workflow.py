"""Contracts for scheduled availability and approved-deployment verification (#512)."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path
from typing import Any, cast

import pytest
import yaml

PROJECT_ROOT = Path(__file__).parents[1]
WORKFLOW_PATH = PROJECT_ROOT / ".github" / "workflows" / "verify-production.yml"


def _workflow(path: Path = WORKFLOW_PATH) -> dict[str, Any]:
    return cast(dict[str, Any], yaml.load(path.read_text(encoding="utf-8"), Loader=yaml.BaseLoader))


def _steps(workflow: dict[str, Any]) -> list[dict[str, Any]]:
    return cast(list[dict[str, Any]], workflow["jobs"]["verify"]["steps"])


def _run_probe_step(step: dict[str, Any], tmp_path: Path, *, dry_run: bool = False) -> list[str]:
    executable = tmp_path / "uv"
    executable.write_text(
        '#!/bin/sh\nprintf \'%s\\n\' "$@" > "$RECORDED_ARGUMENTS"\n', encoding="utf-8"
    )
    executable.chmod(0o755)
    recorded = tmp_path / "arguments.txt"
    subprocess.run(
        ["bash", "-euo", "pipefail", "-c", step["run"]],
        cwd=PROJECT_ROOT,
        env={
            **os.environ,
            "PATH": f"{tmp_path}:{os.environ['PATH']}",
            "RECORDED_ARGUMENTS": str(recorded),
            "PRODUCTION_ORIGIN": "https://seattleelections.guide",
            "GITHUB_REPOSITORY": "shaug/seattle-election-guide",
            "GITHUB_SHA": "b" * 40,
            "DRY_RUN": "1" if dry_run else "",
        },
        check=True,
        capture_output=True,
        text=True,
    )
    return recorded.read_text(encoding="utf-8").splitlines()


def test_availability_runs_hourly_off_the_hour() -> None:
    schedules = _workflow()["on"]["schedule"]
    assert len(schedules) == 1
    minute, *rest = schedules[0]["cron"].split()
    assert minute.isdigit() and 0 < int(minute) < 60
    assert rest == ["*", "*", "*", "*"]


def test_delayed_runs_cannot_skip_the_probe_on_an_execution_clock_gate() -> None:
    steps = _steps(_workflow())
    probe = next(step for step in steps if "check-production" in step.get("run", ""))
    assert "if" not in probe
    assert not any(step.get("id") == "cadence" for step in steps)


@pytest.mark.parametrize("dry_run", [False, True])
def test_scheduled_probe_checks_availability_without_a_main_commit(
    tmp_path: Path,
    dry_run: bool,
) -> None:
    step = next(step for step in _steps(_workflow()) if "check-production" in step.get("run", ""))
    arguments = _run_probe_step(step, tmp_path, dry_run=dry_run)
    assert arguments == [
        "run",
        "election-guide",
        "hosting",
        "check-production",
        "https://seattleelections.guide",
        "--availability-only",
        "--repository",
        "shaug/seattle-election-guide",
        *(["--dry-run"] if dry_run else []),
    ]


def test_the_workflow_can_open_and_update_alert_issues() -> None:
    assert _workflow()["permissions"]["issues"] == "write"


def test_concurrent_runs_are_serialized_not_canceled() -> None:
    assert _workflow()["concurrency"]["cancel-in-progress"] == "false"


def test_deployment_verifies_its_approved_sha_after_upload(tmp_path: Path) -> None:
    workflow = _workflow(PROJECT_ROOT / ".github" / "workflows" / "ci.yml")
    steps = workflow["jobs"]["deploy"]["steps"]
    probe = next((step for step in steps if "check-production" in step.get("run", "")), None)
    assert probe is not None, "an approved upload needs a production verification"
    upload = next(step for step in steps if step.get("name") == "Deploy production site")
    assert steps.index(probe) > steps.index(upload)
    assert "if" not in probe
    arguments = _run_probe_step(probe, tmp_path)
    assert arguments == [
        "run",
        "election-guide",
        "hosting",
        "check-production",
        "https://seattleelections.guide",
        "--expected-git-commit",
        "b" * 40,
        "--dry-run",
        "--output",
        "dist/production-probe.json",
    ]
