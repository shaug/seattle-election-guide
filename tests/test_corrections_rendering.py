"""The Corrections page's own rendering (docs/RESULTS.md, "The corrections
page"; `docs/design/RESULTS_FINALIZATION_2026-08-02.html`; issue #290)."""

from __future__ import annotations

import base64
import json
import os
import threading
import time
from collections.abc import Generator
from contextlib import contextmanager
from datetime import date
from functools import partial
from html import unescape
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, cast

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


def _with_permalink_updates(view_model: PublicationViewModel) -> PublicationViewModel:
    payload = _corrections(view_model.metadata.election_id).model_dump(mode="json")
    payload["schema_version"] = "1.2"
    for entry, slug in zip(
        payload["entries"], ("amended-ld32-result", "endorsement-correction"), strict=True
    ):
        entry.update(slug=slug, topics=["results", "endorsements"], actions=["correction"])
    return view_model.model_copy(
        update={"corrections": ElectionCorrections.model_validate(payload)}
    )


def test_permalink_index_and_detail_share_the_complete_authored_entry(tmp_path: Path) -> None:
    view = _with_permalink_updates(_view_model(tmp_path))
    root = f"/e/{view.metadata.election_id}/updates/"
    index = render_corrections_document(view, public_site_url=PUBLIC_SITE_URL)
    assert f'<a href="{root}amended-ld32-result/">Amended result,' in index
    detail = render_corrections_document(
        view, public_site_url=PUBLIC_SITE_URL, entry_slug="amended-ld32-result"
    )
    markup = detail.split("<script", 1)[0]
    assert markup.count("<h1>") == 1
    assert "<h1>Amended result, State Representative (LD 32, Pos. 1).</h1>" in markup
    assert 'datetime="2026-08-27"' in markup
    assert "county&#39;s amended canvass" in markup
    assert 'href="https://example.org/captures/9f3c" target="_blank" rel="noopener"' in markup
    assert f'href="{root}?topics=results"' in markup
    assert f'href="{root}">Back to Updates</a>' in markup
    assert f'<link rel="canonical" href="{PUBLIC_SITE_URL}{root}amended-ld32-result/">' in markup
    assert 'property="og:url"' in markup and 'name="description"' in markup
    assert "data-update-controls" not in markup
    assert "Corrected an endorsement attribution." not in markup
    assert f'href="{root}" aria-current="page">Updates</a>' in markup


def test_permalink_detail_rejects_unknown_and_unsafe_identity(tmp_path: Path) -> None:
    view = _with_permalink_updates(_view_model(tmp_path))
    for slug in ("missing", "../amended-ld32-result", "%2e%2e"):
        with pytest.raises(ValueError, match="update"):
            render_corrections_document(view, public_site_url=PUBLIC_SITE_URL, entry_slug=slug)


def test_permalink_renderer_keeps_identity_when_prose_dates_and_order_change(
    tmp_path: Path,
) -> None:
    view = _with_permalink_updates(_view_model(tmp_path))
    assert view.corrections is not None
    changed = view.model_copy(deep=True)
    assert changed.corrections is not None
    changed.corrections.entries.reverse()
    entry = changed.corrections.entries[1]
    entry.headline = "Corrected headline with a different publication date."
    entry.corrected_on = date(2026, 8, 28)
    root = f"/e/{view.metadata.election_id}/updates/amended-ld32-result/"
    index = render_corrections_document(changed, public_site_url=PUBLIC_SITE_URL)
    detail = render_corrections_document(
        changed, public_site_url=PUBLIC_SITE_URL, entry_slug="amended-ld32-result"
    )
    assert f'<a href="{root}">{entry.headline}</a>' in index
    assert f'<link rel="canonical" href="{PUBLIC_SITE_URL}{root}">' in detail
    assert f"<h1>{entry.headline}</h1>" in detail


@contextmanager
def _serve_updates(root: Path) -> Generator[str]:
    server = ThreadingHTTPServer(
        ("127.0.0.1", 0), partial(SimpleHTTPRequestHandler, directory=str(root))
    )
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}"
    finally:
        server.shutdown()
        server.server_close()
        thread.join()


def _wait_for_browser(cdp: _CdpSocket, session: str, expression: str) -> None:
    deadline = time.monotonic() + 5
    observed: dict[str, Any] = {}
    while time.monotonic() < deadline:
        observed = cdp.command(
            "Runtime.evaluate",
            {"expression": expression, "returnByValue": True},
            session_id=session,
        )
        if observed.get("result", {}).get("value") is True:
            return
        time.sleep(0.025)
    pytest.fail(f"browser never reached expected navigation state: {expression}; {observed}")


