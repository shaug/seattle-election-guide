"""Strict rendering configuration and validation models."""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

MetadataText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
REQUIRED_RENDER_CHECK_IDS = frozenset(
    {
        "html-race-topology",
        "html-display-values",
        "html-source-evidence",
        "responsive-viewports",
    }
)


class RenderingModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class RenderingConfiguration(RenderingModel):
    id: str = Field(pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
    author: MetadataText
    subject: MetadataText
    project_url: str = Field(pattern=r"^https://")
    public_site_url: str = Field(pattern=r"^https://[^/]+$")
    html_filename: str = Field(pattern=r"^[A-Za-z0-9_.-]+\.html$")
    desktop_width: int = Field(ge=1024, le=2560, strict=True)
    mobile_width: int = Field(ge=320, le=768, strict=True)
    screenshot_height: int = Field(ge=600, le=2000, strict=True)


class RenderCheck(RenderingModel):
    id: str
    passed: bool = Field(strict=True)
    message: str


class RenderingValidationReport(RenderingModel):
    schema_version: Literal["2.0"] = "2.0"
    passed: bool = Field(strict=True)
    checks: list[RenderCheck]

    @model_validator(mode="after")
    def validate_summary(self) -> RenderingValidationReport:
        check_ids = [check.id for check in self.checks]
        if len(check_ids) != len(set(check_ids)) or set(check_ids) != set(
            REQUIRED_RENDER_CHECK_IDS
        ):
            raise ValueError("rendering report must contain each required check exactly once")
        if self.passed != all(check.passed for check in self.checks):
            raise ValueError("rendering validation summary does not match its checks")
        return self
