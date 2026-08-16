"""What one archived day of zone analytics is allowed to contain.

Two datasets, because no single one answers the question (issue #381):

- `httpRequests1dGroups` is pre-aggregated and authoritative, and reaches back
  about thirty days. It carries totals, country, and edge status code — and no
  path or device-type breakdown at all.
- `httpRequestsAdaptiveGroups` carries path and device type, and is capped at
  **eight days**, enforced as a hard error rather than an empty answer. It is
  also sampled, so its counts are estimates.

So the daily dataset is the base every archived day is built from, and the
adaptive one enriches only the days still inside its much shorter window.
`sources` records which of the two actually answered, so a reader can tell a
day that predates the adaptive window from a day nobody looked at.

The exclusions are the other half of the point. This repository is public, so a
committed IP address or user-agent string would be permanent and unretractable
from every fork of it — which is why `extra="forbid"` is load-bearing here
rather than ordinary strictness. A future change that starts collecting an
identifying dimension has to delete that setting to store it, and deleting it
is a visible act in a diff.

That exclusion is structural, and deliberately not a scan of stored values.
Cloudflare offers `clientIP`, `userAgent`, `userAgentBrowser`, and
`userAgentOS`; none is ever requested, so no field here can hold one. A
value-shape screen on top of that would guard nothing real and would misfire on
the one grouping an outsider controls: `by_path` records the URL someone asked
for, so a scanner probing `/10.0.0.1/admin` — and 271 of the 640 paths archived
so far are probes of that kind — would trip an address-shaped pattern while
revealing nothing whatsoever about any visitor. A requester's choice of URL is
not a visitor's identity.
"""

from __future__ import annotations

from datetime import date

from pydantic import BaseModel, ConfigDict, Field, field_validator

# Named for the datasets themselves rather than for a friendly alias: a reader
# checking an archived day against Cloudflare's own documentation should not
# have to translate a nickname first.
SOURCE_DAILY = "httpRequests1dGroups"
SOURCE_ADAPTIVE = "httpRequestsAdaptiveGroups"


class AnalyticsModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class DimensionCount(AnalyticsModel):
    """One grouping's request count for a day — a path, a country, a status code.

    Requests only. The daily dataset's maps carry no visit count, and the
    adaptive dataset's per-dimension visits are sampled estimates, so a single
    uniform metric is both the honest choice and the comparable one.
    """

    key: str | int
    requests: int = Field(ge=0)


class DailyRollup(AnalyticsModel):
    """One complete UTC day, as archived.

    Every list is sorted on construction rather than by whoever writes the
    file. Re-running the export must leave an archived day byte-identical, and
    a sort that lives in the writer is a sort the next caller can forget.
    Heaviest first, because that is the order a human reads a top-list in; the
    key breaks ties so the order never depends on how Cloudflare happened to
    return the rows.

    The three optional fields are `None` — not empty — when the adaptive
    dataset did not cover this day. Empty would claim the site served no paths
    that day; `None` says the question was not answerable, which for any day
    older than eight is the truth.
    """

    schema_version: str = "1.0"
    date: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}$")
    sources: tuple[str, ...] = Field(min_length=1)
    requests: int = Field(ge=0)
    page_views: int = Field(ge=0)
    uniques: int = Field(ge=0)
    by_country: tuple[DimensionCount, ...]
    by_edge_status_code: tuple[DimensionCount, ...]
    visits: int | None = Field(default=None, ge=0)
    by_path: tuple[DimensionCount, ...] | None = None
    by_device_type: tuple[DimensionCount, ...] | None = None

    @classmethod
    def empty(cls, day: date) -> DailyRollup:
        """A day the zone served no traffic on.

        Distinct from a day that was never archived. A gap in the archive says
        "nobody looked"; a zero says "we looked, and there was nothing" — and
        only the second is a fact about the site.
        """
        return cls(
            date=day.isoformat(),
            sources=(SOURCE_DAILY,),
            requests=0,
            page_views=0,
            uniques=0,
            by_country=(),
            by_edge_status_code=(),
        )

    @field_validator("by_country", "by_edge_status_code", "by_path", "by_device_type")
    @classmethod
    def _ordered(
        cls, counts: tuple[DimensionCount, ...] | None
    ) -> tuple[DimensionCount, ...] | None:
        if counts is None:
            return None
        return tuple(sorted(counts, key=lambda count: (-count.requests, str(count.key))))
