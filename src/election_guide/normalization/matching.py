"""Deterministic race-scoped matching that queues ambiguity instead of guessing."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from difflib import SequenceMatcher
from fractions import Fraction
from typing import Literal

from election_guide.evidence.models import CaptureManifest, UnavailableManifest
from election_guide.inventory.models import BallotChoice, Inventory, Race
from election_guide.normalization.models import (
    UNAVAILABLE_EVIDENCE_LOCATOR,
    ExtractedClaim,
    MatchCandidate,
    MatchResult,
    NormalizedEndorsement,
    ReviewItem,
    equal_allocation,
)
from election_guide.normalization.records import new_normalized_endorsement, new_review_item
from election_guide.normalization.semantics import (
    EndorsementStatus,
    classify_endorsement_status,
)
from election_guide.normalization.text import normalize_match_text
from election_guide.sources.models import SourceRegistry

DEFAULT_CANDIDATE_THRESHOLD = Fraction(86, 100)
DEFAULT_RACE_THRESHOLD = Fraction(82, 100)
DEFAULT_AMBIGUITY_MARGIN = Fraction(3, 100)


@dataclass(frozen=True)
class ClaimMatchOutcome:
    race_match: MatchResult
    candidate_match: MatchResult | None
    status: EndorsementStatus | None
    review_item: ReviewItem | None


@dataclass(frozen=True)
class NormalizationOutcome:
    match: ClaimMatchOutcome
    endorsement: NormalizedEndorsement | None


def match_race(
    raw_race_text: str,
    inventory: Inventory,
    *,
    eligible_race_ids: set[str] | None = None,
    threshold: Fraction = DEFAULT_RACE_THRESHOLD,
    ambiguity_margin: Fraction = DEFAULT_AMBIGUITY_MARGIN,
) -> MatchResult:
    """Match a race against authoritative aliases without silent tie-breaking."""
    terms = {
        race.id: (race, _race_terms(race))
        for race in inventory.races
        if race.publication_eligible and (eligible_race_ids is None or race.id in eligible_race_ids)
    }
    return _match_terms(raw_race_text, terms, threshold, ambiguity_margin)


def match_candidate(
    raw_candidate_text: str,
    race_id: str,
    inventory: Inventory,
    *,
    threshold: Fraction = DEFAULT_CANDIDATE_THRESHOLD,
    ambiguity_margin: Fraction = DEFAULT_AMBIGUITY_MARGIN,
) -> MatchResult:
    """Match only choices belonging to the selected race."""
    race = next(
        (candidate_race for candidate_race in inventory.races if candidate_race.id == race_id), None
    )
    if race is None:
        raise ValueError(f"unknown race {race_id!r}")
    terms = {choice.id: (choice, _choice_terms(choice)) for choice in race.choices}
    return _match_terms(raw_candidate_text, terms, threshold, ambiguity_margin)


def match_claim(
    claim: ExtractedClaim,
    inventory: Inventory,
    *,
    created_at: datetime,
    source_registry: SourceRegistry,
) -> ClaimMatchOutcome:
    """Match a claim or produce a high-severity review item for uncertainty."""
    eligible_ids = eligible_race_ids(claim.source_id, inventory, source_registry)
    race_match = match_race(claim.raw_race_text, inventory, eligible_race_ids=eligible_ids)
    if race_match.status != "matched":
        reason = "race_ambiguous" if race_match.status == "ambiguous" else "race_unmatched"
        review = _review_item(claim, created_at, reason, race_match=race_match)
        return ClaimMatchOutcome(race_match, None, None, review)

    status = classify_endorsement_status(claim.raw_status_text)
    if claim.requires_review:
        review = _review_item(
            claim,
            created_at,
            "extraction_requires_review",
            race_match=race_match,
        )
        return ClaimMatchOutcome(race_match, None, status, review)
    if status is None or status in {"ambiguous", "unverified"}:
        review = _review_item(
            claim,
            created_at,
            "semantics_ambiguous",
            race_match=race_match,
        )
        return ClaimMatchOutcome(race_match, None, status, review)

    if status in {"dual_endorsement", "multiple_endorsement"}:
        review = _review_item(
            claim,
            created_at,
            "semantics_ambiguous",
            race_match=race_match,
        )
        return ClaimMatchOutcome(race_match, None, status, review)

    if status != "endorsed":
        if claim.raw_candidate_text is not None:
            review = _review_item(
                claim,
                created_at,
                "semantics_ambiguous",
                race_match=race_match,
            )
            return ClaimMatchOutcome(race_match, None, status, review)
        return ClaimMatchOutcome(race_match, None, status, None)

    if claim.raw_candidate_text is None:
        candidate_match = MatchResult(status="unmatched")
    else:
        candidate_match = match_candidate(
            claim.raw_candidate_text,
            race_match.selected_id or "",
            inventory,
        )
    if candidate_match.status != "matched":
        reason = (
            "candidate_ambiguous"
            if candidate_match.status == "ambiguous"
            else "candidate_unmatched"
        )
        review = _review_item(
            claim,
            created_at,
            reason,
            race_match=race_match,
            candidate_match=candidate_match,
        )
        return ClaimMatchOutcome(race_match, candidate_match, status, review)
    return ClaimMatchOutcome(race_match, candidate_match, status, None)


def normalize_claim(
    claim: ExtractedClaim,
    inventory: Inventory,
    capture: CaptureManifest,
    *,
    created_at: datetime,
    source_registry: SourceRegistry,
) -> NormalizationOutcome:
    """Emit one safe normalized decision, or only a review item when uncertain."""
    if capture.id != claim.capture_id or capture.source_id != claim.source_id:
        raise ValueError("claim and capture provenance do not match")
    if created_at < capture.retrieved_at:
        raise ValueError("normalization review timestamp cannot predate capture retrieval")
    if isinstance(capture, UnavailableManifest) and (
        normalize_match_text(claim.raw_status_text) != "source unavailable"
        or claim.raw_candidate_text is not None
        or claim.raw_notes is not None
        or claim.evidence_excerpt != capture.unavailable_reason
        or claim.evidence_locator != UNAVAILABLE_EVIDENCE_LOCATOR
    ):
        raise ValueError("unavailable evidence claim contains uncaptured content")
    outcome = match_claim(
        claim,
        inventory,
        created_at=created_at,
        source_registry=source_registry,
    )
    if outcome.review_item is not None or outcome.status is None:
        return NormalizationOutcome(outcome, None)
    race_id = outcome.race_match.selected_id
    if race_id is None:
        raise ValueError("resolved normalization is missing a race")
    candidate_ids: list[str] = []
    confidences = [claim.extraction_confidence, _selected_score(outcome.race_match)]
    if outcome.status == "endorsed":
        candidate_id = (
            None if outcome.candidate_match is None else outcome.candidate_match.selected_id
        )
        if candidate_id is None or outcome.candidate_match is None:
            raise ValueError("resolved endorsement is missing a candidate")
        candidate_ids = [candidate_id]
        confidences.append(_selected_score(outcome.candidate_match))
    endorsement = new_normalized_endorsement(
        election_id=inventory.election.id,
        race_id=race_id,
        source_id=claim.source_id,
        status=outcome.status,
        candidate_ids=candidate_ids,
        allocation=equal_allocation(candidate_ids) if candidate_ids else {},
        published_at=capture.published_at,
        source_capture_id=capture.id,
        extracted_claim_id=claim.id,
        normalization_confidence=min(confidences),
        manually_verified=False,
        notes=None,
    )
    return NormalizationOutcome(outcome, endorsement)


def eligible_race_ids(
    source_id: str,
    inventory: Inventory,
    source_registry: SourceRegistry,
) -> set[str]:
    """Return publication races permitted by the frozen source scope."""
    source = next((item for item in source_registry.sources if item.id == source_id), None)
    if source is None:
        raise ValueError(f"unknown source {source_id!r}")
    if source.eligibility.kind == "none":
        return set()
    if source.eligibility.kind == "all_seattle_ballot_races":
        return {race.id for race in inventory.races if race.publication_eligible}
    jurisdictions = set(source.eligibility.jurisdiction_ids)
    return {
        race.id
        for race in inventory.races
        if race.publication_eligible and race.jurisdiction_id in jurisdictions
    }


def _match_terms(
    raw_text: str,
    records: Mapping[str, tuple[Race | BallotChoice, tuple[str, ...]]],
    threshold: Fraction,
    ambiguity_margin: Fraction,
) -> MatchResult:
    stripped = raw_text.strip().casefold()
    normalized = normalize_match_text(raw_text)
    exact = [
        record_id
        for record_id, (_, terms) in records.items()
        if any(stripped == term.strip().casefold() for term in terms)
    ]
    if exact:
        return _exact_result(exact, records, "exact")

    normalized_matches = [
        record_id
        for record_id, (_, terms) in records.items()
        if any(normalized == normalize_match_text(term) for term in terms)
    ]
    if normalized_matches:
        return _exact_result(normalized_matches, records, "normalized")

    scored = sorted(
        (
            MatchCandidate(
                record_id=record_id,
                label=_record_label(record),
                score=max(_similarity(normalized, normalize_match_text(term)) for term in terms),
                match_kind="fuzzy",
            )
            for record_id, (record, terms) in records.items()
        ),
        key=lambda candidate: (-candidate.score, candidate.record_id),
    )
    plausible = [candidate for candidate in scored if candidate.score >= threshold]
    if not plausible:
        return MatchResult(status="unmatched", candidates=scored[:3])
    if len(plausible) > 1 and plausible[0].score - plausible[1].score <= ambiguity_margin:
        return MatchResult(status="ambiguous", candidates=plausible)
    return MatchResult(
        status="matched",
        selected_id=plausible[0].record_id,
        candidates=plausible,
    )


def _exact_result(
    record_ids: list[str],
    records: Mapping[str, tuple[Race | BallotChoice, tuple[str, ...]]],
    kind: Literal["exact", "normalized"],
) -> MatchResult:
    candidates = [
        MatchCandidate(
            record_id=record_id,
            label=_record_label(records[record_id][0]),
            score=Fraction(1),
            match_kind=kind,
        )
        for record_id in sorted(record_ids)
    ]
    if len(candidates) > 1:
        return MatchResult(status="ambiguous", candidates=candidates)
    return MatchResult(status="matched", selected_id=candidates[0].record_id, candidates=candidates)


def _race_terms(race: Race) -> tuple[str, ...]:
    office_position = " ".join(value for value in (race.office, race.position) if value)
    return tuple({race.display_name, race.office, office_position, *race.aliases})


def _choice_terms(choice: BallotChoice) -> tuple[str, ...]:
    return tuple({choice.official_name, choice.display_name, *choice.aliases})


def _record_label(record: Race | BallotChoice) -> str:
    return record.display_name


def _similarity(left: str, right: str) -> Fraction:
    return Fraction(SequenceMatcher(None, left, right, autojunk=False).ratio()).limit_denominator(
        1_000_000
    )


def _selected_score(result: MatchResult) -> Fraction:
    return next(
        candidate.score
        for candidate in result.candidates
        if candidate.record_id == result.selected_id
    )


def _review_item(
    claim: ExtractedClaim,
    created_at: datetime,
    reason: str,
    *,
    race_match: MatchResult,
    candidate_match: MatchResult | None = None,
) -> ReviewItem:
    return new_review_item(
        claim_id=claim.id,
        severity="high",
        reason=reason,
        summary=f"{reason.replace('_', ' ')} for extracted claim {claim.id}",
        race_match=race_match,
        candidate_match=candidate_match,
        capture_id=claim.capture_id,
        raw_race_text=claim.raw_race_text,
        raw_candidate_text=claim.raw_candidate_text,
        raw_status_text=claim.raw_status_text,
        evidence_excerpt=claim.evidence_excerpt,
        evidence_locator=claim.evidence_locator,
        created_at=created_at,
    )
