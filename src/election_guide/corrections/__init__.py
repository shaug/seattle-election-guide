"""Per-election corrections: schema and loader (docs/RESULTS.md, "The
corrections page"; issue #290)."""

from election_guide.corrections.loader import load_rendering_corrections, read_corrections
from election_guide.corrections.models import (
    CorrectionEntry,
    CorrectionProvenanceLink,
    ElectionCorrections,
)

__all__ = [
    "CorrectionEntry",
    "CorrectionProvenanceLink",
    "ElectionCorrections",
    "load_rendering_corrections",
    "read_corrections",
]
