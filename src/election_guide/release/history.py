"""Render software history from explicit Git boundaries with pinned local tooling."""

from __future__ import annotations

import json
import os
import re
import subprocess
import tempfile
import tomllib
from datetime import datetime
from pathlib import Path
from typing import Any


def _run(repository: Path, command: list[str], *, env: dict[str, str] | None = None) -> str:
    result = subprocess.run(
        command, cwd=repository, capture_output=True, text=True, check=False, env=env
    )
    if result.returncode != 0:
        raise ValueError(f"history generation failed: {result.stderr.strip()}")
    return result.stdout


def _commit(repository: Path, sha: str) -> None:
    if re.fullmatch(r"[0-9a-f]{40}", sha) is None:
        raise ValueError("history endpoints must be full lowercase Git commit IDs")
    if _run(repository, ["git", "rev-parse", "--verify", f"{sha}^{{commit}}"]).strip() != sha:
        raise ValueError("history endpoint does not identify the expected commit")


def _cliff(repository: Path, *arguments: str) -> str:
    # Calling the installed binary directly cannot trigger an npx download.
    executable = repository / "node_modules/.bin/git-cliff"
    if not executable.is_file():
        raise ValueError("history generation requires locked Node dependencies (npm ci)")
    return _run(
        repository,
        [
            str(executable),
            "--offline",
            "--no-exec",
            "--config",
            str(repository / "cliff.toml"),
            *arguments,
        ],
        env={key: value for key, value in os.environ.items() if not key.startswith("GIT_CLIFF_")},
    )


def generate_software_history(
    repository: Path,
    *,
    previous_release_sha: str,
    source_sha: str,
    release_version: str,
    generated_at: datetime,
) -> str:
    """Render one declared release, independent of tags and the checkout's HEAD."""
    repository = repository.resolve()
    for sha in (previous_release_sha, source_sha):
        _commit(repository, sha)
    _run(repository, ["git", "merge-base", "--is-ancestor", previous_release_sha, source_sha])
    if generated_at.tzinfo is None or generated_at.utcoffset() is None:
        raise ValueError("software history generated_at must include a UTC offset")
    if re.fullmatch(r"[0-9]{4}-[a-z]+\.[0-9]+", release_version) is None:
        raise ValueError("software history requires an election-scoped release version")
    context: list[dict[str, Any]] = json.loads(
        _cliff(
            repository, "--ignore-tags", ".*", "--context", f"{previous_release_sha}..{source_sha}"
        )
    )
    if len(context) != 1:
        raise ValueError("software history must resolve exactly one release")
    context[0]["version"] = release_version
    context[0]["timestamp"] = int(generated_at.timestamp())
    with tempfile.TemporaryDirectory(prefix="release-history-") as temporary:
        path = Path(temporary) / "context.json"
        path.write_text(json.dumps(context), encoding="utf-8")
        return _cliff(repository, "--from-context", str(path), "--strip", "header")


def generate_changelog_index(repository: Path) -> str:
    """Render the retained tagged history only through its declared fixed endpoint."""
    repository = repository.resolve()
    config = tomllib.loads((repository / "cliff.toml").read_text(encoding="utf-8"))
    endpoint = config["release_history"]["legacy_history_end_sha"]
    _commit(repository, endpoint)
    return _cliff(repository, endpoint)
