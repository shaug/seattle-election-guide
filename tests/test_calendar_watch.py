"""Behavior tests for escalating milestones whose artifact never appeared."""

from __future__ import annotations

import json
import subprocess
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from subprocess import CompletedProcess
from typing import Any
from zoneinfo import ZoneInfo

import pytest
from typer.testing import CliRunner

from election_guide.calendar import (
    ARTIFACT_WINDOW_DAYS,
    ELECTION_TIMEZONE,
    STAGE_LABELS,
    STALE_ESCALATION_DAYS,
    CaptureRecord,
    ElectionCalendar,
    EscalationRequest,
    RepositoryArtifacts,
    artifact_window,
    current_election_date,
    escalation_marker,
    milestone_marker,
    missing_artifacts,
    plan_escalations,
    read_election_calendar,
    read_repository_artifacts,
    untracked_milestones,
)
from election_guide.calendar.github_tracker import (
    LABEL_QUERY_LIMIT,
    GitHubIssueTracker,
    TrackedIssues,
)
from election_guide.cli import app
from election_guide.collection.models import RefreshEvent
from election_guide.evidence.models import (
    CaptureRequest,
    UnavailableRequest,
    evidence_fingerprint,
)
from election_guide.evidence.storage import record_capture, record_unavailable

PROJECT_ROOT = Path(__file__).parents[1]
CALENDAR_PATH = PROJECT_ROOT / "config" / "calendar" / "elections.yaml"

ELECTION_NIGHT_TITLE = "2027 Washington November General election-night results (King County CSV)"
CERTIFIED_TITLE = "2027 Washington November General certified results (King County CSV)"

_LABEL_LIST = ["gh", "label", "list"]


@pytest.fixture(autouse=True)
def forbid_subprocess(monkeypatch: pytest.MonkeyPatch) -> None:
    """Fail loudly rather than reaching GitHub.

    This module drives commands that comment on and label real issues, so
    nothing here may reach a subprocess by accident — the same guard
    `tests/test_calendar_tracking.py` carries, and for the same reason.
    """

    def _forbidden(*args: Any, **kwargs: Any) -> CompletedProcess[str]:
        raise AssertionError(
            f"a test reached subprocess.run{args[:1]}; stub GitHubIssueTracker "
            "or subprocess.run instead"
        )

    monkeypatch.setattr(subprocess, "run", _forbidden)


def _calendar() -> ElectionCalendar:
    """A general election on 2027-11-02 with the milestones this check reads."""
    return ElectionCalendar.model_validate(
        {
            "schema_version": "1.0",
            "elections": [
                {
                    "id": "wa-2027-general",
                    "election_type": "general",
                    "election_scope": "municipal",
                    "election_date": "2027-11-02",
                    "state": "WA",
                }
            ],
            "milestones": [
                {
                    "election_id": "wa-2027-general",
                    "id": "refresh-final",
                    "kind": "refresh",
                    "offset_days": -4,
                },
                {
                    "election_id": "wa-2027-general",
                    "id": "ballots-mail",
                    "kind": "ballots_mail",
                    "offset_days": -18,
                },
                {
                    "election_id": "wa-2027-general",
                    "id": "election-day",
                    "kind": "election_day",
                    "offset_days": 0,
                },
                {
                    "election_id": "wa-2027-general",
                    "id": "results-capture-election-night",
                    "kind": "results_capture_election_night",
                    "offset_days": 0,
                },
                {
                    "election_id": "wa-2027-general",
                    "id": "results-capture-post-certification",
                    "kind": "results_capture_post_certification",
                    "offset_days": 22,
                },
            ],
        }
    )


AUTHORITY_IDS = frozenset({"king-county-elections", "wa-secretary-of-state"})


def _capture(
    title: str, retrieved_at: str, *, source_id: str = "king-county-elections"
) -> CaptureRecord:
    return CaptureRecord(
        source_id=source_id, title=title, retrieved_at=datetime.fromisoformat(retrieved_at)
    )


