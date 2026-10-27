"""Actual headless general-page behavior against independently sourced exact sets."""

import json
from pathlib import Path

import pytest

from election_guide.normalization.models import CanonicalDataset
from election_guide.publication import build_publication_bundle
from election_guide.publication.models import PublicationViewModel
from election_guide.release.compiler import read_release_ledger
from election_guide.rendering.browser import _CdpSocket  # pyright: ignore[reportPrivateUsage]
from election_guide.rendering.config import read_rendering_configuration
from election_guide.rendering.documents import (
    render_comparison_document,
    render_html_document,
    render_race_document,
)
from election_guide.rendering.payload import GeneralSourcesPayload, SourcesPayload, sources_payload
from election_guide.rendering.validation import validate_rendered_guide
from election_guide.scoring import read_scoring_configuration, score_dataset
from election_guide.serialization import read_json
from tests.test_rendering import _evaluate_in_chrome  # pyright: ignore[reportPrivateUsage]

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def general_view() -> PublicationViewModel:
    dataset = CanonicalDataset.model_validate(
        read_json(ROOT / "data/normalized/wa-2026-general-canonical-dataset.json")
    )
    report = score_dataset(
        dataset,
        read_scoring_configuration(ROOT / "config/scoring/default.yaml"),
        computed_at=read_release_ledger(
            ROOT / "data/releases/wa-2026-general/source-decisions.yaml"
        ).data_as_of,
        allow_unresolved=True,
    )
    return build_publication_bundle(
        dataset,
        report,
        git_commit="precinct-focused-test",
        snapshot_root=ROOT / "data/releases/wa-2026-general/snapshots",
    ).view_model


@pytest.mark.parametrize("page", ["guide", "compare"])
@pytest.mark.parametrize("width", [390, 1280])
def test_general_pages_resolve_every_independent_fixture_without_horizontal_overflow(
    tmp_path: Path, general_view: PublicationViewModel, page: str, width: int
) -> None:
    html = (
        render_html_document(
            general_view, read_rendering_configuration(ROOT / "config/rendering/guide.yaml")
        )
        if page == "guide"
        else render_comparison_document(
            general_view, public_site_url="https://seattleelections.guide"
        )
    )
    path = tmp_path / f"{page}.html"
    path.write_text(html)
    fixtures = read_json(
        ROOT / "tests/fixtures/ballot/wa-2026-general-official-precinct-sets.json"
    )["fixtures"]
    public_ids = {race.id for section in general_view.guide_sections for race in section.races}
    expected = [
        {
            "name": f["representative"]["name"],
            "ids": f["selected_precinct_contest_ids"],
            "all_ids": sorted(set(f["official_applicable_SEG_covered_ids"]) & public_ids),
        }
        for f in fixtures
    ]
    expression = """(async () => {
      const fixtures=FIXTURES;
      const input=document.querySelector('#voting-precinct');
      if(!input) return JSON.stringify({error:'precinct control missing'});
      const ids=()=>[...document.querySelectorAll(SELECTOR)]
        .filter(r=>!r.hidden)
        .map(r=>r.dataset.publicationRaceId ?? r.dataset.comparisonRace).sort();
      const failures=[];
      for(const f of fixtures){
        document.querySelector('[data-precinct-open]').click();
        input.value=f.name;input.dispatchEvent(new Event('change',{bubbles:true}));
        document.querySelector('[data-precinct-submit]').click();
        const actual=ids();
        if(JSON.stringify(actual)!==JSON.stringify(f.ids))
          failures.push({name:f.name,actual,expected:f.ids});
        document.querySelector('#complete-filter,[data-comparison-all-races]').click();
        if(JSON.stringify(ids())!==JSON.stringify(f.all_ids))
          failures.push({name:f.name,mode:'all',actual:ids(),expected:f.all_ids});
        document.querySelector('#contested-filter,[data-comparison-contested]').click();
      }
      document.querySelector('[data-precinct-open]').click();
      input.value='1279';input.dispatchEvent(new Event('input',{bubbles:true}));
      document.querySelector('[data-precinct-submit]').click();
      const keyboard=input.value==='SEA 46-1279';
      const first=fixtures.find(f=>f.name==='SEA 46-1279').ids;
      const second=fixtures.find(f=>f.name==='SEA 46-2142').ids;
      history.pushState({}, '', '?precinct=2142');
      window.dispatchEvent(new Event('popstate'));
      const nextPop=()=>new Promise(resolve=>
        window.addEventListener('popstate',resolve,{once:true}));
      let arrived=nextPop();history.back();await arrived;
      const historyBack=JSON.stringify(ids())===JSON.stringify(first);
      arrived=nextPop();history.forward();await arrived;
      const historyForward=JSON.stringify(ids())===JSON.stringify(second);
      const selected=ids();
      document.querySelector('[data-precinct-clear]').click();
      return JSON.stringify({failures,keyboard,historyBack,historyForward,selected,clearIds:ids(),
        query:new URLSearchParams(window.location.search).get('precinct'),
        overflow:document.documentElement.scrollWidth>innerWidth,
        controlCount:document.querySelectorAll('input[list]').length});
    })()""".replace("FIXTURES", json.dumps(expected)).replace(
        "SELECTOR",
        json.dumps("[data-publication-race-id]" if page == "guide" else "[data-comparison-race]"),
    )
    result = _evaluate_in_chrome(path, expression, viewport=(width, 1000))
    assert result.get("error") is None
    assert result["failures"] == []
    assert result["keyboard"] is True
    assert result["historyBack"] is True
    assert result["historyForward"] is True
    assert result["query"] == "all"
    assert result["overflow"] is False
    assert result["controlCount"] == 1
    assert len(result["clearIds"]) > len(result["selected"])


