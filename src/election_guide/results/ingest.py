"""Certified-results CSV adapter: turns King County's certified export into
`data/results/<election-id>.yaml`'s validated contract (docs/RESULTS.md,
"Ingestion mechanics").

This adapter is deliberately distinct from `election_guide.collection`: that
module's `AdapterSpec` targets regex-based endorsement decisions extracted
from HTML or PDF source pages. A certified results export is tabular vote
data with a different resolution problem — matching an authority's own
contest and choice labels to the frozen ballot inventory's race and
ballot-choice IDs — so this module owns a dedicated, deterministic resolver
rather than reusing the collection adapter's regex-decision machinery, or the
endorsement pipeline's fuzzy, review-queueing matcher
(`election_guide.normalization.matching`). Two reasons rule that reuse out:

- A results file is one official, audited artifact assembled in a single
  adapter run, not a stream of per-source claims destined for a human review
  queue — there is nowhere for an "ambiguous" result to wait.
- Fuzzy text similarity actively confuses this export's own contest names,
  which differ only by an embedded district number ("Legislative District
  No. 1 Representative Position No. 1" scores as a close match to "No. 11"
  and "No. 32"). The exact, normalized-phrase match below resolves every
  publication-eligible wa-2026-primary race correctly by construction,
  because two different district numbers never normalize to the same text.
  `REAL_CONTEST_LABEL_BY_RACE_ID` (`tests/test_results.py`) records all 32
  of those races' King County contest labels as observed live on
  2026-08-07, and
  `test_resolve_race_matches_every_publication_eligible_race_label` runs
  the resolver against every one of them offline. That committed test
  proves the resolver maps those 32 strings to the right races; the
  strings' fidelity to King County's own export rests on the capture-time
  observation recorded beside them, not on the test.

Unmatched or ambiguous names abort loudly
(docs/runbooks/results-certified-ingest.md, phase 2's own rule) — this
module never guesses a mapping.
"""

from __future__ import annotations

import csv
import io
import re
from dataclasses import dataclass
from datetime import date

from election_guide.inventory.models import BallotChoice, Inventory, Race
from election_guide.results.models import ElectionResults, RaceOutcome, RaceResults, ResultsCapture

REQUIRED_CSV_COLUMNS = frozenset({"Contest", "Choice", "Votes", "BallotsWith Contest"})


@dataclass(frozen=True)
class ContestRows:
    """One contest's rows plus the export's own count of ballots that
    carried it — a different, authority-reported quantity from the sum of
    this adapter's own vote tallies (overvotes and undervotes are ballots
    the contest recorded that no candidate's vote count reflects), and the
    one `_build_race_results` uses for `ballots_counted`
    (docs/RESULTS.md, Data model)."""

    ballots_with_contest: int
    choices: list[tuple[str, int]]


# Matches the Unicode hyphen/dash block (U+2010 HYPHEN through U+2015
# HORIZONTAL BAR) plus the ASCII hyphen-minus, so an inventory display name
# built with an em dash ("Metropolitan King County Council — District 8")
# normalizes the same way as the export's own plain-ASCII punctuation.
_DASH_OR_PUNCTUATION = re.compile(r"[.,\u2010-\u2015-]")
_VOTE_FOR_SUFFIX = re.compile(r"\(Vote for \d+\)", re.IGNORECASE)
_ORDINAL_NO = re.compile(r"\bNo\.\s*(\d+)", re.IGNORECASE)
_LEADING_POSITION_NUMBER = re.compile(r"Position\s+(\d+)")


class ResultsIngestError(ValueError):
    """Raised when a captured export cannot be resolved against the ballot
    inventory without guessing (docs/RESULTS.md, docs/COLLECTION.md)."""


