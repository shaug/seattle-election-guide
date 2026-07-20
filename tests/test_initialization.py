from __future__ import annotations

import hashlib
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from stat import S_IMODE
from typing import Any, cast

import pytest
import yaml
from typer.testing import CliRunner

from election_guide.cli import app
from election_guide.initialization import (
    initialize_election,
    read_election_configuration,
)
from election_guide.inventory.importer import read_inventory
from election_guide.inventory.initialized import (
    import_initialized_inventory,
    write_initialized_inventory,
)
from election_guide.serialization import canonical_json_bytes, read_json

FIXTURE = Path("tests/fixtures/initialization/wa-2027-seattle-general.yaml")
BALLOT_FIXTURE = Path("tests/fixtures/initialization/wa-2027-seattle-general-ballot.csv")
BALLOT_MANIFEST = Path("tests/fixtures/initialization/wa-2027-seattle-general-ballot-input.yaml")
runner = CliRunner()


def test_cli_initializes_repeatable_scoped_configuration_without_collection(
    tmp_path: Path,
    monkeypatch: Any,
) -> None:
    fetch_attempted = False

    def reject_fetch(*_args: object, **_kwargs: object) -> None:
        nonlocal fetch_attempted
        fetch_attempted = True
        raise AssertionError("election initialization must not collect live data")

    monkeypatch.setattr("election_guide.cli.fetch_http", reject_fetch)
    output = tmp_path / "wa-2027-seattle-general.json"
    first = runner.invoke(app, ["election", "init", str(FIXTURE), "--output", str(output)])
    first_bytes = output.read_bytes()
    second = runner.invoke(app, ["election", "init", str(FIXTURE), "--output", str(output)])

    assert first.exit_code == 0, first.output
    assert "configuration: created" in first.stdout
    assert second.exit_code == 0, second.output
    assert "configuration: unchanged" in second.stdout
    assert output.read_bytes() == first_bytes
    assert S_IMODE(output.stat().st_mode) == 0o644
    assert fetch_attempted is False

    configuration = read_election_configuration(output)
    assert configuration.election.id == "wa-2027-seattle-general"
    assert configuration.election.election_scope == "municipal"
    assert configuration.source_panel.model_dump() == {
        "id": "wa-2027-seattle-general-sources",
        "version": "1.0",
        "path": "config/sources/wa-2027-seattle-general.yaml",
    }
    assert configuration.scoring_policy.model_dump() == {
        "id": "unweighted-progressive",
        "version": "2.0",
        "path": "config/scoring/unweighted-progressive-2.yaml",
    }
    assert [item.id for item in configuration.jurisdictions] == [
        "city-of-seattle",
        "king-county",
        "washington-state",
    ]
    assert [item.id for item in configuration.races] == [
        "seattle-city-attorney",
        "seattle-mayor",
    ]
    assert all(
        item.election_id == configuration.election.id
        for item in [*configuration.jurisdictions, *configuration.races]
    )
    _assert_no_candidate_data(read_json(output))

    validated = runner.invoke(app, ["election", "validate", str(output)])
    assert validated.exit_code == 0, validated.output
    assert "source panel wa-2027-seattle-general-sources@1.0" in validated.stdout
    assert "scoring unweighted-progressive@2.0" in validated.stdout


def test_seed_order_does_not_change_canonical_identifiers_or_bytes(tmp_path: Path) -> None:
    payload = _seed_payload()
    payload["jurisdictions"] = list(reversed(payload["jurisdictions"]))
    payload["races"] = list(reversed(payload["races"]))
    reversed_seed = tmp_path / "reversed.yaml"
    reversed_seed.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")

    first_path = tmp_path / "first.json"
    reversed_path = tmp_path / "reversed.json"
    first, first_created = initialize_election(FIXTURE, first_path)
    reversed_configuration, reversed_created = initialize_election(reversed_seed, reversed_path)

    assert first_created is True
    assert reversed_created is True
    assert first == reversed_configuration
    assert first_path.read_bytes() == reversed_path.read_bytes()


