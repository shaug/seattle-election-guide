"""Cross-document validation for post-election results (docs/RESULTS.md).

`results/models.py` enforces every invariant a results file can check against
itself. The two checks here need documents a results file does not carry: the
frozen ballot inventory a `choice_id` must resolve against, and the evidence
manifests a capture reference must resolve to.
"""

from __future__ import annotations

from pathlib import Path

from election_guide.authorities.registry import read_authority_registry
from election_guide.evidence.models import CapturedManifest, UnavailableManifest
from election_guide.evidence.storage import read_capture_manifest, verify_capture
from election_guide.inventory.models import Inventory
from election_guide.results.models import PreliminaryElectionResults, ResultsDocument


def validate_results_inventory(results: ResultsDocument, inventory: Inventory) -> None:
    """Require every declared race and ballot choice to resolve against the
    frozen ballot inventory. Unmatched names fail loudly rather than being
    guessed at (docs/RESULTS.md, Data model)."""
    if results.election_id != inventory.election.id:
        raise ValueError(
            f"results file belongs to {results.election_id!r}, not {inventory.election.id!r}"
        )
    races_by_id = {race.id: race for race in inventory.races}
    if isinstance(results, PreliminaryElectionResults) and {
        race.race_id for race in results.races
    } != set(races_by_id):
        raise ValueError("preliminary admission must account for every inventory race")
    for race in results.races:
        inventory_race = races_by_id.get(race.race_id)
        if inventory_race is None:
            raise ValueError(f"results cite unknown race {race.race_id!r}")
        choice_ids = {choice.id for choice in inventory_race.choices}
        if isinstance(results, PreliminaryElectionResults):
            preliminary = next(item for item in results.races if item.race_id == race.race_id)
            if preliminary.jurisdiction_id != inventory_race.jurisdiction_id:
                raise ValueError(f"race {race.race_id!r} has the wrong jurisdiction")
            if {outcome.choice_id for outcome in race.outcomes} != choice_ids:
                raise ValueError("preliminary results must contain every named ballot choice")
        for outcome in race.outcomes:
            if outcome.choice_id not in choice_ids:
                raise ValueError(
                    f"results cite unknown ballot choice {outcome.choice_id!r} "
                    f"for race {race.race_id!r}"
                )


def validate_results_evidence(
    results: ResultsDocument,
    *,
    repository_root: Path = Path("."),
) -> None:
    """Require every capture reference — and an amendment's superseded
    capture — to resolve to a real, validated evidence manifest
    (docs/RESULTS.md, Data model; docs/EVIDENCE_CAPTURE.md). Also require
    every race's own `capture_evidence` to name one of this file's
    non-`election_night` captures (issue #417): `election_night` evidence is
    retained but never rendered (docs/RESULTS.md, "The results lifecycle"),
    so it is never a legitimate source for a race's own stated tally."""
    references = [capture.evidence for capture in results.captures]
    if not isinstance(results, PreliminaryElectionResults) and results.supersedes is not None:
        references.append(results.supersedes)
    if isinstance(results, PreliminaryElectionResults):
        references.extend(race.coverage_evidence for race in results.races)
    for reference in references:
        try:
            read_capture_manifest(repository_root / reference)
        except ValueError as error:
            raise ValueError(
                f"results evidence reference {reference!r} does not resolve to a valid "
                f"evidence manifest: {error}"
            ) from error
    citable_evidence = {
        capture.evidence for capture in results.captures if capture.kind != "election_night"
    }
    for race in results.races:
        if race.capture_evidence not in citable_evidence:
            raise ValueError(
                f"race {race.race_id!r} cites capture evidence {race.capture_evidence!r} that "
                "is not one of this file's own non-election-night captures"
            )
    if isinstance(results, PreliminaryElectionResults):
        authorities = {
            item.id: item
            for item in read_authority_registry(
                repository_root / "config/authorities/default.yaml"
            ).authorities
        }
        for reference in set(references):
            manifest = read_capture_manifest(repository_root / reference)
            if not isinstance(manifest, CapturedManifest) or manifest.storage_scope != "repository":
                raise ValueError("preliminary admission requires retained official original bytes")
            if manifest.source_id not in authorities:
                raise ValueError("preliminary evidence must name a registered official authority")
            verify_capture(
                manifest,
                repository_root / "data/snapshots",
                repository_storage_root=repository_root / "data/evidence/official",
            )
        for capture in results.captures:
            manifest = read_capture_manifest(repository_root / capture.evidence)
            if manifest.availability != "captured" or manifest.source_id != capture.authority_id:
                raise ValueError("preliminary capture must be from its stated official authority")
            if manifest.retrieved_at != capture.captured_at:
                raise ValueError("preliminary observation must retain the actual capture clock")
        for race in results.races:
            authority = authorities.get(race.authority_id)
            if authority is None or race.authority != authority.name:
                raise ValueError("preliminary race must retain the registered authority identity")
        for failure in results.failed_refreshes:
            manifest = read_capture_manifest(repository_root / failure.evidence)
            if (
                not isinstance(manifest, UnavailableManifest)
                or manifest.source_id != failure.authority_id
                or manifest.retrieved_at != failure.checked_at
            ):
                raise ValueError("refresh failure must retain its actual unavailable observation")
