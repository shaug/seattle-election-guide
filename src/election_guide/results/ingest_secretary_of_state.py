"""Secretary of State statewide JSON adapter: turns `results.votewa.gov`'s
statewide export into `RaceResults` entries for the races whose district
crosses a county line, merged into the King-County-sourced
`data/results/<election-id>.yaml` that `results/ingest.py` already produced
(docs/RESULTS.md, "Ingestion mechanics," County scope; issue #417).

Deliberately a sibling module, not an extension of `results/ingest.py`: the
source is JSON, not CSV, its contest-naming convention is its own
(`"State Senator - Legislative District 32"`, hyphen-separated, rather than
King County's `"Legislative District No. 32 State Senator"`), and its
write-in rows are self-identifying (`isWriteIn: true` on the ballot option
itself) rather than needing King County's own name-sniffed detection
(`_is_write_in`, `results/ingest.py`). The two modules share only what is
genuinely identical between any two export adapters for this schema: exact
normalized-text matching (`normalization.text.normalize_match_text`) and
ballot-choice resolution (`results.ingest.resolve_ballot_choice`) — never
fuzzy similarity, for the same reason `results/ingest.py`'s own module
docstring gives (two different district numbers must never normalize to the
same text).

This adapter only ever resolves `race_type: candidate` races: every one of
the eight cross-county-line races it is scoped to is a candidate race
(docs/RESULTS.md; issue #417's own scope), and there is no ballot measure in
this site's inventory whose district crosses a county line. Aborting on
anything else keeps that a fact this module checks, not one it assumes.

Unmatched, ambiguous, or missing race and candidate names abort loudly,
matching `results/ingest.py`'s own posture — this module never guesses a
mapping either.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, cast

from election_guide.inventory.models import Inventory, Race
from election_guide.normalization.text import normalize_match_text
from election_guide.results.ingest import ResultsIngestError, resolve_ballot_choice
from election_guide.results.models import RaceOutcome, RaceResults

_LEADING_POSITION_NUMBER_WORD = "Position "


@dataclass(frozen=True)
class BallotItemExport:
    """One contest's totals as the Secretary of State's own export states
    them: `vote_total` is the export's own `voteTotal` for the contest --
    every ballot option's votes, including write-ins -- and `options` is
    each option's `(name, vote_count, is_write_in)` exactly as declared."""

    name: str
    vote_total: int
    options: list[tuple[str, int, bool]]


def parse_statewide_export(content: bytes) -> list[BallotItemExport]:
    """Parse the Secretary of State's statewide JSON export into one
    `BallotItemExport` per contest (`ballotItems[]`), preserving every
    option exactly as declared -- including write-ins, whose votes are
    excluded from ballot-choice resolution and from the `share` denominator,
    but not from `vote_total` (see `resolve_sos_choice`,
    `_build_sos_race_results`)."""
    try:
        raw: Any = json.loads(content)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ResultsIngestError(f"Secretary of State export is not valid JSON: {error}") from error
    if not isinstance(raw, dict):
        raise ResultsIngestError("Secretary of State export is not a JSON object")
    payload = cast(dict[str, Any], raw)
    ballot_items_raw = payload.get("ballotItems")
    if not isinstance(ballot_items_raw, list) or not ballot_items_raw:
        raise ResultsIngestError("Secretary of State export has no ballotItems")
    parsed: list[BallotItemExport] = []
    for item_raw in cast(list[Any], ballot_items_raw):
        if not isinstance(item_raw, dict):
            raise ResultsIngestError("Secretary of State export has a non-object ballot item")
        item = cast(dict[str, Any], item_raw)
        name = _first_text(item.get("name"))
        if name is None:
            raise ResultsIngestError("Secretary of State export has a ballot item with no name")
        vote_total = item.get("voteTotal")
        if not isinstance(vote_total, int):
            raise ResultsIngestError(
                f"Secretary of State export contest {name!r} has no integer voteTotal"
            )
        summary_results = item.get("summaryResults")
        options_raw = (
            cast(dict[str, Any], summary_results).get("ballotOptions")
            if isinstance(summary_results, dict)
            else None
        )
        if not isinstance(options_raw, list) or not options_raw:
            raise ResultsIngestError(
                f"Secretary of State export contest {name!r} has no ballot options"
            )
        options: list[tuple[str, int, bool]] = []
        for option_raw in cast(list[Any], options_raw):
            if not isinstance(option_raw, dict):
                raise ResultsIngestError(
                    f"Secretary of State export contest {name!r} has a non-object ballot option"
                )
            option = cast(dict[str, Any], option_raw)
            option_name = _first_text(option.get("name"))
            vote_count = option.get("voteCount")
            if option_name is None or not isinstance(vote_count, int):
                raise ResultsIngestError(
                    f"Secretary of State export contest {name!r} has a ballot option missing a "
                    "name or vote count"
                )
            options.append((option_name, vote_count, bool(option.get("isWriteIn"))))
        parsed.append(BallotItemExport(name=name, vote_total=vote_total, options=options))
    return parsed


