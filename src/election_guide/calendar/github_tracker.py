"""Fulfil a calendar tracking plan against GitHub Issues.

This is the impure half of milestone tracking. It reads which markers already
exist and creates the missing issues; deciding what should exist belongs to
`election_guide.calendar.tracking`.
"""

from __future__ import annotations

import json
import subprocess
from typing import Any, cast

from election_guide.calendar.tracking import MARKER_PREFIX, TRACKING_LABEL, IssueRequest

# Every issue this tool has ever opened has to be readable in one listing, so
# the bound is the repository's lifetime count of labeled issues, not the lead
# window. The read fails loudly rather than truncating, because a silently
# dropped marker is a duplicate issue.
ISSUE_QUERY_LIMIT = 1000


def _run(command: list[str], failure: str) -> str:
    try:
        completed = subprocess.run(command, capture_output=True, text=True, check=False)
    except OSError as error:
        raise ValueError(
            "the GitHub CLI is required to track calendar milestones: install `gh` "
            "(https://cli.github.com) and authenticate it"
        ) from error
    if completed.returncode != 0:
        detail = completed.stderr.strip() or completed.stdout.strip()
        raise ValueError(f"{failure}: {detail}")
    return completed.stdout


def issue_bodies(payload: str) -> list[str]:
    """Extract issue bodies from `gh issue list --json body` output."""
    issues: Any = json.loads(payload)
    if not isinstance(issues, list):
        raise ValueError("GitHub CLI returned an issue list that is not an array")
    bodies: list[str] = []
    for entry in cast(list[Any], issues):
        if not isinstance(entry, dict):
            raise ValueError("GitHub CLI returned an issue that is not an object")
        body = cast(dict[str, Any], entry).get("body")
        bodies.append(body if isinstance(body, str) else "")
    return bodies


def markers_in_issues(bodies: list[str]) -> set[str]:
    """Collect every calendar marker present in the given issue bodies.

    Public because this parse is the idempotence contract: a marker that is
    written but not read back opens a duplicate on the next run.
    """
    return {
        stripped
        for body in bodies
        for line in body.splitlines()
        if (stripped := line.strip()).startswith(MARKER_PREFIX)
    }


class GitHubIssueTracker:
    """Track milestones as GitHub issues through the authenticated CLI."""

    def __init__(self, repository: str) -> None:
        self.repository = repository

    def existing_markers(self) -> set[str]:
        """Read markers from every issue this tool has opened, open or closed.

        Closed issues count. A milestone whose issue was opened and completed
        must not be reopened as a duplicate on the next run.

        The listing filters by the label the tool applies, not by a text search
        for the marker. GitHub's issue search is a relevance-ranked full-text
        query over an eventually consistent index: it would match unrelated
        issues that merely contain the marker's words, and it can omit an issue
        created moments earlier — precisely when a second run would duplicate
        it.
        """
        payload = _run(
            [
                "gh",
                "issue",
                "list",
                "--repo",
                self.repository,
                "--state",
                "all",
                "--label",
                TRACKING_LABEL,
                "--limit",
                str(ISSUE_QUERY_LIMIT),
                "--json",
                "body",
            ],
            "could not list existing calendar issues",
        )
        bodies = issue_bodies(payload)
        if len(bodies) >= ISSUE_QUERY_LIMIT:
            raise ValueError(
                f"reached the {ISSUE_QUERY_LIMIT}-issue listing limit, so a marker may have been "
                "dropped; raise ISSUE_QUERY_LIMIT before running again"
            )
        return markers_in_issues(bodies)

    def ensure_milestone(self, title: str) -> None:
        """Create the per-election GitHub milestone unless it already exists."""
        payload = _run(
            [
                "gh",
                "api",
                "--paginate",
                f"repos/{self.repository}/milestones?state=all&per_page=100",
                "--jq",
                ".[].title",
            ],
            "could not list repository milestones",
        )
        if title in {line.strip() for line in payload.splitlines() if line.strip()}:
            return
        _run(
            [
                "gh",
                "api",
                "--method",
                "POST",
                f"repos/{self.repository}/milestones",
                "-f",
                f"title={title}",
            ],
            f"could not create milestone {title!r}",
        )

    def create(self, request: IssueRequest) -> str:
        """Open one issue, attached to its election's milestone."""
        self.ensure_milestone(request.milestone)
        command = [
            "gh",
            "issue",
            "create",
            "--repo",
            self.repository,
            "--title",
            request.title,
            "--body",
            request.body,
            "--milestone",
            request.milestone,
        ]
        for label in request.labels:
            command += ["--label", label]
        return _run(command, f"could not create issue {request.title!r}").strip()
