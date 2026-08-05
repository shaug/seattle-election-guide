"""Behavior tests for turning calendar milestones into tracking issues."""

from __future__ import annotations

import json
import subprocess
from datetime import date
from itertools import pairwise
from pathlib import Path
from subprocess import CompletedProcess
from typing import Any

import pytest
from typer.testing import CliRunner

from election_guide.calendar import (
    ElectionCalendar,
    IssueRequest,
    due_milestones,
    milestone_marker,
    plan_issues,
    read_election_calendar,
)
from election_guide.calendar.github_tracker import (
    ISSUE_QUERY_LIMIT,
    GitHubIssueTracker,
    TrackedIssues,
    issue_records,
    markers_in_issues,
)
from election_guide.calendar.tracking import MARKER_PREFIX, unmarked_collisions
from election_guide.cli import app

PROJECT_ROOT = Path(__file__).parents[1]
CALENDAR_PATH = PROJECT_ROOT / "config" / "calendar" / "elections.yaml"


def _calendar() -> ElectionCalendar:
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
                    "workflow": "evidence capture",
                    "reference": "docs/EVIDENCE_CAPTURE.md",
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


def _plan(as_of: date, lead_days: int, existing: set[str] | None = None) -> list[IssueRequest]:
    return plan_issues(
        _calendar(),
        as_of=as_of,
        lead_days=lead_days,
        existing_markers=existing or set(),
    )


def test_a_due_milestone_produces_exactly_one_issue() -> None:
    plan = _plan(date(2027, 10, 14), 3)

    assert [request.title for request in plan] == ["wa-2027-general: ballots-mail due 2027-10-15"]


def test_the_issue_carries_the_election_the_date_and_the_required_action() -> None:
    request = _plan(date(2027, 11, 2), 0)[1]

    assert "wa-2027-general" in request.title
    assert "2027-11-02" in request.title
    assert "wa-2027-general" in request.body
    assert "2027-11-02" in request.body
    assert "Run `election-guide evidence capture`." in request.body
    assert "docs/EVIDENCE_CAPTURE.md" in request.body
    assert request.milestone == "wa-2027-general"
    assert request.labels == ("type: ops", "area: operations")


def test_a_milestone_with_no_workflow_says_so_rather_than_inventing_one() -> None:
    request = _plan(date(2027, 10, 14), 3)[0]

    assert "No pipeline command carries this milestone" in request.body
    assert "None recorded." in request.body


def test_a_second_run_creates_nothing() -> None:
    as_of = date(2027, 11, 2)
    first = _plan(as_of, 0)
    assert first

    already = {request.marker for request in first}
    assert _plan(as_of, 0, already) == []


def test_a_closed_issue_still_suppresses_a_duplicate() -> None:
    """existing_markers reads closed issues too; the plan must honor that."""
    as_of = date(2027, 11, 2)
    marker = milestone_marker("wa-2027-general", "election-day")

    remaining = _plan(as_of, 0, {marker})

    assert marker not in {request.marker for request in remaining}
    assert remaining


def test_the_marker_carries_no_date() -> None:
    """A moved milestone is still recognized, so it never gets a second issue."""
    assert milestone_marker("wa-2027-general", "ballots-mail") == (
        f"{MARKER_PREFIX} wa-2027-general/ballots-mail"
    )


def test_a_moved_milestone_is_skipped_rather_than_rewritten() -> None:
    """Creation is the only operation; the open issue keeps its original date."""
    marker = milestone_marker("wa-2027-general", "ballots-mail")
    opened = _plan(date(2027, 10, 14), 3)
    assert opened[0].marker == marker
    assert "2027-10-15" in opened[0].title

    # The same milestone, now reached on a different day inside its window.
    assert _plan(date(2027, 10, 13), 4, {marker}) == []


def test_a_past_milestone_is_not_due() -> None:
    plan = _plan(date(2027, 11, 3), 60)

    assert [request.title for request in plan] == [
        "wa-2027-general: results-capture-post-certification due 2027-11-24"
    ]


