"""Validated source-panel and discovery records."""

from __future__ import annotations

from datetime import date
from typing import Literal

from pydantic import (
    AwareDatetime,
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
)

from election_guide.inventory.models import Jurisdiction, Race
from election_guide.validation import validated_http_url, validated_media_type


class SourceModel(BaseModel):
    """Reject undeclared fields so policy drift fails loudly."""

    model_config = ConfigDict(extra="forbid")


class Eligibility(SourceModel):
    kind: Literal[
        "all_seattle_ballot_races",
        "seattle_ballot_races_except_other_legislative_districts",
        "jurisdictions_only",
        "none",
    ]
    jurisdiction_ids: list[str] = Field(default_factory=list)
    rationale: str = Field(min_length=1)

    @model_validator(mode="after")
    def validate_scope(self) -> Eligibility:
        if self.kind in {
            "jurisdictions_only",
            "seattle_ballot_races_except_other_legislative_districts",
        }:
            if not self.jurisdiction_ids:
                raise ValueError(f"{self.kind} eligibility requires jurisdiction_ids")
        elif self.jurisdiction_ids:
            raise ValueError(f"{self.kind} eligibility cannot list jurisdiction_ids")
        return self

    def permits_jurisdiction(self, jurisdiction: Jurisdiction) -> bool:
        """Return whether this source may contribute to a race in the jurisdiction."""
        if self.kind == "none":
            return False
        if self.kind == "all_seattle_ballot_races":
            return True
        if self.kind == "jurisdictions_only":
            return jurisdiction.id in self.jurisdiction_ids
        return (
            jurisdiction.kind != "legislative_district" or jurisdiction.id in self.jurisdiction_ids
        )

    def permits_race(self, race: Race, jurisdiction: Jurisdiction) -> bool:
        """Return whether this source may contribute to a publishable ballot race."""
        return race.publication_eligible and self.permits_jurisdiction(jurisdiction)


class Discovery(SourceModel):
    status: Literal["published", "not_found", "not_an_endorsement_publisher", "access_restricted"]
    checked_at: AwareDatetime
    requested_url: str
    canonical_url: str | None = None
    redirect_chain: list[str] = Field(default_factory=list)
    media_type: str | None = None
    published_at: date | None = None
    updated_at: date | None = None
    evidence_locator: str = Field(min_length=1)
    notes: str = Field(min_length=1)

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
        if value is None:
            return None
        try:
            return validated_media_type(value)
        except ValueError as error:
            raise ValueError("media_type must be a nonempty MIME type") from error

    @model_validator(mode="after")
    def validate_publication_metadata(self) -> Discovery:
        if self.status != "access_restricted":
            if self.canonical_url is None:
                raise ValueError("nonrestricted discovery requires canonical_url")
            if self.media_type is None:
                raise ValueError("nonrestricted discovery requires media_type")
        if self.status != "published" and (
            self.published_at is not None or self.updated_at is not None
        ):
            raise ValueError("only published discoveries may carry publication dates")
        checked_date = self.checked_at.date()
        if self.published_at is not None and self.published_at > checked_date:
            raise ValueError("publication date cannot be after discovery access date")
        if self.updated_at is not None and self.updated_at > checked_date:
            raise ValueError("update date cannot be after discovery access date")
        if (
            self.published_at is not None
            and self.updated_at is not None
            and self.updated_at < self.published_at
        ):
            raise ValueError("update date cannot be before publication date")
        if self.redirect_chain:
            if len(self.redirect_chain) < 2:
                raise ValueError("redirect_chain must include requested and canonical URLs")
            if self.redirect_chain[0] != self.requested_url:
                raise ValueError("redirect_chain must begin with requested_url")
            if self.canonical_url is None or self.redirect_chain[-1] != self.canonical_url:
                raise ValueError("redirect_chain must end with canonical_url")
        elif self.canonical_url is not None and self.canonical_url != self.requested_url:
            raise ValueError("changed canonical_url requires a redirect_chain")
        return self


