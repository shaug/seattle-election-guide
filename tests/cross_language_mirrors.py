"""Derive the cross-language mirrors from the tree, rather than listing them.

docs/FRONTEND.md § Cross-language mirrors requires a generated parity fixture
for any logic implemented in both Python and JavaScript. That rule needs an
inventory to apply to, and a hand-written inventory is the wrong artifact: the
mirror this project actually shipped wrong was the one whose comment claimed it
matched the Python "exactly", and every enumeration this epic hand-wrote was
later found under-inclusive.

So the inventory is derived here from two independent signals, and
`tests/mirrors.json` is held to the union of both by `tests/test_mirrors.py`:

``shared text``
    The same display-text template written on both sides of the boundary. A
    label copied into a client module keeps its words, so the words are what
    finds it. Interpolations collapse to a placeholder, so
    ``f"Based on {n} endorsing {noun}"`` and ``` `Based on ${n} endorsing
    ${noun}` ``` are one template.

``named symbols``
    A Python definition a client module names, or a client export a Python or
    Jinja file names. This reads "a comment is not a contract" mechanically: a
    mirror that announces its counterpart in prose is entered into the
    inventory *by* that announcement, so the comment can no longer be the only
    thing documenting it.

Neither signal subsumes the other. Shared text misses a mirror whose output is
arithmetic — ``percentageLabel`` shares only ``%`` with its Python side — and
named symbols misses a mirror nobody annotated. The union is the candidate set,
and every candidate needs an inventory entry saying how that mirror is proven.

Text is read one *rendered branch* at a time on both sides, which took three
corrections to get right and is where this scan previously missed real mirrors:
a ``{% if %}`` splits the markup around it rather than collapsing into it, a
Jinja expression's own literals and ``~`` concatenations are read, and a literal
nested inside a ``${...}`` is read too. The dialog's ``Leading choice`` kicker,
its contributing-count sentence, and the Comparisons status line each hid behind
one of those.

Three limits are deliberate, and are the reason the fixtures rather than this
scan carry the correctness claim:

- Symbol matching is restricted to multiword names (``snake_case`` with an
  underscore, ``camelCase`` with an internal capital). ``text`` and ``boot`` are
  defined on both sides and mean nothing to each other; a single word cannot
  distinguish a reference from a coincidence. Single-word mirrors are left to
  the text signal.
- Symbol matching reads raw source, comments included, while text matching
  reads comment-stripped source. A comment claiming a mirror is the claim this
  rule distrusts, so it must reach the inventory; a comment quoting a label is
  not a second implementation of it, so it must not.
- Text evidence finds only mirrors that share words, and a formatter whose
  output is one word (``supportSummaryCompact``'s ``"N sources"``) shares too
  little to be found. Nor does an evidence key record *where* a template is
  spelled, so a `shared-literal` entry catches wording dropped from a side but
  not one implementation moving while a second occurrence in the same file keeps
  the key alive. Text a macro's caller assembles, or a filter chain builds, is
  beyond it as well. So `tests/mirrors.json` is a floor the derivation raises,
  not a ceiling it defines: every derived candidate must appear there, and
  reviewed entries may be added that no signal pins.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
CLIENT_DIR = PROJECT_ROOT / "src" / "election_guide" / "rendering" / "templates"
SERVER_DIRS = (
    PROJECT_ROOT / "src" / "election_guide" / "rendering",
    PROJECT_ROOT / "src" / "election_guide" / "publication",
)

# The interpolation placeholder, chosen from outside the authored character set
# so it cannot collide with real text.
HOLE = "•"

_JS_STRING = re.compile(r"""(?P<q>["'`])(?P<body>(?:\\.|(?!(?P=q)).)*)(?P=q)""", re.DOTALL)
_JS_HOLE = re.compile(r"\$\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}")
_JS_BLOCK_COMMENT = re.compile(r"/\*[\s\S]*?\*/")
# Whitespace or line start before `//`, so a `https://` inside a string survives.
# The same heuristic `tests/js/support/module-guards.mjs` strips comments with.
_JS_LINE_COMMENT = re.compile(r"(^|\s)//.*$", re.M)
# A `{{ value }}` is an interpolation, so it becomes a hole. A `{% tag %}` is
# control flow, so it becomes a *boundary*: the text on either side of an
# `{% if %}`/`{% else %}` is two templates the page renders separately, and
# fusing them into one produces a template neither side ever writes.
_JINJA_VALUE = re.compile(r"\{\{.*?\}\}", re.DOTALL)
_JINJA_TAG = re.compile(r"\{%.*?%\}", re.DOTALL)
_JINJA_COMMENT = re.compile(r"\{#.*?#\}", re.DOTALL)
_JINJA_CONSTRUCT = re.compile(r"\{\{(.*?)\}\}|\{%(.*?)%\}", re.DOTALL)
_JINJA_QUOTED = re.compile(r"'([^'\\]*(?:\\.[^'\\]*)*)'|\"([^\"\\]*(?:\\.[^\"\\]*)*)\"")
# The contents of one bracket group, non-greedy so nesting is reached by recursion.
_BRACKET_GROUP = re.compile(r"[(\[{](.*)[)\]}]", re.DOTALL)
_HTML_TAG = re.compile(r"<[^>]*>", re.DOTALL)
# Chunk boundary. Like HOLE, chosen from outside the authored character set.
_BOUNDARY = "\x00"
_WHITESPACE = re.compile(r"\s+")
_JS_EXPORT = re.compile(r"^export (?:async )?(?:function|class) (\w+)", re.M)
_MULTIWORD_SNAKE = re.compile(r"^[a-z][a-z0-9]*(?:_[a-z0-9]+)+$")
_MULTIWORD_CAMEL = re.compile(r"^[a-z][a-zA-Z0-9]*[A-Z][a-zA-Z0-9]*$")


def _server_files() -> list[Path]:
    """Every Python module and Jinja template that renders the audited pages."""
    found: set[Path] = set()
    for directory in SERVER_DIRS:
        found.update(directory.rglob("*.py"))
        found.update(directory.rglob("*.j2"))
    return sorted(found)


def _client_files() -> list[Path]:
    return sorted(CLIENT_DIR.glob("*.mjs"))


def _normalize(text: str) -> str:
    """Collapse a literal to the display-text template it writes."""
    return _WHITESPACE.sub(" ", text).strip(HOLE + " ").strip()


def _is_display_text(template: str) -> bool:
    """Whether a normalized template is text a reader could be shown.

    Deliberately generous. A false positive costs one inventory entry recording
    how that text is already proven; a false negative is a mirror nobody looks
    at, which is what this module exists to prevent.
    """
    if len(template) < 4 or not re.search(r"[A-Za-z]{2}", template):
        return False
    # A bare identifier, selector, or path is a name rather than a sentence, and
    # `tests/shared_names.json` already owns names shared as syntax. Requiring a
    # space or a placeholder keeps this scan on prose.
    return " " in template or HOLE in template


def _python_literals(source: str) -> set[str]:
    """Every string constant and f-string skeleton, read from the parse tree.

    Parsed rather than matched: an apostrophe inside a comment desynchronizes a
    regex scan, and Python's own parser cannot be desynchronized.
    """
    literals: set[str] = set()
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            literals.add(node.value)
        elif isinstance(node, ast.JoinedStr):
            literals.add(
                "".join(
                    part.value
                    if isinstance(part, ast.Constant) and isinstance(part.value, str)
                    else HOLE
                    for part in node.values
                )
            )
    return literals


def _split_top_level(text: str, separator: str) -> list[str]:
    """Split on a separator that is outside brackets and outside a string."""
    parts: list[str] = []
    depth = 0
    quote: str | None = None
    current: list[str] = []
    for character in text:
        if quote is not None:
            current.append(character)
            if character == quote:
                quote = None
            continue
        if character in "\"'":
            quote = character
        elif character in "([{":
            depth += 1
        elif character in ")]}":
            depth -= 1
        elif character == separator and depth == 0:
            parts.append("".join(current))
            current = []
            continue
        current.append(character)
    parts.append("".join(current))
    return parts


def _jinja_expression_templates(source: str) -> set[str]:
    """Display text a Jinja *expression* composes rather than writes as markup.

    `compare.html.j2` builds its control status as
    `count ~ ' of ' ~ count ~ ' races shown · ' ~ differ ~ ' differ'` and hands
    it to a macro. Treating the whole construct as one interpolation deletes
    that sentence, so a `~` concatenation is reassembled into the template it
    renders as, with every non-literal operand standing in as a hole. Quoted
    literals that are not part of a concatenation are taken on their own.
    """
    templates: set[str] = set()
    for match in _JINJA_CONSTRUCT.finditer(source):
        body = match.group(1) if match.group(1) is not None else match.group(2)
        templates |= _expression_templates(body or "")
    return templates


def _expression_templates(expression: str, depth: int = 0) -> set[str]:
    """Every template one Jinja expression composes, at any bracket depth.

    Recursive because the sentence that motivated this is an *argument* to a
    macro call: `{% call election_controls(..., a ~ ' of ' ~ b ~ ' differ') %}`
    keeps its concatenation inside parentheses, so splitting only the
    construct's own top level would never reach it.
    """
    if depth > 8:
        return set()
    templates: set[str] = set()
    for argument in _split_top_level(expression, ","):
        operands = _split_top_level(argument, "~")
        if len(operands) > 1:
            templates.add(
                "".join(
                    quoted.group(1) or quoted.group(2) or ""
                    if (quoted := _JINJA_QUOTED.fullmatch(operand.strip()))
                    else HOLE
                    for operand in operands
                )
            )
        for quoted in _JINJA_QUOTED.finditer(argument):
            templates.add(quoted.group(1) or quoted.group(2) or "")
        for inner in _BRACKET_GROUP.finditer(argument):
            templates |= _expression_templates(inner.group(1), depth + 1)
    return templates


def _jinja_markup_templates(source: str) -> set[str]:
    """Display text a Jinja template writes as markup, one branch at a time."""
    holed = _JINJA_VALUE.sub(HOLE, source)
    bounded = _JINJA_TAG.sub(_BOUNDARY, holed)
    chunks: list[str] = []
    for between_tags in _HTML_TAG.split(bounded):
        chunks.extend(between_tags.split(_BOUNDARY))
    return set(chunks)


def _python_templates(path: Path) -> set[str]:
    text = path.read_text(encoding="utf-8")
    if path.suffix == ".j2":
        stripped = _JINJA_COMMENT.sub("", text)
        candidates = _jinja_markup_templates(stripped) | _jinja_expression_templates(stripped)
    else:
        candidates = _python_literals(text)
    return {template for literal in candidates if _is_display_text(template := _normalize(literal))}


def _executable_client_source(path: Path) -> str:
    """Client source with comments removed, as the module guard reads it."""
    text = path.read_text(encoding="utf-8")
    return _JS_LINE_COMMENT.sub(r"\1", _JS_BLOCK_COMMENT.sub("", text))


def _client_literals(source: str, depth: int = 0) -> set[str]:
    """Every string literal, including those nested inside an interpolation.

    The mirror image of the Jinja fix above, and the same blind spot: a
    conditional inside `${...}` — ``` `${tied ? 'No majority · ' : ''}${rest}` ```
    — is a literal the reader sees, but the enclosing template literal collapses
    to a bare hole, and a scan that stopped at the outer quote would never look
    inside. So the interpolations are scanned as source in their own right.
    """
    if depth > 8:
        return set()
    literals: set[str] = set()
    for match in _JS_STRING.finditer(source):
        body = match.group("body")
        literals.add(_JS_HOLE.sub(HOLE, body))
        if match.group("q") == "`":
            for interpolation in _JS_HOLE.finditer(body):
                literals |= _client_literals(interpolation.group(0)[2:-1], depth + 1)
    return literals


def _client_templates(path: Path) -> set[str]:
    return {
        template
        for literal in _client_literals(_executable_client_source(path))
        if _is_display_text(template := _normalize(literal))
    }


def shared_text() -> dict[str, dict[str, list[str]]]:
    """Display-text templates written on both sides of the boundary."""
    server: dict[str, set[str]] = {}
    for path in _server_files():
        for template in _python_templates(path):
            server.setdefault(template, set()).add(path.name)
    client: dict[str, set[str]] = {}
    for path in _client_files():
        for template in _client_templates(path):
            client.setdefault(template, set()).add(path.name)
    return {
        template: {"server": sorted(server[template]), "client": sorted(client[template])}
        for template in sorted(set(server) & set(client))
    }


def named_symbols() -> dict[str, dict[str, list[str]]]:
    """Multiword definitions on one side that the other side names."""
    # Raw source on both sides, comments included. A mirror that names its
    # counterpart only in a comment is precisely the case this signal exists to
    # enter into the inventory, so stripping comments here would delete the
    # signal's whole reason for being.
    server_text = {path.name: path.read_text(encoding="utf-8") for path in _server_files()}
    client_text = {path.name: path.read_text(encoding="utf-8") for path in _client_files()}

    server_defs: dict[str, set[str]] = {}
    for path in _server_files():
        if path.suffix != ".py":
            continue
        for node in ast.walk(ast.parse(server_text[path.name])):
            if isinstance(
                node, ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef
            ) and _MULTIWORD_SNAKE.match(node.name):
                server_defs.setdefault(node.name, set()).add(path.name)
    client_defs: dict[str, set[str]] = {}
    for path in _client_files():
        for match in _JS_EXPORT.finditer(client_text[path.name]):
            if _MULTIWORD_CAMEL.match(match.group(1)):
                client_defs.setdefault(match.group(1), set()).add(path.name)

    found: dict[str, dict[str, list[str]]] = {}
    for name, defined_in in server_defs.items():
        word = re.compile(rf"\b{re.escape(name)}\b")
        named_by = sorted(other for other, body in client_text.items() if word.search(body))
        if named_by:
            found[name] = {"server": sorted(defined_in), "client": named_by}
    for name, defined_in in client_defs.items():
        word = re.compile(rf"\b{re.escape(name)}\b")
        named_by = sorted(other for other, body in server_text.items() if word.search(body))
        if named_by:
            entry = found.setdefault(name, {"server": [], "client": []})
            entry["server"] = sorted({*entry["server"], *named_by})
            entry["client"] = sorted({*entry["client"], *defined_in})
    return dict(sorted(found.items()))


def derived_evidence() -> dict[str, dict[str, list[str]]]:
    """Every candidate mirror the tree shows, keyed by the evidence that found it.

    Text evidence is prefixed `text:` and symbol evidence `symbol:`, so the two
    namespaces cannot collide in `tests/mirrors.json`.
    """
    evidence = {f"text:{template}": where for template, where in shared_text().items()}
    evidence.update({f"symbol:{name}": where for name, where in named_symbols().items()})
    return dict(sorted(evidence.items()))


if __name__ == "__main__":  # pragma: no cover - a reading aid, not a check
    import json

    print(json.dumps(derived_evidence(), indent=2, ensure_ascii=False))
