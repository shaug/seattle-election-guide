"""Which days an export should fetch. Pure; nothing here reaches a network.

Deciding what is missing separately from fetching it is what makes the
scheduled run and the one-time backfill the same operation: both ask this for a
list and archive whatever comes back. A schedule that only ever fetched
"yesterday" would silently leave a hole behind every missed run, and a missed
run is the normal case — GitHub's schedules are best effort (`calendar.yml`).
"""

from __future__ import annotations

from collections.abc import Container
from datetime import date, timedelta

# Cloudflare's dashboard window for this account caps at 30 days, confirmed
# live on 2026-08-11 and recorded in `docs/MONITORING.md` ("Retention").
# Cloudflare publishes no plan-specific retention table for the
# `httpRequestsAdaptiveGroups` dataset, so this is the only figure confirmed
# for this account rather than a documented guarantee — which is the whole
# reason the archive exists (issue #381).
RETENTION_DAYS = 30


def window_floor(as_of: date) -> date:
    """The oldest UTC day the retention window still reaches.

    Defined here rather than at each use so that deciding what to fetch and
    judging what came back cannot drift apart. The export's empty-answer
    discriminator depends on both naming the same day, and two copies of the
    arithmetic would agree only until someone corrected one of them.
    """
    return as_of - timedelta(days=RETENTION_DAYS)


def newest_complete_day(as_of: date) -> date:
    """Yesterday — the newest day that is over and therefore countable.

    Today is still accumulating, and a day archived while in progress would
    record a partial count and never be revisited, because an archived day is
    never fetched again.
    """
    return as_of - timedelta(days=1)


def missing_dates(*, as_of: date, archived: Container[date]) -> list[date]:
    """Every in-window UTC day through yesterday that is not archived yet."""
    newest = newest_complete_day(as_of)
    oldest = window_floor(as_of)
    span = (newest - oldest).days + 1
    return [
        day
        for day in (oldest + timedelta(days=offset) for offset in range(span))
        if day not in archived
    ]
