"""Compiled templates are reused without retaining page data or stale source (#651)."""

import os
from collections import Counter
from pathlib import Path
from types import CodeType

import pytest
from jinja2 import Environment, UndefinedError, nodes

from election_guide.rendering import documents


def _templates(root: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    (root / "_shell.html.j2").write_text(
        "{% macro wrap(value) %}<b>{{ value }}</b>{% endmacro %}", encoding="utf-8"
    )
    (root / "page.html.j2").write_text("{{ shell.wrap(value) }}", encoding="utf-8")
    monkeypatch.setattr(documents, "TEMPLATE_DIR", root)


def _render(value: str) -> str:
    return documents.template_environment().get_template("page.html.j2").render(value=value)


def _replace_without_stat_change(path: Path, old: str, new: str) -> None:
    before = path.stat()
    content = path.read_text(encoding="utf-8")
    path.write_text(content.replace(old, new), encoding="utf-8")
    assert path.stat().st_size == before.st_size
    os.utime(path, ns=(before.st_atime_ns, before.st_mtime_ns))


def test_unchanged_templates_compile_once_with_fresh_escaped_contexts(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Recreating the environment recompiles both inputs on every page render."""
    _templates(tmp_path, monkeypatch)
    compiled: list[str | None] = []
    original = Environment.compile

    def compile_template(
        self: Environment,
        source: str | nodes.Template,
        name: str | None = None,
        filename: str | None = None,
        raw: bool = False,
        defer_init: bool = False,
    ) -> CodeType | str:
        compiled.append(name)
        return original(self, source, name, filename, raw, defer_init)

    monkeypatch.setattr(Environment, "compile", compile_template)
    assert _render("<first>") == "<b>&lt;first&gt;</b>"
    assert _render("<second>") == "<b>&lt;second&gt;</b>"
    with pytest.raises(UndefinedError):
        documents.template_environment().get_template("page.html.j2").render()
    assert Counter(compiled) == {"_shell.html.j2": 1, "page.html.j2": 1}


def test_shell_edit_invalidates_cached_macros_with_unchanged_mtime_and_size(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Caching only by directory or stat metadata would keep the old global macro."""
    _templates(tmp_path, monkeypatch)
    assert _render("first") == "<b>first</b>"
    path = tmp_path / "_shell.html.j2"
    _replace_without_stat_change(path, "<b>", "<i>")
    _replace_without_stat_change(path, "</b>", "</i>")
    assert _render("second") == "<i>second</i>"


def test_page_edit_invalidates_compiled_template_with_unchanged_mtime_and_size(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Auto-reload by mtime alone cannot observe this changed template."""
    _templates(tmp_path, monkeypatch)
    path = tmp_path / "page.html.j2"
    path.write_text("{{ shell.wrap(value) }}A", encoding="utf-8")
    assert _render("first") == "<b>first</b>A"
    _replace_without_stat_change(path, "}}A", "}}B")
    assert _render("second") == "<b>second</b>B"


def test_identical_sources_in_another_root_keep_their_own_loader(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Sharing by content alone would attribute the second root's errors to the first."""
    first, second = tmp_path / "first", tmp_path / "second"
    first.mkdir()
    second.mkdir()
    _templates(first, monkeypatch)
    assert _render("first") == "<b>first</b>"
    _templates(second, monkeypatch)
    template = documents.template_environment().get_template("page.html.j2")
    assert template.filename == str(second / "page.html.j2")
    assert template.render(value="<second>") == "<b>&lt;second&gt;</b>"
