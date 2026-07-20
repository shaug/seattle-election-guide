"""Strict records for configured extraction and incremental refreshes."""

from __future__ import annotations

import re
from datetime import UTC
from typing import Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator

from election_guide.evidence.models import CAPTURE_ID_PATTERN, SHA256_PATTERN, SOURCE_ID_PATTERN
from election_guide.normalization.semantics import EndorsementStatus

EXTRACTION_ID_PATTERN = r"^extraction-[a-z0-9-]+-[0-9]{8}T[0-9]{6}Z-[0-9a-f]{12}$"
REFRESH_ID_PATTERN = r"^refresh-[a-z0-9-]+-[0-9]{8}T[0-9]{6}Z-[0-9a-f]{12}$"
AdapterKind = Literal["static_html", "dynamic_html", "pdf", "image"]


class CollectionModel(BaseModel):
    """Reject undeclared collection fields."""

    model_config = ConfigDict(extra="forbid")


class DecisionRule(CollectionModel):
    """One explicit source-specific mapping from source wording to canonical IDs."""

    race_id: str = Field(pattern=SOURCE_ID_PATTERN)
    pattern: str = Field(min_length=1, max_length=2_000)
    status: EndorsementStatus = "endorsed"
    candidate_ids: list[str] = Field(default_factory=list)
    evidence_locator: str = Field(min_length=1, max_length=1_000)

    @model_validator(mode="after")
    def validate_decision(self) -> DecisionRule:
        explicit = self.status in {"endorsed", "dual_endorsement", "multiple_endorsement"}
        if explicit != bool(self.candidate_ids):
            raise ValueError("candidate IDs are required only for explicit endorsements")
        if len(self.candidate_ids) != len(set(self.candidate_ids)):
            raise ValueError("decision rule repeats a candidate ID")
        if self.status == "endorsed" and len(self.candidate_ids) != 1:
            raise ValueError("endorsed rules require exactly one candidate")
        if self.status == "dual_endorsement" and len(self.candidate_ids) != 2:
            raise ValueError("dual endorsements require exactly two candidates")
        if self.status == "multiple_endorsement" and len(self.candidate_ids) < 2:
            raise ValueError("multiple endorsements require at least two candidates")
        return self


class AdapterSpec(CollectionModel):
    """A complete, reviewed parser contract for one source."""

    schema_version: Literal["1.0"] = "1.0"
    source_id: str = Field(pattern=SOURCE_ID_PATTERN)
    adapter_kind: AdapterKind
    extractor_version: str = Field(pattern=r"^[0-9]+\.[0-9]+\.[0-9]+$")
    complete: Literal[True] = True
    decision_pattern: str = Field(min_length=1, max_length=2_000)
    rules: list[DecisionRule] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_rules(self) -> AdapterSpec:
        race_ids = [rule.race_id for rule in self.rules]
        if len(race_ids) != len(set(race_ids)):
            raise ValueError("adapter repeats a race rule")
        for label, pattern in (
            ("decision pattern", self.decision_pattern),
            *((f"rule {rule.race_id!r}", rule.pattern) for rule in self.rules),
        ):
            try:
                re.compile(pattern, flags=re.IGNORECASE | re.MULTILINE)
            except re.error as error:
                raise ValueError(f"adapter {label} has invalid regex: {error}") from error
        return self


class AdapterDecision(CollectionModel):
    race_id: str = Field(pattern=SOURCE_ID_PATTERN)
    status: EndorsementStatus
    candidate_ids: list[str]
    evidence_excerpt: str = Field(min_length=1, max_length=4_000)
    evidence_locator: str = Field(min_length=1, max_length=1_000)
    requires_review: bool = False
    extraction_confidence: str = Field(pattern=r"^(?:0|1|0\.[0-9]{1,6})$")

    @model_validator(mode="after")
    def validate_decision(self) -> AdapterDecision:
        explicit = self.status in {"endorsed", "dual_endorsement", "multiple_endorsement"}
        if explicit != bool(self.candidate_ids):
            raise ValueError("candidate IDs are required only for explicit endorsements")
        if len(self.candidate_ids) != len(set(self.candidate_ids)):
            raise ValueError("adapter decision repeats a candidate ID")
        if self.status == "endorsed" and len(self.candidate_ids) != 1:
            raise ValueError("endorsed decisions require exactly one candidate")
        if self.status == "dual_endorsement" and len(self.candidate_ids) != 2:
            raise ValueError("dual endorsements require exactly two candidates")
        if self.status == "multiple_endorsement" and len(self.candidate_ids) < 2:
            raise ValueError("multiple endorsements require at least two candidates")
        return self


