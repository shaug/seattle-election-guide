"""Read and write the committed analytics archive.

Tracked, not ignored. `data/raw/`, `data/snapshots/`, and `data/imports/` are
gitignored, and an ignored path is exactly how the 2026-08-04 election-night
capture bytes were lost (issue #357): they verified at capture time and died
with the worktree that wrote them. An archive whose whole purpose is outliving
Cloudflare's 30-day window cannot live somewhere a `git clean` empties.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

from election_guide.analytics.models import DailyRollup
from election_guide.evidence.storage import write_immutable_record
from election_guide.serialization import canonical_json_bytes

ARCHIVE_DIR = Path("data/analytics")


def archive_path(archive_dir: Path, day: date) -> Path:
    """Where one UTC day lives. The filename is the identity."""
    return archive_dir / f"{day.isoformat()}.json"


def archived_dates(archive_dir: Path) -> frozenset[date]:
    """Every day already archived, read from the filenames themselves.

    A file that is not a plain `YYYY-MM-DD.json` is ignored rather than
    rejected: the answer this feeds is "what still needs fetching", and an
    unrecognized neighbour is not evidence about any particular day.
    """
    if not archive_dir.is_dir():
        return frozenset()
    days: set[date] = set()
    for path in archive_dir.glob("*.json"):
        try:
            days.add(date.fromisoformat(path.stem))
        except ValueError:
            continue
    return frozenset(days)


def write_rollup(archive_dir: Path, rollup: DailyRollup) -> Path:
    """Serialize one day deterministically and write it durably, once.

    `write_immutable_record` is the repository's own primitive for exactly this
    shape — one canonical record per filename, fsynced, installed exclusively,
    and refusing to replace existing bytes with different ones. Paired with
    `canonical_json_bytes`, the serializer every other authoritative record
    uses, it makes acceptance criterion 2 a property of the writer rather than
    a convention the caller has to remember: re-writing a day with identical
    bytes is accepted, and re-writing it with different bytes raises.

    Durability matters here because a partially written archive is worse than a
    missing one — the next run reads the filename, sees the day as done, and
    never repairs it.
    """
    destination = archive_path(archive_dir, date.fromisoformat(rollup.date))
    write_immutable_record(destination, canonical_json_bytes(rollup.model_dump(mode="json")))
    return destination
