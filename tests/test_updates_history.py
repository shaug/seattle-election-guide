"""The committed backfill follows actual publication dates, not merge dates."""

import hashlib
import json
import re
from datetime import date, datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import pytest
import yaml

from election_guide.corrections.loader import load_rendering_corrections
from election_guide.serialization import read_yaml

PROJECT_ROOT = Path(__file__).resolve().parents[1]
UPDATES_DIR = PROJECT_ROOT / "data/corrections"
AUDIT_DIR = PROJECT_ROOT / "docs/audits/updates-2026-10-16"
PRESENTATION_MIGRATION = PROJECT_ROOT / "docs/audits/updates-728/presentation.json"


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
    # Old audits bind authored history, including originals now retained internally.
    migration = json.loads(
        (PROJECT_ROOT / "docs/audits/updates-676/classification.json").read_text()
    )
    entries.update((row["election_id"], *row["identity"]) for row in migration["entries"])
    return entries


def test_election_only_migration_preserves_every_complete_original() -> None:
    audit_dir = PROJECT_ROOT / "docs/audits/updates-676"
    audit = json.loads((audit_dir / "classification.json").read_text())
    assert audit["source_revision"] == "79ebdd7811599d9073b5eaa5de6097f415aead39"
    assert len(audit["entries"]) == 66
    original_hashes = {
        "wa-2026-general": "26db6352d9773f693db813a246897654067e1fbbdc5b5ca45232a5161cad3964",
        "wa-2026-primary": "8230910341e2af3c458eb164ff0cd49787b9470d9cfef26ee8dee350f8a9514f",
    }
    for original_file in audit["original_files"]:
        election = Path(original_file["path"]).stem
        original = audit_dir / f"original-{election}.yaml"
        assert original_file["sha256"] == original_hashes[election]
        assert hashlib.sha256(original.read_bytes()).hexdigest() == original_file["sha256"]
        raw = read_yaml(original)
        rows = [row for row in audit["entries"] if row["election_id"] == election]
        assert [row["original_entry"] for row in rows] == json.loads(
            json.dumps(raw["entries"], default=str)
        )
        for row in rows:
            encoded = json.dumps(
                row["original_entry"], sort_keys=True, separators=(",", ":")
            ).encode()
            assert hashlib.sha256(encoded).hexdigest() == row["original_entry_sha256"]
            assert row["identity"] == [
                row["original_entry"]["corrected_on"],
                row["original_entry"]["headline"],
            ]
            assert row["rationale"]
        current = load_rendering_corrections(election, corrections_dir=UPDATES_DIR)
        assert current is not None
        assert current.schema_version == "1.2"
        public = [row for row in rows if row["disposition"] == "election_information"]
        assert len(public) == (15 if election == "wa-2026-primary" else 18)
        migrated = current.entries[: len(public)]
        for entry, row in zip(migrated, public, strict=True):
            serialized = entry.model_dump(mode="json")
            assert serialized.pop("topics") == row["topics"]
            assert serialized.pop("actions") == row["actions"]
            assert serialized.pop("slug") == entry.slug
            serialized.pop("redirect_from", None)
            assert serialized == row["original_entry"]
        if election == "wa-2026-general":
            added = current.entries[len(public) :]
            assert [entry.headline for entry in added[:2]] == [
                "Added SGN's five state Supreme Court endorsements.",
                "Added unofficial election-wide counts to the general guide.",
            ]
            assert added[1].corrected_on == date(2026, 11, 6)
            assert added[1].topics == ["results"]
            assert added[1].actions == ["added"]
            assert {link.url for link in added[1].provenance} == {
                "/e/wa-2026-general/",
                "https://results.votewa.gov/cdn/results/washington/export-20261103.json",
                "https://results.votewa.gov/results/public/api/elections/king-county-wa/20261103/data",
                "https://github.com/shaug/seattle-election-guide/issues/696",
            }
            assert added[0].corrected_on == date(2026, 11, 2)
            assert added[0].topics == ["endorsements"]
            assert added[0].actions == ["added"]
            # #718 audits the original automatic tail, removes metadata-only
            # records and retains every published route through existing aliases.
            # Later genuine tally changes retain distinct publication identities.
            for entry in added[2:]:
                assert entry.corrected_on >= date(2026, 11, 6)
                assert entry.topics == ["results"]
                assert entry.actions == ["changed"]
                assert re.fullmatch(
                    r"Updated preliminary counts for [1-9]\d* contests?\.",
                    entry.headline,
                )
                assert re.search(
                    r" Results checked [A-Z][a-z]+ [1-9]\d?, \d{4} at "
                    r"(?:[1-9]|1[0-2]):[0-5]\d [ap]\.m\. Pacific\.$",
                    entry.body,
                )
                assert {link.url for link in entry.provenance} == {
                    "/e/wa-2026-general/",
                    "https://github.com/shaug/seattle-election-guide/issues/696",
                }
            assert next(
                e for e in current.entries if "Updated King County" in e.headline
            ).actions == ["correction"]
        else:
            assert current.entries == migrated