def test_concurrent_identical_initialization_creates_one_canonical_file(tmp_path: Path) -> None:
    output = tmp_path / "shared.json"

    def initialize_once(_index: int) -> bool:
        return initialize_election(FIXTURE, output)[1]

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(initialize_once, range(2)))

    assert sorted(results) == [False, True]
    assert read_election_configuration(output).election.id == "wa-2027-seattle-general"


def test_existing_symlink_output_is_rejected_even_when_target_bytes_match(tmp_path: Path) -> None:
    external = tmp_path / "external.json"
    initialize_election(FIXTURE, external)
    linked_output = tmp_path / "linked.json"
    linked_output.symlink_to(external)

    result = runner.invoke(
        app,
        ["election", "init", str(FIXTURE), "--output", str(linked_output)],
    )

    assert result.exit_code == 1
    assert "non-regular election configuration output" in result.output
    assert linked_output.is_symlink()


def test_initialization_allows_no_declared_races_but_rejects_candidate_fields(
    tmp_path: Path,
) -> None:
    payload = _seed_payload()
    payload["races"] = []
    empty_seed = tmp_path / "empty.yaml"
    empty_seed.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")
    configuration, _ = initialize_election(empty_seed, tmp_path / "empty.json")
    assert configuration.races == []

    payload = _seed_payload()
    payload["races"][0]["candidates"] = ["Not allowed"]
    candidate_seed = tmp_path / "candidate-data.yaml"
    candidate_seed.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")
    result = runner.invoke(
        app,
        ["election", "init", str(candidate_seed), "--output", str(tmp_path / "invalid.json")],
    )
    assert result.exit_code == 1
    assert "Extra inputs are not permitted" in result.output
    assert not (tmp_path / "invalid.json").exists()


@pytest.mark.parametrize(
    ("election_type", "election_scope"),
    [
        ("primary", "municipal"),
        ("general", "county"),
        ("special", "statewide"),
        ("general", "mixed"),
    ],
)
def test_initialization_supports_future_election_types_and_scopes(
    tmp_path: Path,
    election_type: str,
    election_scope: str,
) -> None:
    payload = _scope_payload(election_scope)
    payload["election"]["election_type"] = election_type
    seed = tmp_path / f"{election_type}-{election_scope}.yaml"
    seed.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")

    configuration, created = initialize_election(seed, seed.with_suffix(".json"))

    assert created is True
    assert configuration.election.election_type == election_type
    assert configuration.election.election_scope == election_scope


