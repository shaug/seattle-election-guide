"""Actual August membership is a separate, complete, hash-bound historical supplement."""

from __future__ import annotations

import copy
import csv
import gzip
import hashlib
import io
import json
import shutil
from pathlib import Path
from typing import Any

import pytest

from election_guide.evidence.models import evidence_fingerprint
from election_guide.hosting.models import HistoricalCapabilityRef
from election_guide.hosting.supplements import read_historical_precinct_supplement
from election_guide.publication.models import PublicationViewModel
from election_guide.release.models import ReleaseManifest
from election_guide.serialization import canonical_json_bytes

ROOT = Path(__file__).resolve().parents[1]
PATH = "config/elections/wa-2026-primary-precinct-supplement.json"
FIXTURES = ROOT / "tests/fixtures/ballot"


def _inputs() -> tuple[PublicationViewModel, ReleaseManifest, dict[str, Any]]:
    return (
        PublicationViewModel.model_validate_json(
            gzip.decompress((FIXTURES / "primary11-view-model.json.gz").read_bytes())
        ),
        ReleaseManifest.model_validate_json(
            (FIXTURES / "primary11-release-manifest.json").read_bytes()
        ),
        json.loads((ROOT / "data/normalized/wa-2026-primary-inventory.json").read_bytes()),
    )


def _admit(repository: Path):
    view, manifest, inventory = _inputs()
    return read_historical_precinct_supplement(
        HistoricalCapabilityRef(
            path=PATH, sha256=hashlib.sha256((repository / PATH).read_bytes()).hexdigest()
        ),
        repository=repository,
        archive_view_model=view,
        archive_manifest=manifest,
        archive_inventory=inventory,
    )


def test_actual_august_supplement_preserves_archive_and_matches_independent_occurrence_sets() -> (
    None
):
    view, manifest, inventory = _inputs()
    before = view.model_dump_json()
    admitted = read_historical_precinct_supplement(
        HistoricalCapabilityRef(
            path=PATH, sha256=hashlib.sha256((ROOT / PATH).read_bytes()).hexdigest()
        ),
        repository=ROOT,
        archive_view_model=view,
        archive_manifest=manifest,
        archive_inventory=inventory,
    )
    contract = admitted.contract("a" * 40)
    assert view.model_dump_json() == before
    assert view.precinct_ballot is None
    assert contract.address_lookup is None
    assert len(contract.precincts) == 1020
    assert all(p.code == p.name and p.code.startswith("SEA ") for p in contract.precincts)
    assert sum(len(p.contest_ids) for p in contract.precincts) == 11886
    assert not any(r.startswith("ld-11-") for p in contract.precincts for r in p.contest_ids)
    assert len({r.id for s in view.guide_sections for r in s.races}) == 32
    oracle = json.loads((FIXTURES / "wa-2026-primary-official-precinct-sets.json").read_bytes())
    assert len(oracle["groups"]) == 31
    by_name = {p.name: p for p in contract.precincts}
    for expected in oracle["groups"]:
        assert by_name[expected["example_precinct"]].contest_ids == expected["contest_ids"]
    provenance = contract.supplement
    assert provenance is not None
    assert provenance.source_git_commit == "a" * 40
    assert provenance.archive_view_model_sha256 == (
        "78b7afc76c77ebe58d9f5195a9ee26fbeceefd7a46538953664e9760d3f9fa22"
    )


def _write_fixture(root: Path) -> dict[str, Any]:
    value = json.loads((ROOT / PATH).read_bytes())
    target = root / PATH
    target.parent.mkdir(parents=True)
    for key in [
        "source_csv",
        "source_metadata",
        "source_csv_capture",
        "source_metadata_capture",
        "source_acquisition",
        "city_membership",
    ]:
        relative = value[key]["path"]
        (root / relative).parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / relative, root / relative)
    return value


def _rehash_mapping(value: dict[str, Any]) -> None:
    value["mapping_hash"] = hashlib.sha256(canonical_json_bytes(value["precincts"])).hexdigest()


def _rehash_source(root: Path, value: dict[str, Any], key: str) -> None:
    """Make a self-consistent synthetic capture so semantic negatives reach admission."""
    path = root / value[key]["path"]
    old_relative = value[key]["path"]
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    relative = f"data/evidence/official/sha256/{digest[:2]}/{digest}"
    target = root / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(path, target)
    value[key].update(path=relative, sha256=digest)
    capture_key = "source_csv_capture" if key == "source_csv" else "source_metadata_capture"
    capture_path = root / value[capture_key]["path"]
    capture = json.loads(capture_path.read_bytes())
    capture.update(
        content_sha256=digest,
        byte_length=target.stat().st_size,
        storage_reference=f"sha256/{digest[:2]}/{digest}",
    )
    capture["id"] = (
        capture["id"].rsplit("-", 1)[0]
        + "-"
        + evidence_fingerprint(
            {k: v for k, v in capture.items() if k not in {"id", "availability"}}
        )[:12]
    )
    capture_path.write_bytes(canonical_json_bytes(capture))
    value[capture_key]["sha256"] = hashlib.sha256(capture_path.read_bytes()).hexdigest()
    acquisition_path = root / value["source_acquisition"]["path"]
    acquisition = json.loads(acquisition_path.read_bytes())
    for source in acquisition["sources"]:
        if source["storage_reference"] == old_relative:
            source.update(storage_reference=relative, sha256=digest, bytes=target.stat().st_size)
    acquisition_path.write_bytes(canonical_json_bytes(acquisition))
    value["source_acquisition"]["sha256"] = hashlib.sha256(
        acquisition_path.read_bytes()
    ).hexdigest()


