"""Admit offline, reviewed precinct geography for one explicitly checked election."""

import csv
import hashlib
import io
import json
from datetime import date, datetime
from pathlib import Path
from typing import Literal

from pydantic import model_validator

from election_guide.inventory.models import Inventory, InventoryModel, SourceReference

ROOT = Path(__file__).resolve().parents[3]
CATALOG_PATH = ROOT / "config/elections/wa-2026-general-precinct-ballots.json"
_SOURCE_IDS = {"precinct-assignments", "seattle-city-membership", "precinct-election-review"}


class PrecinctRecord(InventoryModel):
    code: str
    name: str
    jurisdiction_ids: list[str]


class ReviewedPrecinctCatalog(InventoryModel):
    schema_version: Literal["1.0"]
    election_id: Literal["wa-2026-general"]
    election_date: date
    reviewed_at: datetime
    sources: list[SourceReference]
    precincts: list[PrecinctRecord]

    @model_validator(mode="after")
    def unique_records(self) -> "ReviewedPrecinctCatalog":
        for field in ["code", "name"]:
            values = [getattr(p, field) for p in self.precincts]
            if not values or len(set(values)) != len(values):
                raise ValueError(f"precinct {field} values must be unique and nonempty")
        ids = [s.id for s in self.sources]
        if len(ids) != len(set(ids)) or set(ids) != _SOURCE_IDS:
            raise ValueError("precinct catalog requires its three reviewed sources")
        return self


def _source_bytes(source: SourceReference) -> bytes:
    path = (ROOT / source.storage_reference).resolve()
    if not path.is_relative_to(ROOT / "data"):
        raise ValueError("precinct inputs must remain inside repository data")
    content = path.read_bytes()
    if hashlib.sha256(content).hexdigest() != (source.storage_sha256 or source.sha256):
        raise ValueError(f"precinct source hash changed: {source.id}")
    return content


def read_precinct_catalog(path: Path, inventory: Inventory) -> ReviewedPrecinctCatalog:
    """Validate every record against pinned official facts; never fetch live data."""
    catalog = ReviewedPrecinctCatalog.model_validate_json(path.read_bytes())
    if (catalog.election_id, catalog.election_date) != (
        inventory.election.id,
        inventory.election.election_date,
    ):
        raise ValueError("precinct catalog belongs to another election")
    inputs = {s.id: _source_bytes(s) for s in catalog.sources}
    review = json.loads(inputs["precinct-election-review"])
    if (review["election_id"], review["election_date"]) != (
        catalog.election_id,
        catalog.election_date.isoformat(),
    ):
        raise ValueError("precinct review belongs to another election")
    rows = list(csv.DictReader(io.StringIO(inputs["precinct-assignments"].decode())))
    city = list(csv.DictReader(io.StringIO(inputs["seattle-city-membership"].decode())))
    by_name = {r["PrecinctName"]: r for r in rows}
    city_by_name = {r["PrecinctName"]: r for r in city}
    if (
        len(by_name) != len(rows)
        or len(city_by_name) != len(city)
        or by_name.keys() != city_by_name.keys()
    ):
        raise ValueError("precinct assignments must exactly cover the unique official city rows")
    expected: dict[str, tuple[str, set[str]]] = {}
    for name, row in by_name.items():
        official = city_by_name[name]
        if (
            row["CityName"] != "Seattle"
            or official["CityName"] != "Seattle"
            or row["SeattleCouncilDistrict"] != official["SeattleCouncilDistrict"]
        ):
            raise ValueError("precinct city assignments disagree")
        code = row["PrecinctCode"]
        if code in expected:
            raise ValueError("official precinct codes must be unique")
        expected[code] = (
            name,
            set(review["shared_jurisdiction_ids"])
            | {
                f"congressional-district-{row['CongressionalDistrict']}",
                f"legislative-district-{row['LegislativeDistrict']}",
                f"county-council-district-{row['CountyCouncilDistrict']}",
                f"seattle-city-council-district-{row['SeattleCouncilDistrict']}",
            },
        )
    if len(expected) != review["precinct_count"] or set(expected) != {
        p.code for p in catalog.precincts
    }:
        raise ValueError("precinct catalog must cover the entire reviewed electorate")
    for precinct in catalog.precincts:
        name, jurisdictions = expected[precinct.code]
        if (
            precinct.name != name
            or set(precinct.jurisdiction_ids) != jurisdictions
            or len(precinct.jurisdiction_ids) != len(jurisdictions)
        ):
            raise ValueError("precinct record differs from reviewed official assignments")
    covered = {j for _, ids in expected.values() for j in ids}
    outside = set(review["outside_covered_jurisdiction_ids"])
    if covered & outside:
        raise ValueError("outside jurisdiction overlaps reviewed precincts")
    unmapped = (
        {r.jurisdiction_id for r in inventory.races if r.publication_eligible} - covered - outside
    )
    if unmapped:
        raise ValueError(f"unmapped covered jurisdictions: {sorted(unmapped)}")
    return catalog
