"""Read and validate the preregistered source panel."""

from collections import Counter
from pathlib import Path
from typing import Any, cast

import yaml
from pydantic import ValidationError
from yaml.constructor import ConstructorError
from yaml.nodes import MappingNode, ScalarNode

from election_guide.inventory.models import Inventory
from election_guide.sources.models import SourceRegistry


class _UniqueKeyLoader(yaml.SafeLoader):
    """Load safe YAML while rejecting policy fields that silently overwrite each other."""

    def construct_mapping(self, node: MappingNode, deep: bool = False) -> dict[Any, Any]:
        keys: set[str] = set()
        for key_node, _ in node.value:
            if not isinstance(key_node, ScalarNode):
                raise ConstructorError(
                    "while constructing a mapping",
                    node.start_mark,
                    "mapping keys must be scalar values",
                    key_node.start_mark,
                )
            key = key_node.value
            if key in keys:
                raise ConstructorError(
                    "while constructing a mapping",
                    node.start_mark,
                    f"duplicate mapping key {key!r}",
                    key_node.start_mark,
                )
            keys.add(key)
        return cast(dict[Any, Any], super().construct_mapping(node, deep=deep))


def read_source_registry(path: Path) -> SourceRegistry:
    """Load a YAML source registry and expose validation as a stable value error."""
    try:
        raw: Any = yaml.load(path.read_text(encoding="utf-8"), Loader=_UniqueKeyLoader)
        return SourceRegistry.model_validate(raw)
    except (OSError, yaml.YAMLError, ValidationError) as error:
        raise ValueError(str(error)) from error


def validate_registry_inventory(registry: SourceRegistry, inventory: Inventory) -> None:
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
    if missing:
        raise ValueError(f"source registry omits Seattle legislative districts: {sorted(missing)}")
