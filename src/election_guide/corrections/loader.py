"""Load per-election corrections and gate them for the rendering pipeline
(docs/RESULTS.md, "The corrections page"; issue #290)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from pydantic import ValidationError

from election_guide.corrections.models import ElectionCorrections
from election_guide.serialization import read_yaml


def read_corrections(path: Path) -> ElectionCorrections:
    """Load a YAML corrections file and expose validation as a stable value error."""
    try:
        raw: Any = read_yaml(path)
        return ElectionCorrections.model_validate(raw)
    except (OSError, UnicodeError, yaml.YAMLError, ValidationError) as error:
        raise ValueError(str(error)) from error


def load_rendering_corrections(
    election_id: str,
    *,
    corrections_dir: Path = Path("data/corrections"),
) -> ElectionCorrections | None:
    """The rendering pipeline's one hook onto per-election corrections.

    Returns the validated corrections for `election_id` when a file exists at
    `corrections_dir/<election_id>.yaml` and carries at least one entry, and
    `None` otherwise -- no file, a file for a different election, or
    (defensively) a file that validates but carries no entries. `None` is the
    same "no corrections" signal the corrections page itself gates
    existence, nav exposure, and rendering on (docs/RESULTS.md, Rendering:
    "results render as a state, not an option" -- the same posture governs
    Corrections), mirroring `election_guide.results.load_rendering_results`.
    """
    path = corrections_dir / f"{election_id}.yaml"
    if not path.is_file():
        return None
    corrections = read_corrections(path)
    if corrections.election_id != election_id or not corrections.entries:
        return None
    return corrections
