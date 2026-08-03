"""Rendering configuration loading."""

from pathlib import Path

from election_guide.rendering.models import RenderingConfiguration
from election_guide.serialization import read_yaml


def read_rendering_configuration(path: Path) -> RenderingConfiguration:
    """Read the strict Chromium rendering contract."""
    return RenderingConfiguration.model_validate(read_yaml(path))