@pytest.mark.parametrize("page", ["guide", "compare"])
@pytest.mark.parametrize("width", [390, 1280])
def test_precinct_modal_draft_focus_clear_and_filter_header_alignment(
    tmp_path: Path, general_view: PublicationViewModel, page: str, width: int
) -> None:
    html = (
        render_html_document(
            general_view, read_rendering_configuration(ROOT / "config/rendering/guide.yaml")
        )
        if page == "guide"
        else render_comparison_document(
            general_view, public_site_url="https://seattleelections.guide"
        )
    )
    path = tmp_path / f"modal-{page}.html"
    path.write_text(html)

    def keyboard(cdp: _CdpSocket, session: str) -> None:
        def evaluate(script: str) -> None:
            cdp.command("Runtime.evaluate", {"expression": script}, session_id=session)

        def key(name: str, code: int, modifiers: int = 0) -> None:
            for kind in ["keyDown", "keyUp"]:
                cdp.command(
                    "Input.dispatchKeyEvent",
                    {
                        "type": kind,
                        "key": name,
                        "windowsVirtualKeyCode": code,
                        "modifiers": modifiers,
                        **({"text": "\r"} if name == "Enter" and kind == "keyDown" else {}),
                    },
                    session_id=session,
                )

        evaluate("""window.beforeModalQuery=window.location.search;
          window.beforeModalMemory=localStorage.getItem('seg-precinct-v1:wa-2026-general');
          document.querySelector('[data-precinct-open]').click();
          const draftInput=document.querySelector('#voting-precinct');
          draftInput.value='2142';draftInput.dispatchEvent(new Event('input',{bubbles:true}));""")
        key("Tab", 9, 8)
        evaluate(
            "window.focusContained=document.querySelector('dialog').contains(document.activeElement)"
        )
        key("Tab", 9)
        evaluate(
            "window.forwardContained=document.querySelector('dialog').contains(document.activeElement)"
        )
        key("Escape", 27)
        evaluate("""window.escapeUnchanged=window.location.search===window.beforeModalQuery&&
          localStorage.getItem('seg-precinct-v1:wa-2026-general')===window.beforeModalMemory;
          window.escapeClosed=!document.querySelector('dialog').open;
          window.escapeRestored=document.activeElement===document.querySelector('[data-precinct-open]');
          document.querySelector('[data-precinct-open]').click();
          const commitInput=document.querySelector('#voting-precinct');
          commitInput.value='1279';commitInput.dispatchEvent(new Event('input',{bubbles:true}));""")
        key("Enter", 13)

    expression = """(()=>{
      const root=document.querySelector('[data-precinct-control]');
      const dialog=root.querySelector('dialog');
      const opener=root.querySelector('[data-precinct-open]');
      const ids=()=>[...document.querySelectorAll(
        '[data-publication-race-id],[data-comparison-race]')]
        .filter(r=>!r.hidden).map(r=>r.dataset.publicationRaceId??r.dataset.comparisonRace).sort();
      const selected=ids();const before=window.location.search;
      const center=el=>{const r=el.getBoundingClientRect();return r.top+r.height/2;};
      const bar=root.parentElement;
      const ballotCenter=center(bar.querySelector('select'));
      const viewCenter=center(bar.querySelector('.segmented-control'));
      const racesCenter=center(bar.querySelectorAll('.segmented-control')[1]);
      const precinctCenter=center(root.querySelector('.precinct-summary'));
      const bodiesCentered=Math.abs(ballotCenter-viewCenter)<=1&&
        Math.abs(racesCenter-precinctCenter)<=1;
      const countCentered=innerWidth<720||
        Math.abs(center(bar.querySelector('.filter-control-status'))-viewCenter)<=1;
      const emphasized=Number(getComputedStyle(opener).fontWeight)>=600;
      const memory=localStorage.getItem('seg-precinct-v1:wa-2026-general');
      const label=opener.textContent;
      const inRow=root.parentElement.classList.contains('filter-control-bar');
      opener.click();
      const input=root.querySelector('#voting-precinct');
      const focused=document.activeElement===input;
      const bounds=dialog.getBoundingClientRect();
      input.value='not a precinct';input.dispatchEvent(new Event('input',{bubbles:true}));
      const invalidBlocked=root.querySelector('[data-precinct-submit]').disabled&&dialog.open;
      input.value='2142';input.dispatchEvent(new Event('input',{bubbles:true}));
      const draftUnchanged=window.location.search===before&&
        JSON.stringify(ids())===JSON.stringify(selected);
      root.querySelector('[data-precinct-cancel]').click();
      const cancelUnchanged=window.location.search===before&&
        localStorage.getItem('seg-precinct-v1:wa-2026-general')===memory&&
        JSON.stringify(ids())===JSON.stringify(selected);
      const closed=!dialog.open;
      const restored=document.activeElement===root.querySelector('[data-precinct-open]');
      const headers=[...root.parentElement.querySelectorAll(':scope > div > .filter-control-label')]
        .map(el=>el.getBoundingClientRect());
      const aligned=innerWidth<720||Math.max(...headers.map(r=>r.top))-
        Math.min(...headers.map(r=>r.top))<=1;
      const clear=root.querySelector('[data-precinct-clear]');
      const accessibleClear=clear?.getAttribute('aria-label')==='Clear precinct selection';
      clear.click();
      return JSON.stringify({inRow,focused,closed,restored,invalidBlocked,draftUnchanged,
        cancelUnchanged,aligned,accessibleClear,bodiesCentered,countCentered,emphasized,
        focusContained:window.focusContained,forwardContained:window.forwardContained,escapeClosed:window.escapeClosed,
        escapeRestored:window.escapeRestored,escapeUnchanged:window.escapeUnchanged,
        keyboardCommitted:before==='?precinct=1279'&&label==='SEA 46-1279',
        clearOrdinary:window.location.search==='?precinct=all'&&ids().length>selected.length,
        clearLabel:root.querySelector('[data-precinct-open]').textContent==='Select',
        fits:bounds.left>=0&&bounds.right<=innerWidth&&bounds.height<=innerHeight,
        noOverflow:document.documentElement.scrollWidth<=innerWidth,
        headerCount:headers.length===4});
    })()"""
    result = _evaluate_in_chrome(path, expression, viewport=(width, 1000), interact=keyboard)
    assert all(result.values()), result


