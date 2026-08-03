"""Render the public election calendar as a subscribable iCalendar feed.

The voter-facing words live here, keyed by milestone kind, and not in
`config/calendar/elections.yaml`. Decision D5 keeps the calendar free of display
strings so it stays a planning artifact; this module is the rendering side that
seam was left open for.

The output is deterministic. Nothing here reads the clock, so two builds of the
same calendar produce identical bytes, and a subscriber's client sees a revision
only when the declared data actually changed.
"""

from __future__ import annotations

from collections.abc import Collection
from dataclasses import dataclass
from datetime import UTC, datetime, time, timedelta

from election_guide.calendar.models import CalendarMilestone, ElectionCalendar, MilestoneKind

# RFC 5545 §3.1: lines are folded at 75 octets, continued with one leading
# space. Clients reject longer lines, and Google is stricter than Apple.
LINE_OCTET_LIMIT = 75

FEED_PRODUCT_ID = "-//Seattle Election Guide//Election Calendar//EN"
FEED_NAME = "Seattle election dates"
FEED_DESCRIPTION = (
    "Ballot mailing, publication, and election day for elections covered by the "
    "Seattle Election Guide."
)

# Washington counts ballots on Pacific time, and a subscriber in another zone
# must still see the deadline at the hour it actually falls.
FEED_TIMEZONE = "America/Los_Angeles"

# Drop boxes and in-person voting close at 8:00 p.m. on election day. Every
# other public milestone is a whole day.
BALLOT_DEADLINE = time(20, 0)


@dataclass(frozen=True)
class MilestoneCopy:
    """What a reader sees for one kind of milestone."""

    summary: str
    description: str


# Keyed by milestone kind, so a renamed milestone ID does not silently change a
# subscriber's event text and an unmarked kind cannot leak untitled.
MILESTONE_COPY: dict[MilestoneKind, MilestoneCopy] = {
    "ballots_mail": MilestoneCopy(
        summary="Ballots are mailed",
        description=(
            "King County Elections mails ballots today. Watch for yours, and "
            "check your registration if it does not arrive within a few days."
        ),
    ),
    "guide_publishes": MilestoneCopy(
        summary="Voter guide is published",
        description=(
            "The Seattle Election Guide's endorsement consensus for this election is available."
        ),
    ),
    "election_day": MilestoneCopy(
        summary="Election day — ballots due by 8:00 p.m.",
        description=(
            "Drop boxes close and in-person voting ends at 8:00 p.m. A mailed "
            "ballot must be postmarked today."
        ),
    ),
}


def _escape(value: str) -> str:
    """Escape a text value per RFC 5545 §3.3.11."""
    return value.replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,").replace("\n", "\\n")


def _fold(line: str) -> list[str]:
    """Fold one content line to the octet limit, continuing with a space."""
    encoded = line.encode("utf-8")
    if len(encoded) <= LINE_OCTET_LIMIT:
        return [line]
    folded: list[str] = []
    remaining = encoded
    limit = LINE_OCTET_LIMIT
    while len(remaining) > limit:
        cut = limit
        # Never split a multi-byte character across a fold.
        while cut > 0 and (remaining[cut] & 0xC0) == 0x80:
            cut -= 1
        folded.append(remaining[:cut].decode("utf-8"))
        remaining = remaining[cut:]
        limit = LINE_OCTET_LIMIT - 1
    folded.append(remaining.decode("utf-8"))
    return [folded[0]] + [f" {piece}" for piece in folded[1:]]


def milestone_uid(milestone: CalendarMilestone, *, origin_host: str) -> str:
    """Build the stable identity a subscriber's client updates in place.

    Derived from election and milestone identity and nothing else. A UID that
    moved with the date would give every existing subscriber a second event
    instead of a corrected one, which is the single worst thing this feed can
    do.
    """
    # `/` is excluded by ID_PATTERN, so the join is injective over valid
    # identity pairs; a `-` join could collapse two distinct milestones into
    # one event. This is also the key the calendar's own uniqueness validator
    # uses. It can only be changed before the first publish: afterwards, every
    # subscriber holds these UIDs.
    return f"{milestone.election_id}/{milestone.id}@{origin_host}"


def _timestamp(moment: datetime) -> str:
    return moment.strftime("%Y%m%dT%H%M%S")


def _utc_stamp(moment: datetime) -> str:
    """Format an instant as UTC, converting rather than discarding an offset.

    DTSTAMP's `Z` suffix asserts UTC. It is also the tiebreaker a client uses
    to decide which version of a UID is newer, so a stamp built from a local
    wall clock could move backwards between releases and make a subscriber
    keep the older event.
    """
    if moment.tzinfo is None:
        raise ValueError("published_at must be timezone-aware; a naive time cannot be stamped UTC")
    return _timestamp(moment.astimezone(UTC).replace(tzinfo=None))