def _first_text(name_entries: object) -> str | None:
    if not isinstance(name_entries, list):
        return None
    for entry in cast(list[Any], name_entries):
        text = cast(dict[str, Any], entry).get("text") if isinstance(entry, dict) else None
        if text:
            return str(text)
    return None


def _sos_race_match_phrases(race: Race) -> set[str]:
    """Every normalized phrase this race's contest could plausibly carry in
    the Secretary of State's statewide export, built only from the
    inventory's own official fields.

    The base phrase (`"{office} - {district}"`) and the position variant
    (`"{office} Pos. {N} - {district}"`) resolve every one of the four
    cross-county legislative and congressional races this adapter is scoped
    to (`us-house-9`, `ld-32-state-senator`,
    `ld-32-state-representative-{1,2}`), verified against the committed
    export at `data/manifests/evidence/
    capture-wa-secretary-of-state-20260819T231643Z-a17ab1addf26.json` while
    designing this resolver. The Supreme Court branch is a targeted special
    case for the export's own `"Justice Position #0N - Supreme Court"`
    convention, which names no district or position number this inventory's
    `office`/`district`/`position` fields carry directly -- its own alias
    (`"Justice Position #0N"`, already carried for the King County adapter's
    resolver) plus the export's fixed `" - Supreme Court"` suffix is the
    exact and only string this authority publishes for those four races, the
    same "special-cased for one authentic export convention, not invented
    for every race" posture `results/ingest.py`'s own Citywide branch takes
    for King County's export.
    """
    phrases = {f"{race.office} - {race.district}"}
    if race.position and race.position.startswith(_LEADING_POSITION_NUMBER_WORD):
        position_number = race.position.removeprefix(_LEADING_POSITION_NUMBER_WORD).split(" ", 1)[0]
        if position_number.isdigit():
            phrases.add(f"{race.office} Pos. {position_number} - {race.district}")
    if race.office == "Supreme Court Justice":
        phrases.update(f"{alias} - Supreme Court" for alias in race.aliases)
    return {normalize_match_text(phrase) for phrase in phrases if phrase}


def resolve_sos_race(contest_text: str, races: list[Race]) -> Race | None:
    """Match one export contest name against exactly one candidate race.
    Returns `None` for a contest outside this site's inventory -- the normal
    case for the export's other 139 statewide contests. Aborts when a
    contest name matches more than one race: never guessed."""
    normalized = normalize_match_text(contest_text)
    hits = [race for race in races if normalized in _sos_race_match_phrases(race)]
    if len(hits) > 1:
        raise ResultsIngestError(
            f"Secretary of State export contest {contest_text!r} matches more than one race: "
            f"{sorted(race.id for race in hits)}"
        )
    return hits[0] if hits else None


