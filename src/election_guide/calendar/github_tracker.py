"""Fulfil a calendar tracking plan against GitHub Issues.

This is the impure half of milestone tracking. It reads which markers already
exist, creates the missing issues, and escalates the ones whose promised
artifact never appeared; deciding what should exist and what counts as missing
belongs to `election_guide.calendar.tracking` and `.watch`.
"""

from __future__ import annotations

import json
from collections import defaultdict
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, cast

from election_guide.calendar.tracking import MARKER_PREFIX, IssueRequest
from election_guide.calendar.watch import ESCALATION_MARKER_PREFIX, EscalationRequest
from election_guide.github_cli import ISSUE_QUERY_LIMIT, run_gh, trailing_line

# How each escalation label presents itself the first time a run needs it.
# `gh issue edit --add-label` fails on a label the repository does not have, so
# the run creates them rather than depending on anyone having done it by hand.
ESCALATION_LABEL_COLORS: dict[str, str] = {
    "escalation: overdue": "D93F0B",
    "escalation: stale": "B60205",
}
ESCALATION_LABEL_DESCRIPTION = "A calendar milestone's promised artifact never appeared"


@dataclass(frozen=True)
class IssueRecord:
    """One existing issue, reduced to what milestone tracking reads."""

    number: int
    title: str
    body: str


@dataclass(frozen=True)
class TrackedIssues:
    """What the repository already says about calendar milestones.

    `markers` is the identity the tracker acts on. `titles` is only used to
    notice that a title and the markers disagree; it never establishes that a
    milestone is tracked. `issue_numbers` says which issues carry each marker —
    plural, because a marker is not unique in practice and an escalation that
    reached only one of them would leave the rest looking untouched.
    """

    markers: frozenset[str]
    titles: tuple[str, ...]
    issue_numbers: Mapping[str, tuple[int, ...]]


def issue_records(payload: str) -> list[IssueRecord]:
    """Extract each issue from `gh issue list --json number,title,body` output."""
    issues: Any = json.loads(payload)
    if not isinstance(issues, list):
        raise ValueError("GitHub CLI returned an issue list that is not an array")
    records: list[IssueRecord] = []
    for entry in cast(list[Any], issues):
        if not isinstance(entry, dict):
            raise ValueError("GitHub CLI returned an issue that is not an object")
        issue = cast(dict[str, Any], entry)
        number, title, body = issue.get("number"), issue.get("title"), issue.get("body")
        if not isinstance(number, int):
            raise ValueError("GitHub CLI returned an issue without a number")
        records.append(
            IssueRecord(
                number=number,
                title=title if isinstance(title, str) else "",
                body=body if isinstance(body, str) else "",
            )
        )
    return records


def issue_numbers_by_marker(records: list[IssueRecord]) -> dict[str, tuple[int, ...]]:
    """Group issue numbers by the calendar marker each body ends with."""
    grouped: defaultdict[str, list[int]] = defaultdict(list)
    for record in records:
        tail = trailing_line(record.body)
        if tail.startswith(MARKER_PREFIX):
            grouped[tail].append(record.number)
    return {marker: tuple(sorted(numbers)) for marker, numbers in grouped.items()}


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
                "number,title,body",
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
            markers=frozenset(markers_in_issues([record.body for record in records])),
            titles=tuple(record.title for record in records),
            issue_numbers=issue_numbers_by_marker(records),
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

    def read_escalation_markers(self, number: int) -> frozenset[str]:
        """Collect the escalation markers one issue's comments already carry.

        Comments rather than the body: the body is the milestone's identity and
        is never rewritten (`tracking.plan_issues`), so an escalation has to
        leave its own record. Only each comment's final non-empty line counts,
        matching the marker convention everywhere else here — a human quoting a
        marker mid-comment cannot suppress a real escalation.
        """
        payload = run_gh(
            [
                "gh",
                "issue",
                "view",
                str(number),
                "--repo",
                self.repository,
                "--json",
                "comments",
            ],
            f"could not read comments on issue #{number}",
        )
        document: Any = json.loads(payload)
        if not isinstance(document, dict):
            raise ValueError("GitHub CLI returned an issue that is not an object")
        comments = cast(dict[str, Any], document).get("comments")
        if not isinstance(comments, list):
            raise ValueError(f"GitHub CLI returned no comment list for issue #{number}")
        markers: set[str] = set()
        for entry in cast(list[Any], comments):
            if not isinstance(entry, dict):
                raise ValueError("GitHub CLI returned a comment that is not an object")
            body = cast(dict[str, Any], entry).get("body")
            if not isinstance(body, str):
                continue
            tail = trailing_line(body)
            if tail.startswith(ESCALATION_MARKER_PREFIX):
                markers.add(tail)
        return frozenset(markers)

    def ensure_label(self, name: str) -> None:
        """Create one escalation label unless the repository already has it."""
        payload = run_gh(
            [
                "gh",
                "label",
                "list",
                "--repo",
                self.repository,
                "--json",
                "name",
                "--jq",
                ".[].name",
            ],
            "could not list repository labels",
        )
        if name in {line.strip() for line in payload.splitlines() if line.strip()}:
            return
        run_gh(
            [
                "gh",
                "label",
                "create",
                name,
                "--repo",
                self.repository,
                "--color",
                ESCALATION_LABEL_COLORS[name],
                "--description",
                ESCALATION_LABEL_DESCRIPTION,
            ],
            f"could not create label {name!r}",
        )

    def escalate(self, request: EscalationRequest) -> None:
        """Add the stage's label to one issue and say why, in that order.

        The label first: it is the part visible without opening the issue, and
        a comment that landed under no label is the quiet outcome this check
        exists to avoid. The comment carries the marker, so a failure between
        the two leaves the stage unmarked and the next run retries it.
        """
        self.ensure_label(request.label)
        run_gh(
            [
                "gh",
                "issue",
                "edit",
                str(request.issue_number),
                "--repo",
                self.repository,
                "--add-label",
                request.label,
            ],
            f"could not label issue #{request.issue_number}",
        )
        run_gh(
            [
                "gh",
                "issue",
                "comment",
                str(request.issue_number),
                "--repo",
                self.repository,
                "--body",
                request.body,
            ],
            f"could not comment on issue #{request.issue_number}",
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
