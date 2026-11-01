"""The Corrections page's own rendering (docs/RESULTS.md, "The corrections
page"; `docs/design/RESULTS_FINALIZATION_2026-08-02.html`; issue #290)."""

from __future__ import annotations

import base64
import json
from datetime import date
from html import unescape
from pathlib import Path
from typing import cast

import pytest

from election_guide.corrections.loader import load_rendering_corrections
from election_guide.corrections.models import (
    CorrectionEntry,
    CorrectionProvenanceLink,
    ElectionCorrections,
)
from election_guide.publication.comparisons import ComparisonsPolicy
from election_guide.publication.models import PublicationViewModel
from election_guide.rendering.browser import _CdpSocket  # pyright: ignore[reportPrivateUsage]
from election_guide.rendering.config import read_rendering_configuration
from election_guide.rendering.documents import (
    render_comparison_document,
    render_corrections_document,
    render_html_document,
    render_sources_document,
)
from election_guide.rendering.shell import election_names
from tests.test_precinct_rendering import general_view as general_view
from tests.test_rendering import (
    _evaluate_in_chrome,  # pyright: ignore[reportPrivateUsage]
    _view_model,  # pyright: ignore[reportPrivateUsage]
)

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


def test_current_updates_render_metadata_filters_and_a_complete_no_script_log(
    tmp_path: Path,
) -> None:
    view_model = _view_model(tmp_path)
    corrections = _corrections(view_model.metadata.election_id)
    updates = corrections.model_dump(mode="json")
    updates["schema_version"] = "1.1"
    for entry in updates["entries"]:
        entry.update(topics=["endorsements", "results"], actions=["correction"])
    view_model = view_model.model_copy(
        update={"corrections": ElectionCorrections.model_validate(updates)}
    )
    html = render_corrections_document(view_model, public_site_url=PUBLIC_SITE_URL)
    assert "What changed in this election\u2019s endorsements, sources and results." in html
    markup = html.split("<script", 1)[0]
    assert markup.count('class="topic-button"') == 4
    assert markup.count("data-update-key=") == 2
    assert "data-client-payload" in html
    assert 'data-update-count role="status" aria-live="polite"' in html
    assert 'aria-pressed="true"' in html
    assert 'datetime="2026-08-27"' in html
    assert 'class="action-badge action-correction">Correction' in html
    assert "Illustrative example" not in html
    assert "county&#39;s amended canvass" in html


def test_real_general_log_preserves_complete_classified_entries_in_served_markup(
    general_view: PublicationViewModel,
) -> None:
    """Actual publication inputs render complete prose, without executing scripts."""
    general_view = general_view.model_copy(
        update={
            "corrections": load_rendering_corrections(
                "wa-2026-general", corrections_dir=PROJECT_ROOT / "data/corrections"
            )
        }
    )
    page = render_corrections_document(general_view, public_site_url=PUBLIC_SITE_URL)
    markup = unescape(page.split("<script", 1)[0])
    audit = json.loads((PROJECT_ROOT / "docs/audits/updates-676/classification.json").read_text())
    rows = [r for r in audit["entries"] if r["election_id"] == "wa-2026-general"]
    assert markup.count('class="corrections-entry update-entry"') == 18
    assert '<article class="corrections-entry update-entry" hidden' not in markup
    for row in rows:
        entry = row["original_entry"]
        if row["disposition"] == "software_only":
            assert entry["headline"] not in markup
            continue
        assert entry["headline"] in markup and entry["body"] in markup
        assert f'datetime="{entry["corrected_on"]}"' in markup
        for citation in entry["provenance"]:
            assert f'href="{citation["url"]}"' in markup
    assert "Illustrative example" not in markup


