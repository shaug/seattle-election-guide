"""Strict safe YAML semantics survive the accelerated parser (issue #651)."""

import json
import subprocess
import sys
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

import pytest
import yaml

from election_guide.serialization import read_yaml


@pytest.mark.parametrize(
    ("document", "expected"),
    [
        ("", None),
        (
            "title: 'Café — 西雅图'\nlines: |\n  one\n  two\n",
            {"title": "Café — 西雅图", "lines": "one\ntwo\n"},
        ),
        (
            "null_value: null\nflag: true\ncount: 012\nratio: 1.25\ntext: '012'\n",
            {"null_value": None, "flag": True, "count": 10, "ratio": 1.25, "text": "012"},
        ),
        (
            "day: 2026-10-27\ninstant: 2026-10-27T17:00:00Z\n",
            {"day": date(2026, 10, 27), "instant": datetime(2026, 10, 27, 17, tzinfo=UTC)},
        ),
        ("key: !!binary YWJj\n", {"key": b"abc"}),
        ("null: empty\ntrue: yes-value\n2: two\n", {None: "empty", True: "yes-value", 2: "two"}),
        ("items: [one, {two: 2}]\n", {"items": ["one", {"two": 2}]}),
    ],
)
def test_safe_yaml_preserves_typed_values(tmp_path: Path, document: str, expected: Any) -> None:
    """Changing the safe resolver/constructor would change authoritative typed values."""
    path = tmp_path / "record.yaml"
    path.write_text(document, encoding="utf-8")

    assert read_yaml(path) == expected


@pytest.mark.parametrize(
    "document",
    [
        "reviewer: first\nreviewer: second\n",
        "nested:\n  reviewer: first\n  reviewer: second\n",
        "true: first\nTrue: second\n",
        "1: first\ntrue: second\n",
        "base: &base {reviewer: first}\nentry: {<<: *base}\n",
        "'<<': quoted-merge\n",
        "? [one, two]\n: value\n",
        "!!python/object/apply:builtins.eval ['1 + 1']\n",
        "item: [one, two\n",
        "---\none: 1\n---\ntwo: 2\n",
        "item: bad\x00value\n",
    ],
)
def test_yaml_rejects_ambiguous_unsafe_and_malformed_records(tmp_path: Path, document: str) -> None:
    """Unsafe loaders, permissive mappings or truncated input must never become records."""
    path = tmp_path / "record.yaml"
    path.write_text(document, encoding="utf-8")

    with pytest.raises(yaml.YAMLError):
        read_yaml(path)


def test_yaml_aliases_are_local_to_each_read(tmp_path: Path) -> None:
    """A process cache must not leak mutations into a later validation or file revision."""
    path = tmp_path / "record.yaml"
    path.write_text("first: &entry {choices: [yes]}\nsecond: *entry\n", encoding="utf-8")
    first = read_yaml(path)
    assert first == {"first": {"choices": [True]}, "second": {"choices": [True]}}
    assert first["first"] is first["second"]
    first["first"]["choices"].append(False)
    assert read_yaml(path) == {"first": {"choices": [True]}, "second": {"choices": [True]}}
    path.write_text("first: changed\n", encoding="utf-8")
    assert read_yaml(path) == {"first": "changed"}


def test_yaml_safe_fallback_without_libyaml(tmp_path: Path) -> None:
    """An environment without the optional extension keeps the same safe reader."""
    valid = tmp_path / "valid.yaml"
    valid.write_text("title: Café\nitems: [true, 2]\n", encoding="utf-8")
    duplicate = tmp_path / "duplicate.yaml"
    duplicate.write_text("key: first\nkey: second\n", encoding="utf-8")
    script = """
import json, sys
from pathlib import Path
sys.modules["yaml.cyaml"] = None
import yaml
from election_guide.serialization import read_yaml
print(json.dumps(read_yaml(Path(sys.argv[1])), ensure_ascii=False))
try:
    read_yaml(Path(sys.argv[2]))
except yaml.YAMLError:
    print("duplicate rejected")
else:
    raise AssertionError("unsafe duplicate accepted")
"""
    result = subprocess.run(
        [sys.executable, "-c", script, str(valid), str(duplicate)],
        check=True,
        capture_output=True,
        text=True,
    )
    lines = result.stdout.splitlines()
    assert json.loads(lines[0]) == {"title": "Café", "items": [True, 2]}
    assert lines[1:] == ["duplicate rejected"]
