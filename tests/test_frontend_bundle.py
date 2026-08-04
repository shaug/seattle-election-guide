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
    "race-entry.mjs": "RacePage",
    "shell-entry.mjs": "ShellPage",
    "sources-entry.mjs": "SourcesPage",
}


# esbuild writes bundled dependencies' licence notices into one block at the
# end of the output, introduced by exactly this line.
LICENCE_BANNER = "/*! Bundled license information:"


def _code(bundle: str) -> str:
    """The bundle's code, without the licence block esbuild appends to it."""
    return bundle.split(LICENCE_BANNER, 1)[0]


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
    # esbuild collects the licence notices of bundled dependencies after it —
    # a comment, not code, and one the page must keep carrying.
    assert _code(bundle).rstrip().endswith("})();")
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


@pytest.mark.parametrize(("entry", "global_name"), sorted(ENTRIES.items()))
def test_the_type_checker_config_does_not_reach_the_bundle(entry: str, global_name: str) -> None:
    """The repository tsconfig.json configures `tsc`, not the build.

    esbuild discovers a tsconfig by walking up from the entry module and honors
    several of its options, so the checker's settings could silently move the
    shipped bytes: `strict` alone prepends a `"use strict";` prologue, which
    would put a statement ahead of the single page-scope binding every template
    invokes. The bundler pins `--tsconfig-raw={}` to sever that; this fails if
    the flag is dropped, without depending on which options the checker happens
    to set today.
    """
    bundle = _fresh(entry, global_name)

    assert not bundle.lstrip().startswith(('"use strict"', "'use strict'"))
    assert bundle.startswith("var ")


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


def test_every_declared_dependency_is_an_exact_version() -> None:
    """Runtime and dev-time dependencies alike are exact-pinned.

    The bundler enforces this for esbuild, because its own output depends on
    the version. The rule is wider than that (docs/FRONTEND.md, Dependencies):
    a checker or formatter that drifts between machines fails the diff rather
    than the code, and lit-html ships in the page, so a range there would make
    the published bytes depend on when the build ran.
    """
    manifest = json.loads(PACKAGE_JSON.read_text(encoding="utf-8"))
    declared = {
        **manifest.get("dependencies", {}),
        **manifest.get("devDependencies", {}),
    }
    assert declared, "package.json declares no dependencies"

    ranged = sorted(
        name for name, version in declared.items() if not re.fullmatch(r"\d+\.\d+\.\d+", version)
    )
    assert not ranged, (
        f"{ranged} are not pinned to an exact version in package.json. Every version is "
        f"pinned exactly (rule: dependencies, docs/FRONTEND.md)."
    )


def test_the_runtime_dependency_ships_inline_and_fetches_nothing() -> None:
    """Runtime: lit-html, bundled at build time and readable in the page source.

    `test_each_entry_bundles_to_one_binding_that_boots_the_page` already proves
    no import survives. This adds the other half of the rule for the one
    runtime dependency: its code is actually in the page rather than reached
    for at run time.
    """
    bundle = bundle_entry("compare-entry.mjs", global_name="ComparePage")

    # "lit-html, and nothing else without amending this document" is the whole
    # rule, and asserting only that lit-html is present enforced half of it: a
    # second runtime dependency would have passed every check in this file.
    # Equality is what makes adding one a change to docs/FRONTEND.md, which is
    # what the rule says it must be (#245).
    declared = json.loads(PACKAGE_JSON.read_text(encoding="utf-8"))["dependencies"]
    assert set(declared) == {"lit-html"}, (
        f"package.json declares runtime dependencies {sorted(declared)}. The runtime is "
        f"lit-html and nothing else without amending the document in the same pull request "
        f"(rule: dependencies, docs/FRONTEND.md)."
    )
    assert "node_modules/lit-html/lit-html.js" in bundle, (
        "the Comparisons bundle does not carry lit-html's browser source. It is bundled at "
        "build time and shipped inline like our own modules (rule: dependencies, "
        "docs/FRONTEND.md). lit-html also publishes a `node` build, which binds a DOM stub "
        "when it loads; a page must never be built from that one."
    )
    assert "node_modules/lit-html/node/" not in bundle
    assert "fetch(" not in bundle
    assert "import(" not in bundle


def test_an_unknown_entry_is_a_bundler_error_rather_than_an_esbuild_message() -> None:
    bundle_entry.cache_clear()
    with pytest.raises(BundleError, match="no client entry module"):
        bundle_entry("nonexistent-entry.mjs", global_name="Nope")