@pytest.mark.parametrize("width", [320, 360, 390, 1280])
def test_updates_controls_actual_geometry_keyboard_and_history(tmp_path: Path, width: int) -> None:
    view = _view_model(tmp_path)
    payload = _corrections(view.metadata.election_id).model_dump(mode="json")
    payload["schema_version"] = "1.1"
    for entry in payload["entries"]:
        entry.update(topics=["endorsements"], actions=["correction"])
    view = view.model_copy(update={"corrections": ElectionCorrections.model_validate(payload)})
    page = tmp_path / "updates.html"
    page.write_text(render_corrections_document(view, public_site_url=PUBLIC_SITE_URL))

    def keyboard(cdp: _CdpSocket, session: str) -> None:
        cdp.command(
            "Runtime.evaluate",
            {"expression": "document.querySelector('[data-update-topic=all]').focus()"},
            session_id=session,
        )
        for key, code, number in [("Tab", "Tab", 9), (" ", "Space", 32), ("Enter", "Enter", 13)]:
            cdp.command(
                "Input.dispatchKeyEvent",
                {
                    "type": "keyDown",
                    "key": key,
                    "code": code,
                    "windowsVirtualKeyCode": number,
                    **({"text": "\r" if key == "Enter" else " "} if number in {13, 32} else {}),
                },
                session_id=session,
            )
            cdp.command(
                "Input.dispatchKeyEvent",
                {"type": "keyUp", "key": key, "code": code, "windowsVirtualKeyCode": number},
                session_id=session,
            )
        screenshot = cdp.command("Page.captureScreenshot", {"format": "png"}, session_id=session)
        (tmp_path / f"updates-{width}.png").write_bytes(
            base64.b64decode(cast(str, screenshot["data"]))
        )

    result = _evaluate_in_chrome(
        page,
        """(async()=>{
      const buttons=[...document.querySelectorAll('[data-update-topic]')];
      const active=document.activeElement;
      const keyboard={topic:active.dataset.updateTopic,focused:active.matches(':focus-visible'),
        all:buttons[0].getAttribute('aria-pressed'),outline:getComputedStyle(active).outlineWidth};
      const geometry=buttons.map(b=>{
        const r=b.getBoundingClientRect(),range=document.createRange();range.selectNodeContents(b);
        const t=range.getBoundingClientRect();return {width:r.width,height:r.height,
          center:(t.left+t.right-r.left-r.right)/2,children:b.children.length};});
      const count=document.querySelector('[data-update-count]');
      buttons[1].click();buttons[3].click();
      const combined=location.search;
      await new Promise(resolve=>{
        addEventListener('popstate',resolve,{once:true});history.back();});
      const restored=buttons.filter(b=>b.getAttribute('aria-pressed')==='true')
        .map(b=>b.dataset.updateTopic);
      await new Promise(resolve=>{
        addEventListener('popstate',resolve,{once:true});history.forward();});
      const forwarded=buttons.filter(b=>b.getAttribute('aria-pressed')==='true')
        .map(b=>b.dataset.updateTopic);
      buttons[0].click();buttons[3].click();
      const empty=!document.querySelector('[data-update-empty]').hidden
        &&count.textContent==='0 updates';
      return JSON.stringify({keyboard,geometry,combined,restored,forwarded,empty,
        count:count.textContent,
        final:location.search,sameFocus:document.activeElement===active,
        sameCount:count===document.querySelector('[data-update-count]'),
        overflow:document.documentElement.scrollWidth>innerWidth});
    })()""",
        viewport=(width, 900),
        interact=keyboard,
    )
    assert result["keyboard"] == {
        "topic": "endorsements",
        "focused": True,
        "all": "true",
        "outline": "3px",
    }
    assert result["combined"] == "?topics=endorsements,results"
    assert result["restored"] == ["endorsements"]
    assert result["forwarded"] == ["endorsements", "results"]
    assert result["empty"] and result["sameFocus"] and result["sameCount"], result
    assert not result["overflow"]
    assert len(result["geometry"]) == 4
    for button in result["geometry"]:
        assert button["width"] >= 44 and button["height"] >= 44
        assert abs(button["center"]) < 1 and button["children"] == 0


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

    assert "<h1>Updates</h1>" in html
    assert '<p class="page-tagline">We get it right, eventually.</p>' in html
    assert f"<title>Updates — {election_display_name} — " in html
    assert f'<meta property="og:title" content="Updates — {election_display_name}' in html
    assert (
        f'<link rel="canonical" href="{PUBLIC_SITE_URL}'
        f'/e/{view_model.metadata.election_id}/updates/">' in html
    )
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


def test_updates_link_to_the_affected_position_without_leaving_the_preview(tmp_path: Path) -> None:
    view_model = _view_model(tmp_path)
    position_path = f"/e/{view_model.metadata.election_id}/races/ld-32-state-representative-2/"
    updates = ElectionCorrections(
        election_id=view_model.metadata.election_id,
        entries=[
            CorrectionEntry(
                corrected_on=date(2026, 10, 16),
                headline="Added a newly published endorsement.",
                body="The leading choice is unchanged; its share has changed.",
                provenance=[CorrectionProvenanceLink(label="LD32 Position 2", url=position_path)],
            )
        ],
    )
    html = render_corrections_document(
        view_model.model_copy(update={"corrections": updates}), public_site_url=PUBLIC_SITE_URL
    )

    assert f'<a href="{position_path}">LD32 Position 2</a>' in html


@pytest.mark.parametrize("unsafe_url", ["javascript:alert(1)", "//example.org/", "/\\example.org/"])
def test_render_corrections_document_rejects_an_unsafe_provenance_link(
    tmp_path: Path, unsafe_url: str
) -> None:
    view_model = _view_model(tmp_path)
    unsafe_corrections = ElectionCorrections(
        election_id=view_model.metadata.election_id,
        entries=[
            CorrectionEntry(
                corrected_on=date(2026, 7, 22),
                headline="Corrected an endorsement attribution.",
                body="The guide's recommendation was unaffected.",
                provenance=[CorrectionProvenanceLink(label="capture", url=unsafe_url)],
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
    assert "Updates</a>" not in guide_html_without

    enabled = without.model_copy(
        update={
            "comparisons": without.comparisons.model_copy(
                update={"policy": ComparisonsPolicy(enabled=True)}
            )
        }
    )
    with_corrections = _with_corrections(enabled)
    election_id = with_corrections.metadata.election_id
    corrections_href = f"/e/{election_id}/updates/"
    nav_link = f'href="{corrections_href}">Updates</a>'

    guide_html = render_html_document(with_corrections, config)
    assert nav_link in guide_html
    assert f'href="{corrections_href}" aria-current="page">Updates</a>' not in guide_html

    sources_html = render_sources_document(with_corrections, public_site_url=PUBLIC_SITE_URL)
    assert nav_link in sources_html

    compare_html = render_comparison_document(with_corrections, public_site_url=PUBLIC_SITE_URL)
    assert nav_link in compare_html

    corrections_html = render_corrections_document(
        with_corrections, public_site_url=PUBLIC_SITE_URL
    )
    assert f'href="{corrections_href}" aria-current="page">Updates</a>' in corrections_html
