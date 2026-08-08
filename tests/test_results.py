from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest
import yaml
from pydantic import ValidationError
from typer.testing import CliRunner

from election_guide.cli import app
from election_guide.evidence.models import CaptureRequest
from election_guide.evidence.storage import record_capture
from election_guide.inventory.importer import read_inventory
from election_guide.inventory.models import Inventory
from election_guide.results.loader import (
    load_rendering_results,
    read_results,
    reject_committed_counting_status,
)
from election_guide.results.models import ElectionResults, RaceOutcome, RaceResults, ResultsCapture
from election_guide.results.validation import validate_results_evidence, validate_results_inventory

PROJECT_ROOT = Path(__file__).parents[1]
INVENTORY_PATH = PROJECT_ROOT / "data/normalized/wa-2026-primary-inventory.json"
RACE_ID = "king-county-assessor"


def _inventory() -> Inventory:
    return read_inventory(INVENTORY_PATH)


def _choice_ids() -> list[str]:
    race = next(race for race in _inventory().races if race.id == RACE_ID)
    return [choice.id for choice in race.choices]


def _evidence_reference(root: Path, name: str, *, manifest_root: Path | None = None) -> str:
    """Capture a small fixture artifact and return its manifest's path, relative
    to `root` (or `manifest_root`'s own base when the manifest is stored
    somewhere other than `root` itself)."""
    base = manifest_root or root
    root.mkdir(parents=True, exist_ok=True)
    artifact = root / f"{name}.html"
    artifact.write_text(f"<html>{name}</html>", encoding="utf-8")
    request = CaptureRequest.model_validate(
        {
            "source_id": "king-county-elections",
            "requested_url": f"https://example.org/results/{name}",
            "canonical_url": f"https://example.org/results/{name}",
            "retrieved_at": datetime(2026, 8, 20, 16, 5, tzinfo=UTC),
            "http_status": 200,
            "media_type": "text/html",
            "title": f"Fixture {name} results",
            "capture_method": "static_html",
            "browser_required": False,
            "redistribution": "restricted",
            "redistribution_note": "Fixture content created for repository tests.",
        }
    )
    manifest_path = record_capture(
        request,
        artifact,
        base / "snapshots",
        base / "data/manifests/evidence",
    )
    return str(manifest_path.relative_to(base))


def _valid_results(
    root: Path, *, status: str = "certified", supersedes: str | None = None
) -> ElectionResults:
    choice_ids = _choice_ids()
    certified_reference = _evidence_reference(root, "certified")
    captures = [
        ResultsCapture(
            kind="election_night",
            captured_at=datetime(2026, 8, 4, 20, 35, tzinfo=UTC),
            evidence=_evidence_reference(root, "election-night"),
        ),
        ResultsCapture(
            kind="certified",
            captured_at=datetime(2026, 8, 20, 16, 5, tzinfo=UTC),
            evidence=certified_reference,
        ),
    ]
    return ElectionResults(
        election_id="wa-2026-primary",
        status=status,  # type: ignore[arg-type]
        certified_on=datetime(2026, 8, 19).date(),
        authority="King County Elections",
        captures=captures,
        races=[
            RaceResults(
                race_id=RACE_ID,
                ballots_counted=61234,
                outcomes=[
                    RaceOutcome(choice_id=choice_ids[0], votes=20000, share=0.32, advanced=True),
                    RaceOutcome(choice_id=choice_ids[1], votes=18000, share=0.29, advanced=True),
                    RaceOutcome(choice_id=choice_ids[2], votes=14000, share=0.23, advanced=False),
                    RaceOutcome(choice_id=choice_ids[3], votes=10000, share=0.16, advanced=False),
                ],
            )
        ],
        supersedes=supersedes,
    )


# --- Schema-level invariants (results/models.py) ---------------------------


def test_race_outcomes_reject_duplicate_choice_id() -> None:
    choice_id = _choice_ids()[0]
    with pytest.raises(ValidationError, match="repeats a ballot choice"):
        RaceResults(
            race_id=RACE_ID,
            ballots_counted=100,
            outcomes=[
                RaceOutcome(choice_id=choice_id, votes=60, share=0.6, advanced=True),
                RaceOutcome(choice_id=choice_id, votes=40, share=0.4, advanced=False),
            ],
        )


def test_race_outcomes_reject_shares_not_summing_to_one() -> None:
    choice_ids = _choice_ids()
    with pytest.raises(ValidationError, match="not ~1"):
        RaceResults(
            race_id=RACE_ID,
            ballots_counted=100,
            outcomes=[
                RaceOutcome(choice_id=choice_ids[0], votes=60, share=0.6, advanced=True),
                RaceOutcome(choice_id=choice_ids[1], votes=10, share=0.1, advanced=False),
            ],
        )


