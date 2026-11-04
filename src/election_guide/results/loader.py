"""Load post-election results and gate them for the rendering pipeline
(docs/RESULTS.md)."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, cast

import yaml
from pydantic import ValidationError

from election_guide.evidence.models import CapturedManifest
from election_guide.evidence.storage import REPOSITORY_STORAGE_ROOT, read_capture_manifest
from election_guide.inventory.models import Inventory
from election_guide.results.models import (
    ElectionResults,
    PreliminaryElectionResults,
    ResultsDocument,
)
from election_guide.results.validation import validate_results_evidence, validate_results_inventory
from election_guide.serialization import read_yaml

CERTIFIED_STATUSES = frozenset({"certified", "amended"})
RENDERED_STATUSES = CERTIFIED_STATUSES | {"preliminary"}
"""Results render as a state, not an option (docs/RESULTS.md, Rendering):
`load_rendering_results` surfaces a file only once it is in one of these
statuses."""


def read_results(path: Path) -> ResultsDocument:
    """Load a YAML results file and expose validation as a stable value error."""
    try:
        raw: Any = read_yaml(path)
        if isinstance(raw, dict) and cast(dict[str, Any], raw).get("schema_version") == "1.1":
            return PreliminaryElectionResults.model_validate(raw)
        return ElectionResults.model_validate(raw)
    except (OSError, UnicodeError, yaml.YAMLError, ValidationError) as error:
        raise ValueError(str(error)) from error


def reject_committed_counting_status(results: ResultsDocument) -> None:
    """Reject legacy transient counting files, including after the #696 extension.

    Preliminary admission uses its own strict schema 1.1. It does not relax the
    legacy schema 1.0 rule: calendar counting state never admits a counting file.
    """
    if results.status == "counting":
        raise ValueError(
            f"committed results file for {results.election_id!r} cannot carry status "
            "'counting'; counting-window rendering derives from the calendar, not a file"
        )


def load_rendering_results(
    election_id: str,
    inventory: Inventory,
    *,
    results_dir: Path = Path("data/results"),
    repository_root: Path = Path("."),
) -> ResultsDocument | None:
    """The rendering pipeline's one hook onto post-election results.

    Returns validated preliminary, certified or amended results for `election_id`
    when a file exists at `results_dir/<election_id>.yaml`, and `None`
    otherwise — no file, a file for a different election, or (defensively) a
    file still carrying `status: counting`, which should never have reached
    here committed. `#285`-`#288` call this one function from their own build
    step instead of each re-deriving the file path, the schema, or the
    admitted rendering state gate (docs/RESULTS.md, Rendering: "results
    render as a state, not an option").
    """
    path = results_dir / f"{election_id}.yaml"
    if not path.is_file():
        return None
    results = read_results(path)
    if results.election_id != election_id or results.status not in RENDERED_STATUSES:
        return None
    validate_results_inventory(results, inventory)
    validate_results_evidence(results, repository_root=repository_root)
    return results


def resolve_results_capture_urls(
    results: ResultsDocument,
    *,
    repository_root: Path,
    source_commit: str,
    project_url: str,
) -> dict[str, str]:
    """Preliminary receipts name immutable original bytes, not a later live count.

    Preserve the established canonical-authority links for legacy certified data.
    The release builder supplies the actual verified source commit and repo URL.
    """
    preliminary = isinstance(results, PreliminaryElectionResults)
    if preliminary and not re.fullmatch(r"[0-9a-f]{40}", source_commit):
        raise ValueError("preliminary evidence requires a full immutable source commit")
    by_evidence: dict[str, str] = {}
    for capture in results.captures:
        if capture.kind == "election_night" or capture.evidence in by_evidence:
            continue
        manifest = read_capture_manifest(repository_root / capture.evidence)
        if not isinstance(manifest, CapturedManifest):
            continue
        if preliminary:
            if manifest.storage_scope != "repository":
                raise ValueError("preliminary evidence must retain repository original bytes")
            relative = (REPOSITORY_STORAGE_ROOT / manifest.storage_reference).as_posix()
            by_evidence[capture.evidence] = (
                f"{project_url.rstrip('/')}/blob/{source_commit}/{relative}"
            )
        elif manifest.canonical_url is not None:
            by_evidence[capture.evidence] = manifest.canonical_url
    return {
        race.race_id: by_evidence[race.capture_evidence]
        for race in results.races
        if race.capture_evidence in by_evidence
    }
