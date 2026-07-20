"""Typed canonical claims, endorsements, review records, and overrides."""

from __future__ import annotations

import hashlib
import math
from collections.abc import Mapping
from datetime import date
from fractions import Fraction
from typing import Any, Literal, cast

from pydantic import (
    AwareDatetime,
    BaseModel,
    ConfigDict,
    Field,
    JsonValue,
    ValidationInfo,
    field_validator,
    model_validator,
)

from election_guide.evidence.models import CaptureManifest, UnavailableManifest
from election_guide.inventory.models import Inventory
from election_guide.normalization.semantics import (
    EXPLICIT_STATUSES,
    REVIEW_REQUIRED_STATUSES,
    EndorsementStatus,
    classify_endorsement_status,
)
from election_guide.normalization.text import normalize_match_text
from election_guide.serialization import canonical_json_bytes
from election_guide.sources.models import SourceRegistry

ID_PATTERN = r"^[a-z0-9]+(?:-[a-z0-9]+)*$"
RECORD_ID_PATTERN = r"^[a-z]+-[0-9a-f]{16}$"
Confidence = Fraction
UNAVAILABLE_EVIDENCE_LOCATOR = "Unavailable capture metadata"


class CanonicalModel(BaseModel):
    """Reject schema drift and serialize exact fractions as strings."""

    model_config = ConfigDict(extra="forbid")


class ExtractedClaim(CanonicalModel):
    id: str = Field(pattern=RECORD_ID_PATTERN)
    capture_id: str
    source_id: str = Field(pattern=ID_PATTERN)
    raw_race_text: str = Field(min_length=1, max_length=1_000)
    raw_candidate_text: str | None = Field(default=None, max_length=1_000)
    raw_status_text: str = Field(min_length=1, max_length=500)
    raw_notes: str | None = Field(default=None, max_length=4_000)
    evidence_excerpt: str = Field(min_length=1, max_length=4_000)
    evidence_locator: str = Field(min_length=1, max_length=1_000)
    extractor: str = Field(min_length=1, max_length=200)
    extractor_version: str = Field(min_length=1, max_length=100)
    extraction_confidence: Confidence
    requires_review: bool

    @field_validator("extraction_confidence", mode="before")
    @classmethod
    def reject_inexact_confidence(cls, value: object) -> object:
        return _reject_inexact_number(value, "extraction confidence")

    @field_validator("extraction_confidence")
    @classmethod
    def validate_confidence(cls, value: Fraction) -> Fraction:
        return _bounded_fraction(value, "extraction confidence")

    @model_validator(mode="after")
    def validate_identity(self, info: ValidationInfo) -> ExtractedClaim:
        return _validated_identity(self, "claim", info)


class MatchCandidate(CanonicalModel):
    record_id: str
    label: str = Field(min_length=1)
    score: Confidence
    match_kind: Literal["exact", "normalized", "fuzzy"]

    @field_validator("score", mode="before")
    @classmethod
    def reject_inexact_score(cls, value: object) -> object:
        return _reject_inexact_number(value, "match score")

    @field_validator("score")
    @classmethod
    def validate_score(cls, value: Fraction) -> Fraction:
        return _bounded_fraction(value, "match score")


class MatchResult(CanonicalModel):
    status: Literal["matched", "ambiguous", "unmatched"]
    selected_id: str | None = None
    candidates: list[MatchCandidate] = Field(default_factory=lambda: list[MatchCandidate]())

    @model_validator(mode="after")
    def validate_selection(self) -> MatchResult:
        ids = [candidate.record_id for candidate in self.candidates]
        if len(ids) != len(set(ids)):
            raise ValueError("match result repeats a candidate")
        if self.status == "matched":
            if self.selected_id is None or self.selected_id not in ids:
                raise ValueError("matched result requires a selected candidate")
        elif self.selected_id is not None:
            raise ValueError(f"{self.status} result cannot select a candidate")
        return self


