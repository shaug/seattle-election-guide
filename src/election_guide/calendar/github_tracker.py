"""Fulfil a calendar tracking plan against GitHub Issues.

This is the impure half of milestone tracking. It reads which markers already
exist and creates the missing issues; deciding what should exist belongs to
`election_guide.calendar.tracking`.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, cast

from election_guide.calendar.tracking import MARKER_PREFIX, IssueRequest
from election_guide.github_cli import ISSUE_QUERY_LIMIT, run_gh, trailing_line


@dataclass(frozen=True)
class TrackedIssues:
    """What the repository already says about calendar milestones.

    `markers` is the identity the tracker acts on. `titles` is only used to
    notice that a title and the markers disagree; it never establishes that a
    milestone is tracked.
    """

    markers: frozenset[str]
    titles: tuple[str, ...]


def issue_records(payload: str) -> list[tuple[str, str]]:
    """Extract (title, body) from `gh issue list --json title,body` output."""
    issues: Any = json.loads(payload)
    if not isinstance(issues, list):
        raise ValueError("GitHub CLI returned an issue list that is not an array")
    records: list[tuple[str, str]] = []
    for entry in cast(list[Any], issues):
        if not isinstance(entry, dict):
            raise ValueError("GitHub CLI returned an issue that is not an object")
        issue = cast(dict[str, Any], entry)
        title, body = issue.get("title"), issue.get("body")
        records.append(
            (title if isinstance(title, str) else "", body if isinstance(body, str) else "")
        )
    return records


def markers_in_issues(bodies: list[str]) -> set[str]:
    """Collect the calendar marker each issue body ends with, if any.

    Public because this parse is the idempotence contract: a marker that is
    written but not read back opens a duplicate on the next run.

    Only the final non-empty line counts. Generated issues always end with
    their marker, so nothing is missed — and an issue that merely quotes one
    while discussing this system cannot suppress a real milestone.
    """
    markers: set[str] = set()
    for body in bodies:
        tail = trailing_line(body)
        if tail.startswith(MARKER_PREFIX):
            markers.add(tail)
    return markers


class GitHubIssueTracker:
    """Track milestones as GitHub issues through the authenticated CLI."""

    def __init__(self, repository: str) -> None:
        self.repository = repository

    def read_tracked_issues(self) -> TrackedIssues:
        """Read every issue in the repository, open or closed.

        Closed issues count. A milestone whose issue was opened and completed
        must not be reopened as a duplicate on the next run.

        Every issue, not a labelled subset: a generated issue that loses its
        `type: ops` label during ordinary triage would otherwise become
        invisible, and the next run would reopen its milestone once per run
        forever. Idempotence should not depend on anyone's triage habits.

        The listing is also not a text search. GitHub's issue search is a
        relevance-ranked full-text query over an eventually consistent index:
        it would match unrelated issues that merely contain the marker's words,
        and it can omit an issue created moments earlier — precisely when a
        second run would duplicate it.
        """
        payload = run_gh(
            [
                "gh",
                "issue",
                "list",
                "--repo",
                self.repository,
                "--state",
                "all",
                "--limit",
                str(ISSUE_QUERY_LIMIT),
                "--json",
                "title,body",
            ],
            "could not list existing calendar issues",
        )
        records = issue_records(payload)
        if len(records) >= ISSUE_QUERY_LIMIT:
            raise ValueError(
                f"reached the {ISSUE_QUERY_LIMIT}-issue listing limit, so a marker may have been "
                "dropped; raise ISSUE_QUERY_LIMIT before running again"
            )
        return TrackedIssues(
            markers=frozenset(markers_in_issues([body for _, body in records])),
            titles=tuple(title for title, _ in records),
        )

    def ensure_milestone(self, title: str) -> None:
        """Create the per-election GitHub milestone unless it already exists."""
        payload = run_gh(
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
        run_gh(
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
        return run_gh(command, f"could not create issue {request.title!r}").strip()
