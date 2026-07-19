"""Deterministically import official King County ballot files."""

from __future__ import annotations

import csv
import hashlib
import json
import re
from collections import defaultdict
from pathlib import Path
from typing import cast

import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator

from election_guide.inventory.models import (
    BallotChoice,
    CoverageCheck,
    Election,
    Inventory,
    Jurisdiction,
    Race,
    SeattleApplicability,
    SelectionMethod,
    SourceReference,
)


class ImportModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class InputSource(ImportModel):
    input_key: str | None = None
    extract_filename: str | None = None
    reference: SourceReference


class RaceSelector(ImportModel):
    id: str
    source_jurisdiction: str
    source_office: str
    jurisdiction_id: str
    district: str
    office: str
    position: str | None = None
    display_name: str
    aliases: list[str]
    publication_eligible: bool = True
    source_ids: list[str]


class MeasureChoice(ImportModel):
    official_name: str
    display_name: str
    aliases: list[str] = Field(default_factory=list)
    ballot_order: int


class Measure(ImportModel):
    id: str
    jurisdiction_id: str
    district: str
    office: str
    position: str | None = None
    display_name: str
    aliases: list[str]
    publication_eligible: bool = True
    source_ids: list[str]
    evidence_locator: str
    choices: list[MeasureChoice]


class PcoImport(ImportModel):
    input_key: str
    source_id: str
    precinct_prefix: str
    expected_races: int
    expected_choices: int
    party_label: str
    publication_eligible: bool = False
    evidence_source_ids: list[str]


class ImportConfiguration(ImportModel):
    election: Election
    sources: list[InputSource]
    jurisdictions: list[Jurisdiction]
    candidate_input_key: str
    precinct_crosswalk_input_key: str
    precinct_crosswalk_source_id: str
    race_selectors: list[RaceSelector]
    sample_ballot_pages: dict[str, int]
    measures: list[Measure]
    pco_imports: list[PcoImport]
    selection_method: SelectionMethod

    @model_validator(mode="after")
    def validate_input_bindings(self) -> ImportConfiguration:
        keyed_sources = [source for source in self.sources if source.input_key is not None]
        input_keys = [source.input_key for source in keyed_sources]
        if len(input_keys) != len(set(input_keys)):
            raise ValueError("input source keys must be unique")
        source_ids = [source.reference.id for source in self.sources]
        if len(source_ids) != len(set(source_ids)):
            raise ValueError("source ids must be unique")

        source_by_input = {
            source.input_key: source.reference for source in keyed_sources if source.input_key
        }
        candidate_source = source_by_input.get(self.candidate_input_key)
        if candidate_source is None:
            raise ValueError(f"candidate input {self.candidate_input_key!r} has no source")
        crosswalk_source = source_by_input.get(self.precinct_crosswalk_input_key)
        if crosswalk_source is None:
            raise ValueError(
                f"precinct crosswalk input {self.precinct_crosswalk_input_key!r} has no source"
            )
        if crosswalk_source.id != self.precinct_crosswalk_source_id:
            raise ValueError(
                f"precinct crosswalk input {self.precinct_crosswalk_input_key!r} is bound to "
                f"{crosswalk_source.id!r}, not {self.precinct_crosswalk_source_id!r}"
            )

        selector_keys = [
            (selector.source_jurisdiction, selector.source_office)
            for selector in self.race_selectors
        ]
        if len(selector_keys) != len(set(selector_keys)):
            raise ValueError("race selectors must use unique source jurisdiction and office pairs")
        selector_ids = {selector.id for selector in self.race_selectors}
        if set(self.sample_ballot_pages) != selector_ids:
            raise ValueError("sample ballot page keys must exactly match race selector ids")
        if any(page < 1 for page in self.sample_ballot_pages.values()):
            raise ValueError("sample ballot pages must be positive")
        for selector in self.race_selectors:
            if candidate_source.id not in selector.source_ids:
                raise ValueError(
                    f"selector {selector.id!r} must cite candidate source {candidate_source.id!r}"
                )

        for pco in self.pco_imports:
            source = source_by_input.get(pco.input_key)
            if source is None:
                raise ValueError(f"PCO input {pco.input_key!r} has no source")
            if source.id != pco.source_id:
                raise ValueError(
                    f"PCO input {pco.input_key!r} is bound to {source.id!r}, not {pco.source_id!r}"
                )
            if self.precinct_crosswalk_source_id not in pco.evidence_source_ids:
                raise ValueError(
                    f"PCO input {pco.input_key!r} must cite precinct crosswalk "
                    f"{self.precinct_crosswalk_source_id!r}"
                )
        return self


