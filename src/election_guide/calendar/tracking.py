"""Turn calendar milestones coming due into tracking issues.

The planning half is pure: given a calendar, a date, a lead window, and the
markers already in flight, it decides exactly which issues should exist and
what each one says. Creating them against GitHub lives in `github_tracker`, so
idempotence is decided here and merely carried out there.
"""

from __future__ import annotations

from datetime import date, timedelta

from pydantic import BaseModel, ConfigDict, Field

from election_guide.calendar.models import CalendarMilestone, ElectionCalendar

# Every generated issue carries this marker so a later run recognizes its own
# work. It is the whole idempotence mechanism: stable per milestone, and
# derived from identity rather than from a date, so a milestone whose date
# moves is still recognized as already tracked instead of opening a second
# issue. Nothing rewrites the existing issue — see `plan_issues`.
MARKER_PREFIX = "calendar-milestone:"

# Labels applied to every generated issue, for triage only. Nothing about
# idempotence depends on them: the marker read scans every issue in the
# repository, so removing a label here changes what the issue looks like and
# not whether it is seen.
ISSUE_LABELS: tuple[str, ...] = ("type: ops", "area: operations")


def milestone_marker(election_id: str, milestone_id: str) -> str:
    """Build the stable identity a generated issue is recognized by."""
    return f"{MARKER_PREFIX} {election_id}/{milestone_id}"


class TrackingModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class IssueRequest(TrackingModel):
    """One issue the calendar says should exist."""

    marker: str = Field(min_length=1)
    title: str = Field(min_length=1)
    body: str = Field(min_length=1)
    labels: tuple[str, ...]
    milestone: str = Field(min_length=1)


def due_milestones(
    calendar: ElectionCalendar, *, as_of: date, lead_days: int
) -> list[tuple[CalendarMilestone, date]]:
    """List milestones scheduled within the lead window, soonest first.

    The window is inclusive at both ends and starts at `as_of`: a milestone
    whose date has already passed is not "coming due" and opening an issue for
    it would schedule work nobody can perform.
    """
    if lead_days < 0:
        raise ValueError("lead window cannot be negative")
    horizon = as_of + timedelta(days=lead_days)
    due = [
        (milestone, calendar.scheduled_date(milestone))
        for milestone in calendar.milestones
        if as_of <= calendar.scheduled_date(milestone) <= horizon
    ]
    return sorted(due, key=lambda item: (item[1], item[0].election_id, item[0].id))


def _issue_body(
    milestone: CalendarMilestone, election_id: str, scheduled: date, marker: str
) -> str:
    """Render the issue in the repository's task-template shape."""
    action = (
        f"Run `election-guide {milestone.workflow}`."
        if milestone.workflow is not None
        else "No pipeline command carries this milestone; it is a date to act on."
    )
    reference = (
        f"- `{milestone.reference}`\n" if milestone.reference is not None else "- None recorded.\n"
    )
    return (
        "## Outcome\n\n"
        f"The `{milestone.kind}` milestone for `{election_id}` is complete on or before "
        f"{scheduled.isoformat()}.\n\n"
        "## Scope\n\n"
        f"{action}\n\n"
        "This issue was opened from `config/calendar/elections.yaml` because the milestone "
        "falls inside the tracking lead window. It does not carry the work's design; see the "
        "reference below.\n\n"
        "## Acceptance criteria\n\n"
        f"- [ ] The milestone's work is done on or before {scheduled.isoformat()}.\n\n"
        "## Evidence and references\n\n"
        f"{reference}"
        f"- Calendar milestone `{milestone.id}` at offset {milestone.offset_days:+d} days.\n"
        "- `docs/ELECTION_CALENDAR.md` explains how the offset was chosen.\n\n"
        f"{marker}\n"
    )


def plan_issues(
    calendar: ElectionCalendar,
    *,
    as_of: date,
    lead_days: int,
    existing_markers: set[str],
) -> list[IssueRequest]:
    """Decide which issues are missing for the milestones now coming due.

    A milestone whose marker already exists is skipped outright. Creation is
    the only operation: if the milestone's declared date later moves, the open
    issue keeps the date it was opened with, and reconciling it is a manual
    step. Updating issues in place is deliberately out of scope (O12 excludes
    everything beyond creation), so the tracker must never be read as a
    self-refreshing view of the calendar.
    """
    plan: list[IssueRequest] = []
    for milestone, scheduled in due_milestones(calendar, as_of=as_of, lead_days=lead_days):
        marker = milestone_marker(milestone.election_id, milestone.id)
        if marker in existing_markers:
            continue
        plan.append(
            IssueRequest(
                marker=marker,
                title=f"{milestone.election_id}: {milestone.id} due {scheduled.isoformat()}",
                body=_issue_body(milestone, milestone.election_id, scheduled, marker),
                labels=ISSUE_LABELS,
                milestone=milestone.election_id,
            )
        )
    return plan