def test_modal_lookup_link_is_required_and_does_not_admit_other_links(
    tmp_path: Path, general_view: PublicationViewModel
) -> None:
    configuration = read_rendering_configuration(ROOT / "config/rendering/guide.yaml")
    html = render_html_document(general_view, configuration)
    lookup = "https://experience.arcgis.com/experience/1374a449f39f4cd098643466dab0826a"
    assert html.count(f'href="{lookup}"') == 1
    race_documents = {
        race.id: render_race_document(
            general_view,
            race.id,
            public_site_url=configuration.public_site_url,
            project_url=configuration.project_url,
        )
        for section in general_view.public_view().sections
        for race in section.races
    }
    cases = [
        ("original", html, True),
        ("missing", html.replace(f'href="{lookup}"', 'href=""'), False),
        ("wrong", html.replace(lookup, "https://example.test/wrong-precinct-map"), False),
        (
            "extra",
            html.replace("</body>", '<a href="https://example.test/extra">Extra</a></body>'),
            False,
        ),
    ]
    for name, document, expected in cases:
        path = tmp_path / f"{name}.html"
        path.write_text(document)
        report = validate_rendered_guide(general_view, configuration, path, [], race_documents)
        check = next(check for check in report.checks if check.id == "html-source-evidence")
        assert check.passed is expected, (name, check.message)


def test_general_race_modes_pass_the_release_screenshot_audit(
    tmp_path: Path, general_view: PublicationViewModel
) -> None:
    from election_guide.rendering.browser import find_chrome, render_screenshot

    path = tmp_path / "general.html"
    path.write_text(
        render_html_document(
            general_view, read_rendering_configuration(ROOT / "config/rendering/guide.yaml")
        )
    )
    render_screenshot(
        path,
        tmp_path / "general.png",
        find_chrome(),
        width=1280,
        height=1000,
        expected_race_count=sum(len(section.races) for section in general_view.guide_sections),
    )


def test_general_sources_capability_does_not_extend_the_legacy_payload(
    general_view: PublicationViewModel,
) -> None:
    payload = sources_payload(general_view, guide_path="/e/wa-2026-general/")
    assert isinstance(payload, GeneralSourcesPayload)
    assert payload.race_mode_query_enabled is True
    legacy = sources_payload(
        general_view.model_copy(update={"precinct_ballot": None}),
        guide_path="/e/wa-2026-general/",
    )
    assert type(legacy) is SourcesPayload
    assert "race_mode_query_enabled" not in legacy.model_dump(mode="json")
