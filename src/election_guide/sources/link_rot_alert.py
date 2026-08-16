"""Reconcile the single link-rot alert issue against GitHub (O17).

Mirrors `election_guide.hosting.production_alert`'s update-in-place shape: a
confirmed failure must not open a second issue while the first is still
open, and full recovery closes it. Confirmation itself -- comparing this
run's failing URLs against the previous run's, so a single transient error
never reaches this module -- is `confirmed_failures` below, fed by
`election_guide.sources.link_check_state`.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from enum import Enum
from typing import Any, cast

from election_guide.github_cli import ISSUE_QUERY_LIMIT, run_gh, trailing_line
from election_guide.sources.link_check import LinkCheckResult
from election_guide.sources.link_check_state import LinkCheckState

MARKER = "link-rot-check:monitor"
ISSUE_TITLE = "Cited source links are unreachable"
ISSUE_LABELS: tuple[str, ...] = ("type: ops", "area: operations")


class AlertAction(Enum):
    NONE = "none"
    CREATE = "create"
    UPDATE = "update"
    CLOSE = "close"


def confirmed_failures(
    results: list[LinkCheckResult], previous: LinkCheckState
) -> list[LinkCheckResult]:
    """Failures that repeated: unreachable this run and also unreachable last run."""
    previously_failing = set(previous.failing_urls)
    return [
        result for result in results if not result.ok and result.target.url in previously_failing
    ]


def next_state(results: list[LinkCheckResult]) -> LinkCheckState:
    """The failing-URL set this run leaves behind for the next run to confirm against."""
    return LinkCheckState(
        failing_urls=tuple(sorted(result.target.url for result in results if not result.ok))
    )


def plan_alert_action(*, has_confirmed: bool, existing_alert_number: int | None) -> AlertAction:
    """Decide what a check result implies for the alert issue, given what is open now."""
    if not has_confirmed:
        return AlertAction.CLOSE if existing_alert_number is not None else AlertAction.NONE
    return AlertAction.UPDATE if existing_alert_number is not None else AlertAction.CREATE


def render_alert_body(confirmed: list[LinkCheckResult], *, checked_at: str) -> str:
    """Render the alert issue body (on create) or its update comment (on repeat failure)."""
    findings = "\n".join(
        f"- {result.target.source_name} (`{result.target.source_id}`): {result.target.url}\n"
        f"  {result.error}"
        for result in confirmed
    )
    return (
        "## Outcome\n\n"
        f"The scheduled link-rot check found {len(confirmed)} cited source URL(s) unreachable "
        f"across consecutive runs, as of {checked_at}.\n\n"
        "## Failing\n\n" + findings + "\n\n"
        "## Evidence and references\n\n"
        "- `SOURCE_POLICY.md` governs what may be cited; this check reports only and never "
        "mutates source data, rewrites a stored URL, or re-captures evidence.\n\n"
        f"{MARKER}\n"
    )


def render_recovery_comment(checked_at: str) -> str:
    return f"Recovered: the scheduled check found every cited URL reachable at {checked_at}."


@dataclass(frozen=True)
class OpenAlert:
    number: int


def _carries_marker(body: str) -> bool:
    """Only the final non-empty line counts, matching the calendar tracker's convention."""
    return trailing_line(body) == MARKER


class LinkRotAlertTracker:
    """Open, update, and close the link-rot alert issue through `gh`."""

    def __init__(self, repository: str) -> None:
        self.repository = repository

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
            "could not list open link-rot-check issues",
        )
        issues: Any = json.loads(payload)
        if not isinstance(issues, list):
            raise ValueError("GitHub CLI returned an issue list that is not an array")
        entries = cast(list[Any], issues)
        if len(entries) >= ISSUE_QUERY_LIMIT:
            raise ValueError(
                f"reached the {ISSUE_QUERY_LIMIT}-issue listing limit, so an open alert may have "
                "been missed; raise ISSUE_QUERY_LIMIT before running again"
            )
        for entry in entries:
            if not isinstance(entry, dict):
                raise ValueError("GitHub CLI returned an issue that is not an object")
            issue = cast(dict[str, Any], entry)
            number, body = issue.get("number"), issue.get("body")
            if isinstance(number, int) and isinstance(body, str) and _carries_marker(body):
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
            ISSUE_TITLE,
            "--body",
            body,
        ]
        for label in ISSUE_LABELS:
            command += ["--label", label]
        return run_gh(command, "could not open the link-rot-check alert issue").strip()

    def comment(self, number: int, body: str) -> None:
        run_gh(
            ["gh", "issue", "comment", str(number), "--repo", self.repository, "--body", body],
            f"could not update link-rot-check alert issue #{number}",
        )

    def close(self, number: int, *, comment: str) -> None:
        run_gh(
            ["gh", "issue", "close", str(number), "--repo", self.repository, "--comment", comment],
            f"could not close link-rot-check alert issue #{number}",
        )


def reconcile_alert(
    tracker: LinkRotAlertTracker,
    confirmed: list[LinkCheckResult],
    *,
    checked_at: str,
) -> str:
    """Open, update, or close the alert issue to match the latest confirmed failures."""
    existing = tracker.find_open_alert()
    action = plan_alert_action(
        has_confirmed=bool(confirmed),
        existing_alert_number=existing.number if existing is not None else None,
    )
    if action is AlertAction.NONE:
        return "healthy; no open alert"
    if action is AlertAction.CLOSE:
        assert existing is not None
        tracker.close(existing.number, comment=render_recovery_comment(checked_at))
        return f"closed alert issue #{existing.number}"
    body = render_alert_body(confirmed, checked_at=checked_at)
    if action is AlertAction.CREATE:
        url = tracker.create(body)
        return f"opened alert issue: {url}"
    assert existing is not None
    tracker.comment(existing.number, body)
    return f"updated alert issue #{existing.number}"
