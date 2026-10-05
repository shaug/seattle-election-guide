"""Results ingest is required, recognized, and escalated through the calendar CLI."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import yaml
from typer.testing import CliRunner

from election_guide.calendar import EscalationRequest, read_election_calendar
from election_guide.calendar.github_tracker import GitHubIssueTracker, TrackedIssues
from election_guide.cli import app

PROJECT_ROOT = Path(__file__).parents[1]
CALENDAR_PATH = PROJECT_ROOT / "config/calendar/elections.yaml"
RESULTS_PATH = PROJECT_ROOT / "data/results/wa-2026-primary.yaml"
INGEST_MARKER = "calendar-milestone: wa-2026-primary/results-ingest"
runner = CliRunner()


def _calendar_path(tmp_path: Path, *, ingest_offset: int | None = 15) -> Path:
    raw: Any = yaml.safe_load(CALENDAR_PATH.read_text())
    raw["elections"] = [item for item in raw["elections"] if item["id"] == "wa-2026-primary"]
    raw["milestones"] = [
        item
        for item in raw["milestones"]
        if item["election_id"] == "wa-2026-primary" and item["kind"] != "results_ingest"
    ]
    if ingest_offset is not None:
        raw["milestones"].append(
            {
                "election_id": "wa-2026-primary",
                "id": "results-ingest",
                "kind": "results_ingest",
                "offset_days": ingest_offset,
            }
        )
    path = tmp_path / "calendar.yaml"
    path.write_text(yaml.safe_dump(raw))
    return path


def _watch(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    as_of: str = "2026-09-01",
    posted: list[EscalationRequest] | None = None,
) -> Any:
    def tracked(self: GitHubIssueTracker) -> TrackedIssues:
        return TrackedIssues(titles=(), issue_numbers={INGEST_MARKER: (411,)})

    def no_comments(self: GitHubIssueTracker, number: int) -> frozenset[str]:
        return frozenset()

    monkeypatch.setattr(GitHubIssueTracker, "read_tracked_issues", tracked)
    monkeypatch.setattr(GitHubIssueTracker, "read_escalation_markers", no_comments)

    def post(self: GitHubIssueTracker, request: EscalationRequest) -> None:
        if posted is None:
            raise AssertionError("a dry run must not post")
        posted.append(request)

    monkeypatch.setattr(GitHubIssueTracker, "escalate", post)
    return runner.invoke(
        app,
        [
            "calendar",
            "watch",
            str(_calendar_path(tmp_path)),
            *(["--dry-run"] if posted is None else []),
            "--as-of",
            as_of,
            "--manifest-dir",
            str(tmp_path / "manifests"),
            "--refresh-dir",
            str(tmp_path / "refreshes"),
            "--results-dir",
            str(tmp_path / "results"),
        ],
    )


def _results(tmp_path: Path, status: str, *, filename: str = "wa-2026-primary") -> None:
    raw: Any = yaml.safe_load(RESULTS_PATH.read_text())
    raw["status"] = status
    if status == "amended":
        raw["supersedes"] = raw["captures"][0]["evidence"]
    directory = tmp_path / "results"
    directory.mkdir()
    (directory / f"{filename}.yaml").write_text(yaml.safe_dump(raw))


def test_validate_names_an_election_missing_its_results_ingest(tmp_path: Path) -> None:
    result = runner.invoke(
        app, ["calendar", "validate", str(_calendar_path(tmp_path, ingest_offset=None))]
    )
    assert result.exit_code != 0
    assert "wa-2026-primary" in result.output
    assert "declares no results_ingest" in result.output


def test_validate_rejects_ingest_before_its_post_certification_capture(tmp_path: Path) -> None:
    result = runner.invoke(
        app, ["calendar", "validate", str(_calendar_path(tmp_path, ingest_offset=14))]
    )
    assert result.exit_code != 0
    assert "wa-2026-primary" in result.output
    assert "ingests results before its post-certification capture" in result.output


def test_committed_calendar_schedules_each_ingest_with_its_certified_capture() -> None:
    result = runner.invoke(app, ["calendar", "validate", str(CALENDAR_PATH)])
    assert result.exit_code == 0
    calendar = read_election_calendar(CALENDAR_PATH)
    for election in calendar.elections:
        milestones = calendar.election_milestones(election.id)
        ingests = [item for item in milestones if item.kind == "results_ingest"]
        captures = [
            item for item in milestones if item.kind == "results_capture_post_certification"
        ]
        assert len(ingests) == 1
        assert calendar.scheduled_date(ingests[0]) == calendar.scheduled_date(captures[0])
        assert ingests[0].workflow == "results ingest"
        assert ingests[0].reference == "docs/runbooks/results-certified-ingest.md"
        assert not ingests[0].public


def test_absent_results_escalate_the_ingest_on_its_tracking_issue(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    result = _watch(tmp_path, monkeypatch)
    assert result.exit_code == 0
    assert "would escalate: wa-2026-primary/results-ingest [overdue] on #411" in result.output


@pytest.mark.parametrize("status", ["certified", "amended"])
def test_a_published_results_file_satisfies_the_ingest(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    status: str,
) -> None:
    _results(tmp_path, status)
    result = _watch(tmp_path, monkeypatch)
    assert result.exit_code == 0
    assert "results-ingest" not in result.output


def test_counting_results_do_not_satisfy_the_ingest(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _results(tmp_path, "counting")
    result = _watch(tmp_path, monkeypatch)
    assert result.exit_code == 0
    assert "results-ingest [overdue] on #411" in result.output


def test_results_at_the_wrong_election_path_do_not_satisfy_ingest(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _results(tmp_path, "certified", filename="wa-2026-general")
    result = _watch(tmp_path, monkeypatch)
    assert result.exit_code == 0
    assert "results-ingest [overdue] on #411" in result.output


@pytest.mark.parametrize(("as_of", "escalates"), [("2026-08-26", False), ("2026-08-27", True)])
def test_ingest_keeps_the_existing_seven_day_escalation_window(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    as_of: str,
    escalates: bool,
) -> None:
    result = _watch(tmp_path, monkeypatch, as_of=as_of)
    assert result.exit_code == 0
    assert ("results-ingest [overdue]" in result.output) is escalates


def test_missing_ingest_posts_an_escalation_with_the_results_recognition_rule(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    posted: list[EscalationRequest] = []
    result = _watch(tmp_path, monkeypatch, posted=posted)
    assert result.exit_code == 0
    assert "escalated: wa-2026-primary/results-ingest [overdue] on #411" in result.output
    assert len(posted) == 1
    request = posted[0]
    assert request.issue_number == 411
    assert request.label == "escalation: overdue"
    assert "data/results/wa-2026-primary.yaml" in request.body
    assert "status `certified` or `amended`" in request.body
    assert "Stamped between" not in request.body
    assert request.body.endswith("calendar-escalation: wa-2026-primary/results-ingest overdue\n")
