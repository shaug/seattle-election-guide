"""Recorded-upload propagation confirmation and durable evidence (#550, #563)."""

from __future__ import annotations

import json
import os
import shlex
import subprocess
from itertools import pairwise
from pathlib import Path
from typing import Any, cast

import pytest
import yaml
from typer.testing import CliRunner

from election_guide.hosting import production_wait
from election_guide.hosting.production_check import (
    CommitCheck,
    Observation,
    ProductionCheckReport,
    RouteCheckResult,
)
from election_guide.release.automation_cli import app
from tests.test_release_evidence import (
    evidence_setup,  # noqa: F401 # pyright: ignore[reportUnusedImport]
    operation,
    successful_report,
)
from tests.test_release_promotion import (
    promotion_setup,  # noqa: F401 # pyright: ignore[reportUnusedImport]
)
from tests.test_release_publication import (
    setup_publication,  # noqa: F401 # pyright: ignore[reportUnusedImport]
)

ROOT = Path(__file__).parents[1]


def _finalization_job() -> dict[str, Any]:
    workflow: dict[str, Any] = yaml.load(
        (ROOT / ".github/workflows/ci.yml").read_text(), Loader=yaml.BaseLoader
    )
    return workflow["jobs"]["finalize"]


def _finalization_step() -> dict[str, Any]:
    return next(
        step
        for step in _finalization_job()["steps"]
        if step.get("name") == "Finalize uploaded or skipped operation"
    )


def test_recovery_can_retain_evidence_on_owning_pull_requests() -> None:
    workflow: dict[str, Any] = yaml.load(
        (ROOT / ".github/workflows/verify-release.yml").read_text(), Loader=yaml.BaseLoader
    )
    assert workflow["permissions"] == {
        "contents": "read",
        "actions": "read",
        "issues": "write",
        "pull-requests": "write",
        "deployments": "write",
    }
    assert set(workflow["on"]) == {"workflow_dispatch"}
    assert workflow["jobs"]["verify"]["if"] == "github.ref == 'refs/heads/main'"


@pytest.mark.parametrize("finalize_status", [0, 1])
def test_deployment_verifies_its_uploaded_sha_and_preserves_evidence(
    tmp_path: Path, finalize_status: int
) -> None:
    job = _finalization_job()
    assert job["needs"] == ["deploy"]
    assert job["permissions"]["issues"] == "write"
    step = _finalization_step()
    assert 0 < float(step["timeout-minutes"]) <= 3
    executable = tmp_path / "uv"
    executable.write_text(
        '#!/bin/sh\nprintf "%s\\n" "$*" >> "$RECORDED_ARGUMENTS"\n'
        'case "$*" in *" automation finalize "*) exit "$FINALIZE_STATUS";; esac\n'
    )
    executable.chmod(0o755)
    calls = tmp_path / "calls"
    result = subprocess.run(
        ["bash", "-euo", "pipefail", "-c", step["run"]],
        cwd=tmp_path,
        env={
            **os.environ,
            "PATH": f"{tmp_path}:{os.environ['PATH']}",
            "RECORDED_ARGUMENTS": str(calls),
            "FINALIZE_STATUS": str(finalize_status),
        },
        check=False,
    )
    assert result.returncode == finalize_status
    expected = [
        "run election-guide release automation finalize --upload dist/upload/upload.json "
        "--output-dir dist/finalization",
    ]
    if finalize_status == 0:
        expected.append(
            "run election-guide release automation deployment-status "
            "--upload dist/upload/upload.json"
        )
    assert calls.read_text().splitlines() == expected
    retained = next(s for s in job["steps"] if s.get("uses") == "actions/upload-artifact@v4")
    assert retained["if"] == "always()"
    assert "dist/finalization" in retained["with"]["path"]
    assert "secrets" not in str(job)


def _probe_outcome(healthy: ProductionCheckReport, state: str) -> ProductionCheckReport:
    if state == "healthy":
        return healthy
    if state == "old-commit":
        assert healthy.commit is not None
        return healthy.model_copy(
            update={"commit": CommitCheck(expected=healthy.commit.expected, observed="f" * 40)}
        )
    if state == "invalid-manifest":
        return healthy.model_copy(update={"manifest_parse_error": "invalid manifest"})
    if state in {"bad-route", "redirect"}:
        routes = list(healthy.route_results)
        routes[0] = RouteCheckResult(
            check=routes[0].check,
            observed=Observation(
                status=404 if state == "bad-route" else 307, raw_location="/wrong"
            ),
        )
        return healthy.model_copy(update={"route_results": tuple(routes)})
    assert state == "missing-evidence"
    return ProductionCheckReport(
        base_url=healthy.base_url,
        checked_at=healthy.checked_at,
        manifest=RouteCheckResult(
            check=healthy.manifest.check,
            observed=Observation(error="production probe worker did not return evidence"),
        ),
    )


