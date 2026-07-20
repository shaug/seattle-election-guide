"""Materialize a future inventory from initialized IDs and canonical offline ballot rows."""

from __future__ import annotations

import csv
import hashlib
import io
import re
from collections import defaultdict
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, ConfigDict, ValidationError

from election_guide.initialization.builder import (
    parse_election_configuration,
    write_once_or_verify,
)
from election_guide.initialization.models import ID_PATTERN, ElectionRaceDeclaration
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
from election_guide.serialization import canonical_json_bytes, read_yaml
from election_guide.validation import media_type_essence

CANONICAL_COLUMNS = (
    "race_id",
    "choice_id",
    "choice_type",
    "official_name",
    "display_name",
    "aliases",
    "ballot_order",
    "party_preference",
    "evidence_locator",
)


class InitializedInputModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class InitializedInventoryInput(InitializedInputModel):
    schema_version: Literal["1.0"] = "1.0"
    election_id: str
    adapter_id: Literal["canonical-ballot-csv"]
    adapter_version: Literal["1.0"]
    configuration_source: SourceReference
    ballot_source: SourceReference


def import_initialized_inventory(
    configuration_path: Path,
    manifest_path: Path,
    ballot_path: Path,
) -> Inventory:
    """Join initialized topology to hash-verified canonical ballot rows without network access."""
    manifest = _read_manifest(manifest_path)
    configuration_bytes = configuration_path.read_bytes()
    _verify_hash(
        configuration_bytes,
        manifest.configuration_source,
        "initialized election configuration",
    )
    configuration = parse_election_configuration(configuration_bytes)
    if manifest.election_id != configuration.election.id:
        raise ValueError(
            f"ballot input belongs to {manifest.election_id!r}, not {configuration.election.id!r}"
        )
    if media_type_essence(manifest.configuration_source.media_type) != "application/json":
        raise ValueError("initialized configuration source must use application/json media type")
    if media_type_essence(manifest.ballot_source.media_type) != "text/csv":
        raise ValueError("canonical ballot input must use text/csv media type")
    ballot_bytes = ballot_path.read_bytes()
    _verify_hash(ballot_bytes, manifest.ballot_source, "canonical ballot")

    rows = _read_rows(ballot_bytes)
    declared_by_id = {race.id: race for race in configuration.races}
    rows_by_race: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in rows:
        race_id = row["race_id"]
        if race_id not in declared_by_id:
            raise ValueError(f"canonical ballot row references undeclared race {race_id!r}")
        rows_by_race[race_id].append(row)
    missing = sorted(set(declared_by_id) - set(rows_by_race))
    if missing:
        raise ValueError(f"declared races have no canonical ballot rows: {missing}")
    if not declared_by_id:
        raise ValueError("inventory materialization requires at least one declared race")

    configuration_source_id = manifest.configuration_source.id
    ballot_source_id = manifest.ballot_source.id
    election = Election(
        id=configuration.election.id,
        name=configuration.election.name,
        election_type=configuration.election.election_type,
        election_date=configuration.election.election_date,
        state=configuration.election.state,
        official_url=configuration.election.official_url,
        source_ids=[configuration_source_id],
    )
    jurisdictions = [
        Jurisdiction(
            id=item.id,
            name=item.name,
            kind=item.kind,
            parent_id=item.parent_id,
            aliases=item.aliases,
            seattle_applicability=SeattleApplicability(
                relationship=item.seattle_relationship,
                explanation=item.seattle_explanation,
                source_ids=[configuration_source_id],
            ),
            source_ids=[configuration_source_id],
        )
        for item in configuration.jurisdictions
    ]
    races = [
        _materialized_race(
            configuration.election.id,
            declaration,
            rows_by_race[declaration.id],
            configuration_source_id,
            ballot_source_id,
        )
        for declaration in configuration.races
    ]
    return Inventory(
        schema_version="1.1",
        election=election,
        sources=[manifest.configuration_source, manifest.ballot_source],
        jurisdictions=jurisdictions,
        races=races,
        coverage_checks=[
            CoverageCheck(
                source_id=configuration_source_id,
                rule="race declarations in the hash-verified initialized configuration",
                matched_races=len(races),
                matched_choices=0,
            ),
            CoverageCheck(
                source_id=ballot_source_id,
                rule="canonical ballot choices joined to exact initialized race IDs",
                matched_races=0,
                matched_choices=sum(len(race.choices) for race in races),
            ),
        ],
        selection_method=SelectionMethod(
            target=configuration.election.election_scope,
            rule=(
                "include every initialized race with one or more hash-verified canonical ballot "
                "rows; retain the initialized publication eligibility flag"
            ),
            exclusions=[],
            source_ids=[configuration_source_id, ballot_source_id],
        ),
    )