class ReviewItem(CanonicalModel):
    id: str = Field(pattern=RECORD_ID_PATTERN)
    claim_id: str = Field(pattern=RECORD_ID_PATTERN)
    severity: Literal["high", "medium", "low"]
    reason: Literal[
        "race_unmatched",
        "race_ambiguous",
        "candidate_unmatched",
        "candidate_ambiguous",
        "extraction_requires_review",
        "semantics_ambiguous",
    ]
    summary: str = Field(min_length=1, max_length=1_000)
    race_match: MatchResult | None = None
    candidate_match: MatchResult | None = None
    capture_id: str
    raw_race_text: str = Field(min_length=1, max_length=1_000)
    raw_candidate_text: str | None = Field(default=None, max_length=1_000)
    raw_status_text: str = Field(min_length=1, max_length=500)
    evidence_excerpt: str = Field(min_length=1, max_length=4_000)
    evidence_locator: str = Field(min_length=1, max_length=1_000)
    created_at: AwareDatetime

    @model_validator(mode="after")
    def validate_match_reason(self) -> ReviewItem:
        expected_status = {
            "race_unmatched": "unmatched",
            "race_ambiguous": "ambiguous",
            "candidate_unmatched": "unmatched",
            "candidate_ambiguous": "ambiguous",
        }.get(self.reason)
        if self.reason.startswith("race_"):
            if self.race_match is None or self.race_match.status != expected_status:
                raise ValueError(f"{self.reason} requires a matching race result")
            if self.candidate_match is not None:
                raise ValueError(f"{self.reason} cannot carry a candidate result")
        elif self.reason.startswith("candidate_"):
            if self.race_match is None or self.race_match.status != "matched":
                raise ValueError(f"{self.reason} requires a matched race")
            if self.candidate_match is None or self.candidate_match.status != expected_status:
                raise ValueError(f"{self.reason} requires a matching candidate result")
        elif self.race_match is None or self.race_match.status != "matched":
            raise ValueError("semantics ambiguity requires a matched race")
        return self

    @model_validator(mode="after")
    def validate_identity(self, info: ValidationInfo) -> ReviewItem:
        return _validated_identity(self, "review", info)


class ReviewResolution(CanonicalModel):
    race_id: str = Field(pattern=ID_PATTERN)
    status: EndorsementStatus
    candidate_ids: list[str] = Field(default_factory=list)
    allocation: dict[str, Fraction] = Field(default_factory=dict)

    @field_validator("allocation", mode="before")
    @classmethod
    def reject_inexact_allocations(cls, value: object) -> object:
        return _reject_allocation_numbers(value)

    @model_validator(mode="after")
    def validate_semantics(self) -> ReviewResolution:
        _validate_endorsement_values(self.status, self.candidate_ids, self.allocation)
        if self.status in REVIEW_REQUIRED_STATUSES:
            raise ValueError("an approved review resolution must use a resolved status")
        return self


class ReviewDecision(CanonicalModel):
    id: str = Field(pattern=RECORD_ID_PATTERN)
    review_item_id: str = Field(pattern=RECORD_ID_PATTERN)
    action: Literal["approve", "reject"]
    author: str = Field(min_length=1, max_length=200)
    reason: str = Field(min_length=1, max_length=4_000)
    evidence: str = Field(min_length=1, max_length=1_000)
    created_at: AwareDatetime
    resolution: ReviewResolution | None = None

    @field_validator("author", "reason", "evidence")
    @classmethod
    def validate_audit_text(cls, value: str) -> str:
        return _stripped_nonblank(value, "review audit field")

    @model_validator(mode="after")
    def validate_action(self) -> ReviewDecision:
        if self.action == "approve" and self.resolution is None:
            raise ValueError("review approval requires a structured resolution")
        if self.action == "reject" and self.resolution is not None:
            raise ValueError("review rejection cannot carry a resolution")
        return self

    @model_validator(mode="after")
    def validate_identity(self, info: ValidationInfo) -> ReviewDecision:
        return _validated_identity(self, "decision", info)


