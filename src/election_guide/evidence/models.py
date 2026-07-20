"""Validated evidence capture and manual-entry records."""

from __future__ import annotations

import hashlib
from datetime import UTC, date
from typing import Literal

from pydantic import (
    AwareDatetime,
    BaseModel,
    ConfigDict,
    Field,
    TypeAdapter,
    field_validator,
    model_validator,
)

from election_guide.serialization import canonical_json_bytes
from election_guide.validation import media_type_essence, validated_http_url, validated_media_type

SOURCE_ID_PATTERN = r"^[a-z0-9]+(?:-[a-z0-9]+)*$"
SHA256_PATTERN = r"^[0-9a-f]{64}$"
CAPTURE_ID_PATTERN = r"^capture-[a-z0-9-]+-[0-9]{8}T[0-9]{6}Z-[0-9a-f]{12}$"
MANUAL_ID_PATTERN = r"^manual-[a-z0-9-]+-[0-9]{8}T[0-9]{6}Z-[0-9a-f]{12}$"
MAX_PUBLIC_TRANSCRIPTION_CHARS = 4_000
MAX_PUBLIC_NOTE_CHARS = 4_000
MAX_PUBLIC_LOCATOR_CHARS = 1_000
MAX_PUBLIC_NAME_CHARS = 200
MAX_PUBLIC_TITLE_CHARS = 500


class EvidenceModel(BaseModel):
    """Reject undeclared fields in provenance records."""

    model_config = ConfigDict(extra="forbid")


class CaptureMetadata(EvidenceModel):
    schema_version: Literal["1.0"] = "1.0"
    source_id: str = Field(pattern=SOURCE_ID_PATTERN)
    requested_url: str
    canonical_url: str | None = None
    redirect_chain: list[str] = Field(default_factory=list)
    retrieved_at: AwareDatetime
    http_status: int | None = Field(default=None, ge=100, le=599)
    media_type: str | None = None
    title: str | None = Field(default=None, max_length=MAX_PUBLIC_TITLE_CHARS)
    published_at: date | None = None
    updated_at: date | None = None
    browser_required: bool = False
    redistribution: Literal["permitted", "restricted"]
    redistribution_note: str = Field(min_length=1, max_length=MAX_PUBLIC_NOTE_CHARS)

    @field_validator("requested_url", "canonical_url")
    @classmethod
    def validate_url(cls, value: str | None) -> str | None:
        return None if value is None else validated_http_url(value)

    @field_validator("redirect_chain")
    @classmethod
    def validate_redirect_urls(cls, value: list[str]) -> list[str]:
        return [validated_http_url(url) for url in value]

    @field_validator("media_type")
    @classmethod
    def validate_media_type(cls, value: str | None) -> str | None:
        return None if value is None else validated_media_type(value)

    @field_validator("redistribution_note")
    @classmethod
    def validate_redistribution_note(cls, value: str) -> str:
        return _stripped_nonblank(value, "redistribution note")

    @field_validator("title")
    @classmethod
    def validate_title(cls, value: str | None) -> str | None:
        return None if value is None else _stripped_nonblank(value, "title")

    @model_validator(mode="after")
    def validate_provenance(self) -> CaptureMetadata:
        if self.redirect_chain:
            if len(self.redirect_chain) < 2:
                raise ValueError("redirect chain must include requested and canonical URLs")
            if self.redirect_chain[0] != self.requested_url:
                raise ValueError("redirect chain must begin with requested URL")
            if self.canonical_url is None or self.redirect_chain[-1] != self.canonical_url:
                raise ValueError("redirect chain must end with canonical URL")
        elif self.canonical_url is not None and self.requested_url != self.canonical_url:
            raise ValueError("a changed canonical URL requires a redirect chain")

        retrieved_date = self.retrieved_at.date()
        if self.published_at is not None and self.published_at > retrieved_date:
            raise ValueError("publication date cannot be after retrieval date")
        if self.updated_at is not None and self.updated_at > retrieved_date:
            raise ValueError("update date cannot be after retrieval date")
        if (
            self.published_at is not None
            and self.updated_at is not None
            and self.updated_at < self.published_at
        ):
            raise ValueError("update date cannot be before publication date")
        return self


