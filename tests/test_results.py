from __future__ import annotations

import subprocess
from datetime import UTC, datetime
from pathlib import Path

import pytest
import yaml
from pydantic import ValidationError
from typer.testing import CliRunner

from election_guide.cli import app
from election_guide.evidence.models import CaptureRequest, UnavailableRequest
from election_guide.evidence.storage import record_capture, record_unavailable
from election_guide.inventory.importer import read_inventory
from election_guide.inventory.models import Inventory
from election_guide.results.ingest import (
    ResultsIngestError,
    build_election_results,
    parse_certified_csv,
    resolve_choice,
    resolve_race,
)
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

# A trimmed excerpt of King County's real `webresults-<date>.csv` certified
# export, captured live on 2026-08-07 while designing this adapter (the
# wa-2026-primary election was still counting; certification is due
# ~2026-08-19). The vote counts are therefore an in-progress snapshot, not a
# certified result -- this fixture exists only to prove the adapter parses
# the export's real shape (quoted CSV, comma-thousands vote counts, a
# write-in row, an unrelated jurisdiction's contest) and resolves real
# official names, never to assert an election outcome.
CERTIFIED_CSV_PATH = (
    PROJECT_ROOT / "tests" / "fixtures" / "results" / "wa-2026-primary-certified.csv"
)
AUTHORITY_REGISTRY_PATH = PROJECT_ROOT / "config" / "authorities" / "default.yaml"


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


# --- The certified-CSV adapter (results/ingest.py) --------------------------

ASSESSOR_ID = "king-county-assessor"
PROPOSITION_ID = "seattle-proposition-1-library-levy"
# One of the six publication-eligible races whose ballot carries exactly one
# declared candidate, where the write-in row is a voter's only alternative
# (`results/ingest.py`, `_build_race_results`).
UNOPPOSED_RACE_ID = "ld-36-state-representative-2"


def _capture_certified_csv(root: Path) -> Path:
    """Capture the real fixture CSV through the same evidence pipeline a
    live certified ingest uses, and return the manifest path.

    Copies the committed fixture into `root` (outside the checkout) before
    capture: a restricted capture's input must already be committed or
    Git-ignored (`evidence/storage.py`, `docs/COLLECTION.md`), and this
    fixture may be neither yet in a working tree mid-edit."""
    staged_input = root / "wa-2026-primary-certified.csv"
    staged_input.write_bytes(CERTIFIED_CSV_PATH.read_bytes())
    request = CaptureRequest.model_validate(
        {
            "source_id": "king-county-elections",
            "requested_url": "https://cdn.kingcounty.gov/results/webresults-fixture.csv",
            "canonical_url": "https://cdn.kingcounty.gov/results/webresults-fixture.csv",
            "retrieved_at": datetime(2026, 8, 20, 16, 5, tzinfo=UTC),
            "media_type": "text/csv",
            "title": "2026 Washington August Primary certified results (King County CSV)",
            "capture_method": "manual_upload",
            "redistribution": "restricted",
            "redistribution_note": "Official results retained locally; manifest public.",
        }
    )
    return record_capture(
        request,
        staged_input,
        root / "snapshots",
        root / "data/manifests/evidence",
    )


def test_parse_certified_csv_reads_every_contest_row() -> None:
    by_contest = parse_certified_csv(CERTIFIED_CSV_PATH.read_bytes())

    assert by_contest["Assessor (Vote for 1)"].ballots_with_contest == 495336
    assert by_contest["Assessor (Vote for 1)"].choices == [
        ("Dominique M Scarimbolo", 87507),
        ("Christopher Roberts", 85320),
        ("Rob Foxcurran", 214135),
        ("Al Dams", 68224),
        ("Write-in", 1353),
    ]
    assert by_contest["City of Seattle Proposition No. 1 (Vote for 1)"].ballots_with_contest == (
        195237
    )
    assert by_contest["City of Seattle Proposition No. 1 (Vote for 1)"].choices == [
        ("Yes", 143828),
        ("No", 47882),
    ]


def test_parse_certified_csv_rejects_missing_columns() -> None:
    with pytest.raises(ResultsIngestError, match="missing required columns"):
        parse_certified_csv(b'"Contest","Choice"\n"Race","A"\n')


