"""Executable delivery graph and credential boundaries for issue #550."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path
from typing import Any

import pytest
import yaml

ROOT = Path(__file__).parents[1]


def workflow(name: str = "ci.yml") -> dict[str, Any]:
    return yaml.load((ROOT / ".github/workflows" / name).read_text(), Loader=yaml.BaseLoader)


def test_mainline_serialization_preserves_queued_release() -> None:
    document = workflow()
    lock = document["concurrency"]
    assert lock["queue"] == "max"
    assert lock["cancel-in-progress"] == "false"
    assert "verified-release-mainline" in lock["group"]
    assert "ci-pr-" in lock["group"] and "github.run_id" in lock["group"]
    assert all("concurrency" not in job for job in document["jobs"].values())


def test_publish_requires_every_lane_and_exact_merged_source() -> None:
    jobs = workflow()["jobs"]
    assert jobs["publish"]["needs"] == ["check", "publication"]
    assert jobs["check"]["needs"] == ["python", "client", "contracts", "tests", "publication"]
    assert "publication-evidence" in jobs["deploy"]["needs"]
    assert "check" in jobs["deploy"]["needs"]
    assert jobs["finalize"]["needs"] == ["deploy"]
    publish = "\n".join(s.get("run", "") for s in jobs["publish"]["steps"])
    assert "automation admit" in publish and "--preflight" not in publish
    for name in jobs["check"]["needs"]:
        checkout = next(s for s in jobs[name]["steps"] if s.get("uses") == "actions/checkout@v4")
        assert checkout["with"]["ref"] == "${{ inputs.source_sha || github.sha }}"
        assert checkout["with"]["fetch-depth"] == "0"
    step = jobs["check"]["steps"][0]
    for result in ["success", "failure", "cancelled", "skipped"]:
        env = {key: "success" for key in step["env"]}
        env["PUBLICATION_RESULT"] = result
        observed = subprocess.run(
            ["bash", "-euo", "pipefail", "-c", step["run"]], env=env, check=False
        )
        assert (observed.returncode == 0) == (result == "success")


def test_privileges_and_switch_scope() -> None:
    jobs = workflow()["jobs"]
    assert jobs["publish"]["permissions"]["contents"] == "write"
    for name in ["publish", "publication-evidence", "deploy"]:
        assert "github.event_name != 'pull_request'" in jobs[name]["if"]
        assert "github.ref == 'refs/heads/main'" in jobs[name]["if"]
    assert "CLOUDFLARE_PAGES_ENABLED" not in jobs["publish"]["if"]
    assert "CLOUDFLARE_PAGES_ENABLED" not in jobs["publication-evidence"]["if"]
    assert jobs["deploy"]["environment"]["name"] == "production"
    for name, job in jobs.items():
        assert "CLOUDFLARE_API_TOKEN" not in str(job.get("env", {}))
        for step in job.get("steps", []):
            if "secrets.CLOUDFLARE_" in str(step):
                assert name == "deploy"
                assert step["if"] == "steps.admission.outputs.state == 'eligible'"
                assert "automation upload" in step["run"]
        if name not in ["publication-evidence", "finalize"]:
            assert job.get("permissions", {}).get("issues") != "write"


def test_attempt_scoped_artifact_ids_flow_through_jobs() -> None:
    jobs = workflow()["jobs"]
    for name in ["publication", "publish", "publication-evidence", "deploy", "finalize"]:
        retained = [s for s in jobs[name]["steps"] if s.get("uses") == "actions/upload-artifact@v4"]
        assert any(s.get("if") == "always()" for s in retained), name
        for step in retained:
            assert "github.run_id" in step["with"]["name"]
            assert "github.run_attempt" in step["with"]["name"]
            assert step["with"]["retention-days"] == "7"
    for name in ["publish", "publication-evidence", "deploy", "finalize"]:
        scripts = "\n".join(s.get("run", "") for s in jobs[name]["steps"])
        assert "automation fetch-artifact" in scripts
        assert "ARTIFACT_ID" in scripts
    assert "steps.candidate.outputs.artifact-id" in str(jobs["publication"]["outputs"])


def test_verification_rerun_cannot_build_or_upload() -> None:
    document = workflow("verify-release.yml")
    assert set(document["on"]["workflow_dispatch"]["inputs"]) == {
        "issue",
        "release_version",
        "source_sha",
        "run_id",
        "run_attempt",
    }
    text = str(document)
    for forbidden in [
        "CLOUDFLARE",
        "pages:deploy",
        "automation build",
        "automation record-upload",
        "contents': 'write",
    ]:
        assert forbidden not in text
    assert "automation recover-upload" in text and "automation finalize" in text
    assert "github.ref == 'refs/heads/main'" in document["jobs"]["verify"]["if"]


def test_local_upload_route_is_retired() -> None:
    result = subprocess.run(
        ["make", "hosting-deploy"], cwd=ROOT, capture_output=True, text=True, check=False
    )
    assert result.returncode != 0
    assert "verify-release.yml" in result.stdout + result.stderr


@pytest.mark.parametrize("timeout", ["0", "-1", "nan", "inf"])
def test_invalid_wait_timeout_uses_cli_error(timeout: str) -> None:
    from typer.testing import CliRunner

    from election_guide.cli import app

    result = CliRunner().invoke(
        app,
        [
            "hosting",
            "check-production",
            "https://seattleelections.guide",
            "--wait",
            "--expected-git-commit",
            "a" * 40,
            "--timeout",
            timeout,
        ],
    )
    assert result.exit_code == 1
    assert "hosting check-production failed:" in result.output
    assert isinstance(result.exception, SystemExit)


@pytest.mark.parametrize(
    "scenario", ["complete", "superseded", "paused", "expired-recovery", "failed-probe-retry"]
)
def test_shell_delivery_paths_preserve_one_upload_and_finalization_order(
    tmp_path: Path, scenario: str
) -> None:
    """Execute delivery shell with fixture command boundaries, including failure/rerun.

    Adapter tests separately run real evidence, admission and upload policy. This test
    catches a shell command that ignores a failure, uploads on a skipped state, changes
    the captured source, or reports success before finalization.
    """
    import json
    import sys

    jobs = workflow()["jobs"]
    binary = tmp_path / "uv"
    binary.write_text(
        f"#!{sys.executable}\n"
        + """
