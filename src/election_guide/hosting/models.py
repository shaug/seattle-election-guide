"""Strict configuration for the public election-guide archive."""

from __future__ import annotations

import re
from pathlib import PurePosixPath
from typing import Literal
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from election_guide.validation import validated_http_url


def _validated_canonical_origin(value: str) -> str:
    normalized = validated_http_url(value)
    parsed = urlsplit(normalized)
    if (
        parsed.scheme != "https"
        or parsed.hostname is None
        or parsed.path not in {"", "/"}
        or parsed.query
        or parsed.fragment
    ):
        raise ValueError("canonical origin must be an HTTPS origin without a path or credentials")
    return f"https://{parsed.netloc}"


class HostingModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class PublishedElection(HostingModel):
    """One election release selected for the public archive."""

    election_id: str = Field(pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
    name: str = Field(min_length=1, max_length=200)
    bundle_id: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
    release_version: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
    source_panel_id: str = Field(min_length=1)
    source_panel_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    git_commit: str | None = Field(default=None, pattern=r"^[0-9a-f]{40}$")
    release_manifest_sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    bundle_sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def strip_name(self) -> PublishedElection:
        stripped = self.name.strip()
        if not stripped:
            raise ValueError("published election name cannot be blank")
        self.name = stripped
        return self


class SiteManifest(HostingModel):
    """Versioned source of truth for one complete Pages deployment."""

    schema_version: Literal["1.0"] = "1.0"
    canonical_origin: str
    current_election_id: str = Field(pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
    elections: list[PublishedElection] = Field(min_length=1)

    @field_validator("canonical_origin")
    @classmethod
    def validate_canonical_origin(cls, value: str) -> str:
        return _validated_canonical_origin(value)

    @model_validator(mode="after")
    def validate_archive(self) -> SiteManifest:
        election_ids = [election.election_id for election in self.elections]
        if len(election_ids) != len(set(election_ids)):
            raise ValueError("site manifest repeats an election ID")
        bundle_ids = [election.bundle_id for election in self.elections]
        if len(bundle_ids) != len(set(bundle_ids)):
            raise ValueError("site manifest repeats a bundle ID")
        if self.current_election_id not in set(election_ids):
            raise ValueError("site manifest current election is not published")
        if election_ids[0] != self.current_election_id:
            raise ValueError("site manifest must list the current election first")
        if any(re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", value) is None for value in election_ids):
            raise ValueError("site manifest contains an invalid election ID")
        return self


class DeployedElection(HostingModel):
    election_id: str = Field(pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
    bundle_id: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
    release_version: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
    git_commit: str = Field(pattern=r"^[0-9a-f]{40}$")
    source_panel_id: str = Field(min_length=1)
    source_panel_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    release_manifest_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


class DeploymentManifest(HostingModel):
    """Integrity contract for one completed Pages artifact."""

    schema_version: Literal["2.0"] = "2.0"
    canonical_origin: str
    current_election_id: str = Field(pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
    elections: list[DeployedElection] = Field(min_length=1)
    assets: dict[str, str] = Field(min_length=1)

    @field_validator("canonical_origin")
    @classmethod
    def validate_canonical_origin(cls, value: str) -> str:
        return _validated_canonical_origin(value)

    @field_validator("assets")
    @classmethod
    def validate_asset_hashes(cls, value: dict[str, str]) -> dict[str, str]:
        invalid_paths = [
            path
            for path in value
            if path in {"", "."}
            or "\\" in path
            or PurePosixPath(path).is_absolute()
            or ".." in PurePosixPath(path).parts
            or path != PurePosixPath(path).as_posix()
            or path == "deployment-manifest.json"
        ]
        if invalid_paths:
            raise ValueError(f"deployment manifest contains invalid asset paths: {invalid_paths}")
        if any(re.fullmatch(r"[0-9a-f]{64}", digest) is None for digest in value.values()):
            raise ValueError("deployment manifest contains an invalid asset hash")
        return value

    @model_validator(mode="after")
    def validate_elections(self) -> DeploymentManifest:
        election_ids = [election.election_id for election in self.elections]
        if len(election_ids) != len(set(election_ids)):
            raise ValueError("deployment manifest repeats an election ID")
        if self.current_election_id not in set(election_ids):
            raise ValueError("deployment manifest current election is not published")
        if election_ids[0] != self.current_election_id:
            raise ValueError("deployment manifest must list the current election first")
        return self