@pytest.mark.parametrize("election", ["wa-2026-general", "wa-2026-primary"])
def test_historical_entry_can_preserve_a_retired_route_without_changing_original_fields(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    election: str,
) -> None:
    for path in UPDATES_DIR.glob("*.yaml"):
        (tmp_path / path.name).write_bytes(path.read_bytes())
    path = tmp_path / f"{election}.yaml"
    payload = read_yaml(path)
    entry = payload["entries"][0]
    old_slug = entry["slug"]
    entry["slug"] = old_slug + "-corrected"
    entry["redirect_from"] = [old_slug]
    path.write_text(yaml.safe_dump(payload))
    monkeypatch.setattr(f"{__name__}.UPDATES_DIR", tmp_path)
    test_election_only_migration_preserves_every_complete_original()


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
    original = read_yaml(PROJECT_ROOT / "docs/audits/updates-676/original-wa-2026-general.yaml")
    prefix = json.loads(json.dumps(original["entries"][:26], default=str))
    encoded = json.dumps(prefix, sort_keys=True, separators=(",", ":")).encode()
    assert hashlib.sha256(encoded).hexdigest() == audit["preserved_public_prefix_sha256"]


def _results_check_presentation_entries(audit: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Only #728's exact presentation replaces #718's immutable corrected text."""
    checked_times = {
        "preliminary-results-2026-11-06-232155": "November 6, 2026 at 11:21 p.m.",
        "preliminary-results-2026-11-07-164349": "November 7, 2026 at 4:43 p.m.",
        "preliminary-results-2026-11-07-182532": "November 7, 2026 at 6:25 p.m.",
    }
    retained = [row["corrected_entry"] for row in audit["records"] if row["changed_contest_ids"]]
    assert {entry["slug"] for entry in retained} == checked_times.keys()
    rows: list[dict[str, Any]] = []
    migrated: dict[str, dict[str, Any]] = {}
    for original in retained:
        slug = original["slug"]
        encoded = json.dumps(original, sort_keys=True, separators=(",", ":")).encode()
        headline = original["headline"].split(" at ")[0] + "."
        body = original["body"] + f" Results checked {checked_times[slug]} Pacific."
        rows.append(
            {
                "slug": slug,
                "original_entry_sha256": hashlib.sha256(encoded).hexdigest(),
                "headline": headline,
                "body": body,
            }
        )
        migrated[slug] = {**original, "headline": headline, "body": body}
    migration = json.loads(PRESENTATION_MIGRATION.read_text())
    assert migration == {
        "schema_version": "1.0",
        "authority": "https://github.com/shaug/seattle-election-guide/issues/728",
        "source_revision": "5697bed34bc43e88de145e929fabf9499e6d0f63",
        "source_audit": "docs/audits/updates-718/classification.json",
        "source_audit_sha256": "40a8b6db2a7299e73d6ecee3afa3c920f3058202831218785910a51e27c8ca8d",
        "entries": rows,
    }
    return migrated


def test_results_check_audit_preserves_real_counts_and_all_published_routes() -> None:
    audit_dir = PROJECT_ROOT / "docs/audits/updates-718"
    audit_bytes = (audit_dir / "classification.json").read_bytes()
    assert hashlib.sha256(audit_bytes).hexdigest() == (
        "40a8b6db2a7299e73d6ecee3afa3c920f3058202831218785910a51e27c8ca8d"
    )
    audit = json.loads(audit_bytes)
    presented = _results_check_presentation_entries(audit)
    original = (audit_dir / "original-wa-2026-general.yaml").read_bytes()
    assert hashlib.sha256(original).hexdigest() == audit["original_file_sha256"]
    frozen = json.loads(json.dumps(yaml.safe_load(original), default=str))
    assert [row["original_entry"] for row in audit["records"]] == frozen["entries"][20:]
    current = load_rendering_corrections("wa-2026-general", corrections_dir=UPDATES_DIR)
    assert current is not None
    by_slug = {e.slug: e.model_dump(mode="json") for e in current.entries}
    assert [len(r["changed_contest_ids"]) for r in audit["records"]] == [52, 0, 52, 8, 0]
    for row in audit["records"]:
        before, after = row["before_tallies"], row["after_tallies"]
        assert before.keys() == after.keys() and len(before) == 52
        assert [key for key in before if before[key] != after[key]] == row["changed_contest_ids"]
        slug = row["original_entry"]["slug"]
        assert isinstance(slug, str)
        if row["changed_contest_ids"]:
            assert row["disposition"] == "retain_actual_results_change"
            assert slug in by_slug
            assert by_slug[slug] == presented[slug]
        else:
            assert row["disposition"] == "metadata_only_removed_from_index"
            assert slug not in by_slug
            assert slug in by_slug[row["redirect_to"]]["redirect_from"]
    assert len(current.entries) >= 23
    assert [e.model_dump(mode="json") for e in current.entries[:20]] == frozen["entries"][:20]


@pytest.mark.parametrize(
    "field,value",
    [
        ("headline", "Updated preliminary counts for 53 contests."),
        ("body", "Results checked November 6, 2026 at 11:22 p.m. Pacific."),
        ("slug", "preliminary-results-2026-11-06-232155-changed"),
        ("corrected_on", "2026-11-08"),
        ("topics", ["sources"]),
        ("actions", ["correction"]),
        ("provenance", [{"label": "Changed evidence", "url": "/e/wa-2026-general/"}]),
        ("redirect_from", []),
    ],
)
def test_results_presentation_migration_rejects_other_authored_changes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, field: str, value: object
) -> None:
    raw = read_yaml(UPDATES_DIR / "wa-2026-general.yaml")
    raw["entries"][20][field] = value
    (tmp_path / "wa-2026-general.yaml").write_text(yaml.safe_dump(raw))
    monkeypatch.setattr(f"{__name__}.UPDATES_DIR", tmp_path)
    with pytest.raises(AssertionError):
        test_results_check_audit_preserves_real_counts_and_all_published_routes()


@pytest.mark.parametrize("mutation", ["headline", "body", "hash", "extra", "missing"])
def test_results_presentation_migration_rejects_unapproved_binding(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, mutation: str
) -> None:
    migration = json.loads(PRESENTATION_MIGRATION.read_text())
    if mutation in {"headline", "body"}:
        migration["entries"][0][mutation] += " Unapproved change."
    elif mutation == "hash":
        migration["entries"][0]["original_entry_sha256"] = "0" * 64
    elif mutation == "extra":
        migration["entries"].append(migration["entries"][0])
    else:
        migration["entries"].pop()
    path = tmp_path / "presentation.json"
    path.write_text(json.dumps(migration))
    monkeypatch.setattr(f"{__name__}.PRESENTATION_MIGRATION", path)
    with pytest.raises(AssertionError):
        test_results_check_audit_preserves_real_counts_and_all_published_routes()
