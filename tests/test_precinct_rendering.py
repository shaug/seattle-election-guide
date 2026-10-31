"""Actual headless general-page behavior against independently sourced exact sets."""

import json
from html.parser import HTMLParser
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
from tests.address_lookup_fixtures import without_live_address_requests
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
    path.write_text(without_live_address_requests(html))
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
        input.value=f.name;input.dispatchEvent(new Event('input',{bubbles:true}));
        input.closest('form').querySelector(
          '[role=option][data-kind=precinct]')?.click();
        document.querySelector('[data-precinct-submit]').click();
        const actual=ids();
        if(JSON.stringify(actual)!==JSON.stringify(f.ids))
          failures.push({name:f.name,actual,expected:f.ids});
        const all=document.querySelector('[data-filter-native=races]');
        all.value=[...all.options].find(o=>o.textContent.trim()==='All').value;
        all.dispatchEvent(new Event('change',{bubbles:true}));
        if(JSON.stringify(ids())!==JSON.stringify(f.all_ids))
          failures.push({name:f.name,mode:'all',actual:ids(),expected:f.all_ids});
        all.value='contested';all.dispatchEvent(new Event('change',{bubbles:true}));
      }
      document.querySelector('[data-precinct-open]').click();
      input.value='1279';input.dispatchEvent(new Event('input',{bubbles:true}));
        input.closest('form').querySelector(
          '[role=option][data-kind=precinct]')?.click();
      document.querySelector('[data-precinct-submit]').click();
      const keyboard=document.querySelector('[data-precinct-open]')
        .getAttribute('aria-label')==='Precinct: SEA 46-1279'&&input.value==='';
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
        controlCount:document.querySelectorAll('input[role=combobox]').length});
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
def test_precinct_modal_draft_focus_clear_and_compact_trigger_alignment(
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
    path.write_text(without_live_address_requests(html))

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
                        **(
                            {"text": "\r" if name == "Enter" else name}
                            if kind == "keyDown" and (name == "Enter" or len(name) == 1)
                            else {}
                        ),
                    },
                    session_id=session,
                )

        evaluate("""window.beforeModalQuery=window.location.search;
          window.beforeModalMemory=localStorage.getItem('seg-precinct-v1:wa-2026-general');
          document.querySelector('[data-precinct-open]').click();
          const draftInput=document.querySelector('#voting-precinct');
          draftInput.value='2142';draftInput.dispatchEvent(new Event('input',{bubbles:true}));
        draftInput.closest('form').querySelector(
          '[role=option][data-kind=precinct]')?.click();""")
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
          commitInput.value='1279';commitInput.dispatchEvent(new Event('input',{bubbles:true}));
        commitInput.closest('form').querySelector(
          '[role=option][data-kind=precinct]')?.click();""")
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
      const bar=root.closest('[data-compact-filters]');
      const triggers=[...bar.querySelectorAll('.compact-filter-trigger')];
      const bodiesCentered=triggers.length===4&&triggers.every(el=>
        Math.abs(center(el)-center(opener))<=1);
      const countCentered=bar.querySelector('.compact-filter-controls')
        .getBoundingClientRect().height===46;
      const emphasized=Number(getComputedStyle(opener).fontWeight)>=600;
      const memory=localStorage.getItem('seg-precinct-v1:wa-2026-general');
      const label=opener.getAttribute('aria-label');
      const inRow=root.parentElement.classList.contains('compact-filter-controls')&&
        bar.classList.contains('filter-control-bar');
      opener.click();
      const input=root.querySelector('#voting-precinct');
      const focused=document.activeElement===input;
      const bounds=dialog.getBoundingClientRect();
      input.value='not a precinct';input.dispatchEvent(new Event('input',{bubbles:true}));
        input.closest('form').querySelector(
          '[role=option][data-kind=precinct]')?.click();
      const invalidBlocked=root.querySelector('[data-precinct-submit]').disabled&&dialog.open;
      input.value='2142';input.dispatchEvent(new Event('input',{bubbles:true}));
        input.closest('form').querySelector(
          '[role=option][data-kind=precinct]')?.click();
      const draftUnchanged=window.location.search===before&&
        JSON.stringify(ids())===JSON.stringify(selected);
      root.querySelector('[data-precinct-cancel]').click();
      const cancelUnchanged=window.location.search===before&&
        localStorage.getItem('seg-precinct-v1:wa-2026-general')===memory&&
        JSON.stringify(ids())===JSON.stringify(selected);
      const closed=!dialog.open;
      const restored=document.activeElement===root.querySelector('[data-precinct-open]');
      const headers=triggers.map(el=>el.getBoundingClientRect());
      const aligned=Math.max(...headers.map(r=>r.top))-Math.min(...headers.map(r=>r.top))<=1;
      const clear=root.querySelector('[data-precinct-clear]');
      const accessibleClear=clear?.getAttribute('aria-label')==='Clear precinct selection';
      clear.click();
      return JSON.stringify({inRow,focused,closed,restored,invalidBlocked,draftUnchanged,
        cancelUnchanged,aligned,accessibleClear,bodiesCentered,countCentered,emphasized,
        focusContained:window.focusContained,forwardContained:window.forwardContained,escapeClosed:window.escapeClosed,
        escapeRestored:window.escapeRestored,escapeUnchanged:window.escapeUnchanged,
        keyboardCommitted:before==='?precinct=1279'&&label==='Precinct: SEA 46-1279',
        clearOrdinary:window.location.search==='?precinct=all'&&ids().length>selected.length,
        clearLabel:root.querySelector('[data-precinct-open]').getAttribute('aria-label')
          ==='Precinct',
        fits:bounds.left>=0&&bounds.right<=innerWidth&&bounds.height<=innerHeight,
        noOverflow:document.documentElement.scrollWidth<=innerWidth,
        headerCount:headers.length===4});
    })()"""
    result = _evaluate_in_chrome(path, expression, viewport=(width, 1000), interact=keyboard)
    assert all(result.values()), json.dumps(result, sort_keys=True)


def test_modal_requires_exact_county_info_destination(
    tmp_path: Path, general_view: PublicationViewModel
) -> None:
    configuration = read_rendering_configuration(ROOT / "config/rendering/guide.yaml")
    html = render_html_document(general_view, configuration)
    lookup = "https://experience.arcgis.com/experience/1374a449f39f4cd098643466dab0826a"
    assert html.count(f'href="{lookup}"') == 1

    class CountyInfoLinks(HTMLParser):
        def __init__(self) -> None:
            super().__init__()
            self.links: list[dict[str, str | None]] = []

        def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
            values = dict(attrs)
            if tag == "a" and "precinct-info" in (values.get("class") or "").split():
                self.links.append(values)

    # Exercise actual Jinja globals/templates in both callers, not a substituted
    # hand-built controller fixture. Removing the shared suffix must fail here.
    for document in [
        html,
        render_comparison_document(
            general_view,
            public_site_url=configuration.public_site_url,
            project_url=configuration.project_url,
        ),
    ]:
        parser = CountyInfoLinks()
        parser.feed(document)
        assert len(parser.links) == 1
        link = parser.links[0]
        expected = "Find your precinct on the county map (opens in a new tab)"
        assert link["aria-label"] == expected
        assert link["title"] == expected
        assert link["href"] == lookup
        assert link["target"] == "_blank"
        assert link["rel"] == "noopener noreferrer"
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
        (
            "missing",
            html.replace(f' href="{lookup}"', "", 1),
            False,
        ),
        (
            "wrong",
            html.replace(
                "</body>", '<a href="https://example.test/wrong-precinct-map">Map</a></body>'
            ),
            False,
        ),
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