def _artifacts(
    captures: tuple[CaptureRecord, ...] = (),
    refreshes: tuple[datetime, ...] = (),
) -> RepositoryArtifacts:
    return RepositoryArtifacts(captures=captures, refreshes=refreshes, authority_ids=AUTHORITY_IDS)


def _missing_ids(as_of: date, artifacts: RepositoryArtifacts | None = None) -> list[str]:
    missing = missing_artifacts(
        _calendar(), as_of=as_of, artifacts=artifacts if artifacts is not None else _artifacts()
    )
    return [item.milestone.id for item in missing]


def _stages(as_of: date, milestone_id: str) -> tuple[str, ...]:
    missing = missing_artifacts(_calendar(), as_of=as_of, artifacts=_artifacts())
    return next(item.stages for item in missing if item.milestone.id == milestone_id)


def test_a_milestone_still_inside_its_artifact_window_is_not_escalated() -> None:
    """An artifact can land a little late; the window is what makes it late."""
    closes = date(2027, 11, 2) + timedelta(days=ARTIFACT_WINDOW_DAYS)

    assert _missing_ids(date(2027, 11, 2)) == []
    assert "results-capture-election-night" not in _missing_ids(closes)


def test_a_past_due_milestone_with_no_artifact_reaches_the_overdue_stage() -> None:
    as_of = date(2027, 11, 2) + timedelta(days=ARTIFACT_WINDOW_DAYS + 1)

    assert "results-capture-election-night" in _missing_ids(as_of)
    assert _stages(as_of, "results-capture-election-night") == ("overdue",)


def test_a_long_past_milestone_reaches_every_stage_it_passed() -> None:
    """Stages do not depend on a run having happened at the right moment.

    A watcher that only ever emits the stage a milestone is in right now would
    skip `overdue` entirely whenever the schedule missed the window, which is
    the same silent pass this check exists to stop.
    """
    as_of = date(2027, 11, 2) + timedelta(days=STALE_ESCALATION_DAYS + 1)

    assert _stages(as_of, "results-capture-election-night") == ("overdue", "stale")


def test_the_run_counts_days_on_the_election_s_own_calendar() -> None:
    """Both halves of the comparison must use one calendar.

    The scheduled 03:17 UTC run lands at 19:17 Pacific the previous day. Read
    from UTC, it would already call that tomorrow and escalate a milestone with
    hours of window left — and they are the hours that matter, since King
    County publishes its first count around 8:15 p.m. Pacific.
    """
    run = datetime(2026, 11, 7, 3, 17, tzinfo=UTC)

    assert run.date() == date(2026, 11, 7)
    assert current_election_date(run) == date(2026, 11, 6)


def test_a_window_closing_tonight_is_not_escalated_from_a_utc_rollover() -> None:
    """The end-to-end shape of the same bug, at the boundary that bites."""
    closes = date(2027, 11, 2) + timedelta(days=ARTIFACT_WINDOW_DAYS)
    run = datetime(
        closes.year, closes.month, closes.day, 20, 15, tzinfo=ZoneInfo(ELECTION_TIMEZONE)
    )

    assert run.astimezone(UTC).date() > closes
    assert "results-capture-election-night" not in _missing_ids(current_election_date(run))


def test_a_kind_that_promises_no_checkable_artifact_is_never_escalated() -> None:
    """Ballot mailing and election day are dates, not work this check can verify."""
    as_of = date(2027, 12, 31)

    assert "ballots-mail" not in _missing_ids(as_of)
    assert "election-day" not in _missing_ids(as_of)


def test_a_matching_evidence_manifest_leaves_the_milestone_alone() -> None:
    """Captured at 10 p.m. Pacific, which is the next day in UTC."""
    as_of = date(2027, 12, 31)
    artifacts = _artifacts(captures=(_capture(ELECTION_NIGHT_TITLE, "2027-11-03T06:02:45Z"),))

    assert "results-capture-election-night" not in _missing_ids(as_of, artifacts)


