"""Post-election results: schema, loader, adapter, and validator
(docs/RESULTS.md)."""

from election_guide.results.ingest import (
    ContestRows,
    ResultsIngestError,
    build_election_results,
    merge_race_results,
    parse_certified_csv,
    resolve_ballot_choice,
    resolve_choice,
    resolve_race,
)
from election_guide.results.ingest_secretary_of_state import (
    BallotItemExport,
    build_sos_race_results,
    parse_statewide_export,
    resolve_sos_race,
)
from election_guide.results.loader import (
    load_rendering_results,
    read_results,
    reject_committed_counting_status,
)
from election_guide.results.models import ElectionResults, RaceOutcome, RaceResults, ResultsCapture
from election_guide.results.validation import validate_results_evidence, validate_results_inventory

__all__ = [
    "BallotItemExport",
    "ContestRows",
    "ElectionResults",
    "RaceOutcome",
    "RaceResults",
    "ResultsCapture",
    "ResultsIngestError",
    "build_election_results",
    "build_sos_race_results",
    "load_rendering_results",
    "merge_race_results",
    "parse_certified_csv",
    "parse_statewide_export",
    "read_results",
    "reject_committed_counting_status",
    "resolve_ballot_choice",
    "resolve_choice",
    "resolve_race",
    "resolve_sos_race",
    "validate_results_evidence",
    "validate_results_inventory",
]
