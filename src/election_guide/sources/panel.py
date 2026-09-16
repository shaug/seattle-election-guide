"""Deterministic panel snapshot published for downstream personalization."""

from __future__ import annotations

import hashlib
from typing import Literal

from pydantic import Field

from election_guide.serialization import canonical_json_bytes
from election_guide.sources.models import SourceModel, SourceRegistry
from election_guide.sources.registry import source_registry_hash


class PanelEligibilityIdentity(SourceModel):
    kind: Literal[
        "all_seattle_ballot_races",
        "seattle_ballot_races_except_other_legislative_districts",
        "jurisdictions_only",
        "none",
    ]
    jurisdiction_ids: list[str]


class PanelCategoryIdentity(SourceModel):
    id: str
    code: str
    label: str
    selectable: bool
    panel_role: Literal["tallying", "comparison"]
    member_source_codes: list[str]


class PanelSourceIdentity(SourceModel):
    id: str
    code: str
    name: str
    panel_role: Literal["consensus", "comparison", "excluded"]
    selectable: bool
    reporting_category_id: str
    selection_category_ids: list[str]
    eligibility: PanelEligibilityIdentity
    overlap_group_ids: list[str]


class PanelOverlapIdentity(SourceModel):
    id: str
    label: str
    member_ids: list[str]


class PanelRetiredCodeIdentity(SourceModel):
    code: str
    kind: Literal["source", "category"]
    former_id: str
    retired_in_panel: str
    reason: str


class PanelIdentityContract(SourceModel):
    schema_version: Literal["1.0"] = "1.0"
    categories: list[PanelCategoryIdentity]
    sources: list[PanelSourceIdentity]
    overlap_groups: list[PanelOverlapIdentity]
    retired_codes: list[PanelRetiredCodeIdentity]


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


def _panel_identity_contract(registry: SourceRegistry) -> PanelIdentityContract:
    return PanelIdentityContract(
        categories=[
            PanelCategoryIdentity(
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
            PanelSourceIdentity(
                id=source.id,
                code=source.code,
                name=source.name,
                panel_role=source.panel_role,
                selectable=source.is_selectable,
                reporting_category_id=source.reporting_category_id,
                selection_category_ids=source.selection_category_ids,
                eligibility=PanelEligibilityIdentity(
                    kind=source.eligibility.kind,
                    jurisdiction_ids=source.eligibility.jurisdiction_ids,
                ),
                overlap_group_ids=sorted(source.overlap_group_ids),
            )
            for source in registry.sources
        ],
        overlap_groups=[
            PanelOverlapIdentity(
                id=group.id,
                label=group.label,
                member_ids=sorted(group.member_ids),
            )
            for group in sorted(registry.overlap_groups, key=lambda group: group.id)
        ],
        retired_codes=[
            PanelRetiredCodeIdentity(
                code=retired.code,
                kind=retired.kind,
                former_id=retired.former_id,
                retired_in_panel=retired.retired_in_panel,
                reason=retired.reason,
            )
            for retired in registry.retired_codes
        ],
    )


def panel_identity_hash(registry: SourceRegistry) -> str:
    """Hash only the stable transport-facing source-selection contract."""
    contract = _panel_identity_contract(registry)
    return hashlib.sha256(canonical_json_bytes(contract.model_dump(mode="json"))).hexdigest()


def build_panel_snapshot(registry: SourceRegistry) -> PanelSnapshot:
    """Project the validated registry into its transport-facing identity contract."""
    contract_hash = panel_identity_hash(registry)
    compatibility = registry.panel_hash_compatibility
    if registry.schema_version == "1.1":
        panel_hash = source_registry_hash(registry)
    elif compatibility is not None and compatibility.contract_hash == contract_hash:
        panel_hash = compatibility.published_hash
    else:
        panel_hash = contract_hash
    return PanelSnapshot(
        panel_id=registry.id,
        panel_version=panel_version(registry.id),
        panel_hash=panel_hash,
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
