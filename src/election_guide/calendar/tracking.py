"""Turn calendar milestones coming due into tracking issues.

The planning half is pure: given a calendar, a date, a lead window, and the
markers already in flight, it decides exactly which issues should exist and
what each one says. Creating them against GitHub lives in `github_tracker`, so
idempotence is decided here and merely carried out there.
"""

from __future__ import annotations

from collections.abc import Iterable
from datetime import date, timedelta

from pydantic import BaseModel, ConfigDict, Field

from election_guide.calendar.models import CalendarMilestone, ElectionCalendar, MilestoneKind

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

# Historical statutory anchors can be declared after their dates have passed so
# the calendar records the timing distinction other policy consumes. They are
# facts, not work to schedule, and therefore never open tracking issues.
INFORMATIONAL_MILESTONE_KINDS: frozenset[MilestoneKind] = frozenset(
    {"special_absentee_ballots_available"}
)

# Generated issues must carry the same date semantics as the calendar contract.
# In particular, `ballots_mail` is a domestic checkpoint rather than the first
# possible ballot-in-hand date or a trigger for guide publication and refreshes.
TIMING_CONTEXT: dict[MilestoneKind, str] = {
    "overseas_service_ballots_mail": (
        "This is the scheduled regular issuance checkpoint for overseas and service voters; "
        "electronic delivery can make the issuance day a ballot-in-hand day."
    ),
    "ballots_mail": (
        "This is the domestic mass-mail checkpoint, not the first date a voter may possess a "
        "ballot and not the trigger for guide publication or endorsement refreshes."
    ),
}


def milestone_marker(election_id: str, milestone_id: str) -> str:
    """Build the stable identity a generated issue is recognized by."""
    return f"{MARKER_PREFIX} {election_id}/{milestone_id}"


def milestone_title_prefix(election_id: str, milestone_id: str) -> str:
    """The part of a generated title that names the milestone, without its date.

    A date that moves does not rewrite an open issue's title, so this prefix
    still identifies the milestone afterwards. It is never used to decide that
    a milestone is tracked — only to notice that a title and the markers
    disagree. Recognizing by title would let a human who copied one suppress a
    real milestone.
    """
    return f"{election_id}: {milestone_id} due "


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
    it would schedule work nobody can perform. Informational statutory anchors
    are never due because they record facts rather than work.
    """
    if lead_days < 0:
        raise ValueError("lead window cannot be negative")
    horizon = as_of + timedelta(days=lead_days)
    due = [
        (milestone, calendar.scheduled_date(milestone))
        for milestone in calendar.milestones
        if milestone.kind not in INFORMATIONAL_MILESTONE_KINDS
        and as_of <= calendar.scheduled_date(milestone) <= horizon
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
    timing_context = TIMING_CONTEXT.get(milestone.kind)
    timing = f"\n{timing_context}\n" if timing_context is not None else ""
    return (
        "## Outcome\n\n"
        f"The `{milestone.kind}` milestone for `{election_id}` is complete on or before "
        f"{scheduled.isoformat()}.\n"
        f"{timing}\n"
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
                title=(
                    milestone_title_prefix(milestone.election_id, milestone.id)
                    + scheduled.isoformat()
                ),
                body=_issue_body(milestone, milestone.election_id, scheduled, marker),
                labels=ISSUE_LABELS,
                milestone=milestone.election_id,
            )
        )
    return plan


def unmarked_collisions(
    plan: Iterable[IssueRequest], existing_titles: Iterable[str]
) -> list[tuple[IssueRequest, str]]:
    """Planned issues whose milestone an existing title already claims.

    The marker is the only identity, so a milestone reaching the plan means no
    marker was read for it. If a title nonetheless says the issue exists, the
    two signals disagree — most likely an edit pushed the marker off the body's
    last line — and creating another issue would repeat that every run.

    Returns each such request beside the title that contradicts it, so the
    caller can skip it and say which issue to look at.
    """
    titles = list(existing_titles)
    collisions: list[tuple[IssueRequest, str]] = []
    for request in plan:
        prefix = request.title[: request.title.rindex(" due ") + len(" due ")]
        match = next((title for title in titles if title.startswith(prefix)), None)
        if match is not None:
            collisions.append((request, match))
    return collisions