def parse_certified_csv(content: bytes) -> dict[str, ContestRows]:
    """Parse a King County certified CSV export into `{contest: ContestRows}`,
    preserving every row exactly as declared — including write-in rows,
    whose votes are excluded from ballot-choice resolution and from the
    `share` denominator, but not from `ballots_with_contest`, the export's
    own count of ballots that carried the contest (see `resolve_choice`,
    `_build_race_results`).
    """
    try:
        text = content.decode("utf-8-sig")
    except UnicodeDecodeError as error:
        raise ResultsIngestError(f"certified CSV export is not valid UTF-8: {error}") from error
    reader = csv.DictReader(io.StringIO(text))
    fieldnames = set(reader.fieldnames or ())
    if not REQUIRED_CSV_COLUMNS.issubset(fieldnames):
        raise ResultsIngestError(
            f"certified CSV export is missing required columns {sorted(REQUIRED_CSV_COLUMNS)}; "
            f"found {sorted(fieldnames)}"
        )
    choices_by_contest: dict[str, list[tuple[str, int]]] = {}
    ballots_with_contest_by_contest: dict[str, int] = {}
    for row in reader:
        contest = (row["Contest"] or "").strip()
        choice = (row["Choice"] or "").strip()
        votes_raw = (row["Votes"] or "").strip()
        ballots_raw = (row["BallotsWith Contest"] or "").strip()
        if not contest or not choice:
            raise ResultsIngestError(
                f"certified CSV export has a row with a blank contest or choice: {row!r}"
            )
        votes = _parse_export_int(votes_raw, f"vote count for {choice!r} in {contest!r}")
        ballots_with_contest = _parse_export_int(
            ballots_raw, f"ballots-with-contest count for {contest!r}"
        )
        if contest in ballots_with_contest_by_contest:
            if ballots_with_contest_by_contest[contest] != ballots_with_contest:
                raise ResultsIngestError(
                    f"certified CSV export reports two different ballots-with-contest counts "
                    f"for {contest!r}: {ballots_with_contest_by_contest[contest]} and "
                    f"{ballots_with_contest}"
                )
        else:
            ballots_with_contest_by_contest[contest] = ballots_with_contest
        choices_by_contest.setdefault(contest, []).append((choice, votes))
    if not choices_by_contest:
        raise ResultsIngestError("certified CSV export contained no contest rows")
    return {
        contest: ContestRows(
            ballots_with_contest=ballots_with_contest_by_contest[contest], choices=rows
        )
        for contest, rows in choices_by_contest.items()
    }


def _parse_export_int(raw: str, label: str) -> int:
    try:
        value = int(raw.replace(",", ""))
    except ValueError as error:
        raise ResultsIngestError(
            f"certified CSV export has a non-numeric {label}: {raw!r}"
        ) from error
    if value < 0:
        raise ResultsIngestError(f"certified CSV export has a negative {label}: {value}")
    return value


def _normalize_contest_text(text: str) -> str:
    text = _VOTE_FOR_SUFFIX.sub("", text)
    text = _ORDINAL_NO.sub(r"\1", text)
    text = _DASH_OR_PUNCTUATION.sub(" ", text)
    return " ".join(text.casefold().split())


def _normalize_candidate_text(text: str) -> str:
    return " ".join(text.casefold().split())


def _is_write_in(candidate_text: str) -> bool:
    return re.sub(r"[\s-]", "", candidate_text).casefold() == "writein"


def _race_match_phrases(race: Race) -> set[str]:
    """Every normalized phrase this race's contest could plausibly carry in a
    certified export, built only from the inventory's own official fields —
    never a separately maintained name list.

    Every generator below is individually load-bearing for at least one of
    the 32 publication-eligible wa-2026-primary races' King County contest
    labels as observed live on 2026-08-07 while designing this resolver, and
    `test_resolve_race_matches_every_publication_eligible_race_label`
    (`tests/test_results.py`) re-runs the resolver against that committed
    table of labels offline on every test run.
    `race.display_name` and a bare `race.position` are deliberately absent:
    neither matched any of those 32 observed labels
    (`display_name` duplicates what `district` alone already resolves for
    every race that needs it; every inventory `position` value carries a
    trailing qualifier no export states, e.g. "Position 1 — unexpired
    2-year term").
    """
    # A real King County export omits "State" from representative contests
    # ("Legislative District No. 32 Representative Position No. 1") but
    # keeps it for senate contests ("... State Senator") — an authentic,
    # asymmetric convention `office` (unstripped, for senate) and
    # `stripped_office` (for representative, below) together account for.
    phrases = {
        race.office,
        race.district,
        f"{race.office} {race.district}",
        f"{race.district} {race.office}",
    }
    position_number: str | None = None
    if race.position:
        stripped_office = race.office.removeprefix("State ")
        phrases.add(f"{race.district} {stripped_office} {race.position}")
        match = _LEADING_POSITION_NUMBER.match(race.position)
        if match:
            position_number = match.group(1)
    if position_number is not None:
        office_tail = race.office.rsplit(" ", 1)[-1]
        phrases.add(f"{office_tail} Position {position_number}")
        # Only a "City of Seattle ..." contest carries that prefix in a real
        # export (`seattle-municipal-court-judge-5`, the inventory's only
        # `district: Citywide` race with a position) — scoped to that
        # jurisdiction rather than added for every position-bearing race,
        # which would otherwise manufacture a label no authority publishes
        # for every legislative-district and judicial race instead.
        if race.district == "Citywide":
            phrases.add(f"City of Seattle {race.office} Position {position_number}")
    phrases.update(race.aliases)
    return {_normalize_contest_text(phrase) for phrase in phrases if phrase}