def test_general_ballot_scopes_publish_original_covered_membership(
    general_view: PublicationViewModel,
) -> None:
    html = render_html_document(
        general_view, read_rendering_configuration(ROOT / "config/rendering/guide.yaml")
    )
    payload = json.loads(html.split("data-client-payload>")[1].split("</script>")[0])
    scopes = {scope["value"]: scope["contest_ids"] for scope in payload["filter_scopes"]}
    assert len(scopes["all"]) == 45
    assert len(scopes["state"]) == 28
    assert len(scopes["state-supreme-court"]) == 5
    assert "supreme-court-justice-1" in scopes["state"]
    assert {"initiative-26-001", "initiative-26-638", "initiative-26-645"} <= set(scopes["state"])
    assert "seattle-proposition-1-transit" in scopes["city"]
    assert "seattle-proposition-1-transit" in scopes["Citywide"]
    assert scopes["Congressional District 9"] == ["us-house-9"]


@pytest.mark.parametrize("page", ["guide", "compare"])
def test_compact_bar_owns_three_native_selects_and_own_scope_indicator(
    tmp_path: Path, general_view: PublicationViewModel, page: str
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
    path = tmp_path / f"compact-{page}.html"
    path.write_text(without_live_address_requests(html))
    result = _evaluate_in_chrome(
        path,
        """(()=>{
      const bar=document.querySelector('[data-compact-filters]');
      const triggers=[...bar.querySelectorAll('.compact-filter-trigger')];
      const selects=[...bar.querySelectorAll('[data-filter-native]')];
      const ballot=bar.querySelector('[data-filter-native=ballot]');
      const initial=!ballot.hasAttribute('data-active');
      const parity=['view','races'].every(role=>{
        const select=bar.querySelector('[data-filter-native='+role+']');
        return bar.querySelector('[data-filter-face='+role+'] .compact-filter-value')
          .textContent===select.selectedOptions[0].textContent;});
      ballot.value='county';ballot.dispatchEvent(new Event('change',{bubbles:true}));
      const active=ballot.hasAttribute('data-active')&&
        ballot.getAttribute('aria-label').includes('County');
      ballot.value='all';ballot.dispatchEvent(new Event('change',{bubbles:true}));
      return JSON.stringify({initial,parity,active,all:!ballot.hasAttribute('data-active'),
        roles:selects.map(e=>e.dataset.filterNative),
        native:selects.every(e=>e instanceof HTMLSelectElement&&e.options.length>=2),
        dialogs:bar.querySelectorAll('dialog').length,
        cancel:!!bar.querySelector('[data-filter-cancel]'),
        height:bar.querySelector('.compact-filter-controls').getBoundingClientRect().height,
        targets:triggers.every(b=>b.getBoundingClientRect().height>=44&&b.getBoundingClientRect().width>=44),
        icons:triggers.every(b=>b.querySelector('svg[aria-hidden=true]'))});})()""",
        viewport=(390, 900),
    )
    assert result == {
        "initial": True,
        "parity": True,
        "active": True,
        "all": True,
        "roles": ["view", "races", "ballot"],
        "native": True,
        "dialogs": 1,
        "cancel": False,
        "height": 46,
        "targets": True,
        "icons": True,
    }


@pytest.mark.parametrize("page", ["guide", "compare"])
@pytest.mark.parametrize("screen_sans", [None, "system-ui", "sans-serif"])
def test_compact_bar_fits_real_values_and_measures_container_transition(
    tmp_path: Path, general_view: PublicationViewModel, page: str, screen_sans: str | None
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
    path = tmp_path / f"fit-{page}.html"
    path.write_text(without_live_address_requests(html))
    expression = """(async () => {
      await document.fonts.ready;
      const bar=document.querySelector('[data-compact-filters]');
      if(SCREEN_SANS)bar.style.setProperty('--screen-sans',SCREEN_SANS);
      const settle=()=>new Promise(r=>requestAnimationFrame(()=>requestAnimationFrame(r)));
      const inspect=()=>{const box=bar.getBoundingClientRect();
        const buttons=[...bar.querySelectorAll('.compact-filter-trigger')];
        const values=buttons.flatMap(b=>[...b.querySelectorAll('.compact-filter-value')])
          .filter(el=>getComputedStyle(el).display!=='none');
        return {width:box.width,
          height:bar.querySelector('.compact-filter-controls').getBoundingClientRect().height,
          cue:bar.dataset.cues,spacing:bar.dataset.spacing,
          scope:bar.querySelector('[data-filter-native=ballot]').value,
          ownActive:bar.querySelector('[data-filter-native=ballot]').hasAttribute('data-active'),
          ownDotVisible:getComputedStyle(bar.querySelector('.compact-filter-dot'))
            .visibility==='visible',
          dotClear:(()=>{const d=bar.querySelector('.compact-filter-dot').getBoundingClientRect();
            const b=bar.querySelector('[data-filter-trigger=ballot] > div'),i=b.querySelector('svg')
              .getBoundingClientRect();
            return d.right<=i.left||d.left>=i.right||d.bottom<=i.top||d.top>=i.bottom;})(),
          labelsSeparated:values.every((el,index)=>{if(!index)return true;
            const left=document.createRange(),right=document.createRange();
            left.selectNodeContents(values[index-1]);right.selectNodeContents(el);
            return right.getBoundingClientRect().left-left.getBoundingClientRect().right>=2;}),
          wholeLines:values.every(el=>{const r=document.createRange();r.selectNodeContents(el);
            return r.getClientRects().length===1;}),
          iconsClear:buttons.every(b=>{const icon=b.querySelector('svg').getBoundingClientRect();
            return [...b.querySelectorAll('.compact-filter-value')]
              .filter(e=>getComputedStyle(e).display!=='none').every(e=>{
                const r=document.createRange();r.selectNodeContents(e);
                const text=r.getBoundingClientRect();
                return icon.right<=text.left+.1||icon.bottom<=text.top+.1;});}),
          fits:buttons.every(b=>b.getBoundingClientRect().right<=box.right+.1),
          values:values.map(el=>el.textContent),
          textFits:values.every(el=>{const r=document.createRange();r.selectNodeContents(el);
            return r.getBoundingClientRect().width<=el.getBoundingClientRect().width+.1;}),
          aggregate:buttons.reduce((sum,b)=>sum+b.getBoundingClientRect().width,0)+
            bar.querySelectorAll('.compact-filter-slot').length,
          allIcons:buttons.every(b=>b.querySelector('svg').getBoundingClientRect().width>=14),
          fontSize:buttons.every(b=>getComputedStyle(b).fontSize==='14px'),
          targets:buttons.every(b=>b.getBoundingClientRect().height>=44&&b.getBoundingClientRect().width>=44),
          exclusive:buttons.every(b=>{const value=[...b.querySelectorAll('.compact-filter-value')]
            .find(el=>getComputedStyle(el).display!=='none');
            const arrow=getComputedStyle(b.querySelector('.compact-filter-arrow')).display!=='none';
            return arrow!==getComputedStyle(value).textDecorationLine.includes('underline');})};};
      document.querySelector('[data-precinct-open]').click();
      const input=document.querySelector('#voting-precinct');
      input.value='SEA 46-1279';input.dispatchEvent(new Event('input',{bubbles:true}));
      document.querySelector('[data-code="1279"]').click();
      document.querySelector('[data-precinct-submit]').click();
      const compact=document.querySelector('[data-filter-native=view]');
      if(compact.options.namedItem('compact')||[...compact.options].some(o=>o.value==='compact')){
        compact.value='compact';compact.dispatchEvent(new Event('change',{bubbles:true}));}
      const samples=[];
      for(const width of [280,300,320,360,390]){bar.style.width=width+'px';await settle();
        samples.push(inspect());}
      const transitions=[];
      for(let width=300;width<=450;width++){bar.style.width=width+'px';await settle();
        if(bar.dataset.cues==='arrows'){transitions.push(inspect());
          bar.style.width=(width-1)+'px';await settle();
          transitions.unshift(inspect());break;}}
      const activeSamples=[];
      const select=bar.querySelector('[data-filter-native=ballot]');
      select.value='county';select.dispatchEvent(new Event('change',{bubbles:true}));
      for(const width of [280,300,320]){bar.style.width=width+'px';await settle();
        const b=bar.querySelector('[data-filter-trigger=ballot] > div');
        const dot=b.querySelector('.compact-filter-dot'),r=dot.getBoundingClientRect();
        const text=b.querySelector('.compact-filter-value').getBoundingClientRect();
        activeSamples.push({...inspect(),indicator:b.hasAttribute('data-active')&&
          getComputedStyle(dot).visibility==='visible'&&r.width>=5&&r.height>=5&&
          r.left>=b.getBoundingClientRect().left&&r.right<=b.getBoundingClientRect().right&&
          (r.bottom<=text.top||r.left>=text.right)});}
      const name=document.querySelector('[data-precinct-open]').getAttribute('aria-label');
      const differingSamples=[];
      const differing=document.querySelector('[data-filter-native=view]');
      if([...differing.options].some(o=>o.value==='differing')){
        document.querySelector('[data-precinct-clear]').click();
        differing.value='differing';differing.dispatchEvent(new Event('change',{bubbles:true}));
        for(const width of [280,300,320,360,390]){bar.style.width=width+'px';await settle();
          differingSamples.push(inspect());}}
      return JSON.stringify({samples,activeSamples,differingSamples,transitions,name,
        viewport:innerWidth});
    })()"""
    expression = expression.replace("SCREEN_SANS", json.dumps(screen_sans))
    result = _evaluate_in_chrome(path, expression, viewport=(1280, 1000))
    (tmp_path / f"{page}-fit.json").write_text(json.dumps(result, indent=2) + "\n")
    assert result["name"] == "Precinct: SEA 46-1279"
    assert result["viewport"] == 1280
    assert all(
        s["fits"]
        and s["textFits"]
        and s["wholeLines"]
        and s["labelsSeparated"]
        and s["iconsClear"]
        and s["dotClear"]
        and s["fontSize"]
        and s["height"] == 46
        and s["aggregate"] <= s["width"]
        and s["targets"]
        and s["allIcons"]
        and s["exclusive"]
        for s in result["samples"] + result["activeSamples"] + result["differingSamples"]
    ), json.dumps(result)
    assert all(s["height"] == 46 for s in result["samples"]), result
    assert result["transitions"][0]["cue"] == "underlines", result
    assert result["transitions"][1]["cue"] == "arrows", result
    assert all(s["fits"] and s["exclusive"] for s in result["transitions"]), result
    assert all("46-1279" in s["values"] for s in result["samples"]), result
    expected_view = "Compact" if page == "guide" else "Full"
    assert all(
        s["values"] == ["46-1279", expected_view, "Contested", "Ballot"]
        for s in result["samples"] + result["activeSamples"]
    ), result
    assert all(not s["ownActive"] and not s["ownDotVisible"] for s in result["samples"]), result
    assert all(
        s["scope"] == "county" and s["ownActive"] and s["ownDotVisible"]
        for s in result["activeSamples"] + result["differingSamples"]
    ), result
    assert all(s["indicator"] for s in result["activeSamples"]), result
    if page == "compare":
        assert all("Differing" in s["values"] for s in result["differingSamples"]), result


@pytest.mark.parametrize("page", ["guide", "compare"])
@pytest.mark.parametrize("width", [320, 360, 390])
def test_native_selection_escape_preserves_value_and_tab_reaches_next_control(
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
    path = tmp_path / f"keyboard-{page}.html"
    path.write_text(without_live_address_requests(html))

    def keyboard(cdp: _CdpSocket, session: str) -> None:
        def ev(source: str) -> None:
            result = cdp.command("Runtime.evaluate", {"expression": source}, session_id=session)
            assert "exceptionDetails" not in result, result

        def key(name: str, code: int) -> None:
            for kind in ["keyDown", "keyUp"]:
                cdp.command(
                    "Input.dispatchKeyEvent",
                    {"type": kind, "key": name, "windowsVirtualKeyCode": code},
                    session_id=session,
                )

        ev(
            "window.beforeNative=location.href;document.querySelector('[data-filter-native=view]').focus()"
        )
        key(" ", 32)
        key("ArrowDown", 40)
        key("Escape", 27)
        ev(
            "window.nativeRetained=document.activeElement===document.querySelector('[data-filter-native=view]')"
        )
        key("Tab", 9)

    result = _evaluate_in_chrome(
        path,
        """JSON.stringify({sameURL:location.href===beforeNative,
      retained:nativeRetained,next:document.activeElement===document.querySelector('[data-filter-native=races]'),
      view:document.querySelector('[data-filter-native=view]').value,
      dialogs:document.querySelectorAll('dialog').length,
      overflow:document.documentElement.scrollWidth>innerWidth})""",
        viewport=(width, 844),
        interact=keyboard,
    )
    assert result == {
        "sameURL": True,
        "retained": True,
        "next": True,
        "view": "full",
        "dialogs": 1,
        "overflow": False,
    }, result


@pytest.mark.parametrize("page", ["guide", "compare"])
def test_wide_compact_bar_shows_selected_ballot_scope_and_constrained_bar_keeps_identity(
    tmp_path: Path, general_view: PublicationViewModel, page: str
) -> None:
    document = (
        render_html_document(
            general_view, read_rendering_configuration(ROOT / "config/rendering/guide.yaml")
        )
        if page == "guide"
        else render_comparison_document(
            general_view, public_site_url="https://seattleelections.guide"
        )
    )
    path = tmp_path / f"wide-scope-{page}.html"
    path.write_text(without_live_address_requests(document))
    expression = """(async()=>{
      await document.fonts.ready;
      const bar=document.querySelector('[data-compact-filters]');
      const select=bar.querySelector('[data-filter-native=ballot]');
      const settle=()=>new Promise(r=>requestAnimationFrame(()=>requestAnimationFrame(r)));
      const inspect=()=>{const b=bar.querySelector('[data-filter-trigger=ballot] > div');
        const visible=[...b.querySelectorAll('span')].filter(e=>
          getComputedStyle(e).display!=='none'&&e.getBoundingClientRect().width>0);
        const rect=b.getBoundingClientRect(),box=bar.getBoundingClientRect();
        return {text:visible.map(e=>e.textContent).join(' '),
          fits:rect.right<=box.right+.1,
          height:bar.querySelector('.compact-filter-controls').getBoundingClientRect().height,active:b.hasAttribute('data-active'),
          name:b.getAttribute('aria-label')};};
      const cases=[];
      for(const scope of ['county','state-supreme-court']){
        select.value=scope;select.dispatchEvent(new Event('change',{bubbles:true}));
        await settle();cases.push(inspect());
      }
      const wide=inspect();
      bar.style.width='320px';await settle();const narrow=inspect();
      const unchanged=select.value==='state-supreme-court';
      bar.style.width='100%';await settle();const restored=inspect();
      return JSON.stringify({cases,wide,narrow,restored,unchanged,
        identity:bar.querySelector('[data-precinct-open]').getAttribute('aria-label')});
    })()"""
    result = _evaluate_in_chrome(
        path, expression, viewport=(1280, 1000), initial_url=path.as_uri() + "?precinct=3230"
    )
    assert result["identity"] == "Precinct: SEA 34-3230"
    assert "County" in result["cases"][0]["text"], result
    assert "State Supreme Court" in result["wide"]["text"], result
    assert "State Supreme Court" not in result["narrow"]["text"], result
    assert "Ballot" in result["narrow"]["text"], result
    assert "State Supreme Court" in result["restored"]["text"], result
    assert result["unchanged"], result
    assert all(
        x["fits"] and x["height"] == 46 and x["active"]
        for x in [*result["cases"], result["narrow"], result["restored"]]
    ), result
    assert all("State Supreme Court" in result[k]["name"] for k in ["wide", "narrow", "restored"])


@pytest.mark.parametrize("page", ["guide", "compare"])
def test_open_precinct_editor_tracks_viewport_and_anchor_without_changing_choice(
    tmp_path: Path, general_view: PublicationViewModel, page: str
) -> None:
    opener = "[data-precinct-open]"
    dialog_id = "precinct-dialog"
    cancel = "[data-precinct-cancel]"
    document = (
        render_html_document(
            general_view, read_rendering_configuration(ROOT / "config/rendering/guide.yaml")
        )
        if page == "guide"
        else render_comparison_document(
            general_view, public_site_url="https://seattleelections.guide"
        )
    )
    path = tmp_path / f"moving-{page}-precinct.html"
    path.write_text(without_live_address_requests(document))

    def exercise(cdp: _CdpSocket, session: str) -> None:
        def evaluate(source: str) -> object:
            result = cdp.command(
                "Runtime.evaluate",
                {"expression": source, "awaitPromise": True, "returnByValue": True},
                session_id=session,
            )
            assert "exceptionDetails" not in result, result
            return result["result"].get("value")

        evaluate("""const scope=document.querySelector(
          '#race-filter,[data-comparison-section-filter]');
          scope.value='state-supreme-court';scope.dispatchEvent(new Event('change',{bubbles:true}));
          window.editorURL=location.href;
          window.editorState=[...document.querySelectorAll('[data-filter-native]')].map(x=>x.value);
          window.editorPhases=[];""")
        point = evaluate(
            "(()=>{const b=document.querySelector('OPENER');"
            "const r=b.getBoundingClientRect();"
            "return {x:r.x+r.width/2,y:r.y+r.height/2}})()".replace("OPENER", opener)
            .replace("DIALOG", dialog_id)
            .replace("CANCEL", cancel)
        )
        assert isinstance(point, dict)
        for kind in ["mousePressed", "mouseReleased"]:
            cdp.command(
                "Input.dispatchMouseEvent",
                {"type": kind, **point, "button": "left", "clickCount": 1},
                session_id=session,
            )
        evaluate(
            """window.openEditor=document.querySelector('#DIALOG');
          if(window.openEditor.id==='precinct-dialog'){
            const input=window.openEditor.querySelector('input');
            input.value='1279';input.dispatchEvent(new Event('input',{bubbles:true}));}
          window.editorFocus=document.activeElement;
          const anchor=document.querySelector('OPENER').getBoundingClientRect();
          window.editorAttached=Math.abs(window.openEditor.getBoundingClientRect().top-anchor.bottom-3)<1;
          window.editorBackdrop=getComputedStyle(window.openEditor,'::backdrop').backgroundColor;
          window.recordEditor=async phase=>{
            await new Promise(r=>requestAnimationFrame(()=>requestAnimationFrame(r)));
            const d=window.openEditor,v=visualViewport,r=d.getBoundingClientRect();
            const controls=[...d.querySelectorAll(
              'select,input[role=combobox],.segmented-control label,'+
              '[data-precinct-submit],.ballot-option,CANCEL')];
            let reachable=true,textFits=true;const unreachable=[];
            for(const c of controls){c.scrollIntoView({block:'nearest'});
              const text=c.querySelector('span');
              if(text)textFits&&=text.scrollWidth<=text.clientWidth+1;
              const b=c.getBoundingClientRect();
              const hit=b.top>=Math.max(r.top,v.offsetTop)-.5&&
                b.bottom<=Math.min(r.bottom,v.offsetTop+v.height)+.5&&
                b.left>=v.offsetLeft-.5&&b.right<=v.offsetLeft+v.width+.5;
              if(!hit)unreachable.push({tag:c.tagName,id:c.id,text:c.textContent,box:b.toJSON()});
              reachable&&=hit;}
            window.editorPhases.push({phase,open:d.open,reachable,textFits,unreachable,
              fits:r.left>=v.offsetLeft-.5&&r.right<=v.offsetLeft+v.width+.5&&
                r.top>=v.offsetTop-.5&&r.bottom<=v.offsetTop+v.height+.5,
              focus:document.activeElement===window.editorFocus,
              scope:scope.value,url:location.href===window.editorURL,
              checked:JSON.stringify(window.editorState)===JSON.stringify(
                [...document.querySelectorAll('[data-filter-native]')].map(x=>x.value))});
          };
          window.recordEditor('opened-before-resize');""".replace("OPENER", opener)
            .replace("DIALOG", dialog_id)
            .replace("CANCEL", cancel)
        )
        for width, height in [(390, 844), (844, 320), (320, 240)]:
            cdp.command(
                "Emulation.setDeviceMetricsOverride",
                {"width": width, "height": height, "deviceScaleFactor": 1, "mobile": False},
                session_id=session,
            )
            evaluate(f"window.recordEditor('{width}x{height}')")
        cdp.command("Emulation.setPageScaleFactor", {"pageScaleFactor": 2}, session_id=session)
        evaluate("window.recordEditor('visual-viewport-zoom')")
        cdp.command("Emulation.setPageScaleFactor", {"pageScaleFactor": 1}, session_id=session)
        cdp.command(
            "Emulation.setDeviceMetricsOverride",
            {"width": 1280, "height": 1000, "deviceScaleFactor": 1, "mobile": False},
            session_id=session,
        )
        evaluate(
            """(async()=>{
          await new Promise(r=>requestAnimationFrame(()=>requestAnimationFrame(r)));
          const bar=document.querySelector('[data-compact-filters]');
          window.oldEditorTop=window.openEditor.getBoundingClientRect().top;
          bar.style.transform='translateY(90px)';
          await window.recordEditor('anchor-moved-without-resize');
          window.anchorFollowed=Math.abs(window.openEditor.getBoundingClientRect().top-
            window.oldEditorTop-90)<1;
          window.openEditor.querySelector('CANCEL').click();
        })()""".replace("CANCEL", cancel)
        )

    result = _evaluate_in_chrome(
        path,
        """(()=>JSON.stringify({attached:window.editorAttached,backdrop:window.editorBackdrop,
          phases:window.editorPhases,anchor:window.anchorFollowed,
          closed:!window.openEditor.open,
          returned:document.activeElement===document.querySelector('OPENER')}))()""".replace(
            "OPENER", opener
        ),
        viewport=(1280, 1000),
        interact=exercise,
    )
    assert result["attached"] and result["backdrop"] == "rgba(0, 0, 0, 0)", result
    assert result["closed"] and result["returned"], result
    assert all(
        p["open"]
        and p["fits"]
        and p["reachable"]
        and p["textFits"]
        and p["focus"]
        and p["url"]
        and p["checked"]
        and p["scope"] == "state-supreme-court"
        for p in result["phases"]
    ), json.dumps(result)
    assert result["anchor"], json.dumps(result)


@pytest.mark.parametrize("page", ["guide", "compare"])
def test_scott_preview_empty_precinct_and_ballot_editor_are_unambiguous(
    tmp_path: Path, general_view: PublicationViewModel, page: str
) -> None:
    document = (
        render_html_document(
            general_view, read_rendering_configuration(ROOT / "config/rendering/guide.yaml")
        )
        if page == "guide"
        else render_comparison_document(
            general_view, public_site_url="https://seattleelections.guide"
        )
    )
    path = tmp_path / f"preview-labels-{page}.html"
    path.write_text(without_live_address_requests(document))
    result = _evaluate_in_chrome(
        path,
        """(()=>{const bar=document.querySelector('[data-compact-filters]');
          const button=bar.querySelector('[data-precinct-open]');
          const empty=[...button.querySelectorAll('.compact-filter-value')]
            .filter(e=>getComputedStyle(e).display!=='none').map(e=>e.textContent).join(' ');
          const select=bar.querySelector('[data-filter-native=ballot]');
          select.focus();
          const result={empty,name:button.getAttribute('aria-label'),
            duplicate:!!bar.querySelector('[data-compact-scope-detail]'),
            selectNamed:[...select.labels].some(l=>l.textContent.trim()==='Ballot'),
            heading:select.getAttribute('aria-label'),
            value:select.value};
          result.returned=document.activeElement===select;
          button.click();result.selectAction=document.querySelector('[data-precinct-submit]').textContent;
          document.querySelector('[data-precinct-cancel]').click();
          return JSON.stringify(result);})()""",
        viewport=(1280, 1000),
    )
    assert result == {
        "empty": "Precinct",
        "name": "Precinct",
        "duplicate": False,
        "selectNamed": True,
        "heading": "Ballot: All ballot races",
        "value": "all",
        "returned": True,
        "selectAction": "Select",
    }


@pytest.mark.parametrize("page", ["guide", "compare"])
@pytest.mark.parametrize("width", [300, 320, 360, 390, 1280])
@pytest.mark.parametrize("screen_sans", [None, "system-ui", "sans-serif"])
def test_scott_preview_centers_controls_and_keeps_reactive_count_together(
    tmp_path: Path,
    general_view: PublicationViewModel,
    page: str,
    width: int,
    screen_sans: str | None,
) -> None:
    document = (
        render_html_document(
            general_view, read_rendering_configuration(ROOT / "config/rendering/guide.yaml")
        )
        if page == "guide"
        else render_comparison_document(
            general_view, public_site_url="https://seattleelections.guide"
        )
    )
    if screen_sans:
        document = document.replace(
            "<head>",
            f"<head><style>[data-compact-filters]{{--screen-sans:{screen_sans}}}</style>",
            1,
        )
    path = tmp_path / f"preview-count-{page}.html"
    path.write_text(without_live_address_requests(document))
    expression = """(async()=>{await document.fonts.ready;
      const bar=document.querySelector('[data-compact-filters]');
      const select=bar.querySelector('[data-filter-native=ballot]');
      const status=bar.querySelector('.filter-control-status');
      const settle=()=>new Promise(r=>requestAnimationFrame(()=>requestAnimationFrame(r)));
      const samples=[];
      const inspect=phase=>{const buttons=[...bar.querySelectorAll('.compact-filter-trigger')];
        const first=buttons[0].getBoundingClientRect(),last=buttons.at(-1).getBoundingClientRect();
        const group={left:first.left,right:last.right,top:first.top,bottom:first.bottom};
        const box=bar.getBoundingClientRect(),r=status.getBoundingClientRect();
        const count=status.querySelector('.filter-status-part')??status;
        const range=document.createRange();range.selectNodeContents(count);
        const visible=[...document.querySelectorAll(
          '[data-publication-race-id],[data-comparison-race]')]
          .filter(e=>!e.hidden&&e.getClientRects().length>0).length;
        const countText=count.textContent,reported=Number.parseInt(countText,10);
        const inline=r.bottom<=group.bottom+.1;
        const adjacent=document.querySelector('.site-band').getBoundingClientRect();
        samples.push({phase,reported,visible,countText,
          ballotValues:[...bar.querySelectorAll(
            '[data-filter-trigger=ballot] .compact-filter-value')]
            .filter(e=>getComputedStyle(e).display!=='none').map(e=>e.textContent),
          scopeActive:bar.querySelector('[data-filter-native=ballot]').hasAttribute('data-active'),
          centered:Math.abs((group.left+group.right-box.left-box.right)/2)<.6,
          adjacentCentered:Math.abs((group.left+group.right-adjacent.left-adjacent.right)/2)<.6,
          control46:buttons.every(b=>b.getBoundingClientRect().height===46),
          countVisible:getComputedStyle(status).clipPath==='none'&&r.width>20&&r.height>10,
          whole:range.getClientRects().length===1&&range.getBoundingClientRect().width<=r.width+.5,
          placed:inline?r.left>=group.right&&r.right<=box.right+.1:
            r.top>=group.bottom&&Math.abs((r.left+r.right-box.left-box.right)/2)<.6,
          inline,barHeight:box.height,noOverflow:document.documentElement.scrollWidth<=innerWidth});};
      await settle();inspect('initial');
      select.value='county';select.dispatchEvent(new Event('change',{bubbles:true}));
      await settle();inspect('county');
      select.value='all';select.dispatchEvent(new Event('change',{bubbles:true}));
      const all=document.querySelector('[data-filter-native=races]');
        all.value=[...all.options].find(o=>o.textContent.trim()==='All').value;
        all.dispatchEvent(new Event('change',{bubbles:true}));
      await settle();inspect('all-races');
      select.value='county';select.dispatchEvent(new Event('change',{bubbles:true}));
      await settle();inspect('county-all-races');
      select.value='all';select.dispatchEvent(new Event('change',{bubbles:true}));
      document.querySelector('[data-precinct-open]').click();
      const input=document.querySelector('#voting-precinct');input.value='SEA 46-1279';
      input.dispatchEvent(new Event('input',{bubbles:true}));
      document.querySelector('[data-code="1279"]').click();
      document.querySelector('[data-precinct-submit]').click();await settle();inspect('precinct');
      select.value='legislative-46';select.dispatchEvent(new Event('change',{bubbles:true}));
      await settle();inspect('invalid-scope-fallback');
      document.querySelector('[data-precinct-clear]').click();await settle();inspect('clear');
      const differing=document.querySelector('[data-filter-native=view]');
      if([...differing.options].some(o=>o.value==='differing')){differing.value='differing';
        differing.dispatchEvent(new Event('change',{bubbles:true}));
        await settle();inspect('differing');}
      history.pushState({},'', '?precinct=2142');dispatchEvent(new PopStateEvent('popstate'));
      await settle();inspect('url-precinct');
      const nextPop=()=>new Promise(r=>addEventListener('popstate',r,{once:true}));
      let arrived=nextPop();history.back();await arrived;await settle();inspect('history-back');
      arrived=nextPop();history.forward();await arrived;await settle();inspect('history-forward');
      return JSON.stringify({samples});})()"""
    result = _evaluate_in_chrome(path, expression, viewport=(width, 1000))
    (tmp_path / f"{page}-preview-count.json").write_text(json.dumps(result, indent=2) + "\n")
    assert all(
        s["reported"] == s["visible"]
        and s["centered"]
        and s["adjacentCentered"]
        and s["control46"]
        and s["countVisible"]
        and s["whole"]
        and s["placed"]
        and s["noOverflow"]
        for s in result["samples"]
    ), json.dumps(result)
    assert result["samples"][0]["inline"] == (width == 1280), result
    assert len({s["reported"] for s in result["samples"]}) > 1, result

    assert result["samples"][0]["ballotValues"] == (
        ["All ballot races"] if width == 1280 else ["Ballot"]
    ), result
    assert not result["samples"][0]["scopeActive"], result

    if width < 1280:
        assert all(s["ballotValues"] == ["Ballot"] for s in result["samples"]), result


@pytest.mark.parametrize("page", ["guide", "compare"])
@pytest.mark.parametrize("screen_sans", [None, "system-ui"])
def test_scott_ballot_value_is_wide_only_and_own_scope_dot_survives_compaction(
    tmp_path: Path, general_view: PublicationViewModel, page: str, screen_sans: str | None
) -> None:
    document = (
        render_html_document(
            general_view, read_rendering_configuration(ROOT / "config/rendering/guide.yaml")
        )
        if page == "guide"
        else render_comparison_document(
            general_view, public_site_url="https://seattleelections.guide"
        )
    )
    if screen_sans:
        document = document.replace(
            "<head>", "<head><style>[data-compact-filters]{--screen-sans:system-ui}</style>", 1
        )
    path = tmp_path / f"preview-ballot-{page}.html"
    path.write_text(without_live_address_requests(document))
    expression = """(async()=>{await document.fonts.ready;
      const bar=document.querySelector('[data-compact-filters]');
      const select=bar.querySelector('[data-filter-native=ballot]');
      const settle=()=>new Promise(r=>requestAnimationFrame(()=>requestAnimationFrame(r)));
      const samples=[];
      for(const [scope,label] of [['all','All ballot races'],['county','County'],
        ['state-supreme-court','State Supreme Court']]){
        select.value=scope;select.dispatchEvent(new Event('change',{bubbles:true}));
        for(const width of [1280,320]){bar.style.width=width+'px';await settle();
          const button=bar.querySelector('[data-filter-trigger=ballot] > div');
          const values=[...button.querySelectorAll('.compact-filter-value,.compact-ballot-scope')]
            .filter(e=>getComputedStyle(e).display!=='none').map(e=>e.textContent);
          select.focus();
          const named=[...select.labels].some(e=>e.textContent.trim()==='Ballot');
          const current=select.selectedOptions[0].textContent.trim();
          const payload=JSON.parse(
            document.querySelector('script[data-client-payload]').textContent);
          const payloadLabel=payload.filter_scopes?.find(s=>s.value===scope)?.label??null;
          const dot=button.querySelector('.compact-filter-dot');
          samples.push({scope,label,width,values,current,named,payloadLabel,
            active:button.hasAttribute('data-active'),
            dotVisible:getComputedStyle(dot).visibility==='visible',
            name:button.getAttribute('aria-label'),
            duplicate:!!bar.querySelector('[data-compact-scope-detail]'),
            returned:document.activeElement===select,
            fits:button.getBoundingClientRect().right<=bar.getBoundingClientRect().right+.1});
        }
      }
      select.value='county';select.dispatchEvent(new Event('change',{bubbles:true}));
      document.querySelector('[data-precinct-clear]').click();await settle();
      const clearRetainsOwnScope=select.value==='county'&&
        bar.querySelector('[data-filter-trigger=ballot] > div').hasAttribute('data-active');
      select.value='all';select.dispatchEvent(new Event('change',{bubbles:true}));await settle();
      const allInactive=!select.hasAttribute('data-active');
      return JSON.stringify({samples,clearRetainsOwnScope,allInactive});})()"""
    result = _evaluate_in_chrome(
        path,
        expression,
        viewport=(1280, 1000),
        initial_url=path.as_uri() + "?precinct=1279",
    )
    (tmp_path / f"{page}-preview-ballot.json").write_text(json.dumps(result, indent=2) + "\n")
    assert all(
        s["values"] == ([s["label"]] if s["width"] == 1280 else ["Ballot"])
        and s["current"] == s["label"]
        and (s["payloadLabel"] == s["label"] if page == "guide" else True)
        and s["named"]
        and s["active"] == (s["scope"] != "all")
        and s["dotVisible"] == (s["scope"] != "all")
        and s["label"] in s["name"]
        and not s["duplicate"]
        and s["returned"]
        and s["fits"]
        for s in result["samples"]
    ), json.dumps(result)
    assert result["clearRetainsOwnScope"] and result["allInactive"], result


@pytest.mark.parametrize("page", ["guide", "compare"])
@pytest.mark.parametrize("font", [None, "system-ui", "sans-serif"])
def test_complete_control_families_keep_track_edges_stable(
    tmp_path: Path, general_view: PublicationViewModel, page: str, font: str | None
) -> None:
    document = (
        render_html_document(
            general_view, read_rendering_configuration(ROOT / "config/rendering/guide.yaml")
        )
        if page == "guide"
        else render_comparison_document(
            general_view, public_site_url="https://seattleelections.guide"
        )
    )
    path = tmp_path / "stable.html"
    path.write_text(without_live_address_requests(document))
    script = """(async()=>{await document.fonts.ready;
      const bar=document.querySelector('[data-compact-filters]');
      if(FONT)bar.style.setProperty('--screen-sans',FONT);
      const settle=()=>new Promise(r=>requestAnimationFrame(()=>requestAnimationFrame(r)));
      const read=()=>({mode:[bar.dataset.cues,bar.dataset.spacing,
        bar.dataset.precinctDisplay,bar.dataset.ballotDetail],
        edges:[...bar.querySelectorAll('.compact-filter-trigger')].map(e=>{
          const r=e.getBoundingClientRect();return [r.left,r.right,r.width];})});
      const samples=[];
      for(const width of [280,300,320,360,390,1280]){
        bar.style.width=width+'px';await settle();const before=read();
        for(const native of bar.querySelectorAll(
          '[data-filter-native=view],[data-filter-native=races]')){
          for(const option of native.options){native.value=option.value;
            native.dispatchEvent(new Event('change',{bubbles:true}));
            await settle();samples.push({width,before,after:read()});}}
        const select=bar.querySelector('[data-filter-native=ballot]');
        for(const value of ['county','all']){select.value=value;
          select.dispatchEvent(new Event('change',{bubbles:true}));await settle();
          samples.push({width,before,after:read()});}
        document.querySelector('[data-precinct-clear]').click();await settle();
        samples.push({width,before,after:read()});
        document.querySelector('[data-precinct-open]').click();
        const input=document.querySelector('#voting-precinct');input.value='1279';
        input.dispatchEvent(new Event('input',{bubbles:true}));
        document.querySelector('[data-code="1279"]').click();
        document.querySelector('[data-precinct-submit]').click();await settle();
      }return JSON.stringify({samples});})()""".replace("FONT", json.dumps(font))
    result = _evaluate_in_chrome(
        path, script, viewport=(1400, 1000), initial_url=path.as_uri() + "?precinct=1279"
    )
    assert all(s["before"] == s["after"] for s in result["samples"]), json.dumps(result)


@pytest.mark.parametrize("code", ["1273", "1279"])
def test_precinct_compare_native_view_history_and_shared_sources_remain_independent(
    tmp_path: Path, general_view: PublicationViewModel, code: str
) -> None:
    html = render_comparison_document(
        general_view, public_site_url="https://seattleelections.guide"
    )
    path = tmp_path / "independent-view.html"
    path.write_text(without_live_address_requests(html))
    payload = json.loads(html.split("data-client-payload>")[1].split("</script>")[0])
    panel = payload["personalization"]
    fragment = (
        f"#cmp=1&cols=strnstim&panel={panel['panel_id']}&ph={panel['panel_hash'][:12]}"
        f"&data={payload['data_version']}&scoring=unweighted-progressive-v1&diff=1&show=county"
    )

    def interact(cdp: _CdpSocket, session: str) -> None:
        def ev(script: str) -> object:
            r = cdp.command(
                "Runtime.evaluate",
                {"expression": script, "awaitPromise": True, "returnByValue": True},
                session_id=session,
            )
            assert "exceptionDetails" not in r, r
            return r["result"].get("value")

        def key(name: str, number: int) -> None:
            for kind in ["keyDown", "keyUp"]:
                cdp.command(
                    "Input.dispatchKeyEvent",
                    {
                        "type": kind,
                        "key": name,
                        "windowsVirtualKeyCode": number,
                        **(
                            {"text": "\r" if name == "Enter" else name}
                            if kind == "keyDown" and (name == "Enter" or len(name) == 1)
                            else {}
                        ),
                    },
                    session_id=session,
                )

        observe = """window.take=async phase=>{
          await document.fonts.ready;
          await new Promise(r=>requestAnimationFrame(()=>requestAnimationFrame(r)));
          const rows=[...document.querySelectorAll('[data-comparison-race]')];
          const ids=rows.map(e=>e.dataset.comparisonRace);
          const cells=Object.fromEntries(rows.map(e=>[e.dataset.comparisonRace,
            [...e.querySelectorAll('[data-column-signal]')].map(c=>[c.dataset.columnSignal,c.textContent])]));
          const view=document.querySelector('[data-filter-native=view]');
          samples.push({phase,url:location.href,ids,cells,columns:[...document.querySelectorAll(
            '[data-comparison-head] [data-column-signal]')].map(e=>e.dataset.columnSignal),
            full:view.value==='full',diff:view.value==='differing',enabled:!view.disabled,
            scope:document.querySelector('[data-comparison-section-filter]').value,
            count:document.querySelector('[data-comparison-status]').textContent});}"""
        ev("window.samples=[];" + observe + ";take('direct-differing-county')")
        ev("document.querySelector('[data-filter-native=view]').focus()")
        key("f", 70)
        assert ev("document.querySelector('[data-filter-native=view]').value") == "full"
        ev("take('native-full')")
        ev("document.querySelector('[data-filter-native=view]').focus()")
        # Native select type-ahead groups rapid letters into one search. Allow
        # that platform search session to expire before a separate user choice.
        ev("new Promise(resolve=>setTimeout(resolve,1200))")
        key("d", 68)
        assert ev("document.querySelector('[data-filter-native=view]').value") == "differing"
        ev("take('native-differing')")
        other = "1279" if code == "1273" else "1273"
        ev(
            """(()=>{document.querySelector('[data-precinct-open]').click();
          const i=document.querySelector('#voting-precinct');i.value='OTHER';
          i.dispatchEvent(new Event('input',{bubbles:true}));
          document.querySelector('[data-code="OTHER"]').click();
          document.querySelector('[data-precinct-submit]').click();})()""".replace("OTHER", other)
        )
        ev("take('changed-precinct')")
        # Filter choices replace their current entry. Establish two explicit shared-URL
        # entries before exercising real Back/Forward, rather than leaving the document.
        ev(
            """(()=>{const forward=location.href,back=samples.find(s=>s.phase==='native-full').url;
            history.pushState({},'',back);
            dispatchEvent(new PopStateEvent('popstate'));
            history.pushState({},'',forward);
            dispatchEvent(new PopStateEvent('popstate'));
            })()"""
        )
        ev(
            """(async()=>{const p=new Promise(r=>addEventListener('popstate',r,{once:true}));
            history.back();
            await p;
            await take('back-full');
            })()"""
        )
        ev(
            """(async()=>{const p=new Promise(r=>addEventListener('popstate',r,{once:true}));
            history.forward();
            await p;
            await take('forward-differing');
            })()"""
        )
        before = ev("JSON.stringify(samples)")
        cdp.command("Page.reload", {}, session_id=session)
        cdp.wait_event("Page.loadEventFired", session_id=session)
        ev("window.samples=" + str(before) + ";")
        ev(observe + ";take('reloaded')")
        ev("""(()=>{const view=document.querySelector('[data-filter-native=view]');
          view.value='full';view.dispatchEvent(new Event('change',{bubbles:true}));
          const s=document.querySelector('[data-comparison-section-filter]');s.value='all';
          s.dispatchEvent(new Event('change',{bubbles:true}));})()
          """)
        ev("take('full-measures')")
        ev(
            "const view=document.querySelector('[data-filter-native=view]');"
            "view.value='differing';view.dispatchEvent(new Event('change',{bubbles:true}));"
            "take('differing-measures')"
        )
        ev("""(()=>{const s=document.querySelector('[data-comparison-section-filter]');
          s.value='county';s.dispatchEvent(new Event('change',{bubbles:true}));})()""")

        ev(
            """document.querySelector('[data-precinct-open]').click();
            document.querySelector('[data-precinct-clear]').click();
            take('clear-keeps-differing')"""
        )
        ev(
            """history.replaceState({},'',location.pathname+'?precinct=not-real'+location.hash);
            dispatchEvent(new PopStateEvent('popstate'));
            take('invalid-fallback')"""
        )

    result = _evaluate_in_chrome(
        path,
        "JSON.stringify({samples})",
        viewport=(390, 844),
        initial_url=path.as_uri() + f"?precinct={code}" + fragment,
        interact=interact,
    )
    samples = result["samples"]
    assert len(samples) == 11, result
    measures = {"initiative-26-645", "initiative-26-001", "initiative-26-638"}
    full = next(s for s in samples if s["phase"] == "full-measures")
    differing = next(s for s in samples if s["phase"] == "differing-measures")
    assert all(full["cells"][k] == v for k, v in differing["cells"].items()), result
    for s in samples:
        assert s["enabled"] and s["columns"] == ["strn", "stim"], result
        for binding in [
            "cols=strnstim",
            f"panel={panel['panel_id']}",
            f"ph={panel['panel_hash'][:12]}",
            f"data={payload['data_version']}",
            "scoring=unweighted-progressive-v1",
        ]:
            assert binding in s["url"], result
        if s["phase"] == "full-measures":
            assert s["scope"] == "all" and s["full"] and not s["diff"], result
            assert measures <= set(s["ids"]), result
            continue
        if s["phase"] == "differing-measures":
            assert s["scope"] == "all" and s["diff"] and not s["full"], result
            assert not measures & set(s["ids"]), result
            continue
        assert s["scope"] == "county" and "show=county" in s["url"], result
        if s["phase"] in ["native-full", "back-full"]:
            assert s["full"] and not s["diff"] and s["ids"] == ["king-county-assessor"], result
        elif s["phase"] in ["clear-keeps-differing", "invalid-fallback"]:
            assert s["diff"] and s["ids"] == ["king-county-council-2", "king-county-council-8"], (
                result
            )
        else:
            assert s["diff"] and not s["full"] and s["ids"] == [], result
            assert "0 of 1" in s["count"], result


@pytest.mark.parametrize("page", ["guide", "compare"])
@pytest.mark.parametrize("width", [300, 390, 1280])
def test_view_races_ballot_are_real_native_selects_without_editors(
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
    path = tmp_path / "native-selects.html"
    path.write_text(without_live_address_requests(html))

    def interact(cdp: _CdpSocket, session: str) -> None:
        def ev(script: str) -> object:
            r = cdp.command(
                "Runtime.evaluate",
                {"expression": script, "returnByValue": True, "awaitPromise": True},
                session_id=session,
            )
            assert "exceptionDetails" not in r, r
            return r["result"].get("value")

        def key(name: str, number: int, text: str = "") -> None:
            for kind in ["keyDown", "keyUp"]:
                cdp.command(
                    "Input.dispatchKeyEvent",
                    {
                        "type": kind,
                        "key": name,
                        "windowsVirtualKeyCode": number,
                        **({"text": text} if text and kind == "keyDown" else {}),
                    },
                    session_id=session,
                )

        ready = ev("""(()=>{
          const controls=[...document.querySelectorAll('select[data-filter-native]')];
          return controls.length===3&&controls.every(e=>e.options.length>=2)&&
          document.querySelectorAll('dialog').length===1&&!document.querySelector('[data-filter-cancel]');})()""")
        assert ready, "View/Races/Ballot must be native selects; only Precinct retains a dialog"
        ev(
            "document.fonts.ready.then(()=>new Promise(r=>"
            "requestAnimationFrame(()=>requestAnimationFrame(r))))"
        )
        ev("""document.querySelector('[data-compact-filters]').addEventListener('change',e=>{
          (window.nativeChanges??=[]).push({trusted:e.isTrusted,role:e.target.dataset.filterNative});
        });document.querySelector('[data-filter-native=view]').focus();""")
        key(
            "c" if page == "guide" else "d",
            67 if page == "guide" else 68,
            "c" if page == "guide" else "d",
        )
        ev("new Promise(r=>requestAnimationFrame(()=>requestAnimationFrame(r)))")
        ev("window.nativeView=document.querySelector('[data-filter-native=view]').value")
        ev("document.querySelector('[data-filter-native=races]').focus()")
        key("a", 65, "a")
        ev("new Promise(r=>requestAnimationFrame(()=>requestAnimationFrame(r)))")
        point = ev("""(()=>{const s=document.querySelector('[data-filter-native=ballot]');
          const r=s.getBoundingClientRect();
          window.nativeHit=document.elementFromPoint(r.x+r.width/2,r.y+r.height/2)===s;
          return {x:r.x+r.width/2,y:r.y+r.height/2};})()""")
        assert isinstance(point, dict)
        for kind in ["mousePressed", "mouseReleased"]:
            cdp.command(
                "Input.dispatchMouseEvent",
                {"type": kind, **point, "button": "left", "clickCount": 1},
                session_id=session,
            )
        key("c", 67, "c")
        key("Enter", 13, "\r")
        ev("new Promise(r=>requestAnimationFrame(()=>requestAnimationFrame(r)))")
        tree = cdp.command("Accessibility.getFullAXTree", {}, session_id=session)
        combos = [n for n in tree["nodes"] if n.get("role", {}).get("value") == "combobox"]
        assert len(combos) == 3, combos
        assert sorted((n["name"]["value"], n["value"]["value"]) for n in combos) == sorted(
            [
                (
                    "View: Compact" if page == "guide" else "View: Differing",
                    "Compact" if page == "guide" else "Differing",
                ),
                ("Races: All", "All"),
                ("Ballot filter active: County", "County"),
            ]
        ), combos

    result = _evaluate_in_chrome(
        path,
        """JSON.stringify({nativeView,hit:nativeHit,nativeChanges,
      url:location.href,
      view:document.querySelector('[data-filter-native=view]').value,
      races:document.querySelector('[data-filter-native=races]').value,
      ballot:document.querySelector('[data-filter-native=ballot]').value,
      focus:document.activeElement===document.querySelector('[data-filter-native=ballot]'),
      row:document.querySelector('.compact-filter-controls').getBoundingClientRect().height,
      dialogs:document.querySelectorAll('dialog').length,
      overflow:document.documentElement.scrollWidth>innerWidth})""",
        viewport=(width, 844),
        initial_url=path.as_uri() + "?precinct=1273",
        interact=interact,
    )
    assert result["nativeView"] == ("compact" if page == "guide" else "differing"), result
    assert result["view"] == result["nativeView"] and result["races"] in ["complete", "all"], result
    assert result["ballot"] == "county" and result["hit"] and result["focus"], result
    assert result["nativeChanges"] == [
        {"trusted": True, "role": "view"},
        {"trusted": True, "role": "races"},
        {"trusted": True, "role": "ballot"},
    ], result
    assert (
        "races=all" in result["url"]
        and ("filter=county" if page == "guide" else "show=county") in result["url"]
    ), result
    assert result["row"] == 46 and result["dialogs"] == 1 and not result["overflow"], result
