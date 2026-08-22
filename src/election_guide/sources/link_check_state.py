"""Persist the previous run's failing-URL sets (O17).

A scheduled link check must confirm a failure repeats before reporting it, so
it needs to remember what failed last run. That memory lives outside Git and
outside the source registry -- a GitHub Actions cache entry the workflow
restores before this command runs and saves after -- because the one thing
this check must never do is mutate committed source data to remember its own
run history.

Two sets, not one, because confirmation compares causes and not just URLs
(issue #406). `failing_urls` is every URL that failed, the record an operator
reads out of the cache to see what a run actually hit. `rot_confirming_urls`
is the subset whose cause was evidence the page is gone, and it is the one
`confirmed_failures` compares the next run against -- a URL that answered 403
twice running has not been shown to be dead even once.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class LinkCheckState(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    failing_urls: tuple[str, ...] = Field(default_factory=tuple)
    rot_confirming_urls: tuple[str, ...] = Field(default_factory=tuple)


EMPTY_STATE = LinkCheckState()


def read_link_check_state(path: Path) -> LinkCheckState:
    """Read the previous run's state, treating a missing or unreadable file as empty.

    A first-ever run, a cache miss, and a corrupt cache entry all mean the
    same thing here: there is no prior run to confirm a failure against yet.
    A cache entry written before `rot_confirming_urls` existed reads as having
    confirmed nothing, which costs one run of confirmation delay after deploy
    and never a false alert.
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
