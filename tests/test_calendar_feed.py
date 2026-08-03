"""Behavior tests for the subscribable election calendar feed."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import pytest

from election_guide.calendar import ElectionCalendar, read_election_calendar
from election_guide.publication.calendar_feed import (
    LINE_OCTET_LIMIT,
    MILESTONE_COPY,
    build_calendar_feed,
    milestone_uid,
)

PROJECT_ROOT = Path(__file__).parents[1]
CALENDAR_PATH = PROJECT_ROOT / "config" / "calendar" / "elections.yaml"
ORIGIN = "https://seattleelections.guide"
PUBLISHED_AT = datetime(2026, 8, 3, 17, 0, 0, tzinfo=UTC)
STAGED = ("wa-2027-general",)


def _milestone(**overrides: Any) -> dict[str, Any]:
    return {
        "election_id": "wa-2027-general",
        "id": "ballots-mail",
        "kind": "ballots_mail",
        "offset_days": -18,
    } | overrides


def _calendar(*milestones: dict[str, Any]) -> ElectionCalendar:
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
                _milestone(id="election-day", kind="election_day", offset_days=0),
                _milestone(
                    id="results-capture-election-night",
                    kind="results_capture_election_night",
                    offset_days=0,
                ),
                _milestone(
                    id="results-capture-post-certification",
                    kind="results_capture_post_certification",
                    offset_days=22,
                ),
                *milestones,
            ],
        }
    )


def _feed(calendar: ElectionCalendar, staged: tuple[str, ...] = STAGED) -> str:
    return build_calendar_feed(
        calendar,
        canonical_origin=ORIGIN,
        published_at=PUBLISHED_AT,
        published_election_ids=staged,
    )


def _public_election_day_event() -> list[str]:
    """Publish the election-day milestone the shared builder declares privately."""
    payload = _calendar().model_dump(mode="json")
    for milestone in payload["milestones"]:
        if milestone["kind"] == "election_day":
            milestone["public"] = True
    return _events(_feed(ElectionCalendar.model_validate(payload)))[0]


def _events(feed: str) -> list[list[str]]:
    events: list[list[str]] = []
    current: list[str] | None = None
    for line in feed.split("\r\n"):
        if line == "BEGIN:VEVENT":
            current = []
        elif line == "END:VEVENT" and current is not None:
            events.append(current)
            current = None
        elif current is not None:
            current.append(line)
    return events


def test_a_milestone_with_no_public_marking_is_absent() -> None:
    """Exclusion is by default, not by omission from a hand-maintained list."""
    feed = _feed(_calendar())

    assert _events(feed) == []


def test_only_publicly_marked_milestones_appear() -> None:
    feed = _feed(_calendar(_milestone(public=True)))

    uids = [line for event in _events(feed) for line in event if line.startswith("UID:")]
    assert uids == ["UID:wa-2027-general/ballots-mail@seattleelections.guide"]


def test_the_uid_is_derived_from_identity_and_not_from_the_date() -> None:
    """A UID that moved with the date would duplicate every subscriber's event."""
    early = _calendar(_milestone(public=True))
    late = _calendar(_milestone(public=True, offset_days=-25))

    assert milestone_uid(
        early.public_milestones()[0], origin_host="seattleelections.guide"
    ) == milestone_uid(late.public_milestones()[0], origin_host="seattleelections.guide")


def test_moving_a_date_changes_the_start_but_not_the_identity() -> None:
    before = _events(_feed(_calendar(_milestone(public=True))))[0]
    after = _events(_feed(_calendar(_milestone(public=True, offset_days=-25))))[0]

    uid = next(line for line in before if line.startswith("UID:"))
    assert uid in after
    assert "DTSTART;VALUE=DATE:20271015" in before
    assert "DTSTART;VALUE=DATE:20271008" in after


def test_the_revision_becomes_the_sequence() -> None:
    """A client treats a higher SEQUENCE as a revision of the same event."""
    first = _events(_feed(_calendar(_milestone(public=True))))[0]
    revised = _events(_feed(_calendar(_milestone(public=True, revision=3))))[0]

    assert "SEQUENCE:0" in first
    assert "SEQUENCE:2" in revised


def test_a_date_milestone_is_an_all_day_event() -> None:
    event = _events(_feed(_calendar(_milestone(public=True))))[0]

    assert "DTSTART;VALUE=DATE:20271015" in event
    # RFC 5545 all-day ranges are half-open, so the end is the following day.
    assert "DTEND;VALUE=DATE:20271016" in event


def test_dtstamp_converts_an_offset_rather_than_discarding_it() -> None:
    """The Z suffix asserts UTC, and DTSTAMP is the newer-version tiebreaker.

    Release timestamps come from commit dates, whose offsets are not uniform:
    locally authored commits carry -07:00 while merge commits carry +00:00. A
    stamp built from the wall clock could move backwards between releases and
    make a client keep the older event.
    """
    pacific = datetime(2026, 8, 3, 10, 14, 22, tzinfo=timezone(timedelta(hours=-7)))
    calendar = _calendar(_milestone(public=True))

    feed = build_calendar_feed(calendar, canonical_origin=ORIGIN, published_at=pacific)

    assert "DTSTAMP:20260803T171422Z" in feed
    assert "DTSTAMP:20260803T101422Z" not in feed
    # The same instant expressed in UTC must produce the same stamp.
    utc = build_calendar_feed(
        calendar, canonical_origin=ORIGIN, published_at=pacific.astimezone(UTC)
    )
    assert feed == utc


