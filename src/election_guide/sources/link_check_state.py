"""Persist the previous run's failing-URL set (O17).

A scheduled link check must confirm a failure repeats before reporting it, so
it needs to remember what failed last run. That memory lives outside Git and
outside the source registry -- a GitHub Actions cache entry the workflow
restores before this command runs and saves after -- because the one thing
this check must never do is mutate committed source data to remember its own
run history.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class LinkCheckState(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    failing_urls: tuple[str, ...] = Field(default_factory=tuple)


EMPTY_STATE = LinkCheckState()


def read_link_check_state(path: Path) -> LinkCheckState:
    """Read the previous run's state, treating a missing or unreadable file as empty.

    A first-ever run, a cache miss, and a corrupt cache entry all mean the
    same thing here: there is no prior run to confirm a failure against yet.
    """
    try:
        raw: Any = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return EMPTY_STATE
    try:
        return LinkCheckState.model_validate(raw)
    except ValueError:
        return EMPTY_STATE


def write_link_check_state(path: Path, state: LinkCheckState) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state.model_dump(mode="json")), encoding="utf-8")