@pytest.mark.parametrize(
    "fault",
    [
        "future-schema",
        "wrong-date",
        "wrong-vm",
        "wrong-inventory",
        "numeric-id",
        "omitted-precinct",
        "duplicate-precinct",
        "missing-contest",
        "swapped-races",
        "raw-hash",
        "metadata-election",
        "missing-counter",
        "conflicting-district",
        "duplicate-counter",
    ],
)
def test_historical_admission_rejects_incomplete_or_ambiguous_rehashed_inputs(
    tmp_path: Path, fault: str
) -> None:
    value = _write_fixture(tmp_path)
    if fault == "future-schema":
        value["schema_version"] = "2.0"
    elif fault == "wrong-date":
        value["election_date"] = "2026-11-03"
    elif fault == "wrong-vm":
        value["archive_view_model_sha256"] = "a" * 64
    elif fault == "wrong-inventory":
        value["archive_inventory_sha256"] = "a" * 64
    elif fault == "numeric-id":
        value["precincts"][0]["code"] = "2153"
    elif fault == "omitted-precinct":
        value["precincts"].pop()
        _rehash_mapping(value)
    elif fault == "duplicate-precinct":
        value["precincts"].append(copy.deepcopy(value["precincts"][0]))
        _rehash_mapping(value)
    elif fault == "missing-contest":
        value["precincts"][0]["contest_ids"].pop()
        _rehash_mapping(value)
    elif fault == "swapped-races":
        mappings = value["race_mappings"]
        keys = [k for k, v in mappings.items() if v in {"us-house-7", "us-house-9"}]
        mappings[keys[0]], mappings[keys[1]] = mappings[keys[1]], mappings[keys[0]]
    elif fault == "raw-hash":
        with (tmp_path / value["source_csv"]["path"]).open("ab") as stream:
            stream.write(b"corrupt")
    elif fault == "metadata-election":
        path = tmp_path / value["source_metadata"]["path"]
        metadata = json.loads(path.read_bytes())
        metadata["description"] = "November general"
        path.write_bytes(canonical_json_bytes(metadata))
        _rehash_source(tmp_path, value, "source_metadata")
    else:
        path = tmp_path / value["source_csv"]["path"]
        rows = list(csv.DictReader(io.StringIO(path.read_text())))
        index = next(
            i for i, r in enumerate(rows) if r["Precinct"] == value["precincts"][0]["name"]
        )
        if fault == "missing-counter":
            rows.pop(index)
        elif fault == "duplicate-counter":
            rows.append(dict(rows[index]))
        elif fault == "conflicting-district":
            rows[index]["SeattleCouncilDistrict"] = "7"
        stream = io.StringIO()
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
        path.write_text(stream.getvalue())
        value["source_row_count"] = len(rows)
        _rehash_source(tmp_path, value, "source_csv")
    (tmp_path / PATH).write_bytes(canonical_json_bytes(value))
    with pytest.raises(ValueError):
        _admit(tmp_path)


@pytest.mark.parametrize("fault", ["size", "time-order", "capture-time", "capture-url"])
def test_acquisition_must_match_literal_custody_and_ordered_capture_clocks(
    tmp_path: Path, fault: str
) -> None:
    value = _write_fixture(tmp_path)
    path = tmp_path / value["source_acquisition"]["path"]
    receipt = json.loads(path.read_bytes())
    record = receipt["sources"][0]
    if fault == "size":
        record["bytes"] += 1
    elif fault == "time-order":
        record["started_at"] = "2026-11-09T05:10:00+00:00"
    elif fault == "capture-time":
        record["completed_at"] = "2026-11-09T05:05:00+00:00"
    else:
        capture_path = tmp_path / value["source_csv_capture"]["path"]
        capture = json.loads(capture_path.read_bytes())
        capture["requested_url"] = capture["canonical_url"] = (
            "https://example.test/another-election"
        )
        capture["id"] = (
            capture["id"].rsplit("-", 1)[0]
            + "-"
            + evidence_fingerprint(
                {k: v for k, v in capture.items() if k not in {"id", "availability"}}
            )[:12]
        )
        capture_path.write_bytes(canonical_json_bytes(capture))
        value["source_csv_capture"]["sha256"] = hashlib.sha256(
            capture_path.read_bytes()
        ).hexdigest()
    path.write_bytes(canonical_json_bytes(receipt))
    value["source_acquisition"]["sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
    (tmp_path / PATH).write_bytes(canonical_json_bytes(value))
    with pytest.raises(ValueError, match="acquisition"):
        _admit(tmp_path)