def test_a_naive_published_at_is_refused() -> None:
    """The Z suffix asserts UTC, so an unlabelled wall clock cannot carry it."""
    with pytest.raises(ValueError, match="timezone-aware"):
        build_calendar_feed(
            _calendar(_milestone(public=True)),
            canonical_origin=ORIGIN,
            published_at=datetime(2026, 8, 3, 17, 0, 0),
        )


def test_the_feed_declares_no_itip_method() -> None:
    """METHOD:PUBLISH would require an ORGANIZER (RFC 5546 3.2.1)."""
    feed = _feed(_calendar(_milestone(public=True)))

    assert "METHOD:" not in feed
    assert "ORGANIZER" not in feed


def test_the_uid_separator_cannot_collide_across_identities() -> None:
    """`/` is excluded by the ID pattern, so the join stays injective."""
    milestone = _calendar(_milestone(public=True)).public_milestones()[0]

    assert milestone_uid(milestone, origin_host="example.test") == (
        "wa-2027-general/ballots-mail@example.test"
    )


def test_election_day_omits_dtend_rather_than_repeating_dtstart() -> None:
    """RFC 5545 3.8.2.2 requires DTEND strictly later; 3.6.1 allows omitting it."""
    event = _public_election_day_event()

    assert any(line.startswith("DTSTART;TZID=") for line in event)
    assert not any(line.startswith("DTEND") for line in event)


def test_election_day_closes_at_eight_in_pacific_time() -> None:
    event = _public_election_day_event()

    assert "DTSTART;TZID=America/Los_Angeles:20271102T200000" in event


def test_the_feed_carries_the_timezone_a_client_needs() -> None:
    feed = _feed(_calendar(_milestone(public=True)))

    assert "BEGIN:VTIMEZONE" in feed
    assert "TZID:America/Los_Angeles" in feed
    assert "END:VTIMEZONE" in feed


def test_an_event_links_to_its_election_once_that_election_is_staged() -> None:
    event = _events(_feed(_calendar(_milestone(public=True))))[0]

    assert f"URL:{ORIGIN}/e/wa-2027-general/" in event


def test_an_unstaged_election_links_to_the_archive_rather_than_a_404() -> None:
    """The calendar declares elections years before the site serves them."""
    event = _events(_feed(_calendar(_milestone(public=True)), staged=()))[0]

    assert f"URL:{ORIGIN}/e/" in event
    assert f"URL:{ORIGIN}/e/wa-2027-general/" not in event


def test_a_public_milestone_with_no_copy_is_refused() -> None:
    """Better to fail the build than publish an untitled event to subscribers."""
    calendar = _calendar(
        _milestone(
            id="source-panel-freeze", kind="source_panel_freeze", offset_days=-60, public=True
        )
    )

    with pytest.raises(ValueError, match="no voter-facing copy"):
        _feed(calendar)


def test_the_feed_uses_crlf_and_terminates_its_last_line() -> None:
    feed = _feed(_calendar(_milestone(public=True)))

    assert feed.endswith("END:VCALENDAR\r\n")
    assert "\n" not in feed.replace("\r\n", "")


def test_no_content_line_exceeds_the_octet_limit() -> None:
    feed = _feed(_calendar(_milestone(public=True)))

    for line in feed.split("\r\n"):
        assert len(line.encode("utf-8")) <= LINE_OCTET_LIMIT, line


def test_text_values_are_escaped() -> None:
    feed = _feed(_calendar(_milestone(public=True)))

    # The description contains a comma, which RFC 5545 requires escaping.
    assert "\\," in feed


def test_two_builds_of_the_same_calendar_are_byte_identical() -> None:
    calendar = _calendar(_milestone(public=True))

    assert _feed(calendar).encode("utf-8") == _feed(calendar).encode("utf-8")


def test_the_committed_calendar_publishes_only_voter_facing_kinds() -> None:
    calendar = read_election_calendar(CALENDAR_PATH)

    published = {item.kind for item in calendar.public_milestones()}
    assert published == {"ballots_mail", "guide_publishes", "election_day"}
    assert published <= set(MILESTONE_COPY)


def test_every_voter_facing_milestone_is_marked_public() -> None:
    """A dropped marking deletes the event from every existing subscription."""
    calendar = read_election_calendar(CALENDAR_PATH)

    unmarked = [
        f"{item.election_id}/{item.id}"
        for item in calendar.milestones
        if item.kind in MILESTONE_COPY and not item.public
    ]
    assert unmarked == []


def test_the_committed_calendar_keeps_internal_milestones_private() -> None:
    calendar = read_election_calendar(CALENDAR_PATH)

    internal = {item.kind for item in calendar.milestones if not item.public}
    for kind in ("source_panel_freeze", "official_inventory_import", "retrospective"):
        assert kind in internal


def test_the_committed_calendar_renders_a_feed_with_one_event_per_public_milestone() -> None:
    calendar = read_election_calendar(CALENDAR_PATH)

    feed = _feed(calendar)

    assert len(_events(feed)) == len(calendar.public_milestones())
    assert len({line for event in _events(feed) for line in event if line.startswith("UID:")}) == (
        len(calendar.public_milestones())
    )
