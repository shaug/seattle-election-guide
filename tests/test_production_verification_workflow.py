"""Contracts for read-only production verification after deployment (#523, #563)."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any, cast

import pytest
import yaml

PROJECT_ROOT = Path(__file__).parents[1]
WORKFLOW_PATH = PROJECT_ROOT / ".github" / "workflows" / "ci.yml"


def _workflow(path: Path = WORKFLOW_PATH) -> dict[str, Any]:
    return cast(dict[str, Any], yaml.load(path.read_text(encoding="utf-8"), Loader=yaml.BaseLoader))


def _probe_step() -> dict[str, Any]:
    steps = _workflow()["jobs"]["deploy"]["steps"]
    return next(step for step in steps if "check-production" in step.get("run", ""))


def _run_probe_step(
    step: dict[str, Any], tmp_path: Path, outcomes: tuple[str, ...] = ("healthy",)
) -> subprocess.CompletedProcess[str]:
    # Execute the actual workflow shell. Only the strict HTTP checker and the
    # real-time delay are replaced; their outcomes are controlled independently
    # so a retry, streak-reset, or evidence-copy bug changes the shell's result.
    executable = tmp_path / "uv"
    executable.write_text(
        f"#!{sys.executable}\n"
        + """import json
import os
import sys
from pathlib import Path

calls = Path(os.environ['RECORDED_CALLS'])
previous = calls.read_text().splitlines() if calls.exists() else []
outcomes = json.loads(os.environ['PROBE_OUTCOMES'])
state = outcomes[min(len(previous), len(outcomes) - 1)]
arguments = sys.argv[1:]
record = {'arguments': arguments, 'state': state}
with calls.open('a') as stream:
    stream.write(json.dumps(record) + '\\n')
if state != 'missing-evidence':
    output = Path(arguments[arguments.index('--output') + 1])
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps({'state': state}))
sys.exit(0 if state == 'healthy' else 1)
""",
        encoding="utf-8",
    )
    executable.chmod(0o755)
    sleeper = tmp_path / "sleep"
    sleeper.write_text('#!/bin/sh\nprintf \'%s\\n\' "$@" >> "$RECORDED_SLEEPS"\n', encoding="utf-8")
    sleeper.chmod(0o755)
    return subprocess.run(
        ["bash", "-euo", "pipefail", "-c", step["run"]],
        cwd=tmp_path,
        env={
            **os.environ,
            "PATH": f"{tmp_path}:{os.environ['PATH']}",
            "RECORDED_CALLS": str(tmp_path / "calls.jsonl"),
            "RECORDED_SLEEPS": str(tmp_path / "sleeps.txt"),
            "PROBE_OUTCOMES": json.dumps(outcomes),
            "PRODUCTION_ORIGIN": "https://seattleelections.guide",
            "GITHUB_REPOSITORY": "shaug/seattle-election-guide",
            "GITHUB_SHA": "b" * 40,
        },
        check=False,
        capture_output=True,
        text=True,
        timeout=10,
    )


def _calls(tmp_path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in (tmp_path / "calls.jsonl").read_text().splitlines()]


def _reports(tmp_path: Path) -> list[dict[str, Any]]:
    paths = sorted(
        (tmp_path / "dist/production-probes").glob("attempt-*.json"),
        key=lambda path: int(path.stem.removeprefix("attempt-")),
    )
    return [json.loads(path.read_text()) for path in paths]


def test_deployment_verifies_its_uploaded_sha_and_preserves_evidence(tmp_path: Path) -> None:
    steps = _workflow()["jobs"]["deploy"]["steps"]
    probe = _probe_step()
    upload = next(step for step in steps if step.get("name") == "Deploy production site")
    assert steps.index(probe) > steps.index(upload)
    assert "if" not in probe
    assert 0 < float(probe["timeout-minutes"]) <= 3
    result = _run_probe_step(probe, tmp_path)
    assert result.returncode == 0, result.stdout + result.stderr
    calls = _calls(tmp_path)
    assert len(calls) == 2, "one passing edge response must be confirmed"
    for number, call in enumerate(calls, 1):
        assert call["arguments"] == [
            "run",
            "election-guide",
            "hosting",
            "check-production",
            "https://seattleelections.guide",
            "--expected-git-commit",
            "b" * 40,
            "--output",
            f"dist/production-probes/attempt-{number}.json",
        ]
    assert (tmp_path / "sleeps.txt").read_text().splitlines() == ["5"]
    assert json.loads((tmp_path / "dist/production-probe.json").read_text()) == {"state": "healthy"}

    evidence = next(
        step for step in steps if step.get("name") == "Preserve production verification evidence"
    )
    assert steps.index(evidence) > steps.index(probe)
    assert evidence["if"] == "always()"
    assert set(evidence["with"]["path"].splitlines()) == {
        "dist/production-probe.json",
        "dist/production-probes/",
    }


def test_propagation_waits_for_the_expected_deployment_then_confirms_it(tmp_path: Path) -> None:
    result = _run_probe_step(_probe_step(), tmp_path, ("old-commit", "healthy", "healthy"))
    assert result.returncode == 0, result.stdout + result.stderr
    assert [report["state"] for report in _reports(tmp_path)] == [
        "old-commit",
        "healthy",
        "healthy",
    ]
    assert (tmp_path / "sleeps.txt").read_text().splitlines() == ["5", "5"]


def test_an_intervening_failure_resets_the_confirmation_streak(tmp_path: Path) -> None:
    states = ("healthy", "old-commit", "healthy", "bad-route", "healthy", "healthy")
    result = _run_probe_step(_probe_step(), tmp_path, states)
    assert result.returncode == 0, result.stdout + result.stderr
    assert [report["state"] for report in _reports(tmp_path)] == list(states)


@pytest.mark.parametrize("failure", ["old-commit", "bad-route", "invalid-manifest"])
def test_persistent_failure_still_fails_with_all_attempt_evidence(
    tmp_path: Path, failure: str
) -> None:
    result = _run_probe_step(_probe_step(), tmp_path, (failure,))
    assert result.returncode != 0
    assert len(_calls(tmp_path)) == 24
    assert len(_reports(tmp_path)) == 24
    assert all(report["state"] == failure for report in _reports(tmp_path))
    assert (tmp_path / "sleeps.txt").read_text().splitlines() == ["5"] * 23
    assert "::error::" in result.stdout


def test_missing_attempt_evidence_fails_without_reusing_a_previous_report(tmp_path: Path) -> None:
    previous = tmp_path / "dist/production-probe.json"
    previous.parent.mkdir()
    previous.write_text(json.dumps({"state": "healthy"}))
    result = _run_probe_step(_probe_step(), tmp_path, ("missing-evidence",))
    assert result.returncode != 0
    assert len(_calls(tmp_path)) == 1
    assert not _reports(tmp_path)
    assert not (tmp_path / "sleeps.txt").exists()
