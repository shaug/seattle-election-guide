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
  and "No. 32" — verified against a live King County export while designing
  this adapter). The exact, normalized-phrase match below resolves every
  publication-eligible wa-2026-primary race correctly by construction,
  because two different district numbers never normalize to the same text.

Unmatched or ambiguous names abort loudly
(docs/runbooks/results-certified-ingest.md, phase 2's own rule) — this
module never guesses a mapping.
"""

from __future__ import annotations

import csv
import io
import re
from datetime import date

from election_guide.inventory.models import BallotChoice, Inventory, Race
from election_guide.results.models import ElectionResults, RaceOutcome, RaceResults, ResultsCapture

REQUIRED_CSV_COLUMNS = frozenset({"Contest", "Choice", "Votes"})

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


def parse_certified_csv(content: bytes) -> dict[str, list[tuple[str, int]]]:
    """Parse a King County certified CSV export into `{contest: [(choice,
    votes), ...]}`, preserving every row exactly as declared — including
    write-in rows, whose votes still belong in a race's total even though
    they are excluded from ballot-choice resolution (see `resolve_choice`).
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
    by_contest: dict[str, list[tuple[str, int]]] = {}
    for row in reader:
        contest = (row["Contest"] or "").strip()
        choice = (row["Choice"] or "").strip()
        votes_raw = (row["Votes"] or "").strip()
        if not contest or not choice:
            raise ResultsIngestError(
                f"certified CSV export has a row with a blank contest or choice: {row!r}"
            )
        try:
            votes = int(votes_raw.replace(",", ""))
        except ValueError as error:
            raise ResultsIngestError(
                f"certified CSV export has a non-numeric vote count {votes_raw!r} for "
                f"{choice!r} in {contest!r}"
            ) from error
        if votes < 0:
            raise ResultsIngestError(
                f"certified CSV export has a negative vote count for {choice!r} in {contest!r}"
            )
        by_contest.setdefault(contest, []).append((choice, votes))
    if not by_contest:
        raise ResultsIngestError("certified CSV export contained no contest rows")
    return by_contest


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
    never a separately maintained name list. A real King County export omits
    "State" from representative contests ("Legislative District No. 32
    Representative Position No. 1") but keeps it for senate contests ("...
    State Senator") — an authentic, asymmetric convention accounted for by
    generating both the full and the "State "-stripped office phrasing."""
    phrases = {race.display_name, race.office, race.district}
    position_number: str | None = None
    if race.position:
        phrases.add(race.position)
        phrases.add(f"{race.office} {race.position}")
        phrases.add(f"{race.district} {race.office} {race.position}")
        phrases.add(f"{race.district} {race.position}")
        stripped_office = race.office.removeprefix("State ")
        phrases.add(f"{race.district} {stripped_office} {race.position}")
        match = _LEADING_POSITION_NUMBER.match(race.position)
        if match:
            position_number = match.group(1)
    if position_number is not None:
        office_tail = race.office.rsplit(" ", 1)[-1]
        phrases.add(f"{office_tail} Position {position_number}")
        phrases.add(f"City of Seattle {race.office} Position {position_number}")
    phrases.add(f"{race.office} {race.district}")
    phrases.add(f"{race.district} {race.office}")
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
    expected_race_ids: frozenset[str] | None = None,
) -> ElectionResults:
    """Turn a captured certified CSV export into a validated `ElectionResults`.

    `expected_race_ids` names exactly the races this ingest run must resolve
    from the export — every one is required, and every other publication-
    eligible race is ignored even if its contest appears in the export.
    Defaults to every publication-eligible race in the inventory. Passing a
    narrower set is how an operator honors the county-scope decision
    (docs/RESULTS.md, "Ingestion mechanics"): King County's own certified
    canvass states King County's own tally for a race whose district crosses
    a county line, not that race's true total, so a King-County-sourced
    ingest excludes those specific races rather than silently publishing a
    partial count as final.
    """
    eligible_races = {race.id: race for race in inventory.races if race.publication_eligible}
    if expected_race_ids is None:
        expected_race_ids = frozenset(eligible_races)
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
    for contest_text, rows in by_contest.items():
        race = resolve_race(contest_text, candidate_races)
        if race is None:
            continue
        if race.id in seen_contest_by_race:
            raise ResultsIngestError(
                f"certified export contests {seen_contest_by_race[race.id]!r} and "
                f"{contest_text!r} both resolved to race {race.id!r}"
            )
        seen_contest_by_race[race.id] = contest_text
        race_results.append(_build_race_results(race, rows))

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


def _build_race_results(race: Race, rows: list[tuple[str, int]]) -> RaceResults:
    """One race's tallies: `ballots_counted` is the total votes recorded for
    the contest, including write-ins, so `share` (votes / ballots_counted)
    for the declared choices sums to ~1 minus any write-in share — exactly
    the slack `RaceResults.SHARE_SUM_TOLERANCE` exists to absorb
    (`results/models.py`). The top two vote-getters advance in a
    candidate race (top-two primary); a measure's single winning choice
    advances (Approved/Rejected)."""
    tallies: list[tuple[BallotChoice, int]] = []
    total_votes = 0
    for candidate_text, votes in rows:
        total_votes += votes
        choice = resolve_choice(candidate_text, race)
        if choice is None:
            continue
        tallies.append((choice, votes))
    if not tallies:
        raise ResultsIngestError(
            f"certified export has no resolvable ballot choices for race {race.id!r}"
        )
    if total_votes <= 0:
        raise ResultsIngestError(f"certified export reports zero total votes for race {race.id!r}")

    top_count = 1 if race.race_type == "measure" else 2
    ranked = sorted(tallies, key=lambda item: (-item[1], item[0].ballot_order))
    advancing_ids = {choice.id for choice, _ in ranked[:top_count]}
    outcomes = [
        RaceOutcome(
            choice_id=choice.id,
            votes=votes,
            share=round(votes / total_votes, 4),
            advanced=choice.id in advancing_ids,
        )
        for choice, votes in sorted(tallies, key=lambda item: item[0].ballot_order)
    ]
    return RaceResults(race_id=race.id, ballots_counted=total_votes, outcomes=outcomes)
