"""The impure half: authenticated reads against Cloudflare's GraphQL API.

Read-only by construction — the GraphQL analytics endpoint exposes no mutation
this token could reach, and the token itself is scoped to Zone / Analytics /
Read (`docs/HOSTING.md`, credential inventory).

Kept apart from `window` and `storage` so that deciding what to fetch and
deciding what may be stored are both testable without a network or a
credential. `collection.http` is not reused here: it is a deliberately
hardened, unauthenticated GET path for public artifact capture, and widening it
to carry an Authorization header would weaken the one boundary it exists to
hold.
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any, cast

from election_guide.analytics.models import (
    SOURCE_ADAPTIVE,
    SOURCE_DAILY,
    DailyRollup,
    DimensionCount,
)

GRAPHQL_ENDPOINT = "https://api.cloudflare.com/client/v4/graphql"
TOKEN_VARIABLE = "CLOUDFLARE_ANALYTICS_TOKEN"
ZONE_VARIABLE = "CLOUDFLARE_ZONE_ID"

# Measured against this zone on 2026-08-16 by walking the boundary a day at a
# time: seven days back answered, eight days back returned a `quota` error
# reading "cannot request data older than 1w1d". It is a hard refusal, not an
# empty result, and it is why the adaptive dataset cannot carry this archive on
# its own (issue #381).
#
# Treated as a hint rather than a contract: the run skips days it expects to be
# refused, and still tolerates a refusal on days it expected to work, so a
# boundary that drifts costs a wasted request instead of a failed backfill.
ADAPTIVE_RETENTION_DAYS = 8

# Cloudflare caps a group at 10000 rows. Paths are the only grouping that could
# plausibly approach it; device type is bounded at three.
ROW_LIMIT = 10000

DAILY_QUERY = """
query ZoneDailyTotals($zoneTag: String!, $start: Date!, $end: Date!) {
  viewer {
    zones(filter: { zoneTag: $zoneTag }) {
      httpRequests1dGroups(limit: 1, filter: { date_geq: $start, date_lt: $end }) {
        sum {
          requests
          pageViews
          countryMap { clientCountryName requests }
          responseStatusMap { edgeResponseStatus requests }
        }
        uniq { uniques }
      }
    }
  }
}
"""

# `clientIP`, `userAgent`, `userAgentBrowser`, and `userAgentOS` all exist in
# this dataset and are deliberately absent from this query. This repository is
# public (issue #381, non-goals), and the cheapest place to enforce that is the
# request: nothing downstream has to filter, because nothing upstream asks.
ADAPTIVE_QUERY = """
query ZoneAdaptiveDetail($zoneTag: String!, $start: Time!, $end: Time!) {
  viewer {
    zones(filter: { zoneTag: $zoneTag }) {
      total: httpRequestsAdaptiveGroups(
        limit: 1
        filter: { datetime_geq: $start, datetime_lt: $end }
      ) {
        sum { visits }
      }
      byPath: httpRequestsAdaptiveGroups(
        limit: LIMIT
        filter: { datetime_geq: $start, datetime_lt: $end }
        orderBy: [count_DESC]
      ) {
        count
        dimensions { clientRequestPath }
      }
      byDeviceType: httpRequestsAdaptiveGroups(
        limit: LIMIT
        filter: { datetime_geq: $start, datetime_lt: $end }
        orderBy: [count_DESC]
      ) {
        count
        dimensions { clientDeviceType }
      }
    }
  }
}
""".replace("LIMIT", str(ROW_LIMIT))


@dataclass(frozen=True)
class DailyTotals:
    """What the thirty-day dataset can say about a day."""

    requests: int
    page_views: int
    uniques: int
    by_country: tuple[DimensionCount, ...]
    by_edge_status_code: tuple[DimensionCount, ...]


@dataclass(frozen=True)
class AdaptiveDetail:
    """What only the eight-day dataset can say about a day."""

    visits: int
    by_path: tuple[DimensionCount, ...]
    by_device_type: tuple[DimensionCount, ...]


@dataclass(frozen=True)
class CloudflareZone:
    """One zone's analytics, queried a day at a time."""

    zone_tag: str
    token: str
    timeout_seconds: float = 60

    def archive_day(self, day: date, *, as_of: date) -> DailyRollup | None:
        """One complete UTC day, enriched wherever the adaptive window still reaches.

        `None` means the daily dataset reported nothing, which is how both a
        day past retention and a day with genuinely no traffic answer. The
        caller decides which — see `cli.analytics_export`.
        """
        totals = self._daily_totals(day)
        if totals is None:
            return None
        detail = (
            self._adaptive_detail(day) if (as_of - day).days <= ADAPTIVE_RETENTION_DAYS else None
        )
        return DailyRollup(
            date=day.isoformat(),
            sources=(SOURCE_DAILY,) if detail is None else (SOURCE_DAILY, SOURCE_ADAPTIVE),
            requests=totals.requests,
            page_views=totals.page_views,
            uniques=totals.uniques,
            by_country=totals.by_country,
            by_edge_status_code=totals.by_edge_status_code,
            visits=None if detail is None else detail.visits,
            by_path=None if detail is None else detail.by_path,
            by_device_type=None if detail is None else detail.by_device_type,
        )

    def _daily_totals(self, day: date) -> DailyTotals | None:
        payload = self._post(
            DAILY_QUERY,
            {
                "zoneTag": self.zone_tag,
                "start": day.isoformat(),
                "end": (day + timedelta(days=1)).isoformat(),
            },
        )
        rows = _zone_field(payload, "httpRequests1dGroups")
        if not rows:
            return None
        row = _mapping(rows[0])
        total = _mapping(row.get("sum"))
        return DailyTotals(
            requests=_int(total.get("requests")),
            page_views=_int(total.get("pageViews")),
            uniques=_int(_mapping(row.get("uniq")).get("uniques")),
            by_country=_map_counts(total.get("countryMap"), "clientCountryName"),
            by_edge_status_code=_map_counts(total.get("responseStatusMap"), "edgeResponseStatus"),
        )

    def _adaptive_detail(self, day: date) -> AdaptiveDetail | None:
        """Path and device type, or `None` when the day is past the eight-day edge.

        A refused day is a normal outcome during a backfill, not a failure —
        every run reaching further back than eight days hits it — so the quota
        refusal is absorbed here rather than ending the run.
        """
        try:
            payload = self._post(
                ADAPTIVE_QUERY,
                {
                    "zoneTag": self.zone_tag,
                    "start": f"{day.isoformat()}T00:00:00Z",
                    "end": f"{(day + timedelta(days=1)).isoformat()}T00:00:00Z",
                },
            )
        except AnalyticsQuotaError:
            return None
        total = _zone_field(payload, "total")
        if not total:
            return None
        summary = _mapping(_mapping(total[0]).get("sum"))
        return AdaptiveDetail(
            visits=_int(summary.get("visits")),
            by_path=_grouped(_zone_field(payload, "byPath"), "clientRequestPath"),
            by_device_type=_grouped(_zone_field(payload, "byDeviceType"), "clientDeviceType"),
        )

    def _post(self, query: str, variables: dict[str, Any]) -> dict[str, Any]:
        request = urllib.request.Request(
            GRAPHQL_ENDPOINT,
            data=json.dumps({"query": query, "variables": variables}).encode("utf-8"),
            method="POST",
            headers={
                "Authorization": f"Bearer {self.token}",
                "Content-Type": "application/json",
                "User-Agent": (
                    "SeattleElectionGuide/0.1 (+https://github.com/shaug/seattle-election-guide)"
                ),
            },
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout_seconds) as response:
                content = response.read()
        except urllib.error.HTTPError as error:
            # The status alone, never the body: an error body can echo request
            # content, and this request carries a bearer token.
            raise ValueError(
                f"Cloudflare rejected the analytics request (HTTP {error.code}); "
                f"check that {TOKEN_VARIABLE} is current and scoped to Zone / Analytics / Read"
            ) from error
        except (OSError, urllib.error.URLError) as error:
            raise ValueError(f"could not reach the Cloudflare analytics API: {error}") from error
        try:
            document: Any = json.loads(content.decode("utf-8"))
        except (UnicodeError, json.JSONDecodeError) as error:
            raise ValueError("Cloudflare returned a response that is not JSON") from error
        if not isinstance(document, dict):
            raise ValueError("Cloudflare returned a response that is not an object")
        payload = cast(dict[str, Any], document)
        # GraphQL reports both authorization failures and retention refusals as
        # HTTP 200 carrying `errors`, so a run that only checked the status code
        # would read either as a day with no traffic and archive a zero.
        errors = payload.get("errors")
        if errors:
            if _is_quota(errors):
                raise AnalyticsQuotaError(_messages(errors))
            raise ValueError(
                f"Cloudflare analytics query failed: {_messages(errors)}; "
                f"check that {TOKEN_VARIABLE} is scoped to Zone / Analytics / Read"
            )
        return payload


