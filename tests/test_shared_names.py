"""The shared-name contract (docs/FRONTEND.md § Shared names).

A name that template, stylesheet, client, and audit code all spell is spelled
once here and checked everywhere. `tests/shared_names.json` is that single
declaration: for every shared name it records the exact set of *surface kinds*
that restate it. This module derives the same map from the tree and holds the
two to equality in both directions, so a rename that reaches three surfaces and
misses the fourth fails `make check` rather than shipping.

**Why a check and not a generator.** The proposal this ticket started from was a
build step emitting a client module, CSS custom properties, and a Jinja context.
The stylesheet is what defeats it: an attribute or class name is *selector
syntax*, and a custom property holds a value — `[var(--x)]` is not a selector,
and `@media (max-width: var(--bp))` is not a query. A stylesheet therefore
cannot consume a generated name, and it is one of the three surfaces the rule
names. Substituting names into the CSS during the build is not open either: each
page's stylesheet is concatenated, deliberately, so that "the shipped bytes are
the authored bytes" (docs/FRONTEND.md, Modules). Any generator would leave the
one surface a rename most often misses still restating every literal. So the
declaration is enforced by reading every surface rather than by emitting into
some of them, and no name gains a second generator.

**The surfaces.** `template` is the Jinja templates, `stylesheet` the page
stylesheets, `client` the `.mjs` modules, `python` everything under
`src/election_guide` — which is where `rendering/browser.py` holds the CDP audit
probes — and `test` the Python and Node tests. The committed fixtures under
`tests/js/fixtures/` are excluded: they are rendered output, not an authored
restatement, and counting them would put every name on the `test` surface and
make the whole check vacuous.

**What is in scope, and what is not.** Three categories, matching the rule:

* every `data-*` attribute name that more than one surface spells;
* every class name that reaches *executable* code — a `.mjs` module or a Python
  probe string — alongside the stylesheet or template that also spells it; and
* every `@media` width breakpoint that executable code restates.

Class names shared only between a template and a stylesheet are deliberately
out. That pair is every class in the codebase, and a miss there is loud: the
element renders unstyled. The pairs this check covers are the quiet ones. A
class name a Chrome probe spells is the sharpest case and the reason issue #237
widened past "root state classes": `rendering/browser.py` selects
`.screen-race-context` in four probe strings, and a rename that misses one makes
the probe match zero elements and *report success* — a false green, not a
failing test.

Grade strings are not here. They have a Python origin —
`scoring/models.py`'s `Grade` — and reach the client through the payload
generator that issue #236 landed, which
`tests/test_client_payload_types.py::test_the_grade_strings_have_exactly_one_generator`
holds. Declaring them again would be the duplicate identifier space
docs/FRONTEND.md § The data contract calls a defect, so this module checks that
they stay absent instead.

**The limits of the metric, stated so it is not mistaken for more.**

*Surfaces are recorded by kind, not by file.* A rename that misses a second file
of the *same* kind does not move the declaration and is not caught here; within
one language that file's own checker owns it — `tsc --checkJs` and the module
tests for the client, `pyright` for Python. What this check owns is the boundary
between languages, which is the boundary no other checker can see.

*The scan is textual, so prose counts as spelling a name.* A comment that
mentions `.visually-hidden` puts its file's surface on the declaration just as a
selector would. That is deliberate: a probe string and a docstring are both
string literals, telling them apart would need a Python-only parsing path the
other four surfaces do not have, and the conservative reading has the better
failure mode — a real use is never missed, and a rename leaves the prose about
it accurate. What it costs is that a comment can be the reason a surface is
listed. No entry in the manifest is present *only* for that reason.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import TypedDict, cast

REPO_ROOT = Path(__file__).resolve().parents[1]
PACKAGE_ROOT = REPO_ROOT / "src" / "election_guide"
TEMPLATE_DIR = PACKAGE_ROOT / "rendering" / "templates"
TESTS_ROOT = Path(__file__).resolve().parent
FIXTURE_DIR = TESTS_ROOT / "js" / "fixtures"
MANIFEST_PATH = TESTS_ROOT / "shared_names.json"

DOCUMENT = "docs/FRONTEND.md"
RULE = f"rule: names shared across template, JS, and CSS are declared once, {DOCUMENT}"

# Surface kinds, in the order a reader meets them: what the server writes, how
# it is styled, what the client runs, what Python renders and probes, and what
# the tests assert.
SURFACE_ORDER = ("template", "stylesheet", "client", "python", "test")


class SharedNames(TypedDict):
    data_attributes: dict[str, list[str]]
    class_names: dict[str, list[str]]
    breakpoints: dict[str, list[str]]


def read_manifest() -> SharedNames:
    return cast(SharedNames, json.loads(MANIFEST_PATH.read_text(encoding="utf-8")))


def _surface_files() -> dict[str, list[Path]]:
    return {
        "template": sorted(TEMPLATE_DIR.glob("*.j2")),
        "stylesheet": sorted(TEMPLATE_DIR.glob("*.css")),
        "client": sorted(TEMPLATE_DIR.glob("*.mjs")),
        "python": sorted(PACKAGE_ROOT.rglob("*.py")),
        "test": sorted(
            path
            for path in [*TESTS_ROOT.rglob("*.py"), *TESTS_ROOT.rglob("*.mjs")]
            if FIXTURE_DIR not in path.parents and path != Path(__file__).resolve()
        ),
    }


def _read_surfaces() -> dict[str, list[str]]:
    return {
        kind: [path.read_text(encoding="utf-8") for path in paths]
        for kind, paths in _surface_files().items()
    }


CSS_COMMENT = re.compile(r"/\*.*?\*/", re.DOTALL)

DATA_ATTRIBUTE = re.compile(r"data-[a-z][a-z0-9-]*")

# A class selector in a stylesheet: a dot-prefixed kebab-case name, ended by
# something that can follow a selector. The kebab requirement is what keeps
# `guide.css` and `FRONTEND.md` — file names in comments read as selectors —
# out of the vocabulary; every class this codebase authors is hyphenated.
CSS_CLASS_SELECTOR = re.compile(r"\.(-?[a-z][a-z0-9]*(?:-[a-z0-9]+)+)(?![a-zA-Z0-9_-])")

CLASS_LIST_OPERAND = re.compile(
    r"classList\.(?:add|remove|toggle|contains|replace)\(\s*['\"]([a-z][a-z0-9-]*)['\"]"
)

MEDIA_BREAKPOINT = re.compile(r"@media[^{]*?\(\s*(?:min|max)-width:\s*(\d+)px")

# Outside a stylesheet a bare integer is ambiguous — a vote count is not a
# breakpoint — so a restatement counts only where the same line also names a
# width. That is exactly how `rendering/browser.py` restates one:
# `window.innerWidth<=720?2:window.innerWidth<=1050?3:4`.
WIDTH_CONTEXT = re.compile(r"innerWidth|outerWidth|clientWidth|matchMedia|min-width|max-width")


# A name followed by one of these is a file, not a name in use: the modules are
# named after what they render, so `election-day.mjs` in a comment would
# otherwise read as a restatement of the `.election-day` class.
ASSET_SUFFIX = r"(?!\.(?:mjs|js|ts|css|j2|py|md|html|json|yaml|yml)\b)"


def spelled_as_word(name: str) -> re.Pattern[str]:
    """Match `name` where it is not part of a longer name or of a file name.

    The boundary excludes `-` as well as word characters, so `election-day` does
    not match inside `data-election-day`: those are two declared names and the
    check must not conflate them.
    """
    return re.compile(rf"(?<![a-zA-Z0-9_-]){re.escape(name)}{ASSET_SUFFIX}(?![a-zA-Z0-9_-])")


def surfaces_spelling(pattern: re.Pattern[str], surfaces: dict[str, list[str]]) -> list[str]:
    return [
        kind
        for kind in SURFACE_ORDER
        if any(pattern.search(text) for text in surfaces.get(kind, []))
    ]


def data_attribute_survey(surfaces: dict[str, list[str]]) -> dict[str, list[str]]:
    """Every `data-*` name more than one surface spells."""
    candidates: set[str] = set()
    for texts in surfaces.values():
        for text in texts:
            candidates |= set(DATA_ATTRIBUTE.findall(text))

    survey: dict[str, list[str]] = {}
    for name in sorted(candidates):
        found = surfaces_spelling(spelled_as_word(name), surfaces)
        if len(found) >= 2:
            survey[name] = found
    return survey


def class_vocabulary(surfaces: dict[str, list[str]]) -> set[str]:
    """The class names this codebase authors.

    Discovered from real selector positions in the stylesheets — comments
    stripped first, so a file name in prose is not read as a class — plus the
    names client wiring toggles, which is how a state class with no selector of
    its own would still be found.
    """
    names: set[str] = set()
    for text in surfaces.get("stylesheet", []):
        names |= set(CSS_CLASS_SELECTOR.findall(CSS_COMMENT.sub(" ", text)))
    for text in surfaces.get("client", []):
        names |= set(CLASS_LIST_OPERAND.findall(text))
    return names


def class_name_survey(surfaces: dict[str, list[str]]) -> dict[str, list[str]]:
    """Every authored class name that executable code also spells."""
    survey: dict[str, list[str]] = {}
    for name in sorted(class_vocabulary(surfaces)):
        found = surfaces_spelling(spelled_as_word(name), surfaces)
        if "client" in found or "python" in found:
            survey[name] = found
    return survey


def breakpoint_survey(surfaces: dict[str, list[str]]) -> dict[str, list[str]]:
    """Every `@media` width breakpoint that executable code or a test restates."""
    thresholds: set[str] = set()
    for text in surfaces.get("stylesheet", []):
        thresholds |= set(MEDIA_BREAKPOINT.findall(CSS_COMMENT.sub(" ", text)))

    survey: dict[str, list[str]] = {}
    for threshold in sorted(thresholds, key=int):
        number = re.compile(rf"(?<![\d.]){threshold}(?![\d.])")
        found = ["stylesheet"]
        found += [
            kind
            for kind in SURFACE_ORDER
            if kind != "stylesheet"
            and any(
                number.search(line) and WIDTH_CONTEXT.search(line)
                for text in surfaces.get(kind, [])
                for line in text.splitlines()
            )
        ]
        if len(found) >= 2:
            survey[threshold] = found
    return survey


def survey_tree() -> SharedNames:
    """The shared-name map the tree actually holds, derived rather than listed."""
    surfaces = _read_surfaces()
    return {
        "data_attributes": data_attribute_survey(surfaces),
        "class_names": class_name_survey(surfaces),
        "breakpoints": breakpoint_survey(surfaces),
    }


# --------------------------------------------------------------------------
# The scanners, checked against hand-built sources.
#
# The declaration means nothing if an ordinary authoring form escapes the scan,
# so each scanner is exercised the way `test_frontend_ratchets.py` exercises the
# inline-script metric: on a source small enough to read.
# --------------------------------------------------------------------------


def test_the_data_attribute_scan_sees_every_authoring_form() -> None:
    surfaces = {
        "template": ['<div data-lens-only class="x">'],
        "stylesheet": ["[data-lens-only] { display: none; }"],
        "client": ["el.querySelector('[data-lens-only]')"],
        "python": ["\"document.querySelector('[data-probe-only]')\""],
        "test": [""],
    }
    survey = data_attribute_survey(surfaces)

    assert survey["data-lens-only"] == ["template", "stylesheet", "client"]
    # One surface is not a shared name.
    assert "data-probe-only" not in survey


def test_a_data_attribute_is_not_confused_with_a_longer_one() -> None:
    surfaces = {
        "template": ["<b data-election-day-short>"],
        "client": ["dataset.electionDay", "'[data-election-day]'"],
        "stylesheet": [""],
        "python": [""],
        "test": [""],
    }
    survey = data_attribute_survey(surfaces)

    # `data-election-day` must not be found inside `data-election-day-short`:
    # they are two names, and conflating them would hide a rename of either.
    assert survey.get("data-election-day") is None
    assert survey.get("data-election-day-short") is None


def test_a_name_is_not_found_in_a_file_named_after_it() -> None:
    """Modules are named for what they render, so the two collide in prose.

    `rendering/shell.py` mentions `election-day.mjs`; the class `.election-day`
    is a different thing, and recording Python as a surface that spells it would
    put a fact in the contract that renaming the class could not honour.
    """
    surfaces = {
        "stylesheet": [".election-day { display: flex; }"],
        "client": ["root.classList.toggle('election-day', soon);"],
        "python": ["# `election-day.mjs` escalates the banner as the date nears."],
        "template": [""],
        "test": [""],
    }

    assert class_name_survey(surfaces) == {"election-day": ["stylesheet", "client"]}


def test_the_class_vocabulary_ignores_file_names_in_comments() -> None:
    surfaces = {
        "stylesheet": [
            "/* base.css and docs/FRONTEND.md govern this. */\n"
            ".screen-race-context { display: grid; }\n"
            "html.compact-ballot-mode .race-grid { gap: 0; }\n"
        ],
        "client": ["root.classList.toggle('lens-personalized', on);"],
        "template": [""],
        "python": [""],
        "test": [""],
    }

    assert class_vocabulary(surfaces) == {
        "screen-race-context",
        "compact-ballot-mode",
        "race-grid",
        "lens-personalized",
    }


def test_the_class_scan_reports_only_names_executable_code_spells() -> None:
    surfaces = {
        "stylesheet": [".screen-race-context { display: grid; }\n.quiet-only { color: red; }\n"],
        "template": ['<div class="screen-race-context"></div><p class="quiet-only">'],
        # The probe form the rule exists for: a selector inside a CDP string.
        "python": ["\"[...document.querySelectorAll('.screen-race-context')]\""],
        "client": [""],
        "test": [""],
    }
    survey = class_name_survey(surfaces)

    assert survey == {"screen-race-context": ["template", "stylesheet", "python"]}
    # Template + stylesheet alone is every class in the codebase, and a miss
    # there renders unstyled rather than silently passing.
    assert "quiet-only" not in survey


def test_the_breakpoint_scan_needs_a_width_context_outside_the_stylesheet() -> None:
    surfaces = {
        "stylesheet": ["@media (max-width: 720px) { .race-grid { gap: 0; } }"],
        "python": ['"const columns=window.innerWidth<=720?2:4;"'],
        "template": [""],
        "client": [""],
        "test": [""],
    }
    assert breakpoint_survey(surfaces) == {"720": ["stylesheet", "python"]}

    # A bare 720 that is not about width is a coincidence, not a restatement.
    coincidence = dict(surfaces, python=["total_votes = 720"])
    assert breakpoint_survey(coincidence) == {}


# --------------------------------------------------------------------------
# The contract itself.
# --------------------------------------------------------------------------


def _assert_declared(declared: dict[str, list[str]], found: dict[str, list[str]]) -> None:
    undeclared = {name: kinds for name, kinds in found.items() if name not in declared}
    assert not undeclared, (
        f"{sorted(undeclared)} are spelled on more than one surface but are not declared in "
        f"tests/shared_names.json. A shared name is declared once and consumed, not restated "
        f"per surface; add it with the surfaces that spell it: {undeclared} ({RULE})."
    )

    stale = sorted(set(declared) - set(found))
    assert not stale, (
        f"tests/shared_names.json declares {stale}, which no surface pair spells any more. "
        f"Delete the entry in this pull request ({RULE})."
    )

    drifted = {
        name: {"declared": declared[name], "found": kinds}
        for name, kinds in found.items()
        if name in declared and declared[name] != kinds
    }
    assert not drifted, (
        f"the surfaces spelling {sorted(drifted)} are not the ones tests/shared_names.json "
        f"declares: {drifted}. A name that gained or lost a surface was renamed on some of "
        f"them and not others, or is newly shared; reconcile every surface, then the "
        f"declaration ({RULE})."
    )


def test_shared_data_attributes_are_declared_once() -> None:
    """docs/FRONTEND.md, Shared names: `data-*` attributes are declared once."""
    _assert_declared(read_manifest()["data_attributes"], survey_tree()["data_attributes"])


def test_shared_class_names_are_declared_once() -> None:
    """docs/FRONTEND.md, Shared names: a class name executable code spells is declared."""
    _assert_declared(read_manifest()["class_names"], survey_tree()["class_names"])


def test_shared_breakpoints_are_declared_once() -> None:
    """docs/FRONTEND.md, Shared names: breakpoints are declared once."""
    _assert_declared(read_manifest()["breakpoints"], survey_tree()["breakpoints"])


def declared_names() -> dict[str, list[str]]:
    """Every declaration, whatever category it is filed under."""
    manifest = read_manifest()
    return {
        **manifest["data_attributes"],
        **manifest["class_names"],
        **manifest["breakpoints"],
    }


def test_the_manifest_declares_no_surface_that_is_not_a_surface() -> None:
    """A typo in a surface name would silently weaken every comparison above."""
    for name, kinds in declared_names().items():
        unknown = sorted(set(kinds) - set(SURFACE_ORDER))
        assert not unknown, (
            f"tests/shared_names.json records surface {unknown} for {name!r}, which is not "
            f"one of {list(SURFACE_ORDER)} ({RULE})."
        )
        assert kinds == [kind for kind in SURFACE_ORDER if kind in kinds], (
            f"the surfaces for {name!r} are recorded out of order; keep them in "
            f"{list(SURFACE_ORDER)} order so the file diffs cleanly ({RULE})."
        )
        assert len(kinds) >= 2, (
            f"{name!r} is declared with a single surface, so it is not a shared name. "
            f"Delete the entry ({RULE})."
        )


def test_no_value_with_a_python_origin_is_declared_here() -> None:
    """docs/FRONTEND.md, The data contract: one identifier space, one generator.

    The grade strings reach the client through the payload generator issue #236
    landed. Declaring them here as well would give one vocabulary two owners,
    which is the defect the contract names — so the boundary is checked, not
    just written down.
    """
    from election_guide.scoring.models import Grade

    grades = set(Grade.__args__)  # pyright: ignore[reportAttributeAccessIssue]
    collisions = sorted(grades & set(declared_names()))
    assert not collisions, (
        f"{collisions} have a Python origin (`scoring/models.py`'s `Grade`) and already reach "
        f"the client through the payload generator. A second declaration here would give one "
        f"vocabulary two generators (rule: one identifier space, {DOCUMENT} § The data "
        f"contract)."
    )
