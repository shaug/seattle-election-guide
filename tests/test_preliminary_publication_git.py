"""Real Git verifies that scheduled staging cannot smuggle unrelated changes."""

import json
import os
import subprocess
from importlib import import_module
from importlib.util import find_spec
from pathlib import Path

import pytest
import yaml


def git(root: Path, *args: str) -> str:
    return subprocess.check_output(["git", *args], cwd=root, text=True).strip()


def repository(root: Path) -> None:
    git(root, "init")
    git(root, "config", "user.name", "Test")
    git(root, "config", "user.email", "test@example.invalid")
    for name in [
        "data/results/wa-2026-general.yaml",
        "data/corrections/wa-2026-general.yaml",
        "data/evidence/official/original.json",
    ]:
        p = root / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text("original")
    git(root, "add", ".")
    git(root, "commit", "-m", "test baseline")


def stage(root: Path):
    assert find_spec("election_guide.results.publication") is not None, (
        "hourly publication staging is missing"
    )
    return import_module("election_guide.results.publication").stage_preliminary_publication(root)


def test_staging_includes_only_scoped_new_evidence_and_general_results(tmp_path: Path) -> None:
    repository(tmp_path)
    (tmp_path / "data/results/wa-2026-general.yaml").write_text("new counts")
    (tmp_path / "data/evidence/official/new.json").write_text("new original")
    assert set(stage(tmp_path)) == {
        "data/results/wa-2026-general.yaml",
        "data/evidence/official/new.json",
    }
    assert set(git(tmp_path, "diff", "--cached", "--name-only").splitlines()) == set(
        stage(tmp_path)
    )
    assert git(tmp_path, "show", "HEAD:data/evidence/official/original.json") == "original"


def test_unrelated_code_blocks_staging_without_index_mutation(tmp_path: Path) -> None:
    repository(tmp_path)
    (tmp_path / "unexpected.py").write_text("print('not a result')")
    with pytest.raises(ValueError, match="publication scope"):
        stage(tmp_path)
    assert git(tmp_path, "diff", "--cached", "--name-only") == ""


def test_immutable_evidence_cannot_be_replaced_by_an_hourly_candidate(tmp_path: Path) -> None:
    repository(tmp_path)
    (tmp_path / "data/evidence/official/original.json").write_text("rewritten")
    with pytest.raises(ValueError, match="immutable"):
        stage(tmp_path)
    assert git(tmp_path, "diff", "--cached", "--name-only") == ""


def test_existing_updates_cannot_be_rewritten_by_an_hourly_candidate(tmp_path: Path) -> None:
    repository(tmp_path)
    (tmp_path / "data/corrections/wa-2026-general.yaml").write_text("rewritten history")
    with pytest.raises(ValueError, match=r"Updates.*append-only"):
        stage(tmp_path)
    assert git(tmp_path, "diff", "--cached", "--name-only") == ""


def test_hourly_updates_append_preserves_every_previous_byte(tmp_path: Path) -> None:
    repository(tmp_path)
    p = tmp_path / "data/corrections/wa-2026-general.yaml"
    p.write_text(p.read_text() + "\nnew truthful results entry\n")
    assert stage(tmp_path) == ("data/corrections/wa-2026-general.yaml",)
    assert git(tmp_path, "show", "HEAD:data/corrections/wa-2026-general.yaml") == "original"
    assert git(tmp_path, "diff", "--cached", "--name-only") == str(p.relative_to(tmp_path))


