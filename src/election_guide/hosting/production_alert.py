"""Reconcile the single production-check alert issue against GitHub.

Unlike calendar milestone tracking (`election_guide.calendar.tracking`),
which only ever creates, this identity is update-in-place by design
(`docs/SITE_OPERATIONS_PLAN.md`, O14 acceptance): a failing scheduled check
must not open a second issue while the first is still open, and a recovered
check must close it. Once closed, a later failure opens a fresh issue —
nothing here reopens a resolved one.
"""

from __future__ import annotations

from election_guide.hosting.production_check import ProductionCheckReport, render_summary_lines
from election_guide.single_issue_alert import (
    AlertAction,
    OpenAlert,
    SingleIssueAlertTracker,
)
from election_guide.single_issue_alert import plan_alert_action as _plan_alert_action
from election_guide.single_issue_alert import reconcile as _reconcile

MARKER = "production-check:monitor"
ISSUE_TITLE = "Production is not serving the expected build"
ISSUE_LABELS: tuple[str, ...] = ("type: ops", "area: operations")

__all__ = [
    "ISSUE_LABELS",
    "ISSUE_TITLE",
    "MARKER",
    "AlertAction",
    "OpenAlert",
    "ProductionAlertTracker",
    "plan_alert_action",
    "reconcile_alert",
    "render_alert_body",
    "render_recovery_comment",
]


def plan_alert_action(*, healthy: bool, existing_alert_number: int | None) -> AlertAction:
    """Decide what a check result implies for the alert issue, given what is open now."""
    return _plan_alert_action(healthy=healthy, existing_alert_number=existing_alert_number)


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


class ProductionAlertTracker(SingleIssueAlertTracker):
    """Open, update, and close the production-check alert issue through `gh`."""

    def __init__(self, repository: str) -> None:
        super().__init__(
            repository,
            marker=MARKER,
            issue_title=ISSUE_TITLE,
            issue_labels=ISSUE_LABELS,
            kind="production-check",
        )


def reconcile_alert(
    tracker: ProductionAlertTracker,
    report: ProductionCheckReport,
    *,
    base_url: str,
    checked_at: str,
) -> str:
    """Open, update, or close the alert issue to match the latest check result."""
    return _reconcile(
        tracker,
        healthy=report.ok,
        render_body=lambda: render_alert_body(report, base_url=base_url, checked_at=checked_at),
        render_recovery_comment=lambda: render_recovery_comment(checked_at),
    )
