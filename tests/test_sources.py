import copy
from collections import Counter
from pathlib import Path
from typing import Any

import pytest
import yaml
from pydantic import ValidationError

from election_guide.inventory.importer import read_inventory
from election_guide.sources.models import SourceRegistry
from election_guide.sources.registry import read_source_registry, validate_registry_inventory
from election_guide.sources.report import render_discovery_report

PROJECT_ROOT = Path(__file__).parent.parent
REGISTRY_PATH = PROJECT_ROOT / "config" / "sources" / "default.yaml"


def test_committed_source_panel_is_frozen_and_complete() -> None:
    registry = read_source_registry(REGISTRY_PATH)

    assert registry.research_cutoff <= registry.frozen_at
    assert len(registry.sources) == 42
    assert Counter(source.panel_role for source in registry.sources) == {
        "consensus": 36,
        "comparison": 1,
        "excluded": 5,
    }
    assert all(source.discovery.status for source in registry.sources)
    assert all(source.panel_reason for source in registry.sources)
    assert any(source.discovery.status == "published" for source in registry.sources)
    assert any(source.panel_role == "excluded" for source in registry.sources)


def test_legislative_district_sources_only_count_in_their_district() -> None:
    registry = read_source_registry(REGISTRY_PATH)
    district_sources = [
        source for source in registry.sources if source.geographic_kind == "legislative_district"
    ]

    assert {source.id for source in district_sources} == {
        "11th-district-democrats",
        "32nd-district-democrats",
        "34th-district-democrats",
        "36th-district-democrats",
        "37th-district-democrats",
        "43rd-district-democrats",
        "46th-district-democrats",
    }
    for source in district_sources:
        assert source.panel_role == "consensus"
        assert source.eligibility.kind == "jurisdictions_only"
        assert len(source.eligibility.jurisdiction_ids) == 1


def test_source_districts_match_the_authoritative_inventory() -> None:
    registry = read_source_registry(REGISTRY_PATH)
    inventory = read_inventory(
        PROJECT_ROOT / "data" / "normalized" / "wa-2026-primary-inventory.json"
    )

    validate_registry_inventory(registry, inventory)


def test_seattle_times_is_the_only_comparison_source() -> None:
    registry = read_source_registry(REGISTRY_PATH)
    comparison = [source for source in registry.sources if source.panel_role == "comparison"]

    assert [source.id for source in comparison] == ["seattle-times-editorial-board"]


def test_committed_discovery_report_matches_registry() -> None:
    registry = read_source_registry(REGISTRY_PATH)
    committed = (PROJECT_ROOT / "docs" / "SOURCE_DISCOVERY.md").read_text(encoding="utf-8")

    assert committed == render_discovery_report(registry)


def test_registry_rejects_duplicate_publisher_as_consensus_source() -> None:
    payload = _registry_payload()
    guide = next(
        source for source in payload["sources"] if source["id"] == "progressive-voters-guide"
    )
    guide["panel_role"] = "consensus"
    guide["eligibility"] = {
        "kind": "all_seattle_ballot_races",
        "rationale": "invalid duplicate",
    }

    with pytest.raises(ValidationError, match="with a publisher must be excluded"):
        SourceRegistry.model_validate(payload)


def test_registry_rejects_broad_legislative_district_eligibility() -> None:
    payload = _registry_payload()
    source = next(
        source for source in payload["sources"] if source["id"] == "43rd-district-democrats"
    )
    source["eligibility"] = {
        "kind": "all_seattle_ballot_races",
        "rationale": "invalid broad eligibility",
    }

    with pytest.raises(ValidationError, match="must use jurisdictions_only"):
        SourceRegistry.model_validate(payload)


def test_registry_rejects_unpaired_overlap_metadata() -> None:
    payload = _registry_payload()
    source = next(source for source in payload["sources"] if source["id"] == "fuse-washington")
    source["overlap_group_ids"] = []

    with pytest.raises(ValidationError, match="overlap groups do not match"):
        SourceRegistry.model_validate(payload)


def test_registry_rejects_discovery_after_panel_freeze() -> None:
    payload = _registry_payload()
    payload["research_cutoff"] = "2026-07-20T00:00:00Z"

    with pytest.raises(ValidationError, match="research cutoff cannot be after panel freeze"):
        SourceRegistry.model_validate(payload)


def test_registry_rejects_unrecorded_redirect() -> None:
    payload = _registry_payload()
    source = next(source for source in payload["sources"] if source["id"] == "fuse-washington")
    source["discovery"]["canonical_url"] = "https://fusewashington.org/changed"

    with pytest.raises(ValidationError, match="changed canonical_url requires a redirect_chain"):
        SourceRegistry.model_validate(payload)


def _registry_payload() -> dict[str, Any]:
    return copy.deepcopy(yaml.safe_load(REGISTRY_PATH.read_text(encoding="utf-8")))
