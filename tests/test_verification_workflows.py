"""Execute the Calendar state handoff against disposable local Git repositories."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any, cast

import pytest
import yaml

from election_guide.collection.verification_tasks import require_committed_state

PROJECT_ROOT = Path(__file__).parents[1]
ARCHIVE_BRANCH = "codex/endorsement-verification-state"


def _git(root: Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=root, capture_output=True, text=True, check=True
    ).stdout.strip()


@pytest.mark.parametrize("state", ["pending", "merged-and-deleted", "initial"])
def test_calendar_restores_selected_committed_state(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, state: str
) -> None:
    origin = tmp_path / "origin.git"
    _git(tmp_path, "init", "--bare", str(origin))
    repo = tmp_path / "checkout"
    repo.mkdir()
    _git(repo, "init", "--initial-branch=main")
    _git(repo, "config", "user.name", "Workflow fixture")
    _git(repo, "config", "user.email", "workflow@example.invalid")
    _git(repo, "remote", "add", "origin", str(origin))
    (repo / "README").write_text("Fixture repository\n")
    _git(repo, "add", ".")
    _git(repo, "commit", "-m", "Initial checkout")
    expected = _git(repo, "rev-parse", "HEAD")
    if state != "initial":
        _git(repo, "switch", "-c", ARCHIVE_BRANCH)
        archive = repo / "data/verification/checks/saved.json"
        archive.parent.mkdir(parents=True)
        archive.write_text(json.dumps({"status": "previously-committed"}) + "\n")
        _git(repo, "add", ".")
        _git(repo, "commit", "-m", "Previous source event")
        expected = _git(repo, "rev-parse", "HEAD")
        _git(repo, "push", "origin", ARCHIVE_BRANCH)
        _git(repo, "switch", "main")
        if state == "merged-and-deleted":
            _git(repo, "merge", "--ff-only", ARCHIVE_BRANCH)
            _git(repo, "push", "origin", "main")
            _git(repo, "push", "origin", "--delete", ARCHIVE_BRANCH)
        # No new source event is written before the watcher runs.

    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    args_file = tmp_path / "reconcile-args.json"
    uv = bin_dir / "uv"
    uv.write_text(
        f"#!{sys.executable}\n"
        "import json, os, sys\n"
        "from pathlib import Path\n"
        "Path(os.environ['WATCH_ARGS']).write_text(json.dumps(sys.argv[1:]))\n"
    )
    uv.chmod(0o755)
    workflow = cast(
        dict[str, Any],
        yaml.safe_load((PROJECT_ROOT / ".github/workflows/calendar.yml").read_text()),
    )
    step = next(
        step
        for step in workflow["jobs"]["track"]["steps"]
        if step.get("name")
        == "Watch for endorsement checks whose source job never recorded an event"
    )
    subprocess.run(
        ["bash", "-e", "-o", "pipefail", "-c", step["run"]],
        cwd=repo,
        env={
            **os.environ,
            "PATH": f"{bin_dir}{os.pathsep}{os.environ['PATH']}",
            "RUNNER_TEMP": str(tmp_path / "runner"),
            "GITHUB_REPOSITORY": "fixture/guide",
            "WATCH_ARGS": str(args_file),
            "DRY_RUN": "",
        },
        capture_output=True,
        text=True,
        check=True,
    )
    args = cast(list[str], json.loads(args_file.read_text()))
    assert args[:4] == ["run", "election-guide", "verification", "reconcile"]
    assert "--watch" in args
    assert "--dry-run" not in args
    revision = args[args.index("--revision") + 1]
    assert revision == expected
    state_root = Path(args[args.index("--state-root") + 1])
    if state != "initial":
        assert json.loads((state_root / "checks/saved.json").read_text()) == {
            "status": "previously-committed"
        }
    monkeypatch.chdir(repo)
    require_committed_state(state_root, revision)


def test_scheduled_job_uses_repository_auth_without_an_evidence_secret() -> None:
    workflow = yaml.safe_load(
        (PROJECT_ROOT / ".github/workflows/endorsement-verification.yml").read_text()
    )
    assert "ENDORSEMENT_EVIDENCE_KEY" not in workflow.get("env", {})
    job = workflow["jobs"]["verify"]
    assert "ENDORSEMENT_EVIDENCE_KEY" not in job.get("env", {})
    assert all("ENDORSEMENT_EVIDENCE_KEY" not in step.get("env", {}) for step in job["steps"])
    app = next(step for step in job["steps"] if step.get("id") == "app-token")
    assert app["with"]["permission-contents"] == "write"
    assert app["with"]["permission-pull-requests"] == "write"
    assert workflow["concurrency"] == {"group": "election-maintenance", "cancel-in-progress": False}


@pytest.mark.parametrize("existing_pr", [False, True])
def test_scheduled_pr_delivers_factual_evidence_contract(tmp_path: Path, existing_pr: bool) -> None:
    """Exercise the real PR step so the operator receives the current contract."""
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    body_file = tmp_path / "delivered.md"
    gh = bin_dir / "gh"
    gh.write_text(
        f"#!{sys.executable}\n"
        "import os, sys\n"
        "from pathlib import Path\n"
        "if sys.argv[1:3] == ['pr', 'list']:\n"
        "    print('42' if os.environ['EXISTING_PR'] == 'true' else '')\n"
        "elif sys.argv[1:3] == ['pr', 'create']:\n"
        "    Path(os.environ['DELIVERED_BODY']).write_text(\n"
        "        Path(sys.argv[sys.argv.index('--body-file') + 1]).read_text())\n"
        "else:\n"
        "    raise AssertionError(sys.argv)\n"
    )
    gh.chmod(0o755)
    workflow = yaml.safe_load(
        (PROJECT_ROOT / ".github/workflows/endorsement-verification.yml").read_text()
    )
    step = next(
        step
        for step in workflow["jobs"]["verify"]["steps"]
        if step.get("name") == "Open or retain the evidence review PR"
    )
    subprocess.run(
        ["bash", "-e", "-o", "pipefail", "-c", step["run"]],
        cwd=PROJECT_ROOT,
        env={
            **os.environ,
            "PATH": f"{bin_dir}{os.pathsep}{os.environ['PATH']}",
            "ARCHIVE_BRANCH": ARCHIVE_BRANCH,
            "EXISTING_PR": str(existing_pr).lower(),
            "DELIVERED_BODY": str(body_file),
        },
        capture_output=True,
        text=True,
        check=True,
    )
    if existing_pr:
        assert not body_file.exists()
        return
    body = body_file.read_text()
    assert "public factual observations" in body
    assert "actual check" in body and "actual reviewer" in body
    assert "does not claim" in body and "re-read" in body
    assert "no full-page" in body
    assert "encrypted restricted" not in body
    assert "Refs #497" in body and "Closes #497" not in body


def test_active_runbook_requires_factual_review_and_real_scheduled_adoption() -> None:
    runbook = (PROJECT_ROOT / "docs/runbooks/endorsement-source-daily-verification.md").read_text()
    active = runbook.split("## Legacy encrypted custody", 1)[0]
    assert "Status: proposed" in active
    assert "public factual baseline" in active
    assert "no evidence key" in active
    assert "verification restore" not in active
    assert "temporary test key" not in active
    assert "later independent normal scheduled reuse" in active
    assert "SEIU 775" in active and "46" in active
    assert "September 18" in active and "October 16" in active
    assert "full-page reconstruction" in active
    assert "verification seal" in runbook.split("## Legacy encrypted custody", 1)[1]


@pytest.mark.parametrize(
    "document",
    [
        "SOURCE_POLICY.md",
        "ARCHITECTURE.md",
        "REVIEW_GUIDE.md",
        "docs/COLLECTION.md",
        "docs/EVIDENCE_CAPTURE.md",
    ],
)
def test_evidence_authorities_distinguish_observed_facts_from_original_bytes(document: str) -> None:
    text = " ".join((PROJECT_ROOT / document).read_text().lower().split())
    assert "observed" in text
    assert "actual reviewer" in text
    assert any(
        limit in text
        for limit in (
            "full-page reconstruction is not required",
            "full-page reconstruction is not promised",
        )
    )