import json, os, pathlib, sys
args = sys.argv[1:]
with open('calls.jsonl', 'a') as stream:
    stream.write(json.dumps(args) + '\\n')
assert args[:3] == ['run', 'election-guide', 'release']
assert args[3] == 'automation'
command = args[4]
pathlib.Path('dist/upload').mkdir(parents=True, exist_ok=True)
if command == 'delivery-check':
    state = os.environ['FIXTURE_STATE']
    with open(os.environ['GITHUB_OUTPUT'], 'a') as stream:
        stream.write('state=' + state + '\\n')
    if state != 'eligible':
        pathlib.Path('dist/upload/operation.json').write_text(json.dumps({'state':state}))
elif command == 'create-deployment':
    pathlib.Path('dist/upload/deployment.json').write_text('{"id":50}')
elif command == 'upload':
    source = os.environ['RELEASE_SOURCE_SHA']
    pathlib.Path('dist/upload/upload.json').write_text(json.dumps({'source_sha':source}))
elif command == 'finalize' and os.environ.get('FAIL_PROBE') == 'true':
    sys.exit(1)
elif command not in ['finalize', 'deployment-status', 'retain-operation']:
    raise AssertionError(args)
"""
    )
    binary.chmod(0o755)
    state = {"superseded": "superseded", "paused": "deployment_paused"}.get(scenario, "eligible")
    env = {
        **os.environ,
        "PATH": f"{tmp_path}:{os.environ['PATH']}",
        "GITHUB_OUTPUT": str(tmp_path / "outputs"),
        "RELEASE_SOURCE_SHA": "a" * 40,
        "GITHUB_SHA": ("b" if scenario == "expired-recovery" else "a") * 40,
        "FIXTURE_STATE": state,
    }

    def run(step: dict[str, Any], **extra: str) -> int:
        return subprocess.run(
            ["bash", "-euo", "pipefail", "-c", step["run"]],
            cwd=tmp_path,
            env=env | extra,
            check=False,
        ).returncode

    steps = jobs["deploy"]["steps"]
    admission = next(s for s in steps if s.get("id") == "admission")
    assert run(admission) == 0
    observed_state = (tmp_path / "outputs").read_text().strip().split("=")[1]
    for name in ["Create owned production deployment", "Deploy production site"]:
        step = next(s for s in steps if s.get("name") == name)
        assert step["if"] == "steps.admission.outputs.state == 'eligible'"
        if observed_state == "eligible":
            assert run(step) == 0
    finish = next(
        s
        for s in jobs["finalize"]["steps"]
        if s.get("name") == "Finalize uploaded or skipped operation"
    )
    if scenario == "failed-probe-retry":
        assert run(finish, FAIL_PROBE="true") == 1
        calls = [
            json.loads(line)[4] for line in (tmp_path / "calls.jsonl").read_text().splitlines()
        ]
        assert "deployment-status" not in calls
    assert run(finish) == 0
    calls = [json.loads(line)[4] for line in (tmp_path / "calls.jsonl").read_text().splitlines()]
    assert calls.count("upload") == (1 if state == "eligible" else 0)
    if state == "eligible":
        assert calls[-2:] == ["finalize", "deployment-status"]
        assert (
            json.loads((tmp_path / "dist/upload/upload.json").read_text())["source_sha"] == "a" * 40
        )
    else:
        assert calls[-1] == "retain-operation"