class OverrideRecord(CanonicalModel):
    id: str = Field(pattern=RECORD_ID_PATTERN)
    target_record_id: str
    field: str = Field(min_length=1, max_length=200)
    old_value: JsonValue
    new_value: JsonValue
    reason: str = Field(min_length=1, max_length=4_000)
    evidence: str = Field(min_length=1, max_length=1_000)
    author: str = Field(min_length=1, max_length=200)
    created_at: AwareDatetime

    @field_validator("target_record_id", "field", "reason", "evidence", "author")
    @classmethod
    def validate_audit_text(cls, value: str) -> str:
        return _stripped_nonblank(value, "override audit field")

    @field_validator("old_value", "new_value", mode="before")
    @classmethod
    def reject_nonfinite_json(cls, value: object) -> object:
        if _contains_nonfinite(value):
            raise ValueError("override values must contain only finite JSON numbers")
        return value

    @model_validator(mode="after")
    def validate_change(self) -> OverrideRecord:
        if self.old_value == self.new_value:
            raise ValueError("override old and new values must differ")
        return self

    @model_validator(mode="after")
    def validate_identity(self, info: ValidationInfo) -> OverrideRecord:
        return _validated_identity(self, "override", info)


class NormalizedEndorsement(CanonicalModel):
    id: str = Field(pattern=RECORD_ID_PATTERN)
    election_id: str = Field(pattern=ID_PATTERN)
    race_id: str = Field(pattern=ID_PATTERN)
    source_id: str = Field(pattern=ID_PATTERN)
    status: EndorsementStatus
    candidate_ids: list[str] = Field(default_factory=list)
    allocation: dict[str, Fraction] = Field(default_factory=dict)
    published_at: date | None = None
    source_capture_id: str
    extracted_claim_id: str = Field(pattern=RECORD_ID_PATTERN)
    normalization_confidence: Confidence
    manually_verified: bool = False
    reviewer: str | None = Field(default=None, max_length=200)
    reviewed_at: AwareDatetime | None = None
    review_item_id: str | None = Field(default=None, pattern=RECORD_ID_PATTERN)
    notes: str | None = Field(default=None, max_length=4_000)

    @field_validator("normalization_confidence", mode="before")
    @classmethod
    def reject_inexact_confidence(cls, value: object) -> object:
        return _reject_inexact_number(value, "normalization confidence")

    @field_validator("normalization_confidence")
    @classmethod
    def validate_confidence(cls, value: Fraction) -> Fraction:
        return _bounded_fraction(value, "normalization confidence")

    @field_validator("allocation", mode="before")
    @classmethod
    def reject_inexact_allocations(cls, value: object) -> object:
        return _reject_allocation_numbers(value)

    @model_validator(mode="after")
    def validate_semantics(self) -> NormalizedEndorsement:
        _validate_endorsement_values(self.status, self.candidate_ids, self.allocation)

        if self.status in REVIEW_REQUIRED_STATUSES:
            if self.review_item_id is None:
                raise ValueError(f"{self.status} requires a review item")
        elif self.review_item_id is not None and not self.manually_verified:
            raise ValueError("an automated resolved status cannot retain a review item")

        review_fields = (self.reviewer, self.reviewed_at)
        if self.manually_verified and any(value is None for value in review_fields):
            raise ValueError("manual verification requires reviewer and timestamp")
        if not self.manually_verified and any(value is not None for value in review_fields):
            raise ValueError("unverified normalization cannot carry reviewer metadata")
        return self

    @model_validator(mode="after")
    def validate_identity(self, info: ValidationInfo) -> NormalizedEndorsement:
        return _validated_identity(self, "endorsement", info)