@pytest.mark.parametrize("width", [320, 1280])
@pytest.mark.parametrize("scripts", [True, False])
def test_permalink_actual_detail_and_native_back_preserve_index_state(
    tmp_path: Path,
    general_view: PublicationViewModel,
    width: int,
    scripts: bool,
) -> None:
    view = general_view.model_copy(
        update={
            "corrections": load_rendering_corrections(
                general_view.metadata.election_id, corrections_dir=PROJECT_ROOT / "data/corrections"
            )
        }
    )
    assert view.corrections is not None
    slug = "cascade-il26-638-endorsement"
    entry = next(entry for entry in view.corrections.entries if entry.slug == slug)
    root = f"/e/{view.metadata.election_id}/updates/"
    index = tmp_path / root.lstrip("/") / "index.html"
    index.parent.mkdir(parents=True)
    index.write_text(render_corrections_document(view, public_site_url=PUBLIC_SITE_URL))
    detail = index.parent / slug / "index.html"
    detail.parent.mkdir()
    detail.write_text(
        render_corrections_document(view, public_site_url=PUBLIC_SITE_URL, entry_slug=slug)
    )
    observations: dict[str, Any] = {}

    def journey(cdp: _CdpSocket, session: str) -> None:
        observations["browser"] = cdp.command("Browser.getVersion")
        if not scripts:
            cdp.command("Emulation.setScriptExecutionDisabled", {"value": True}, session_id=session)
            cdp.command("Page.reload", {}, session_id=session)
            cdp.wait_event("Page.loadEventFired", session_id=session)
        else:
            _wait_for_browser(
                cdp,
                session,
                "document.querySelector('[data-update-topic=endorsements]')?.getAttribute('aria-pressed')==='true'",
            )
        _wait_for_browser(cdp, session, "document.fonts.status==='loaded'")
        prepared = cdp.command(
            "Runtime.evaluate",
            {
                "expression": f"""(()=>{{
          const link=document.querySelector('a[href="{root}{slug}/"]');
          link.focus();link.scrollIntoView({{block:'center'}});
          const visible=[...document.querySelectorAll('[data-update-key]')]
            .filter(e=>!e.hidden).map(e=>e.dataset.updateKey);
          return {{scroll:scrollY,url:location.href,visible}};
        }})()""",
                "awaitPromise": True,
                "returnByValue": True,
            },
            session_id=session,
        )
        observations["index_before"] = prepared["result"]["value"]
        for kind in ("keyDown", "keyUp"):
            cdp.command(
                "Input.dispatchKeyEvent",
                {"type": kind, "key": "Enter", "code": "Enter", "windowsVirtualKeyCode": 13},
                session_id=session,
            )
        cdp.wait_event("Page.loadEventFired", session_id=session)
        _wait_for_browser(
            cdp, session, f"location.pathname==='{root}{slug}/' && document.readyState==='complete'"
        )
        _wait_for_browser(cdp, session, "document.fonts.status==='loaded'")
        snapshot = cdp.command(
            "Runtime.evaluate",
            {
                "expression": """(()=>{
          const h=document.querySelector('h1');const box=h.getBoundingClientRect();
          return {url:location.href,canonical:document.querySelector('link[rel=canonical]').href,
            h1:h.textContent,h1Count:document.querySelectorAll('h1').length,
            date:document.querySelector('time').dateTime,body:document.querySelector('.entry-impact').textContent,
            topic:[...document.querySelectorAll('.entry-topics a')].map(a=>a.getAttribute('href')),
            controls:!!document.querySelector('[data-update-controls]'),
            width:innerWidth,scrollWidth:document.documentElement.scrollWidth,
            h1Bounds:{left:box.left,right:box.right},
            evidence:[...document.querySelectorAll('.entry-links a')]
              .map(a=>({href:a.getAttribute('href'),target:a.target,rel:a.rel}))};
        })()""",
                "awaitPromise": True,
                "returnByValue": True,
            },
            session_id=session,
        )
        observations["detail"] = snapshot["result"]["value"]
        if directory := os.environ.get("SEG_677_EVIDENCE_DIR"):
            destination = Path(directory)
            destination.mkdir(parents=True, exist_ok=True)
            shot = cdp.command("Page.captureScreenshot", {"format": "png"}, session_id=session)
            (destination / f"detail-{width}-scripts{scripts}.png").write_bytes(
                base64.b64decode(shot["data"])
            )
        cdp.command("Page.reload", {}, session_id=session)
        cdp.wait_event("Page.loadEventFired", session_id=session)
        _wait_for_browser(
            cdp, session, f"location.pathname==='{root}{slug}/' && !!document.querySelector('h1')"
        )
        cdp.command("Runtime.evaluate", {"expression": "history.back()"}, session_id=session)
        _wait_for_browser(
            cdp,
            session,
            f"location.pathname==='{root}' && !!document.querySelector('[data-update-key]')",
        )
        if scripts:
            _wait_for_browser(
                cdp,
                session,
                "document.querySelector('[data-update-topic=endorsements]')?.getAttribute('aria-pressed')==='true'",
            )

    with _serve_updates(tmp_path) as origin:
        result = _evaluate_in_chrome(
            index,
            """(()=>{
          return JSON.stringify({scroll:scrollY,url:location.href,
            visible:[...document.querySelectorAll('[data-update-key]')].filter(e=>!e.hidden).map(e=>e.dataset.updateKey)});
        })()""",
            viewport=(width, 900),
            initial_url=origin + root + "?topics=endorsements",
            interact=journey,
        )
    observations["index_after"] = result
    if directory := os.environ.get("SEG_677_EVIDENCE_DIR"):
        (Path(directory) / f"journey-{width}-scripts{scripts}.json").write_text(
            json.dumps(observations, indent=2)
        )
    before = cast(dict[str, Any], observations["index_before"])
    actual = cast(dict[str, Any], observations["detail"])
    assert actual["h1"] == entry.headline and actual["h1Count"] == 1
    assert actual["date"] == entry.corrected_on.isoformat() and actual["body"] == entry.body
    assert actual["canonical"] == PUBLIC_SITE_URL + root + slug + "/"
    assert actual["controls"] is False and actual["scrollWidth"] <= width
    assert actual["topic"] == [root + "?topics=" + topic for topic in entry.topics]
    assert len(actual["evidence"]) == len(entry.provenance)
    assert result["url"] == before["url"] and result["visible"] == before["visible"]
    assert abs(result["scroll"] - before["scroll"]) <= 2, (before, result)


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
    assert markup.count('class="topic-button"') == 3
    assert markup.count("data-update-key=") == 2
    assert "data-client-payload" in html
    assert 'data-update-count role="status" aria-live="polite"' in html
    controls = markup.split("data-update-controls", 1)[1].split("</div>", 1)[0]
    assert controls.count('aria-pressed="false"') == 3
    assert 'aria-pressed="true"' not in controls
    assert "all_label" not in html
    assert ">All updates</button>" not in markup
    assert 'role="group" aria-label="Filter updates by topic"' in markup
    assert "aria-describedby" not in controls
    assert "Choose any topics. No topics selected shows all updates." not in markup
    assert "Dates show when an update was published in this guide." not in markup
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
    assert general_view.corrections is not None
    assert markup.count('class="corrections-entry update-entry"') == len(
        general_view.corrections.entries
    )
    for current in general_view.corrections.entries:
        assert current.headline in markup and current.body in markup
        assert f'datetime="{current.corrected_on}"' in markup
        for citation in current.provenance:
            assert f'href="{citation.url}"' in markup
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
    assert "Added SGN's five state Supreme Court endorsements." in markup
    assert 'datetime="2026-11-02"' in markup
    for candidate in (
        "Colleen Melody",
        "Jaime Michelle Hawk",
        "Ian Birk",
        "Theo Angelis",
        "Debra L. Stephens",
    ):
        assert candidate in markup
    assert 'href="https://www.sgn.org/story/171606/"' in markup
    assert "Illustrative example" not in markup
    assert "Choose any topics. No topics selected shows all updates." not in markup
    assert "Dates show when an update was published in this guide." not in markup
    assert 'aria-describedby="filter-help"' not in markup


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
            {
                "expression": "document.querySelector('[data-update-topic=endorsements]').focus();"
                "window.updatesKeyboardFocusTrace=['endorsements']"
            },
            session_id=session,
        )
        for key, code, number in [
            ("Tab", "Tab", 9),
            (" ", "Space", 32),
            ("Enter", "Enter", 13),
            ("Tab", "Tab", 9),
        ]:
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
            cdp.command(
                "Runtime.evaluate",
                {
                    "expression": "window.updatesKeyboardFocusTrace.push("
                    "document.activeElement.dataset.updateTopic)"
                },
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
        pressed:buttons.map(b=>b.getAttribute('aria-pressed')),
        trace:window.updatesKeyboardFocusTrace,outline:getComputedStyle(active).outlineWidth};
      const geometry=buttons.map(b=>{
        const r=b.getBoundingClientRect(),range=document.createRange();range.selectNodeContents(b);
        const t=range.getBoundingClientRect();return {width:r.width,height:r.height,
          center:(t.left+t.right-r.left-r.right)/2,children:b.children.length,
          left:r.left,right:r.right,top:r.top,textFits:t.width<=r.width};});
      const group=document.querySelector('[data-update-controls]');
      const control=group.getBoundingClientRect();
      const accessibleGroup={role:group.getAttribute('role'),name:group.getAttribute('aria-label'),
        describedBy:group.getAttribute('aria-describedby')};
      const leadIn=[];
      for(let node=group.parentElement.nextElementSibling;
        node&&!node.querySelector('[data-update-key]');node=node.nextElementSibling){
        if(node.tagName!=='NOSCRIPT'&&!node.hidden&&getComputedStyle(node).display!=='none')
          leadIn.push({tag:node.tagName,copy:node.textContent.trim()});
      }
      const dates=[...document.querySelectorAll('[data-update-key] time')]
        .map(node=>[node.tagName,node.getAttribute('datetime')]);
      const count=document.querySelector('[data-update-count]');
      buttons[0].click();buttons[2].click();
      const combined=location.search;
      await new Promise(resolve=>{
        addEventListener('popstate',resolve,{once:true});history.back();});
      const restored=buttons.filter(b=>b.getAttribute('aria-pressed')==='true')
        .map(b=>b.dataset.updateTopic);
      await new Promise(resolve=>{
        addEventListener('popstate',resolve,{once:true});history.forward();});
      const forwarded=buttons.filter(b=>b.getAttribute('aria-pressed')==='true')
        .map(b=>b.dataset.updateTopic);
      buttons[0].click();
      const empty=!document.querySelector('[data-update-empty]').hidden
        &&count.textContent==='0 updates';
      buttons[2].click();
      const complete=buttons.every(b=>b.getAttribute('aria-pressed')==='false')
        &&document.querySelector('[data-update-empty]').hidden
        &&[...document.querySelectorAll('[data-update-key]')].every(e=>!e.hidden);
      return JSON.stringify({keyboard,geometry,control:{left:control.left,right:control.right},
        combined,restored,forwarded,empty,complete,accessibleGroup,leadIn,dates,
        count:count.textContent,
        final:location.search,sameFocus:document.activeElement===active,
        sameCount:count===document.querySelector('[data-update-count]'),
        overflow:document.documentElement.scrollWidth>innerWidth});
    })()""",
        viewport=(width, 900),
        interact=keyboard,
    )
    assert result["keyboard"] == {
        "topic": "results",
        "focused": True,
        "pressed": ["false", "false", "false"],
        "trace": ["endorsements", "sources", "sources", "sources", "results"],
        "outline": "3px",
    }
    assert result["accessibleGroup"] == {
        "role": "group",
        "name": "Filter updates by topic",
        "describedBy": None,
    }
    assert result["leadIn"] == []
    assert result["dates"] == [["TIME", "2026-08-27"], ["TIME", "2026-07-22"]]
    assert result["combined"] == "?topics=endorsements,results"
    assert result["restored"] == ["endorsements"]
    assert result["forwarded"] == ["endorsements", "results"]
    assert result["empty"] and result["complete"] and result["sameFocus"] and result["sameCount"], (
        result
    )
    assert result["final"] == "" and result["count"] == "2 updates"
    assert not result["overflow"]
    assert len(result["geometry"]) == 3
    for button in result["geometry"]:
        assert button["width"] >= 44 and button["height"] >= 44
        assert abs(button["center"]) < 1 and button["children"] == 0 and button["textFits"]
    if width < 640:
        for top in {button["top"] for button in result["geometry"]}:
            row = [button for button in result["geometry"] if button["top"] == top]
            assert abs(row[0]["left"] - result["control"]["left"]) < 1
            assert abs(row[-1]["right"] - result["control"]["right"]) < 1


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
