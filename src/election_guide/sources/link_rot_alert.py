"""Reconcile the single link-rot alert issue against GitHub (O17).

Mirrors `election_guide.hosting.production_alert`'s update-in-place shape: a
confirmed failure must not open a second issue while the first is still
open, and full recovery closes it. Confirmation itself -- comparing this
run's failing URLs against the previous run's, so a single transient error
never reaches this module -- is `confirmed_failures` below, fed by
`election_guide.sources.link_check_state`.
"""

from __future__ import annotations

from election_guide.single_issue_alert import (
    AlertAction,
    OpenAlert,
    SingleIssueAlertTracker,
)
from election_guide.single_issue_alert import plan_alert_action as _plan_alert_action
from election_guide.single_issue_alert import reconcile as _reconcile
from election_guide.sources.link_check import LinkCheckResult
from election_guide.sources.link_check_state import LinkCheckState

MARKER = "link-rot-check:monitor"
ISSUE_TITLE = "Cited source links are unreachable"
ISSUE_LABELS: tuple[str, ...] = ("type: ops", "area: operations")

__all__ = [
    "ISSUE_LABELS",
    "ISSUE_TITLE",
    "MARKER",
    "AlertAction",
    "LinkRotAlertTracker",
    "OpenAlert",
    "confirmed_failures",
    "next_state",
    "plan_alert_action",
    "reconcile_alert",
    "render_alert_body",
    "render_recovery_comment",
]


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
    return _plan_alert_action(
        healthy=not has_confirmed, existing_alert_number=existing_alert_number
    )


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


class LinkRotAlertTracker(SingleIssueAlertTracker):
    """Open, update, and close the link-rot alert issue through `gh`."""

    def __init__(self, repository: str) -> None:
        super().__init__(
            repository,
            marker=MARKER,
            issue_title=ISSUE_TITLE,
            issue_labels=ISSUE_LABELS,
            kind="link-rot-check",
        )


def reconcile_alert(
    tracker: LinkRotAlertTracker,
    confirmed: list[LinkCheckResult],
    *,
    checked_at: str,
) -> str:
    """Open, update, or close the alert issue to match the latest confirmed failures."""
    return _reconcile(
        tracker,
        healthy=not confirmed,
        render_body=lambda: render_alert_body(confirmed, checked_at=checked_at),
        render_recovery_comment=lambda: render_recovery_comment(checked_at),
    )