def test_parse_certified_csv_rejects_non_numeric_votes() -> None:
    content = (
        b'"Contest","Choice","Votes","BallotsWith Contest"\n'
        b'"Assessor (Vote for 1)","Al Dams","not-a-number","1,000"\n'
    )
    with pytest.raises(ResultsIngestError, match="non-numeric vote count"):
        parse_certified_csv(content)


def test_parse_certified_csv_rejects_an_empty_export() -> None:
    with pytest.raises(ResultsIngestError, match="no contest rows"):
        parse_certified_csv(b'"Contest","Choice","Votes","BallotsWith Contest"\n')


def test_parse_certified_csv_rejects_inconsistent_ballots_with_contest() -> None:
    content = (
        b'"Contest","Choice","Votes","BallotsWith Contest"\n'
        b'"Assessor (Vote for 1)","Al Dams","500","1,000"\n'
        b'"Assessor (Vote for 1)","Rob Foxcurran","500","1,001"\n'
    )
    with pytest.raises(ResultsIngestError, match="two different ballots-with-contest counts"):
        parse_certified_csv(content)


def test_resolve_race_matches_the_real_assessor_contest() -> None:
    inventory = _inventory()
    races = [race for race in inventory.races if race.publication_eligible]

    race = resolve_race("Assessor (Vote for 1)", races)

    assert race is not None
    assert race.id == ASSESSOR_ID


def test_resolve_race_disambiguates_near_identical_legislative_district_names() -> None:
    # Regression: naive fuzzy text similarity confuses "Legislative District
    # No. 1 Representative Position No. 1" with "No. 11" and "No. 32" because
    # they differ only by an embedded digit. Exact normalized-phrase
    # matching must not make that mistake.
    inventory = _inventory()
    races = [race for race in inventory.races if race.publication_eligible]

    race_11 = resolve_race(
        "Legislative District No. 11 Representative Position No. 1 (Vote for 1)", races
    )
    race_32 = resolve_race(
        "Legislative District No. 32 Representative Position No. 1 (Vote for 1)", races
    )

    assert race_11 is not None
    assert race_32 is not None
    assert race_11.id == "ld-11-state-representative-1"
    assert race_32.id == "ld-32-state-representative-1"