def test_the_window_is_inclusive_at_both_ends() -> None:
    assert _plan(date(2027, 10, 15), 0)
    assert _plan(date(2027, 10, 12), 3)
    assert _plan(date(2027, 10, 12), 2) == []


def test_a_negative_lead_window_is_rejected() -> None:
    with pytest.raises(ValueError, match="lead window cannot be negative"):
        due_milestones(_calendar(), as_of=date(2027, 1, 1), lead_days=-1)


def test_the_plan_is_ordered_by_date() -> None:
    scheduled = [
        scheduled
        for _, scheduled in due_milestones(_calendar(), as_of=date(2027, 10, 1), lead_days=120)
    ]

    assert scheduled == sorted(scheduled)
    assert [request.title.rsplit(" ", 1)[-1] for request in _plan(date(2027, 10, 1), 120)] == [
        item.isoformat() for item in scheduled
    ]


def test_every_planned_issue_embeds_its_own_marker() -> None:
    for request in _plan(date(2027, 10, 1), 120):
        assert request.body.rstrip().endswith(request.marker)


def test_markers_are_read_back_out_of_issue_bodies() -> None:
    """The round trip that makes a second run idempotent."""
    request = _plan(date(2027, 11, 2), 0)[0]
    payload = json.dumps([{"body": request.body}])

    assert markers_in_issues([body for _, body in issue_records(payload)]) == {request.marker}


def test_markers_ignores_an_issue_with_no_body() -> None:
    payload = '[{"body": null}, {"body": "no marker here"}]'
    assert markers_in_issues([body for _, body in issue_records(payload)]) == set()


def test_the_committed_calendar_plans_only_milestones_ahead_of_the_window() -> None:
    calendar = read_election_calendar(CALENDAR_PATH)

    plan = plan_issues(calendar, as_of=date(2026, 8, 3), lead_days=21, existing_markers=set())

    # Through 2026-08-24. The two 2026-08-04 milestones tie on date and break
    # by milestone ID; the two on 2026-08-20 break by election ID.
    assert [request.marker for request in plan] == [
        milestone_marker("wa-2026-primary", "election-day"),
        milestone_marker("wa-2026-primary", "results-capture-election-night"),
        milestone_marker("wa-2026-primary", "certification"),
        milestone_marker("wa-2026-general", "initialize-election"),
        milestone_marker("wa-2026-primary", "results-capture-post-certification"),
    ]
    # The general's inventory import is 2026-08-25, one day past the window.
    assert all("official-inventory-import" not in request.marker for request in plan)


def _completed(command: list[str], stdout: str = "", code: int = 0) -> CompletedProcess[str]:
    return CompletedProcess(command, code, stdout=stdout, stderr="")


def _nothing_tracked(self: GitHubIssueTracker) -> TrackedIssues:
    return TrackedIssues(markers=frozenset(), titles=())


