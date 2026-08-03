"""The audited Comparisons page, as the Node markup-parity test consumes it.

docs/FRONTEND.md § Rendering requires that a lit-html template rendered with
audited data produce the region the Jinja template rendered. The two renderers
run in different languages, so the audited side is committed as a fixture and
the Node test diffs against it, exactly as the lens engine's parity fixture is
committed for the client scorer.

The fixture is the rendered page with two assets removed: the stylesheet, which
no markup comparison reads, and the bundled entry script, which a Node DOM must
not run. What remains is the server's markup and the payload element the client
renders from — the two halves the rule is about. That stripping is shared with
the guide and sources fixtures issue #248 added, and lives in `page_parity.py`.

Regenerate with::

    uv run python -m tests.compare_parity
"""

from __future__ import annotations

from pathlib import Path

from election_guide.publication.comparisons import ComparisonsPolicy
from election_guide.publication.models import PublicationViewModel
from election_guide.rendering.documents import render_comparison_document
from tests.page_parity import PUBLIC_SITE_URL, strip_for_parity
from tests.test_comparisons import _bundle  # pyright: ignore[reportPrivateUsage]

PROJECT_ROOT = Path(__file__).resolve().parents[1]
AUDITED_PAGE_PATH = PROJECT_ROOT / "tests" / "js" / "fixtures" / "compare-audited-page.html"

PROJECT_URL = "https://github.com/shaug/seattle-election-guide"

# The address the fixture's relative links resolve against, which is the page
# the audited document is published at. The Node harness resolves both sides
# against it, so the server's absolute race links and the client's relative
# ones compare as the links they are.
PAGE_URL = f"{PUBLIC_SITE_URL}/e/wa-2026-primary/comparisons/"


def enabled_view_model() -> PublicationViewModel:
    """The published view model with the Comparisons page switched on."""
    view_model = _bundle().view_model
    return view_model.model_copy(
        update={
            "comparisons": view_model.comparisons.model_copy(
                update={"policy": ComparisonsPolicy(enabled=True)}
            )
        }
    )


def build_audited_comparison_page() -> str:
    """Render the Comparisons page and strip what a markup comparison must not run."""
    return strip_for_parity(
        render_comparison_document(
            enabled_view_model(),
            public_site_url=PUBLIC_SITE_URL,
            project_url=PROJECT_URL,
        )
    )


def write_audited_comparison_page() -> Path:
    """Write the committed fixture."""
    page = build_audited_comparison_page()
    AUDITED_PAGE_PATH.parent.mkdir(parents=True, exist_ok=True)
    AUDITED_PAGE_PATH.write_text(page, encoding="utf-8")
    return AUDITED_PAGE_PATH


if __name__ == "__main__":
    print(f"wrote {write_audited_comparison_page()}")
