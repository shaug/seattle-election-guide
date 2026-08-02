"""Enforcement suite for the front-end code guidelines (docs/FRONTEND.md).

Three of the document's rules are checkable against the Python side of the
build and are checked here. Each one reads its grandfathered baseline from
`tests/frontend_ratchets.json` so that a migration ticket shrinks the recorded
value in the same pull request that removes the debt (AGENTS.md: ratchet checks
only move one way).

The Node half of the suite lives in `tests/js/module-isolation.test.mjs` and
`tests/js/support/module-guards.mjs`.
"""

from __future__ import annotations

import ast
import json
import re
from collections.abc import Iterator
from pathlib import Path
from typing import TypedDict, cast

REPO_ROOT = Path(__file__).resolve().parents[1]
SOURCE_ROOT = REPO_ROOT / "src"
PACKAGE_ROOT = SOURCE_ROOT / "election_guide"
TEMPLATE_DIR = PACKAGE_ROOT / "rendering" / "templates"
MANIFEST_PATH = Path(__file__).resolve().parent / "frontend_ratchets.json"

DOCUMENT = "docs/FRONTEND.md"

# A line whose entire content is a Jinja module-injection placeholder. These
# lines carry no authored logic — they inline a `.mjs` module verbatim — so
# they are excluded from the inline-script line count and registered by name
# instead.
PLACEHOLDER_LINE = re.compile(r"^\s*\{\{\s*([A-Za-z_][A-Za-z0-9_]*)\s*\|\s*safe\s*\}\}\s*$")

SCRIPT_ELEMENT = re.compile(r"<script\b([^>]*)>(.*?)</script>", re.DOTALL)

# Payload elements are the data contract, not behavior (docs/FRONTEND.md, "The
# data contract"), so they are outside the inline-script ceiling. The
# attribute-name boundary matters: without it a `data-type="application/json"`
# on an executable module script would exempt it from the whole metric.
PAYLOAD_TYPE = re.compile(r"""(?:^|\s)type\s*=\s*["']application/json["']""")

DOCTYPE_PREFIX = "<!doctype"


class FstringDocument(TypedDict):
    module: str
    function: str
    reason: str


class IsolationExemption(TypedDict):
    module: str
    error: str
    reason: str


class Ratchets(TypedDict):
    inline_script_ceilings: dict[str, int]
    module_injection_placeholders: dict[str, list[str]]
    fstring_documents: list[FstringDocument]
    module_isolation_exemptions: list[IsolationExemption]


def read_ratchets() -> Ratchets:
    return cast(Ratchets, json.loads(MANIFEST_PATH.read_text(encoding="utf-8")))


class InlineScript(TypedDict):
    """One template's measurement under the inline-script metric."""

    lines: int
    placeholders: list[str]


def measure_inline_script(source: str) -> InlineScript:
    """Measure a Jinja template's inline script.

    The metric, stated once here so later tickets lower ceilings against the
    same definition: for every `<script>` element in the template *source* that
    is not a `type="application/json"` payload, take its content — everything
    between the tags, whether or not it shares a line with them — and count its
    lines, less the lines that are nothing but a `{{ name | safe }}`
    module-injection placeholder. A blank first or last line is the ordinary
    consequence of writing the tags on their own lines and does not count.
    Placeholder names are reported separately so that adding an injection point
    is itself a checked change rather than an unmeasured way to inject
    Python-built script.
    """

    counted = 0
    placeholders: list[str] = []
    for element in SCRIPT_ELEMENT.finditer(source):
        attributes = element.group(1)
        if PAYLOAD_TYPE.search(attributes):
            continue
        content = element.group(2).splitlines()
        if content and not content[0].strip():
            content = content[1:]
        if content and not content[-1].strip():
            content = content[:-1]
        for line in content:
            placeholder = PLACEHOLDER_LINE.match(line)
            if placeholder:
                placeholders.append(placeholder.group(1))
            else:
                counted += 1
    return {"lines": counted, "placeholders": sorted(placeholders)}


def test_the_metric_sees_script_that_shares_a_line_with_its_tags() -> None:
    """A ceiling means nothing if an ordinary authoring form escapes the count."""

    assert measure_inline_script("<script>evil();</script>")["lines"] == 1
    assert measure_inline_script("<script>\n  evil();\n</script>")["lines"] == 1
    assert measure_inline_script("<script>a();\n  b();</script>")["lines"] == 2
    assert measure_inline_script('<script type="application/json">{"a": 1}</script>')["lines"] == 0
    assert (
        measure_inline_script('<script type="module" data-type="application/json">a();</script>')[
            "lines"
        ]
        == 1
    )
    assert measure_inline_script("<script>{{ entry_script | safe }}\n  boot();\n</script>") == {
        "lines": 1,
        "placeholders": ["entry_script"],
    }


