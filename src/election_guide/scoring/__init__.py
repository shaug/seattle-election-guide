"""Deterministic consensus scoring over canonical endorsement records."""

from election_guide.scoring.config import read_scoring_configuration
from election_guide.scoring.engine import PublicationBlockedError, score_dataset
from election_guide.scoring.models import ConsensusReport, ScoringConfiguration

__all__ = [
    "ConsensusReport",
    "PublicationBlockedError",
    "ScoringConfiguration",
    "read_scoring_configuration",
    "score_dataset",
]
