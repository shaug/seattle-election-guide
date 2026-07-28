"""Deterministic panel snapshot published for downstream personalization."""

from __future__ import annotations

from typing import Literal

from pydantic import Field

from election_guide.sources.models import SourceModel, SourceRegistry
from election_guide.sources.registry import source_registry_hash


class PanelCategorySnapshot(SourceModel):
    id: str
    code: str
    label: str
    selectable: bool
    panel_role: Literal["tallying", "comparison"] = "tallying"
    member_source_codes: list[str]


class PanelSourceSnapshot(SourceModel):
    id: str
    code: str
    name: str
    panel_role: Literal["consensus", "comparison", "excluded"]
    selectable: bool
    reporting_category_id: str
    selection_category_ids: list[str]


class PanelSnapshot(SourceModel):
    """The frozen identity contract consumed by versioned personalized lenses."""

    schema_version: Literal["1.0"] = "1.0"
    panel_id: str
    panel_version: str
    panel_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    categories: list[PanelCategorySnapshot]
    sources: list[PanelSourceSnapshot]


def panel_version(panel_id: str) -> str:
    """Read the published panel version from its identifier suffix."""
    return panel_id.rsplit("-", maxsplit=1)[-1]


def build_panel_snapshot(registry: SourceRegistry) -> PanelSnapshot:
    """Project the validated registry into its transport-facing identity contract."""
    return PanelSnapshot(
        panel_id=registry.id,
        panel_version=panel_version(registry.id),
        panel_hash=source_registry_hash(registry),
        categories=[
            PanelCategorySnapshot(
                id=category.id,
                code=category.code,
                label=category.label,
                selectable=category.selectable,
                panel_role=category.panel_role,
                member_source_codes=registry.selectable_source_codes(category.id),
            )
            for category in registry.categories
        ],
        sources=[
            PanelSourceSnapshot(
                id=source.id,
                code=source.code,
                name=source.name,
                panel_role=source.panel_role,
                selectable=source.is_selectable,
                reporting_category_id=source.reporting_category_id,
                selection_category_ids=source.selection_category_ids,
            )
            for source in registry.sources
        ],
    )
