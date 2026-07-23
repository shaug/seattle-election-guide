"""Deterministic consensus scoring over canonical endorsement records."""

from election_guide.scoring.config import read_scoring_configuration
from election_guide.scoring.engine import PublicationBlockedError, score_dataset
from election_guide.scoring.impact import (
    ConsensusImpactReport,
    ConsensusImpactSnapshot,
    compare_consensus,
    compare_consensus_snapshots,
    summarize_consensus,
    summarize_consensus_payload,
)
from election_guide.scoring.models import ConsensusReport, ScoringConfiguration

__all__ = [
    "ConsensusImpactReport",
    "ConsensusImpactSnapshot",
    "ConsensusReport",
    "PublicationBlockedError",
    "ScoringConfiguration",
    "compare_consensus",
    "compare_consensus_snapshots",
    "read_scoring_configuration",
    "score_dataset",
    "summarize_consensus",
    "summarize_consensus_payload",
]
