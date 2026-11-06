"""Validated post-election results contract (docs/RESULTS.md, Data model).

One results file per election records how a race completed: status, the
evidence captures behind it, and each race's certifying authority and exact
outcome. A file can hold races from more than one counting authority (issue
#417); each race states its own. Nothing here renders a surface — `#285`-`#288`
own that — so this module only encodes the shape and the invariants
`docs/RESULTS.md` names: every `choice_id` resolves against the frozen ballot
inventory, shares sum to ~1 per race, and an amended file cites the capture it
supersedes. Unmatched names fail loudly, never guessed.
"""

from __future__ import annotations

from datetime import date, datetime
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
PRELIMINARY_STALE_AFTER_SECONDS = 24 * 60 * 60


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
    """One race's certified tally, stated by the authority that counted it.

    `authority` and `capture_evidence` are per-race, not per-file: a results
    file can hold races from more than one counting authority (issue #417 —
    King County states its own tally for a race wholly inside the county;
    the Secretary of State states the true total for one whose district
    crosses a county line). `capture_evidence` is one of the file's own
    `ElectionResults.captures[].evidence` references
    (`validate_results_evidence`, `results/validation.py`), naming which
    capture this race's own tally came from.

    Exactly one of `ballots_counted` or `votes_counted` is set, never both and
    never neither -- the two are different quantities with no shared
    analogue (docs/RESULTS.md's three-distinct-totals rule, extended to a
    fourth by issue #417): `ballots_counted` is an authority's own count of
    ballots that carried the contest (larger than the vote sum whenever a
    ballot over- or under-voted it); `votes_counted` is a vote total
    including write-ins, for an authority whose export states no
    ballots-with-contest analogue at all.
    """

    race_id: str = Field(min_length=1)
    authority: str = Field(min_length=1)
    capture_evidence: str = Field(min_length=1)
    ballots_counted: int | None = Field(default=None, ge=0, strict=True)
    votes_counted: int | None = Field(default=None, ge=0, strict=True)
    outcomes: list[RaceOutcome] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_outcomes(self) -> RaceResults:
        choice_ids = [outcome.choice_id for outcome in self.outcomes]
        if len(set(choice_ids)) != len(choice_ids):
            raise ValueError(f"race {self.race_id!r} repeats a ballot choice in its outcomes")
        total_share = sum(outcome.share for outcome in self.outcomes)
        if abs(total_share - 1.0) > SHARE_SUM_TOLERANCE:
            raise ValueError(f"race {self.race_id!r} outcome shares sum to {total_share!r}, not ~1")
        if (self.ballots_counted is None) == (self.votes_counted is None):
            raise ValueError(
                f"race {self.race_id!r} must state exactly one of ballots_counted or "
                "votes_counted, not both and not neither"
            )
        return self


class ElectionResults(ResultsModel):
    """`data/results/<election-id>.yaml`'s validated contract (docs/RESULTS.md,
    Data model)."""

    schema_version: Literal["1.0"] = "1.0"
    election_id: str = Field(min_length=1)
    status: ResultsStatus
    certified_on: date | None = None
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


class PreliminaryCapture(ResultsModel):
    """A current official observation; its retrieval clock is not the count clock."""

    kind: Literal["preliminary"] = "preliminary"
    authority_id: str = Field(min_length=1)
    captured_at: AwareDatetime
    evidence: str = Field(min_length=1)
    publisher_is_official_results: bool | None = Field(default=None, strict=True)


class PreliminaryOutcome(ResultsModel):
    """A named choice's count-so-far, never a called outcome or stored percentage."""

    choice_id: str = Field(min_length=1)
    votes: int = Field(ge=0, strict=True)


class PreliminaryWriteInOverride(ResultsModel):
    """Reviewed generic-row classification; the publisher's flag remains literal."""

    source_choice_id: str = Field(min_length=1)
    source_name: Literal["Write-in", "Write in"]
    publisher_is_write_in: bool | None = Field(strict=True)
    reason: str = Field(min_length=1)


