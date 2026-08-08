"""Validated post-election results contract (docs/RESULTS.md, Data model).

One results file per election records how a race completed: status, the
certifying authority, the evidence captures behind it, and each ballot
choice's exact outcome. Nothing here renders a surface — `#285`-`#288` own
that — so this module only encodes the shape and the invariants
`docs/RESULTS.md` names: every `choice_id` resolves against the frozen ballot
inventory, shares sum to ~1 per race, and an amended file cites the capture it
supersedes. Unmatched names fail loudly, never guessed.
"""

from __future__ import annotations

from datetime import date
from typing import Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator

ResultsStatus = Literal["counting", "certified", "amended"]
"""`counting` stays in the enum for forward compatibility only — an in-memory
value some future adapter step might hold transiently while ballots are still
being counted. A *committed* `data/results/` file may never carry it
(`reject_committed_counting_status`, `results/loader.py`): the counting-window
rendering states derive from the calendar, not from a file
(docs/RESULTS.md, "The results lifecycle")."""

CaptureKind = Literal["election_night", "certified", "amended"]

# The tolerance for the "shares sum to ~1 per race" invariant (docs/RESULTS.md,
# Data model). Certified vote shares are real decimal counts, not the site's
# own exact-rational endorsement math, and write-in or minor candidates this
# schema never enumerates can leave a race's declared choices a little under
# one. One percentage point absorbs ordinary rounding and undeclared write-ins
# without letting an actually wrong or incomplete race pass.
SHARE_SUM_TOLERANCE = 0.01


class ResultsModel(BaseModel):
    """Reject undeclared fields so schema drift fails loudly."""

    model_config = ConfigDict(extra="forbid")


class ResultsCapture(ResultsModel):
    """One evidence capture behind a results file (docs/EVIDENCE_CAPTURE.md,
    docs/COLLECTION.md conventions). `evidence` is the manifest's own path —
    the same shape `evidence capture` writes to `data/manifests/evidence/` —
    so a results file cites evidence the same way every other collected record
    does, rather than inventing a second reference scheme.

    `election_night`'s capture is retained as evidence only; it is never
    rendered (docs/RESULTS.md, "The results lifecycle").
    """

    kind: CaptureKind
    captured_at: AwareDatetime
    evidence: str = Field(min_length=1)


class RaceOutcome(ResultsModel):
    """One ballot choice's certified outcome.

    `advanced` marks the choice that prevailed in its race — nothing more. One
    boolean serves every race type because the rendered label depends on the
    race type *and* on which choice carries the flag, neither of which this
    schema states: a primary's "Advances", a general's "Elected", and a
    measure's "Approved" or "Rejected" (a rejected measure is the one whose
    `No` choice carries `advanced: true` — no separate rejection field exists,
    or is needed) are all read off the same boolean (docs/RESULTS.md, "The
    results chip"; that labeling is `#285`'s job).
    """

    choice_id: str = Field(min_length=1)
    votes: int = Field(ge=0, strict=True)
    share: float = Field(ge=0, le=1)
    advanced: bool = Field(strict=True)


class RaceResults(ResultsModel):
    """One race's certified tally."""

    race_id: str = Field(min_length=1)
    ballots_counted: int = Field(ge=0, strict=True)
    outcomes: list[RaceOutcome] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_outcomes(self) -> RaceResults:
        choice_ids = [outcome.choice_id for outcome in self.outcomes]
        if len(set(choice_ids)) != len(choice_ids):
            raise ValueError(f"race {self.race_id!r} repeats a ballot choice in its outcomes")
        total_share = sum(outcome.share for outcome in self.outcomes)
        if abs(total_share - 1.0) > SHARE_SUM_TOLERANCE:
            raise ValueError(f"race {self.race_id!r} outcome shares sum to {total_share!r}, not ~1")
        return self


class ElectionResults(ResultsModel):
    """`data/results/<election-id>.yaml`'s validated contract (docs/RESULTS.md,
    Data model)."""

    schema_version: Literal["1.0"] = "1.0"
    election_id: str = Field(min_length=1)
    status: ResultsStatus
    certified_on: date | None = None
    authority: str = Field(min_length=1)
    captures: list[ResultsCapture] = Field(min_length=1)
    races: list[RaceResults] = Field(min_length=1)
    supersedes: str | None = Field(
        default=None,
        min_length=1,
        description=(
            "The evidence reference of the capture this amendment supersedes "
            "(docs/RESULTS.md, Data model). Required exactly when status is "
            "'amended'; absent otherwise."
        ),
    )

    @model_validator(mode="after")
    def validate_election_results(self) -> ElectionResults:
        race_ids = [race.race_id for race in self.races]
        if len(set(race_ids)) != len(race_ids):
            raise ValueError(f"results file for {self.election_id!r} repeats a race id")
        if self.status == "amended" and self.supersedes is None:
            raise ValueError(
                f"amended results for {self.election_id!r} must cite the capture they supersede"
            )
        if self.status != "amended" and self.supersedes is not None:
            raise ValueError(
                f"{self.status} results for {self.election_id!r} cannot cite a superseded capture"
            )
        if self.status in {"certified", "amended"} and self.certified_on is None:
            raise ValueError(
                f"{self.status} results for {self.election_id!r} require a certification date"
            )
        return self