class CanonicalDataset(CanonicalModel):
    schema_version: Literal["1.0"] = "1.0"
    inventory: Inventory
    source_registry: SourceRegistry
    captures: list[CaptureManifest]
    claims: list[ExtractedClaim]
    endorsements: list[NormalizedEndorsement]
    review_items: list[ReviewItem] = Field(default_factory=lambda: list[ReviewItem]())
    review_decisions: list[ReviewDecision] = Field(default_factory=lambda: list[ReviewDecision]())
    overrides: list[OverrideRecord] = Field(default_factory=lambda: list[OverrideRecord]())

    def effective_records(self) -> dict[str, BaseModel]:
        """Return normalization records after applying the validated override chain."""
        targets: dict[str, BaseModel] = {
            record.id: record
            for record in (
                *self.claims,
                *self.endorsements,
                *self.review_items,
                *self.review_decisions,
            )
        }
        return _validate_override_chain(self.overrides, targets)

    @model_validator(mode="after")
    def validate_references(self) -> CanonicalDataset:
        if self.source_registry.election_id != self.inventory.election.id:
            raise ValueError("source registry and inventory target different elections")
        race_by_id = {race.id: race for race in self.inventory.races}
        source_by_id = {source.id: source for source in self.source_registry.sources}
        capture_by_id = _unique_records(self.captures, "capture")
        base_claim_by_id = _unique_records(self.claims, "claim")
        base_review_by_id = _unique_records(self.review_items, "review item")
        base_decision_by_id = _unique_records(self.review_decisions, "review decision")
        _unique_records(self.overrides, "override")
        base_endorsement_by_id = _unique_records(self.endorsements, "endorsement")

        override_targets: dict[str, BaseModel] = {
            **base_claim_by_id,
            **base_endorsement_by_id,
            **base_review_by_id,
            **base_decision_by_id,
        }
        for override in self.overrides:
            target = override_targets.get(override.target_record_id)
            if target is None:
                continue
            lower_bound = None
            if isinstance(target, ExtractedClaim):
                capture = capture_by_id.get(target.capture_id)
                lower_bound = None if capture is None else capture.retrieved_at
            elif isinstance(target, NormalizedEndorsement):
                capture = capture_by_id.get(target.source_capture_id)
                lower_bound = None if capture is None else capture.retrieved_at
            elif isinstance(target, (ReviewItem, ReviewDecision)):
                lower_bound = target.created_at
            if lower_bound is not None and override.created_at < lower_bound:
                raise ValueError(f"override {override.id!r} predates its canonical target")
        effective = _validate_override_chain(self.overrides, override_targets)
        claim_by_id = {
            record_id: cast(ExtractedClaim, effective[record_id]) for record_id in base_claim_by_id
        }
        endorsement_by_id = {
            record_id: cast(NormalizedEndorsement, effective[record_id])
            for record_id in base_endorsement_by_id
        }
        review_by_id = {
            record_id: cast(ReviewItem, effective[record_id]) for record_id in base_review_by_id
        }
        decision_by_id = {
            record_id: cast(ReviewDecision, effective[record_id])
            for record_id in base_decision_by_id
        }

        if len(race_by_id) != len(self.inventory.races):
            raise ValueError("canonical inventory repeats a race")
        if len(source_by_id) != len(self.source_registry.sources):
            raise ValueError("source registry repeats a source")

        decision_for_review: dict[str, ReviewDecision] = {}
        for decision in decision_by_id.values():
            if decision.review_item_id in decision_for_review:
                raise ValueError(f"review item {decision.review_item_id!r} has multiple decisions")
            decision_for_review[decision.review_item_id] = decision

        for race in self.inventory.races:
            aliases: dict[str, str] = {}
            for choice in race.choices:
                for alias in (choice.official_name, choice.display_name, *choice.aliases):
                    normalized = _normalized_alias(alias)
                    if not normalized:
                        raise ValueError(
                            f"race {race.id!r} candidate alias {alias!r} has no matchable text"
                        )
                    owner = aliases.get(normalized)
                    if owner is not None and owner != choice.id:
                        raise ValueError(
                            f"race {race.id!r} candidate alias {alias!r} collides between "
                            f"{owner!r} and {choice.id!r}"
                        )
                    aliases[normalized] = choice.id

        for claim in claim_by_id.values():
            capture = capture_by_id.get(claim.capture_id)
            if capture is None:
                raise ValueError(f"claim {claim.id!r} references unknown capture")
            if isinstance(capture, UnavailableManifest) and (
                normalize_match_text(claim.raw_status_text) != "source unavailable"
                or claim.raw_candidate_text is not None
                or claim.raw_notes is not None
                or claim.evidence_excerpt != capture.unavailable_reason
                or claim.evidence_locator != UNAVAILABLE_EVIDENCE_LOCATOR
            ):
                raise ValueError(
                    f"claim {claim.id!r} may use unavailable metadata only for an explicit "
                    "source-unavailable state"
                )
            if capture.source_id != claim.source_id:
                raise ValueError(f"claim {claim.id!r} source does not match its capture")
            if claim.source_id not in source_by_id:
                raise ValueError(f"claim {claim.id!r} references unknown source")

        decisions: set[str] = set()
        source_races: set[tuple[str, str]] = set()
        for endorsement in endorsement_by_id.values():
            if endorsement.election_id != self.inventory.election.id:
                raise ValueError(f"endorsement {endorsement.id!r} targets another election")
            race = race_by_id.get(endorsement.race_id)
            if race is None:
                raise ValueError(f"endorsement {endorsement.id!r} references unknown race")
            source = source_by_id.get(endorsement.source_id)
            if source is None:
                raise ValueError(f"endorsement {endorsement.id!r} references unknown source")
            if source.eligibility.kind == "none" or (
                source.eligibility.kind == "jurisdictions_only"
                and race.jurisdiction_id not in source.eligibility.jurisdiction_ids
            ):
                raise ValueError(
                    f"endorsement {endorsement.id!r} is outside its source eligibility"
                )
            claim = claim_by_id.get(endorsement.extracted_claim_id)
            if claim is None:
                raise ValueError(f"endorsement {endorsement.id!r} references unknown claim")
            capture = capture_by_id.get(endorsement.source_capture_id)
            if capture is None:
                raise ValueError(f"endorsement {endorsement.id!r} references unknown capture")
            if claim.source_id != endorsement.source_id or claim.capture_id != capture.id:
                raise ValueError(f"endorsement {endorsement.id!r} provenance is inconsistent")
            if isinstance(capture, UnavailableManifest):
                if endorsement.status != "source_unavailable":
                    raise ValueError(
                        f"endorsement {endorsement.id!r} must preserve unavailable provenance"
                    )
            elif endorsement.status == "source_unavailable":
                raise ValueError(f"endorsement {endorsement.id!r} requires an unavailable capture")
            if endorsement.published_at != capture.published_at:
                raise ValueError(
                    f"endorsement {endorsement.id!r} publication date does not match its capture"
                )
            if (
                endorsement.published_at is not None
                and endorsement.published_at > self.inventory.election.election_date
            ):
                raise ValueError(
                    f"endorsement {endorsement.id!r} publication date is after election"
                )
            if (
                endorsement.reviewed_at is not None
                and endorsement.reviewed_at < capture.retrieved_at
            ):
                raise ValueError(f"endorsement {endorsement.id!r} was reviewed before capture")
            choice_ids = {choice.id for choice in race.choices}
            unknown_choices = set(endorsement.candidate_ids) - choice_ids
            if unknown_choices:
                raise ValueError(
                    f"endorsement {endorsement.id!r} has candidates outside its race: "
                    f"{sorted(unknown_choices)}"
                )
            key = (endorsement.source_id, endorsement.race_id)
            if key in source_races:
                raise ValueError(f"duplicate source/race decision for {key!r}")
            source_races.add(key)
            if endorsement.review_item_id is not None:
                review = review_by_id.get(endorsement.review_item_id)
                if review is None:
                    raise ValueError(
                        f"endorsement {endorsement.id!r} references unknown review item"
                    )
                if review.claim_id != endorsement.extracted_claim_id:
                    raise ValueError(
                        f"endorsement {endorsement.id!r} review item belongs to another claim"
                    )
                race_match = review.race_match
                if race_match is None:
                    raise ValueError(
                        f"endorsement {endorsement.id!r} review item has no race provenance"
                    )
                related_race_ids = {candidate.record_id for candidate in race_match.candidates}
                if race_match.selected_id is not None:
                    related_race_ids.add(race_match.selected_id)
                linked_resolution = _approved_resolution(
                    endorsement.review_item_id,
                    decision_for_review,
                )
                if linked_resolution is not None:
                    related_race_ids.add(linked_resolution.race_id)
                if endorsement.race_id not in related_race_ids:
                    raise ValueError(
                        f"endorsement {endorsement.id!r} review item belongs to another race"
                    )
            approved_resolution = _approved_resolution(
                endorsement.review_item_id,
                decision_for_review,
            )
            linked_decision = (
                None
                if endorsement.review_item_id is None
                else decision_for_review.get(endorsement.review_item_id)
            )
            if linked_decision is not None and linked_decision.action == "reject":
                raise ValueError(
                    f"endorsement {endorsement.id!r} references a rejected review item"
                )
            if approved_resolution is not None and not _resolution_matches_endorsement(
                approved_resolution, endorsement
            ):
                raise ValueError(
                    f"endorsement {endorsement.id!r} does not match its approved resolution"
                )
            if endorsement.status not in REVIEW_REQUIRED_STATUSES:
                requires_resolution = claim.requires_review
                claim_status = classify_endorsement_status(claim.raw_status_text)
                if claim_status != endorsement.status:
                    requires_resolution = True
                if endorsement.status in {"dual_endorsement", "multiple_endorsement"}:
                    requires_resolution = True
                elif endorsement.status == "endorsed":
                    from election_guide.normalization.matching import match_candidate

                    candidate_match = (
                        None
                        if claim.raw_candidate_text is None
                        else match_candidate(
                            claim.raw_candidate_text, endorsement.race_id, self.inventory
                        )
                    )
                    if (
                        candidate_match is None
                        or candidate_match.status != "matched"
                        or candidate_match.selected_id != endorsement.candidate_ids[0]
                    ):
                        requires_resolution = True
                elif claim.raw_candidate_text is not None:
                    requires_resolution = True
                if requires_resolution and approved_resolution is None:
                    raise ValueError(
                        f"endorsement {endorsement.id!r} departs from its claim without an "
                        "approved review resolution"
                    )
                if endorsement.review_item_id is not None and approved_resolution is None:
                    raise ValueError(
                        f"endorsement {endorsement.id!r} has no approved review resolution"
                    )

        reviewed_claims: set[str] = set()
        for review in review_by_id.values():
            claim = claim_by_id.get(review.claim_id)
            if claim is None:
                raise ValueError(f"review item {review.id!r} references unknown claim")
            if review.claim_id in reviewed_claims:
                raise ValueError(f"claim {review.claim_id!r} has multiple review items")
            reviewed_claims.add(review.claim_id)
            if review.capture_id != claim.capture_id:
                raise ValueError(f"review item {review.id!r} capture does not match its claim")
            capture = capture_by_id[review.capture_id]
            if review.created_at < capture.retrieved_at:
                raise ValueError(f"review item {review.id!r} was created before capture")
            review_claim_fields = (
                review.raw_race_text,
                review.raw_candidate_text,
                review.raw_status_text,
                review.evidence_excerpt,
                review.evidence_locator,
            )
            claim_fields = (
                claim.raw_race_text,
                claim.raw_candidate_text,
                claim.raw_status_text,
                claim.evidence_excerpt,
                claim.evidence_locator,
            )
            if review_claim_fields != claim_fields:
                raise ValueError(f"review item {review.id!r} does not preserve its claim evidence")
            race_match = review.race_match
            if race_match is None:
                raise ValueError(f"review item {review.id!r} is missing its race match")
            known_races = set(race_by_id)
            unknown_races = {
                candidate.record_id for candidate in race_match.candidates
            } - known_races
            if unknown_races:
                raise ValueError(
                    f"review item {review.id!r} has unknown race matches: {sorted(unknown_races)}"
                )
            if review.candidate_match is not None:
                selected_race_id = race_match.selected_id
                if selected_race_id is None:
                    raise ValueError(
                        f"review item {review.id!r} cannot match candidates without a race"
                    )
                race = race_by_id[selected_race_id]
                race_choice_ids = {choice.id for choice in race.choices}
                outside_race = {
                    candidate.record_id for candidate in review.candidate_match.candidates
                } - race_choice_ids
                if outside_race:
                    raise ValueError(
                        f"review item {review.id!r} has candidate matches outside its race: "
                        f"{sorted(outside_race)}"
                    )
        for decision in decision_by_id.values():
            review = review_by_id.get(decision.review_item_id)
            if review is None:
                raise ValueError(f"review decision {decision.id!r} references unknown item")
            if decision.created_at < review.created_at:
                raise ValueError(f"review decision {decision.id!r} predates its review item")
            if decision.review_item_id in decisions:
                raise ValueError(f"review item {decision.review_item_id!r} has multiple decisions")
            decisions.add(decision.review_item_id)
            resolution = decision.resolution
            if resolution is not None:
                resolution_race = race_by_id.get(resolution.race_id)
                if resolution_race is None:
                    raise ValueError(f"review decision {decision.id!r} resolves to an unknown race")
                choice_ids = {choice.id for choice in resolution_race.choices}
                outside_race = set(resolution.candidate_ids) - choice_ids
                if outside_race:
                    raise ValueError(
                        f"review decision {decision.id!r} has candidates outside its race: "
                        f"{sorted(outside_race)}"
                    )
                claim = claim_by_id[review.claim_id]
                capture = capture_by_id[claim.capture_id]
                if isinstance(capture, UnavailableManifest):
                    if resolution.status != "source_unavailable":
                        raise ValueError(
                            f"review decision {decision.id!r} must preserve unavailable provenance"
                        )
                elif resolution.status == "source_unavailable":
                    raise ValueError(
                        f"review decision {decision.id!r} requires an unavailable capture"
                    )
                source = source_by_id[claim.source_id]
                if source.eligibility.kind == "none" or (
                    source.eligibility.kind == "jurisdictions_only"
                    and resolution_race.jurisdiction_id not in source.eligibility.jurisdiction_ids
                ):
                    raise ValueError(
                        f"review decision {decision.id!r} resolves outside source eligibility"
                    )
                race_match = review.race_match
                if (
                    race_match is not None
                    and race_match.status == "ambiguous"
                    and resolution.race_id
                    not in {candidate.record_id for candidate in race_match.candidates}
                ):
                    raise ValueError(
                        f"review decision {decision.id!r} selects a race outside the ambiguity"
                    )
                candidate_match = review.candidate_match
                if (
                    candidate_match is not None
                    and candidate_match.status == "ambiguous"
                    and not set(resolution.candidate_ids).issubset(
                        {candidate.record_id for candidate in candidate_match.candidates}
                    )
                ):
                    raise ValueError(
                        f"review decision {decision.id!r} selects a candidate outside the ambiguity"
                    )
        return self


