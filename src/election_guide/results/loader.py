"""Load post-election results and gate them for the rendering pipeline
(docs/RESULTS.md)."""

from __future__ import annotations

from pathlib import Path
from typing import Any, cast

import yaml
from pydantic import ValidationError

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
    """Committed results files are only ever `certified` or `amended`
    (docs/RESULTS.md, Data model). `status: counting` stays in the schema for
    forward compatibility, but a file that has actually been committed to
    `data/results/` may never carry it — the counting-window rendering states
    derive from the calendar, not from a file."""
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

    Returns the validated results for `election_id` when a `certified` or
    `amended` file exists at `results_dir/<election_id>.yaml`, and `None`
    otherwise — no file, a file for a different election, or (defensively) a
    file still carrying `status: counting`, which should never have reached
    here committed. `#285`-`#288` call this one function from their own build
    step instead of each re-deriving the file path, the schema, or the
    certified-or-amended state gate (docs/RESULTS.md, Rendering: "results
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