class AnalyticsQuotaError(ValueError):
    """Cloudflare refused a day as older than the dataset retains.

    Distinct from every other failure because it is usually expected: it is how
    the adaptive dataset says "past my eight days", and a backfill reaching
    further back absorbs it rather than stopping.

    A `ValueError` so that the one path which does not absorb it — an explicit
    `--date` older than the adaptive window — still reaches the CLI's own
    handler and exits with the named-credential message instead of a traceback.
    """


def open_analytics_zone() -> CloudflareZone:
    """Build the client from the environment, failing before anything is written."""
    token = os.environ.get(TOKEN_VARIABLE, "").strip()
    if not token:
        raise ValueError(
            f"{TOKEN_VARIABLE} is not set; it must carry a Cloudflare API token scoped to "
            "Zone / Analytics / Read (docs/HOSTING.md, credential inventory)"
        )
    zone_tag = os.environ.get(ZONE_VARIABLE, "").strip()
    if not zone_tag:
        raise ValueError(
            f"{ZONE_VARIABLE} is not set; it must carry the zone id the "
            f"{TOKEN_VARIABLE} token reads (docs/HOSTING.md, credential inventory)"
        )
    return CloudflareZone(zone_tag=zone_tag, token=token)


def _is_quota(errors: Any) -> bool:
    if not isinstance(errors, list):
        return False
    return any(
        isinstance(entry, dict)
        and isinstance(extensions := cast(dict[str, Any], entry).get("extensions"), dict)
        and cast(dict[str, Any], extensions).get("code") == "quota"
        for entry in cast(list[Any], errors)
    )


