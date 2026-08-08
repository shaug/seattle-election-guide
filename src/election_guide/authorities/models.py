"""Validated counting-authority identity records (docs/EVIDENCE_CAPTURE.md).

Distinct from `election_guide.sources` (the preregistered endorsement-source
panel): a counting authority publishes election results, not endorsements. It
carries no panel role, reporting category, or endorsement eligibility, so it
gets its own minimal registry rather than being forced into the source
panel's schema, which would corrupt what a "source" means in this repository.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from election_guide.validation import validated_http_url

AUTHORITY_ID_PATTERN = r"^[a-z0-9]+(?:-[a-z0-9]+)*$"


class AuthorityModel(BaseModel):
    """Reject undeclared fields so registry drift fails loudly."""

    model_config = ConfigDict(extra="forbid")


class Authority(AuthorityModel):
    id: str = Field(pattern=AUTHORITY_ID_PATTERN)
    name: str = Field(min_length=1, max_length=200)
    organization_url: str
    notes: str | None = None

    @field_validator("organization_url")
    @classmethod
    def validate_organization_url(cls, value: str) -> str:
        return validated_http_url(value)


class AuthorityRegistry(AuthorityModel):
    schema_version: Literal["1.0"] = "1.0"
    authorities: list[Authority] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_unique_ids(self) -> AuthorityRegistry:
        ids = [authority.id for authority in self.authorities]
        if len(ids) != len(set(ids)):
            raise ValueError("authority registry repeats an authority id")
        return self

    def authority_ids(self) -> set[str]:
        """Expose registered identities for external membership checks."""
        return {authority.id for authority in self.authorities}
