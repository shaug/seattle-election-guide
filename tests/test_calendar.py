"""Schema and repository-data tests for the election operations calendar."""

from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError
from typer.testing import CliRunner

from election_guide.calendar import (
    REQUIRED_MILESTONE_KINDS,
    CalendarElection,
    CalendarMilestone,
    ElectionCalendar,
    read_election_calendar,
)
from election_guide.cli import app

PROJECT_ROOT = Path(__file__).parents[1]
CALENDAR_PATH = PROJECT_ROOT / "config" / "calendar" / "elections.yaml"

runner = CliRunner()


def _milestone(**overrides: Any) -> dict[str, Any]:
    return {
        "election_id": "wa-2027-general",
        "id": "election-day",
        "kind": "election_day",
        "offset_days": 0,
    } | overrides


def _required_milestones() -> list[dict[str, Any]]:
    return [
        _milestone(),
        _milestone(id="results-capture-election-night", kind="results_capture_election_night"),
        _milestone(
            id="results-capture-post-certification",
            kind="results_capture_post_certification",
            offset_days=22,
        ),
    ]


def _calendar(milestones: list[dict[str, Any]]) -> dict[str, Any]:
    return {
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
        "milestones": milestones,
    }


def test_committed_calendar_declares_the_2026_general_and_the_2027_cycle() -> None:
    calendar = read_election_calendar(CALENDAR_PATH)

    assert [election.id for election in calendar.elections] == [
        "wa-2026-primary",
        "wa-2026-general",
        "wa-2027-february-special",
        "wa-2027-april-special",
        "wa-2027-primary",
        "wa-2027-general",
    ]


def test_every_declared_election_captures_results_at_both_unrecoverable_windows() -> None:
    calendar = read_election_calendar(CALENDAR_PATH)

    for election in calendar.elections:
        kinds = {item.kind for item in calendar.election_milestones(election.id)}
        assert set(REQUIRED_MILESTONE_KINDS) <= kinds


def test_2026_primary_declares_only_the_windows_still_ahead_of_it() -> None:
    """Added after its runway passed, so its earlier milestones stay absent."""
    calendar = read_election_calendar(CALENDAR_PATH)

    milestones = calendar.election_milestones("wa-2026-primary")
    assert [item.kind for item in milestones] == [
        "election_day",
        "results_capture_election_night",
        "certification",
        "results_capture_post_certification",
    ]
    scheduled = {item.kind: calendar.scheduled_date(item) for item in milestones}
    assert scheduled["results_capture_election_night"] == date(2026, 8, 4)
    assert scheduled["results_capture_post_certification"] == date(2026, 8, 20)


def test_certification_date_resolves_the_certification_milestone() -> None:
    """#285's banner reads this to know when its counting window ends."""
    calendar = read_election_calendar(CALENDAR_PATH)

    assert calendar.certification_date("wa-2026-primary") == date(2026, 8, 19)
    assert calendar.certification_date("wa-2026-general") == date(2026, 11, 24)


def test_certification_date_is_none_without_a_declared_milestone() -> None:
    """An undeclared election id is not an error here -- callers with an
    election the calendar has not scheduled yet get a graceful `None`, the
    same way a committed results file's absence is a graceful `None`
    (`election_guide.results.loader.load_rendering_results`)."""
    calendar = read_election_calendar(CALENDAR_PATH)

    assert calendar.certification_date("not-a-declared-election") is None


def test_calendar_coverage_starts_at_the_soonest_election_day() -> None:
    calendar = read_election_calendar(CALENDAR_PATH)

    earliest = min(calendar.scheduled_date(item) for item in calendar.milestones)
    assert earliest == date(2026, 8, 4)


def test_2026_general_hands_initialization_to_the_election_init_workflow() -> None:
    calendar = read_election_calendar(CALENDAR_PATH)

    initialize = next(
        item
        for item in calendar.election_milestones("wa-2026-general")
        if item.kind == "initialize_election"
    )
    assert initialize.workflow == "election init"
    assert initialize.reference == "docs/ELECTION_INITIALIZATION.md"


