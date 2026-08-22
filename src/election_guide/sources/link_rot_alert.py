"""Reconcile the single link-rot alert issue against GitHub (O17).

Mirrors `election_guide.hosting.production_alert`'s update-in-place shape: a
confirmed failure must not open a second issue while the first is still
open, and full recovery closes it. Confirmation itself -- comparing this
run's failing URLs against the previous run's, so a single transient error
never reaches this module -- is `confirmed_failures` below, fed by
`election_guide.sources.link_check_state`.

Repetition alone is not enough, though. A site that answers a robot with 403
answers every run with 403, so counting consecutive failures confirmed a
policy rather than a dead page: the check spent three days reporting 17 live
URLs as rot (issue #399). `_cause_confirms_rot` is the second half of
confirmation -- it asks what the failure *was*, and only a cause that is
evidence the page is gone may repeat its way into an alert (issue #406).
"""

from __future__ import annotations

import errno
import re

from election_guide.collection.http import (
    DEADLINE_EXCEEDED,
    HTTP_STATUS_PREFIX,
    HTTPS_DOWNGRADE_REFUSED,
    REDIRECT_LIMIT_EXCEEDED,
    TOTAL_TIMEOUT_EXCEEDED,
)
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

# The only statuses that assert the page itself is gone. Every other non-2xx
# answer describes the request -- who asked, how often, from where.
_GONE_HTTP_STATUSES = frozenset({404, 410})

_HTTP_STATUS = re.compile(re.escape(HTTP_STATUS_PREFIX) + r"(\d+)")

# Causes that say how a site answered a robot rather than whether its page
# still exists. Every one is imported from the module that raises it, never
# spelled again here: a copy would keep matching its own prose after
# `fetch_http` reworded the real message, and silently flip that cause back to
# rot-confirming. Matched as substrings because `fetch_http` re-raises most of
# these wrapped in its own failure prefix, and the timeout that trips the outer
# deadline check arrives as that flat message on its own.
_INCONCLUSIVE_CAUSES = (
    TOTAL_TIMEOUT_EXCEEDED,
    DEADLINE_EXCEEDED,
    REDIRECT_LIMIT_EXCEEDED,
    HTTPS_DOWNGRADE_REFUSED,
    # A timeout in an `OSError`'s clothing. `EBADF` means the socket was
    # closed underneath an in-flight operation, and the only thing that does
    # that here is `fetch_http`'s own `threading.Timer(..., peer.close)`
    # deadline -- no remote host can produce it. Live evidence: the
    # 2026-08-22 run reported `sierra-club-washington` this way, a page the
    # 2026-08-17 run had reported as HTTP 403 and which is not gone.
    f"[Errno {errno.EBADF}]",
)

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


def _cause_confirms_rot(error: str | None) -> bool:
    """Whether one probe failure is evidence the page is gone, or only that it was guarded.

    Inconclusive by exception and confirming by default. The exceptions are
    enumerable because `fetch_http` owns every cause: an access-control or
    rate-limit status, a redirect loop, a refused HTTPS downgrade, a timeout.
    Everything else -- 404, 410, DNS that will not resolve, a socket that will
    not open -- keeps the behavior O17 has always had. Defaulting the other
    way would have to recognize a connection failure, and `_open_public_connection`
    re-raises the operating system's own `OSError` text, which carries no
    marker to recognize; it would also silence any cause `fetch_http` grows
    later, turning a new kind of real rot into silence rather than an alert.
    """
    if error is None:
        return False
    status = _HTTP_STATUS.search(error)
    if status is not None:
        return int(status.group(1)) in _GONE_HTTP_STATUSES
    return not any(cause in error for cause in _INCONCLUSIVE_CAUSES)


def confirmed_failures(
    results: list[LinkCheckResult], previous: LinkCheckState
) -> list[LinkCheckResult]:
    """Failures that repeated as rot: evidence the page is gone this run and last run."""
    previously_rotting = set(previous.rot_confirming_urls)
    return [
        result
        for result in results
        if not result.ok
        and _cause_confirms_rot(result.error)
        and result.target.url in previously_rotting
    ]


def next_state(results: list[LinkCheckResult]) -> LinkCheckState:
    """What this run leaves behind: everything that failed, and what looked like rot."""
    failing = [result for result in results if not result.ok]
    return LinkCheckState(
        failing_urls=tuple(sorted(result.target.url for result in failing)),
        rot_confirming_urls=tuple(
            sorted(result.target.url for result in failing if _cause_confirms_rot(result.error))
        ),
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