def test_existing_markers_lists_by_label_across_open_and_closed_issues(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    recorded: dict[str, Any] = {}
    marker = milestone_marker("wa-2027-general", "election-day")

    def _run(command: list[str], **kwargs: Any) -> CompletedProcess[str]:
        recorded["command"] = command
        return _completed(command, json.dumps([{"body": f"anything\n{marker}\n"}]))

    monkeypatch.setattr(subprocess, "run", _run)

    assert GitHubIssueTracker("owner/repo").read_tracked_issues().markers == {marker}
    command = recorded["command"]
    assert command[:3] == ["gh", "issue", "list"]
    # Closed issues count, and the filter is the label rather than a text search.
    assert "--state" in command and command[command.index("--state") + 1] == "all"
    # Every issue, not a labelled subset: a generated issue that loses its
    # label must still be seen, or its milestone reopens on every run.
    assert "--label" not in command
    assert "--search" not in command
    # The body is what carries the marker back; any other field reads as empty.
    assert command[command.index("--json") + 1] == "title,body"
    assert str(ISSUE_QUERY_LIMIT) in command


def test_existing_markers_refuses_a_truncated_listing(monkeypatch: pytest.MonkeyPatch) -> None:
    """A dropped marker is a duplicate issue, so the read fails instead."""
    payload = json.dumps([{"body": "x"} for _ in range(ISSUE_QUERY_LIMIT)])

    def _run(command: list[str], **kwargs: Any) -> CompletedProcess[str]:
        return _completed(command, payload)

    monkeypatch.setattr(subprocess, "run", _run)

    with pytest.raises(ValueError, match="listing limit"):
        GitHubIssueTracker("owner/repo").read_tracked_issues()


def test_an_unlabelled_issue_still_suppresses_its_milestone(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Idempotence must not depend on anyone leaving a label alone."""
    marker = milestone_marker("wa-2027-general", "election-day")

    def _run(command: list[str], **kwargs: Any) -> CompletedProcess[str]:
        # An issue stripped of every label, carrying only its marker.
        return _completed(command, json.dumps([{"body": f"triaged\n\n{marker}"}]))

    monkeypatch.setattr(subprocess, "run", _run)

    assert GitHubIssueTracker("owner/repo").read_tracked_issues().markers == {marker}


def test_a_quoted_marker_does_not_suppress_a_milestone() -> None:
    """Only the last line counts, so discussing the system is safe."""
    marker = milestone_marker("wa-2027-general", "election-day")
    quoting = f"Every issue ends with a line like\n\n    {marker}\n\nwhich is its identity."

    assert markers_in_issues([quoting]) == set()
    assert markers_in_issues([f"{quoting}\n\n{marker}"]) == {marker}


def test_a_trailing_blank_line_does_not_hide_the_marker() -> None:
    marker = milestone_marker("wa-2027-general", "election-day")

    assert markers_in_issues([f"body\n\n{marker}\n\n"]) == {marker}


def test_create_attaches_the_milestone_and_every_label(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    commands: list[list[str]] = []

    def _run(command: list[str], **kwargs: Any) -> CompletedProcess[str]:
        commands.append(command)
        if "milestones" in " ".join(command) and "--method" not in command:
            return _completed(command, "wa-2027-general\n")
        return _completed(command, "https://github.com/owner/repo/issues/1\n")

    monkeypatch.setattr(subprocess, "run", _run)
    request = _plan(date(2027, 11, 2), 0)[0]

    assert GitHubIssueTracker("owner/repo").create(request) == (
        "https://github.com/owner/repo/issues/1"
    )
    # The milestone is resolved before the issue that attaches to it.
    assert "milestones" in " ".join(commands[0])
    create = commands[-1]
    assert create[:3] == ["gh", "issue", "create"]
    assert create[create.index("--milestone") + 1] == request.milestone
    # The body carries the marker; without it the next run duplicates the issue.
    assert create[create.index("--body") + 1] == request.body
    assert [create[i + 1] for i, part in enumerate(create) if part == "--label"] == list(
        request.labels
    )


def test_an_existing_milestone_is_not_recreated(monkeypatch: pytest.MonkeyPatch) -> None:
    commands: list[list[str]] = []

    def _run(command: list[str], **kwargs: Any) -> CompletedProcess[str]:
        commands.append(command)
        return _completed(command, "wa-2027-general\n")

    monkeypatch.setattr(subprocess, "run", _run)
    GitHubIssueTracker("owner/repo").ensure_milestone("wa-2027-general")

    assert len(commands) == 1
    assert "--method" not in commands[0]


def test_a_missing_milestone_is_created_once(monkeypatch: pytest.MonkeyPatch) -> None:
    commands: list[list[str]] = []

    def _run(command: list[str], **kwargs: Any) -> CompletedProcess[str]:
        commands.append(command)
        return _completed(command, "some-other-election\n")

    monkeypatch.setattr(subprocess, "run", _run)
    GitHubIssueTracker("owner/repo").ensure_milestone("wa-2027-general")

    assert commands[-1][:4] == ["gh", "api", "--method", "POST"]
    assert "title=wa-2027-general" in commands[-1]


def test_a_failing_cli_is_reported(monkeypatch: pytest.MonkeyPatch) -> None:
    def _run(command: list[str], **kwargs: Any) -> CompletedProcess[str]:
        return _completed(command, "", code=1)

    monkeypatch.setattr(subprocess, "run", _run)

    with pytest.raises(ValueError, match="could not list existing calendar issues"):
        GitHubIssueTracker("owner/repo").read_tracked_issues()


def test_a_missing_cli_is_reported(monkeypatch: pytest.MonkeyPatch) -> None:
    def _run(command: list[str], **kwargs: Any) -> CompletedProcess[str]:
        raise FileNotFoundError(command[0])

    monkeypatch.setattr(subprocess, "run", _run)

    with pytest.raises(ValueError, match="GitHub CLI is required"):
        GitHubIssueTracker("owner/repo").read_tracked_issues()


def test_a_malformed_issue_listing_is_rejected() -> None:
    with pytest.raises(ValueError, match="not an array"):
        issue_records(json.dumps({"body": "x"}))
    with pytest.raises(ValueError, match="not an object"):
        issue_records(json.dumps(["x"]))


def test_dry_run_prints_the_plan_and_creates_nothing(monkeypatch: pytest.MonkeyPatch) -> None:
    """The only guard between a dry run and real issues in the live repository."""

    def _never(self: GitHubIssueTracker, request: IssueRequest) -> str:
        raise AssertionError("a dry run must not create anything")

    monkeypatch.setattr(GitHubIssueTracker, "read_tracked_issues", _nothing_tracked)
    monkeypatch.setattr(GitHubIssueTracker, "create", _never)

    result = CliRunner().invoke(
        app,
        [
            "calendar",
            "track",
            str(CALENDAR_PATH),
            "--as-of",
            "2026-08-03",
            "--lead-days",
            "21",
            "--dry-run",
        ],
    )

    assert result.exit_code == 0
    assert result.stdout.count("would create: ") == 5
    assert "calendar tracking: 5 would be opened, window 21 days from 2026-08-03" in result.stdout


def test_a_real_run_creates_each_planned_issue(monkeypatch: pytest.MonkeyPatch) -> None:
    created: list[str] = []

    def _record(self: GitHubIssueTracker, request: IssueRequest) -> str:
        created.append(request.marker)
        return "issues/1"

    monkeypatch.setattr(GitHubIssueTracker, "read_tracked_issues", _nothing_tracked)
    monkeypatch.setattr(GitHubIssueTracker, "create", _record)

    result = CliRunner().invoke(
        app,
        ["calendar", "track", str(CALENDAR_PATH), "--as-of", "2026-08-03", "--lead-days", "21"],
    )

    assert result.exit_code == 0
    assert len(created) == 5
    assert "calendar tracking: 5 opened," in result.stdout


def test_the_workflow_runs_every_six_hours_off_the_hour() -> None:
    """A single daily attempt has no margin for a same-day milestone."""
    workflow = (PROJECT_ROOT / ".github" / "workflows" / "calendar.yml").read_text(encoding="utf-8")

    schedule = [line.strip() for line in workflow.splitlines() if "cron:" in line]
    assert len(schedule) == 1
    cron = schedule[0].split('"')[1]
    minute, hours = cron.split()[0], cron.split()[1]

    # Every day, so a weekly or monthly restriction cannot slip past.
    assert cron.split()[2:] == ["*", "*", "*"]

    # Off the hour: the top of the hour is GitHub's most congested slot.
    # Compared numerically, so "00" cannot pass where "0" would not.
    assert int(minute) != 0
    # Evenly spaced every six hours, so a dropped slot is covered soon.
    slots = sorted(int(hour) for hour in hours.split(","))
    assert len(slots) == 4
    assert {later - earlier for earlier, later in pairwise(slots)} == {6}
    assert (slots[0] + 24) - slots[-1] == 6


def _tracked(markers: set[str], titles: tuple[str, ...]) -> object:
    def _read(self: GitHubIssueTracker) -> TrackedIssues:
        return TrackedIssues(markers=frozenset(markers), titles=titles)

    return _read


def test_a_title_claiming_an_unmarked_milestone_is_a_collision() -> None:
    """The signals disagree, which means a marker went missing."""
    plan = _plan(date(2027, 10, 14), 3)
    assert plan

    collisions = unmarked_collisions(plan, ("wa-2027-general: ballots-mail due 2027-09-01",))

    assert [request.marker for request, _ in collisions] == [plan[0].marker]
    assert collisions[0][1] == "wa-2027-general: ballots-mail due 2027-09-01"


def test_an_unrelated_title_is_not_a_collision() -> None:
    plan = _plan(date(2027, 10, 14), 3)

    assert (
        unmarked_collisions(plan, ("Something else entirely", "wa-2027-general: refresh due x"))
        == []
    )


def test_a_copied_title_cannot_suppress_a_milestone(monkeypatch: pytest.MonkeyPatch) -> None:
    """A title never establishes tracking; it only reports a contradiction.

    The run stops rather than silently skipping, so a human who copied a
    generated title cannot quietly cost a milestone its reminder.
    """
    created: list[str] = []

    def _record(self: GitHubIssueTracker, request: IssueRequest) -> str:
        created.append(request.marker)
        return "issues/1"

    monkeypatch.setattr(
        GitHubIssueTracker,
        "read_tracked_issues",
        _tracked(set(), ("wa-2026-primary: election-day due 2026-08-04 — questions",)),
    )
    monkeypatch.setattr(GitHubIssueTracker, "create", _record)

    result = CliRunner().invoke(
        app,
        ["calendar", "track", str(CALENDAR_PATH), "--as-of", "2026-08-03", "--lead-days", "1"],
    )

    assert result.exit_code == 1
    assert "already claims that milestone but carries no readable marker" in result.output
    # The contradiction is reported, not silently swallowed: the milestone the
    # copied title claimed was skipped, and the other one was still opened.
    assert milestone_marker("wa-2026-primary", "election-day") not in created
    assert created == [milestone_marker("wa-2026-primary", "results-capture-election-night")]


def test_a_collision_skips_only_its_own_milestone(monkeypatch: pytest.MonkeyPatch) -> None:
    """One contradicted milestone must not cost the others their reminders."""
    created: list[str] = []

    def _record(self: GitHubIssueTracker, request: IssueRequest) -> str:
        created.append(request.marker)
        return "issues/1"

    monkeypatch.setattr(
        GitHubIssueTracker,
        "read_tracked_issues",
        _tracked(set(), ("wa-2026-primary: election-day due 2026-08-04",)),
    )
    monkeypatch.setattr(GitHubIssueTracker, "create", _record)

    result = CliRunner().invoke(
        app,
        ["calendar", "track", str(CALENDAR_PATH), "--as-of", "2026-08-03", "--lead-days", "21"],
    )

    assert result.exit_code == 1
    assert milestone_marker("wa-2026-primary", "election-day") not in created
    # The other four due milestones were still opened.
    assert len(created) == 4
    assert "4 opened" in result.output


def test_a_marked_milestone_never_reaches_the_collision_check(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A readable marker settles it; the title is never consulted."""
    # Both milestones fall on 2026-08-04, so both must be marked for the run
    # to have nothing left to do.
    marked = {
        milestone_marker("wa-2026-primary", "election-day"),
        milestone_marker("wa-2026-primary", "results-capture-election-night"),
    }

    def _never(self: GitHubIssueTracker, request: IssueRequest) -> str:
        raise AssertionError("nothing should be created")

    monkeypatch.setattr(
        GitHubIssueTracker,
        "read_tracked_issues",
        _tracked(marked, ("wa-2026-primary: election-day due 2026-08-04",)),
    )
    monkeypatch.setattr(GitHubIssueTracker, "create", _never)

    result = CliRunner().invoke(
        app,
        ["calendar", "track", str(CALENDAR_PATH), "--as-of", "2026-08-03", "--lead-days", "1"],
    )

    assert result.exit_code == 0
    assert "0 opened" in result.output
