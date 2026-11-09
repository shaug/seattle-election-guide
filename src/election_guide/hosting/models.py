"""Strict configuration for the public election-guide archive."""

from __future__ import annotations

import re
from pathlib import PurePosixPath
from typing import Literal
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from election_guide.publication.precinct_ballot import HistoricalPrecinctProvenance
from election_guide.rendering.models import PagePresentation
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


class InputHashes(HostingModel):
    """Reviewed file-byte bindings, separate from semantic panel identities."""

    ledger_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    dataset_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    registry_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


class PublicationRequest(HostingModel):
    issue_number: int = Field(gt=0, strict=True)
    previous_release_sha: str = Field(pattern=r"^[0-9a-f]{40}$")
    inputs: InputHashes


class PublishedElection(HostingModel):
    """One election release selected for the public archive."""

    election_id: str = Field(pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
    bundle_id: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
    release_version: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
    source_panel_id: str = Field(min_length=1)
    source_panel_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    source_registry_hash: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    publication_request: PublicationRequest | None = None
    comparison_route_preview: bool = Field(default=False, strict=True)
    updates_from_current_source: bool = Field(
        default=False, strict=True, exclude_if=lambda value: not value
    )
    git_commit: str | None = Field(default=None, pattern=r"^[0-9a-f]{40}$")
    release_manifest_sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    bundle_sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")


class HistoricalCapabilityRef(HostingModel):
    """Reviewed current capability input, separate from an immutable release."""

    path: str
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")

    @field_validator("path")
    @classmethod
    def validate_path(cls, value: str) -> str:
        path = PurePosixPath(value)
        if (
            path.is_absolute()
            or ".." in path.parts
            or "\\" in value
            or path.as_posix() != value
            or not value.startswith("config/elections/")
            or not value.endswith(".json")
        ):
            raise ValueError("historical capability path must be a safe election configuration")
        return value


class SiteManifest(HostingModel):
    """Versioned source of truth for one complete Pages deployment."""

    schema_version: Literal["1.0", "1.1", "1.2"] = "1.0"
    canonical_origin: str
    current_election_id: str = Field(pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
    elections: list[PublishedElection] = Field(min_length=1)
    historical_capabilities: dict[str, HistoricalCapabilityRef] = Field(
        default_factory=dict, exclude_if=lambda value: not value
    )

    @property
    def current_presentation(self) -> bool:
        return self.schema_version != "1.0"

    @property
    def deployment_schema(self) -> str:
        return {"1.0": "2.0", "1.1": "3.0", "1.2": "3.1"}[self.schema_version]

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
        if self.schema_version != "1.2" and "historical_capabilities" in self.model_fields_set:
            raise ValueError("historical capabilities require source schema1.2")
        if self.schema_version == "1.2" and not self.historical_capabilities:
            raise ValueError("source schema1.2 requires a reviewed historical capability")
        if set(self.historical_capabilities) - (set(election_ids) - {self.current_election_id}):
            raise ValueError("historical capabilities must name declared historical elections")
        if any(
            election.publication_request is not None
            and election.election_id != self.current_election_id
            for election in self.elections
        ):
            raise ValueError("only the current election may request publication")
        preview_elections = [
            election.election_id for election in self.elections if election.comparison_route_preview
        ]
        if preview_elections not in ([], [self.current_election_id]):
            raise ValueError("only the current election may preview its comparison route")
        if any(re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", value) is None for value in election_ids):
            raise ValueError("site manifest contains an invalid election ID")
        return self


class UpdatesProjection(HostingModel):
    """Current authored log provenance, separate from immutable election artifacts."""

    schema_version: Literal["1.1"] = "1.1"
    source_git_commit: str = Field(pattern=r"^[0-9a-f]{40}$")
    authored_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    archive_release_version: str = Field(min_length=1)


class DeployedElection(HostingModel):
    election_id: str = Field(pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
    bundle_id: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
    release_version: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
    git_commit: str = Field(pattern=r"^[0-9a-f]{40}$")
    source_panel_id: str = Field(min_length=1)
    source_panel_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    source_registry_hash: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    release_manifest_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    presentation: PagePresentation | None = Field(
        default=None, exclude_if=lambda value: value is None
    )
    updates_projection: UpdatesProjection | None = Field(
        default=None, exclude_if=lambda value: value is None
    )
    precinct_supplement: HistoricalPrecinctProvenance | None = Field(
        default=None, exclude_if=lambda value: value is None
    )


class DeploymentManifest(HostingModel):
    """Integrity contract for one completed Pages artifact."""

    schema_version: Literal["2.0", "3.0", "3.1"] = "2.0"
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
        for election in self.elections:
            if self.schema_version in {"3.0", "3.1"} and election.presentation is None:
                raise ValueError("deployment schema3 requires election presentation provenance")
            if self.schema_version == "2.0" and "presentation" in election.model_fields_set:
                raise ValueError("deployment schema2.0 cannot declare presentation provenance")
            if self.schema_version != "3.1" and "precinct_supplement" in election.model_fields_set:
                raise ValueError("historical precinct supplements require deployment schema3.1")
            if election.precinct_supplement is not None and (
                election.precinct_supplement.election_id != election.election_id
                or election.election_id == self.current_election_id
            ):
                raise ValueError("precinct supplement must belong to its historical election")
        if self.schema_version == "3.1" and not any(
            e.precinct_supplement is not None for e in self.elections
        ):
            raise ValueError("deployment schema3.1 requires a historical precinct supplement")
        election_ids = [election.election_id for election in self.elections]
        if len(election_ids) != len(set(election_ids)):
            raise ValueError("deployment manifest repeats an election ID")
        if self.current_election_id not in set(election_ids):
            raise ValueError("deployment manifest current election is not published")
        if election_ids[0] != self.current_election_id:
            raise ValueError("deployment manifest must list the current election first")
        return self
