"""Notice a calendar milestone whose promised artifact never appeared.

Tracking (`tracking.py`) makes a milestone visible before it is due. This is
the other half: after the window closes, it asks whether the work actually
landed, and escalates the milestone's tracking issue when nothing in the
repository says it did. A vanity project's automation fails silently; this is
what makes a missed capture window loud instead of lost.

The planning half is pure, exactly as tracking's is: given a calendar, a date,
and what the repository holds, it decides which milestones passed without their
artifact and what each escalation should say. Posting against GitHub lives in
`github_tracker`, so what counts as missing is decided here and merely carried
out there.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Literal
from zoneinfo import ZoneInfo

from pydantic import Field

from election_guide.calendar.models import (
    ELECTION_TIMEZONE,
    CalendarMilestone,
    ElectionCalendar,
    MilestoneKind,
)
from election_guide.calendar.tracking import TrackingModel, milestone_marker
from election_guide.collection.refresh import read_refresh_event
from election_guide.evidence.models import CapturedManifest
from election_guide.evidence.storage import read_capture_manifest

# Every escalation comment carries this marker so a later run recognizes its
# own work, the same way `MARKER_PREFIX` works for the issues themselves. It is
# the whole idempotence mechanism here: stable per milestone and stage, so a
# schedule running four times a day comments once and then stays quiet.
ESCALATION_MARKER_PREFIX = "calendar-escalation:"

# How long after its date a milestone's artifact may still appear. An
# election-night capture that ran late is still the capture; one that never ran
# is the thing worth saying out loud. The window also scopes a capture to one
# election: manifests carry no election field, so the only thing keeping a
# November capture from satisfying an August milestone is that it falls outside
# this window.
ARTIFACT_WINDOW_DAYS = 7

# How long past its date a still-missing artifact stops being late and starts
# being lost. Nothing here can recover the window; the second stage exists so
# that a first comment nobody read does not become the last word.
STALE_ESCALATION_DAYS = 21

EscalationStage = Literal["overdue", "stale"]

STAGE_ORDER: tuple[EscalationStage, ...] = ("overdue", "stale")

# Days past the milestone's own date at which each stage starts applying.
STAGE_THRESHOLD_DAYS: dict[EscalationStage, int] = {
    "overdue": ARTIFACT_WINDOW_DAYS,
    "stale": STALE_ESCALATION_DAYS,
}


@dataclass(frozen=True)
class EscalationLabel:
    """The louder label one stage adds, and how it presents itself.

    Name and colour travel together so they cannot drift into two tables keyed
    by the same strings — a stage whose colour went missing would raise inside
    the label creation and kill the run before it posted anything, which is the
    silent failure this check exists to avoid.
    """

    name: str
    color: str


# Labels are the part of an escalation visible without opening the issue, which
# is why the stage shows in the name rather than in a description nobody sees.
STAGE_LABELS: dict[EscalationStage, EscalationLabel] = {
    "overdue": EscalationLabel(name="escalation: overdue", color="D93F0B"),
    "stale": EscalationLabel(name="escalation: stale", color="B60205"),
}

# Derived, never hand-maintained: every declared stage label has a colour by
# construction.
LABEL_COLORS: dict[str, str] = {label.name: label.color for label in STAGE_LABELS.values()}

# Where each kind of promised artifact lives. Declared here rather than at the
# CLI so the sentence an escalation prints and the directory the check reads
# cannot drift apart.
EVIDENCE_MANIFEST_DIR = Path("data/manifests/evidence")
REFRESH_EVENT_DIR = Path("data/collection/refreshes")


ArtifactKind = Literal["evidence_manifest", "refresh_event"]

ARTIFACT_NAMES: dict[ArtifactKind, str] = {
    "evidence_manifest": "an evidence manifest",
    "refresh_event": "a refresh event",
}
ARTIFACT_DIRECTORIES: dict[ArtifactKind, Path] = {
    "evidence_manifest": EVIDENCE_MANIFEST_DIR,
    "refresh_event": REFRESH_EVENT_DIR,
}


CaptureSource = Literal["authority", "endorsement"]


@dataclass(frozen=True)
class ArtifactExpectation:
    """What a milestone kind promises, and how the check recognizes it."""

    kinds: tuple[ArtifactKind, ...]
    # Which registry the capture's `source_id` must belong to. Results captures
    # come from a counting authority; a sweep's captures come from the
    # endorsement panel. Both land in the same manifest directory, so without
    # this the two are indistinguishable inside an overlapping window — and
    # they do overlap: `wa-2026-general`'s final refresh falls four days before
    # election day, so its window (2026-10-30 through 2026-11-06) contains
    # election night. The election-night capture would then satisfy a sweep
    # that never ran, which is exactly the silent pass this check exists to
    # stop.
    capture_source: CaptureSource
    # The phrase the runbooks' title convention puts in a capture's title.
    # Evidence manifests carry no election or capture-kind field — a structured
    # one was tried and reverted, because adding a field to `CaptureMetadata`
    # changes what every already-committed manifest serializes to
    # (`docs/EVIDENCE_CAPTURE.md`, "Counting authorities") — so the title is
    # what separates a first count from a certified one. Unset means any
    # capture from the right registry counts, which is all a sweep can promise:
    # its titles are the sources' own.
    title_phrase: str | None = None

    def describe(self) -> str:
        return " or ".join(ARTIFACT_NAMES[kind] for kind in self.kinds)

    def locations(self) -> str:
        return " or ".join(f"`{ARTIFACT_DIRECTORIES[kind].as_posix()}/`" for kind in self.kinds)


ARTIFACT_EXPECTATIONS: dict[MilestoneKind, ArtifactExpectation] = {
    "results_capture_election_night": ArtifactExpectation(
        kinds=("evidence_manifest",),
        capture_source="authority",
        title_phrase="election-night results",
    ),
    # `certified`, not `certified results`: the election-night runbook pins an
    # exact title template, but the certified one asks only for "titles naming
    # the certified status" (`docs/runbooks/results-certified-ingest.md`), so a
    # conforming "certified canvass" must not read as a missing capture.
    "results_capture_post_certification": ArtifactExpectation(
        kinds=("evidence_manifest",),
        capture_source="authority",
        title_phrase="certified",
    ),
    # Either, because a sweep leaves whichever its sources allowed. `collect
    # refresh` writes a refresh event, but most of the 2026 primary's panel was
    # captured directly and left evidence manifests instead — the runbook's own
    # verification is written around those (`docs/runbooks/
    # endorsement-discovery-sweep.md`). Demanding the event alone would
    # escalate a sweep that did happen; accepting either still catches the
    # window where nothing did.
    "refresh": ArtifactExpectation(
        kinds=("evidence_manifest", "refresh_event"), capture_source="endorsement"
    ),
}


def escalation_marker(election_id: str, milestone_id: str, stage: EscalationStage) -> str:
    """Build the stable identity one escalation comment is recognized by."""
    return f"{ESCALATION_MARKER_PREFIX} {election_id}/{milestone_id} {stage}"


@dataclass(frozen=True)
class CaptureRecord:
    """One captured evidence manifest, reduced to what matching reads."""

    source_id: str
    title: str
    retrieved_at: datetime


@dataclass(frozen=True)
class RepositoryArtifacts:
    """What the repository holds that a milestone could have promised.

    `authority_ids` is what tells a counting authority's capture apart from an
    endorsement source's; both kinds land in the same manifest directory and
    the manifest itself does not say which registry its `source_id` came from.
    """

    captures: tuple[CaptureRecord, ...] = ()
    refreshes: tuple[datetime, ...] = ()
    authority_ids: frozenset[str] = frozenset()


@dataclass(frozen=True)
class ArtifactWindow:
    """The dates, in the election's own zone, an artifact may be stamped with.

    Pacific, not UTC: King County posts its first count around 8:15 p.m., so an
    election-night capture is routinely stamped with the following UTC date.
    Comparing UTC dates would call the 2026-08-04 capture a day late.
    """

    start: date
    end: date

    def contains(self, moment: datetime) -> bool:
        return self.start <= election_date(moment) <= self.end


@dataclass(frozen=True)
class MissingArtifact:
    """One past-due milestone with nothing in the repository to show for it."""

    milestone: CalendarMilestone
    scheduled: date
    window: ArtifactWindow
    expectation: ArtifactExpectation
    stages: tuple[EscalationStage, ...]


class EscalationRequest(TrackingModel):
    """One escalation the check says an issue should carry."""

    marker: str = Field(min_length=1)
    # `<election-id>/<milestone-id>`, for the run's own output. The marker
    # carries the same identity, but reporting should not ask a reader to
    # parse it back out.
    milestone: str = Field(min_length=1)
    stage: EscalationStage
    label: str = Field(min_length=1)
    body: str = Field(min_length=1)
    issue_number: int = Field(gt=0)


def artifact_window(scheduled: date) -> ArtifactWindow:
    """The dates an artifact for a milestone scheduled on `scheduled` may carry."""
    return ArtifactWindow(start=scheduled, end=scheduled + timedelta(days=ARTIFACT_WINDOW_DAYS))


def election_date(moment: datetime) -> date:
    """Place one instant on the election's own calendar.

    The single rule every day-count here obeys. Both halves of this check have
    to agree on what day it is: an artifact's timestamp is compared in Pacific,
    so "has the window closed" must be too — read from UTC instead, the
    scheduled 03:17 UTC run lands at 19:17 Pacific the previous day and already
    calls it tomorrow. That would escalate a milestone with hours of its window
    left, and they are the hours that matter: King County publishes its first
    count around 8:15 p.m. Pacific, inside the gap. Nothing retracts an
    escalation once posted, and its marker stops the next run from
    reconsidering, so the wrong call would be permanent.
    """
    return moment.astimezone(ZoneInfo(ELECTION_TIMEZONE)).date()


def current_election_date(now: datetime) -> date:
    """Today where the election is, which is the calendar the windows use."""
    return election_date(now)


def reached_stages(scheduled: date, *, as_of: date) -> tuple[EscalationStage, ...]:
    """Every escalation stage a still-missing artifact has passed.

    Every stage it passed, not only the one it is in now. A run that first
    happens weeks late would otherwise skip `overdue` outright, which is the
    same quiet pass this check exists to stop — and it would make what an issue
    says depend on when the schedule happened to fire.
    """
    elapsed = (as_of - scheduled).days
    return tuple(stage for stage in STAGE_ORDER if elapsed > STAGE_THRESHOLD_DAYS[stage])


def _capture_matches(
    expectation: ArtifactExpectation,
    capture: CaptureRecord,
    window: ArtifactWindow,
    authority_ids: frozenset[str],
) -> bool:
    """Whether one capture is the artifact this milestone promised."""
    if not window.contains(capture.retrieved_at):
        return False
    from_authority = capture.source_id in authority_ids
    if from_authority != (expectation.capture_source == "authority"):
        return False
    return (expectation.title_phrase or "").casefold() in capture.title.casefold()


def artifact_exists(
    expectation: ArtifactExpectation, window: ArtifactWindow, artifacts: RepositoryArtifacts
) -> bool:
    """Whether the repository holds what this milestone promised, in its window."""
    if "evidence_manifest" in expectation.kinds and any(
        _capture_matches(expectation, capture, window, artifacts.authority_ids)
        for capture in artifacts.captures
    ):
        return True
    return "refresh_event" in expectation.kinds and any(
        window.contains(moment) for moment in artifacts.refreshes
    )


def missing_artifacts(
    calendar: ElectionCalendar, *, as_of: date, artifacts: RepositoryArtifacts
) -> list[MissingArtifact]:
    """List past-due milestones whose promised artifact never appeared.

    A milestone is skipped outright when its kind promises nothing this check
    can verify — most kinds are dates to act on rather than work that leaves a
    record — or when it declares an `artifact_record`, which says the work
    landed in a form no artifact directory holds.
    """
    missing: list[MissingArtifact] = []
    for milestone in calendar.milestones:
        expectation = ARTIFACT_EXPECTATIONS.get(milestone.kind)
        if expectation is None or milestone.artifact_record is not None:
            continue
        scheduled = calendar.scheduled_date(milestone)
        stages = reached_stages(scheduled, as_of=as_of)
        window = artifact_window(scheduled)
        if not stages or artifact_exists(expectation, window, artifacts):
            continue
        missing.append(
            MissingArtifact(
                milestone=milestone,
                scheduled=scheduled,
                window=window,
                expectation=expectation,
                stages=stages,
            )
        )
    return sorted(
        missing, key=lambda item: (item.scheduled, item.milestone.election_id, item.milestone.id)
    )


def _escalation_body(missing: MissingArtifact, stage: EscalationStage, *, as_of: date) -> str:
    """Render one escalation comment, in the repository's issue-body shape."""
    milestone = missing.milestone
    elapsed = (as_of - missing.scheduled).days
    expectation = missing.expectation
    lead = (
        f"and {expectation.describe()} for it still does not exist {elapsed} days later. "
        "Treat the window as lost unless the artifact can still be produced."
        if stage == "stale"
        else f"and {expectation.describe()} for it does not exist {elapsed} days later."
    )
    looked_for = [
        f"- {expectation.describe().capitalize()} under {expectation.locations()}.",
        f"- Stamped between {missing.window.start.isoformat()} and "
        f"{missing.window.end.isoformat()}, Pacific.",
    ]
    if expectation.title_phrase is not None:
        looked_for.append(f"- Titled with `{expectation.title_phrase}`.")
    references = [
        f"- `{milestone.reference}` is the procedure this milestone hands its work to."
        if milestone.reference is not None
        else "- No procedure document is recorded for this milestone.",
        '- `docs/ELECTION_CALENDAR.md`, "Watching for the promised artifact", explains what this '
        "check looks for and what to do when the work did happen in another form.",
    ]
    return (
        "## Outcome\n\n"
        f"The `{milestone.kind}` milestone for `{milestone.election_id}` was due "
        f"{missing.scheduled.isoformat()}, {lead}\n\n"
        "## Observed\n\n" + "\n".join(looked_for) + "\n\n"
        "## Evidence and references\n\n" + "\n".join(references) + "\n\n"
        f"{escalation_marker(milestone.election_id, milestone.id, stage)}\n"
    )


