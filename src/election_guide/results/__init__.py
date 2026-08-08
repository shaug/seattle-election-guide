"""Post-election results: schema, loader, adapter, and validator
(docs/RESULTS.md)."""

from election_guide.results.ingest import (
    ContestRows,
    ResultsIngestError,
    build_election_results,
    parse_certified_csv,
    resolve_choice,
    resolve_race,
)
from election_guide.results.loader import (
    load_rendering_results,
    read_results,
    reject_committed_counting_status,
)
from election_guide.results.models import ElectionResults, RaceOutcome, RaceResults, ResultsCapture
from election_guide.results.validation import validate_results_evidence, validate_results_inventory

__all__ = [
    "ContestRows",
    "ElectionResults",
    "RaceOutcome",
    "RaceResults",
    "ResultsCapture",
    "ResultsIngestError",
    "build_election_results",
    "load_rendering_results",
    "parse_certified_csv",
    "read_results",
    "reject_committed_counting_status",
    "resolve_choice",
    "resolve_race",
    "validate_results_evidence",
    "validate_results_inventory",
]