class CaptureRequest(CaptureMetadata):
    capture_method: Literal["static_html", "pdf", "image", "browser", "manual_upload"]

    @model_validator(mode="after")
    def validate_capture_request(self) -> CaptureRequest:
        if self.title is None:
            raise ValueError("captured evidence requires a title")
        if self.canonical_url is None:
            raise ValueError("captured evidence requires a canonical URL")
        if self.media_type is None:
            raise ValueError("captured evidence requires a media type")
        essence = media_type_essence(self.media_type)
        if self.capture_method in {"static_html", "pdf", "image", "browser"}:
            if self.http_status is None:
                raise ValueError("direct captures require an HTTP status")
            if not 200 <= self.http_status < 300:
                raise ValueError("a successful direct capture requires a 2xx HTTP status")
        if self.capture_method == "static_html" and essence not in {
            "text/html",
            "application/xhtml+xml",
        }:
            raise ValueError("static_html capture requires an HTML media type")
        if self.capture_method == "pdf" and essence != "application/pdf":
            raise ValueError("pdf capture requires application/pdf")
        if self.capture_method == "image" and not essence.startswith("image/"):
            raise ValueError("image capture requires an image media type")
        if self.capture_method == "browser" and not self.browser_required:
            raise ValueError("browser capture must record browser_required=true")
        return self


class UnavailableRequest(CaptureMetadata):
    capture_method: Literal["unavailable"] = "unavailable"
    unavailable_reason: str = Field(min_length=1, max_length=MAX_PUBLIC_NOTE_CHARS)

    @field_validator("unavailable_reason")
    @classmethod
    def validate_unavailable_reason(cls, value: str) -> str:
        return _stripped_nonblank(value, "unavailable reason")

    @model_validator(mode="after")
    def validate_unavailable_request(self) -> UnavailableRequest:
        if self.published_at is not None or self.updated_at is not None:
            raise ValueError("unavailable evidence cannot claim publication dates")
        return self


class CapturedManifest(CaptureRequest):
    id: str = Field(pattern=CAPTURE_ID_PATTERN)
    availability: Literal["captured"] = "captured"
    content_sha256: str = Field(pattern=SHA256_PATTERN)
    byte_length: int = Field(gt=0)
    storage_scope: Literal["local_only"] = "local_only"
    storage_reference: str

    @model_validator(mode="after")
    def validate_content_address(self) -> CapturedManifest:
        expected = f"sha256/{self.content_sha256[:2]}/{self.content_sha256}"
        if self.storage_reference != expected:
            raise ValueError(f"storage reference must equal content address {expected!r}")
        if not self.id.startswith(_capture_id_prefix(self.source_id, self.retrieved_at)):
            raise ValueError("capture ID must encode its source and UTC retrieval time")
        payload = self.model_dump(mode="json", exclude={"id", "availability"})
        fingerprint = evidence_fingerprint(payload)
        if not self.id.endswith(f"-{fingerprint[:12]}"):
            raise ValueError("captured evidence ID must end with its record hash prefix")
        return self


class UnavailableManifest(UnavailableRequest):
    id: str = Field(pattern=CAPTURE_ID_PATTERN)
    availability: Literal["unavailable"] = "unavailable"

    @model_validator(mode="after")
    def validate_identity(self) -> UnavailableManifest:
        if not self.id.startswith(_capture_id_prefix(self.source_id, self.retrieved_at)):
            raise ValueError("capture ID must encode its source and UTC retrieval time")
        payload = self.model_dump(mode="json", exclude={"id", "availability"})
        fingerprint = evidence_fingerprint(payload)
        if not self.id.endswith(f"-{fingerprint[:12]}"):
            raise ValueError("unavailable capture ID must end with its metadata hash prefix")
        return self