def test_scope_parent_identity_and_text_invariants_reject_false_stability(
    tmp_path: Path,
) -> None:
    false_scope = _seed_payload()
    false_scope["election"]["election_scope"] = "statewide"
    false_scope_path = _write_seed(tmp_path, "false-scope", false_scope)
    false_scope_result = _initialize_result(tmp_path, false_scope_path)
    assert false_scope_result.exit_code == 1
    assert "statewide scope requires exactly one state target" in false_scope_result.output

    inverted = _seed_payload()
    inverted["jurisdictions"][0]["parent_id"] = "city-of-seattle"
    inverted["jurisdictions"][1]["parent_id"] = None
    inverted["jurisdictions"][2]["parent_id"] = None
    inverted_path = _write_seed(tmp_path, "inverted", inverted)
    inverted_result = _initialize_result(tmp_path, inverted_path)
    assert inverted_result.exit_code == 1
    assert "cannot have parent kind" in inverted_result.output

    duplicate = _seed_payload()
    copied_race = dict(duplicate["races"][0])
    copied_race["id"] = "seattle-city-attorney-copy"
    duplicate["races"].append(copied_race)
    duplicate_path = _write_seed(tmp_path, "duplicate-race", duplicate)
    duplicate_result = _initialize_result(tmp_path, duplicate_path)
    assert duplicate_result.exit_code == 1
    assert "duplicates a declared logical race" in duplicate_result.output

    punctuation_duplicate = _seed_payload()
    copied_race = dict(punctuation_duplicate["races"][1])
    copied_race["id"] = "seattle-mayor-copy"
    copied_race["office"] = "Máyor!"
    punctuation_duplicate["races"].append(copied_race)
    punctuation_path = _write_seed(
        tmp_path,
        "punctuation-duplicate-race",
        punctuation_duplicate,
    )
    punctuation_result = _initialize_result(tmp_path, punctuation_path)
    assert punctuation_result.exit_code == 1
    assert "duplicates a declared logical race" in punctuation_result.output

    blank = _seed_payload()
    blank["races"][0]["aliases"] = ["   "]
    blank_path = _write_seed(tmp_path, "blank", blank)
    blank_result = _initialize_result(tmp_path, blank_path)
    assert blank_result.exit_code == 1
    assert "race alias must not be blank" in blank_result.output

    contradictory = _seed_payload()
    contradictory["jurisdictions"][0]["seattle_relationship"] = "within_city"
    contradictory_path = _write_seed(tmp_path, "contradictory", contradictory)
    contradictory_result = _initialize_result(tmp_path, contradictory_path)
    assert contradictory_result.exit_code == 1
    assert "must use Seattle relationship 'contains_city'" in contradictory_result.output

    foreign_state = _scope_payload("statewide")
    foreign_state["jurisdictions"].append(
        {
            "id": "oregon-state",
            "name": "State of Oregon",
            "kind": "state",
            "state_code": "OR",
            "parent_id": None,
            "aliases": ["Oregon"],
            "seattle_relationship": "intersects_city",
            "seattle_explanation": "Synthetic unrelated state.",
        }
    )
    foreign_state["election"]["target_jurisdiction_ids"] = ["oregon-state"]
    for race in foreign_state["races"]:
        race["jurisdiction_id"] = "oregon-state"
    foreign_path = _write_seed(tmp_path, "foreign-state", foreign_state)
    foreign_result = _initialize_result(tmp_path, foreign_path)
    assert foreign_result.exit_code == 1
    assert "Seattle-containing hierarchy" in foreign_result.output

    detached_state = _seed_payload()
    detached_state["jurisdictions"][0]["state_code"] = "OR"
    detached_state["jurisdictions"].append(
        {
            "id": "declared-washington-state",
            "name": "Detached Washington State",
            "kind": "state",
            "state_code": "WA",
            "parent_id": None,
            "aliases": [],
            "seattle_relationship": "intersects_city",
            "seattle_explanation": "Synthetic detached state anchor.",
        }
    )
    detached_state["election"]["state_jurisdiction_id"] = "declared-washington-state"
    detached_path = _write_seed(tmp_path, "detached-state", detached_state)
    detached_result = _initialize_result(tmp_path, detached_path)
    assert detached_result.exit_code == 1
    assert "Seattle's unique state jurisdiction ancestor" in detached_result.output

    wrong_mixed_level = _scope_payload("mixed")
    wrong_mixed_level["election"]["target_jurisdiction_ids"] = [
        "city-of-seattle",
        "washington-state",
    ]
    wrong_mixed_level["races"] = wrong_mixed_level["races"][:2]
    wrong_mixed_path = _write_seed(tmp_path, "wrong-mixed-level", wrong_mixed_level)
    wrong_mixed_result = _initialize_result(tmp_path, wrong_mixed_path)
    assert wrong_mixed_result.exit_code == 1
    assert "state target cannot be represented by a race in 'county'" in wrong_mixed_result.output

    county_judicial = _scope_payload("mixed")
    county_judicial["election"]["target_jurisdiction_ids"] = [
        "city-of-seattle",
        "washington-state",
    ]
    county_judicial["jurisdictions"].append(
        {
            "id": "king-county-judicial-district",
            "name": "King County Judicial District",
            "kind": "judicial_district",
            "parent_id": "king-county",
            "aliases": [],
            "seattle_relationship": "intersects_city",
            "seattle_explanation": "Synthetic county-level judicial district.",
        }
    )
    county_judicial["races"] = county_judicial["races"][:2]
    county_judicial["races"][1].update(
        {
            "id": "king-county-judge",
            "jurisdiction_id": "king-county-judicial-district",
            "district": "King County Judicial District",
            "office": "Judge",
            "display_name": "King County Judge",
            "aliases": [],
        }
    )
    county_judicial_path = _write_seed(tmp_path, "county-judicial", county_judicial)
    county_judicial_result = _initialize_result(tmp_path, county_judicial_path)
    assert county_judicial_result.exit_code == 1
    assert "county-parented judicial district" in county_judicial_result.output

    city_council_for_county = _scope_payload("county")
    city_council_for_county["jurisdictions"].append(
        {
            "id": "generic-city-council-1",
            "name": "Generic Seattle Council District 1",
            "kind": "council_district",
            "parent_id": "city-of-seattle",
            "aliases": [],
            "seattle_relationship": "within_city",
            "seattle_explanation": "Synthetic city-parented generic council district.",
        }
    )
    city_council_for_county["races"] = [city_council_for_county["races"][0]]
    city_council_for_county["races"][0].update(
        {
            "id": "seattle-council-1",
            "jurisdiction_id": "generic-city-council-1",
            "district": "Seattle Council District 1",
            "office": "City Councilmember",
            "display_name": "Seattle City Council District 1",
            "aliases": [],
        }
    )
    council_path = _write_seed(tmp_path, "city-council-for-county", city_council_for_county)
    council_result = _initialize_result(tmp_path, council_path)
    assert council_result.exit_code == 1
    assert "differently parented generic council district" in council_result.output


