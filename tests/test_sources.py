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
    assert Counter(source.discovery.status for source in registry.sources) == {
        "published": 33,
        "not_found": 4,
        "access_restricted": 2,
        "not_an_endorsement_publisher": 3,
    }
    assert all(source.discovery.status for source in registry.sources)
    assert all(source.panel_reason for source in registry.sources)
    assert any(source.discovery.status == "published" for source in registry.sources)
    assert any(source.panel_role == "excluded" for source in registry.sources)

    wea = next(
        source for source in registry.sources if source.id == "washington-education-association"
    )
    assert wea.discovery.status == "published"
    assert wea.discovery.canonical_url == (
        "https://www.washingtonea.org/advocacy/wea-pac/2026-endorsements/"
    )


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
    protec17_line = next(line for line in committed.splitlines() if line.startswith("| PROTEC17 "))
    assert "updated 2026-07-16" in protec17_line


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
    payload["research_cutoff"] = "2026-07-20T11:00:00Z"

    with pytest.raises(ValidationError, match="research cutoff cannot be after panel freeze"):
        SourceRegistry.model_validate(payload)


def test_registry_rejects_unrecorded_redirect() -> None:
    payload = _registry_payload()
    source = next(source for source in payload["sources"] if source["id"] == "fuse-washington")
    source["discovery"]["canonical_url"] = "https://fusewashington.org/changed"

    with pytest.raises(ValidationError, match="changed canonical_url requires a redirect_chain"):
        SourceRegistry.model_validate(payload)


def test_registry_rejects_source_access_after_research_cutoff() -> None:
    payload = _registry_payload()
    payload["sources"][0]["discovery"]["checked_at"] = "2026-07-20T11:00:00Z"

    with pytest.raises(ValidationError, match="checked after the research cutoff"):
        SourceRegistry.model_validate(payload)


@pytest.mark.parametrize("field", ["published_at", "updated_at"])
def test_registry_rejects_publication_metadata_after_access(field: str) -> None:
    payload = _registry_payload()
    payload["sources"][0]["discovery"][field] = "2026-07-20"

    with pytest.raises(ValidationError, match="date cannot be after discovery access date"):
        SourceRegistry.model_validate(payload)


def test_registry_rejects_update_before_publication() -> None:
    payload = _registry_payload()
    payload["sources"][0]["discovery"]["updated_at"] = "2026-06-01"

    with pytest.raises(ValidationError, match="update date cannot be before publication date"):
        SourceRegistry.model_validate(payload)


def test_registry_requires_timezone_aware_timestamps() -> None:
    payload = _registry_payload()
    payload["research_cutoff"] = "2026-07-19T23:05:54"

    with pytest.raises(ValidationError):
        SourceRegistry.model_validate(payload)


def test_registry_rejects_consensus_non_endorsement_publisher() -> None:
    payload = _registry_payload()
    source = payload["sources"][0]
    source["discovery"]["status"] = "not_an_endorsement_publisher"
    source["discovery"].pop("published_at", None)
    source["discovery"].pop("updated_at", None)

    with pytest.raises(ValidationError, match="must be excluded from the panel"):
        SourceRegistry.model_validate(payload)


@pytest.mark.parametrize("value", ["not a URL", "javascript:alert(1)"])
def test_registry_rejects_non_http_official_urls(value: str) -> None:
    payload = _registry_payload()
    payload["sources"][0]["organization_url"] = value
    payload["sources"][0]["discovery"]["requested_url"] = value
    payload["sources"][0]["discovery"]["canonical_url"] = value

    with pytest.raises(ValidationError):
        SourceRegistry.model_validate(payload)


def test_registry_rejects_credentials_in_official_urls() -> None:
    payload = _registry_payload()
    payload["sources"][0]["discovery"]["requested_url"] = (
        "https://admin:secret@example.com/endorsements"
    )

    with pytest.raises(ValidationError, match="official URLs cannot contain credentials"):
        SourceRegistry.model_validate(payload)


@pytest.mark.parametrize("value", ["", "   ", "not-a-media-type"])
def test_registry_rejects_invalid_media_types(value: str) -> None:
    payload = _registry_payload()
    payload["sources"][0]["discovery"]["media_type"] = value

    with pytest.raises(ValidationError, match="media_type must be a nonempty MIME type"):
        SourceRegistry.model_validate(payload)


def test_registry_rejects_duplicate_source_overlap_group() -> None:
    payload = _registry_payload()
    source = next(
        source for source in payload["sources"] if source["id"] == "progressive-voters-guide"
    )
    source["overlap_group_ids"].append("fuse-publications")

    with pytest.raises(ValidationError, match="repeats an overlap group"):
        SourceRegistry.model_validate(payload)


def test_registry_file_rejects_duplicate_yaml_keys(tmp_path: Path) -> None:
    text = REGISTRY_PATH.read_text(encoding="utf-8")
    path = tmp_path / "duplicate.yaml"
    path.write_text(
        text.replace('schema_version: "1.0"', 'schema_version: "1.0"\nschema_version: "1.0"', 1),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="duplicate mapping key 'schema_version'"):
        read_source_registry(path)


def _registry_payload() -> dict[str, Any]:
    return copy.deepcopy(yaml.safe_load(REGISTRY_PATH.read_text(encoding="utf-8")))