CaptureManifest = CapturedManifest | UnavailableManifest
CAPTURE_MANIFEST_ADAPTER: TypeAdapter[CaptureManifest] = TypeAdapter(CaptureManifest)


class ManualEntryDraft(EvidenceModel):
    schema_version: Literal["1.0"] = "1.0"
    entry_method: Literal["manual"] = "manual"
    source_id: str = Field(pattern=SOURCE_ID_PATTERN)
    capture_id: str = Field(pattern=CAPTURE_ID_PATTERN)
    evidence_type: Literal[
        "screenshot",
        "blocked_page",
        "paywalled_page",
        "email",
        "scanned_material",
        "image",
        "pdf",
    ]
    evidence_locator: str = Field(min_length=1, max_length=MAX_PUBLIC_LOCATOR_CHARS)
    transcription: str = Field(min_length=1, max_length=MAX_PUBLIC_TRANSCRIPTION_CHARS)
    reviewer: str = Field(min_length=1, max_length=MAX_PUBLIC_NAME_CHARS)
    entered_at: AwareDatetime
    review_status: Literal["pending", "verified", "rejected"]
    reviewed_by: str | None = Field(default=None, max_length=MAX_PUBLIC_NAME_CHARS)
    reviewed_at: AwareDatetime | None = None
    review_note: str | None = Field(default=None, max_length=MAX_PUBLIC_NOTE_CHARS)

    @field_validator("evidence_locator", "transcription", "reviewer")
    @classmethod
    def validate_required_audit_text(cls, value: str) -> str:
        return _stripped_nonblank(value, "manual audit field")

    @field_validator("reviewed_by", "review_note")
    @classmethod
    def validate_optional_audit_text(cls, value: str | None) -> str | None:
        return None if value is None else _stripped_nonblank(value, "manual review field")

    @model_validator(mode="after")
    def validate_review(self) -> ManualEntryDraft:
        review_fields = (self.reviewed_by, self.reviewed_at, self.review_note)
        if self.review_status == "pending" and any(value is not None for value in review_fields):
            raise ValueError("pending manual entries cannot carry completed review metadata")
        if self.review_status != "pending":
            if self.reviewed_by is None or self.reviewed_at is None:
                raise ValueError("completed manual review requires reviewer and timestamp")
            if self.reviewed_at < self.entered_at:
                raise ValueError("manual review cannot predate entry")
            if self.review_note is None:
                raise ValueError("completed manual review requires a review note")
        return self


class ManualEntry(ManualEntryDraft):
    id: str = Field(pattern=MANUAL_ID_PATTERN)

    @model_validator(mode="after")
    def validate_identity(self) -> ManualEntry:
        timestamp = self.entered_at.astimezone(UTC).strftime("%Y%m%dT%H%M%SZ")
        if not self.id.startswith(f"manual-{self.source_id}-{timestamp}-"):
            raise ValueError("manual entry ID must encode its source and UTC entry time")
        payload = self.model_dump(mode="json", exclude={"id"})
        fingerprint = evidence_fingerprint(payload)
        if not self.id.endswith(f"-{fingerprint[:12]}"):
            raise ValueError("manual entry ID must end with its metadata hash prefix")
        return self


def _capture_id_prefix(source_id: str, retrieved_at: AwareDatetime) -> str:
    timestamp = retrieved_at.astimezone(UTC).strftime("%Y%m%dT%H%M%SZ")
    return f"capture-{source_id}-{timestamp}-"


def evidence_fingerprint(payload: object) -> str:
    """Hash the canonical public record fields used to derive immutable IDs."""
    return hashlib.sha256(canonical_json_bytes(payload)).hexdigest()


def _stripped_nonblank(value: str, label: str) -> str:
    stripped = value.strip()
    if not stripped:
        raise ValueError(f"{label} cannot be blank")
    return stripped