# Every publication-eligible wa-2026-primary race's real King County
# certified-export contest label, observed live on 2026-08-07 while
# designing this resolver (docs/RESULTS.md, "Ingestion mechanics"). The
# provenance of each string is that capture-time observation, recorded here
# so it survives the fetch; what the test below proves is the separate,
# offline-reproducible half -- that the resolver maps these 32 strings to the
# right races, exercising every phrase-generation rule
# `_race_match_phrases` (`results/ingest.py`) carries. The first 24 are the
# races `docs/runbooks/results-certified-ingest.md` phase 2 names for the
# live wa-2026-primary ingest (King County's canvass suffices for their true
# total); the last 8 are the races that need the Secretary of State's data
# instead (docs/RESULTS.md, County scope) -- resolved here too, since the
# resolver itself is race-agnostic and a future Secretary-of-State-scoped
# adapter will need the same race IDs.
REAL_CONTEST_LABEL_BY_RACE_ID: dict[str, str] = {
    "king-county-assessor": "Assessor (Vote for 1)",
    "king-county-council-2": "Metropolitan King County Council District No. 2 (Vote for 1)",
    "king-county-council-8": "Metropolitan King County Council District No. 8 (Vote for 1)",
    "ld-11-state-representative-1": (
        "Legislative District No. 11 Representative Position No. 1 (Vote for 1)"
    ),
    "ld-11-state-representative-2": (
        "Legislative District No. 11 Representative Position No. 2 (Vote for 1)"
    ),
    "ld-34-state-representative-1": (
        "Legislative District No. 34 Representative Position No. 1 (Vote for 1)"
    ),
    "ld-34-state-representative-2": (
        "Legislative District No. 34 Representative Position No. 2 (Vote for 1)"
    ),
    "ld-34-state-senator": "Legislative District No. 34 State Senator (Vote for 1)",
    "ld-36-state-representative-1": (
        "Legislative District No. 36 Representative Position No. 1 (Vote for 1)"
    ),
    "ld-36-state-representative-2": (
        "Legislative District No. 36 Representative Position No. 2 (Vote for 1)"
    ),
    "ld-36-state-senator": "Legislative District No. 36 State Senator (Vote for 1)",
    "ld-37-state-representative-1": (
        "Legislative District No. 37 Representative Position No. 1 (Vote for 1)"
    ),
    "ld-37-state-representative-2": (
        "Legislative District No. 37 Representative Position No. 2 (Vote for 1)"
    ),
    "ld-37-state-senator": "Legislative District No. 37 State Senator (Vote for 1)",
    "ld-43-state-representative-1": (
        "Legislative District No. 43 Representative Position No. 1 (Vote for 1)"
    ),
    "ld-43-state-representative-2": (
        "Legislative District No. 43 Representative Position No. 2 (Vote for 1)"
    ),
    "ld-43-state-senator": "Legislative District No. 43 State Senator (Vote for 1)",
    "ld-46-state-representative-1": (
        "Legislative District No. 46 Representative Position No. 1 (Vote for 1)"
    ),
    "ld-46-state-representative-2": (
        "Legislative District No. 46 Representative Position No. 2 (Vote for 1)"
    ),
    "ld-46-state-senator": "Legislative District No. 46 State Senator (Vote for 1)",
    "seattle-city-council-5": "Seattle City Council District No. 5 (Vote for 1)",
    "seattle-municipal-court-judge-5": (
        "City of Seattle Municipal Court Judge Position No. 5 (Vote for 1)"
    ),
    "seattle-proposition-1-library-levy": "City of Seattle Proposition No. 1 (Vote for 1)",
    "us-house-7": "U.S. Representative, Congressional District No. 7 (Vote for 1)",
    # Races King County's canvass alone cannot state the true total for
    # (docs/RESULTS.md, County scope) -- omitted from the runbook's live
    # `--race-id` list, but still real, resolvable contest labels.
    "supreme-court-justice-1": "Justice Position No. 1 (Vote for 1)",
    "supreme-court-justice-3": "Justice Position No. 3 (Vote for 1)",
    "supreme-court-justice-5": "Justice Position No. 5 (Vote for 1)",
    "supreme-court-justice-7": "Justice Position No. 7 (Vote for 1)",
    "ld-32-state-representative-1": (
        "Legislative District No. 32 Representative Position No. 1 (Vote for 1)"
    ),
    "ld-32-state-representative-2": (
        "Legislative District No. 32 Representative Position No. 2 (Vote for 1)"
    ),
    "ld-32-state-senator": "Legislative District No. 32 State Senator (Vote for 1)",
    "us-house-9": "U.S. Representative Congressional District No. 9 (Vote for 1)",
}


def test_resolve_race_matches_every_publication_eligible_race_label() -> None:
    inventory = _inventory()
    races = [race for race in inventory.races if race.publication_eligible]
    pub_eligible_ids = {race.id for race in races}

    # The fixture table itself must stay in sync with the inventory: no
    # publication-eligible race silently missing from this evidence, and no
    # stale entry for a race the inventory no longer carries.
    assert set(REAL_CONTEST_LABEL_BY_RACE_ID) == pub_eligible_ids

    for race_id, contest_label in REAL_CONTEST_LABEL_BY_RACE_ID.items():
        race = resolve_race(contest_label, races)
        assert race is not None, f"{contest_label!r} did not resolve to any race"
        assert race.id == race_id, f"{contest_label!r} resolved to {race.id!r}, not {race_id!r}"


def test_resolve_race_returns_none_for_a_contest_outside_the_inventory() -> None:
    inventory = _inventory()
    races = [race for race in inventory.races if race.publication_eligible]

    assert resolve_race("City of Black Diamond Proposition No. 1 (Vote for 1)", races) is None


def test_resolve_choice_skips_a_write_in_row() -> None:
    inventory = _inventory()
    race = next(race for race in inventory.races if race.id == ASSESSOR_ID)

    assert resolve_choice("Write-in", race) is None


def test_resolve_choice_matches_the_official_name() -> None:
    inventory = _inventory()
    race = next(race for race in inventory.races if race.id == ASSESSOR_ID)

    choice = resolve_choice("Rob Foxcurran", race)

    assert choice is not None
    assert choice.id == f"{ASSESSOR_ID}--rob-foxcurran"