def test_a_manifest_outside_the_window_does_not_satisfy_the_milestone() -> None:
    """The window is what ties a capture to one election rather than any."""
    as_of = date(2027, 12, 31)
    artifacts = _artifacts(captures=(_capture(ELECTION_NIGHT_TITLE, "2027-11-30T06:02:45Z"),))

    assert "results-capture-election-night" in _missing_ids(as_of, artifacts)


def test_a_certified_capture_does_not_satisfy_the_election_night_milestone() -> None:
    """The title's capture-kind phrase is the only thing separating the two.

    Evidence manifests carry no election or capture-kind field — a structured
    one was tried and reverted (`docs/EVIDENCE_CAPTURE.md`) — so the runbooks'
    title convention is what distinguishes a first count from a certified one.
    """
    as_of = date(2027, 12, 31)
    artifacts = _artifacts(captures=(_capture(CERTIFIED_TITLE, "2027-11-03T06:02:45Z"),))

    assert "results-capture-election-night" in _missing_ids(as_of, artifacts)


def test_a_certified_capture_satisfies_the_post_certification_milestone() -> None:
    as_of = date(2027, 12, 31)
    artifacts = _artifacts(captures=(_capture(CERTIFIED_TITLE, "2027-11-24T18:00:00Z"),))

    assert "results-capture-post-certification" not in _missing_ids(as_of, artifacts)


def test_a_refresh_event_in_the_window_satisfies_a_refresh_milestone() -> None:
    as_of = date(2027, 12, 31)
    artifacts = _artifacts(refreshes=(datetime(2027, 10, 29, 15, 0, tzinfo=UTC),))

    assert "refresh-final" not in _missing_ids(as_of, artifacts)
    assert "results-capture-election-night" in _missing_ids(as_of, artifacts)


def test_a_capture_in_the_window_also_satisfies_a_refresh_milestone() -> None:
    """A sweep leaves whichever record its sources allowed.

    `collect refresh` writes a refresh event, but most of the 2026 primary's
    panel was captured directly and left evidence manifests instead. Demanding
    the event alone would escalate a sweep that did happen.
    """
    as_of = date(2027, 12, 31)
    artifacts = _artifacts(
        captures=(
            _capture("The Stranger endorsements", "2027-10-30T15:00:00Z", source_id="the-stranger"),
        )
    )

    assert "refresh-final" not in _missing_ids(as_of, artifacts)


def test_a_capture_outside_the_refresh_window_does_not_satisfy_it() -> None:
    as_of = date(2027, 12, 31)
    artifacts = _artifacts(
        captures=(
            _capture("The Stranger endorsements", "2027-09-30T15:00:00Z", source_id="the-stranger"),
        )
    )

    assert "refresh-final" in _missing_ids(as_of, artifacts)


def test_an_election_night_capture_cannot_satisfy_the_final_refresh() -> None:
    """The two windows overlap, and both captures land in the same directory.

    A final refresh sits four days before election day, so its seven-day window
    contains election night. Matching a sweep on time alone would let the
    authority's results capture stand in for a sweep that never ran — which is
    the silent pass this check exists to stop.
    """
    as_of = date(2027, 12, 31)
    election_night = _capture(ELECTION_NIGHT_TITLE, "2027-11-03T06:02:45Z")
    assert artifact_window(date(2027, 10, 29)).contains(election_night.retrieved_at)

    assert "refresh-final" in _missing_ids(as_of, _artifacts(captures=(election_night,)))


def test_a_sweep_capture_cannot_satisfy_a_results_capture_milestone() -> None:
    """The same rule in the other direction: identity, not just timing."""
    as_of = date(2027, 12, 31)
    sweep = _capture(
        "The Stranger election-night results reaction",
        "2027-11-03T06:02:45Z",
        source_id="the-stranger",
    )

    assert "results-capture-election-night" in _missing_ids(as_of, _artifacts(captures=(sweep,)))


