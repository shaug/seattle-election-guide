"""Post-election results: schema, loader, and validator (docs/RESULTS.md)."""

from election_guide.results.loader import (
    load_rendering_results,
    read_results,
    reject_committed_counting_status,
)
from election_guide.results.models import ElectionResults, RaceOutcome, RaceResults, ResultsCapture
from election_guide.results.validation import validate_results_evidence, validate_results_inventory

__all__ = [
    "ElectionResults",
    "RaceOutcome",
    "RaceResults",
    "ResultsCapture",
    "load_rendering_results",
    "read_results",
    "reject_committed_counting_status",
    "validate_results_evidence",
    "validate_results_inventory",
]