def _candidate_match_terms(choice: BallotChoice) -> set[str]:
    terms = {choice.official_name, choice.display_name, *choice.aliases}
    return {_normalize_candidate_text(term) for term in terms if term}


def resolve_race(contest_text: str, races: list[Race]) -> Race | None:
    """Match one CSV contest label against exactly one candidate race.

    Returns `None` when the contest matches none of the given races — the
    normal case for the export's many contests outside this site's inventory
    (other jurisdictions, precinct committee officers, other counties'
    measures). Aborts when a contest label matches more than one race: that
    is never guessed at (docs/COLLECTION.md).
    """
    normalized = _normalize_contest_text(contest_text)
    hits = [race for race in races if normalized in _race_match_phrases(race)]
    if len(hits) > 1:
        raise ResultsIngestError(
            f"certified export contest {contest_text!r} matches more than one race: "
            f"{sorted(race.id for race in hits)}"
        )
    return hits[0] if hits else None


def resolve_choice(candidate_text: str, race: Race) -> BallotChoice | None:
    """Match one CSV choice label against exactly one of the race's ballot
    choices. Returns `None` for a write-in row, which this schema never
    enumerates as a ballot choice (docs/RESULTS.md). Aborts for anything
    else that is unresolved or ambiguous."""
    if _is_write_in(candidate_text):
        return None
    normalized = _normalize_candidate_text(candidate_text)
    hits = [choice for choice in race.choices if normalized in _candidate_match_terms(choice)]
    if len(hits) != 1:
        raise ResultsIngestError(
            f"certified export choice {candidate_text!r} for race {race.id!r} matched "
            f"{len(hits)} ballot choices, not exactly one"
        )
    return hits[0]


def build_election_results(
    csv_content: bytes,
    inventory: Inventory,
    *,
    authority: str,
    certified_on: date,
    captures: list[ResultsCapture],
    expected_race_ids: frozenset[str],
) -> ElectionResults:
    """Turn a captured certified CSV export into a validated `ElectionResults`.

    `expected_race_ids` names exactly the races this ingest run must resolve
    from the export — every one is required, and every other publication-
    eligible race is ignored even if its contest appears in the export.

    There is deliberately no "every publication-eligible race" default: an
    election almost always has at least one race a given authority's export
    cannot state the true total for (docs/RESULTS.md, "Ingestion mechanics,"
    County scope — for wa-2026-primary, King County's own canvass does not
    suffice for a race whose district crosses a county line). A silent
    default would let an ordinary King-County-sourced run publish those
    races' partial county tallies as if they were final; naming the expected
    races explicitly is how an operator honors that decision instead.
    """
    eligible_races = {race.id: race for race in inventory.races if race.publication_eligible}
    unknown_expected = expected_race_ids - eligible_races.keys()
    if unknown_expected:
        raise ResultsIngestError(
            f"expected race ids are not publication-eligible in the inventory: "
            f"{sorted(unknown_expected)}"
        )
    if not expected_race_ids:
        raise ResultsIngestError("no race is expected from this ingest run")
    candidate_races = [eligible_races[race_id] for race_id in expected_race_ids]

    by_contest = parse_certified_csv(csv_content)
    race_results: list[RaceResults] = []
    seen_contest_by_race: dict[str, str] = {}
    for contest_text, contest_rows in by_contest.items():
        race = resolve_race(contest_text, candidate_races)
        if race is None:
            continue
        if race.id in seen_contest_by_race:
            raise ResultsIngestError(
                f"certified export contests {seen_contest_by_race[race.id]!r} and "
                f"{contest_text!r} both resolved to race {race.id!r}"
            )
        seen_contest_by_race[race.id] = contest_text
        race_results.append(_build_race_results(race, contest_rows))

    missing = expected_race_ids - seen_contest_by_race.keys()
    if missing:
        raise ResultsIngestError(
            f"certified export did not include {len(missing)} expected race(s): {sorted(missing)}"
        )

    return ElectionResults(
        election_id=inventory.election.id,
        status="certified",
        certified_on=certified_on,
        authority=authority,
        captures=captures,
        races=sorted(race_results, key=lambda result: result.race_id),
    )