def tracked_issue_numbers(
    item: MissingArtifact, issue_numbers: Mapping[str, Sequence[int]]
) -> tuple[int, ...]:
    """Which issues track this milestone, if any.

    The one place that knows a milestone's marker is how its issues are found.
    Everything that needs the answer — the plan, the untracked report, and the
    run that reads each issue's comments — asks here rather than rebuilding the
    marker itself.
    """
    return tuple(
        issue_numbers.get(milestone_marker(item.milestone.election_id, item.milestone.id), ())
    )


def plan_escalations(
    missing: Iterable[MissingArtifact],
    *,
    as_of: date,
    issue_numbers: Mapping[str, Sequence[int]],
    escalated: Mapping[int, frozenset[str]],
) -> list[EscalationRequest]:
    """Decide which escalations are missing from which tracking issues.

    Every issue carrying the milestone's marker is escalated, not one chosen
    among them. A marker is not unique in practice — this repository already
    holds five issues for one milestone — and picking one would leave the
    others looking untouched.

    A stage whose marker an issue already carries is skipped, which is what
    makes a schedule running four times a day comment once.
    """
    plan: list[EscalationRequest] = []
    for item in missing:
        milestone = item.milestone
        for number in tracked_issue_numbers(item, issue_numbers):
            posted = escalated.get(number, frozenset())
            for stage in item.stages:
                escalation = escalation_marker(milestone.election_id, milestone.id, stage)
                if escalation in posted:
                    continue
                plan.append(
                    EscalationRequest(
                        marker=escalation,
                        milestone=f"{milestone.election_id}/{milestone.id}",
                        stage=stage,
                        label=STAGE_LABELS[stage].name,
                        body=_escalation_body(item, stage, as_of=as_of),
                        issue_number=number,
                    )
                )
    return plan


