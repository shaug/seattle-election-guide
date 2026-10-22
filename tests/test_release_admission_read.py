"""Issue #597: capture-source requires a complete, exact merged PR read."""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

import pytest
from typer.testing import CliRunner

from election_guide.cli import app
from election_guide.github_cli import run_gh


def git(repository: Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=repository, text=True, capture_output=True, check=True
    ).stdout.strip()


@pytest.fixture
def admission_repo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[Path, str, Path]:
    repository = tmp_path / "repo"
    repository.mkdir()
    git(repository, "init", "-b", "main")
    (repository / "README.md").write_text("fixture\n")
    git(repository, "add", ".")
    git(
        repository,
        "-c",
        "user.name=Test",
        "-c",
        "user.email=test@example.org",
        "commit",
        "-m",
        "base",
    )
    (repository / "README.md").write_text("fixture source\n")
    git(repository, "add", ".")
    git(
        repository,
        "-c",
        "user.name=Test",
        "-c",
        "user.email=test@example.org",
        "commit",
        "-m",
        "source",
    )
    source = git(repository, "rev-parse", "HEAD")
    git(repository, "remote", "add", "origin", "https://github.com/owner/repository.git")
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    executable = bin_dir / "gh"
    executable.write_text(
        """#!/usr/bin/env python3
import json
import os
import pathlib
import sys

if sys.argv[1:3] == ['issue', 'comment']:
    count_file = pathlib.Path(os.environ['ADMISSION_COUNT'])
    count = int(count_file.read_text()) + 1 if count_file.exists() else 1
    count_file.write_text(str(count))
    sys.stderr.write('mutation failed\\n')
    sys.exit(1)
endpoint = sys.argv[2]
if '/compare/' in endpoint:
    sha = endpoint.split('/compare/')[1].split('...')[0]
    actual = 'a' * 40 if os.environ.get('ADMISSION_CASE') == 'lineage' else sha
    print(json.dumps({'status': 'ahead', 'merge_base_commit': {'sha': actual}}))
    sys.exit(0)
if not endpoint.endswith('/pulls?per_page=100'):
    sys.exit(4)
if sys.argv[3:] != ['--paginate', '--slurp']:
    sys.exit(5)
count_file = pathlib.Path(os.environ['ADMISSION_COUNT'])
count = int(count_file.read_text()) + 1 if count_file.exists() else 1
count_file.write_text(str(count))
case = os.environ['ADMISSION_CASE']
if case in ('recover', 'exhausted') and (case == 'exhausted' or count == 1):
    sys.stdout.write('[[{"number":999}],')
    sys.stderr.write('unexpected end of JSON input\\n')
    sys.exit(1)
if case == 'other-error':
    sys.stdout.write('[[{"number":999}],')
    sys.stderr.write('HTTP 403\\n')
    sys.exit(1)
if case == 'malformed':
    sys.stdout.write('[[{"number":999}],')
    sys.exit(0)
if case == 'incomplete':
    print('[]')
    sys.exit(0)
sha = endpoint.split('/commits/')[1].split('/pulls')[0]
valid = {'number': 597, 'merged_at': '2026-10-22T12:00:00Z',
         'merge_commit_sha': sha,
         'base': {'ref': 'main', 'repo': {'full_name': 'owner/repository'}}}
pages = [[{'number': 998, 'merged_at': None,
           'base': {'ref': 'main', 'repo': {'full_name': 'owner/repository'}}}], [valid]]
if case == 'ambiguous':
    pages[1].append({**valid, 'number': 598})
print(json.dumps(pages))
"""
    )
    executable.chmod(0o755)
    count_file = tmp_path / "gh-count"
    monkeypatch.setenv("PATH", str(bin_dir) + os.pathsep + os.environ["PATH"])
    monkeypatch.setenv("ADMISSION_COUNT", str(count_file))
    monkeypatch.setenv("GITHUB_EVENT_NAME", "push")
    monkeypatch.setenv("GITHUB_REF", "refs/heads/main")
    monkeypatch.setenv("GITHUB_REPOSITORY", "owner/repository")
    monkeypatch.setenv("GITHUB_SHA", source)
    monkeypatch.setenv("GITHUB_RUN_ID", "100")
    monkeypatch.setenv("GITHUB_RUN_ATTEMPT", "1")
    monkeypatch.chdir(repository)
    return repository, source, count_file


def capture(repository: Path, source: str) -> tuple[int, str, Path]:
    output = repository / "out"
    result = CliRunner().invoke(
        app,
        [
            "release",
            "automation",
            "capture-source",
            "--source-sha",
            source,
            "--output-dir",
            str(output),
        ],
    )
    return result.exit_code, result.output, output


def test_transient_partial_subprocess_read_restarts_all_pages(
    admission_repo: tuple[Path, str, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    repository, source, count_file = admission_repo
    monkeypatch.setenv("ADMISSION_CASE", "recover")
    code, message, output = capture(repository, source)
    assert code == 0, message
    assert "pulls?per_page=100 attempt 1/3 exit 1" in message
    assert '"number"' not in message
    assert count_file.read_text() == "2"
    assert json.loads((output / "source.json").read_text())["source_sha"] == source
    assert json.loads((output / "producer.json").read_text())["source_sha"] == source


@pytest.mark.parametrize(
    "case", ["exhausted", "other-error", "malformed", "incomplete", "ambiguous", "lineage"]
)
def test_incomplete_or_invalid_association_never_writes_capture(
    admission_repo: tuple[Path, str, Path], monkeypatch: pytest.MonkeyPatch, case: str
) -> None:
    repository, source, count_file = admission_repo
    monkeypatch.setenv("ADMISSION_CASE", case)
    code, message, output = capture(repository, source)
    assert code == 1
    assert not (output / "source.json").exists()
    assert not (output / "producer.json").exists()
    assert '"number"' not in message
    if case == "exhausted":
        assert count_file.read_text() == "3"
        assert "pulls?per_page=100" in message
        assert "attempt 3/3" in message
        assert "exit 1" in message
        assert "number" not in message
    elif case == "lineage":
        assert not count_file.exists()
    else:
        assert count_file.read_text() == "1"


def test_shared_mutation_failure_is_not_retried(
    admission_repo: tuple[Path, str, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    _, _, count_file = admission_repo
    monkeypatch.setenv("ADMISSION_CASE", "exhausted")
    with pytest.raises(ValueError):
        run_gh(["gh", "issue", "comment", "597", "--body", "test"], "write failed")
    assert count_file.read_text() == "1"
