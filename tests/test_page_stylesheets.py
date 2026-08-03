"""The check for `each page has one CSS entry` (docs/FRONTEND.md, Modules).

The guide and the sources editor read one stylesheet before issue 246, so the
guide document carried the editor's whole checkbox tree and coverage-gap
section and the editor carried the guide's race grid, race-detail dialog, and
printable edition. The manifest in `rendering/stylesheets.py` is what stops
that recurring; these tests hold the manifest to its claims.
"""

from __future__ import annotations

import re
from collections import Counter

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


def _declared_classes(source: str) -> set[str]:
    """Every class the CSS in `source` writes a rule for, comments excluded.

    Takes the stylesheet text rather than a filename so the same definition of
    "declares a class" answers for a part and for a whole page's entry — one
    rule, not one per side of the comparison.

    `[^{}]*` cannot cross a brace, so each match is one block's prelude at any
    nesting depth: a selector inside an `@media` block counts, and reading only
    top-level ones would let a page hide another page's rules in a media query.
    """
    without_comments = re.sub(r"/\*.*?\*/", "", source, flags=re.S)
    selectors = [
        prelude
        for prelude in re.findall(r"[^{}]*(?=\{)", without_comments)
        # An at-rule's prelude is a condition, not a selector.
        if not prelude.strip().startswith("@")
    ]
    return set(CLASS_SELECTOR.findall("\n".join(selectors)))


def _part_classes(part: str) -> set[str]:
    """Every class one stylesheet part declares."""
    return _declared_classes((TEMPLATE_DIR / part).read_text(encoding="utf-8"))


def _readers() -> Counter[str]:
    """How many pages read each declared part."""
    return Counter(part for parts in PAGE_STYLESHEETS.values() for part in parts)


def _exclusive_parts(page: str) -> set[str]:
    """The parts only `page` reads."""
    readers = _readers()
    return {part for part in PAGE_STYLESHEETS[page] if readers[part] == 1}


def _shared_classes() -> set[str]:
    """Classes declared in a part more than one page reads."""
    return set[str]().union(*(_part_classes(p) for p, n in _readers().items() if n > 1))


@pytest.mark.parametrize("page", sorted(PAGE_STYLESHEETS))
def test_every_page_reads_the_shared_base_first_and_its_own_stylesheet_last(page: str) -> None:
    parts = PAGE_STYLESHEETS[page]
    assert parts[0] == SHARED_FIRST, f"{page} must read the tokens and shell first ({RULE})"
    assert parts[-1] == f"{page}.css", (
        f"{page}'s own stylesheet must be its last part, so it can override the shared "
        f"ones ({RULE})"
    )
    assert len(set(parts)) == len(parts), f"{page} reads a part twice ({RULE})"


@pytest.mark.parametrize("page", sorted(PAGE_STYLESHEETS))
def test_a_page_renders_a_template_of_the_same_name(page: str) -> None:
    assert (TEMPLATE_DIR / f"{page}.html.j2").is_file(), (
        f"{page} is declared a page but renders no template ({RULE})"
    )


def test_every_stylesheet_is_declared_by_a_page_and_every_declared_part_exists() -> None:
    """Set equality both ways: no stylesheet nothing ships, no part that is missing.

    An undeclared stylesheet would go stale unseen; a declared part with no
    file would fail at render time instead of here.
    """
    declared = {part for parts in PAGE_STYLESHEETS.values() for part in parts}
    on_disk = {path.name for path in TEMPLATE_DIR.glob("*.css")}
    assert on_disk == declared, (
        f"declared but missing: {sorted(declared - on_disk)}; "
        f"on disk but read by no page: {sorted(on_disk - declared)} ({RULE})"
    )


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

    A class styled only by a stylesheet one other page reads must not be styled
    by this page's entry at all — not through the manifest, and not through a
    rule copied back in, since a copied rule declares the class too. A class two
    pages really do render belongs in a part they both read, which is what makes
    `_shared_classes` the right exemption rather than an allowlist to maintain.
    """
    shipped = _declared_classes(page_stylesheet(page))
    shared = _shared_classes()
    for other in PAGE_STYLESHEETS:
        if other == page:
            continue
        exclusive = set[str]().union(*(_part_classes(p) for p in _exclusive_parts(other)))
        leaked = sorted((exclusive - shared) & shipped)
        assert not leaked, (
            f"the {page} page styles {leaked}, styled only by the {other} page's own "
            f"stylesheet; move them to a part both read (rendering/stylesheets.py; {RULE})"
        )


def test_the_guide_document_no_longer_ships_the_sources_editors_checkbox_tree() -> None:
    """Issue 246's spot check, named so a regression reads as the thing it is.

    Asked of the classes each entry declares rather than of its raw text, so a
    comment that names a moved rule — the natural way to explain where it went
    — is prose rather than a build failure.
    """
    guide = _declared_classes(page_stylesheet("guide"))
    sources = _declared_classes(page_stylesheet("sources"))

    editor_only = {
        "sources-tree",
        "sources-columns",
        "sources-category",
        "sources-check",
        "sources-count",
        "screen-coverage-gaps",
        "coverage-gap-row",
    }
    assert not editor_only & guide, (
        f"the guide document styles {sorted(editor_only & guide)}, which only the sources "
        f"editor renders ({RULE})"
    )
    assert editor_only <= sources, (
        f"the sources editor lost {sorted(editor_only - sources)}, which it renders ({RULE})"
    )

    # ...and the reverse: the editor stopped carrying the guide's race grid,
    # race-detail dialog, and printable edition.
    guide_only = {"race-grid", "race-detail-dialog", "race-card", "screen-meter"}
    assert not guide_only & sources, (
        f"the sources editor styles {sorted(guide_only & sources)}, which only the guide "
        f"renders ({RULE})"
    )
    assert guide_only <= guide, (
        f"the guide lost {sorted(guide_only - guide)}, which it renders ({RULE})"
    )


def test_the_guide_and_the_sources_editor_still_share_what_they_both_render() -> None:
    """The other half of the split: neither page lost a rule it does render.

    Both templates render a `.lens-notice`, both render the band whose nav the
    720px rule resets, and both documents print with the same page margins, so
    dropping `guide-sources.css` from either entry is a silent visual
    regression rather than a saving.
    """
    for page in ("guide", "sources"):
        stylesheet = re.sub(r"/\*.*?\*/", "", page_stylesheet(page), flags=re.S)
        classes = _declared_classes(stylesheet)
        assert {"lens-notice", "site-band"} <= classes, (
            f"the {page} page lost the shared lens notice or band rules ({RULE})"
        )
        assert re.search(r"@page\s*\{", stylesheet), (
            f"the {page} page lost its @page margins, which it prints with; they belong to "
            f"the part both pages read (rendering/stylesheets.py; {RULE})"
        )