def test_election_results_rejects_duplicate_race_id(tmp_path: Path) -> None:
    results = _valid_results(tmp_path)
    with pytest.raises(ValidationError, match="repeats a race id"):
        ElectionResults.model_validate(
            {
                **results.model_dump(mode="json"),
                "races": [*results.model_dump(mode="json")["races"]] * 2,
            }
        )


def test_amended_status_requires_supersedes(tmp_path: Path) -> None:
    with pytest.raises(ValidationError, match="must cite the capture they supersede"):
        _valid_results(tmp_path, status="amended")


def test_non_amended_status_forbids_supersedes(tmp_path: Path) -> None:
    with pytest.raises(ValidationError, match="cannot cite a superseded capture"):
        _valid_results(tmp_path, status="certified", supersedes="data/manifests/evidence/x.json")


def test_amended_status_with_citation_is_valid(tmp_path: Path) -> None:
    results = _valid_results(
        tmp_path, status="amended", supersedes=_evidence_reference(tmp_path, "superseded")
    )
    assert results.status == "amended"
    assert results.supersedes is not None


def test_certified_status_requires_certification_date(tmp_path: Path) -> None:
    results = _valid_results(tmp_path).model_dump(mode="json")
    results["certified_on"] = None
    with pytest.raises(ValidationError, match="require a certification date"):
        ElectionResults.model_validate(results)


def test_counting_status_permits_no_certification_date(tmp_path: Path) -> None:
    results = _valid_results(tmp_path).model_dump(mode="json")
    results["status"] = "counting"
    results["certified_on"] = None
    validated = ElectionResults.model_validate(results)
    assert validated.status == "counting"


def test_reject_committed_counting_status(tmp_path: Path) -> None:
    results = _valid_results(tmp_path).model_dump(mode="json")
    results["status"] = "counting"
    results["certified_on"] = None
    counting_results = ElectionResults.model_validate(results)
    with pytest.raises(ValueError, match="cannot carry status 'counting'"):
        reject_committed_counting_status(counting_results)
    # A committed certified/amended file passes the same gate untouched.
    reject_committed_counting_status(_valid_results(tmp_path))


# --- Cross-document validation (results/validation.py) ---------------------


def test_validate_results_inventory_accepts_a_matching_fixture(tmp_path: Path) -> None:
    validate_results_inventory(_valid_results(tmp_path), _inventory())


def test_validate_results_inventory_rejects_unknown_race(tmp_path: Path) -> None:
    payload = _valid_results(tmp_path).model_dump(mode="json")
    payload["races"][0]["race_id"] = "not-a-real-race"
    unmatched = ElectionResults.model_validate(payload)
    with pytest.raises(ValueError, match="unknown race"):
        validate_results_inventory(unmatched, _inventory())


def test_validate_results_inventory_rejects_unknown_choice_id(tmp_path: Path) -> None:
    payload = _valid_results(tmp_path).model_dump(mode="json")
    payload["races"][0]["outcomes"][0]["choice_id"] = "king-county-assessor--not-a-candidate"
    unmatched = ElectionResults.model_validate(payload)
    with pytest.raises(ValueError, match="unknown ballot choice"):
        validate_results_inventory(unmatched, _inventory())


def test_validate_results_inventory_rejects_election_id_mismatch(tmp_path: Path) -> None:
    payload = _valid_results(tmp_path).model_dump(mode="json")
    payload["election_id"] = "wa-2026-general"
    mismatched = ElectionResults.model_validate(payload)
    with pytest.raises(ValueError, match="belongs to 'wa-2026-general'"):
        validate_results_inventory(mismatched, _inventory())


def test_validate_results_evidence_accepts_resolvable_captures(tmp_path: Path) -> None:
    validate_results_evidence(_valid_results(tmp_path), repository_root=tmp_path)


def test_validate_results_evidence_rejects_missing_manifest(tmp_path: Path) -> None:
    payload = _valid_results(tmp_path).model_dump(mode="json")
    payload["captures"][0]["evidence"] = "data/manifests/evidence/does-not-exist.json"
    broken = ElectionResults.model_validate(payload)
    with pytest.raises(ValueError, match="does not resolve to a valid evidence manifest"):
        validate_results_evidence(broken, repository_root=tmp_path)