def test_a_certified_canvass_title_satisfies_the_post_certification_milestone() -> None:
    """The certified runbook pins no exact template, only "the certified status"."""
    as_of = date(2027, 12, 31)
    canvass = _capture(
        "2027 Washington November General certified canvass (King County abstract)",
        "2027-11-24T18:00:00Z",
    )

    assert "results-capture-post-certification" not in _missing_ids(
        as_of, _artifacts(captures=(canvass,))
    )


def test_a_milestone_whose_artifact_record_is_declared_is_left_alone() -> None:
    """The pre-#281 election-night capture is a document, not a manifest.

    Its bytes and manifests do not exist and cannot be reconstructed, so the
    milestone declares where its provenance actually lives. Escalating it would
    be escalating work that was done.
    """
    payload = _calendar().model_dump(mode="json")
    for milestone in payload["milestones"]:
        if milestone["id"] == "results-capture-election-night":
            milestone["artifact_record"] = "docs/runbooks/results-capture-election-night.md"
    calendar = ElectionCalendar.model_validate(payload)

    missing = missing_artifacts(calendar, as_of=date(2027, 12, 31), artifacts=_artifacts())

    assert "results-capture-election-night" not in [item.milestone.id for item in missing]
    assert "results-capture-post-certification" in [item.milestone.id for item in missing]


def _missing_election_night(as_of: date = date(2027, 12, 31)) -> Any:
    missing = missing_artifacts(_calendar(), as_of=as_of, artifacts=_artifacts())
    return [item for item in missing if item.milestone.id == "results-capture-election-night"]


def test_each_stage_is_planned_once_against_every_issue_carrying_the_marker() -> None:
    """A milestone's marker is not unique in practice — five duplicates of one
    already exist in this repository — and picking one arbitrarily would leave
    the others silently green."""
    marker = milestone_marker("wa-2027-general", "results-capture-election-night")

    plan = plan_escalations(
        _missing_election_night(),
        as_of=date(2027, 12, 31),
        issue_numbers={marker: (299, 327)},
        escalated={299: frozenset(), 327: frozenset()},
    )

    assert {(request.issue_number, request.stage) for request in plan} == {
        (299, "overdue"),
        (299, "stale"),
        (327, "overdue"),
        (327, "stale"),
    }


def test_an_existing_escalation_comment_suppresses_only_its_own_stage() -> None:
    """Idempotence: the marker a run wrote is the marker the next run reads."""
    marker = milestone_marker("wa-2027-general", "results-capture-election-night")
    already = escalation_marker("wa-2027-general", "results-capture-election-night", "overdue")

    plan = plan_escalations(
        _missing_election_night(),
        as_of=date(2027, 12, 31),
        issue_numbers={marker: (299,)},
        escalated={299: frozenset({already})},
    )

    assert [request.stage for request in plan] == ["stale"]


def test_a_fully_escalated_milestone_plans_nothing() -> None:
    marker = milestone_marker("wa-2027-general", "results-capture-election-night")
    posted = frozenset(
        escalation_marker("wa-2027-general", "results-capture-election-night", stage)
        for stage in ("overdue", "stale")
    )

    assert (
        plan_escalations(
            _missing_election_night(),
            as_of=date(2027, 12, 31),
            issue_numbers={marker: (299,)},
            escalated={299: posted},
        )
        == []
    )


def test_an_escalation_says_what_was_looked_for_and_ends_with_its_marker() -> None:
    marker = milestone_marker("wa-2027-general", "results-capture-election-night")

    plan = plan_escalations(
        _missing_election_night(),
        as_of=date(2027, 12, 31),
        issue_numbers={marker: (299,)},
        escalated={299: frozenset()},
    )
    overdue = next(request for request in plan if request.stage == "overdue")

    assert "evidence manifest" in overdue.body
    assert "election-night results" in overdue.body
    assert "2027-11-02" in overdue.body
    assert overdue.body.strip().endswith(
        escalation_marker("wa-2027-general", "results-capture-election-night", "overdue")
    )
    assert overdue.label == "escalation: overdue"


