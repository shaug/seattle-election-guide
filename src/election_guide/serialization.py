"""Strict serialization helpers for authoritative project records."""

import json
from pathlib import Path
from typing import Any, cast

import yaml
from yaml.constructor import ConstructorError
from yaml.nodes import MappingNode, ScalarNode


class UniqueKeyLoader(yaml.SafeLoader):
    """Load safe YAML while rejecting fields that silently overwrite each other."""

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


def read_yaml(path: Path) -> Any:
    """Read safe YAML without accepting duplicate mapping keys."""
    return yaml.load(path.read_text(encoding="utf-8"), Loader=UniqueKeyLoader)


def read_json(path: Path) -> Any:
    """Read JSON without accepting duplicate object keys."""

    def unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise ValueError(f"duplicate JSON object key {key!r}")
            result[key] = value
        return result

    return json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=unique_object)


def canonical_json_bytes(value: Any) -> bytes:
    """Serialize a JSON-compatible value deterministically."""
    return (json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + "\n").encode()
