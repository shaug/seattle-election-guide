"""Offline admission of reviewed historical geography, separate from archive facts."""

from __future__ import annotations

import csv
import hashlib
import io
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path, PurePosixPath
from typing import Any, Literal, cast

from pydantic import Field, field_validator, model_validator

from election_guide.evidence.models import CapturedManifest
from election_guide.evidence.storage import verify_capture
from election_guide.hosting.models import HistoricalCapabilityRef, HostingModel
from election_guide.inventory.models import Inventory
from election_guide.publication.models import PublicationViewModel
from election_guide.publication.precinct_ballot import (
    HistoricalPrecinctProvenance,
    PrecinctBallotContract,
    PrecinctContests,
)
from election_guide.release.models import ReleaseManifest
from election_guide.serialization import canonical_json_bytes, parse_json_bytes

CSV_COLUMNS = [
    "Precinct",
    "Race",
    "LegislativeDistrict",
    "CountyCouncil",
    "CongressionalDistrict",
    "SeattleCouncilDistrict",
    "CounterGroup",
    "CounterType",
    "Party Preference",
    "SumOfCount",
]
DISTRICT_COLUMNS = [
    "LegislativeDistrict",
    "CountyCouncil",
    "CongressionalDistrict",
    "SeattleCouncilDistrict",
]
DATASET_ID = "2ydw-3iau"
DATASET_TITLE = "August 2026 Primary Election - Final Precinct Results"
DATASET_DESCRIPTION = (
    "Final precinct level results for the August 4, 2026 Primary Election in King County, WA."
)


class SupplementSource(HostingModel):
    path: str
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")

    @field_validator("path")
    @classmethod
    def safe_source_path(cls, value: str) -> str:
        path = PurePosixPath(value)
        if (
            path.is_absolute()
            or ".." in path.parts
            or "\\" in value
            or path.as_posix() != value
            or not value.startswith("data/")
        ):
            raise ValueError("historical precinct source must be inside repository data")
        return value


class HistoricalPrecinctSupplement(HostingModel):
    schema_version: Literal["1.0"]
    election_id: Literal["wa-2026-primary"]
    election_date: date
    archive_release_version: str
    archive_git_commit: str = Field(pattern=r"^[0-9a-f]{40}$")
    archive_view_model_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    archive_inventory_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    reviewed_at: datetime
    application_id: Literal["literal_official_precinct_name"]
    source_csv: SupplementSource
    source_metadata: SupplementSource
    source_csv_capture: SupplementSource
    source_metadata_capture: SupplementSource
    source_acquisition: SupplementSource
    city_membership: SupplementSource
    race_mappings: dict[str, str] = Field(min_length=1)
    source_row_count: int = Field(gt=0, strict=True)
    source_precinct_count: int = Field(gt=0, strict=True)
    covered_pair_count: int = Field(gt=0, strict=True)
    mapping_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    precincts: list[PrecinctContests] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_identity(self) -> HistoricalPrecinctSupplement:
        if self.election_date != date(2026, 8, 4):
            raise ValueError("historical precinct supplement belongs to another election date")
        if self.reviewed_at.tzinfo is None:
            raise ValueError("historical precinct review must have a timezone")
        names = [p.name for p in self.precincts]
        if len(names) != len(set(names)) or any(p.code != p.name for p in self.precincts):
            raise ValueError("historical precinct application IDs must be unique literal names")
        if any(
            len(p.contest_ids) != len(set(p.contest_ids))
            or len(p.jurisdiction_ids) != len(set(p.jurisdiction_ids))
            for p in self.precincts
        ):
            raise ValueError("historical precinct membership repeats an identity")
        if len(set(self.race_mappings.values())) != len(self.race_mappings):
            raise ValueError("historical precinct race mapping must be unambiguous")
        if mapping_digest(self.precincts) != self.mapping_hash:
            raise ValueError("historical precinct normalized mapping hash differs")
        return self


def mapping_digest(precincts: list[PrecinctContests]) -> str:
    return hashlib.sha256(
        canonical_json_bytes([p.model_dump(mode="json") for p in precincts])
    ).hexdigest()


