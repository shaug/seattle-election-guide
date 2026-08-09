"""The Corrections page's own rendering (docs/RESULTS.md, "The corrections
page"; `docs/design/RESULTS_FINALIZATION_2026-08-02.html`; issue #290)."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from election_guide.corrections.models import (
    CorrectionEntry,
    CorrectionProvenanceLink,
    ElectionCorrections,
)
from election_guide.publication.comparisons import ComparisonsPolicy
from election_guide.publication.models import PublicationViewModel
from election_guide.rendering.config import read_rendering_configuration
from election_guide.rendering.documents import (
    render_comparison_document,
    render_corrections_document,
    render_html_document,
    render_sources_document,
)
from election_guide.rendering.shell import election_names
from tests.test_rendering import _view_model  # pyright: ignore[reportPrivateUsage]

PROJECT_ROOT = Path(__file__).resolve().parents[1]
PUBLIC_SITE_URL = "https://seattleelections.guide"
PROJECT_URL = "https://github.com/shaug/seattle-election-guide"
RENDERING_CONFIG = PROJECT_ROOT / "config" / "rendering" / "guide.yaml"


def _corrections(election_id: str) -> ElectionCorrections:
    return ElectionCorrections(
        election_id=election_id,
        entries=[
            CorrectionEntry(
                corrected_on=date(2026, 8, 27),
                headline="Amended result, State Representative (LD 32, Pos. 1).",
                body=(
                    "The county's amended canvass moved the second advancing candidate "
                    "after a machine recount. The certified figures published August 19 "
                    "have been replaced; both captures remain in the archive."
                ),
                provenance=[
                    CorrectionProvenanceLink(
                        label="capture 9f3c…e2", url="https://example.org/captures/9f3c"
                    ),
                    CorrectionProvenanceLink(
                        label="capture 41ab…77", url="https://example.org/captures/41ab"
                    ),
                ],
            ),
            CorrectionEntry(
                corrected_on=date(2026, 7, 22),
                headline="Corrected an endorsement attribution.",
                body=(
                    "The 46th District Democrats' sole endorsement in the County Assessor "
                    "race was attributed to the wrong candidate for roughly six hours on "
                    "July 21. The guide's recommendation was unaffected."
                ),
            ),
        ],
    )


def _with_corrections(view_model: PublicationViewModel) -> PublicationViewModel:
    return view_model.model_copy(
        update={"corrections": _corrections(view_model.metadata.election_id)}
    )


def test_render_corrections_document_raises_without_any_corrections(tmp_path: Path) -> None:
    """An election with no corrections renders no page (issue #290, acceptance
    criterion 1) -- a caller must gate on this before calling here, and this
    function itself fails loudly rather than publishing an empty log."""
    view_model = _view_model(tmp_path)
    assert view_model.corrections is None

    with pytest.raises(ValueError, match="no corrections"):
        render_corrections_document(view_model, public_site_url=PUBLIC_SITE_URL)


def test_render_corrections_document_renders_the_ratified_page(tmp_path: Path) -> None:
    """An election with entries renders the ratified page: eyebrow, title,
    tagline, dated entries, provenance links (issue #290, acceptance
    criterion 2)."""
    view_model = _with_corrections(_view_model(tmp_path))
    election_display_name, _ = election_names(
        view_model.metadata.election_date,
        view_model.metadata.election_type,
        view_model.metadata.state,
        legacy_name=view_model.metadata.election_name,
        election_id=view_model.metadata.election_id,
    )

    html = render_corrections_document(
        view_model, public_site_url=PUBLIC_SITE_URL, project_url=PROJECT_URL
    )

    assert "<h1>Corrections</h1>" in html
    assert '<p class="page-tagline">We get it right, eventually.</p>' in html
    assert f"<title>Corrections — {election_display_name} — " in html
    assert f'<meta property="og:title" content="Corrections — {election_display_name}' in html
    # The eyebrow names the election, exactly like Sources and Comparisons.
    assert f'<p class="page-eyebrow">{election_display_name}</p>' in html

    # Entries render newest first, each with its own date, headline, and body.
    assert html.index("August 27, 2026") < html.index("July 22, 2026")
    assert "<strong>Amended result, State Representative (LD 32, Pos. 1).</strong>" in html
    assert "<strong>Corrected an endorsement attribution.</strong>" in html

    # The amended-results entry's provenance line links both captures; the
    # endorsement-correction entry carries no provenance line at all.
    assert (
        '<p class="corrections-provenance"><a href="https://example.org/captures/9f3c" '
        'target="_blank" rel="noopener">capture 9f3c…e2</a> → '
        '<a href="https://example.org/captures/41ab" target="_blank" rel="noopener">'
        "capture 41ab…77</a></p>" in html
    )
    assert html.count('class="corrections-provenance"') == 1

    # No interactive client region: the page carries the shared shell script,
    # not a dedicated entry module or client payload.
    assert "data-client-payload" not in html


def test_render_corrections_document_orders_entries_newest_first_regardless_of_input_order(
    tmp_path: Path,
) -> None:
    view_model = _view_model(tmp_path)
    corrections = _corrections(view_model.metadata.election_id)
    reversed_corrections = corrections.model_copy(
        update={"entries": list(reversed(corrections.entries))}
    )
    view_model = view_model.model_copy(update={"corrections": reversed_corrections})

    html = render_corrections_document(view_model, public_site_url=PUBLIC_SITE_URL)

    assert html.index("August 27, 2026") < html.index("July 22, 2026")


def test_render_corrections_document_rejects_an_unsafe_provenance_link(tmp_path: Path) -> None:
    view_model = _view_model(tmp_path)
    unsafe_corrections = ElectionCorrections(
        election_id=view_model.metadata.election_id,
        entries=[
            CorrectionEntry(
                corrected_on=date(2026, 7, 22),
                headline="Corrected an endorsement attribution.",
                body="The guide's recommendation was unaffected.",
                provenance=[CorrectionProvenanceLink(label="capture", url="javascript:alert(1)")],
            )
        ],
    )
    view_model = view_model.model_copy(update={"corrections": unsafe_corrections})

    with pytest.raises(ValueError, match="not a safe HTTP"):
        render_corrections_document(view_model, public_site_url=PUBLIC_SITE_URL)


def test_corrections_nav_link_appears_only_when_the_election_has_corrections(
    tmp_path: Path,
) -> None:
    """No corrections: no nav link anywhere (issue #290, acceptance criterion
    1). With corrections: every other full page links the corrections page,
    exactly like Comparisons' own `compare_href`."""
    without = _view_model(tmp_path)
    config = read_rendering_configuration(RENDERING_CONFIG)
    guide_html_without = render_html_document(without, config)
    assert "Corrections</a>" not in guide_html_without

    enabled = without.model_copy(
        update={
            "comparisons": without.comparisons.model_copy(
                update={"policy": ComparisonsPolicy(enabled=True)}
            )
        }
    )
    with_corrections = _with_corrections(enabled)
    election_id = with_corrections.metadata.election_id
    corrections_href = f"/e/{election_id}/corrections/"
    nav_link = f'href="{corrections_href}">Corrections</a>'

    guide_html = render_html_document(with_corrections, config)
    assert nav_link in guide_html
    assert f'href="{corrections_href}" aria-current="page">Corrections</a>' not in guide_html

    sources_html = render_sources_document(with_corrections, public_site_url=PUBLIC_SITE_URL)
    assert nav_link in sources_html

    compare_html = render_comparison_document(with_corrections, public_site_url=PUBLIC_SITE_URL)
    assert nav_link in compare_html

    corrections_html = render_corrections_document(
        with_corrections, public_site_url=PUBLIC_SITE_URL
    )
    assert f'href="{corrections_href}" aria-current="page">Corrections</a>' in corrections_html