def build_sos_race_results(
    json_content: bytes,
    inventory: Inventory,
    *,
    authority: str,
    capture_evidence: str,
    expected_race_ids: frozenset[str],
) -> list[RaceResults]:
    """Turn a captured Secretary of State statewide export into the
    `RaceResults` for `expected_race_ids` -- every one is required, and every
    other contest in the export is ignored. Merging these into an existing
    committed file is `results.ingest.merge_race_results`'s job, not this
    function's (issue #417's own "why this is not a King County ingest": the
    two adapters produce races, a shared merge step combines them).
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
    non_candidate = {
        race_id for race_id in expected_race_ids if eligible_races[race_id].race_type != "candidate"
    }
    if non_candidate:
        raise ResultsIngestError(
            f"Secretary of State adapter only resolves candidate races, not: "
            f"{sorted(non_candidate)}"
        )
    candidate_races = [eligible_races[race_id] for race_id in expected_race_ids]

    race_results: list[RaceResults] = []
    seen_contest_by_race: dict[str, str] = {}
    for item in parse_statewide_export(json_content):
        race = resolve_sos_race(item.name, candidate_races)
        if race is None:
            continue
        if race.id in seen_contest_by_race:
            raise ResultsIngestError(
                f"Secretary of State export contests {seen_contest_by_race[race.id]!r} and "
                f"{item.name!r} both resolved to race {race.id!r}"
            )
        seen_contest_by_race[race.id] = item.name
        race_results.append(
            _build_sos_race_results(
                race, item, authority=authority, capture_evidence=capture_evidence
            )
        )

    missing = expected_race_ids - seen_contest_by_race.keys()
    if missing:
        raise ResultsIngestError(
            f"Secretary of State export did not include {len(missing)} expected race(s): "
            f"{sorted(missing)}"
        )
    return sorted(race_results, key=lambda result: result.race_id)


def _build_sos_race_results(
    race: Race, item: BallotItemExport, *, authority: str, capture_evidence: str
) -> RaceResults:
    """One race's tallies from the Secretary of State's own export.

    `votes_counted` is `item.vote_total` -- the export's own `voteTotal`,
    taken directly rather than re-derived from the resolved options, exactly
    as `results/ingest.py`'s `ballots_counted` takes King County's
    `BallotsWith Contest` verbatim. `share` is each declared choice's votes
    over the declared (non-write-in) vote total, matching that same module's
    reasoning: a write-in-inclusive denominator would abort this race's
    ingest the moment its write-in tally passed a single point.
    """
    tallies: list[tuple[str, int]] = []
    declared_votes = 0
    resolved_ids: set[str] = set()
    for option_name, vote_count, is_write_in in item.options:
        if is_write_in:
            continue
        choice = resolve_ballot_choice(option_name, race)
        declared_votes += vote_count
        tallies.append((choice.id, vote_count))
        resolved_ids.add(choice.id)
    if not tallies:
        raise ResultsIngestError(
            f"Secretary of State export has no resolvable ballot choices for race {race.id!r}"
        )
    missing_choice_ids = {choice.id for choice in race.choices} - resolved_ids
    if missing_choice_ids:
        raise ResultsIngestError(
            f"Secretary of State export for race {race.id!r} is missing "
            f"{len(missing_choice_ids)} declared ballot choice(s): {sorted(missing_choice_ids)}"
        )
    if item.vote_total <= 0:
        raise ResultsIngestError(
            f"Secretary of State export reports zero voteTotal for race {race.id!r}"
        )
    if declared_votes <= 0:
        raise ResultsIngestError(
            f"Secretary of State export reports zero votes for every declared ballot choice in "
            f"race {race.id!r}; only write-in rows carry votes"
        )

    ballot_order = {choice.id: choice.ballot_order for choice in race.choices}
    ranked = sorted(tallies, key=lambda pair: (-pair[1], ballot_order[pair[0]]))
    advancing_ids = {choice_id for choice_id, _ in ranked[:2]}
    outcomes = [
        RaceOutcome(
            choice_id=choice_id,
            votes=votes,
            share=round(votes / declared_votes, 4),
            advanced=choice_id in advancing_ids,
        )
        for choice_id, votes in sorted(tallies, key=lambda pair: ballot_order[pair[0]])
    ]
    return RaceResults(
        race_id=race.id,
        authority=authority,
        capture_evidence=capture_evidence,
        votes_counted=item.vote_total,
        outcomes=outcomes,
    )
