"""Cross-document validation for post-election results (docs/RESULTS.md).

`results/models.py` enforces every invariant a results file can check against
itself. The two checks here need documents a results file does not carry: the
frozen ballot inventory a `choice_id` must resolve against, and the evidence
manifests a capture reference must resolve to.
"""

from __future__ import annotations

from pathlib import Path

from election_guide.evidence.storage import read_capture_manifest
from election_guide.inventory.models import Inventory
from election_guide.results.models import ElectionResults


def validate_results_inventory(results: ElectionResults, inventory: Inventory) -> None:
    """Require every declared race and ballot choice to resolve against the
    frozen ballot inventory. Unmatched names fail loudly rather than being
    guessed at (docs/RESULTS.md, Data model)."""
    if results.election_id != inventory.election.id:
        raise ValueError(
            f"results file belongs to {results.election_id!r}, not {inventory.election.id!r}"
        )
    races_by_id = {race.id: race for race in inventory.races}
    for race in results.races:
        inventory_race = races_by_id.get(race.race_id)
        if inventory_race is None:
            raise ValueError(f"results cite unknown race {race.race_id!r}")
        choice_ids = {choice.id for choice in inventory_race.choices}
        for outcome in race.outcomes:
            if outcome.choice_id not in choice_ids:
                raise ValueError(
                    f"results cite unknown ballot choice {outcome.choice_id!r} "
                    f"for race {race.race_id!r}"
                )


def validate_results_evidence(
    results: ElectionResults,
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
    if results.supersedes is not None:
        references.append(results.supersedes)
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
