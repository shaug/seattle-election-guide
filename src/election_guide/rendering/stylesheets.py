"""Each page's CSS entry: the stylesheet parts it ships (issue 246).

The scripts side of this seam bundles a real import graph, because modules
resolving each other by paste order was a correctness problem
(rendering/bundler.py). CSS has no such graph — a stylesheet is an ordered list
of rules and the cascade is the only relationship between them — so the entry
here is a declared list of parts rather than a bundler invocation. Running
esbuild over the CSS would buy nothing a list does not (there is no collision
class to close and nothing to tree-shake) and would cost the authored bytes:
it reprints every rule and drops the comments that explain them, which are
most of what makes these files reviewable.

What the list buys is that a rule group belongs to the pages that render it.
Before this, the guide and the sources editor both read `base.css + guide.css`,
so the guide document shipped the editor's whole checkbox tree and coverage-gap
section without rendering any of it, and the editor shipped the guide's race
grid, race-detail dialog, and printable edition.

Parts compose in order, so a later part may override an earlier one: `base.css`
carries the tokens and the shell every page renders (docs/DESIGN.md) and is
always first; a page's own stylesheet is always last.
"""

from __future__ import annotations

from functools import cache

from election_guide.rendering.bundler import TEMPLATE_DIR

# The one place a page's stylesheet is declared. Adding a page means adding it
# here; `tests/test_page_stylesheets.py` holds every part to a real file, holds
# every page stylesheet to exactly one page, and holds the pages named here to
# the templates that exist.
PAGE_STYLESHEETS: dict[str, tuple[str, ...]] = {
    "guide": ("base.css", "guide-sources.css", "guide.css"),
    "sources": ("base.css", "guide-sources.css", "sources.css"),
    "compare": ("base.css", "compare.css"),
    "about": ("base.css", "about.css"),
    "archive": ("base.css", "archive.css"),
    "not-found": ("base.css", "not-found.css"),
}


class StylesheetError(LookupError):
    """A page was rendered that has no declared stylesheet."""


@cache
def page_stylesheet(page: str) -> str:
    """The CSS `page` inlines into its `<style>` element, parts in order."""
    try:
        parts = PAGE_STYLESHEETS[page]
    except KeyError:
        raise StylesheetError(
            f"no stylesheet is declared for page {page!r}; declare its parts in "
            "rendering/stylesheets.py (docs/FRONTEND.md, Modules)."
        ) from None
    return "".join((TEMPLATE_DIR / part).read_text(encoding="utf-8") for part in parts)
