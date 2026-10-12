"""Task reconciliation is stable across retries and recovered source runs."""

import json
import subprocess
from pathlib import Path
from typing import Any, cast

import pytest
from typer.testing import CliRunner

from election_guide.cli import app
from tests.test_verification_runtime import run_fixture, setup_verification_fixture

runner = CliRunner()


def test_same_day_batch_retry_missing_events_and_escalation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    policy, state, fixtures = setup_verification_fixture(tmp_path, monkeypatch)
    archive = tmp_path / "archive"
    (archive / "data").mkdir(parents=True)
    state = archive / "data/verification"
    original_run = subprocess.run
    for args in (
        ["git", "init", "-q"],
        ["git", "config", "user.name", "Fixture"],
        ["git", "config", "user.email", "fixture@example.test"],
    ):
        original_run(args, cwd=archive, check=True, capture_output=True)
    monkeypatch.chdir(archive)
    issues: list[dict[str, Any]] = []
    comments: dict[str, list[dict[str, str]]] = {}
    labels: list[str] = []

    def fake_run(command: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        if command[0] != "gh":
            return cast(subprocess.CompletedProcess[str], original_run(command, **kwargs))
        output = ""
        if command[1:3] == ["issue", "list"]:
            output = json.dumps(issues)
        elif command[1] == "api":
            output = "wa-2026-general\n"
        elif command[1:3] == ["issue", "view"]:
            output = json.dumps({"comments": comments[command[3]]})
        elif command[1:3] == ["issue", "create"]:
            number = len(issues) + 1
            body = Path(command[command.index("--body-file") + 1]).read_text()
            issues.append({"number": number, "body": body, "state": "OPEN"})
            comments[str(number)] = []
            output = f"https://github.com/example/guide/issues/{number}"
        elif command[1:3] == ["issue", "comment"]:
            body = Path(command[command.index("--body-file") + 1]).read_text()
            comments[command[3]].append({"body": body})
        elif command[1:3] == ["issue", "edit"]:
            labels.append(command[command.index("--add-label") + 1])
        else:
            raise AssertionError(command)
        return subprocess.CompletedProcess(command, 0, output, "")

    monkeypatch.setattr(subprocess, "run", fake_run)

    def reconcile(day: str) -> str:
        original_run(["git", "add", "-A", "--", "."], cwd=archive, check=True)
        original_run(
            ["git", "commit", "-qm", "Fixture observations", "--allow-empty"],
            cwd=archive,
            check=True,
        )
        revision = original_run(
            ["git", "rev-parse", "HEAD"], cwd=archive, capture_output=True, text=True, check=True
        ).stdout.strip()
        result = runner.invoke(
            app,
            [
                "verification",
                "reconcile",
                str(policy),
                "--state-root",
                str(state),
                "--repository",
                "example/guide",
                "--revision",
                revision,
                "--as-of",
                day,
                "--watch",
            ],
        )
        assert result.exit_code == 0, result.output
        return result.output

    reconcile("2026-10-05")
    reconcile("2026-10-06")
    reconcile("2026-10-07")
    assert len(issues) == 3 and "priority: high" in labels
    assert any("three observed days" in comment["body"] for comment in comments["3"])
    run_fixture(policy, state, fixtures, "2026-10-08")
    reconcile("2026-10-08")
    assert len(issues) == 4 and len(comments["4"]) == 43
    assert any("Human baseline spot-check" in comment["body"] for comment in comments["4"])
    assert json.loads(reconcile("2026-10-08")) == []
    assert len(issues) == 4 and len(comments["4"]) == 43
    reconcile("2026-10-12")
    assert len(issues) == 7
    counts = {number: len(entries) for number, entries in comments.items()}
    run_fixture(policy, state, fixtures, "2026-10-12")
    reconcile("2026-10-12")
    assert all(len(comments[number]) == count for number, count in counts.items())
    assert len(issues) == 8


def test_uncommitted_archive_cannot_publish_misleading_evidence_links(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    policy, state, fixtures = setup_verification_fixture(tmp_path, monkeypatch)
    run_fixture(policy, state, fixtures, "2026-10-05")
    revision = subprocess.run(
        ["git", "rev-parse", "HEAD"], text=True, capture_output=True, check=True
    ).stdout.strip()
    result = runner.invoke(
        app,
        [
            "verification",
            "reconcile",
            str(policy),
            "--state-root",
            str(state),
            "--repository",
            "example/guide",
            "--revision",
            revision,
            "--as-of",
            "2026-10-05",
        ],
    )
    assert result.exit_code != 0
    assert "exactly match its committed" in result.output
