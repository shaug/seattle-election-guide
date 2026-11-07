"""Offline end-to-end refreshes retain scope, clocks and durable failure holds."""

import fcntl
import json
import os
import shutil
from datetime import UTC, datetime
from pathlib import Path

import pytest
import yaml

import election_guide.results as results
from election_guide.collection.http import HttpArtifact, HttpFetchFailure
from election_guide.evidence.models import CapturedManifest
from election_guide.evidence.storage import captured_artifact_path, read_capture_manifest
from election_guide.inventory.importer import read_inventory
from election_guide.results.models import PreliminaryElectionResults
from election_guide.results.preliminary import build_preliminary_results
from election_guide.serialization import read_yaml

ROOT = Path(__file__).parents[1]
MAP = ROOT / "config/results/wa-2026-general-preliminary.yaml"
INVENTORY = ROOT / "data/normalized/wa-2026-general-inventory.json"
NOW = datetime(2026, 11, 6, 21, tzinfo=UTC)


def setup_repository(tmp_path: Path) -> tuple[Path, dict[str, bytes]]:
    authority = tmp_path / "config/authorities/default.yaml"
    authority.parent.mkdir(parents=True)
    shutil.copyfile(ROOT / "config/authorities/default.yaml", authority)
    plan = read_yaml(MAP)
    bodies: dict[str, bytes] = {}
    for binding in plan["sources"]:
        source = ROOT / binding["evidence"]
        target = tmp_path / binding["evidence"]
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
        manifest = read_capture_manifest(source)
        assert isinstance(manifest, CapturedManifest)
        original = captured_artifact_path(manifest, ROOT / "data/snapshots")
        stored = tmp_path / "data/evidence/official" / manifest.storage_reference
        stored.parent.mkdir(parents=True, exist_ok=True)
        os.link(original, stored)
        bodies[binding["format"]] = original.read_bytes()
    previous = build_preliminary_results(plan, read_inventory(INVENTORY), repository_root=tmp_path)
    output = tmp_path / "data/results/wa-2026-general.yaml"
    output.parent.mkdir(parents=True)
    output.write_text(yaml.safe_dump(previous.model_dump(mode="json")))
    return output, bodies


def test_refresh_rebinds_both_sources_and_writes_all_52_races(tmp_path: Path) -> None:
    refresh = results.prepare_preliminary_refresh
    output, bodies = setup_repository(tmp_path)
    calls: list[str] = []

    def fetch(url: str) -> HttpArtifact:
        calls.append(url)
        source = "statewide" if "/cdn/" in url else "county"
        return HttpArtifact(bodies[source], 200, url, [], "application/json")

    report = refresh(MAP, INVENTORY, repository_root=tmp_path, fetcher=fetch, clock=lambda: NOW)
    updated = results.read_results(output)
    assert isinstance(updated, PreliminaryElectionResults)
    assert report["status"] == "prepared" and len(calls) == 2
    assert len(updated.races) == 52
    assert all(c.captured_at == NOW for c in updated.captures[-2:])
    assert updated.races[0].reported_at is None
    assert updated.races[0].export_generated_at != NOW


def test_refresh_failure_is_retained_and_next_tick_does_not_repeat_it(tmp_path: Path) -> None:
    refresh = results.prepare_preliminary_refresh
    output, _ = setup_repository(tmp_path)
    previous = results.read_results(output)
    calls: list[str] = []

    def denied(url: str) -> HttpArtifact:
        calls.append(url)
        raise HttpFetchFailure(
            "HTTP 403", response_status=403, followed_redirects=0, redirect_class="SAME_ORIGIN"
        )

    with pytest.raises(ValueError, match="403"):
        refresh(MAP, INVENTORY, repository_root=tmp_path, fetcher=denied, clock=lambda: NOW)
    after = results.read_results(output)
    assert isinstance(after, PreliminaryElectionResults)
    assert after.races == previous.races
    assert after.failed_refreshes[0].checked_at == NOW
    with pytest.raises(ValueError, match="held"):
        refresh(MAP, INVENTORY, repository_root=tmp_path, fetcher=denied, clock=lambda: NOW)
    assert len(calls) == 1


def test_overlapping_refresh_stops_before_network(tmp_path: Path) -> None:
    refresh = results.prepare_preliminary_refresh
    setup_repository(tmp_path)
    lock = tmp_path / "output/preliminary-refresh.lock"
    lock.parent.mkdir()
    with lock.open("a+") as stream:
        fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
        with pytest.raises(ValueError, match="already active"):
            refresh(MAP, INVENTORY, repository_root=tmp_path)


def test_certified_file_is_preserved_before_any_source_request(tmp_path: Path) -> None:
    refresh = results.prepare_preliminary_refresh
    output, _ = setup_repository(tmp_path)
    certified = (ROOT / "data/results/wa-2026-primary.yaml").read_bytes()
    output.write_bytes(certified)
    with pytest.raises(ValueError, match="certified"):
        refresh(MAP, INVENTORY, repository_root=tmp_path)
    assert output.read_bytes() == certified


def test_invalid_mapping_stops_before_any_request(tmp_path: Path) -> None:
    refresh = results.prepare_preliminary_refresh
    setup_repository(tmp_path)
    plan = read_yaml(MAP)
    plan["races"] = plan["races"][:-1]
    invalid = tmp_path / "invalid.yaml"
    invalid.write_text(json.dumps(plan))
    with pytest.raises(ValueError, match="every inventory race"):
        refresh(invalid, INVENTORY, repository_root=tmp_path)


def test_publisher_clock_regression_preserves_exact_previous_file(tmp_path: Path) -> None:
    output, bodies = setup_repository(tmp_path)
    previous = output.read_bytes()
    raw = json.loads(bodies["county"])
    for race in raw["ballotItems"]:
        race["reportingStatus"]["asOf"] = "2026-11-03T23:00:00Z"
    bodies["county"] = json.dumps(raw).encode()

    def fetch(url: str) -> HttpArtifact:
        body = bodies["statewide" if "/cdn/" in url else "county"]
        return HttpArtifact(body, 200, url, [], "application/json")

    with pytest.raises(ValueError, match="regressed"):
        results.prepare_preliminary_refresh(
            MAP, INVENTORY, repository_root=tmp_path, fetcher=fetch, clock=lambda: NOW
        )
    assert output.read_bytes() == previous
