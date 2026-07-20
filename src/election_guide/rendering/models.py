"""Strict rendering configuration and validation models."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

MetadataText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
REQUIRED_RENDER_CHECK_IDS = frozenset(
    {
        "html-race-topology",
        "html-display-values",
        "html-source-evidence",
        "pdf-page-count",
        "pdf-letter-size",
        "pdf-selectable-text",
        "pdf-display-values",
        "pdf-metadata",
        "pdf-links",
        "rendered-pages",
        "safe-print-edges",
        "detailed-fallback",
        "responsive-viewports",
    }
)


class RenderingModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class RenderingConfiguration(RenderingModel):
    id: str = Field(pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
    page_size: Literal["Letter"]
    orientation: Literal["portrait"]
    concise_page_count: Literal[2]
    render_engine: Literal["chromium"]
    require_selectable_text: bool = Field(strict=True)
    require_accessible_metadata: bool = Field(strict=True)
    title: MetadataText
    author: MetadataText
    subject: MetadataText
    project_url: str = Field(pattern=r"^https://")
    html_filename: str = Field(pattern=r"^[A-Za-z0-9_.-]+\.html$")
    pdf_filename: str = Field(pattern=r"^[A-Za-z0-9_.-]+\.pdf$")
    detailed_pdf_filename: str = Field(pattern=r"^[A-Za-z0-9_.-]+\.pdf$")
    desktop_width: int = Field(ge=1024, le=2560, strict=True)
    mobile_width: int = Field(ge=320, le=768, strict=True)
    screenshot_height: int = Field(ge=600, le=2000, strict=True)
    minimum_print_font_points: float = Field(ge=6, le=12, strict=True)

    @model_validator(mode="after")
    def validate_required_features(self) -> RenderingConfiguration:
        if not self.require_selectable_text or not self.require_accessible_metadata:
            raise ValueError("rendering requirements must remain enabled")
        return self


class RenderCheck(RenderingModel):
    id: str
    passed: bool = Field(strict=True)
    message: str


class RenderedPage(RenderingModel):
    page_number: int = Field(ge=1, strict=True)
    image_path: Path
    width: int = Field(ge=1, strict=True)
    height: int = Field(ge=1, strict=True)
    ink_fraction: float = Field(ge=0, le=1)
    edge_ink_fraction: float = Field(ge=0, le=1)


class RenderingValidationReport(RenderingModel):
    schema_version: Literal["1.0"] = "1.0"
    passed: bool = Field(strict=True)
    page_count: int = Field(ge=0, strict=True)
    pdf_text_length: int = Field(ge=0, strict=True)
    link_count: int = Field(ge=0, strict=True)
    edition: Literal["concise", "concise_plus_detailed"]
    detailed_page_count: int = Field(ge=0, strict=True)
    checks: list[RenderCheck]
    pages: list[RenderedPage]
    detailed_pages: list[RenderedPage]

    @model_validator(mode="after")
    def validate_summary(self) -> RenderingValidationReport:
        check_ids = [check.id for check in self.checks]
        if len(check_ids) != len(set(check_ids)) or set(check_ids) != set(
            REQUIRED_RENDER_CHECK_IDS
        ):
            raise ValueError("rendering report must contain each required check exactly once")
        if self.passed != all(check.passed for check in self.checks):
            raise ValueError("rendering validation summary does not match its checks")
        if self.page_count != len(self.pages):
            raise ValueError("rendered page count does not match its page records")
        if self.detailed_page_count != len(self.detailed_pages):
            raise ValueError("detailed page count does not match its page records")
        if (self.edition == "concise") != (self.detailed_page_count == 0):
            raise ValueError("rendering edition does not match detailed page output")
        if self.passed:
            if self.page_count != 2 or self.pdf_text_length == 0 or self.link_count == 0:
                raise ValueError("passed rendering report is missing required concise artifacts")
            if [page.page_number for page in self.pages] != [1, 2]:
                raise ValueError("passed concise page records must be ordered pages 1 and 2")
            if any(
                page.image_path.parent != Path("pdf/pages")
                or _page_path_number(page.image_path) != page.page_number
                for page in self.pages
            ):
                raise ValueError("concise page paths must match their page numbers")
            if any(
                page.ink_fraction <= 0.005 or page.edge_ink_fraction >= 0.002 for page in self.pages
            ):
                raise ValueError("passed concise pages must be nonblank and inside safe edges")
            if self.edition == "concise_plus_detailed":
                if self.detailed_page_count <= 2:
                    raise ValueError("passed detailed fallback must be longer than two pages")
                if [page.page_number for page in self.detailed_pages] != list(
                    range(1, self.detailed_page_count + 1)
                ):
                    raise ValueError("passed detailed page records must be in document order")
                if any(
                    page.image_path.parent != Path("pdf/detailed-pages")
                    or _page_path_number(page.image_path) != page.page_number
                    for page in self.detailed_pages
                ):
                    raise ValueError("detailed page paths must match their page numbers")
                if any(
                    page.ink_fraction <= 0.005 or page.edge_ink_fraction >= 0.002
                    for page in self.detailed_pages
                ):
                    raise ValueError("passed detailed pages must be nonblank and inside safe edges")
        return self


def _page_path_number(path: Path) -> int:
    match = re.fullmatch(r"page-(\d+)\.png", path.name)
    return int(match.group(1)) if match is not None else -1
