"""Scoring configuration loading with exact-number validation."""

from pathlib import Path

from yaml import YAMLError

from election_guide.scoring.models import ScoringConfiguration
from election_guide.serialization import read_yaml


def read_scoring_configuration(path: Path) -> ScoringConfiguration:
    """Read and validate one explicit scoring policy."""
    try:
        payload = read_yaml(path)
    except (UnicodeError, YAMLError) as error:
        raise ValueError(f"invalid scoring configuration YAML: {error}") from error
    return ScoringConfiguration.model_validate(payload)
