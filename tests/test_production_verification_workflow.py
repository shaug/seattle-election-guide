"""Verification consumes the recorded upload and cannot repeat it (#550)."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).parents[1]


def test_deployment_verifies_its_uploaded_sha_and_preserves_evidence(tmp_path: Path) -> None:
    workflow: dict[str, Any] = yaml.load(
        (ROOT / ".github/workflows/ci.yml").read_text(), Loader=yaml.BaseLoader
    )
    job = workflow["jobs"]["finalize"]
    assert job["needs"] == ["deploy"]
    assert job["permissions"]["issues"] == "write"
    step = next(
        s for s in job["steps"] if s.get("name") == "Finalize uploaded or skipped operation"
    )
    executable = tmp_path / "uv"
    executable.write_text('#!/bin/sh\nprintf "%s\\n" "$*" >> "$RECORDED_ARGUMENTS"\n')
    executable.chmod(0o755)
    calls = tmp_path / "calls"
    subprocess.run(
        ["bash", "-euo", "pipefail", "-c", step["run"]],
        cwd=tmp_path,
        env={
            **os.environ,
            "PATH": f"{tmp_path}:{os.environ['PATH']}",
            "RECORDED_ARGUMENTS": str(calls),
        },
        check=True,
    )
    assert calls.read_text().splitlines() == [
        "run election-guide release automation finalize --upload dist/upload/upload.json "
        "--output-dir dist/finalization",
        "run election-guide release automation deployment-status --upload dist/upload/upload.json",
    ]
    retained = next(s for s in job["steps"] if s.get("uses") == "actions/upload-artifact@v4")
    assert retained["if"] == "always()"
    assert "dist/finalization" in retained["with"]["path"]
    assert "secrets" not in str(job)