def test_validate_results_evidence_rejects_unresolvable_supersedes(tmp_path: Path) -> None:
    valid = _valid_results(tmp_path)
    payload = {**valid.model_dump(mode="json"), "status": "amended", "supersedes": "missing.json"}
    amended = ElectionResults.model_validate(payload)
    with pytest.raises(ValueError, match="does not resolve to a valid evidence manifest"):
        validate_results_evidence(amended, repository_root=tmp_path)


# --- The loader and its rendering hook (results/loader.py) -----------------


def test_read_results_round_trips_yaml(tmp_path: Path) -> None:
    results = _valid_results(tmp_path)
    path = tmp_path / "wa-2026-primary.yaml"
    path.write_text(yaml.safe_dump(results.model_dump(mode="json")), encoding="utf-8")

    loaded = read_results(path)

    assert loaded == results


def test_load_rendering_results_returns_none_without_a_file(tmp_path: Path) -> None:
    assert (
        load_rendering_results(
            "wa-2026-primary",
            _inventory(),
            results_dir=tmp_path / "results",
            repository_root=tmp_path,
        )
        is None
    )


def test_load_rendering_results_loads_and_validates_a_certified_file(tmp_path: Path) -> None:
    results = _valid_results(tmp_path)
    results_dir = tmp_path / "results"
    results_dir.mkdir()
    (results_dir / "wa-2026-primary.yaml").write_text(
        yaml.safe_dump(results.model_dump(mode="json")), encoding="utf-8"
    )

    loaded = load_rendering_results(
        "wa-2026-primary", _inventory(), results_dir=results_dir, repository_root=tmp_path
    )

    assert loaded == results


def test_load_rendering_results_gates_a_counting_status_file(tmp_path: Path) -> None:
    payload = _valid_results(tmp_path).model_dump(mode="json")
    payload["status"] = "counting"
    payload["certified_on"] = None
    results_dir = tmp_path / "results"
    results_dir.mkdir()
    (results_dir / "wa-2026-primary.yaml").write_text(yaml.safe_dump(payload), encoding="utf-8")

    assert (
        load_rendering_results(
            "wa-2026-primary", _inventory(), results_dir=results_dir, repository_root=tmp_path
        )
        is None
    )


def test_load_rendering_results_rejects_invalid_committed_data(tmp_path: Path) -> None:
    payload = _valid_results(tmp_path).model_dump(mode="json")
    payload["races"][0]["outcomes"][0]["choice_id"] = "king-county-assessor--not-a-candidate"
    results_dir = tmp_path / "results"
    results_dir.mkdir()
    (results_dir / "wa-2026-primary.yaml").write_text(yaml.safe_dump(payload), encoding="utf-8")

    with pytest.raises(ValueError, match="unknown ballot choice"):
        load_rendering_results(
            "wa-2026-primary", _inventory(), results_dir=results_dir, repository_root=tmp_path
        )


# --- CLI (`election-guide results validate`) --------------------------------


def test_cli_results_validate_accepts_a_valid_certified_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    results = _valid_results(tmp_path)
    path = tmp_path / "wa-2026-primary.yaml"
    path.write_text(yaml.safe_dump(results.model_dump(mode="json")), encoding="utf-8")

    result = CliRunner().invoke(
        app,
        ["results", "validate", str(path), "--inventory-path", str(INVENTORY_PATH)],
    )

    assert result.exit_code == 0, result.output
    assert "wa-2026-primary" in result.output
    assert "certified" in result.output


def test_cli_results_validate_rejects_a_committed_counting_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    payload = _valid_results(tmp_path).model_dump(mode="json")
    payload["status"] = "counting"
    payload["certified_on"] = None
    path = tmp_path / "wa-2026-primary.yaml"
    path.write_text(yaml.safe_dump(payload), encoding="utf-8")

    result = CliRunner().invoke(
        app,
        ["results", "validate", str(path), "--inventory-path", str(INVENTORY_PATH)],
    )

    assert result.exit_code == 1
    assert "counting" in result.output


def test_cli_results_validate_rejects_an_unmatched_choice_id(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    payload = _valid_results(tmp_path).model_dump(mode="json")
    payload["races"][0]["outcomes"][0]["choice_id"] = "king-county-assessor--not-a-candidate"
    path = tmp_path / "wa-2026-primary.yaml"
    path.write_text(yaml.safe_dump(payload), encoding="utf-8")

    result = CliRunner().invoke(
        app,
        ["results", "validate", str(path), "--inventory-path", str(INVENTORY_PATH)],
    )

    assert result.exit_code == 1
    assert "unknown ballot choice" in result.output
