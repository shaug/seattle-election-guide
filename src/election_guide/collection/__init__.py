"""Source-specific collection adapters and immutable refresh history."""

from election_guide.collection.adapters import extract_decisions, validate_adapter
from election_guide.collection.models import (
    AdapterDecision,
    AdapterSpec,
    DecisionDiff,
    DecisionRule,
    ExtractionSnapshot,
    RefreshEvent,
)
from election_guide.collection.refresh import (
    read_adapter_spec,
    read_extraction_snapshot,
    read_refresh_event,
    refresh_source,
)

__all__ = [
    "AdapterDecision",
    "AdapterSpec",
    "DecisionDiff",
    "DecisionRule",
    "ExtractionSnapshot",
    "RefreshEvent",
    "extract_decisions",
    "read_adapter_spec",
    "read_extraction_snapshot",
    "read_refresh_event",
    "refresh_source",
    "validate_adapter",
]
