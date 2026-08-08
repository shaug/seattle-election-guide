"""Read and validate the preregistered counting-authority identity registry."""

from pathlib import Path
from typing import Any

import yaml
from pydantic import ValidationError

from election_guide.authorities.models import AuthorityRegistry
from election_guide.serialization import read_yaml


def read_authority_registry(path: Path) -> AuthorityRegistry:
    """Load a YAML authority registry and expose validation as a stable value error."""
    try:
        raw: Any = read_yaml(path)
        return AuthorityRegistry.model_validate(raw)
    except (OSError, yaml.YAMLError, ValidationError) as error:
        raise ValueError(str(error)) from error