def test_committed_milestones_name_workflows_the_cli_actually_exposes() -> None:
    calendar = read_election_calendar(CALENDAR_PATH)

    workflows = sorted({item.workflow for item in calendar.milestones if item.workflow is not None})
    assert workflows
    for workflow in workflows:
        result = runner.invoke(app, [*workflow.split(" "), "--help"])
        assert result.exit_code == 0, f"calendar names a missing workflow: {workflow}"


def test_every_retrospective_milestone_references_the_checklist() -> None:
    calendar = read_election_calendar(CALENDAR_PATH)

    retrospectives = [item for item in calendar.milestones if item.kind == "retrospective"]
    assert retrospectives
    for milestone in retrospectives:
        assert milestone.reference == "docs/POST_ELECTION_RETROSPECTIVE.md"


def test_the_general_endorsement_windows_reference_the_discovery_sweep_runbook() -> None:
    """The sweep is one procedure spanning three milestones (issue 292).

    `collection_opens` opens the window and each `refresh` re-runs it, so all
    three hand their work to the same runbook rather than to the CLI reference
    for `collect refresh` alone.
    """
    calendar = read_election_calendar(CALENDAR_PATH)

    windows = [
        item
        for item in calendar.election_milestones("wa-2026-general")
        if item.kind in {"collection_opens", "refresh"}
    ]
    assert [item.id for item in windows] == [
        "collection-opens",
        "refresh-mid-ballot",
        "refresh-final",
    ]
    for milestone in windows:
        assert milestone.workflow == "collect refresh"
        assert milestone.reference == "docs/runbooks/endorsement-discovery-sweep.md"


def test_committed_milestone_references_point_at_existing_documents() -> None:
    calendar = read_election_calendar(CALENDAR_PATH)

    for milestone in calendar.milestones:
        for path in (milestone.reference, milestone.artifact_record):
            if path is None:
                continue
            assert (PROJECT_ROOT / path).is_file(), path


@pytest.mark.parametrize(
    "artifact_record", ["/docs/RELEASE.md", "../secrets.yaml", "docs\\RELEASE.md"]
)
def test_artifact_record_outside_the_repository_fails_validation(artifact_record: str) -> None:
    payload = _calendar(_required_milestones())
    payload["milestones"][0]["artifact_record"] = artifact_record

    with pytest.raises(ValidationError, match="repository-relative path"):
        ElectionCalendar.model_validate(payload)


def test_calendar_schema_declares_no_presentation_fields() -> None:
    """D5 keeps the rendering seam open: identity and dates, never copy.

    `public` and `revision` were added for the calendar feed (issue 259) and do
    not cross that line. `public` says *whether* a reader should see a date, not
    what they see; the words live in `MILESTONE_COPY` on the rendering side.
    `revision` is a data version a subscriber's client compares, not anything
    displayed. `artifact_record` (issue 279) is a repository path, the same
    shape as `reference`, saying where a milestone's provenance actually
    landed. None of the three is a display string, banner semantic, or copy.
    """
    declared = set(CalendarElection.model_fields) | set(CalendarMilestone.model_fields)

    assert declared == {
        "public",
        "revision",
        "id",
        "election_type",
        "election_scope",
        "election_date",
        "state",
        "election_id",
        "kind",
        "offset_days",
        "workflow",
        "reference",
        "artifact_record",
    }


def test_scheduled_date_resolves_a_milestone_offset_against_its_election() -> None:
    calendar = read_election_calendar(CALENDAR_PATH)

    ballots_mail = next(
        item
        for item in calendar.election_milestones("wa-2026-general")
        if item.kind == "ballots_mail"
    )
    assert calendar.scheduled_date(ballots_mail) == date(2026, 10, 16)


@pytest.mark.parametrize(
    ("kind", "offset_days", "expected"),
    [
        ("ballots_mail", 4, "must fall before election day"),
        ("ballots_mail", 0, "must fall before election day"),
        ("election_day", -1, "must fall on election day"),
        ("results_capture_election_night", 1, "must fall on election day"),
        ("certification", 0, "must fall after election day"),
        ("retrospective", -30, "must fall after election day"),
    ],
)
def test_offset_must_agree_with_the_milestone_phase(
    kind: str, offset_days: int, expected: str
) -> None:
    payload = _calendar(
        [*_required_milestones(), _milestone(id="offending", kind=kind, offset_days=offset_days)]
    )

    with pytest.raises(ValidationError, match=expected):
        ElectionCalendar.model_validate(payload)