class DecisionDiff(CollectionModel):
    kind: Literal["added", "changed", "removed"]
    race_id: str = Field(pattern=SOURCE_ID_PATTERN)
    before: AdapterDecision | None = None
    after: AdapterDecision | None = None

    @model_validator(mode="after")
    def validate_shape(self) -> DecisionDiff:
        expected = {
            "added": (False, True),
            "changed": (True, True),
            "removed": (True, False),
        }[self.kind]
        if (self.before is not None, self.after is not None) != expected:
            raise ValueError(f"{self.kind} diff has invalid before/after values")
        if self.before is not None and self.before.race_id != self.race_id:
            raise ValueError("before decision race does not match diff race")
        if self.after is not None and self.after.race_id != self.race_id:
            raise ValueError("after decision race does not match diff race")
        if (
            self.kind == "changed"
            and self.before is not None
            and self.after is not None
            and (
                self.before.status,
                sorted(self.before.candidate_ids),
            )
            == (
                self.after.status,
                sorted(self.after.candidate_ids),
            )
        ):
            raise ValueError("changed diff must alter decision semantics")
        return self


class ExtractionSnapshot(CollectionModel):
    schema_version: Literal["1.0"] = "1.0"
    id: str = Field(pattern=EXTRACTION_ID_PATTERN)
    source_id: str = Field(pattern=SOURCE_ID_PATTERN)
    capture_id: str = Field(pattern=CAPTURE_ID_PATTERN)
    content_sha256: str = Field(pattern=SHA256_PATTERN)
    adapter_kind: AdapterKind
    extractor_version: str
    adapter_fingerprint: str = Field(pattern=SHA256_PATTERN)
    extraction_fingerprint: str = Field(pattern=SHA256_PATTERN)
    extracted_at: AwareDatetime
    decisions: list[AdapterDecision] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_decisions(self) -> ExtractionSnapshot:
        timestamp = self.extracted_at.astimezone(UTC).strftime("%Y%m%dT%H%M%SZ")
        if not self.id.startswith(f"extraction-{self.source_id}-{timestamp}-"):
            raise ValueError("extraction ID must encode its source and UTC extraction time")
        race_ids = [decision.race_id for decision in self.decisions]
        if race_ids != sorted(race_ids):
            raise ValueError("snapshot decisions must use stable race order")
        if len(race_ids) != len(set(race_ids)):
            raise ValueError("snapshot repeats a race decision")
        return self


class RefreshEvent(CollectionModel):
    schema_version: Literal["1.0"] = "1.0"
    id: str = Field(pattern=REFRESH_ID_PATTERN)
    source_id: str = Field(pattern=SOURCE_ID_PATTERN)
    checked_at: AwareDatetime
    status: Literal["created", "updated", "unchanged", "failed"]
    content_changed: bool | None
    capture_id: str | None = Field(default=None, pattern=CAPTURE_ID_PATTERN)
    snapshot_id: str | None = Field(default=None, pattern=EXTRACTION_ID_PATTERN)
    previous_snapshot_id: str | None = Field(default=None, pattern=EXTRACTION_ID_PATTERN)
    diff: list[DecisionDiff] = Field(default_factory=list[DecisionDiff])
    error: str | None = Field(default=None, min_length=1, max_length=2_000)

    @model_validator(mode="after")
    def validate_status(self) -> RefreshEvent:
        timestamp = self.checked_at.astimezone(UTC).strftime("%Y%m%dT%H%M%SZ")
        if not self.id.startswith(f"refresh-{self.source_id}-{timestamp}-"):
            raise ValueError("refresh ID must encode its source and UTC check time")
        if self.status == "failed":
            if self.error is None or self.snapshot_id is not None or self.diff:
                raise ValueError("failed refresh must have only an error and prior state")
            return self
        if self.error is not None or self.capture_id is None or self.snapshot_id is None:
            raise ValueError("successful refresh requires capture and snapshot without an error")
        if self.content_changed is None:
            raise ValueError("successful refresh requires a content-change result")
        if self.status == "unchanged" and (self.content_changed or self.diff):
            raise ValueError("unchanged refresh cannot contain changes")
        if self.status == "unchanged" and self.snapshot_id != self.previous_snapshot_id:
            raise ValueError("unchanged refresh must retain the previous snapshot")
        if self.status == "created" and not self.content_changed:
            raise ValueError("created refresh must represent new content")
        if self.status == "created" and self.previous_snapshot_id is not None:
            raise ValueError("created refresh cannot reference prior state")
        if self.status == "updated" and self.previous_snapshot_id is None:
            raise ValueError("updated refresh requires prior state")
        if self.status == "updated" and self.snapshot_id == self.previous_snapshot_id:
            raise ValueError("updated refresh must create a new snapshot")
        return self
