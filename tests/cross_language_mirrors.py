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
  little to be found. So `tests/mirrors.json` is a floor the derivation raises,
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
_JINJA_HOLE = re.compile(r"\{\{.*?\}\}|\{%.*?%\}", re.DOTALL)
_JINJA_COMMENT = re.compile(r"\{#.*?#\}", re.DOTALL)
_HTML_TAG = re.compile(r"<[^>]*>", re.DOTALL)
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


def _python_templates(path: Path) -> set[str]:
    text = path.read_text(encoding="utf-8")
    if path.suffix == ".j2":
        stripped = _JINJA_HOLE.sub(HOLE, _JINJA_COMMENT.sub("", text))
        return {
            template
            for chunk in _HTML_TAG.split(stripped)
            if _is_display_text(template := _normalize(chunk))
        }
    return {
        template
        for literal in _python_literals(text)
        if _is_display_text(template := _normalize(literal))
    }


def _executable_client_source(path: Path) -> str:
    """Client source with comments removed, as the module guard reads it."""
    text = path.read_text(encoding="utf-8")
    return _JS_LINE_COMMENT.sub(r"\1", _JS_BLOCK_COMMENT.sub("", text))


def _client_templates(path: Path) -> set[str]:
    return {
        template
        for match in _JS_STRING.finditer(_executable_client_source(path))
        if _is_display_text(template := _normalize(_JS_HOLE.sub(HOLE, match.group("body"))))
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
