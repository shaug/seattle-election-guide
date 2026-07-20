"""Build canonical election configuration without collection or candidate data."""

from __future__ import annotations

import os
import stat
import tempfile
from pathlib import Path
from typing import Any

import yaml
from pydantic import ValidationError

from election_guide.initialization.models import (
    ElectionConfiguration,
    ElectionInitializationSeed,
    ElectionJurisdiction,
    ElectionRaceDeclaration,
)
from election_guide.serialization import canonical_json_bytes, parse_json_bytes, read_yaml


def initialize_election(seed_path: Path, output_path: Path) -> tuple[ElectionConfiguration, bool]:
    """Validate one offline seed and atomically create its canonical configuration."""
    try:
        raw: Any = read_yaml(seed_path)
        seed = ElectionInitializationSeed.model_validate(raw)
    except (OSError, UnicodeError, yaml.YAMLError, ValidationError) as error:
        raise ValueError(f"invalid election initialization seed: {error}") from error

    election_id = seed.election.id
    configuration = ElectionConfiguration(
        election=seed.election,
        source_panel=seed.source_panel,
        scoring_policy=seed.scoring_policy,
        jurisdictions=[
            ElectionJurisdiction(
                **item.model_dump(),
                election_id=election_id,
            )
            for item in sorted(seed.jurisdictions, key=lambda item: item.id)
        ],
        races=[
            ElectionRaceDeclaration(
                **item.model_dump(),
                election_id=election_id,
            )
            for item in sorted(seed.races, key=lambda item: item.id)
        ],
    )
    content = canonical_json_bytes(configuration.model_dump(mode="json"))
    created = write_once_or_verify(output_path, content, "election configuration")
    return configuration, created


def read_election_configuration(path: Path) -> ElectionConfiguration:
    """Read one canonical initialized election configuration."""
    try:
        return parse_election_configuration(path.read_bytes())
    except (OSError, UnicodeError, ValueError, ValidationError) as error:
        raise ValueError(f"invalid election configuration: {error}") from error


def parse_election_configuration(content: bytes) -> ElectionConfiguration:
    """Validate one exact canonical election-configuration byte snapshot."""
    configuration = ElectionConfiguration.model_validate(parse_json_bytes(content))
    canonical = canonical_json_bytes(configuration.model_dump(mode="json"))
    if content != canonical:
        raise ValueError("election configuration is not canonical")
    return configuration


def write_once_or_verify(path: Path, content: bytes, artifact_label: str) -> bool:
    """Exclusively create canonical bytes or verify an identical regular file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        path.lstat()
    except FileNotFoundError:
        pass
    else:
        _verify_existing_regular_file(path, content, artifact_label)
        return False

    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            prefix=f".{path.name}.",
            dir=path.parent,
            delete=False,
        ) as temporary:
            temporary.write(content)
            temporary.flush()
            os.fsync(temporary.fileno())
            os.fchmod(temporary.fileno(), 0o644)
            temporary_path = Path(temporary.name)
        try:
            os.link(temporary_path, path)
        except FileExistsError:
            _verify_existing_regular_file(path, content, artifact_label)
            return False
        return True
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)


def _verify_existing_regular_file(path: Path, expected: bytes, artifact_label: str) -> None:
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(path, flags)
    except OSError as error:
        raise ValueError(f"refusing non-regular {artifact_label} output at {path}") from error
    try:
        metadata = os.fstat(descriptor)
        if not stat.S_ISREG(metadata.st_mode):
            raise ValueError(f"refusing non-regular {artifact_label} output at {path}")
        with os.fdopen(descriptor, "rb", closefd=False) as handle:
            actual = handle.read()
    finally:
        os.close(descriptor)
    if actual != expected:
        raise ValueError(f"refusing to replace different {artifact_label} at {path}")
