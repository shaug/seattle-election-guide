"""Bundle a page's client entry module with esbuild (docs/FRONTEND.md, Modules).

The Python/esbuild seam is an invocation from the renderer, not a separate
prebuild step: the renderer already owns "read the client module, inline it
into the page", and bundling makes that one call resolve a real import graph
instead of a hand-maintained paste order. Nothing new has to run before
`election-guide release build` or `pytest`, and no generated bundle lives in
the tree to go stale. The cost is that Node and the locked `node_modules` are
prerequisites for rendering, not just for `make check-js` (CONTRIBUTING.md).

Determinism (ARCHITECTURE.md): esbuild is exact-pinned in `package.json`, the
version on disk is verified against that pin before the first bundle, the
bundler runs with the template directory as its working directory so the file
banners esbuild writes carry no absolute path, and output is never minified —
every shipped byte stays readable in the page source.
"""

from __future__ import annotations

import json
import subprocess
from functools import cache
from pathlib import Path

# Every template asset — Jinja documents, stylesheets, client modules — lives
# here. Declared in this module because it is the leaf of `rendering`: the
# renderer imports it back rather than restating the path.
TEMPLATE_DIR = Path(__file__).parent / "templates"
REPO_ROOT = Path(__file__).resolve().parents[3]
ESBUILD = REPO_ROOT / "node_modules" / ".bin" / "esbuild"
PACKAGE_JSON = REPO_ROOT / "package.json"

# es2022 rather than esnext: an explicit floor keeps the output stable across
# esbuild upgrades, and it is above everything the modules use, so nothing is
# lowered and the bundle reads like its sources.
TARGET = "es2022"


class BundleError(RuntimeError):
    """esbuild is unavailable, mispinned, or failed on a client entry module."""


@cache
def _pinned_esbuild_version() -> str:
    """The exact version `package.json` pins, which is what may be run."""
    manifest = json.loads(PACKAGE_JSON.read_text(encoding="utf-8"))
    pinned = manifest.get("devDependencies", {}).get("esbuild")
    if not isinstance(pinned, str) or not pinned[:1].isdigit():
        raise BundleError(
            f"{PACKAGE_JSON} must pin esbuild to an exact version; found {pinned!r}. "
            "Dev-time dependencies are exact-pinned (docs/FRONTEND.md, Dependencies)."
        )
    return pinned


@cache
def _verified_esbuild() -> Path:
    """The esbuild binary, proven to be the pinned version before it is used."""
    pinned = _pinned_esbuild_version()
    if not ESBUILD.exists():
        raise BundleError(
            f"esbuild is not installed at {ESBUILD}. Client entry modules are bundled at "
            "render time, so rendering needs the locked Node toolchain: run `npm ci` "
            "(CONTRIBUTING.md; docs/FRONTEND.md, Dependencies)."
        )
    found = subprocess.run(
        [str(ESBUILD), "--version"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    if found != pinned:
        raise BundleError(
            f"{ESBUILD} is version {found}, but package.json pins {pinned}. Bundle output is "
            "only reproducible for the pinned version: run `npm ci` (docs/FRONTEND.md, "
            "Dependencies)."
        )
    return ESBUILD


@cache
def bundle_entry(entry_module: str, *, global_name: str) -> str:
    """Bundle one page's client entry into the text its template inlines.

    `global_name` is the single binding the bundle leaves in the page's module
    scope; the template invokes `<global_name>.boot()` and, until issue #239
    moves the guide's and sources page's remaining inline glue into modules,
    destructures that entry's `glue` object off the same binding.
    """
    entry_path = TEMPLATE_DIR / entry_module
    if not entry_path.exists():
        raise BundleError(f"no client entry module at {entry_path}")
    command = [
        str(_verified_esbuild()),
        # Relative to the working directory below, so the module banners
        # esbuild writes into the bundle are checkout-independent.
        f"./{entry_module}",
        "--bundle",
        # One binding in the page's module scope instead of every module's
        # top-level names: the collision class docs/FRONTEND.md describes
        # cannot occur, because no module's names reach page scope at all.
        "--format=iife",
        f"--global-name={global_name}",
        f"--target={TARGET}",
        # Ship the source characters rather than \u escapes: the page stays
        # readable, as it was under concatenation.
        "--charset=utf8",
    ]
    result = subprocess.run(
        command,
        capture_output=True,
        text=True,
        cwd=TEMPLATE_DIR,
    )
    if result.returncode != 0:
        raise BundleError(f"esbuild failed on {entry_module}:\n{result.stderr.strip()}")
    return result.stdout