def test_inline_script_stays_within_its_recorded_ceiling() -> None:
    """docs/FRONTEND.md, Modules: templates carry no logic in `<script>`."""

    ceilings = read_ratchets()["inline_script_ceilings"]
    templates = sorted(TEMPLATE_DIR.glob("*.j2"))
    assert templates, "expected Jinja templates under rendering/templates"

    unknown = sorted(set(ceilings) - {template.name for template in templates})
    assert not unknown, (
        f"tests/frontend_ratchets.json records an inline-script ceiling for {unknown}, "
        f"which no longer exists. Delete the entry "
        f"(rule: templates carry no logic in <script>, {DOCUMENT})."
    )

    for template in templates:
        measured = measure_inline_script(template.read_text(encoding="utf-8"))["lines"]
        ceiling = ceilings.get(template.name, 0)
        assert measured <= ceiling, (
            f"the inline-script measurement for {template.name} is {measured}, above its recorded "
            f"ceiling of {ceiling}. Behavior belongs in a module, where it can be imported "
            f"and tested; a ceiling may never grow (rule: templates carry no logic in "
            f"<script>, {DOCUMENT}; AGENTS.md: ratchet checks only move one way). "
            f"A newly scripted template is registered in tests/frontend_ratchets.json."
        )
        assert measured == ceiling, (
            f"the inline-script measurement for {template.name} is {measured}, below the {ceiling} "
            f"recorded in tests/frontend_ratchets.json. Lower the recorded ceiling "
            f"in this pull request (rule: ceilings only decrease, {DOCUMENT} § Adoption)."
        )


def test_module_injection_placeholders_are_registered() -> None:
    """docs/FRONTEND.md, Modules: inline script is bundled text, not logic."""

    registered = read_ratchets()["module_injection_placeholders"]
    templates = sorted(TEMPLATE_DIR.glob("*.j2"))

    unknown = sorted(set(registered) - {template.name for template in templates})
    assert not unknown, (
        f"tests/frontend_ratchets.json registers injection placeholders for {unknown}, "
        f"which no longer exists. Delete the entry ({DOCUMENT})."
    )

    for template in templates:
        found = measure_inline_script(template.read_text(encoding="utf-8"))["placeholders"]
        expected = sorted(registered.get(template.name, []))
        assert found == expected, (
            f"{template.name} injects {found} but tests/frontend_ratchets.json registers "
            f"{expected}. Placeholder lines are excluded from the inline-script ceiling, so "
            f"every injection point must be recorded for the ceiling to mean anything "
            f"(rule: templates carry no logic in <script>, {DOCUMENT})."
        )


def _own_nodes(function: ast.FunctionDef | ast.AsyncFunctionDef) -> Iterator[ast.AST]:
    """Every node inside this function, but not inside a function nested in it."""

    stack: list[ast.AST] = list(ast.iter_child_nodes(function))
    while stack:
        node = stack.pop()
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef | ast.Lambda):
            continue
        yield node
        stack.extend(ast.iter_child_nodes(node))


def document_functions(source: str) -> list[str]:
    """The functions in one module that build an HTML document from a Python string.

    The detection mechanism, stated explicitly so this check is as
    well-specified as the inline-script metric: parse the module with `ast` and
    report every function whose own body — not a function nested inside it —
    holds a string literal beginning `<!doctype` (case-insensitively, after
    leading whitespace). An f-string's literal chunks are such literals, so the
    house form `return f\"\"\"<!doctype html>…\"\"\"` and the equally ordinary
    `page = f\"\"\"<!doctype html>…\"\"\"; return page` are both reported. A
    document assembled from a doctype held somewhere else entirely is not.
    """

    found: list[str] = []
    for node in ast.walk(ast.parse(source)):
        if not isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
            continue
        for child in _own_nodes(node):
            if (
                isinstance(child, ast.Constant)
                and isinstance(child.value, str)
                and child.value.lstrip().lower().startswith(DOCTYPE_PREFIX)
            ):
                found.append(node.name)
                break
    return found


def find_fstring_documents() -> list[tuple[str, str]]:
    """Every function under `src/` that builds a Python-string HTML document."""

    return sorted(
        (module.relative_to(SOURCE_ROOT).as_posix(), name)
        for module in PACKAGE_ROOT.rglob("*.py")
        for name in document_functions(module.read_text(encoding="utf-8"))
    )


def test_the_document_scan_sees_a_document_that_is_named_before_it_is_returned() -> None:
    """The allowlist means nothing if an ordinary authoring form escapes the scan."""

    returned = 'def page() -> str:\n    return f"""<!doctype html>\n<html></html>"""\n'
    named = (
        'def page() -> str:\n    body = f"""<!doctype html>\n<html></html>"""\n    return body\n'
    )
    uppercase = 'def page() -> str:\n    return "<!DOCTYPE html><html></html>"\n'
    fragment = 'def part() -> str:\n    return "<p>hello</p>"\n'
    nested = (
        "def outer() -> str:\n"
        "    def inner() -> str:\n"
        '        return "<!doctype html>"\n'
        "    return inner()\n"
    )

    assert document_functions(returned) == ["page"]
    assert document_functions(named) == ["page"]
    assert document_functions(uppercase) == ["page"]
    assert document_functions(fragment) == []
    assert document_functions(nested) == ["inner"]


def test_python_string_documents_stay_on_the_shrinking_allowlist() -> None:
    """docs/FRONTEND.md, Server-side templates: full documents are Jinja templates."""

    allowed = sorted(
        (entry["module"], entry["function"]) for entry in read_ratchets()["fstring_documents"]
    )
    found = find_fstring_documents()

    added = [entry for entry in found if entry not in allowed]
    assert not added, (
        f"{added} build an HTML document from a Python string. Full HTML documents are "
        f"Jinja templates extending the shared layout, so autoescaping is the default rather "
        f"than a per-call discipline (rule: server-side templates, {DOCUMENT}). The existing "
        f"pages are grandfathered on a shrinking allowlist; new ones are not."
    )

    removed = [entry for entry in allowed if entry not in found]
    assert not removed, (
        f"tests/frontend_ratchets.json still allows {removed}, which is no longer a "
        f"Python-string document. Delete the entry in this pull request "
        f"(rule: the allowlist only shrinks, {DOCUMENT} § Adoption)."
    )