def test_state_target_supports_congressional_and_legislative_district_races(
    tmp_path: Path,
) -> None:
    payload = _scope_payload("mixed")
    payload["election"]["target_jurisdiction_ids"] = [
        "city-of-seattle",
        "washington-state",
    ]
    payload["jurisdictions"].extend(
        [
            {
                "id": "wa-congressional-7",
                "name": "Washington Congressional District 7",
                "kind": "congressional_district",
                "parent_id": "washington-state",
                "aliases": [],
                "seattle_relationship": "intersects_city",
                "seattle_explanation": "Synthetic congressional district containing Seattle.",
            },
            {
                "id": "wa-legislative-36",
                "name": "Washington Legislative District 36",
                "kind": "legislative_district",
                "parent_id": "washington-state",
                "aliases": [],
                "seattle_relationship": "intersects_city",
                "seattle_explanation": "Synthetic legislative district intersecting Seattle.",
            },
        ]
    )
    payload["races"][1].update(
        {
            "id": "us-house-wa-7",
            "jurisdiction_id": "wa-congressional-7",
            "district": "Washington Congressional District 7",
            "office": "U.S. Representative",
            "display_name": "U.S. House District 7",
            "aliases": [],
        }
    )
    payload["races"][2].update(
        {
            "id": "wa-senate-36",
            "jurisdiction_id": "wa-legislative-36",
            "district": "Washington Legislative District 36",
            "office": "State Senator",
            "display_name": "Washington State Senate District 36",
            "aliases": [],
        }
    )
    seed = _write_seed(tmp_path, "state-district-races", payload)

    configuration, _ = initialize_election(seed, tmp_path / "state-district-races.json")

    assert {race.jurisdiction_id for race in configuration.races} >= {
        "wa-congressional-7",
        "wa-legislative-36",
    }


def test_configuration_validation_rejects_noncanonical_serialized_values(
    tmp_path: Path,
) -> None:
    output = tmp_path / "configuration.json"
    initialize_election(FIXTURE, output)
    raw = cast(dict[str, Any], read_json(output))
    election = cast(dict[str, Any], raw["election"])
    election["name"] = f"  {election['name']}  "
    jurisdictions = cast(list[dict[str, Any]], raw["jurisdictions"])
    jurisdictions[2]["aliases"][0] = "  WA  "
    output.write_bytes(canonical_json_bytes(raw))

    result = runner.invoke(app, ["election", "validate", str(output)])

    assert result.exit_code == 1
    assert "election configuration is not canonical" in result.output