@pytest.mark.parametrize("offset_days", [-731, 366])
def test_offset_outside_the_planning_horizon_fails_validation(offset_days: int) -> None:
    payload = _calendar([*_required_milestones(), _milestone(id="offending", kind="refresh")])
    payload["milestones"][-1]["offset_days"] = offset_days

    with pytest.raises(ValidationError):
        ElectionCalendar.model_validate(payload)


def test_milestone_naming_an_undeclared_election_fails_validation() -> None:
    payload = _calendar([*_required_milestones(), _milestone(election_id="wa-2099-general")])

    with pytest.raises(ValidationError, match="name unknown election IDs"):
        ElectionCalendar.model_validate(payload)


def test_repeated_milestone_identity_fails_validation() -> None:
    payload = _calendar([*_required_milestones(), _milestone()])

    with pytest.raises(ValidationError, match="repeats milestones"):
        ElectionCalendar.model_validate(payload)


def test_repeated_election_identity_fails_validation() -> None:
    payload = _calendar(_required_milestones())
    payload["elections"] = [payload["elections"][0], dict(payload["elections"][0])]

    with pytest.raises(ValidationError, match="repeats election IDs"):
        ElectionCalendar.model_validate(payload)


def test_election_without_an_election_day_milestone_fails_validation() -> None:
    payload = _calendar([item for item in _required_milestones() if item["id"] != "election-day"])

    with pytest.raises(ValidationError, match="exactly one election-day milestone"):
        ElectionCalendar.model_validate(payload)


def test_election_with_two_election_day_milestones_fails_validation() -> None:
    payload = _calendar([*_required_milestones(), _milestone(id="election-day-again")])

    with pytest.raises(ValidationError, match="exactly one election-day milestone"):
        ElectionCalendar.model_validate(payload)


def test_election_without_a_results_capture_milestone_fails_validation() -> None:
    payload = _calendar(
        [
            item
            for item in _required_milestones()
            if item["kind"] != "results_capture_post_certification"
        ]
    )

    with pytest.raises(ValidationError, match="declares no results_capture_post_certification"):
        ElectionCalendar.model_validate(payload)


def test_capturing_certified_results_before_certification_fails_validation() -> None:
    payload = _calendar(
        [
            *_required_milestones(),
            _milestone(id="certification", kind="certification", offset_days=30),
        ]
    )

    with pytest.raises(ValidationError, match="captures certified results before certification"):
        ElectionCalendar.model_validate(payload)


@pytest.mark.parametrize("reference", ["/docs/RELEASE.md", "../secrets.yaml", "docs\\RELEASE.md"])
def test_reference_outside_the_repository_fails_validation(reference: str) -> None:
    payload = _calendar(_required_milestones())
    payload["milestones"][0]["reference"] = reference

    with pytest.raises(ValidationError, match="repository-relative path"):
        ElectionCalendar.model_validate(payload)


def test_undeclared_field_fails_validation() -> None:
    payload = _calendar(_required_milestones())
    payload["milestones"][0]["title"] = "Election Day"

    with pytest.raises(ValidationError):
        ElectionCalendar.model_validate(payload)


def test_calendar_validate_reports_the_declared_span() -> None:
    result = runner.invoke(app, ["calendar", "validate", str(CALENDAR_PATH)])

    assert result.exit_code == 0
    assert "election calendar: valid (6 elections" in result.stdout
    assert "2026-08-04 through 2027-12-02" in result.stdout


def test_calendar_validate_rejects_an_invalid_calendar(tmp_path: Path) -> None:
    invalid = tmp_path / "elections.yaml"
    invalid.write_text("schema_version: '1.0'\nelections: []\nmilestones: []\n", encoding="utf-8")

    result = runner.invoke(app, ["calendar", "validate", str(invalid)])

    assert result.exit_code == 1