@dataclass(frozen=True)
class AdmittedPrecinctSupplement:
    raw: bytes
    declaration: HistoricalPrecinctSupplement

    def provenance(self, source_git_commit: str) -> HistoricalPrecinctProvenance:
        value = self.declaration
        return HistoricalPrecinctProvenance(
            election_id=value.election_id,
            source_git_commit=source_git_commit,
            artifact_path=f"e/{value.election_id}/precinct-supplement.json",
            artifact_sha256=hashlib.sha256(self.raw).hexdigest(),
            archive_view_model_sha256=value.archive_view_model_sha256,
            archive_inventory_sha256=value.archive_inventory_sha256,
            mapping_hash=value.mapping_hash,
        )

    def contract(self, source_git_commit: str) -> PrecinctBallotContract:
        return PrecinctBallotContract(
            election_id=self.declaration.election_id,
            mapping_hash=self.declaration.mapping_hash,
            endorsements_path=None,
            comparisons_path=None,
            sources_path=None,
            precincts=self.declaration.precincts,
            address_lookup=None,
            supplement=self.provenance(source_git_commit),
        )


def _source_bytes(repository: Path, source: SupplementSource) -> bytes:
    path = (repository / source.path).resolve()
    if not path.is_relative_to((repository / "data").resolve()):
        raise ValueError("historical precinct source escaped repository data")
    raw = path.read_bytes()
    if hashlib.sha256(raw).hexdigest() != source.sha256:
        raise ValueError(f"historical precinct source hash differs: {source.path}")
    return raw


def _verify_archive(
    value: HistoricalPrecinctSupplement,
    view: PublicationViewModel,
    manifest: ReleaseManifest,
    inventory_raw: dict[str, Any],
) -> Inventory:
    inventory = Inventory.model_validate(inventory_raw)
    if (
        view.metadata.election_id != value.election_id
        or view.metadata.election_date != value.election_date.isoformat()
        or inventory.election.id != value.election_id
        or inventory.election.election_date != value.election_date
        or inventory.election.election_type != "primary"
        or view.metadata.git_commit != value.archive_git_commit
        or manifest.release_version != value.archive_release_version
        or manifest.artifact_hashes.get("data/publication_view_model.json")
        != value.archive_view_model_sha256
        or hashlib.sha256(canonical_json_bytes(inventory_raw)).hexdigest()
        != value.archive_inventory_sha256
    ):
        raise ValueError("historical precinct supplement differs from original archive identity")
    public_ids = {r.id for section in view.guide_sections for r in section.races}
    if set(value.race_mappings.values()) != public_ids:
        raise ValueError("historical precinct mappings must cover every archived public contest")
    if view.precinct_ballot is not None:
        raise ValueError("historical supplement cannot replace an archived precinct capability")
    return inventory


def _verify_metadata(raw: bytes) -> None:
    raw_metadata = parse_json_bytes(raw)
    if not isinstance(raw_metadata, dict):
        raise ValueError("historical precinct metadata must be an object")
    metadata = cast(dict[str, Any], raw_metadata)
    if (
        metadata.get("id") != DATASET_ID
        or metadata.get("name") != DATASET_TITLE
        or metadata.get("description") != DATASET_DESCRIPTION
        or metadata.get("attribution") != "King County Elections"
        or metadata.get("provenance") != "official"
        or [c["name"] for c in metadata.get("columns", []) if not c.get("name", "").startswith(":")]
        != CSV_COLUMNS
    ):
        raise ValueError("historical precinct source metadata has unsupported election identity")


def _verify_custody(
    repository: Path, source: SupplementSource, capture: SupplementSource
) -> CapturedManifest:
    manifest = CapturedManifest.model_validate(parse_json_bytes(_source_bytes(repository, capture)))
    if (
        manifest.source_id != "king-county-elections"
        or manifest.storage_scope != "repository"
        or manifest.redistribution != "permitted"
        or manifest.content_sha256 != source.sha256
        or source.path != f"data/evidence/official/{manifest.storage_reference}"
    ):
        raise ValueError("historical precinct source differs from official evidence custody")
    verify_capture(
        manifest,
        repository / "data/snapshots",
        repository_storage_root=repository / "data/evidence/official",
    )
    return manifest