def untracked_milestones(
    missing: Iterable[MissingArtifact], *, issue_numbers: Mapping[str, Sequence[int]]
) -> list[MissingArtifact]:
    """Missing artifacts whose milestone has no tracking issue to escalate.

    Opening one is `calendar track`'s job, and it deliberately refuses a
    milestone whose date has passed, so this reports the gap rather than
    creating work nobody can still do.
    """
    return [item for item in missing if not tracked_issue_numbers(item, issue_numbers)]


def read_repository_artifacts(
    *, manifest_dir: Path, refresh_dir: Path, authority_ids: frozenset[str] = frozenset()
) -> RepositoryArtifacts:
    """Read what the repository holds, reduced to what matching needs.

    Through each format's own reader, never a second parse of the same bytes.
    Re-deriving `availability` or `status` as string comparisons here would put
    a copy of those semantics in a file nobody edits when the models change,
    and both directions of that drift are the operator-visible failure this
    check exists to prevent: a discriminator this reader stops recognizing
    empties the repository and escalates completed work, and one it stops
    rejecting lets a failed refresh count as a landed one.

    A directory that does not exist reads as empty. A checkout that has
    captured nothing yet is a real state, not an error.
    """
    captures: list[CaptureRecord] = []
    for path in _artifact_files(manifest_dir, "capture-*.json"):
        manifest = read_capture_manifest(path)
        # Only a captured manifest is evidence the work landed. An unavailable
        # one records an attempt that found nothing, which is exactly the case
        # a human should still hear about.
        if not isinstance(manifest, CapturedManifest):
            continue
        captures.append(
            CaptureRecord(
                source_id=manifest.source_id,
                title=manifest.title or "",
                retrieved_at=manifest.retrieved_at,
            )
        )
    refreshes: list[datetime] = []
    for path in _artifact_files(refresh_dir, "refresh-*.json"):
        event = read_refresh_event(path)
        # A failed refresh is the record of a refresh that did not happen.
        if event.status == "failed":
            continue
        refreshes.append(event.checked_at)
    return RepositoryArtifacts(
        captures=tuple(captures), refreshes=tuple(refreshes), authority_ids=authority_ids
    )


def _artifact_files(directory: Path, pattern: str) -> list[Path]:
    return sorted(directory.glob(pattern)) if directory.is_dir() else []