def test_resolve_choice_aborts_on_an_unmatched_candidate() -> None:
    inventory = _inventory()
    race = next(race for race in inventory.races if race.id == ASSESSOR_ID)

    with pytest.raises(ResultsIngestError, match="matched 0 ballot choices"):
        resolve_choice("Someone Not On The Ballot", race)


def test_build_election_results_from_the_fixture_csv(tmp_path: Path) -> None:
    inventory = _inventory()
    certified_manifest_path = _capture_certified_csv(tmp_path)
    captures = [
        ResultsCapture(
            kind="certified",
            captured_at=datetime(2026, 8, 20, 16, 5, tzinfo=UTC),
            evidence=str(certified_manifest_path.relative_to(tmp_path)),
        )
    ]

    results = build_election_results(
        CERTIFIED_CSV_PATH.read_bytes(),
        inventory,
        authority="King County Elections",
        certified_on=datetime(2026, 8, 19).date(),
        captures=captures,
        expected_race_ids=frozenset({ASSESSOR_ID, PROPOSITION_ID}),
    )

    # The produced file is itself a valid, schema- and inventory-conformant
    # results file -- the fixture-driven acceptance criterion this ticket
    # names ("captured export in, valid results file out, no network").
    validate_results_inventory(results, inventory)
    validate_results_evidence(results, repository_root=tmp_path)

    assert results.election_id == "wa-2026-primary"
    assert results.status == "certified"
    assert {race.race_id for race in results.races} == {ASSESSOR_ID, PROPOSITION_ID}

    assessor = next(race for race in results.races if race.race_id == ASSESSOR_ID)
    # `ballots_counted` is the export's own `BallotsWith Contest` figure (the
    # fixture's real recorded value), not a re-derived vote sum -- it
    # legitimately exceeds the sum of recorded votes (overvotes/undervotes).
    assert assessor.ballots_counted == 495336
    outcomes_by_choice = {outcome.choice_id: outcome for outcome in assessor.outcomes}
    assert outcomes_by_choice[f"{ASSESSOR_ID}--rob-foxcurran"].votes == 214135
    assert outcomes_by_choice[f"{ASSESSOR_ID}--rob-foxcurran"].advanced is True
    assert outcomes_by_choice[f"{ASSESSOR_ID}--dominique-m-scarimbolo"].advanced is True
    assert outcomes_by_choice[f"{ASSESSOR_ID}--christopher-roberts"].advanced is False
    assert outcomes_by_choice[f"{ASSESSOR_ID}--al-dams"].advanced is False
    # `share` is votes over the *declared* (non-write-in) total -- a third
    # total, distinct from both `ballots_counted` and the raw vote sum
    # (docs/RESULTS.md, "Ingestion mechanics").
    assert outcomes_by_choice[f"{ASSESSOR_ID}--rob-foxcurran"].share == pytest.approx(
        214135 / (87507 + 85320 + 214135 + 68224), abs=1e-4
    )
    assert sum(outcome.share for outcome in assessor.outcomes) == pytest.approx(1.0, abs=1e-4)
    # No write-in choice_id was invented -- the write-in row is excluded.
    assert len(assessor.outcomes) == 4

    proposition = next(race for race in results.races if race.race_id == PROPOSITION_ID)
    assert proposition.ballots_counted == 195237
    prop_outcomes = {outcome.choice_id: outcome for outcome in proposition.outcomes}
    assert prop_outcomes[f"{PROPOSITION_ID}--yes"].advanced is True
    assert prop_outcomes[f"{PROPOSITION_ID}--no"].advanced is False
    assert prop_outcomes[f"{PROPOSITION_ID}--yes"].share == pytest.approx(
        143828 / (143828 + 47882), abs=1e-4
    )


def test_build_election_results_aborts_when_an_expected_race_is_missing(tmp_path: Path) -> None:
    inventory = _inventory()
    certified_manifest_path = _capture_certified_csv(tmp_path)
    captures = [
        ResultsCapture(
            kind="certified",
            captured_at=datetime(2026, 8, 20, 16, 5, tzinfo=UTC),
            evidence=str(certified_manifest_path.relative_to(tmp_path)),
        )
    ]

    with pytest.raises(ResultsIngestError, match="did not include 1 expected race"):
        build_election_results(
            CERTIFIED_CSV_PATH.read_bytes(),
            inventory,
            authority="King County Elections",
            certified_on=datetime(2026, 8, 19).date(),
            captures=captures,
            expected_race_ids=frozenset({ASSESSOR_ID, "king-county-council-8"}),
        )


