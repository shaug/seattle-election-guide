"""Offline, hash-pinned major districts for Seattle's reviewed 2026 electorate."""

from __future__ import annotations

import csv
import hashlib
import io
import json
from dataclasses import dataclass
from pathlib import Path

from pydantic import BaseModel, ConfigDict

ROOT = Path(__file__).resolve().parents[3]
CONFIGURATION = ROOT / "config/elections/wa-2026-ballot-geography.json"


class GeographyConfiguration(BaseModel):
    model_config = ConfigDict(extra="forbid")
    schema_version: str
    election_ids: list[str]
    assignment_path: str
    assignment_sha256: str
    city_crosswalk_path: str
    city_crosswalk_sha256: str
    expected_district_codes: dict[str, list[str]]
    outside_target_jurisdiction_ids: list[str]
    review_record: str
    review_sha256: str
    inventory_notice: str


@dataclass(frozen=True)
class ReviewedGeography:
    districts: dict[str, tuple[str, ...]]
    outside_target_jurisdiction_ids: frozenset[str]
    configuration_hash: str
    inventory_notice: str


def _pinned_input(path: str, expected_hash: str) -> bytes:
    resolved = (ROOT / path).resolve()
    if not resolved.is_relative_to(ROOT / "data"):
        raise ValueError("geography inputs must remain inside repository data")
    content = resolved.read_bytes()
    if hashlib.sha256(content).hexdigest() != expected_hash:
        raise ValueError(f"reviewed geography input hash changed: {path}")
    return content


def reviewed_geography(election_id: str) -> ReviewedGeography | None:
    """No live fetch or contest-derived district list enters publication."""
    raw = CONFIGURATION.read_bytes()
    config = GeographyConfiguration.model_validate_json(raw)
    if config.schema_version != "1.0":
        raise ValueError("unsupported ballot geography schema")
    if election_id not in config.election_ids:
        return None
    assignments = list(
        csv.DictReader(
            io.StringIO(
                _pinned_input(config.assignment_path, config.assignment_sha256).decode("utf-8")
            )
        )
    )
    city = list(
        csv.DictReader(
            io.StringIO(
                _pinned_input(config.city_crosswalk_path, config.city_crosswalk_sha256).decode(
                    "utf-8"
                )
            )
        )
    )
    by_precinct = {row["PrecinctName"]: row for row in assignments}
    city_by_precinct = {row["PrecinctName"]: row for row in city}
    if (
        not assignments
        or len(by_precinct) != len(assignments)
        or len(city_by_precinct) != len(city)
    ):
        raise ValueError("geography assignments require unique precincts")
    if set(by_precinct) != set(city_by_precinct):
        raise ValueError("reviewed geography must cover exactly the official Seattle crosswalk")
    for name, row in by_precinct.items():
        official = city_by_precinct[name]
        if row["CityName"] != "Seattle" or official["CityName"] != "Seattle":
            raise ValueError("ballot geography must use explicit Seattle city membership")
        if row["SeattleCouncilDistrict"] != official["SeattleCouncilDistrict"]:
            raise ValueError("Seattle council assignments disagree with the official crosswalk")
    columns = {
        "congressional_district": "CongressionalDistrict",
        "legislative_district": "LegislativeDistrict",
        "county_council_district": "CountyCouncilDistrict",
        "city_council_district": "SeattleCouncilDistrict",
    }
    districts = {
        kind: tuple(sorted({row[column] for row in assignments}, key=int))
        for kind, column in columns.items()
    }
    if {kind: list(codes) for kind, codes in districts.items()} != config.expected_district_codes:
        raise ValueError("geography district universe changed without reviewed configuration")
    review = json.loads(_pinned_input(config.review_record, config.review_sha256))
    if review["join"]["normalized_assignment_sha256"] != config.assignment_sha256:
        raise ValueError("geography review must bind the exact normalized assignment extract")
    return ReviewedGeography(
        districts=districts,
        outside_target_jurisdiction_ids=frozenset(config.outside_target_jurisdiction_ids),
        configuration_hash=hashlib.sha256(raw).hexdigest(),
        inventory_notice=config.inventory_notice,
    )