class Source(SourceModel):
    id: str = Field(pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
    name: str = Field(min_length=1)
    category: Literal[
        "progressive_general",
        "democratic_party",
        "transportation_urbanism",
        "environmental",
        "labor",
        "rights_representation",
        "comparison",
    ]
    organization_url: str
    geographic_kind: Literal["general", "legislative_district"]
    panel_role: Literal["consensus", "comparison", "excluded"]
    panel_reason: str = Field(min_length=1)
    eligibility: Eligibility
    discovery: Discovery
    publisher_id: str | None = None
    overlap_group_ids: list[str] = Field(default_factory=list)

    @field_validator("organization_url")
    @classmethod
    def validate_organization_url(cls, value: str) -> str:
        return validated_http_url(value)

    @model_validator(mode="after")
    def validate_role(self) -> Source:
        if self.panel_role == "excluded" and self.eligibility.kind != "none":
            raise ValueError(f"excluded source {self.id!r} must have no eligibility")
        if self.panel_role != "excluded" and self.eligibility.kind == "none":
            raise ValueError(f"active source {self.id!r} must define eligibility")
        if self.panel_role == "comparison" and self.category != "comparison":
            raise ValueError(f"comparison source {self.id!r} must use comparison category")
        if self.panel_role != "comparison" and self.category == "comparison":
            raise ValueError(f"comparison category source {self.id!r} must be comparison-only")
        if (
            self.discovery.status == "not_an_endorsement_publisher"
            and self.panel_role != "excluded"
        ):
            raise ValueError(
                f"non-endorsement publisher {self.id!r} must be excluded from the panel"
            )
        if self.publisher_id is not None and self.panel_role != "excluded":
            raise ValueError(f"publication {self.id!r} with a publisher must be excluded")
        if len(self.overlap_group_ids) != len(set(self.overlap_group_ids)):
            raise ValueError(f"source {self.id!r} repeats an overlap group")
        if self.geographic_kind == "legislative_district":
            if self.eligibility.kind != "seattle_ballot_races_except_other_legislative_districts":
                raise ValueError(
                    f"legislative-district source {self.id!r} must include Seattle-ballot "
                    "races while excluding other legislative districts"
                )
            if len(self.eligibility.jurisdiction_ids) != 1:
                raise ValueError(
                    f"legislative-district source {self.id!r} must name exactly one district"
                )
        elif self.eligibility.kind in {
            "jurisdictions_only",
            "seattle_ballot_races_except_other_legislative_districts",
        }:
            raise ValueError(f"general source {self.id!r} cannot use district-scoped eligibility")
        return self


class OverlapGroup(SourceModel):
    id: str = Field(pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
    label: str = Field(min_length=1)
    description: str = Field(min_length=1)
    member_ids: list[str] = Field(min_length=2)


class SourceRegistry(SourceModel):
    schema_version: Literal["1.0"] = "1.0"
    id: str
    election_id: str
    frozen_at: AwareDatetime
    research_cutoff: AwareDatetime
    notes: list[str]
    sources: list[Source] = Field(min_length=1)
    overlap_groups: list[OverlapGroup]

    @model_validator(mode="after")
    def validate_registry(self) -> SourceRegistry:
        if self.research_cutoff > self.frozen_at:
            raise ValueError("research cutoff cannot be after panel freeze")

        source_ids = [source.id for source in self.sources]
        if len(source_ids) != len(set(source_ids)):
            raise ValueError("duplicate source id")
        known_sources = set(source_ids)

        comparison_sources = [
            source for source in self.sources if source.panel_role == "comparison"
        ]
        if len(comparison_sources) != 1:
            raise ValueError("registry must contain exactly one comparison source")

        for source in self.sources:
            if source.discovery.checked_at > self.research_cutoff:
                raise ValueError(f"source {source.id!r} was checked after the research cutoff")
            if source.publisher_id is not None:
                if source.publisher_id not in known_sources:
                    raise ValueError(
                        f"source {source.id!r} has unknown publisher {source.publisher_id!r}"
                    )
                if source.publisher_id == source.id:
                    raise ValueError(f"source {source.id!r} cannot publish itself")
        group_ids = [group.id for group in self.overlap_groups]
        if len(group_ids) != len(set(group_ids)):
            raise ValueError("duplicate overlap group id")
        memberships: dict[str, set[str]] = {source.id: set() for source in self.sources}
        for group in self.overlap_groups:
            if len(group.member_ids) != len(set(group.member_ids)):
                raise ValueError(f"overlap group {group.id!r} repeats a member")
            unknown = set(group.member_ids) - known_sources
            if unknown:
                raise ValueError(
                    f"overlap group {group.id!r} has unknown members: {sorted(unknown)}"
                )
            for member_id in group.member_ids:
                memberships[member_id].add(group.id)

        for source in self.sources:
            declared = set(source.overlap_group_ids)
            if declared != memberships[source.id]:
                raise ValueError(
                    f"source {source.id!r} overlap groups do not match group membership"
                )
        return self
