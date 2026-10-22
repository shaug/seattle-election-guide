"""Shared plumbing for invoking the GitHub CLI (`gh`).

Every caller that lists, creates, updates, or closes GitHub issues through
`gh` shares this same subprocess boundary, listing bound, and trailing-line
marker convention, so a fix here reaches every consumer at once instead of
drifting between independently duplicated copies (calendar milestone
tracking and source-link alerts both maintain their own
generated issue's identity this way).
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any, cast

# Every issue in the repository has to be readable in one listing, so the
# bound is its lifetime issue count — not any narrower window a specific
# caller cares about. This repository opened its first 174 issues in 17
# days, so a four-figure bound is months of headroom rather than years;
# `gh issue list` paginates to this without extra code. A caller reads fail
# loudly rather than truncate, because a silently dropped marker is a
# duplicate issue or a missed alert — and because tripping it stops the run
# from acting on incomplete data.
ISSUE_QUERY_LIMIT = 10000


class GitHubCliError(ValueError):
    """A nonzero gh process, with the exit details needed by admission."""

    def __init__(self, message: str, *, returncode: int, stderr: str) -> None:
        super().__init__(message)
        self.returncode = returncode
        self.stderr = stderr


def run_gh(command: list[str], failure: str) -> str:
    """Run one `gh` invocation, raising `ValueError` uniformly on failure."""
    try:
        completed = subprocess.run(command, capture_output=True, text=True, check=False)
    except OSError as error:
        raise ValueError(
            "the GitHub CLI is required for this operation: install `gh` "
            "(https://cli.github.com) and authenticate it"
        ) from error
    if completed.returncode != 0:
        detail = completed.stderr.strip() or completed.stdout.strip()
        raise GitHubCliError(
            f"{failure}: {detail}", returncode=completed.returncode, stderr=completed.stderr.strip()
        )
    return completed.stdout


def download_gh(command: list[str], destination: Path, failure: str) -> None:
    """Stream a binary GitHub response to disk; never decode archive bytes."""
    destination.parent.mkdir(parents=True, exist_ok=True)
    try:
        with destination.open("xb") as sink:
            completed = subprocess.run(command, stdout=sink, stderr=subprocess.PIPE, check=False)
    except FileExistsError as error:
        raise ValueError(f"download destination already exists: {destination}") from error
    except OSError as error:
        destination.unlink(missing_ok=True)
        raise ValueError("the GitHub CLI is required for this download") from error
    if completed.returncode != 0:
        destination.unlink(missing_ok=True)
        detail = completed.stderr.decode("utf-8", errors="replace").strip()
        raise ValueError(f"{failure}: {detail}")


def parse_issue_list(payload: str) -> list[dict[str, Any]]:
    """Validate a `gh issue list --json ...` payload: a JSON array of objects.

    Every caller that lists issues (calendar milestone tracking and
    source-link alerts) shares this same shape
    requirement before it diverges into its own field extraction, so the
    check lives here once. Field extraction --
    including which fields are required -- stays with each caller.
    """
    issues: Any = json.loads(payload)
    if not isinstance(issues, list):
        raise ValueError("GitHub CLI returned an issue list that is not an array")
    records: list[dict[str, Any]] = []
    for entry in cast(list[Any], issues):
        if not isinstance(entry, dict):
            raise ValueError("GitHub CLI returned an issue that is not an object")
        records.append(cast(dict[str, Any], entry))
    return records


def parse_paginated_objects(
    payload: str, *, context: str, key: str | None = None
) -> list[dict[str, Any]]:
    """Validate every `gh api --paginate --slurp` page before returning its records."""
    pages: Any = json.loads(payload)
    if not isinstance(pages, list) or not pages:
        raise ValueError(f"incomplete {context} pages")
    records: list[dict[str, Any]] = []
    for page in cast(list[Any], pages):
        if key is not None:
            if not isinstance(page, dict):
                raise ValueError(f"invalid {context} keyed page")
            page = cast(dict[str, Any], page).get(key)
        if not isinstance(page, list):
            raise ValueError(f"invalid {context} page")
        for entry in cast(list[Any], page):
            if not isinstance(entry, dict):
                raise ValueError(f"invalid {context} record")
            records.append(cast(dict[str, Any], entry))
    return records


def trailing_line(body: str) -> str:
    """The last non-empty, stripped line of an issue body.

    The marker convention calendar tracking and source-link alerts use
    to identify their generated issues: an issue always ends with
    its identity, so a marker discussed mid-body (for example, a human
    quoting one while asking about the system) cannot be mistaken for the
    real thing.
    """
    lines = [line.strip() for line in body.splitlines()]
    return next((line for line in reversed(lines) if line), "")