def test_build_election_results_rejects_a_non_publication_eligible_expected_race(
    tmp_path: Path,
) -> None:
    inventory = _inventory()
    captures = [
        ResultsCapture(
            kind="certified",
            captured_at=datetime(2026, 8, 20, 16, 5, tzinfo=UTC),
            evidence=_evidence_reference(tmp_path, "certified"),
        )
    ]

    with pytest.raises(ResultsIngestError, match="not publication-eligible"):
        build_election_results(
            CERTIFIED_CSV_PATH.read_bytes(),
            inventory,
            authority="King County Elections",
            certified_on=datetime(2026, 8, 19).date(),
            captures=captures,
            expected_race_ids=frozenset({"not-a-real-race"}),
        )


def test_build_election_results_handles_a_large_write_in_share_on_an_unopposed_race(
    tmp_path: Path,
) -> None:
    # Regression for a review finding: six of this election's 32
    # publication-eligible races carry exactly one declared candidate, so the
    # write-in row is a voter's only alternative and a write-in share past
    # `SHARE_SUM_TOLERANCE`'s single point is the ordinary case there, not an
    # anomaly. Computing `share` against the write-in-inclusive total made
    # every such race abort the whole multi-race run; against the declared
    # total the declared shares sum to ~1 by construction, while
    # `ballots_counted` still reports every vote the contest recorded.
    inventory = _inventory()
    csv_content = (
        b'"Contest","Choice","Votes","BallotsWith Contest"\n'
        b'"Legislative District No. 36 Representative Position No. 2 (Vote for 1)"'
        b',"Liz Berry","5,000","6,200"\n'
        b'"Legislative District No. 36 Representative Position No. 2 (Vote for 1)"'
        b',"Write-in","1,000","6,200"\n'
    )
    captures = [
        ResultsCapture(
            kind="certified",
            captured_at=datetime(2026, 8, 20, 16, 5, tzinfo=UTC),
            evidence=_evidence_reference(tmp_path, "certified"),
        )
    ]

    results = build_election_results(
        csv_content,
        inventory,
        authority="King County Elections",
        certified_on=datetime(2026, 8, 19).date(),
        captures=captures,
        expected_race_ids=frozenset({UNOPPOSED_RACE_ID}),
    )

    validate_results_inventory(results, inventory)
    race = next(race for race in results.races if race.race_id == UNOPPOSED_RACE_ID)
    # `ballots_counted` is the export's own `BallotsWith Contest` figure, not
    # a re-derived vote sum -- it legitimately differs from 5,000 + 1,000.
    assert race.ballots_counted == 6200
    assert len(race.outcomes) == 1
    outcome = race.outcomes[0]
    assert outcome.choice_id == f"{UNOPPOSED_RACE_ID}--liz-berry"
    assert outcome.votes == 5000
    assert outcome.share == pytest.approx(1.0, abs=1e-4)
    assert outcome.advanced is True


def test_build_election_results_aborts_when_only_write_ins_carry_votes(tmp_path: Path) -> None:
    # The one remaining way a race has no declared vote to compute a share
    # against: every declared choice at zero. That is a data problem to
    # escalate, not a division by zero
    # (docs/runbooks/results-certified-ingest.md, Escalation).
    inventory = _inventory()
    csv_content = (
        b'"Contest","Choice","Votes","BallotsWith Contest"\n'
        b'"Legislative District No. 36 Representative Position No. 2 (Vote for 1)"'
        b',"Liz Berry","0","1,200"\n'
        b'"Legislative District No. 36 Representative Position No. 2 (Vote for 1)"'
        b',"Write-in","1,000","1,200"\n'
    )
    captures = [
        ResultsCapture(
            kind="certified",
            captured_at=datetime(2026, 8, 20, 16, 5, tzinfo=UTC),
            evidence=_evidence_reference(tmp_path, "certified"),
        )
    ]

    with pytest.raises(ResultsIngestError, match="zero votes for every declared ballot choice"):
        build_election_results(
            csv_content,
            inventory,
            authority="King County Elections",
            certified_on=datetime(2026, 8, 19).date(),
            captures=captures,
            expected_race_ids=frozenset({UNOPPOSED_RACE_ID}),
        )