def equal_allocation(candidate_ids: list[str]) -> dict[str, Fraction]:
    """Return an exact equal allocation for one or more distinct candidates."""
    if not candidate_ids:
        raise ValueError("cannot allocate an endorsement without candidates")
    if len(candidate_ids) != len(set(candidate_ids)):
        raise ValueError("cannot allocate duplicate candidates")
    share = Fraction(1, len(candidate_ids))
    return {candidate_id: share for candidate_id in candidate_ids}


def _unique_records(records: list[Any], label: str) -> dict[str, Any]:
    by_id = {record.id: record for record in records}
    if len(by_id) != len(records):
        raise ValueError(f"canonical dataset repeats a {label}")
    return by_id


def _normalized_alias(value: str) -> str:
    return normalize_match_text(value)


def _reject_inexact_number(value: object, label: str) -> object:
    if isinstance(value, (bool, float, complex)):
        raise ValueError(f"{label} must use an exact integer or fraction string")
    return value


def _reject_allocation_numbers(value: object) -> object:
    if isinstance(value, dict):
        allocations = cast(dict[object, object], value)
        for allocation in allocations.values():
            _reject_inexact_number(allocation, "allocation")
        return allocations
    return value


def _validate_endorsement_values(
    status: EndorsementStatus,
    candidate_ids: list[str],
    allocation: Mapping[str, Fraction],
) -> None:
    if len(candidate_ids) != len(set(candidate_ids)):
        raise ValueError("normalized endorsement repeats a candidate")
    if set(candidate_ids) != set(allocation):
        raise ValueError("candidate IDs must exactly match allocation keys")
    if status in EXPLICIT_STATUSES:
        if any(value <= 0 for value in allocation.values()):
            raise ValueError("explicit endorsement allocations must be positive")
        if sum(allocation.values(), start=Fraction(0)) != Fraction(1):
            raise ValueError("explicit endorsement allocations must total exactly one")
        valid_count = {
            "endorsed": len(candidate_ids) == 1,
            "dual_endorsement": len(candidate_ids) == 2,
            "multiple_endorsement": len(candidate_ids) >= 3,
        }[status]
        if not valid_count:
            raise ValueError(f"{status} has an invalid candidate count")
    elif candidate_ids or allocation:
        raise ValueError(f"{status} cannot carry candidates or allocations")