def write_initialized_inventory(inventory: Inventory, output_path: Path) -> bool:
    """Exclusively create one canonical initialized inventory or verify identical bytes."""
    validated = Inventory.model_validate(inventory.model_dump(mode="json"))
    content = canonical_json_bytes(validated.model_dump(mode="json"))
    return write_once_or_verify(output_path, content, "initialized inventory")


def _verify_hash(content: bytes, source: SourceReference, label: str) -> None:
    expected = source.storage_sha256 or source.sha256
    actual = hashlib.sha256(content).hexdigest()
    if actual != expected:
        raise ValueError(f"{label} SHA-256 mismatch: expected {expected}, got {actual}")


def _read_manifest(path: Path) -> InitializedInventoryInput:
    try:
        raw: Any = read_yaml(path)
        return InitializedInventoryInput.model_validate(raw)
    except (OSError, UnicodeError, yaml.YAMLError, ValidationError) as error:
        raise ValueError(f"invalid initialized inventory input manifest: {error}") from error


def _read_rows(content: bytes) -> list[dict[str, str]]:
    try:
        decoded = content.decode("utf-8-sig")
    except UnicodeError as error:
        raise ValueError("canonical ballot CSV must be UTF-8") from error
    with io.StringIO(decoded, newline="") as handle:
        reader = csv.DictReader(handle)
        actual_columns = tuple(reader.fieldnames or ())
        if actual_columns != CANONICAL_COLUMNS:
            raise ValueError(
                "canonical ballot CSV columns must exactly equal "
                f"{list(CANONICAL_COLUMNS)}, got {list(actual_columns)}"
            )
        rows: list[dict[str, str]] = []
        for row_number, row in enumerate(reader, 2):
            if None in row:
                raise ValueError(f"canonical ballot CSV row {row_number} has extra fields")
            values: dict[str, str] = {}
            for key in CANONICAL_COLUMNS:
                value = row.get(key)
                if not isinstance(value, str):
                    raise ValueError(
                        f"canonical ballot CSV row {row_number} is missing field {key!r}"
                    )
                values[key] = value
            rows.append(values)
    if not rows:
        raise ValueError("canonical ballot CSV must contain at least one row")
    return rows


def _materialized_race(
    election_id: str,
    declaration: ElectionRaceDeclaration,
    rows: list[dict[str, str]],
    configuration_source_id: str,
    ballot_source_id: str,
) -> Race:
    expected_choice_type = "ballot_option" if declaration.race_type == "measure" else "candidate"
    choices: list[BallotChoice] = []
    for row in rows:
        if row["choice_type"] != expected_choice_type:
            raise ValueError(
                f"race {declaration.id!r} requires choice type {expected_choice_type!r}"
            )
        official_name = _nonblank(row["official_name"], "official_name")
        display_name = _nonblank(row["display_name"], "display_name")
        evidence_locator = _nonblank(row["evidence_locator"], "evidence_locator")
        choice_id = _stable_choice_id(row["choice_id"])
        aliases = [item.strip() for item in row["aliases"].split("|") if item.strip()]
        if aliases != sorted(set(aliases)):
            raise ValueError(f"race {declaration.id!r} choice aliases must be unique and sorted")
        try:
            ballot_order = int(row["ballot_order"])
        except ValueError as error:
            raise ValueError("ballot_order must be a canonical positive integer") from error
        if str(ballot_order) != row["ballot_order"] or ballot_order < 1:
            raise ValueError("ballot_order must be a canonical positive integer")
        choices.append(
            BallotChoice(
                id=f"{declaration.id}--{choice_id}",
                race_id=declaration.id,
                choice_type=expected_choice_type,
                official_name=official_name,
                display_name=display_name,
                aliases=aliases,
                ballot_order=ballot_order,
                party_preference=row["party_preference"].strip() or None,
                source_ids=[ballot_source_id],
                evidence_locator=evidence_locator,
            )
        )
    choices.sort(key=lambda item: item.ballot_order)
    return Race(
        id=declaration.id,
        election_id=election_id,
        jurisdiction_id=declaration.jurisdiction_id,
        race_type=declaration.race_type,
        district=declaration.district,
        office=declaration.office,
        position=declaration.position,
        display_name=declaration.display_name,
        aliases=declaration.aliases,
        publication_eligible=declaration.publication_eligible,
        source_ids=[configuration_source_id],
        evidence_locator=f"initialized election configuration race id={declaration.id!r}",
        choices=choices,
    )


def _nonblank(value: str, label: str) -> str:
    normalized = value.strip()
    if not normalized:
        raise ValueError(f"{label} must not be blank")
    return normalized


def _stable_choice_id(value: str) -> str:
    normalized = _nonblank(value, "choice_id")
    if re.fullmatch(ID_PATTERN, normalized) is None:
        raise ValueError("choice_id must be a stable lowercase slug")
    return normalized