def test_a_milestone_with_no_tracking_issue_is_reported_rather_than_invented() -> None:
    """Opening the issue is `calendar track`'s job, and it refuses past dates."""
    missing = _missing_election_night()

    assert plan_escalations(missing, as_of=date(2027, 12, 31), issue_numbers={}, escalated={}) == []
    assert [item.milestone.id for item in untracked_milestones(missing, issue_numbers={})] == [
        "results-capture-election-night"
    ]


def _capture_metadata(**overrides: Any) -> dict[str, Any]:
    return {
        "source_id": "king-county-elections",
        "requested_url": "https://example.org/results",
        "canonical_url": "https://example.org/results",
        "retrieved_at": datetime(2027, 11, 3, 6, 2, 45, tzinfo=UTC),
        "media_type": "text/html",
        "title": ELECTION_NIGHT_TITLE,
        "redistribution": "permitted",
        "redistribution_note": "Official public record; bytes retained in the repository.",
    } | overrides


def _refresh_event(**fields: Any) -> RefreshEvent:
    """Build a refresh event carrying the content identity its reader demands."""
    timestamp = fields["checked_at"].astimezone(UTC).strftime("%Y%m%dT%H%M%SZ")
    prefix = f"refresh-{fields['source_id']}-{timestamp}-"
    draft = RefreshEvent(id=f"{prefix}000000000000", **fields)
    fingerprint = evidence_fingerprint(draft.model_dump(mode="json", exclude={"id"}))[:12]
    return RefreshEvent(id=f"{prefix}{fingerprint}", **fields)


def test_repository_artifacts_read_captured_manifests_and_successful_refreshes(
    tmp_path: Path,
) -> None:
    """Written by the real writers, so the reader is held to the real formats.

    Hand-written JSON would pass whatever this reader happens to accept; these
    records are the ones `evidence capture` and `collect refresh` actually
    produce.
    """
    manifest_dir = tmp_path / "manifests"
    refresh_dir = tmp_path / "refreshes"
    refresh_dir.mkdir()
    artifact = tmp_path / "results.html"
    artifact.write_text("<html>first count</html>", encoding="utf-8")

    record_capture(
        CaptureRequest(**_capture_metadata(), http_status=200, capture_method="static_html"),
        artifact,
        tmp_path / "snapshots",
        manifest_dir,
    )
    # An attempt that found nothing is not evidence the work landed.
    record_unavailable(
        UnavailableRequest(
            **_capture_metadata(title=None, media_type=None),
            unavailable_reason="The authority had published nothing yet.",
        ),
        manifest_dir,
    )
    for event in (
        _refresh_event(
            source_id="the-stranger",
            checked_at=datetime(2027, 10, 29, 15, 0, tzinfo=UTC),
            status="unchanged",
            content_changed=False,
            capture_id="capture-the-stranger-20271029T150000Z-000000000000",
            snapshot_id="extraction-the-stranger-20271029T150000Z-000000000000",
            previous_snapshot_id="extraction-the-stranger-20271029T150000Z-000000000000",
        ),
        # A failed refresh is the record of a refresh that did not happen.
        _refresh_event(
            source_id="the-stranger",
            checked_at=datetime(2027, 10, 29, 16, 0, tzinfo=UTC),
            status="failed",
            content_changed=None,
            error="the source did not respond",
        ),
    ):
        (refresh_dir / f"{event.id}.json").write_text(
            event.model_dump_json(indent=2), encoding="utf-8"
        )

    artifacts = read_repository_artifacts(manifest_dir=manifest_dir, refresh_dir=refresh_dir)

    assert [capture.title for capture in artifacts.captures] == [ELECTION_NIGHT_TITLE]
    assert artifacts.refreshes == (datetime(2027, 10, 29, 15, 0, tzinfo=UTC),)


def test_absent_artifact_directories_read_as_empty(tmp_path: Path) -> None:
    """A checkout that has captured nothing yet is a real state, not an error."""
    artifacts = read_repository_artifacts(
        manifest_dir=tmp_path / "nope", refresh_dir=tmp_path / "also-nope"
    )

    assert artifacts == RepositoryArtifacts(captures=(), refreshes=())