CANDIDATE_COLUMNS = {
    "Jurisdiction Name",
    "Office",
    "Candidate",
    "Party Preference",
    "Ballot Order",
}
PCO_COLUMNS = {"Leg District", "Precinct", "Office & Party", "Candidate", "Ballot Order"}
PRECINCT_COLUMNS = {"PrecinctName", "CityName", "SeattleCouncilDistrict"}
SAFE_COLUMNS_BY_INPUT = {
    "candidates": [
        "Jurisdiction Name",
        "Office",
        "Candidate",
        "Party Preference",
        "Ballot Order",
    ],
    "pco_democrats": [
        "Leg District",
        "Precinct",
        "Office & Party",
        "Candidate",
        "Ballot Order",
    ],
    "pco_republicans": [
        "Leg District",
        "Precinct",
        "Office & Party",
        "Candidate",
        "Ballot Order",
    ],
}


def import_inventory(config_path: Path, inputs: dict[str, Path]) -> Inventory:
    """Build a validated inventory from captured official files."""
    raw_config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    config = ImportConfiguration.model_validate(raw_config)
    source_by_input = {
        source.input_key: source.reference
        for source in config.sources
        if source.input_key is not None
    }
    for input_key, source in source_by_input.items():
        if input_key not in inputs:
            raise ValueError(f"missing input file for {input_key!r}")
        expected_hash = source.storage_sha256 or source.sha256
        actual_hash = _sha256(inputs[input_key])
        if actual_hash != expected_hash:
            raise ValueError(
                f"{input_key!r} SHA-256 mismatch: expected {expected_hash}, got {actual_hash}"
            )

    candidate_source = source_by_input.get(config.candidate_input_key)
    if candidate_source is None:
        raise ValueError(f"candidate input {config.candidate_input_key!r} has no source")
    candidate_rows = _read_csv(inputs[config.candidate_input_key], CANDIDATE_COLUMNS)
    precinct_rows = _read_csv(inputs[config.precinct_crosswalk_input_key], PRECINCT_COLUMNS)
    seattle_precincts = _validated_seattle_precincts(precinct_rows)

    races: list[Race] = []
    for selector in config.race_selectors:
        matched = [
            row
            for row in candidate_rows
            if row["Jurisdiction Name"] == selector.source_jurisdiction
            and row["Office"] == selector.source_office
        ]
        if not matched:
            raise ValueError(
                f"selector {selector.id!r} matched no candidate rows "
                f"for {selector.source_jurisdiction!r} / {selector.source_office!r}"
            )
        races.append(
            _candidate_race(
                config.election.id,
                selector,
                matched,
                config.sample_ballot_pages[selector.id],
            )
        )

    jurisdictions = list(config.jurisdictions)
    coverage_checks = [
        CoverageCheck(
            source_id=candidate_source.id,
            rule="exact configured jurisdiction and office selectors",
            matched_races=len(config.race_selectors),
            matched_choices=sum(len(race.choices) for race in races),
        )
    ]

    for measure in config.measures:
        races.append(_measure_race(config.election.id, measure))

    for pco in config.pco_imports:
        pco_rows = _read_csv(inputs[pco.input_key], PCO_COLUMNS)
        new_jurisdictions, pco_races = _pco_races(
            config.election.id, pco, pco_rows, seattle_precincts
        )
        if len(pco_races) != pco.expected_races:
            raise ValueError(
                f"{pco.input_key!r} matched {len(pco_races)} PCO races; "
                f"expected {pco.expected_races}"
            )
        choice_count = sum(len(race.choices) for race in pco_races)
        if choice_count != pco.expected_choices:
            raise ValueError(
                f"{pco.input_key!r} matched {choice_count} PCO choices; "
                f"expected {pco.expected_choices}"
            )
        jurisdictions.extend(new_jurisdictions)
        races.extend(pco_races)
        coverage_checks.append(
            CoverageCheck(
                source_id=pco.source_id,
                rule="precinct appears in the official City of Seattle crosswalk",
                matched_races=len(pco_races),
                matched_choices=choice_count,
            )
        )

    inventory = Inventory(
        election=config.election,
        sources=[source.reference for source in config.sources],
        jurisdictions=sorted(jurisdictions, key=lambda item: item.id),
        races=sorted(races, key=lambda item: item.id),
        coverage_checks=coverage_checks,
        selection_method=config.selection_method,
    )
    return inventory