class PreliminaryRaceResults(ResultsModel):
    """Whole-contest geography does not imply finished reporting or counting.

    Coverage is a reviewed assertion backed by a separate official evidence
    reference, not inferred from empty county metadata or a matching name.
    """

    race_id: str = Field(min_length=1)
    jurisdiction_id: str = Field(min_length=1)
    source_contest_id: str = Field(min_length=1)
    coverage: Literal["whole_jurisdiction"]
    coverage_evidence: str = Field(min_length=1)
    authority_id: str = Field(min_length=1)
    authority: str = Field(min_length=1)
    capture_evidence: str = Field(min_length=1)
    reported_at: AwareDatetime | None = None
    export_generated_at: AwareDatetime | None = None
    vote_total_basis: Literal["authority_stated", "complete_choice_sum"] = "authority_stated"
    reporting_complete: bool | None = Field(strict=True)
    ballots_counted: int | None = Field(default=None, ge=0, strict=True)
    votes_counted: int | None = Field(default=None, ge=0, strict=True)
    write_in_votes: int = Field(ge=0, strict=True)
    write_in_overrides: list[PreliminaryWriteInOverride] = Field(
        default_factory=list[PreliminaryWriteInOverride]
    )
    outcomes: list[PreliminaryOutcome] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_tally(self) -> PreliminaryRaceResults:
        if self.reported_at is None and self.export_generated_at is None:
            raise ValueError(
                "preliminary tally requires a publisher timestamp with its actual basis"
            )
        if self.vote_total_basis == "complete_choice_sum" and self.ballots_counted is not None:
            raise ValueError("a complete choice sum is votes, never contest ballots")
        choices = [outcome.choice_id for outcome in self.outcomes]
        if len(choices) != len(set(choices)):
            raise ValueError(f"race {self.race_id!r} repeats a named ballot choice")
        if (self.ballots_counted is None) == (self.votes_counted is None):
            raise ValueError("state exactly one of contest ballots or votes, never infer ballots")
        votes = sum(outcome.votes for outcome in self.outcomes) + self.write_in_votes
        if self.votes_counted is not None and self.votes_counted != votes:
            raise ValueError("authority vote total must include every named choice and write-ins")
        if self.ballots_counted is not None and self.ballots_counted < votes:
            raise ValueError("contest ballots cannot be less than the single-vote contest tally")
        return self

    @property
    def source_timestamp(self) -> datetime:
        timestamp = self.reported_at or self.export_generated_at
        if timestamp is None:
            raise ValueError("preliminary tally has no publisher timestamp")
        return timestamp


class PreliminaryRefreshFailure(ResultsModel):
    """An actual failed attempt, never a successful observation or a new count."""

    authority_id: str = Field(min_length=1)
    checked_at: AwareDatetime
    evidence: str = Field(min_length=1)


class PreliminaryElectionResults(ResultsModel):
    """Explicit unofficial admission; legacy certified schema 1.0 stays unchanged."""

    schema_version: Literal["1.1"] = "1.1"
    election_id: str = Field(min_length=1)
    status: Literal["preliminary"] = "preliminary"
    captures: list[PreliminaryCapture] = Field(min_length=1)
    races: list[PreliminaryRaceResults] = Field(min_length=1)
    failed_refreshes: list[PreliminaryRefreshFailure] = Field(
        default_factory=list[PreliminaryRefreshFailure]
    )

    @model_validator(mode="after")
    def validate_admission(self) -> PreliminaryElectionResults:
        captures = {capture.evidence: capture for capture in self.captures}
        if any(capture.publisher_is_official_results is True for capture in self.captures):
            raise ValueError("official results require the separate certified admission path")
        if len(captures) != len(self.captures):
            raise ValueError("preliminary results repeat a capture reference")
        if len({race.race_id for race in self.races}) != len(self.races):
            raise ValueError("preliminary results repeat a race id")
        for race in self.races:
            capture = captures.get(race.capture_evidence)
            if capture is None or capture.authority_id != race.authority_id:
                raise ValueError(f"race {race.race_id!r} must cite its own authority capture")
            if any(
                timestamp is not None and timestamp > capture.captured_at
                for timestamp in (race.reported_at, race.export_generated_at)
            ):
                raise ValueError(
                    "publisher count timestamp or generation timestamp "
                    "cannot follow the observation"
                )
        authority_ids = {capture.authority_id for capture in self.captures}
        if any(failure.authority_id not in authority_ids for failure in self.failed_refreshes):
            raise ValueError("refresh failure must belong to an admitted authority")
        return self


type ResultsDocument = ElectionResults | PreliminaryElectionResults
