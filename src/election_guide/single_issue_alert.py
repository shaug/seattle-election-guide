"""Shared open/update/close-single-tracked-issue mechanism.

The production-check alert (`hosting.production_alert`, O14) and the
link-rot alert (`sources.link_rot_alert`, O17) each reconcile one marker-
identified GitHub issue against a check result: a failure opens or updates
it, a recovery closes it, and nothing duplicates it while it is still open.
That lifecycle is identical between the two -- only the marker, issue
title, labels, error-message wording, and the domain payload rendered into
the issue body differ -- so it lives here once and each domain module
builds a thin wrapper on top, preserving its own public names and keyword
arguments.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from enum import Enum

from election_guide.github_cli import ISSUE_QUERY_LIMIT, parse_issue_list, run_gh, trailing_line


class AlertAction(Enum):
    NONE = "none"
    CREATE = "create"
    UPDATE = "update"
    CLOSE = "close"


def plan_alert_action(*, healthy: bool, existing_alert_number: int | None) -> AlertAction:
    """Decide what a check result implies for the alert issue, given what is open now."""
    if healthy:
        return AlertAction.CLOSE if existing_alert_number is not None else AlertAction.NONE
    return AlertAction.UPDATE if existing_alert_number is not None else AlertAction.CREATE


@dataclass(frozen=True)
class OpenAlert:
    number: int


class SingleIssueAlertTracker:
    """Open, update, and close one marker-tracked alert issue through `gh`."""

    def __init__(
        self,
        repository: str,
        *,
        marker: str,
        issue_title: str,
        issue_labels: tuple[str, ...],
        kind: str,
    ) -> None:
        self.repository = repository
        self.marker = marker
        self.issue_title = issue_title
        self.issue_labels = issue_labels
        self.kind = kind

    def find_open_alert(self) -> OpenAlert | None:
        payload = run_gh(
            [
                "gh",
                "issue",
                "list",
                "--repo",
                self.repository,
                "--state",
                "open",
                "--limit",
                str(ISSUE_QUERY_LIMIT),
                "--json",
                "number,body",
            ],
            f"could not list open {self.kind} issues",
        )
        entries = parse_issue_list(payload)
        if len(entries) >= ISSUE_QUERY_LIMIT:
            raise ValueError(
                f"reached the {ISSUE_QUERY_LIMIT}-issue listing limit, so an open alert may have "
                "been missed; raise ISSUE_QUERY_LIMIT before running again"
            )
        for entry in entries:
            number, body = entry.get("number"), entry.get("body")
            if (
                isinstance(number, int)
                and isinstance(body, str)
                and trailing_line(body) == self.marker
            ):
                return OpenAlert(number=number)
        return None

    def create(self, body: str) -> str:
        command = [
            "gh",
            "issue",
            "create",
            "--repo",
            self.repository,
            "--title",
            self.issue_title,
            "--body",
            body,
        ]
        for label in self.issue_labels:
            command += ["--label", label]
        return run_gh(command, f"could not open the {self.kind} alert issue").strip()

    def comment(self, number: int, body: str) -> None:
        run_gh(
            ["gh", "issue", "comment", str(number), "--repo", self.repository, "--body", body],
            f"could not update {self.kind} alert issue #{number}",
        )

    def close(self, number: int, *, comment: str) -> None:
        run_gh(
            ["gh", "issue", "close", str(number), "--repo", self.repository, "--comment", comment],
            f"could not close {self.kind} alert issue #{number}",
        )


def reconcile(
    tracker: SingleIssueAlertTracker,
    *,
    healthy: bool,
    render_body: Callable[[], str],
    render_recovery_comment: Callable[[], str],
) -> str:
    """Open, update, or close the alert issue to match the latest check result.

    `render_body` and `render_recovery_comment` are deferred (called only when
    their outcome is actually reached) because each domain renders a
    different payload into the same three positions.
    """
    existing = tracker.find_open_alert()
    action = plan_alert_action(
        healthy=healthy, existing_alert_number=existing.number if existing is not None else None
    )
    if action is AlertAction.NONE:
        return "healthy; no open alert"
    if action is AlertAction.CLOSE:
        assert existing is not None
        tracker.close(existing.number, comment=render_recovery_comment())
        return f"closed alert issue #{existing.number}"
    body = render_body()
    if action is AlertAction.CREATE:
        url = tracker.create(body)
        return f"opened alert issue: {url}"
    assert existing is not None
    tracker.comment(existing.number, body)
    return f"updated alert issue #{existing.number}"