def _messages(errors: Any) -> str:
    if not isinstance(errors, list):
        return "unreadable error payload"
    collected = [
        str(cast(dict[str, Any], entry).get("message", "")).strip()
        for entry in cast(list[Any], errors)
        if isinstance(entry, dict)
    ]
    return "; ".join(message for message in collected if message) or "no message given"


def _zone_field(payload: dict[str, Any], field: str) -> list[Any]:
    """One field of the single zone the query filtered to."""
    current: Any = payload
    for key in ("data", "viewer", "zones"):
        if not isinstance(current, dict):
            return []
        current = cast(dict[str, Any], current).get(key)
    if not isinstance(current, list) or not current:
        raise ValueError(
            f"Cloudflare returned no zone for {ZONE_VARIABLE}; check that the id names a "
            "zone this token can read"
        )
    zone = cast(list[Any], current)[0]
    if not isinstance(zone, dict):
        return []
    rows = cast(dict[str, Any], zone).get(field)
    return cast(list[Any], rows) if isinstance(rows, list) else []


def _int(value: Any) -> int:
    return value if isinstance(value, int) else 0


def _mapping(value: Any) -> dict[str, Any]:
    """One JSON object, or an empty one when the field is absent or malformed."""
    return cast(dict[str, Any], value) if isinstance(value, dict) else {}


def _map_counts(rows: Any, key_field: str) -> tuple[DimensionCount, ...]:
    """Counts from a daily-dataset map, whose key sits beside its metric."""
    if not isinstance(rows, list):
        return ()
    counts: list[DimensionCount] = []
    for entry in cast(list[Any], rows):
        if not isinstance(entry, dict):
            continue
        row = cast(dict[str, Any], entry)
        if key_field not in row:
            continue
        counts.append(DimensionCount(key=row[key_field], requests=_int(row.get("requests"))))
    return tuple(counts)


def _grouped(rows: list[Any], key_field: str) -> tuple[DimensionCount, ...]:
    """Counts from an adaptive group, whose key sits under `dimensions`."""
    counts: list[DimensionCount] = []
    for entry in rows:
        if not isinstance(entry, dict):
            continue
        row = cast(dict[str, Any], entry)
        dimensions = row.get("dimensions")
        if not isinstance(dimensions, dict):
            continue
        value = cast(dict[str, Any], dimensions).get(key_field)
        if value is None:
            continue
        counts.append(DimensionCount(key=value, requests=_int(row.get("count"))))
    return tuple(counts)