def _build_race_results(race: Race, contest_rows: ContestRows) -> RaceResults:
    """One race's tallies, with two different counts doing two jobs.

    `ballots_counted` is `ballots_with_contest` — King County's own count of
    ballots whose ballot style carried this contest, straight from the
    export's `BallotsWith Contest` column, not derived from this adapter's
    own vote sum. That is a materially different, larger quantity than the
    sum of recorded votes: it includes every overvoted and undervoted
    ballot, the ones the contest recorded but no vote count reflects
    (docs/RESULTS.md, Data model — the race card's provenance line and the
    endorsements-dialog certified strip both render "ballots counted", the
    authority's own figure, not a re-derivation of it).

    Each declared choice's `share`, by contrast, is its votes over the
    *declared* (non-write-in) vote total, so a race's declared shares sum to
    ~1 by construction however large its write-in tally is;
    `RaceResults.SHARE_SUM_TOLERANCE` (`results/models.py`) then only ever
    absorbs the fourth-decimal rounding applied below. A write-in-inclusive
    `share` denominator would instead have made declared shares sum to
    exactly one minus the write-in share, aborting the *whole* multi-race
    ingest run whenever any one race's write-ins passed a single point of its
    total — the ordinary case, not an anomaly, for the six wa-2026-primary
    races whose ballot carries exactly one declared candidate
    (`ld-11-state-representative-2`, `ld-34-state-representative-1`,
    `ld-34-state-senator`, `ld-36-state-representative-1`,
    `ld-36-state-representative-2`, `ld-43-state-representative-2`), where
    the write-in row is a voter's only alternative to that candidate.

    The top two vote-getters advance in a candidate race (top-two primary); a
    measure's single winning choice — whichever of its two declared outcomes
    drew more votes, `Yes` or `No` — advances. `advanced` marks the choice
    that prevailed, not the choice a reader would call a good outcome: on a
    rejected measure it is the `No` choice that carries it. Deriving a
    rendered "Approved"/"Rejected" label from *which* choice advanced is
    `#285`'s decision, not this adapter's.
    """
    tallies: list[tuple[BallotChoice, int]] = []
    declared_votes = 0
    for candidate_text, votes in contest_rows.choices:
        choice = resolve_choice(candidate_text, race)
        if choice is None:
            continue
        declared_votes += votes
        tallies.append((choice, votes))
    if not tallies:
        raise ResultsIngestError(
            f"certified export has no resolvable ballot choices for race {race.id!r}"
        )
    # The loop above only ever proves that every *exported* row resolves to
    # a known choice; a row missing entirely from a truncated or malformed
    # export is invisible to it. Without this check a missing choice would
    # silently renormalize `share` over the survivors -- the schema's
    # "shares sum to ~1" invariant (results/models.py) is satisfied either
    # way, so nothing downstream would ever catch it (verified: dropping one
    # of the fixture's four Assessor candidates still produces a
    # `results validate`-clean file, with the remaining candidates' shares
    # inflated to fill the gap). Every declared ballot choice the inventory
    # names for this race must appear in the export, or this aborts.
    resolved_ids = {choice.id for choice, _ in tallies}
    missing_choice_ids = {choice.id for choice in race.choices} - resolved_ids
    if missing_choice_ids:
        raise ResultsIngestError(
            f"certified export for race {race.id!r} is missing "
            f"{len(missing_choice_ids)} declared ballot choice(s): {sorted(missing_choice_ids)}"
        )
    if contest_rows.ballots_with_contest <= 0:
        raise ResultsIngestError(
            f"certified export reports zero ballots-with-contest for race {race.id!r}"
        )
    if declared_votes <= 0:
        raise ResultsIngestError(
            f"certified export reports zero votes for every declared ballot choice in race "
            f"{race.id!r}; only write-in rows carry votes"
        )

    top_count = 1 if race.race_type == "measure" else 2
    ranked = sorted(tallies, key=lambda item: (-item[1], item[0].ballot_order))
    advancing_ids = {choice.id for choice, _ in ranked[:top_count]}
    outcomes = [
        RaceOutcome(
            choice_id=choice.id,
            votes=votes,
            share=round(votes / declared_votes, 4),
            advanced=choice.id in advancing_ids,
        )
        for choice, votes in sorted(tallies, key=lambda item: item[0].ballot_order)
    ]
    return RaceResults(
        race_id=race.id,
        ballots_counted=contest_rows.ballots_with_contest,
        outcomes=outcomes,
    )
