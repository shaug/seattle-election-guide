"""The client bundle contract (docs/FRONTEND.md, Modules and Dependencies).

Each page has one client entry module; the renderer bundles that entry's
import graph with esbuild and inlines the result, so published pages stay
self-contained single files. Determinism is the property that makes the
reproducible-release check in CI meaningful, and it is asserted here directly
rather than inferred from two whole builds agreeing.
"""

from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path

import pytest

from election_guide.rendering.bundler import (
    ESBUILD,
    PACKAGE_JSON,
    BundleError,
    bundle_entry,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
TEMPLATE_DIR = REPO_ROOT / "src" / "election_guide" / "rendering" / "templates"

# Every page's entry and the single binding its bundle leaves in page scope.
# The renderer and hosting/pages.py name these same pairs; a page added without
# an entry has nowhere for its client code to live.
ENTRIES = {
    "compare-entry.mjs": "ComparePage",
    "guide-entry.mjs": "GuidePage",
    "shell-entry.mjs": "ShellPage",
    "sources-entry.mjs": "SourcesPage",
}


def _fresh(entry: str, global_name: str) -> str:
    """Bundle without the render-time cache, so esbuild actually runs."""
    bundle_entry.cache_clear()
    return bundle_entry(entry, global_name=global_name)


@pytest.mark.parametrize(("entry", "global_name"), sorted(ENTRIES.items()))
def test_each_entry_bundles_to_one_binding_that_boots_the_page(
    entry: str, global_name: str
) -> None:
    bundle = _fresh(entry, global_name)

    assert bundle.startswith(f"var {global_name} = (() => {{")
    assert "boot: () => boot" in bundle
    # An IIFE, so no module's top-level names reach page scope: the collision
    # class the concatenated pages carried cannot recur (docs/FRONTEND.md).
    assert bundle.rstrip().endswith("})();")
    # Self-contained: no statement or specifier survives that would make the
    # published page fetch anything at runtime.
    assert not re.search(r"^\s*(?:import|export)[\s({]", bundle, re.MULTILINE)
    assert not re.search(r"""['"][^'"\n]*\.mjs['"]""", bundle)


@pytest.mark.parametrize(("entry", "global_name"), sorted(ENTRIES.items()))
def test_bundling_the_same_entry_twice_produces_the_same_bytes(
    entry: str, global_name: str
) -> None:
    """The release build renders twice and compares; this is why that holds."""
    assert _fresh(entry, global_name) == _fresh(entry, global_name)


def test_every_entry_module_on_disk_is_covered_here() -> None:
    """A page added with an entry but no bundle test would go unchecked."""
    on_disk = sorted(path.name for path in TEMPLATE_DIR.glob("*-entry.mjs"))
    assert on_disk == sorted(ENTRIES)


def test_the_installed_esbuild_is_the_exact_version_package_json_pins() -> None:
    """Dev-time dependencies are exact-pinned (docs/FRONTEND.md, Dependencies).

    Bundle output is only reproducible for one version, so `bundle_entry`
    refuses both a manifest range and an installed binary that disagrees with
    the pin. That rule lives in the bundler alone; bundling successfully is
    what proves it held, and the version is named here only so a failure reads
    as "run `npm ci`" rather than as a mystery.
    """
    pinned = json.loads(PACKAGE_JSON.read_text(encoding="utf-8"))["devDependencies"]["esbuild"]
    installed = subprocess.run(
        [str(ESBUILD), "--version"], capture_output=True, text=True, encoding="utf-8", check=True
    ).stdout.strip()

    assert installed == pinned, f"esbuild {installed} is installed, not {pinned}: run `npm ci`"
    assert _fresh("shell-entry.mjs", "ShellPage")


def test_an_unknown_entry_is_a_bundler_error_rather_than_an_esbuild_message() -> None:
    bundle_entry.cache_clear()
    with pytest.raises(BundleError, match="no client entry module"):
        bundle_entry("nonexistent-entry.mjs", global_name="Nope")
