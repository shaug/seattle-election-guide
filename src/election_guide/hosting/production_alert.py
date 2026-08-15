"""Reconcile the single production-check alert issue against GitHub.

Unlike calendar milestone tracking (`election_guide.calendar.tracking`),
which only ever creates, this identity is update-in-place by design
(`docs/SITE_OPERATIONS_PLAN.md`, O14 acceptance): a failing scheduled check
must not open a second issue while the first is still open, and a recovered
check must close it. Once closed, a later failure opens a fresh issue —
nothing here reopens a resolved one.
"""

from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass
from enum import Enum
from typing import Any, cast

from election_guide.hosting.production_check import ProductionCheckReport, render_summary_lines

MARKER = "production-check:monitor"
ISSUE_TITLE = "Production is not serving the expected build"
ISSUE_LABELS: tuple[str, ...] = ("type: ops", "area: operations")

# Open issues only; a triaged repository keeps this far smaller than the
# calendar tracker's lifetime-issue-count bound, but the same "fail loudly
# rather than truncate" reasoning applies: a dropped alert here is a
# duplicate, not a suppressed reminder.
ISSUE_QUERY_LIMIT = 10000


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


def render_alert_body(report: ProductionCheckReport, *, base_url: str, checked_at: str) -> str:
    """Render the alert issue body (on create) or its update comment (on repeat failure)."""
    return (
        "## Outcome\n\n"
        f"The scheduled production check against {base_url} failed at {checked_at}.\n\n"
        "## Observed\n\n" + "\n".join(f"- {line}" for line in render_summary_lines(report)) + "\n\n"
        "## Evidence and references\n\n"
        '- `docs/HOSTING.md`, "Archive manifest and routes", is the route contract this check '
        "asserts against.\n"
        "- `docs/runbooks/production-rollback.md` is the recovery procedure.\n\n"
        f"{MARKER}\n"
    )


def render_recovery_comment(checked_at: str) -> str:
    return f"Recovered: the scheduled check passed at {checked_at}."


@dataclass(frozen=True)
class OpenAlert:
    number: int


def _run(command: list[str], failure: str) -> str:
    try:
        completed = subprocess.run(command, capture_output=True, text=True, check=False)
    except OSError as error:
        raise ValueError(
            "the GitHub CLI is required for the production-check alert: install `gh` "
            "(https://cli.github.com) and authenticate it"
        ) from error
    if completed.returncode != 0:
        detail = completed.stderr.strip() or completed.stdout.strip()
        raise ValueError(f"{failure}: {detail}")
    return completed.stdout


def _carries_marker(body: str) -> bool:
    """Only the final non-empty line counts, matching the calendar tracker's convention."""
    lines = [line.strip() for line in body.splitlines()]
    tail = next((line for line in reversed(lines) if line), "")
    return tail == MARKER


class ProductionAlertTracker:
    """Open, update, and close the production-check alert issue through `gh`."""

    def __init__(self, repository: str) -> None:
        self.repository = repository

    def find_open_alert(self) -> OpenAlert | None:
        payload = _run(
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
            "could not list open production-check issues",
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
        return _run(command, "could not open the production-check alert issue").strip()

    def comment(self, number: int, body: str) -> None:
        _run(
            ["gh", "issue", "comment", str(number), "--repo", self.repository, "--body", body],
            f"could not update production-check alert issue #{number}",
        )

    def close(self, number: int, *, comment: str) -> None:
        _run(
            ["gh", "issue", "close", str(number), "--repo", self.repository, "--comment", comment],
            f"could not close production-check alert issue #{number}",
        )


def reconcile_alert(
    tracker: ProductionAlertTracker,
    report: ProductionCheckReport,
    *,
    base_url: str,
    checked_at: str,
) -> str:
    """Open, update, or close the alert issue to match the latest check result."""
    existing = tracker.find_open_alert()
    action = plan_alert_action(
        healthy=report.ok, existing_alert_number=existing.number if existing is not None else None
    )
    if action is AlertAction.NONE:
        return "healthy; no open alert"
    if action is AlertAction.CLOSE:
        assert existing is not None
        tracker.close(existing.number, comment=render_recovery_comment(checked_at))
        return f"closed alert issue #{existing.number}"
    body = render_alert_body(report, base_url=base_url, checked_at=checked_at)
    if action is AlertAction.CREATE:
        url = tracker.create(body)
        return f"opened alert issue: {url}"
    assert existing is not None
    tracker.comment(existing.number, body)
    return f"updated alert issue #{existing.number}"