class AcquisitionRecord(HostingModel):
    requested_url: str
    final_url: str
    status: Literal[200]
    started_at: datetime
    completed_at: datetime
    bytes: int = Field(gt=0, strict=True)
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    storage_reference: str


class SourceAcquisition(HostingModel):
    schema_version: Literal["1.0"]
    dataset_id: Literal["2ydw-3iau"]
    authority: Literal["King County Elections"]
    catalog_url: Literal[
        "https://catalog.data.gov/dataset/august-2026-primary-election-final-precinct-results"
    ]
    sources: list[AcquisitionRecord]


def _verify_acquisition(
    raw: bytes,
    value: HistoricalPrecinctSupplement,
    captures: dict[str, CapturedManifest],
) -> None:
    receipt = SourceAcquisition.model_validate(parse_json_bytes(raw))
    records = receipt.sources
    if len(records) != len(captures) or {r.storage_reference for r in records} != captures.keys():
        raise ValueError("historical precinct acquisition is incomplete")
    for record in records:
        capture = captures[record.storage_reference]
        csv_source = record.storage_reference == value.source_csv.path
        expected_url = (
            f"https://data.kingcounty.gov/api/v3/views/{DATASET_ID}/export.csv?accessType=DOWNLOAD"
            if csv_source
            else f"https://data.kingcounty.gov/api/views/{DATASET_ID}"
        )
        if (
            record.sha256 != capture.content_sha256
            or record.bytes != capture.byte_length
            or record.requested_url != expected_url
            or record.final_url != expected_url
            or capture.requested_url != expected_url
            or capture.canonical_url != expected_url
            or capture.http_status != record.status
            or capture.media_type
            != ("text/csv; charset=utf-8" if csv_source else "application/json; charset=utf-8")
            or record.started_at.tzinfo is None
            or record.completed_at.tzinfo is None
            or not record.started_at <= record.completed_at <= value.reviewed_at
            or record.completed_at != capture.retrieved_at
        ):
            raise ValueError("historical precinct acquisition identity differs")


def _verify_source_membership(
    raw: bytes,
    city_raw: bytes,
    value: HistoricalPrecinctSupplement,
    inventory: Inventory,
) -> None:
    city_rows = list(csv.DictReader(io.StringIO(city_raw.decode("utf-8-sig"))))
    city = {r["PrecinctName"]: r for r in city_rows}
    if len(city) != len(city_rows) or any(r["CityName"] != "Seattle" for r in city_rows):
        raise ValueError("historical Seattle crosswalk has duplicate or non-city records")
    reader = csv.DictReader(io.StringIO(raw.decode("utf-8-sig")))
    if reader.fieldnames != CSV_COLUMNS:
        raise ValueError("historical precinct CSV has unsupported columns")
    districts: dict[str, tuple[str, ...]] = {}
    observed: dict[str, set[str]] = defaultdict(set)
    counters: dict[tuple[str, str], Counter[str]] = defaultdict(Counter)
    all_names: set[str] = set()
    all_races: set[str] = set()
    official_city: set[str] = set()
    row_count = 0
    for row in reader:
        row_count += 1
        if None in row or any(v is None for v in row.values()):
            raise ValueError("historical precinct CSV contains an incomplete row")
        name = row["Precinct"]
        all_names.add(name)
        all_races.add(row["Race"])
        if row["SeattleCouncilDistrict"] in {"1", "2", "3", "4", "5", "6", "7"}:
            official_city.add(name)
        if name not in city:
            continue
        district = tuple(row[field] for field in DISTRICT_COLUMNS)
        if (
            any(not part.isdigit() for part in district)
            or (name in districts and district != districts[name])
            or district[3] != city[name]["SeattleCouncilDistrict"]
            or row["CounterGroup"] != "Total"
        ):
            raise ValueError("historical precinct district assignments conflict")
        districts[name] = district
        key = name, row["Race"]
        counters[key][row["CounterType"]] += 1
        if counters[key][row["CounterType"]] > 1:
            raise ValueError("historical precinct source repeats a counter identity")
        if row["Race"] in value.race_mappings:
            observed[name].add(value.race_mappings[row["Race"]])
        elif row["Race"] != f"{name} Precinct Committee Officer - Democratic":
            raise ValueError("historical precinct source has an unmapped Seattle contest")
    if (
        row_count != value.source_row_count
        or len(all_names) != value.source_precinct_count
        or set(city) != official_city
        or set(city) != districts.keys()
        or {p.name for p in value.precincts} != set(city)
        or set(value.race_mappings) - all_races
        or any(c["Registered Voters"] != 1 or c["Times Counted"] != 1 for c in counters.values())
    ):
        raise ValueError("historical precinct source does not cover the complete electorate")
    public_ids = set(value.race_mappings.values())
    pair_count = 0
    for precinct in value.precincts:
        ld, cc, cd, sc = districts[precinct.name]
        jurisdictions = {
            "washington-state",
            "king-county",
            "city-of-seattle",
            f"legislative-district-{ld}",
            f"county-council-district-{cc}",
            f"congressional-district-{cd}",
            f"seattle-city-council-district-{sc}",
        }
        expected = {
            r.id
            for r in inventory.races
            if r.id in public_ids and r.jurisdiction_id in jurisdictions
        }
        if (
            set(precinct.jurisdiction_ids) != jurisdictions
            or set(precinct.contest_ids) != observed[precinct.name]
            or observed[precinct.name] != expected
        ):
            raise ValueError("historical precinct membership differs from official August contests")
        pair_count += len(expected)
    if pair_count != value.covered_pair_count:
        raise ValueError("historical precinct covered contest count differs")


