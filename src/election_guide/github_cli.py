"""Shared plumbing for invoking the GitHub CLI (`gh`).

Every caller that lists, creates, updates, or closes GitHub issues through
`gh` shares this same subprocess boundary, listing bound, and trailing-line
marker convention, so a fix here reaches every consumer at once instead of
drifting between independently duplicated copies (calendar milestone
tracking and the production-check alert issue both maintain their own
generated issue's identity this way).
"""

from __future__ import annotations

import subprocess

# Every issue in the repository has to be readable in one listing, so the
# bound is its lifetime issue count — not any narrower window a specific
# caller cares about. This repository opened its first 174 issues in 17
# days, so a four-figure bound is months of headroom rather than years;
# `gh issue list` paginates to this without extra code. A caller reads fail
# loudly rather than truncate, because a silently dropped marker is a
# duplicate issue or a missed alert — and because tripping it stops the run
# from acting on incomplete data.
ISSUE_QUERY_LIMIT = 10000


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
        raise ValueError(f"{failure}: {detail}")
    return completed.stdout


def trailing_line(body: str) -> str:
    """The last non-empty, stripped line of an issue body.

    The marker convention both calendar tracking and the production-check
    alert identify their own generated issues by: an issue always ends with
    its identity, so a marker discussed mid-body (for example, a human
    quoting one while asking about the system) cannot be mistaken for the
    real thing.
    """
    lines = [line.strip() for line in body.splitlines()]
    return next((line for line in reversed(lines) if line), "")