def _bounded_fraction(value: Fraction, label: str) -> Fraction:
    if not Fraction(0) <= value <= Fraction(1):
        raise ValueError(f"{label} must be between zero and one")
    return value


def _stripped_nonblank(value: str, label: str) -> str:
    stripped = value.strip()
    if not stripped:
        raise ValueError(f"{label} must not be blank")
    return stripped


def _contains_nonfinite(value: object) -> bool:
    if isinstance(value, float):
        return not math.isfinite(value)
    if isinstance(value, dict):
        mapping = cast(dict[object, object], value)
        return any(_contains_nonfinite(item) for item in mapping.values())
    if isinstance(value, (list, tuple)):
        sequence = cast(list[object] | tuple[object, ...], value)
        return any(_contains_nonfinite(item) for item in sequence)
    return False


def _validate_override_chain(
    overrides: list[OverrideRecord],
    target_records: Mapping[str, BaseModel],
) -> dict[str, BaseModel]:
    values = {
        record_id: record.model_dump(mode="json") for record_id, record in target_records.items()
    }
    record_types = {record_id: type(record) for record_id, record in target_records.items()}
    for override in sorted(overrides, key=lambda item: (item.created_at, item.id)):
        target = values.get(override.target_record_id)
        if target is None:
            raise ValueError(f"override {override.id!r} references unknown target")
        if override.field == "id":
            raise ValueError(f"override {override.id!r} cannot change record identity")
        if override.field not in target:
            raise ValueError(f"override {override.id!r} references unknown field")
        if target[override.field] != override.old_value:
            raise ValueError(f"override {override.id!r} old value does not match its target")
        target[override.field] = override.new_value
    return {
        record_id: record_types[record_id].model_validate(
            value, context={"skip_record_identity": True}
        )
        for record_id, value in values.items()
    }