def read_historical_precinct_supplement(
    ref: HistoricalCapabilityRef,
    *,
    repository: Path,
    archive_view_model: PublicationViewModel,
    archive_manifest: ReleaseManifest,
    archive_inventory: dict[str, Any],
) -> AdmittedPrecinctSupplement:
    """Admit complete official historical membership; never fetch or rescore election data."""
    repository = repository.resolve()
    path = (repository / ref.path).resolve()
    if not path.is_relative_to((repository / "config/elections").resolve()):
        raise ValueError("historical precinct supplement escaped election configuration")
    raw = path.read_bytes()
    if hashlib.sha256(raw).hexdigest() != ref.sha256:
        raise ValueError("historical precinct supplement hash differs from reviewed declaration")
    value = HistoricalPrecinctSupplement.model_validate(parse_json_bytes(raw))
    inventory = _verify_archive(value, archive_view_model, archive_manifest, archive_inventory)
    captures = {
        value.source_csv.path: _verify_custody(
            repository, value.source_csv, value.source_csv_capture
        ),
        value.source_metadata.path: _verify_custody(
            repository, value.source_metadata, value.source_metadata_capture
        ),
    }
    metadata = _source_bytes(repository, value.source_metadata)
    _verify_metadata(metadata)
    _verify_acquisition(_source_bytes(repository, value.source_acquisition), value, captures)
    _verify_source_membership(
        _source_bytes(repository, value.source_csv),
        _source_bytes(repository, value.city_membership),
        value,
        inventory,
    )
    return AdmittedPrecinctSupplement(raw=raw, declaration=value)


def verify_served_precinct_supplement(
    raw: bytes,
    *,
    expected_sha256: str,
    provenance: HistoricalPrecinctProvenance,
    archive_manifest: ReleaseManifest,
    archive_git_commit: str,
    source_git_commit: str,
) -> HistoricalPrecinctSupplement:
    """Bind the copied reviewed audit asset without recreating its original archive."""
    digest = hashlib.sha256(raw).hexdigest()
    if digest != expected_sha256 or digest != provenance.artifact_sha256:
        raise ValueError("served precinct supplement differs from reviewed source")
    value = HistoricalPrecinctSupplement.model_validate(parse_json_bytes(raw))
    if (
        provenance.source_git_commit != source_git_commit
        or provenance.election_id != value.election_id
        or provenance.mapping_hash != value.mapping_hash
        or provenance.archive_view_model_sha256 != value.archive_view_model_sha256
        or provenance.archive_inventory_sha256 != value.archive_inventory_sha256
        or archive_git_commit != value.archive_git_commit
        or archive_manifest.release_version != value.archive_release_version
        or archive_manifest.artifact_hashes.get("data/publication_view_model.json")
        != value.archive_view_model_sha256
    ):
        raise ValueError(
            "served precinct supplement provenance differs from data or current source"
        )
    return value
