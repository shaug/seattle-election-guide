"""Explain expired interior dates without inventing zero-traffic rollups (#397)."""

from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path
from typing import Literal, Self

from pydantic import Field, model_validator

from election_guide.analytics.models import AnalyticsModel
from election_guide.analytics.storage import archived_dates
from election_guide.analytics.window import window_floor
from election_guide.evidence.storage import write_immutable_record
from election_guide.serialization import canonical_json_bytes


class ExpiredGap(AnalyticsModel):
    """Exact missing dates proven outside the configured window at observation."""

    schema_version: Literal["1.0"] = "1.0"
    dates: tuple[date, ...] = Field(min_length=1)
    reason: Literal["outside the retention window; traffic could not be recovered"]
    as_of: date
    window_floor: date

    @model_validator(mode="after")
    def validate_expiry(self) -> Self:
        if self.window_floor != window_floor(self.as_of):
            raise ValueError("gap window_floor must match the observation's retention window")
        if tuple(sorted(set(self.dates))) != self.dates:
            raise ValueError("gap dates must be sorted and unique")
        if any(day >= self.window_floor for day in self.dates):
            raise ValueError("gap dates must be older than the observation's retention window")
        return self


def _missing_interior_dates(days: frozenset[date]) -> frozenset[date]:
    if len(days) < 2:
        return frozenset()
    first, last = min(days), max(days)
    return frozenset(
        day
        for offset in range(1, (last - first).days)
        if (day := first + timedelta(days=offset)) not in days
    )


def _recorded_dates(archive_dir: Path) -> frozenset[date]:
    dates: set[date] = set()
    for path in sorted((archive_dir / "gaps").glob("*.json")):
        gap = ExpiredGap.model_validate_json(path.read_bytes())
        dates.update(gap.dates)
    return frozenset(dates)


def unexplained_dates(archive_dir: Path) -> frozenset[date]:
    """Missing interior dates not covered by valid, date-specific expiry evidence.

    Invalid evidence raises rather than silently accepting or ignoring it. The
    same check applies to the historical archive and a manual investigation.
    """
    return _missing_interior_dates(archived_dates(archive_dir)) - _recorded_dates(archive_dir)


def record_expired_gaps(archive_dir: Path, *, as_of: date) -> Path | None:
    """Persist newly proven expired dates once, separate from traffic records.

    Only holes bracketed by saved days count. A new investigation makes no claim
    about earlier history, and an empty API response within the configured
    window cannot prove expiry. Reruns preserve all previously written bytes.
    """
    floor = window_floor(as_of)
    dates = tuple(sorted(day for day in unexplained_dates(archive_dir) if day < floor))
    if not dates:
        return None
    gap = ExpiredGap(
        dates=dates,
        reason="outside the retention window; traffic could not be recovered",
        as_of=as_of,
        window_floor=floor,
    )
    path = archive_dir / "gaps" / f"{as_of}_{dates[0]}_{dates[-1]}.json"
    write_immutable_record(path, canonical_json_bytes(gap.model_dump(mode="json")))
    return path
