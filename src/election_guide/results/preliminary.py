"""Read captured preliminary formats without inventing admission/coverage facts.

These parsers do not fetch, write a production result file or infer certification.
In particular the Media Export's generation time is not a publisher count time.
Reviewed whole-contest mapping and capture admission remain separate requirements.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any, Literal, cast

from pydantic import Field

from election_guide.authorities.registry import read_authority_registry
from election_guide.evidence.models import CapturedManifest
from election_guide.evidence.storage import (
    captured_artifact_path,
    read_capture_manifest,
    verify_capture,
)
from election_guide.inventory.models import Inventory, Race
from election_guide.results.ingest import resolve_ballot_choice
from election_guide.results.models import (
    PreliminaryCapture,
    PreliminaryElectionResults,
    PreliminaryOutcome,
    PreliminaryRaceResults,
    PreliminaryWriteInOverride,
    ResultsModel,
)
from election_guide.results.validation import validate_results_evidence, validate_results_inventory


@dataclass(frozen=True)
class SourceChoice:
    id: str
    name: str
    votes: int
    is_write_in: bool | None


@dataclass(frozen=True)
class SourceContest:
    id: str
    name: str
    choices: tuple[SourceChoice, ...]
    reported_at: datetime | None
    votes_counted: int | None
    reporting_complete: bool | None
    kind: str


@dataclass(frozen=True)
class PreliminaryFeed:
    election_date: date
    jurisdiction: str
    publisher_jurisdiction_id: str
    is_official_results: bool | None
    generated_at: datetime | None
    contests: dict[str, SourceContest]


def _object(value: object, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be an object")
    return cast(dict[str, Any], value)


def _array(value: object, label: str) -> list[Any]:
    if not isinstance(value, list):
        raise ValueError(f"{label} must be an array")
    return cast(list[Any], value)


def _text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} must be nonempty text")
    return value


def _name(value: object) -> str:
    if isinstance(value, str):
        return _text(value, "name")
    names = [_object(item, "name") for item in _array(value, "language names")]
    english = [item for item in names if item.get("languageId") == "en"]
    if len(english) != 1:
        raise ValueError("source must state exactly one English name")
    return _text(english[0].get("text"), "English name")


def _count(value: object) -> int:
    if type(value) is not int or value < 0:
        raise ValueError("source count must be a strict nonnegative integer")
    return value


def _clock(value: object) -> datetime | None:
    if value is None:
        return None
    parsed = datetime.fromisoformat(_text(value, "source timestamp"))
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("source timestamp requires a timezone")
    return parsed


def _contest(raw: dict[str, Any], *, county: bool) -> SourceContest:
    if county:
        options = _object(raw.get("summaryResults"), "summaryResults").get("ballotOptions")
    else:
        options = raw.get("ballotOptions")
    choices: list[SourceChoice] = []
    for value in _array(options, "ballotOptions"):
        option = _object(value, "ballot option")
        name = _name(option.get("name"))
        if county:
            write_in = option.get("isWriteIn")
            if type(write_in) is not bool:
                raise ValueError("County source must state isWriteIn explicitly")
        else:
            # Export supplies no isWriteIn flag. Only its explicit generic
            # write-in row is recognized here; other choice classification
            # needs the reviewed frozen-ballot mapping, never a guessed flag.
            write_in = True if name.casefold() in {"write-in", "write in"} else None
        choices.append(
            SourceChoice(
                id=_text(option.get("id"), "source choice id"),
                name=name,
                votes=_count(option.get("voteCount")),
                is_write_in=write_in,
            )
        )
    if not choices or len({item.id for item in choices}) != len(choices):
        raise ValueError("source contest must contain distinct choices")
    status = raw.get("reportingStatus")
    reported_at = _clock(_object(status, "reportingStatus").get("asOf")) if county else None
    total = _count(raw["voteTotal"]) if county else None
    if total is not None and total != sum(choice.votes for choice in choices):
        raise ValueError("source vote total disagrees with its complete choice rows")
    return SourceContest(
        id=_text(raw.get("id"), "source contest id"),
        name=_name(raw.get("name")),
        choices=tuple(choices),
        reported_at=reported_at,
        votes_counted=total,
        # 0/0 units and export nulls do not mean all reporting is complete.
        reporting_complete=None,
        kind=_text(raw.get("contestType"), "contest type"),
    )


def parse_preliminary_feed(
    content: bytes, *, format: Literal["county", "statewide"]
) -> PreliminaryFeed:
    """Preserve supported source facts and explicit unknowns from a captured export.

    `format` is selected by the reviewed capture binding, not auto-discovered
    from a successful parse. A County feed never becomes statewide through
    empty crossCounties; the statewide export uses results, never localResults.
    """
    try:
        raw = _object(json.loads(content.decode("utf-8-sig")), "results publication")
    except (UnicodeError, json.JSONDecodeError) as error:
        raise ValueError("results publication is not supported JSON") from error
    if format == "county":
        election = _object(raw.get("election"), "County election")
        publisher = _object(raw.get("jurisdiction"), "County jurisdiction")
        jurisdiction = _text(publisher.get("shortName"), "County jurisdiction shortName")
        official = election.get("isOfficialResults")
        if type(official) is not bool:
            raise ValueError("County source must state official status")
        election_date = date.fromisoformat(_text(election.get("electionDate"), "election date"))
        generated_at = None
        items = raw.get("ballotItems")
    elif format == "statewide":
        publisher = _object(raw.get("results"), "statewide results")
        if publisher.get("name") != "Washington":
            raise ValueError("statewide export must identify Washington's aggregate")
        jurisdiction = "washington"
        election_date = date.fromisoformat(_text(raw.get("electionDate"), "election date"))
        generated_at = _clock(raw.get("createdAt"))
        official_flags = [raw.get("isOfficialResults"), publisher.get("isOfficialResults")]
        if any(value is not None and type(value) is not bool for value in official_flags):
            raise ValueError("State official status must be an explicit boolean or absent")
        stated = {value for value in official_flags if value is not None}
        if len(stated) > 1:
            raise ValueError("State official-status fields disagree")
        official = next(iter(stated), None)
        items = publisher.get("ballotItems")
    else:
        raise ValueError("unsupported preliminary source format")
    contests: dict[str, SourceContest] = {}
    for value in _array(items, "ballotItems"):
        contest = _contest(_object(value, "contest"), county=format == "county")
        if contest.id in contests:
            raise ValueError(f"duplicate contest id {contest.id!r}")
        contests[contest.id] = contest
    if not contests:
        raise ValueError("source export contains no contests")
    return PreliminaryFeed(
        election_date=election_date,
        jurisdiction=jurisdiction,
        publisher_jurisdiction_id=_text(publisher.get("id"), "publisher jurisdiction id"),
        is_official_results=official,
        generated_at=generated_at,
        contests=contests,
    )


class PreliminarySourceBinding(ResultsModel):
    authority_id: str = Field(min_length=1)
    format: Literal["county", "statewide"]
    evidence: str = Field(min_length=1)
    publisher_jurisdiction_id: str | None = Field(default=None, min_length=1)


class PreliminaryChoiceBinding(ResultsModel):
    source_choice_id: str = Field(min_length=1)
    source_name: str = Field(min_length=1)
    choice_id: str = Field(min_length=1)


class PreliminaryRaceBinding(ResultsModel):
    race_id: str = Field(min_length=1)
    jurisdiction_id: str = Field(min_length=1)
    source_jurisdiction: str = Field(min_length=1)
    coverage: Literal["whole_jurisdiction"]
    coverage_evidence: str = Field(min_length=1)
    source_contest_id: str = Field(min_length=1)
    source_contest_name: str = Field(min_length=1)
    capture_evidence: str = Field(min_length=1)
    choices: list[PreliminaryChoiceBinding] = Field(min_length=1)
    coverage_basis: Literal["state_aggregate", "county_containment"] | None = None
    write_in_overrides: list[PreliminaryWriteInOverride] = Field(
        default_factory=list[PreliminaryWriteInOverride]
    )


class PreliminaryAdmissionPlan(ResultsModel):
    """Reviewed source/coverage mapping, not a publisher-supplied assertion.

    All IDs/names and the geographic proof are explicit. An empty County
    crossCounties array never manufactures this mapping. The complete map and
    original proof must be reviewed before normal production admission.
    """

    schema_version: Literal["1.0"] = "1.0"
    election_id: str = Field(pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
    sources: list[PreliminarySourceBinding] = Field(min_length=1)
    races: list[PreliminaryRaceBinding] = Field(min_length=1)


def build_preliminary_results(
    plan: PreliminaryAdmissionPlan | dict[str, Any],
    inventory: Inventory,
    *,
    repository_root: Path = Path("."),
) -> PreliminaryElectionResults:
    """Build only from retained official bytes and an explicit whole-inventory map.

    Missing publisher metadata stays missing. Generation is explicitly labeled;
    a complete-choice sum is tagged as calculated votes, never ballots or a
    publisher-stated total. No certification is inferred from the calendar.
    This function performs no requests and writes nothing.
    """
    plan = PreliminaryAdmissionPlan.model_validate(plan)
    if plan.election_id != inventory.election.id:
        raise ValueError("preliminary mapping belongs to a different election")
    races = {item.race_id: item for item in plan.races}
    if len(races) != len(plan.races) or set(races) != {race.id for race in inventory.races}:
        raise ValueError("preliminary mapping must account for every inventory race exactly once")
    registry = read_authority_registry(repository_root / "config/authorities/default.yaml")
    authorities = {item.id: item for item in registry.authorities}
    captures: dict[str, PreliminaryCapture] = {}
    feeds: dict[str, PreliminaryFeed] = {}
    for binding in plan.sources:
        manifest = read_capture_manifest(repository_root / binding.evidence)
        if (
            not isinstance(manifest, CapturedManifest)
            or manifest.storage_scope != "repository"
            or manifest.source_id != binding.authority_id
            or manifest.source_id not in authorities
        ):
            raise ValueError("preliminary source must be a retained registered authority capture")
        if binding.evidence in captures:
            raise ValueError("preliminary mapping repeats a source capture")
        verify_capture(
            manifest,
            repository_root / "data/snapshots",
            repository_storage_root=repository_root / "data/evidence/official",
        )
        path = captured_artifact_path(
            manifest,
            repository_root / "data/snapshots",
            repository_storage_root=repository_root / "data/evidence/official",
        )
        feed = parse_preliminary_feed(path.read_bytes(), format=binding.format)
        if feed.election_date != inventory.election.election_date:
            raise ValueError("source feed belongs to a different election date")
        if feed.is_official_results is True:
            raise ValueError("official results require separate certified admission")
        if (
            binding.publisher_jurisdiction_id is not None
            and binding.publisher_jurisdiction_id != feed.publisher_jurisdiction_id
        ):
            raise ValueError("publisher jurisdiction identity changed")
        feeds[binding.evidence] = feed
        captures[binding.evidence] = PreliminaryCapture(
            authority_id=binding.authority_id,
            captured_at=manifest.retrieved_at,
            evidence=binding.evidence,
            publisher_is_official_results=feed.is_official_results,
        )
    result_races: list[PreliminaryRaceResults] = []
    for race in inventory.races:
        binding = races[race.id]
        capture = captures.get(binding.capture_evidence)
        if capture is None:
            raise ValueError("race mapping must cite its declared source capture")
        feed = feeds[binding.capture_evidence]
        if (
            binding.jurisdiction_id != race.jurisdiction_id
            or binding.source_jurisdiction != feed.jurisdiction
        ):
            raise ValueError("source jurisdiction disagrees with the reviewed coverage mapping")
        contest = feed.contests.get(binding.source_contest_id)
        if contest is None or contest.name != binding.source_contest_name:
            raise ValueError("source contest ID/name changed or is missing")
        expected_kind = "BallotMeasure" if race.race_type == "measure" else "Candidate"
        if contest.kind != expected_kind:
            raise ValueError("source contest type disagrees with the frozen race")
        _validate_coverage(binding, feed, inventory)
        if contest.reported_at is None and feed.generated_at is None:
            raise ValueError("publisher timestamp unavailable; do not substitute retrieval time")
        outcomes = _mapped_outcomes(binding, contest, race)
        _, write_ins = _classified_choices(binding, contest)
        result_races.append(
            PreliminaryRaceResults(
                race_id=race.id,
                jurisdiction_id=race.jurisdiction_id,
                source_contest_id=contest.id,
                coverage=binding.coverage,
                coverage_evidence=binding.coverage_evidence,
                authority_id=capture.authority_id,
                authority=authorities[capture.authority_id].name,
                capture_evidence=capture.evidence,
                reported_at=contest.reported_at,
                export_generated_at=feed.generated_at,
                reporting_complete=contest.reporting_complete,
                votes_counted=contest.votes_counted
                if contest.votes_counted is not None
                else sum(item.votes for item in contest.choices),
                vote_total_basis="authority_stated"
                if contest.votes_counted is not None
                else "complete_choice_sum",
                write_in_votes=sum(item.votes for item in write_ins),
                write_in_overrides=binding.write_in_overrides,
                outcomes=outcomes,
            )
        )
    results = PreliminaryElectionResults(
        election_id=inventory.election.id,
        captures=list(captures.values()),
        races=result_races,
    )
    validate_results_inventory(results, inventory)
    validate_results_evidence(results, repository_root=repository_root)
    return results


def _mapped_outcomes(
    binding: PreliminaryRaceBinding,
    contest: SourceContest,
    race: Race,
) -> list[PreliminaryOutcome]:
    choices, _ = _classified_choices(binding, contest)
    if (
        {item.source_choice_id for item in binding.choices} != set(choices)
        or len(binding.choices) != len(choices)
        or {item.choice_id for item in binding.choices} != {item.id for item in race.choices}
    ):
        raise ValueError(
            "mapping must include every source row and frozen named choice exactly once"
        )
    mapped: dict[str, PreliminaryOutcome] = {}
    for item in binding.choices:
        source = choices[item.source_choice_id]
        if (
            source.name != item.source_name
            or resolve_ballot_choice(source.name, race).id != item.choice_id
        ):
            raise ValueError("source choice ID/name no longer matches the frozen ballot choice")
        mapped[item.choice_id] = PreliminaryOutcome(choice_id=item.choice_id, votes=source.votes)
    return [
        mapped[item.id] for item in sorted(race.choices, key=lambda choice: choice.ballot_order)
    ]


def _classified_choices(
    binding: PreliminaryRaceBinding, contest: SourceContest
) -> tuple[dict[str, SourceChoice], list[SourceChoice]]:
    original = {item.id: item for item in contest.choices}
    overrides = {item.source_choice_id: item for item in binding.write_in_overrides}
    if len(overrides) != len(binding.write_in_overrides):
        raise ValueError("mapping repeats a Write-in classification")
    for key, item in overrides.items():
        source = original.get(key)
        if (
            source is None
            or source.name != item.source_name
            or source.is_write_in is not item.publisher_is_write_in
        ):
            raise ValueError("Write-in source identity/name/flag changed; review the mapping")
    write_ins = [
        item for item in contest.choices if item.is_write_in is True or item.id in overrides
    ]
    return (
        {item.id: item for item in contest.choices if item not in write_ins},
        write_ins,
    )


def _validate_coverage(
    binding: PreliminaryRaceBinding, feed: PreliminaryFeed, inventory: Inventory
) -> None:
    if feed.jurisdiction == "washington":
        if binding.coverage_basis not in {None, "state_aggregate"}:
            raise ValueError("State aggregate disagrees with coverage basis")
        return
    if feed.jurisdiction != "king-county-wa":
        raise ValueError("unsupported source jurisdiction for whole-contest coverage")
    if binding.coverage_basis not in {None, "county_containment"}:
        raise ValueError("County source disagrees with coverage basis")
    parents = {item.id: item.parent_id for item in inventory.jurisdictions}
    current: str | None = binding.jurisdiction_id
    seen: set[str] = set()
    while current is not None and current not in seen:
        if current == "king-county":
            return
        seen.add(current)
        current = parents.get(current)
    raise ValueError("County source does not prove the whole contest jurisdiction")
