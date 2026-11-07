"""Real Git verifies that scheduled staging cannot smuggle unrelated changes."""

import subprocess
from importlib import import_module
from importlib.util import find_spec
from pathlib import Path

import pytest


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
