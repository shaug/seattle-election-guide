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
