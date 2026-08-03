"""Each page's CSS entry ships that page's rules and no other page's (issue 246).

The guide and the sources editor read one stylesheet before this, so the guide
document carried the editor's whole checkbox tree and coverage-gap section and
the editor carried the guide's race grid, race-detail dialog, and printable
edition. The manifest in `rendering/stylesheets.py` is what stops that
recurring; these tests hold the manifest to its claims.
"""

from __future__ import annotations

import re

import pytest

from election_guide.rendering.bundler import TEMPLATE_DIR
from election_guide.rendering.stylesheets import (
    PAGE_STYLESHEETS,
    StylesheetError,
    page_stylesheet,
)

# `.foo` in a selector, which is how a rule names the markup it styles.
CLASS_SELECTOR = re.compile(r"\.(-?[_a-zA-Z][\w-]*)")

# The part every page reads: the design tokens and the shell (docs/DESIGN.md).
SHARED_FIRST = "base.css"


def _declared_classes(part: str) -> set[str]:
    """Every class a stylesheet part writes a rule for, comments excluded."""
    source = re.sub(r"/\*.*?\*/", "", (TEMPLATE_DIR / part).read_text(encoding="utf-8"), flags=re.S)
    selectors = "\n".join(re.findall(r"^[^{@\s][^{]*(?=\{)", source, re.MULTILINE))
    return set(CLASS_SELECTOR.findall(selectors))


def _exclusive_parts(page: str) -> set[str]:
    """The parts only `page` reads."""
    others = {part for name, parts in PAGE_STYLESHEETS.items() if name != page for part in parts}
    return set(PAGE_STYLESHEETS[page]) - others


def _shared_classes() -> set[str]:
    """Classes declared in a part more than one page reads."""
    readers: dict[str, int] = {}
    for parts in PAGE_STYLESHEETS.values():
        for part in parts:
            readers[part] = readers.get(part, 0) + 1
    shared: set[str] = set()
    for part, count in readers.items():
        if count > 1:
            shared |= _declared_classes(part)
    return shared


@pytest.mark.parametrize("page", sorted(PAGE_STYLESHEETS))
def test_every_page_reads_the_shared_base_first_and_its_own_stylesheet_last(page: str) -> None:
    parts = PAGE_STYLESHEETS[page]
    assert parts[0] == SHARED_FIRST, f"{page} must read the tokens and shell first"
    assert parts[-1] == f"{page}.css", (
        f"{page}'s own stylesheet must be its last part, so it can override the shared ones"
    )
    assert len(set(parts)) == len(parts), f"{page} reads a part twice"
    for part in parts:
        assert (TEMPLATE_DIR / part).is_file(), f"{page} names a stylesheet that does not exist"


@pytest.mark.parametrize("page", sorted(PAGE_STYLESHEETS))
def test_a_page_renders_a_template_of_the_same_name(page: str) -> None:
    assert (TEMPLATE_DIR / f"{page}.html.j2").is_file()


def test_every_stylesheet_in_the_template_directory_is_declared_by_a_page() -> None:
    """An undeclared stylesheet is one nothing ships: it would go stale unseen."""
    declared = {part for parts in PAGE_STYLESHEETS.values() for part in parts}
    on_disk = {path.name for path in TEMPLATE_DIR.glob("*.css")}
    assert on_disk == declared


def test_page_stylesheet_is_its_declared_parts_in_order() -> None:
    for page, parts in PAGE_STYLESHEETS.items():
        expected = "".join((TEMPLATE_DIR / part).read_text(encoding="utf-8") for part in parts)
        assert page_stylesheet(page) == expected


def test_an_undeclared_page_is_a_named_failure_rather_than_a_missing_file() -> None:
    with pytest.raises(StylesheetError, match="no stylesheet is declared"):
        page_stylesheet("race")


@pytest.mark.parametrize("page", sorted(PAGE_STYLESHEETS))
def test_no_page_ships_a_rule_group_only_another_page_renders(page: str) -> None:
    """The acceptance property, as a property of the shipped bytes.

    A class styled only by a stylesheet one other page reads must not appear in
    this page's stylesheet at all — not through the manifest, and not through a
    rule copied back in. A class two pages really do render belongs in a part
    they both read, which is what makes `_shared_classes` the right exemption
    rather than an allowlist that would have to be maintained.
    """
    shipped = page_stylesheet(page)
    shared = _shared_classes()
    for other in PAGE_STYLESHEETS:
        if other == page:
            continue
        exclusive: set[str] = set()
        for part in _exclusive_parts(other):
            exclusive |= _declared_classes(part)
        for name in sorted(exclusive - shared):
            assert not re.search(rf"(?<![\w-])\.{re.escape(name)}(?![\w-])", shipped), (
                f"the {page} page ships .{name}, styled only by the {other} page's own "
                "stylesheet (rendering/stylesheets.py)"
            )


def test_the_guide_document_no_longer_ships_the_sources_editors_checkbox_tree() -> None:
    """Issue 246's spot check, named so a regression reads as the thing it is."""
    guide = page_stylesheet("guide")
    for selector in (
        ".sources-tree",
        ".sources-columns",
        ".sources-category",
        ".sources-check",
        ".sources-count",
        ".screen-coverage-gaps",
        ".coverage-gap-row",
    ):
        assert selector not in guide

    sources = page_stylesheet("sources")
    for selector in (".sources-tree", ".screen-coverage-gaps", ".coverage-gap-row"):
        assert selector in sources
    # ...and the reverse: the editor stopped carrying the guide's race grid,
    # race-detail dialog, and printable edition.
    for selector in (".race-grid", ".race-detail-dialog", ".race-card", ".screen-meter"):
        assert selector not in sources
        assert selector in guide


def test_the_guide_and_the_sources_editor_still_share_what_they_both_render() -> None:
    """The other half of the split: neither page lost a rule it does render.

    Both templates render a `.lens-notice`, and both documents print with the
    same page margins, so dropping `guide-sources.css` from either entry is a
    silent visual regression rather than a saving.
    """
    for page in ("guide", "sources"):
        shipped = page_stylesheet(page)
        assert ".lens-notice" in shipped
        assert "@page" in shipped
        assert ".site-band nav" in shipped
