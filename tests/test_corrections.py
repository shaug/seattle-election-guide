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
