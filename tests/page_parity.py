"""The audited pages, as the Node markup-parity tests consume them.

docs/FRONTEND.md § Rendering requires that a lit-html template rendered with
audited data produce the region the Jinja template rendered. The two renderers
run in different languages, so the audited side is committed as a fixture and
the Node tests diff against it, exactly as the lens engine's parity fixture is
committed for the client scorer.

Each fixture is the rendered page with two assets removed: the stylesheet, which
no markup comparison reads, and the bundled entry script, which a Node DOM must
not run. What remains is the server's markup and the payload element the client
renders from — the two halves the rule is about.

Issue #238 committed the Comparisons page here first (`compare_parity.py`, which
shares this module's stripping); issue #248 added the guide and the sources
editor when their lens regions moved to lit.

Regenerate with::

    uv run python -m tests.page_parity
"""

from __future__ import annotations

import re
from pathlib import Path

from election_guide.publication.models import PublicationViewModel
from election_guide.rendering import read_rendering_configuration, render_html_document
from election_guide.rendering.renderer import render_sources_document
from tests.test_personalization import _bundle  # pyright: ignore[reportPrivateUsage]

PROJECT_ROOT = Path(__file__).resolve().parents[1]
FIXTURE_DIR = PROJECT_ROOT / "tests" / "js" / "fixtures"
GUIDE_PAGE_PATH = FIXTURE_DIR / "guide-audited-page.html"
SOURCES_PAGE_PATH = FIXTURE_DIR / "sources-audited-page.html"
RENDERING_CONFIG = PROJECT_ROOT / "config" / "rendering" / "guide.yaml"

# Fixed so the fixtures are a function of the committed dataset alone.
PUBLIC_SITE_URL = "https://seattleelections.guide"

# The addresses the fixtures' relative links resolve against, which are the
# pages the audited documents are published at. The Node harness resolves both
# sides against them, so a server's absolute path and a client's relative one
# compare as the link they are.
GUIDE_PAGE_URL = f"{PUBLIC_SITE_URL}/e/wa-2026-primary/"
SOURCES_PAGE_URL = f"{GUIDE_PAGE_URL}sources/"

_STYLE = re.compile(r"<style>.*?</style>", re.DOTALL)
_MODULE_SCRIPT = re.compile(r'<script type="module">.*?</script>', re.DOTALL)
# The race-detail dialog's interior, which is roughly three quarters of the
# guide's bytes and is not a lit region: #136 replaces the dialog with real race
# pages, and #248 deliberately left its renderer imperative. Emptying it keeps
# the element the wiring looks for while keeping the committed fixture to the
# markup a parity comparison actually reads. The dialog's own behavior is
# covered by the headless tests in `test_rendering.py`.
_DIALOG_BODY = re.compile(r"(<dialog\b[^>]*>).*?(</dialog>)", re.DOTALL)


def strip_for_parity(rendered: str) -> str:
    """Remove what a markup comparison must not read or run.

    The payload element is asserted rather than assumed: it is what the client
    renders from, so a fixture without one would make the whole comparison
    vacuous (docs/FRONTEND.md, The data contract).
    """
    stripped = _STYLE.sub("<style></style>", rendered)
    stripped = _MODULE_SCRIPT.sub("", stripped)
    if "data-client-payload" not in stripped:
        raise AssertionError(
            "the audited fixture lost its payload element; the client renders from it "
            "(docs/FRONTEND.md, The data contract)."
        )
    return stripped


def published_view_model() -> PublicationViewModel:
    """The published view model, with the lens policy as the release ships it."""
    return _bundle().view_model


def build_audited_guide_page() -> str:
    """Render the endorsements guide and strip what a markup comparison must not
    run, plus the dialog interiors no lit region covers."""
    rendered = render_html_document(
        published_view_model(), read_rendering_configuration(RENDERING_CONFIG)
    )
    return _DIALOG_BODY.sub(r"\1\2", strip_for_parity(rendered))


def build_audited_sources_page() -> str:
    """Render the sources editor and strip what a markup comparison must not run."""
    return strip_for_parity(
        render_sources_document(published_view_model(), public_site_url=PUBLIC_SITE_URL)
    )


def write_audited_pages() -> list[Path]:
    """Write the committed fixtures."""
    FIXTURE_DIR.mkdir(parents=True, exist_ok=True)
    GUIDE_PAGE_PATH.write_text(build_audited_guide_page(), encoding="utf-8")
    SOURCES_PAGE_PATH.write_text(build_audited_sources_page(), encoding="utf-8")
    return [GUIDE_PAGE_PATH, SOURCES_PAGE_PATH]


if __name__ == "__main__":
    for path in write_audited_pages():
        print(f"wrote {path}")
