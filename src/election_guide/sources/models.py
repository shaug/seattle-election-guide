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

CATEGORY_ID_PATTERN = r"^[a-z0-9]+(?:_[a-z0-9]+)*$"
CATEGORY_CODE_PATTERN = r"^G[0-9A-Za-z]{3}$"
SOURCE_CODE_PATTERN = r"^[0-9A-Za-z]{4}$"
TRANSPORT_CODE_PATTERN = r"^[0-9A-Za-z]{4}$"
RESERVED_CATEGORY_INITIALS = frozenset({"G", "g"})


def _validated_source_code(value: str) -> str:
    """Keep `G` and `g` reserved for categories anywhere in a source code."""
    reserved = RESERVED_CATEGORY_INITIALS & set(value)
    if reserved:
        raise ValueError(f"source code {value!r} uses category-reserved {sorted(reserved)}")
    return value


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


class SourceCategory(SourceModel):
    """A selection grouping with a stable semantic id and immutable transport code."""

    id: str = Field(pattern=CATEGORY_ID_PATTERN)
    code: str = Field(pattern=CATEGORY_CODE_PATTERN)
    label: str = Field(min_length=1)
    selectable: bool
    description: str = Field(min_length=1)


class RetiredCode(SourceModel):
    """A tombstone that keeps a withdrawn transport code permanently unusable."""

    code: str = Field(pattern=TRANSPORT_CODE_PATTERN)
    kind: Literal["source", "category"]
    former_id: str = Field(min_length=1)
    retired_in_panel: str = Field(min_length=1)
    reason: str = Field(min_length=1)

    @model_validator(mode="after")
    def validate_code_family(self) -> RetiredCode:
        if self.kind == "category":
            if not self.code.startswith("G"):
                raise ValueError(f"retired category code {self.code!r} must start with 'G'")
        else:
            _validated_source_code(self.code)
        return self


class Source(SourceModel):
    id: str = Field(pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
    code: str = Field(pattern=SOURCE_CODE_PATTERN)
    name: str = Field(min_length=1)
    reporting_category_id: str = Field(pattern=CATEGORY_ID_PATTERN)
    selection_category_ids: list[str] = Field(min_length=1)
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

    @field_validator("code")
    @classmethod
    def validate_code(cls, value: str) -> str:
        return _validated_source_code(value)

    @field_validator("selection_category_ids")
    @classmethod
    def normalize_selection_categories(cls, value: list[str]) -> list[str]:
        """Accept several categories in any order as one sorted, deduplicated set."""
        return sorted(set(value))

    @property
    def is_selectable(self) -> bool:
        """Only panel sources that contribute to the progressive score may be selected."""
        return self.panel_role == "consensus"

    @model_validator(mode="after")
    def validate_role(self) -> Source:
        if self.panel_role == "excluded" and self.eligibility.kind != "none":
            raise ValueError(f"excluded source {self.id!r} must have no eligibility")
        if self.panel_role != "excluded" and self.eligibility.kind == "none":
            raise ValueError(f"active source {self.id!r} must define eligibility")
        if self.reporting_category_id not in self.selection_category_ids:
            raise ValueError(
                f"source {self.id!r} reporting category {self.reporting_category_id!r} "
                "must also be a selection category"
            )
        if self.panel_role == "comparison":
            if self.reporting_category_id != "comparison":
                raise ValueError(f"comparison source {self.id!r} must use comparison category")
            if self.selection_category_ids != ["comparison"]:
                raise ValueError(
                    f"comparison source {self.id!r} cannot join another selection category"
                )
        elif "comparison" in self.selection_category_ids:
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
    schema_version: Literal["1.1"] = "1.1"
    id: str
    election_id: str
    frozen_at: AwareDatetime
    research_cutoff: AwareDatetime
    notes: list[str]
    categories: list[SourceCategory] = Field(min_length=1)
    retired_codes: list[RetiredCode] = Field(default_factory=list[RetiredCode])
    sources: list[Source] = Field(min_length=1)
    overlap_groups: list[OverlapGroup]

    def category_by_id(self, category_id: str) -> SourceCategory:
        """Resolve a validated semantic category id to its catalog entry."""
        return next(category for category in self.categories if category.id == category_id)

    def selectable_source_codes(self, category_id: str) -> list[str]:
        """Return the current selectable members of a category in transport order."""
        if not self.category_by_id(category_id).selectable:
            return []
        return sorted(
            source.code
            for source in self.sources
            if source.is_selectable and category_id in source.selection_category_ids
        )

    @model_validator(mode="after")
    def validate_identities(self) -> SourceRegistry:
        category_ids = [category.id for category in self.categories]
        if len(category_ids) != len(set(category_ids)):
            raise ValueError("duplicate category id")
        known_categories = set(category_ids)

        in_use: dict[str, str] = {}
        for category in self.categories:
            in_use[category.code] = f"category {category.id!r}"
        for source in self.sources:
            if source.code in in_use:
                raise ValueError(f"source {source.id!r} reuses code {source.code!r}")
            in_use[source.code] = f"source {source.id!r}"

        confusable: dict[str, str] = {}
        for code, owner in in_use.items():
            previous = confusable.setdefault(code.casefold(), owner)
            if previous != owner:
                raise ValueError(f"{owner} uses a code confusable with {previous}")

        for retired in self.retired_codes:
            if retired.code in in_use:
                raise ValueError(
                    f"retired code {retired.code!r} was reissued to {in_use[retired.code]}"
                )
            owner = confusable.get(retired.code.casefold())
            if owner is not None:
                raise ValueError(
                    f"retired code {retired.code!r} is confusable with the code of {owner}"
                )
        retired_codes = [retired.code for retired in self.retired_codes]
        if len(retired_codes) != len(set(retired_codes)):
            raise ValueError("duplicate retired code")

        for source in self.sources:
            unknown = set(source.selection_category_ids) - known_categories
            if unknown:
                raise ValueError(f"source {source.id!r} has unknown categories: {sorted(unknown)}")
            if source.reporting_category_id not in known_categories:
                raise ValueError(
                    f"source {source.id!r} has unknown reporting category "
                    f"{source.reporting_category_id!r}"
                )
            if source.is_selectable and not any(
                self.category_by_id(category_id).selectable
                for category_id in source.selection_category_ids
            ):
                raise ValueError(f"consensus source {source.id!r} needs a selectable category")
        return self

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
