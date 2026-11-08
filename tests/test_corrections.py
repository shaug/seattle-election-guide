"""Per-election corrections schema and loader tests (docs/RESULTS.md, "The
corrections page"; issue #290)."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest
import yaml
from pydantic import ValidationError

from election_guide.corrections.loader import load_rendering_corrections, read_corrections
from election_guide.corrections.models import (
    CorrectionEntry,
    CorrectionProvenanceLink,
    ElectionCorrections,
)

ELECTION_ID = "wa-2026-primary"


def _valid_corrections(*, election_id: str = ELECTION_ID) -> ElectionCorrections:
    return ElectionCorrections(
        election_id=election_id,
        entries=[
            CorrectionEntry(
                corrected_on=date(2026, 8, 27),
                headline="Amended result, State Representative (LD 32, Pos. 1).",
                body=(
                    "The county's amended canvass moved the second advancing candidate "
                    "after a machine recount."
                ),
                provenance=[
                    CorrectionProvenanceLink(
                        label="capture 9f3c…e2", url="https://example.org/captures/9f3c"
                    ),
                    CorrectionProvenanceLink(
                        label="capture 41ab…77", url="https://example.org/captures/41ab"
                    ),
                ],
            ),
            CorrectionEntry(
                corrected_on=date(2026, 7, 22),
                headline="Corrected an endorsement attribution.",
                body=(
                    "The 46th District Democrats' sole endorsement in the County Assessor "
                    "race was attributed to the wrong candidate for roughly six hours."
                ),
            ),
        ],
    )


def test_election_corrections_round_trips_through_yaml(tmp_path: Path) -> None:
    corrections = _valid_corrections()
    path = tmp_path / "wa-2026-primary.yaml"
    path.write_text(yaml.safe_dump(corrections.model_dump(mode="json")), encoding="utf-8")

    loaded = read_corrections(path)

    assert loaded == corrections


def test_election_corrections_rejects_undeclared_fields() -> None:
    payload = _valid_corrections().model_dump(mode="json")
    payload["unexpected"] = True

    with pytest.raises(ValidationError):
        ElectionCorrections.model_validate(payload)


def test_election_corrections_requires_at_least_one_entry() -> None:
    payload = _valid_corrections().model_dump(mode="json")
    payload["entries"] = []

    with pytest.raises(ValidationError):
        ElectionCorrections.model_validate(payload)


def test_election_corrections_rejects_a_repeated_date_and_headline_entry() -> None:
    payload = _valid_corrections().model_dump(mode="json")
    payload["entries"].append(payload["entries"][0])

    with pytest.raises(ValidationError, match="repeats a"):
        ElectionCorrections.model_validate(payload)


def test_correction_entry_provenance_defaults_to_empty() -> None:
    entry = CorrectionEntry(
        corrected_on=date(2026, 7, 22),
        headline="Corrected an endorsement attribution.",
        body="The guide's recommendation was unaffected.",
    )

    assert entry.provenance == []


def _permalink_log() -> dict[str, object]:
    payload = _valid_corrections().model_dump(mode="json")
    payload["schema_version"] = "1.2"
    for entry, slug in zip(
        payload["entries"], ("amended-ld32-result", "endorsement-correction"), strict=True
    ):
        entry.update(slug=slug, topics=["results"], actions=["correction"])
    return payload


@pytest.mark.parametrize(
    "slug",
    [None, "", "Uppercase", "two--hyphens", "-start", "end-", "a/b", "..", "%2e", "é", "index"],
)
def test_updates_permalink_schema_rejects_missing_or_unsafe_slugs(slug: str | None) -> None:
    payload = _permalink_log()
    payload["entries"][0]["slug"] = slug  # type: ignore[index]
    with pytest.raises(ValidationError, match="slug"):
        ElectionCorrections.model_validate(payload)


def test_updates_permalink_identity_survives_prose_date_and_order_changes() -> None:
    original = ElectionCorrections.model_validate(_permalink_log())
    changed = original.model_copy(deep=True)
    changed.entries.reverse()
    changed.entries[1].headline = "A corrected headline"
    changed.entries[1].corrected_on = date(2026, 8, 28)
    assert changed.entries[1].slug == "amended-ld32-result"
    another_election = original.model_copy(update={"election_id": "wa-2026-general"})
    assert another_election.entries[0].slug == original.entries[0].slug


@pytest.mark.parametrize("collision", ["canonical", "alias", "self"])
def test_updates_permalink_routes_cannot_be_reused(collision: str) -> None:
    payload = _permalink_log()
    entries = payload["entries"]
    if collision == "canonical":
        entries[1]["slug"] = entries[0]["slug"]  # type: ignore[index]
    elif collision == "alias":
        entries[1]["redirect_from"] = [entries[0]["slug"]]  # type: ignore[index]
    else:
        entries[0]["redirect_from"] = [entries[0]["slug"]]  # type: ignore[index]
    with pytest.raises(ValidationError, match="slug"):
        ElectionCorrections.model_validate(payload)


def test_updates_permalink_aliases_are_explicit_and_legacy_shape_is_unchanged() -> None:
    payload = _permalink_log()
    payload["entries"][0]["redirect_from"] = ["former-result-notice"]  # type: ignore[index]
    assert ElectionCorrections.model_validate(payload).entries[0].redirect_from == [
        "former-result-notice"
    ]
    legacy = _valid_corrections().model_dump(mode="json")
    assert all("slug" not in entry and "redirect_from" not in entry for entry in legacy["entries"])


@pytest.mark.parametrize("alias", ["index", "../retired", "former%2Fnotice", "Duplicate"])
def test_retired_permalink_aliases_follow_the_same_safe_segment_contract(alias: str) -> None:
    payload = _permalink_log()
    payload["entries"][0]["redirect_from"] = [alias]  # type: ignore[index]
    with pytest.raises(ValidationError, match="slug"):
        ElectionCorrections.model_validate(payload)


def test_election_updates_metadata_is_required_only_for_the_new_schema() -> None:
    legacy = _valid_corrections().model_dump(mode="json")
    assert "topics" not in legacy["entries"][0]
    assert "actions" not in legacy["entries"][0]
    legacy["schema_version"] = "1.1"
    with pytest.raises(ValidationError, match="topics and actions"):
        ElectionCorrections.model_validate(legacy)
    for entry in legacy["entries"]:
        entry.update(topics=["endorsements", "sources"], actions=["correction"])
    assert ElectionCorrections.model_validate(legacy).model_dump(mode="json") == legacy


@pytest.mark.parametrize(
    "metadata",
    [
        {"topics": ["software"], "actions": ["added"]},
        {"topics": ["endorsements", "endorsements"], "actions": ["added"]},
        {"topics": ["sources"], "actions": ["deployed"]},
        {"topics": ["results"], "actions": ["certified", "certified"]},
    ],
)
def test_election_updates_metadata_rejects_unknown_or_duplicate_values(
    metadata: dict[str, list[str]],
) -> None:
    payload = _valid_corrections().model_dump(mode="json")["entries"][0]
    with pytest.raises(ValidationError):
        CorrectionEntry.model_validate({**payload, **metadata})


def test_load_rendering_corrections_returns_none_without_a_file(tmp_path: Path) -> None:
    assert load_rendering_corrections(ELECTION_ID, corrections_dir=tmp_path / "corrections") is None


def test_load_rendering_corrections_loads_and_validates_a_committed_file(tmp_path: Path) -> None:
    corrections = _valid_corrections()
    corrections_dir = tmp_path / "corrections"
    corrections_dir.mkdir()
    (corrections_dir / f"{ELECTION_ID}.yaml").write_text(
        yaml.safe_dump(corrections.model_dump(mode="json")), encoding="utf-8"
    )

    loaded = load_rendering_corrections(ELECTION_ID, corrections_dir=corrections_dir)

    assert loaded == corrections


def test_load_rendering_corrections_gates_a_file_for_a_different_election(tmp_path: Path) -> None:
    corrections = _valid_corrections(election_id="wa-2025-general")
    corrections_dir = tmp_path / "corrections"
    corrections_dir.mkdir()
    # Committed under the *requested* election's own filename, but the file's
    # own `election_id` names a different election -- the loader must not
    # surface another election's entries under this one's address.
    (corrections_dir / f"{ELECTION_ID}.yaml").write_text(
        yaml.safe_dump(corrections.model_dump(mode="json")), encoding="utf-8"
    )

    assert load_rendering_corrections(ELECTION_ID, corrections_dir=corrections_dir) is None


def test_load_rendering_corrections_rejects_invalid_committed_data(tmp_path: Path) -> None:
    payload = _valid_corrections().model_dump(mode="json")
    payload["entries"] = []
    corrections_dir = tmp_path / "corrections"
    corrections_dir.mkdir()
    (corrections_dir / f"{ELECTION_ID}.yaml").write_text(yaml.safe_dump(payload), encoding="utf-8")

    with pytest.raises(ValueError, match="entries"):
        load_rendering_corrections(ELECTION_ID, corrections_dir=corrections_dir)
