"""Contracts for read-only production verification after deployment (#523)."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path
from typing import Any, cast

import yaml

PROJECT_ROOT = Path(__file__).parents[1]
WORKFLOW_PATH = PROJECT_ROOT / ".github" / "workflows" / "ci.yml"


def _workflow(path: Path = WORKFLOW_PATH) -> dict[str, Any]:
    return cast(dict[str, Any], yaml.load(path.read_text(encoding="utf-8"), Loader=yaml.BaseLoader))


def _run_probe_step(step: dict[str, Any], tmp_path: Path) -> list[str]:
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
        },
        check=True,
        capture_output=True,
        text=True,
    )
    return recorded.read_text(encoding="utf-8").splitlines()


def test_deployment_verifies_its_uploaded_sha_and_preserves_evidence(tmp_path: Path) -> None:
    workflow = _workflow(PROJECT_ROOT / ".github" / "workflows" / "ci.yml")
    steps = workflow["jobs"]["deploy"]["steps"]
    probe = next((step for step in steps if "check-production" in step.get("run", "")), None)
    assert probe is not None, "a production upload needs verification"
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
        "--output",
        "dist/production-probe.json",
    ]

    evidence = next(
        step for step in steps if step.get("name") == "Preserve production verification evidence"
    )
    assert steps.index(evidence) > steps.index(probe)
    assert evidence["if"] == "always()"
    assert evidence["with"]["path"] == "dist/production-probe.json"
