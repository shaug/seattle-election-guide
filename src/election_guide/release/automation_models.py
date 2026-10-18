"""Strict operational records, separate from immutable release bundle schemas."""

from __future__ import annotations

import re
from typing import Annotated, Literal
from urllib.parse import urlsplit

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, field_validator, model_validator

from election_guide.hosting.models import InputHashes, PublishedElection
from election_guide.validation import validated_http_url

GitSha = Annotated[str, Field(pattern=r"^[0-9a-f]{40}$")]
Sha256 = Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]
PositiveId = Annotated[int, Field(gt=0, strict=True)]


class OperationalRecord(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    schema_version: Literal["1.0"] = "1.0"


class Producer(OperationalRecord):
    repository: str = Field(pattern=r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
    source_sha: GitSha
    workflow_sha: GitSha
    run_id: PositiveId
    run_attempt: PositiveId


class FileDigest(OperationalRecord):
    sha256: Sha256
    size: int = Field(ge=0, strict=True)


class ArtifactRef(OperationalRecord):
    id: PositiveId
    name: str = Field(min_length=1)
    digest: FileDigest
    producer: Producer


class CandidateRecord(OperationalRecord):
    declaration: PublishedElection
    site_manifest_sha256: Sha256
    source_sha: GitSha
    generated_at: AwareDatetime
    inputs: InputHashes
    producer: Producer
    archive: FileDigest
    bundle_sha256: Sha256
    deployment_manifest_sha256: Sha256
    release_artifact: ArtifactRef
    site_artifact: ArtifactRef
    recovered_from: Producer | None = None

    @model_validator(mode="after")
    def validate_identities(self) -> CandidateRecord:
        if self.source_sha != self.producer.source_sha:
            raise ValueError("candidate source differs from its producer")
        for kind, artifact in (("release", self.release_artifact), ("site", self.site_artifact)):
            if artifact.producer != self.producer:
                raise ValueError("candidate artifact producer differs")
            if artifact.name != f"{kind}-{self.producer.run_id}-{self.producer.run_attempt}":
                raise ValueError("candidate artifact name differs from producing attempt")
        if self.release_artifact.id == self.site_artifact.id:
            raise ValueError("release and site artifacts require distinct IDs")
        if self.recovered_from is not None and (
            self.recovered_from.repository != self.producer.repository
            or self.recovered_from.source_sha != self.source_sha
        ):
            raise ValueError("recovery producer must identify the same repository and source")
        return self


class PublishedArchive(OperationalRecord):
    candidate: CandidateRecord
    candidate_artifact: ArtifactRef
    release_id: PositiveId
    asset_id: PositiveId
    asset_name: str = Field(min_length=1)
    archive: FileDigest
    release_manifest_sha256: Sha256
    canonical_bundle_sha256: Sha256
    promotion_manifest_sha256: Sha256


class PublicationResult(OperationalRecord):
    published: PublishedArchive
    promotion_artifact: ArtifactRef


class UploadReceipt(OperationalRecord):
    publication: PublicationResult
    producer: Producer
    github_deployment_id: PositiveId
    deployment_url: str
    uploaded_at: AwareDatetime
    source_sha: GitSha

    @field_validator("deployment_url")
    @classmethod
    def validate_deployment_url(cls, value: str) -> str:
        value = validated_http_url(value)
        parsed = urlsplit(value)
        if (
            parsed.scheme != "https"
            or not parsed.hostname
            or not parsed.hostname.endswith(".pages.dev")
        ):
            raise ValueError("deployment URL must identify a unique HTTPS Pages upload")
        labels = parsed.hostname.removesuffix(".pages.dev").split(".")
        if len(labels) != 2 or re.fullmatch(r"[0-9a-f]+", labels[0]) is None:
            raise ValueError("deployment URL must identify a unique Pages upload")
        if parsed.path not in {"", "/"} or parsed.query or parsed.fragment:
            raise ValueError("deployment URL must be an upload origin")
        return value


class OperationReceipt(OperationalRecord):
    phase: Literal["publication", "deployment"]
    state: Literal["superseded", "deployment_paused", "published", "verified", "failed"]
    producer: Producer
    publication: PublicationResult
    upload: UploadReceipt | None
    verification_sha256: Sha256 | None
    error: str | None