def write_inventory(inventory: Inventory, output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    payload = inventory.model_dump(mode="json")
    output_path.write_text(
        json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def read_inventory(path: Path) -> Inventory:
    return Inventory.model_validate_json(path.read_text(encoding="utf-8"))


def extract_public_inputs(
    config_path: Path, raw_inputs: dict[str, Path], output_dir: Path
) -> list[Path]:
    """Create deterministic, privacy-stripped CSVs from hash-verified official files."""
    raw_config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    config = ImportConfiguration.model_validate(raw_config)
    source_by_input = {
        source.input_key: source for source in config.sources if source.input_key is not None
    }
    outputs: list[Path] = []
    output_dir.mkdir(parents=True, exist_ok=True)
    for input_key, columns in SAFE_COLUMNS_BY_INPUT.items():
        source = source_by_input.get(input_key)
        if source is None or input_key not in raw_inputs:
            raise ValueError(f"missing configured raw input {input_key!r}")
        if source.extract_filename is None:
            raise ValueError(f"input {input_key!r} has no extract filename")
        actual_hash = _sha256(raw_inputs[input_key])
        if actual_hash != source.reference.sha256:
            raise ValueError(
                f"raw {input_key!r} SHA-256 mismatch: expected "
                f"{source.reference.sha256}, got {actual_hash}"
            )
        rows = _read_csv(raw_inputs[input_key], set(columns))
        output_path = output_dir / source.extract_filename
        with output_path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=columns, lineterminator="\n")
            writer.writeheader()
            writer.writerows({column: row[column] for column in columns} for row in rows)
        outputs.append(output_path)
    return outputs


def _read_csv(path: Path, required_columns: set[str]) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        actual = set(reader.fieldnames or [])
        missing = required_columns - actual
        if missing:
            raise ValueError(f"{path} is missing required columns: {sorted(missing)}")
        return [
            {key: value or "" for key, value in cast(dict[str, str | None], row).items()}
            for row in reader
        ]


def _validated_seattle_precincts(rows: list[dict[str, str]]) -> set[str]:
    assignments: dict[str, tuple[str, str]] = {}
    for row in rows:
        precinct = row["PrecinctName"]
        assignment = (row["CityName"], row["SeattleCouncilDistrict"])
        if precinct in assignments:
            raise ValueError(
                f"precinct crosswalk repeats {precinct!r}: "
                f"{assignments[precinct]!r} and {assignment!r}"
            )
        assignments[precinct] = assignment
    return {
        precinct
        for precinct, (city, council_district) in assignments.items()
        if city == "Seattle" and council_district
    }


def _candidate_race(
    election_id: str,
    selector: RaceSelector,
    rows: list[dict[str, str]],
    sample_ballot_page: int,
) -> Race:
    choices = [
        BallotChoice(
            id=f"{selector.id}--{_slug(row['Candidate'])}",
            race_id=selector.id,
            choice_type="candidate",
            official_name=row["Candidate"],
            display_name=row["Candidate"],
            aliases=[],
            ballot_order=int(row["Ballot Order"]),
            party_preference=row["Party Preference"] or None,
            source_ids=selector.source_ids,
            evidence_locator=(
                f"candidate CSV row: Jurisdiction Name={selector.source_jurisdiction!r}, "
                f"Office={selector.source_office!r}, Candidate={row['Candidate']!r}, "
                f"Ballot Order={row['Ballot Order']!r}; composite sample ballot page "
                f"{sample_ballot_page}"
            ),
        )
        for row in rows
    ]
    choices.sort(key=lambda item: item.ballot_order)
    return Race(
        id=selector.id,
        election_id=election_id,
        jurisdiction_id=selector.jurisdiction_id,
        race_type="candidate",
        district=selector.district,
        office=selector.office,
        position=selector.position,
        display_name=selector.display_name,
        aliases=selector.aliases,
        publication_eligible=selector.publication_eligible,
        source_ids=selector.source_ids,
        evidence_locator=(
            f"candidate CSV: Jurisdiction Name={selector.source_jurisdiction!r}, "
            f"Office={selector.source_office!r}; composite sample ballot page "
            f"{sample_ballot_page}"
        ),
        choices=choices,
    )


def _measure_race(election_id: str, measure: Measure) -> Race:
    return Race(
        id=measure.id,
        election_id=election_id,
        jurisdiction_id=measure.jurisdiction_id,
        race_type="measure",
        district=measure.district,
        office=measure.office,
        position=measure.position,
        display_name=measure.display_name,
        aliases=measure.aliases,
        publication_eligible=measure.publication_eligible,
        source_ids=measure.source_ids,
        evidence_locator=measure.evidence_locator,
        choices=[
            BallotChoice(
                id=f"{measure.id}--{_slug(choice.official_name)}",
                race_id=measure.id,
                choice_type="ballot_option",
                official_name=choice.official_name,
                display_name=choice.display_name,
                aliases=choice.aliases,
                ballot_order=choice.ballot_order,
                source_ids=measure.source_ids,
                evidence_locator=(
                    f"{measure.evidence_locator}; ballot option={choice.official_name!r}"
                ),
            )
            for choice in measure.choices
        ],
    )


def _pco_races(
    election_id: str,
    config: PcoImport,
    rows: list[dict[str, str]],
    seattle_precincts: set[str],
) -> tuple[list[Jurisdiction], list[Race]]:
    prefixed = [row for row in rows if row["Precinct"].startswith(config.precinct_prefix)]
    unknown_precincts = sorted({row["Precinct"] for row in prefixed} - seattle_precincts)
    if unknown_precincts:
        raise ValueError(
            "PCO rows use precincts absent from the official Seattle crosswalk: "
            f"{unknown_precincts}"
        )
    selected = [row for row in rows if row["Precinct"] in seattle_precincts]
    groups: dict[tuple[str, str, str], list[dict[str, str]]] = defaultdict(list)
    for row in selected:
        groups[(row["Leg District"], row["Precinct"], row["Office & Party"])].append(row)

    jurisdictions: list[Jurisdiction] = []
    races: list[Race] = []
    for (legislative_district, precinct, source_office), candidates in sorted(groups.items()):
        precinct_id = f"precinct-{_slug(precinct)}"
        race_id = f"pco-{_slug(config.party_label)}-{_slug(precinct)}"
        source_ids = list(dict.fromkeys([config.source_id, *config.evidence_source_ids]))
        jurisdictions.append(
            Jurisdiction(
                id=precinct_id,
                name=precinct,
                kind="precinct",
                parent_id="city-of-seattle",
                aliases=[],
                seattle_applicability=SeattleApplicability(
                    relationship="within_city",
                    explanation=(
                        f"The official King County precinct crosswalk maps {precinct!r} "
                        "to the City of Seattle."
                    ),
                    source_ids=source_ids,
                ),
                source_ids=source_ids,
            )
        )
        choices = [
            BallotChoice(
                id=f"{race_id}--{_slug(row['Candidate'])}",
                race_id=race_id,
                choice_type="candidate",
                official_name=row["Candidate"],
                display_name=row["Candidate"],
                aliases=[],
                ballot_order=int(row["Ballot Order"]),
                party_preference=config.party_label,
                source_ids=source_ids,
                evidence_locator=(
                    f"PCO CSV row: Precinct={precinct!r}, "
                    f"Office & Party={source_office!r}, Candidate={row['Candidate']!r}, "
                    f"Ballot Order={row['Ballot Order']!r}; precinct crosswalk: "
                    f"PrecinctName={precinct!r}, CityName='Seattle'"
                ),
            )
            for row in candidates
        ]
        choices.sort(key=lambda item: item.ballot_order)
        races.append(
            Race(
                id=race_id,
                election_id=election_id,
                jurisdiction_id=precinct_id,
                race_type="party_office",
                district=f"Legislative District {legislative_district}; {precinct}",
                office="Precinct Committee Officer",
                position=config.party_label,
                display_name=f"{precinct} {config.party_label} Precinct Committee Officer",
                aliases=[source_office],
                publication_eligible=config.publication_eligible,
                source_ids=source_ids,
                evidence_locator=(
                    f"PCO CSV: Precinct={precinct!r}, Office & Party={source_office!r}; "
                    f"precinct crosswalk: PrecinctName={precinct!r}, CityName='Seattle'; "
                    "composite sample ballot pages 8-12"
                ),
                choices=choices,
            )
        )
    return jurisdictions, races


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _slug(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.casefold()).strip("-")
    if not slug:
        raise ValueError(f"cannot create stable id from {value!r}")
    return slug
