"""Load the declared election operations calendar."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from pydantic import ValidationError

from election_guide.calendar.models import ElectionCalendar
from election_guide.serialization import read_yaml


def read_election_calendar(path: Path) -> ElectionCalendar:
    """Load a YAML election calendar and expose validation as a stable value error."""
    try:
        raw: Any = read_yaml(path)
        return ElectionCalendar.model_validate(raw)
    except (OSError, UnicodeError, yaml.YAMLError, ValidationError) as error:
        raise ValueError(str(error)) from error