def _event_lines(
    calendar: ElectionCalendar,
    milestone: CalendarMilestone,
    *,
    origin: str,
    origin_host: str,
    dtstamp: str,
    published_election_ids: Collection[str],
) -> list[str]:
    copy = MILESTONE_COPY[milestone.kind]
    scheduled = calendar.scheduled_date(milestone)
    lines = [
        "BEGIN:VEVENT",
        f"UID:{milestone_uid(milestone, origin_host=origin_host)}",
        f"DTSTAMP:{dtstamp}Z",
        f"SEQUENCE:{milestone.revision - 1}",
    ]
    if milestone.kind == "election_day":
        start = datetime.combine(scheduled, BALLOT_DEADLINE)
        # No DTEND: RFC 5545 3.8.2.2 requires it to be strictly later than
        # DTSTART, and 3.6.1 already defines a timed event without one as
        # ending at the same instant — which is exactly this deadline.
        lines.append(f"DTSTART;TZID={FEED_TIMEZONE}:{_timestamp(start)}")
    else:
        lines += [
            f"DTSTART;VALUE=DATE:{scheduled.strftime('%Y%m%d')}",
            f"DTEND;VALUE=DATE:{(scheduled + timedelta(days=1)).strftime('%Y%m%d')}",
        ]
    # The calendar declares elections years before they are published, so a
    # per-election link is only offered once that election is actually staged.
    # Otherwise the archive index, which always exists. A link a subscriber
    # cannot follow is worse than one more click.
    href = (
        f"{origin}/e/{milestone.election_id}/"
        if milestone.election_id in published_election_ids
        else f"{origin}/e/"
    )
    lines += [
        f"SUMMARY:{_escape(copy.summary)}",
        f"DESCRIPTION:{_escape(copy.description)}",
        f"URL:{href}",
        "TRANSP:TRANSPARENT",
        "END:VEVENT",
    ]
    return lines


def _timezone_lines() -> list[str]:
    """The VTIMEZONE Apple and Google need to place a timed event correctly."""
    return [
        "BEGIN:VTIMEZONE",
        f"TZID:{FEED_TIMEZONE}",
        "BEGIN:DAYLIGHT",
        "TZOFFSETFROM:-0800",
        "TZOFFSETTO:-0700",
        "TZNAME:PDT",
        "DTSTART:19700308T020000",
        "RRULE:FREQ=YEARLY;BYMONTH=3;BYDAY=2SU",
        "END:DAYLIGHT",
        "BEGIN:STANDARD",
        "TZOFFSETFROM:-0700",
        "TZOFFSETTO:-0800",
        "TZNAME:PST",
        "DTSTART:19701101T020000",
        "RRULE:FREQ=YEARLY;BYMONTH=11;BYDAY=1SU",
        "END:STANDARD",
        "END:VTIMEZONE",
    ]


def build_calendar_feed(
    calendar: ElectionCalendar,
    *,
    canonical_origin: str,
    published_at: datetime,
    published_election_ids: Collection[str] = (),
) -> str:
    """Render every publicly marked milestone as an RFC 5545 calendar.

    `published_at` is supplied rather than read from the clock so the feed is
    reproducible; pass the release's deterministic build timestamp.

    `published_election_ids` is the set of elections the site actually serves.
    An event for an election that is not staged yet links to the archive index
    instead of a page that would 404.
    """
    origin = canonical_origin.rstrip("/")
    origin_host = origin.removeprefix("https://").removeprefix("http://")

    public = calendar.public_milestones()
    dtstamp = _utc_stamp(published_at)

    unrenderable = sorted({item.kind for item in public if item.kind not in MILESTONE_COPY})
    if unrenderable:
        raise ValueError(
            f"public milestones have no voter-facing copy: {unrenderable}; add it to "
            "MILESTONE_COPY or unmark the milestone"
        )

    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        f"PRODID:{FEED_PRODUCT_ID}",
        "CALSCALE:GREGORIAN",
        f"X-WR-CALNAME:{_escape(FEED_NAME)}",
        f"X-WR-CALDESC:{_escape(FEED_DESCRIPTION)}",
        f"X-WR-TIMEZONE:{FEED_TIMEZONE}",
        *_timezone_lines(),
    ]
    for milestone in public:
        lines += _event_lines(
            calendar,
            milestone,
            origin=origin,
            origin_host=origin_host,
            dtstamp=dtstamp,
            published_election_ids=published_election_ids,
        )
    lines.append("END:VCALENDAR")

    folded = [piece for line in lines for piece in _fold(line)]
    # RFC 5545 §3.1: CRLF line endings, and the final line is terminated too.
    return "".join(f"{piece}\r\n" for piece in folded)