def test_initialization_supports_project_jurisdiction_families(tmp_path: Path) -> None:
    payload = _seed_payload()
    payload["jurisdictions"].extend(
        [
            {
                "id": "state-judicial-district-1",
                "name": "State Judicial District 1",
                "kind": "judicial_district",
                "parent_id": "washington-state",
                "aliases": [],
                "seattle_relationship": "intersects_city",
                "seattle_explanation": "Synthetic future judicial district fixture.",
            },
            {
                "id": "seattle-ballot-style-1",
                "name": "Seattle Ballot Style 1",
                "kind": "ballot_style",
                "parent_id": "city-of-seattle",
                "aliases": [],
                "seattle_relationship": "within_city",
                "seattle_explanation": "Synthetic future ballot style fixture.",
            },
        ]
    )
    seed = _write_seed(tmp_path, "jurisdiction-families", payload)
    configuration, _ = initialize_election(seed, tmp_path / "jurisdiction-families.json")
    assert {item.kind for item in configuration.jurisdictions} >= {
        "judicial_district",
        "ballot_style",
    }


def test_initialized_configuration_feeds_generic_offline_inventory_import(
    tmp_path: Path,
    monkeypatch: Any,
) -> None:
    def reject_fetch(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("initialized inventory import must not fetch")

    monkeypatch.setattr("election_guide.cli.fetch_http", reject_fetch)
    configuration_path = tmp_path / "configuration.json"
    initialize_election(FIXTURE, configuration_path)
    first_output = tmp_path / "inventory.json"
    first = runner.invoke(
        app,
        [
            "inventory",
            "import-initialized",
            str(configuration_path),
            "--manifest",
            str(BALLOT_MANIFEST),
            "--ballot-choices",
            str(BALLOT_FIXTURE),
            "--output",
            str(first_output),
        ],
    )

    assert first.exit_code == 0, first.output
    assert "initialized inventory: created" in first.output
    inventory = read_inventory(first_output)
    assert inventory.schema_version == "1.1"
    assert inventory.election.id == "wa-2027-seattle-general"
    assert [race.id for race in inventory.races] == [
        "seattle-city-attorney",
        "seattle-mayor",
    ]
    assert sum(len(race.choices) for race in inventory.races) == 4
    assert all(race.election_id == inventory.election.id for race in inventory.races)
    assert [choice.id for race in inventory.races for choice in race.choices] == [
        "seattle-city-attorney--alexis-example",
        "seattle-city-attorney--bailey-sample",
        "seattle-mayor--morgan-example",
        "seattle-mayor--riley-sample",
    ]
    assert inventory.election.source_ids == ["fixture-2027-municipal-configuration"]
    assert all(
        race.source_ids == ["fixture-2027-municipal-configuration"] for race in inventory.races
    )
    assert all(
        choice.source_ids == ["fixture-2027-municipal-ballot"]
        for race in inventory.races
        for choice in race.choices
    )

    second_output = tmp_path / "inventory-second.json"
    second = runner.invoke(
        app,
        [
            "inventory",
            "import-initialized",
            str(configuration_path),
            "--manifest",
            str(BALLOT_MANIFEST),
            "--ballot-choices",
            str(BALLOT_FIXTURE),
            "--output",
            str(second_output),
        ],
    )
    assert second.exit_code == 0, second.output
    assert first_output.read_bytes() == second_output.read_bytes()

    unchanged = runner.invoke(
        app,
        [
            "inventory",
            "import-initialized",
            str(configuration_path),
            "--manifest",
            str(BALLOT_MANIFEST),
            "--ballot-choices",
            str(BALLOT_FIXTURE),
            "--output",
            str(first_output),
        ],
    )
    assert unchanged.exit_code == 0, unchanged.output
    assert "initialized inventory: unchanged" in unchanged.output


def test_initialized_inventory_output_rejects_symlink_without_overwriting_target(
    tmp_path: Path,
) -> None:
    configuration_path = tmp_path / "configuration.json"
    initialize_election(FIXTURE, configuration_path)
    external = tmp_path / "external.txt"
    external.write_text("DO NOT OVERWRITE", encoding="utf-8")
    output = tmp_path / "inventory.json"
    output.symlink_to(external)

    result = runner.invoke(
        app,
        [
            "inventory",
            "import-initialized",
            str(configuration_path),
            "--manifest",
            str(BALLOT_MANIFEST),
            "--ballot-choices",
            str(BALLOT_FIXTURE),
            "--output",
            str(output),
        ],
    )

    assert result.exit_code == 1
    assert "refusing non-regular initialized inventory output" in result.output
    assert external.read_text(encoding="utf-8") == "DO NOT OVERWRITE"


def test_initialized_inventory_rejects_extra_csv_fields_even_with_matching_hash(
    tmp_path: Path,
) -> None:
    configuration_path = tmp_path / "configuration.json"
    initialize_election(FIXTURE, configuration_path)
    ballot = tmp_path / "ballot.csv"
    content = BALLOT_FIXTURE.read_text(encoding="utf-8").replace(
        "Fixture ballot row 1",
        "Fixture ballot row 1,SMUGGLED",
    )
    ballot.write_text(content, encoding="utf-8")
    manifest = cast(dict[str, Any], yaml.safe_load(BALLOT_MANIFEST.read_text(encoding="utf-8")))
    source = cast(dict[str, Any], manifest["ballot_source"])
    source["sha256"] = hashlib.sha256(ballot.read_bytes()).hexdigest()
    manifest_path = tmp_path / "manifest.yaml"
    manifest_path.write_text(yaml.safe_dump(manifest, sort_keys=False), encoding="utf-8")

    result = runner.invoke(
        app,
        [
            "inventory",
            "import-initialized",
            str(configuration_path),
            "--manifest",
            str(manifest_path),
            "--ballot-choices",
            str(ballot),
            "--output",
            str(tmp_path / "inventory.json"),
        ],
    )

    assert result.exit_code == 1
    assert "row 2 has extra fields" in result.output


def test_initialized_inventory_writer_revalidates_mutated_models(tmp_path: Path) -> None:
    configuration_path = tmp_path / "configuration.json"
    initialize_election(FIXTURE, configuration_path)
    inventory = import_initialized_inventory(
        configuration_path,
        BALLOT_MANIFEST,
        BALLOT_FIXTURE,
    )
    inventory.races[0].choices[0].race_id = "fabricated-race"
    output = tmp_path / "invalid-inventory.json"

    with pytest.raises(ValueError, match="belongs to 'fabricated-race'"):
        write_initialized_inventory(inventory, output)

    assert not output.exists()


def test_initialization_rejects_drift_unknown_topology_and_unsafe_policy_paths(
    tmp_path: Path,
) -> None:
    output = tmp_path / "configuration.json"
    initialize_election(FIXTURE, output)
    original = output.read_bytes()

    drifted = _seed_payload()
    drifted["election"]["name"] = "Drifted election name"
    drifted_seed = tmp_path / "drifted.yaml"
    drifted_seed.write_text(yaml.safe_dump(drifted, sort_keys=False), encoding="utf-8")
    drifted_result = runner.invoke(
        app, ["election", "init", str(drifted_seed), "--output", str(output)]
    )
    assert drifted_result.exit_code == 1
    assert "refusing to replace different election configuration" in drifted_result.output
    assert output.read_bytes() == original

    unknown = _seed_payload()
    unknown["races"][0]["jurisdiction_id"] = "unknown-city"
    unknown_seed = tmp_path / "unknown.yaml"
    unknown_seed.write_text(yaml.safe_dump(unknown, sort_keys=False), encoding="utf-8")
    unknown_result = runner.invoke(
        app,
        ["election", "init", str(unknown_seed), "--output", str(tmp_path / "unknown.json")],
    )
    assert unknown_result.exit_code == 1
    assert "unknown jurisdiction" in unknown_result.output

    unknown_parent = _seed_payload()
    unknown_parent["jurisdictions"][1]["parent_id"] = "unknown-parent"
    unknown_parent_seed = tmp_path / "unknown-parent.yaml"
    unknown_parent_seed.write_text(
        yaml.safe_dump(unknown_parent, sort_keys=False), encoding="utf-8"
    )
    unknown_parent_result = runner.invoke(
        app,
        [
            "election",
            "init",
            str(unknown_parent_seed),
            "--output",
            str(tmp_path / "unknown-parent.json"),
        ],
    )
    assert unknown_parent_result.exit_code == 1
    assert "unknown parent" in unknown_parent_result.output

    cycle = _seed_payload()
    cycle["jurisdictions"][0]["parent_id"] = "city-of-seattle"
    cycle_seed = tmp_path / "cycle.yaml"
    cycle_seed.write_text(yaml.safe_dump(cycle, sort_keys=False), encoding="utf-8")
    cycle_result = runner.invoke(
        app,
        ["election", "init", str(cycle_seed), "--output", str(tmp_path / "cycle.json")],
    )
    assert cycle_result.exit_code == 1
    assert "hierarchy contains a cycle" in cycle_result.output

    unsafe = _seed_payload()
    unsafe["scoring_policy"]["path"] = "../outside.yaml"
    unsafe_seed = tmp_path / "unsafe.yaml"
    unsafe_seed.write_text(yaml.safe_dump(unsafe, sort_keys=False), encoding="utf-8")
    unsafe_result = runner.invoke(
        app,
        ["election", "init", str(unsafe_seed), "--output", str(tmp_path / "unsafe.json")],
    )
    assert unsafe_result.exit_code == 1
    assert "canonical and relative" in unsafe_result.output


def _seed_payload() -> dict[str, Any]:
    loaded: object = yaml.safe_load(FIXTURE.read_text(encoding="utf-8"))
    assert isinstance(loaded, dict)
    return cast(dict[str, Any], loaded)


def _scope_payload(scope: str) -> dict[str, Any]:
    payload = _seed_payload()
    payload["election"]["election_scope"] = scope
    if scope == "municipal":
        return payload
    if scope == "county":
        payload["election"]["target_jurisdiction_ids"] = ["king-county"]
        for index, race in enumerate(payload["races"], 1):
            race.update(
                {
                    "id": f"king-county-office-{index}",
                    "jurisdiction_id": "king-county",
                    "district": "King County",
                    "office": f"County Office {index}",
                    "display_name": f"King County Office {index}",
                    "aliases": [],
                }
            )
        return payload
    if scope == "statewide":
        payload["election"]["target_jurisdiction_ids"] = ["washington-state"]
        for index, race in enumerate(payload["races"], 1):
            race.update(
                {
                    "id": f"washington-office-{index}",
                    "jurisdiction_id": "washington-state",
                    "district": "Washington State",
                    "office": f"State Office {index}",
                    "display_name": f"Washington State Office {index}",
                    "aliases": [],
                }
            )
        return payload
    payload["election"]["target_jurisdiction_ids"] = [
        "city-of-seattle",
        "king-county",
        "washington-state",
    ]
    payload["races"][1].update(
        {
            "id": "king-county-executive",
            "jurisdiction_id": "king-county",
            "district": "King County",
            "office": "County Executive",
            "display_name": "King County Executive",
            "aliases": [],
        }
    )
    payload["races"].append(
        {
            "id": "washington-governor",
            "jurisdiction_id": "washington-state",
            "race_type": "candidate",
            "district": "Washington State",
            "office": "Governor",
            "position": None,
            "display_name": "Washington Governor",
            "aliases": [],
            "publication_eligible": True,
        }
    )
    return payload


def _write_seed(tmp_path: Path, name: str, payload: dict[str, Any]) -> Path:
    path = tmp_path / f"{name}.yaml"
    path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")
    return path


def _initialize_result(tmp_path: Path, seed: Path):
    return runner.invoke(
        app,
        ["election", "init", str(seed), "--output", str(tmp_path / f"{seed.stem}.json")],
    )


def _assert_no_candidate_data(value: object) -> None:
    if isinstance(value, dict):
        mapping = cast(dict[object, object], value)
        assert "candidates" not in mapping
        assert "choices" not in mapping
        for nested in mapping.values():
            _assert_no_candidate_data(nested)
    elif isinstance(value, list):
        for nested in cast(list[object], value):
            _assert_no_candidate_data(nested)