def _run_recorded_finalizer(
    setup: tuple[Any, ...], monkeypatch: pytest.MonkeyPatch, states: tuple[str, ...]
) -> tuple[int, dict[str, Any], list[float]]:
    """Run the workflow's real CLI/finalizer/waiter; replace only HTTP and time."""
    evidence, _, _, publication, upload, root = setup
    evidence.retain_evidence(operation(publication), issue_number=550, reports={})
    healthy = successful_report(setup).attempts[0]
    output = root / "dist/finalization"
    output.mkdir()
    # A leftover successful local report has no durable receipt and must not
    # replace fresh confirmation, even when the next worker supplies no evidence.
    stale = successful_report(setup).model_dump(mode="json")
    (output / "production-wait.json").write_text(json.dumps(stale))
    upload_path = root / "dist/upload/upload.json"
    upload_path.parent.mkdir()
    upload_path.write_text(upload.model_dump_json())
    original_upload = upload_path.read_bytes()
    starts: list[float] = []
    now = 0.0

    def delay(seconds: float) -> None:
        nonlocal now
        assert seconds >= 0
        now += seconds

    def probe(base_url: str, **kwargs: Any) -> ProductionCheckReport:
        assert base_url == healthy.base_url
        assert kwargs["site_manifest"] == healthy.deployment_contract.expected_site
        assert kwargs["expected_git_commit"] == upload.source_sha
        assert len(upload.source_sha) == 40
        assert kwargs["deadline"] == 120
        assert 0 < kwargs["timeout"] <= min(15, 120 - now)
        starts.append(now)
        return _probe_outcome(healthy, states[min(len(starts) - 1, len(states) - 1)])

    original_run = subprocess.run

    def only_git(command: list[str], **kwargs: Any) -> subprocess.CompletedProcess[Any]:
        assert command[0] == "git", "finalization must never build or upload"
        return cast(subprocess.CompletedProcess[Any], original_run(command, **kwargs))

    monkeypatch.setattr(production_wait, "monotonic", lambda: now)
    monkeypatch.setattr(production_wait, "sleep", delay)
    monkeypatch.setattr(production_wait, "run_deadline_probe", probe)
    monkeypatch.setattr(subprocess, "run", only_git)
    for name, value in {
        "GITHUB_REPOSITORY": upload.producer.repository,
        "GITHUB_SHA": "b" * 40,  # Recovery's workflow/main SHA is not the upload SHA.
        "GITHUB_RUN_ID": str(upload.producer.run_id),
        "GITHUB_RUN_ATTEMPT": str(upload.producer.run_attempt),
    }.items():
        monkeypatch.setenv(name, value)
    command = next(
        shlex.split(line.strip())[5:]
        for line in _finalization_step()["run"].splitlines()
        if line.strip().startswith("uv run election-guide release automation finalize ")
    )
    result = CliRunner().invoke(app, command)
    report = json.loads((output / "production-wait.json").read_bytes())
    assert report["attempts"][: len(starts)] == [
        _probe_outcome(healthy, states[min(index, len(states) - 1)]).model_dump(mode="json")
        for index in range(len(starts))
    ]
    receipt = evidence.OperationReceipt.model_validate_json(
        (output / "operation-receipt.json").read_bytes()
    )
    assert upload_path.read_bytes() == original_upload
    assert receipt.upload == upload
    retained = evidence.read_evidence_reports(receipt, issue_number=550)
    assert json.loads(retained["production-wait.json"]) == report
    assert receipt.state == ("verified" if result.exit_code == 0 else "failed")
    assert all(b - a >= 5 for a, b in pairwise(starts))
    assert now <= 120
    return result.exit_code, report, starts


@pytest.mark.parametrize(
    "states",
    [
        ("healthy", "healthy"),
        ("old-commit", "healthy", "healthy"),
        ("healthy", "old-commit", "healthy", "bad-route", "healthy", "healthy"),
    ],
)
def test_propagation_confirms_expected_upload_after_two_consecutive_passes(
    evidence_setup: tuple[Any, ...],  # noqa: F811
    monkeypatch: pytest.MonkeyPatch,
    states: tuple[str, ...],
) -> None:
    status, report, starts = _run_recorded_finalizer(evidence_setup, monkeypatch, states)
    assert status == 0
    assert report["timed_out"] is False
    assert len(report["attempts"]) == len(states)
    assert report["successful_indices"] == [len(states) - 2, len(states) - 1]
    assert starts == list(range(0, 5 * len(states), 5))


@pytest.mark.parametrize(
    "failure", ["old-commit", "bad-route", "redirect", "invalid-manifest", "missing-evidence"]
)
def test_persistent_failure_retains_every_attempt_and_cannot_reuse_stale_success(
    evidence_setup: tuple[Any, ...],  # noqa: F811
    monkeypatch: pytest.MonkeyPatch,
    failure: str,
) -> None:
    status, report, starts = _run_recorded_finalizer(evidence_setup, monkeypatch, (failure,))
    assert status == 1
    assert report["timed_out"] is True
    assert report["successful_indices"] == []
    assert len(starts) == 24
    assert len(report["attempts"]) == 25  # Includes the explicit deadline observation.
    assert all(attempt == report["attempts"][0] for attempt in report["attempts"][:24])
    assert "deadline" in report["attempts"][-1]["manifest"]["observed"]["error"]
