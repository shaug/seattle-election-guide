"""Read and validate the preregistered source panel."""

import hashlib
from collections import Counter
from pathlib import Path
from typing import Any

import yaml
from pydantic import ValidationError

from election_guide.inventory.models import Inventory
from election_guide.serialization import canonical_json_bytes, read_yaml
from election_guide.sources.models import SourceRegistry


def read_source_registry(path: Path) -> SourceRegistry:
    """Load a YAML source registry and expose validation as a stable value error."""
    try:
        raw: Any = read_yaml(path)
        return SourceRegistry.model_validate(raw)
    except (OSError, yaml.YAMLError, ValidationError) as error:
        raise ValueError(str(error)) from error


def source_registry_hash(registry: SourceRegistry) -> str:
    """Hash the validated panel independent of YAML formatting."""
    return hashlib.sha256(canonical_json_bytes(registry.model_dump(mode="json"))).hexdigest()


def validate_registry_inventory(
    registry: SourceRegistry,
    inventory: Inventory,
    *,
    require_all_districts: bool = True,
) -> None:
    """Require district eligibility to match the authoritative Seattle inventory."""
    if registry.election_id != inventory.election.id:
        raise ValueError(
            f"source registry belongs to {registry.election_id!r}, not {inventory.election.id!r}"
        )
    known_districts = {
        jurisdiction.id
        for jurisdiction in inventory.jurisdictions
        if jurisdiction.kind == "legislative_district"
    }
    referenced_districts = [
        jurisdiction_id
        for source in registry.sources
        if source.geographic_kind == "legislative_district"
        for jurisdiction_id in source.eligibility.jurisdiction_ids
    ]
    duplicate_districts = sorted(
        district for district, count in Counter(referenced_districts).items() if count > 1
    )
    if duplicate_districts:
        raise ValueError(
            f"source registry repeats legislative-district organizations for: {duplicate_districts}"
        )
    referenced_district_set = set(referenced_districts)
    unknown = referenced_district_set - known_districts
    if unknown:
        raise ValueError(
            f"source registry references unknown legislative districts: {sorted(unknown)}"
        )
    missing = known_districts - referenced_district_set
    if require_all_districts and missing:
        raise ValueError(f"source registry omits Seattle legislative districts: {sorted(missing)}")