def _approved_resolution(
    review_item_id: str | None,
    decisions: Mapping[str, ReviewDecision],
) -> ReviewResolution | None:
    if review_item_id is None:
        return None
    decision = decisions.get(review_item_id)
    if decision is None or decision.action != "approve":
        return None
    return decision.resolution


def _resolution_matches_endorsement(
    resolution: ReviewResolution,
    endorsement: NormalizedEndorsement,
) -> bool:
    return (
        resolution.race_id == endorsement.race_id
        and resolution.status == endorsement.status
        and resolution.candidate_ids == endorsement.candidate_ids
        and resolution.allocation == endorsement.allocation
    )


IdentityRecord = (
    ExtractedClaim | ReviewItem | ReviewDecision | OverrideRecord | NormalizedEndorsement
)


def _validated_identity[RecordType: IdentityRecord](
    record: RecordType,
    prefix: str,
    info: ValidationInfo,
) -> RecordType:
    context = cast(Mapping[str, object] | None, info.context)
    if context is not None and context.get("skip_record_identity") is True:
        return record
    payload = record.model_dump(mode="json", exclude={"id"})
    digest = hashlib.sha256(canonical_json_bytes(payload)).hexdigest()
    expected = f"{prefix}-{digest[:16]}"
    if record.id != expected:
        raise ValueError(f"{prefix} record ID must equal its canonical content hash")
    return record