@pytest.mark.parametrize(
    "history",
    [
        "orphan",
        "squashed",
        "closed",
        "open",
        "older",
        "fork",
        "wrong_base",
        "invalid",
        "advanced",
        "unreadable",
    ],
)
def test_candidate_step_respects_exact_pr_history(tmp_path: Path, history: str) -> None:
    remote = tmp_path / "remote.git"
    git(tmp_path, "init", "--bare", str(remote))
    repo = tmp_path / "checkout"
    repo.mkdir()
    repository(repo)
    git(repo, "branch", "-M", "main")
    git(repo, "remote", "add", "origin", str(remote))
    git(repo, "push", "origin", "main")
    branch = "codex/preliminary-results-refresh"
    git(repo, "checkout", "-b", branch)
    (repo / "data/results/wa-2026-general.yaml").write_text("prepared counts")
    git(repo, "commit", "-am", "prepared result candidate")
    candidate_head = git(repo, "rev-parse", "HEAD")
    git(repo, "push", "origin", branch)
    git(repo, "checkout", "main")
    if history == "squashed":
        git(repo, "merge", "--squash", branch)
        git(repo, "commit", "-m", "accepted normal squash")
    (repo / "later.txt").write_text("later independent main change")
    git(repo, "add", ".")
    git(repo, "commit", "-m", "later unrelated work")
    git(repo, "push", "origin", "main")
    if history == "closed":
        # A stale candidate would conflict if recovery tried to merge it.
        (repo / "data/results/wa-2026-general.yaml").write_text("main's later counts")
        git(repo, "commit", "-am", "later counts")
        git(repo, "push", "origin", "main")
    tools = tmp_path / "tools"
    tools.mkdir()
    gh = tools / "gh"
    slug = "shaug/seattle-election-guide"
    row = {
        "head": {
            "ref": branch,
            "repo": {"full_name": "other/project" if history == "fork" else slug},
            "sha": "a" * 40 if history == "older" else candidate_head,
        },
        "base": {
            "ref": "other" if history == "wrong_base" else "main",
            "repo": {"full_name": slug},
        },
        "state": "open" if history == "open" else "closed",
        "merged_at": "2026-11-01T00:00:00Z" if history == "squashed" else None,
    }
    if history == "invalid":
        del row["state"]
    # Two API pages. A head on the second page must still be respected.
    pages = "[]\n" + json.dumps([] if history == "orphan" else [row])
    gh.write_text(
        "#!/bin/sh\n"
        'case "$*" in *"--paginate"*) ;; *) exit 11;; esac\n'
        + ("exit 12\n" if history == "unreadable" else "cat <<'JSON'\n" + pages + "\nJSON\n")
    )
    gh.chmod(0o755)
    output = tmp_path / "step-output.txt"
    workflow = yaml.safe_load(
        (Path(__file__).parents[1] / ".github/workflows/preliminary-results.yml").read_text()
    )
    step = next(s for s in workflow["jobs"]["prepare"]["steps"] if s.get("id") == "candidate")
    # The workflow helper is in the trusted main checkout at job start.
    root = Path(__file__).parents[1]
    helper = Path(".github/scripts/preliminary-pr-state.sh")
    (repo / helper).parent.mkdir(parents=True, exist_ok=True)
    (repo / helper).write_bytes((root / helper).read_bytes())
    main_head = git(repo, "rev-parse", "origin/main")
    result = subprocess.run(
        ["bash", "-euo", "pipefail", "-c", step["run"]],
        cwd=repo,
        env={
            **os.environ,
            "PATH": str(tools) + os.pathsep + os.environ["PATH"],
            "GITHUB_REPOSITORY": "shaug/seattle-election-guide",
            "PRELIMINARY_RESULTS_BRANCH": branch,
            "GITHUB_OUTPUT": str(output),
            "ADMITTED_MAIN": "b" * 40 if history == "advanced" else main_head,
        },
        capture_output=True,
        text=True,
    )
    if history in {"unreadable", "invalid", "advanced"}:
        assert result.returncode != 0
        assert git(repo, "rev-parse", "HEAD") == main_head
        return
    assert result.returncode == 0, result.stderr
    if history in {"open", "closed"}:
        assert "pending=true" in output.read_text()
        assert git(repo, "rev-parse", "HEAD") == main_head
        assert git(repo, "rev-parse", "origin/" + branch) == candidate_head
        return
    assert "pending=false" in output.read_text()
    assert f"recover={str(history != 'squashed').lower()}" in output.read_text()
    assert (
        subprocess.run(
            ["git", "merge-base", "--is-ancestor", candidate_head, "HEAD"], cwd=repo
        ).returncode
        == 0
    )  # The next ordinary branch push remains a fast-forward.
    assert (repo / "later.txt").read_text() == "later independent main change"
    assert (repo / "data/results/wa-2026-general.yaml").read_text() == "prepared counts"
    if history == "squashed":
        assert git(repo, "rev-parse", "HEAD^{tree}") == git(repo, "rev-parse", "origin/main^{tree}")


@pytest.mark.parametrize(
    "value,expected", [("inactive", "false"), ("active", "true"), ("typo", None), (None, None)]
)
def test_main_lifecycle_entry_point(
    tmp_path: Path, value: str | None, expected: str | None
) -> None:
    root = Path(__file__).parents[1]
    workflow = yaml.safe_load((root / ".github/workflows/preliminary-results.yml").read_text())
    step = next(s for s in workflow["jobs"]["lifecycle"]["steps"] if s.get("id") == "state")
    policy = Path("config/results/wa-2026-general-preliminary.lifecycle")
    assert (root / policy).read_bytes() in {b"inactive\n", b"active\n"}
    repository(tmp_path)
    if value is not None:
        (tmp_path / policy).parent.mkdir(parents=True)
        (tmp_path / policy).write_text(value + "\n")
    output = tmp_path / "step-output"
    process = subprocess.run(
        ["bash", "-euo", "pipefail", "-c", step["run"]],
        cwd=tmp_path,
        env={**os.environ, "GITHUB_OUTPUT": str(output)},
        capture_output=True,
        text=True,
    )
    if expected is None:
        assert process.returncode != 0
        assert not output.exists()
    else:
        assert process.returncode == 0, process.stderr
        lines = output.read_text().splitlines()
        assert f"active={expected}" in lines
        if value == "active":
            assert f"revision={git(tmp_path, 'rev-parse', 'HEAD')}" in lines