def test_build_election_results_aborts_when_the_export_drops_a_declared_choice(
    tmp_path: Path,
) -> None:
    # Regression for a review finding: the resolution loop only ever checks
    # that every *exported* row resolves to a known choice -- a choice the
    # inventory declares but whose row is missing entirely from a truncated
    # or malformed export was invisible to it, silently renormalizing
    # `share` over the survivors (the schema's "shares sum to ~1" invariant
    # is satisfied either way). Every declared ballot choice must appear in
    # the export or this aborts loudly -- never guessed.
    inventory = _inventory()
    csv_content = (
        b'"Contest","Choice","Votes","BallotsWith Contest"\n'
        b'"Assessor (Vote for 1)","Dominique M Scarimbolo","87,507","495,336"\n'
        b'"Assessor (Vote for 1)","Christopher Roberts","85,320","495,336"\n'
        b'"Assessor (Vote for 1)","Rob Foxcurran","214,135","495,336"\n'
        b'"Assessor (Vote for 1)","Write-in","1,353","495,336"\n'
    )
    captures = [
        ResultsCapture(
            kind="certified",
            captured_at=datetime(2026, 8, 20, 16, 5, tzinfo=UTC),
            evidence=_evidence_reference(tmp_path, "certified"),
        )
    ]

    with pytest.raises(
        ResultsIngestError,
        match=r"missing 1 declared ballot choice\(s\).*al-dams",
    ):
        build_election_results(
            csv_content,
            inventory,
            authority="King County Elections",
            certified_on=datetime(2026, 8, 19).date(),
            captures=captures,
            expected_race_ids=frozenset({ASSESSOR_ID}),
        )


def test_build_election_results_advances_the_winning_choice_of_a_rejected_measure(
    tmp_path: Path,
) -> None:
    # Regression for a review finding: `advanced` marks the choice that
    # prevailed, not an approval. A rejected measure is the one whose `No`
    # choice carries `advanced: true` -- there is no separate rejection field,
    # and `#285` derives the "Approved"/"Rejected" chip from which choice
    # advanced (docs/RESULTS.md, "The results chip"). The committed fixture
    # only covers an approved measure, so this inverts its two tallies.
    inventory = _inventory()
    csv_content = (
        b'"Contest","Choice","Votes","BallotsWith Contest"\n'
        b'"City of Seattle Proposition No. 1 (Vote for 1)","Yes","47,882","195,237"\n'
        b'"City of Seattle Proposition No. 1 (Vote for 1)","No","143,828","195,237"\n'
    )
    captures = [
        ResultsCapture(
            kind="certified",
            captured_at=datetime(2026, 8, 20, 16, 5, tzinfo=UTC),
            evidence=_evidence_reference(tmp_path, "certified"),
        )
    ]

    results = build_election_results(
        csv_content,
        inventory,
        authority="King County Elections",
        certified_on=datetime(2026, 8, 19).date(),
        captures=captures,
        expected_race_ids=frozenset({PROPOSITION_ID}),
    )

    validate_results_inventory(results, inventory)
    outcomes = {
        outcome.choice_id: outcome
        for race in results.races
        if race.race_id == PROPOSITION_ID
        for outcome in race.outcomes
    }
    assert outcomes[f"{PROPOSITION_ID}--no"].advanced is True
    assert outcomes[f"{PROPOSITION_ID}--yes"].advanced is False
    assert outcomes[f"{PROPOSITION_ID}--no"].share == pytest.approx(
        143828 / (143828 + 47882), abs=1e-4
    )


# --- CLI (`election-guide results ingest`) -----------------------------------


