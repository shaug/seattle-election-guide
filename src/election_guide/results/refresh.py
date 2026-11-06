"""Serialized official refresh preparation; protected publication remains separate."""

from __future__ import annotations

import fcntl
from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from typing import Any

import yaml

from election_guide.collection.http import HttpArtifact
from election_guide.evidence.storage import read_capture_manifest
from election_guide.inventory.importer import read_inventory
from election_guide.results.acquisition import (
    FEEDS,
    PreliminaryAcquisitionError,
    acquire_preliminary,
    check_preliminary_access,
)
from election_guide.results.loader import read_results
from election_guide.results.models import PreliminaryElectionResults, PreliminaryRefreshFailure
from election_guide.results.preliminary import PreliminaryAdmissionPlan, build_preliminary_results
from election_guide.results.validation import validate_results_evidence
from election_guide.serialization import read_yaml, write_generated_bytes


def merge_preliminary_history(
    current: PreliminaryElectionResults,
    previous: PreliminaryElectionResults | None,
) -> PreliminaryElectionResults:
    if previous is None:
        return current
    if previous.election_id != current.election_id:
        raise ValueError("existing preliminary file belongs to a different election")
    old_races = {race.race_id: race for race in previous.races}
    if any(
        race.race_id in old_races
        and race.source_timestamp < old_races[race.race_id].source_timestamp
        for race in current.races
    ):
        raise ValueError("publisher count timestamp regressed; retain the previous snapshot")
    captures = {capture.evidence: capture for capture in previous.captures}
    captures.update({capture.evidence: capture for capture in current.captures})
    return PreliminaryElectionResults.model_validate(
        {
            **current.model_dump(),
            "captures": list(captures.values()),
            "failed_refreshes": previous.failed_refreshes,
        }
    )


def _previous(path: Path) -> PreliminaryElectionResults | None:
    if not path.exists():
        return None
    results = read_results(path)
    if not isinstance(results, PreliminaryElectionResults):
        raise ValueError("cannot overwrite a legacy/certified results file with preliminary data")
    return results


def _write(path: Path, results: PreliminaryElectionResults) -> None:
    write_generated_bytes(
        path, yaml.safe_dump(results.model_dump(mode="json"), sort_keys=True).encode()
    )


def prepare_preliminary_refresh(
    mapping_path: Path,
    inventory_path: Path,
    *,
    repository_root: Path,
    fetcher: Callable[[str], HttpArtifact] | None = None,
    clock: Callable[[], datetime] | None = None,
) -> dict[str, Any]:
    """Validate, acquire once per source, rebind and atomically prepare a snapshot.

    All sources are preflighted before any request. A denied source stops the
    batch and later ticks; source/schema/admission errors never become fake
    HTTP failures. Existing counts survive every unsuccessful preparation.
    """
    plan = PreliminaryAdmissionPlan.model_validate(read_yaml(mapping_path))
    inventory = read_inventory(inventory_path)
    lock_path = repository_root / "output/preliminary-refresh.lock"
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    with lock_path.open("a+") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as error:
            raise ValueError("a preliminary refresh is already active") from error
        output_path = repository_root / "data/results" / f"{plan.election_id}.yaml"
        previous = _previous(output_path)
        build_preliminary_results(plan, inventory, repository_root=repository_root)
        formats = [binding.format for binding in plan.sources]
        if len(formats) != len(set(formats)):
            raise ValueError("refresh mapping repeats a source format")
        for binding in plan.sources:
            authority, url, _ = FEEDS[binding.format]
            seed = read_capture_manifest(repository_root / binding.evidence)
            if binding.authority_id != authority or seed.requested_url != url:
                raise ValueError("refresh source is not its fixed reviewed official resource")
            check_preliminary_access(binding.format, repository_root=repository_root)
        replacements: dict[str, str] = {}
        for binding in plan.sources:
            try:
                captured = acquire_preliminary(
                    binding.format, repository_root=repository_root, fetcher=fetcher, clock=clock
                )
            except PreliminaryAcquisitionError as error:
                if previous is not None:
                    manifest = read_capture_manifest(error.manifest_path)
                    failure = PreliminaryRefreshFailure(
                        authority_id=manifest.source_id,
                        checked_at=manifest.retrieved_at,
                        evidence=error.manifest_path.relative_to(repository_root).as_posix(),
                    )
                    failures = {item.evidence: item for item in previous.failed_refreshes}
                    failures[failure.evidence] = failure
                    retained = PreliminaryElectionResults.model_validate(
                        {**previous.model_dump(), "failed_refreshes": list(failures.values())}
                    )
                    validate_results_evidence(retained, repository_root=repository_root)
                    _write(output_path, retained)
                raise
            replacements[binding.evidence] = captured.relative_to(repository_root).as_posix()
        rebound = plan.model_dump()
        for source in rebound["sources"]:
            source["evidence"] = replacements[source["evidence"]]
        for race in rebound["races"]:
            race["capture_evidence"] = replacements[race["capture_evidence"]]
            race["coverage_evidence"] = replacements.get(
                race["coverage_evidence"], race["coverage_evidence"]
            )
        current = build_preliminary_results(rebound, inventory, repository_root=repository_root)
        prepared = merge_preliminary_history(current, previous)
        validate_results_evidence(prepared, repository_root=repository_root)
        _write(output_path, prepared)
        return {
            "status": "prepared",
            "election_id": plan.election_id,
            "races": len(prepared.races),
            "output": str(output_path),
            "new_captures": replacements,
            "publication": "not performed",
        }
