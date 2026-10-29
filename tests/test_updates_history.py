"""The committed backfill follows actual publication dates, not merge dates."""

import hashlib
import json
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from election_guide.corrections.loader import load_rendering_corrections

PROJECT_ROOT = Path(__file__).resolve().parents[1]
UPDATES_DIR = PROJECT_ROOT / "data/corrections"
AUDIT_DIR = PROJECT_ROOT / "docs/audits/updates-2026-10-16"


def test_primary_has_a_publication_history() -> None:
    updates = load_rendering_corrections("wa-2026-primary", corrections_dir=UPDATES_DIR)

    assert updates is not None
    assert min(entry.corrected_on for entry in updates.entries) == date(2026, 7, 19)
    assert all(entry.provenance for entry in updates.entries)


@pytest.mark.parametrize(
    ("headline", "published_on"),
    [
        ("Updated King County Democrats\u2019 LD32 Position 2 endorsement.", date(2026, 10, 11)),
        ("Changed how sparse and unopposed races appear.", date(2026, 10, 12)),
    ],
)
def test_general_changes_use_their_first_publication_date(
    headline: str, published_on: date
) -> None:
    updates = load_rendering_corrections("wa-2026-general", corrections_dir=UPDATES_DIR)
    assert updates is not None

    entry = next(entry for entry in updates.entries if entry.headline == headline)

    assert entry.corrected_on == published_on


def test_general_history_starts_at_its_first_release() -> None:
    updates = load_rendering_corrections("wa-2026-general", corrections_dir=UPDATES_DIR)
    assert updates is not None

    assert min(entry.corrected_on for entry in updates.entries) == date(2026, 10, 3)


def _authored_entries() -> set[tuple[str, str, str]]:
    entries: set[tuple[str, str, str]] = set()
    for election in ("wa-2026-primary", "wa-2026-general"):
        updates = load_rendering_corrections(election, corrections_dir=UPDATES_DIR)
        assert updates is not None
        entries.update(
            (election, entry.corrected_on.isoformat(), entry.headline) for entry in updates.entries
        )
    return entries


def test_every_audited_change_is_bound_to_an_authored_entry() -> None:
    inventory = json.loads((AUDIT_DIR / "commit-inventory.json").read_text())
    commits = inventory["commits"]
    revisions = [row["commit"] for row in commits]
    authored = _authored_entries()

    assert len(revisions) == len(set(revisions)) == 283
    assert (
        hashlib.sha256(("\n".join(revisions) + "\n").encode()).hexdigest()
        == inventory["ordered_commit_sha256"]
    )
    for row in commits:
        assert row["disposition"] in {"logged", "excluded"}
        assert row["reason"]
        if row["disposition"] == "logged":
            assert row["entries"]
            for entry in row["entries"]:
                assert (entry["election_id"], entry["date"], entry["headline"]) in authored
        else:
            assert not row["entries"]


def test_audited_entry_dates_match_publication_evidence_in_pacific_time() -> None:
    publications = json.loads((AUDIT_DIR / "publications.json").read_text())
    authored = _authored_entries()
    timezone = ZoneInfo(publications["timezone"])

    assert publications["timezone"] == "America/Los_Angeles"
    assert len(publications["entries"]) == 39
    for entry in publications["entries"]:
        assert (entry["election_id"], entry["date"], entry["headline"]) in authored
        assert entry["publication_evidence"]
        for evidence in entry["publication_evidence"]:
            instant = datetime.fromisoformat(evidence["published_at"].replace("Z", "+00:00"))
            assert instant.utcoffset() is not None
            assert instant.astimezone(timezone).date().isoformat() == entry["date"]
            assert evidence["url"].startswith("https://github.com/shaug/seattle-election-guide/")


def test_minor_copy_announcement_is_audited_instead_of_publicly_announced() -> None:
    updates = load_rendering_corrections("wa-2026-general", corrections_dir=UPDATES_DIR)
    assert updates is not None
    assert not any(
        entry.headline == "Updated the Sources and Comparisons subheadings."
        for entry in updates.entries
    )

    audit = json.loads((PROJECT_ROOT / "docs/audits/minor-copy-updates-663.json").read_text())
    assert audit["source_revision"] == "ae819c57ef936d23eacf597fff518dd441e77ad1"
    assert audit["release"] == "2026-general.62"
    assert audit["authority"] == "https://github.com/shaug/seattle-election-guide/issues/663"
    assert audit["original_entry_sha256"] == (
        "f7da793c4b291f5862a13d0b1b656c709ef48c9e068747feac3e64f70c1367a7"
    )
    original = audit["original_entry"]
    assert original["corrected_on"] == "2026-10-28"
    assert original["headline"] == "Updated the Sources and Comparisons subheadings."
    encoded = json.dumps(original, sort_keys=True, separators=(",", ":")).encode()
    assert hashlib.sha256(encoded).hexdigest() == audit["original_entry_sha256"]
    prefix = [entry.model_dump(mode="json") for entry in updates.entries[:26]]
    encoded = json.dumps(prefix, sort_keys=True, separators=(",", ":")).encode()
    assert hashlib.sha256(encoded).hexdigest() == audit["preserved_public_prefix_sha256"]