def test_cli_results_ingest_produces_a_valid_results_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    certified_manifest_path = _capture_certified_csv(tmp_path)
    output_dir = tmp_path / "data" / "results"

    result = CliRunner().invoke(
        app,
        [
            "results",
            "ingest",
            "--election-id",
            "wa-2026-primary",
            "--authority-id",
            "king-county-elections",
            "--certified-on",
            "2026-08-19",
            "--certified-capture",
            str(certified_manifest_path),
            "--race-id",
            ASSESSOR_ID,
            "--race-id",
            PROPOSITION_ID,
            "--inventory-path",
            str(INVENTORY_PATH),
            "--authority-registry-path",
            str(AUTHORITY_REGISTRY_PATH),
            "--storage-root",
            str(tmp_path / "snapshots"),
            "--output-dir",
            str(output_dir),
        ],
    )

    assert result.exit_code == 0, result.output
    output_path = output_dir / "wa-2026-primary.yaml"
    assert output_path.is_file()
    results = read_results(output_path)
    reject_committed_counting_status(results)
    inventory = _inventory()
    validate_results_inventory(results, inventory)
    validate_results_evidence(results, repository_root=tmp_path)
    assert {race.race_id for race in results.races} == {ASSESSOR_ID, PROPOSITION_ID}


def test_cli_results_ingest_reads_a_repository_scope_certified_capture(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The certified capture the 2026-08-20 runbook produces is stored in the
    tracked official store, not the ignored one (issue #357, `docs/COLLECTION.md`).
    Ingest has to resolve its bytes from the manifest's own recorded scope."""
    monkeypatch.chdir(tmp_path)
    subprocess.run(["git", "init", "--quiet", str(tmp_path)], check=True)
    official_root = tmp_path / "data" / "evidence" / "official"
    staged_input = tmp_path / "webresults-certified.csv"
    staged_input.write_bytes(CERTIFIED_CSV_PATH.read_bytes())
    certified_manifest_path = record_capture(
        CaptureRequest.model_validate(
            {
                "source_id": "king-county-elections",
                "requested_url": "https://cdn.kingcounty.gov/results/webresults-fixture.csv",
                "canonical_url": "https://cdn.kingcounty.gov/results/webresults-fixture.csv",
                "retrieved_at": datetime(2026, 8, 20, 16, 5, tzinfo=UTC),
                "media_type": "text/csv",
                "title": "2026 Washington August Primary certified results (King County CSV)",
                "capture_method": "manual_upload",
                "redistribution": "permitted",
                "redistribution_note": "Official public record; bytes retained in the repository.",
            }
        ),
        staged_input,
        official_root,
        tmp_path / "data/manifests/evidence",
        repository_storage_root=official_root,
    )
    output_dir = tmp_path / "data" / "results"

    result = CliRunner().invoke(
        app,
        [
            "results",
            "ingest",
            "--election-id",
            "wa-2026-primary",
            "--authority-id",
            "king-county-elections",
            "--certified-on",
            "2026-08-19",
            "--certified-capture",
            str(certified_manifest_path),
            "--race-id",
            ASSESSOR_ID,
            "--race-id",
            PROPOSITION_ID,
            "--inventory-path",
            str(INVENTORY_PATH),
            "--authority-registry-path",
            str(AUTHORITY_REGISTRY_PATH),
            "--storage-root",
            str(tmp_path / "data" / "snapshots"),
            "--output-dir",
            str(output_dir),
        ],
    )

    assert result.exit_code == 0, result.output
    results = read_results(output_dir / "wa-2026-primary.yaml")
    assert {race.race_id for race in results.races} == {ASSESSOR_ID, PROPOSITION_ID}


def test_cli_results_ingest_accepts_an_election_night_capture(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    certified_manifest_path = _capture_certified_csv(tmp_path)
    election_night_manifest_path = tmp_path / _evidence_reference(tmp_path, "election-night")
    output_dir = tmp_path / "data" / "results"

    result = CliRunner().invoke(
        app,
        [
            "results",
            "ingest",
            "--election-id",
            "wa-2026-primary",
            "--authority-id",
            "king-county-elections",
            "--certified-on",
            "2026-08-19",
            "--certified-capture",
            str(certified_manifest_path),
            "--election-night-capture",
            str(election_night_manifest_path),
            "--race-id",
            ASSESSOR_ID,
            "--race-id",
            PROPOSITION_ID,
            "--inventory-path",
            str(INVENTORY_PATH),
            "--authority-registry-path",
            str(AUTHORITY_REGISTRY_PATH),
            "--storage-root",
            str(tmp_path / "snapshots"),
            "--output-dir",
            str(output_dir),
        ],
    )

    assert result.exit_code == 0, result.output
    results = read_results(output_dir / "wa-2026-primary.yaml")
    kinds = {capture.kind for capture in results.captures}
    assert kinds == {"election_night", "certified"}


def test_cli_results_ingest_rejects_an_unavailable_election_night_capture(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Regression for a review finding: an "unavailable" manifest -- the
    # evidence lane's own record that nothing was captured -- previously
    # flowed unchallenged into a committed results file when passed as
    # `--election-night-capture` (the certified capture was already guarded
    # the same way `read_capture_manifest`/`isinstance`/`verify_capture` now
    # guards both).
    monkeypatch.chdir(tmp_path)
    certified_manifest_path = _capture_certified_csv(tmp_path)
    manifest_dir = tmp_path / "data/manifests/evidence"
    unavailable_request = UnavailableRequest.model_validate(
        {
            "source_id": "king-county-elections",
            "requested_url": "https://example.org/results/election-night",
            "retrieved_at": datetime(2026, 8, 4, 20, 35, tzinfo=UTC),
            "unavailable_reason": "Not retained in this checkout.",
            "redistribution": "restricted",
            "redistribution_note": "Nothing was captured.",
        }
    )
    unavailable_manifest_path = record_unavailable(unavailable_request, manifest_dir)

    result = CliRunner().invoke(
        app,
        [
            "results",
            "ingest",
            "--election-id",
            "wa-2026-primary",
            "--authority-id",
            "king-county-elections",
            "--certified-on",
            "2026-08-19",
            "--certified-capture",
            str(certified_manifest_path),
            "--election-night-capture",
            str(unavailable_manifest_path),
            "--race-id",
            ASSESSOR_ID,
            "--race-id",
            PROPOSITION_ID,
            "--inventory-path",
            str(INVENTORY_PATH),
            "--authority-registry-path",
            str(AUTHORITY_REGISTRY_PATH),
            "--storage-root",
            str(tmp_path / "snapshots"),
            "--output-dir",
            str(tmp_path / "data" / "results"),
        ],
    )

    assert result.exit_code == 1
    assert "election-night capture must be a captured, not unavailable, manifest" in result.output


def test_cli_results_ingest_fails_for_an_unknown_authority(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    certified_manifest_path = _capture_certified_csv(tmp_path)

    result = CliRunner().invoke(
        app,
        [
            "results",
            "ingest",
            "--election-id",
            "wa-2026-primary",
            "--authority-id",
            "not-a-real-authority",
            "--certified-on",
            "2026-08-19",
            "--certified-capture",
            str(certified_manifest_path),
            "--race-id",
            ASSESSOR_ID,
            "--race-id",
            PROPOSITION_ID,
            "--inventory-path",
            str(INVENTORY_PATH),
            "--authority-registry-path",
            str(AUTHORITY_REGISTRY_PATH),
            "--storage-root",
            str(tmp_path / "snapshots"),
            "--output-dir",
            str(tmp_path / "data" / "results"),
        ],
    )

    assert result.exit_code == 1
    assert "unknown authority id" in result.output


def test_cli_results_ingest_requires_at_least_one_race_id(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Regression: there is deliberately no every-publication-eligible-race
    # default (a silent default could publish a King-County-only partial
    # tally for a race that needs the Secretary of State's true total).
    monkeypatch.chdir(tmp_path)
    certified_manifest_path = _capture_certified_csv(tmp_path)

    result = CliRunner().invoke(
        app,
        [
            "results",
            "ingest",
            "--election-id",
            "wa-2026-primary",
            "--authority-id",
            "king-county-elections",
            "--certified-on",
            "2026-08-19",
            "--certified-capture",
            str(certified_manifest_path),
            "--inventory-path",
            str(INVENTORY_PATH),
            "--authority-registry-path",
            str(AUTHORITY_REGISTRY_PATH),
            "--storage-root",
            str(tmp_path / "snapshots"),
            "--output-dir",
            str(tmp_path / "data" / "results"),
        ],
    )

    assert result.exit_code == 1
    assert "requires at least one --race-id" in result.output
    assert not (tmp_path / "data" / "results" / "wa-2026-primary.yaml").exists()