def _tracked(numbers: dict[str, tuple[int, ...]]) -> Any:
    def _read(self: GitHubIssueTracker) -> TrackedIssues:
        return TrackedIssues(titles=(), issue_numbers=dict(numbers))

    return _read


def _no_comments(self: GitHubIssueTracker, number: int) -> frozenset[str]:
    return frozenset()


def _watch(
    *extra: str, monkeypatch: pytest.MonkeyPatch, numbers: dict[str, tuple[int, ...]]
) -> Any:
    monkeypatch.setattr(GitHubIssueTracker, "read_tracked_issues", _tracked(numbers))
    monkeypatch.setattr(GitHubIssueTracker, "read_escalation_markers", _no_comments)
    return CliRunner().invoke(
        app, ["calendar", "watch", str(CALENDAR_PATH), "--as-of", "2026-08-31", *extra]
    )


def test_dry_run_prints_the_plan_and_posts_nothing(monkeypatch: pytest.MonkeyPatch) -> None:
    def _never(self: GitHubIssueTracker, request: EscalationRequest) -> None:
        raise AssertionError("a dry run must not escalate anything")

    monkeypatch.setattr(GitHubIssueTracker, "escalate", _never)
    marker = milestone_marker("wa-2026-primary", "results-capture-post-certification")

    result = _watch("--dry-run", monkeypatch=monkeypatch, numbers={marker: (302,)})

    assert result.exit_code == 0
    assert "would escalate: " in result.stdout
    assert "#302" in result.stdout
    assert "would be posted" in result.stdout


def test_a_real_run_escalates_each_planned_stage(monkeypatch: pytest.MonkeyPatch) -> None:
    escalated: list[tuple[int, str]] = []

    def _record(self: GitHubIssueTracker, request: EscalationRequest) -> None:
        escalated.append((request.issue_number, request.stage))

    monkeypatch.setattr(GitHubIssueTracker, "escalate", _record)
    marker = milestone_marker("wa-2026-primary", "results-capture-post-certification")

    result = _watch(monkeypatch=monkeypatch, numbers={marker: (302,)})

    assert result.exit_code == 0
    assert escalated == [(302, "overdue")]
    assert "escalated: " in result.stdout


