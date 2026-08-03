"""The check for `each page has one CSS entry` (docs/FRONTEND.md, Modules).

The guide and the sources editor read one stylesheet before issue 246, so the
guide document carried the editor's whole checkbox tree and coverage-gap
section and the editor carried the guide's race grid, race-detail dialog, and
printable edition. The manifest in `rendering/stylesheets.py` is what stops
that recurring; these tests hold the manifest to its claims.
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

# Named in every failure message below, per docs/FRONTEND.md's own preamble:
# a check's failure must name the rule it enforces and the document that owns
# it, or the reader cannot get from the failure back to the rule.
RULE = "rule: each page has one CSS entry, docs/FRONTEND.md, Modules"

# `.foo` in a selector, which is how a rule names the markup it styles.
CLASS_SELECTOR = re.compile(r"\.(-?[_a-zA-Z][\w-]*)")

# The part every page reads: the design tokens and the shell (docs/DESIGN.md).
SHARED_FIRST = "base.css"

# The one template allowed to open a <style> element or fill the styles slot.
LAYOUT = "base.html.j2"


def _declared_classes(part: str) -> set[str]:
    """Every class a stylesheet part writes a rule for, comments excluded.

    Scanned brace by brace rather than line by line so a selector nested in an
    `@media` block counts too: a responsive rule is as much this part's as an
    unconditional one, and reading only column-zero selectors would let a page
    stylesheet hide another page's rules inside a media query.
    """
    source = re.sub(r"/\*.*?\*/", "", (TEMPLATE_DIR / part).read_text(encoding="utf-8"), flags=re.S)
    selectors: list[str] = []
    prelude: list[str] = []
    for character in source:
        if character == "{":
            candidate = "".join(prelude).strip()
            # An at-rule's prelude is a condition, not a selector.
            if not candidate.startswith("@"):
                selectors.append(candidate)
            prelude = []
        elif character == "}":
            prelude = []
        else:
            prelude.append(character)
    return set(CLASS_SELECTOR.findall("\n".join(selectors)))


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
    assert parts[0] == SHARED_FIRST, f"{page} must read the tokens and shell first ({RULE})"
    assert parts[-1] == f"{page}.css", (
        f"{page}'s own stylesheet must be its last part, so it can override the shared "
        f"ones ({RULE})"
    )
    assert len(set(parts)) == len(parts), f"{page} reads a part twice ({RULE})"
    for part in parts:
        assert (TEMPLATE_DIR / part).is_file(), (
            f"{page} names a stylesheet that does not exist ({RULE})"
        )


@pytest.mark.parametrize("page", sorted(PAGE_STYLESHEETS))
def test_a_page_renders_a_template_of_the_same_name(page: str) -> None:
    assert (TEMPLATE_DIR / f"{page}.html.j2").is_file(), (
        f"{page} is declared a page but renders no template ({RULE})"
    )


def test_every_stylesheet_in_the_template_directory_is_declared_by_a_page() -> None:
    """An undeclared stylesheet is one nothing ships: it would go stale unseen."""
    declared = {part for parts in PAGE_STYLESHEETS.values() for part in parts}
    on_disk = {path.name for path in TEMPLATE_DIR.glob("*.css")}
    assert on_disk == declared, f"a stylesheet on disk is read by no page ({RULE})"


def test_only_the_shared_layout_writes_a_style_element_or_fills_the_styles_slot() -> None:
    """A page writes no rules in its template, so its CSS is in one place.

    This is the clause the other tests here cannot reach: rules written inline
    in a template ship to that page's document without passing through
    `page_stylesheet`, so they are invisible to every manifest-level check
    above — which is exactly how about, the archive, the 404, and the sources
    editor each carried their own rules before issue 246.
    """
    offenders = {
        path.name: [
            marker
            for marker in ("{% block styles %}", "<style")
            if marker in path.read_text(encoding="utf-8")
        ]
        for path in sorted(TEMPLATE_DIR.glob("*.html.j2"))
        if path.name != LAYOUT
    }
    assert not {name: found for name, found in offenders.items() if found}, (
        f"only {LAYOUT} may open a <style> element or fill the styles slot; a page's own "
        f"rules belong in its own stylesheet (rendering/stylesheets.py; {RULE})"
    )


def test_page_stylesheet_is_its_declared_parts_in_order() -> None:
    for page, parts in PAGE_STYLESHEETS.items():
        expected = "".join((TEMPLATE_DIR / part).read_text(encoding="utf-8") for part in parts)
        assert page_stylesheet(page) == expected, (
            f"{page} ships something other than its declared parts, in order ({RULE})"
        )


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
                f"stylesheet; move it to a part both read (rendering/stylesheets.py; {RULE})"
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