def test_an_untracked_past_due_milestone_is_named_on_stderr(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def _never(self: GitHubIssueTracker, request: EscalationRequest) -> None:
        raise AssertionError("nothing should be escalated")

    monkeypatch.setattr(GitHubIssueTracker, "escalate", _never)

    result = _watch(monkeypatch=monkeypatch, numbers={})

    assert result.exit_code == 0
    assert "no tracking issue" in result.output


def test_the_committed_calendar_escalates_nothing_for_the_2026_primary() -> None:
    """The one past-due results capture this repository actually has.

    `wa-2026-primary`'s election-night capture ran on 2026-08-04 and produced a
    documented provenance record rather than manifests — the authority capture
    lane (#281) did not exist yet, and the bytes it would have backfilled from
    are gone. It is completed work, so the check must leave it alone.
    """
    calendar = read_election_calendar(CALENDAR_PATH)
    artifacts = read_repository_artifacts(
        manifest_dir=PROJECT_ROOT / "data" / "manifests" / "evidence",
        refresh_dir=PROJECT_ROOT / "data" / "collection" / "refreshes",
    )

    # Before the post-certification capture (2026-08-20) is itself past due,
    # so the only past-due milestone in the window is the election-night one.
    missing = missing_artifacts(calendar, as_of=date(2026, 8, 19), artifacts=artifacts)

    assert missing == []


def _completed(command: list[str], stdout: str = "") -> CompletedProcess[str]:
    return CompletedProcess(command, 0, stdout=stdout, stderr="")


def test_only_a_comments_trailing_line_counts_as_an_escalation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A human quoting a marker must not suppress a real escalation."""
    posted = escalation_marker("wa-2027-general", "results-capture-election-night", "overdue")
    comments = [
        {"body": f"why does {posted} keep showing up?"},
        {"body": f"## Outcome\n\nsomething\n\n{posted}\n"},
        {"body": "unrelated"},
    ]

    def _run(command: list[str], **kwargs: Any) -> CompletedProcess[str]:
        assert command[:3] == ["gh", "issue", "view"]
        assert command[command.index("--json") + 1] == "comments"
        return _completed(command, json.dumps({"comments": comments}))

    monkeypatch.setattr(subprocess, "run", _run)

    assert GitHubIssueTracker("owner/repo").read_escalation_markers(299) == {posted}


def test_escalating_labels_the_issue_before_it_comments(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A comment that landed under no label is the quiet outcome to avoid."""
    calls: list[list[str]] = []

    def _run(command: list[str], **kwargs: Any) -> CompletedProcess[str]:
        calls.append(command)
        return _completed(command, "escalation: overdue\n" if command[:3] == _LABEL_LIST else "")

    monkeypatch.setattr(subprocess, "run", _run)
    request = plan_escalations(
        _missing_election_night(),
        as_of=date(2027, 12, 31),
        issue_numbers={
            milestone_marker("wa-2027-general", "results-capture-election-night"): (299,)
        },
        escalated={299: frozenset()},
    )[0]

    GitHubIssueTracker("owner/repo").escalate(request)

    assert [command[:3] for command in calls] == [
        _LABEL_LIST,
        ["gh", "issue", "edit"],
        ["gh", "issue", "comment"],
    ]
    assert "--add-label" in calls[1]
    assert calls[1][calls[1].index("--add-label") + 1] == STAGE_LABELS["overdue"].name
    # Nothing here closes or reopens anything: the escalation is a label and a
    # comment, and the milestone's own issue stays whatever state a human left
    # it in.
    assert not any("close" in command or "reopen" in command for command in calls)


def test_a_missing_escalation_label_is_created_once(monkeypatch: pytest.MonkeyPatch) -> None:
    """`gh issue edit --add-label` fails on a label the repository lacks."""
    calls: list[list[str]] = []

    def _run(command: list[str], **kwargs: Any) -> CompletedProcess[str]:
        calls.append(command)
        return _completed(command, "some other label\n" if command[:3] == _LABEL_LIST else "")

    monkeypatch.setattr(subprocess, "run", _run)

    GitHubIssueTracker("owner/repo").ensure_label("escalation: stale")

    assert [command[:3] for command in calls] == [_LABEL_LIST, ["gh", "label", "create"]]
    assert "escalation: stale" in calls[1]
    # `gh label list` pages at 30 by default, newest last, and these two labels
    # are the newest — a truncated read would report an existing label absent,
    # `gh label create` would fail on it, and the run would die before posting
    # anything.
    assert calls[0][calls[0].index("--limit") + 1] == str(LABEL_QUERY_LIMIT)


def test_a_truncated_label_listing_fails_rather_than_recreating(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A dropped label is a failed run, so the read fails instead."""
    payload = "".join(f"label-{index}\n" for index in range(LABEL_QUERY_LIMIT))

    def _run(command: list[str], **kwargs: Any) -> CompletedProcess[str]:
        return _completed(command, payload)

    monkeypatch.setattr(subprocess, "run", _run)

    with pytest.raises(ValueError, match="label listing limit"):
        GitHubIssueTracker("owner/repo").ensure_label("escalation: stale")


def test_the_workflow_watches_after_it_tracks() -> None:
    """Both halves run on one schedule, and a tracking collision must not
    silence the watch: `track` exits non-zero on a contradicted title."""
    workflow = (PROJECT_ROOT / ".github" / "workflows" / "calendar.yml").read_text(encoding="utf-8")

    assert "calendar track" in workflow
    assert "calendar watch" in workflow
    assert workflow.index("calendar track") < workflow.index("calendar watch")
    assert "!cancelled()" in workflow
