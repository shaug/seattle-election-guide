"""Real production bundles with deterministic public-civic GIS transport, never live lookup."""

import json
from pathlib import Path

import pytest

from election_guide.publication.models import PublicationViewModel
from election_guide.rendering.config import read_rendering_configuration
from election_guide.rendering.documents import render_comparison_document, render_html_document
from tests.test_precinct_rendering import general_view  # noqa: F401 # pyright: ignore[reportUnusedImport]
from tests.test_rendering import _evaluate_in_chrome  # pyright: ignore[reportPrivateUsage]

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize("page", ["guide", "compare"])
@pytest.mark.parametrize("width", [390, 1280])
def test_address_selection_preserves_real_dialog_commit_and_geographic_views(
    tmp_path: Path,
    general_view: PublicationViewModel,  # noqa: F811
    page: str,
    width: int,
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
    path = tmp_path / "address.html"
    fixture = json.loads((ROOT / "tests/fixtures/address/public-civic.json").read_text())
    mock = (
        "const fixture="
        + json.dumps(fixture)
        + ";"
        + """      const calls=window.addressCalls=[];
      window.fetch=async(url,options)=>{
        const contract=JSON.parse(
          document.querySelector('[data-client-payload]').textContent).precinct_ballot;
        const selected=fixture.candidate.candidates[0].address;
        calls.push({url,method:options.method,credentials:options.credentials,cache:options.cache});
        let response;
        if(url.endsWith('/suggest')) response={suggestions:[{text:selected
        ,magicKey:'public-fixture',isCollection:false}]};
        else if(url.endsWith('/findAddressCandidates')) response=fixture.candidate;
        else if(url.endsWith('/query')) response=url.includes('ADDRESS_POINT')
        ?fixture.site:url.includes('CITY_AREA')?fixture.city:fixture.precinct;
        else {
          const key=url.includes('ADDRESS_POINT')
        ?'address':url.includes('CITY_AREA')?'city':'precinct';
          const expected=contract.address_lookup[key];
          response={serviceItemId:expected.item
        ,editingInfo:{dataLastEditDate:expected.data,schemaLastEditDate:expected.schema_edit}};
        }
        return new Response(JSON.stringify(response));
      };
"""
    )
    path.write_text(html.replace("<head>", "<head><script>" + mock + "</script>", 1))
    expression = """(async () => {
      const fixture=FIXTURE;
      const calls=window.addressCalls;
      const payload=JSON.parse(document.querySelector('[data-client-payload]').textContent);
      const contract=payload.precinct_ballot;
      const selected=fixture.candidate.candidates[0].address;
      const wait=()=>new Promise(done=>setTimeout(done,400));
      const click=(selector)=>document.querySelector(selector).click();
      const before=location.search;
      click('[data-precinct-open]');click('[data-address-mode]');
      const input=document.querySelector('[data-address-input]');
      input.value='600 4th';input.dispatchEvent(new Event('input',{bubbles:true}));await wait();
      const status=document.querySelector('[data-precinct-status]');
      const announced=status.textContent.includes('suggestions');
      const selectKey=new KeyboardEvent('keydown',{key:'Enter',bubbles:true,cancelable:true});
      input.dispatchEvent(selectKey);
      const notFirst=selectKey.defaultPrevented
        &&document.querySelector('[data-precinct-submit]').disabled;
      input.dispatchEvent(new KeyboardEvent('keydown',{key:'ArrowDown'
        ,bubbles:true,cancelable:true}));
      input.dispatchEvent(new KeyboardEvent('keydown',{key:'Enter'
        ,bubbles:true,cancelable:true}));await wait();
      const draftOnly=location.search===before&&document.querySelector('dialog').open;
      const ready=!document.querySelector('[data-precinct-submit]').disabled;
      click('[data-precinct-submit]');
      const committed=new URLSearchParams(location.search).get('precinct')==='3230';
      const ids=()=>[...document.querySelectorAll(SELECTOR)]
        .filter(r=>!r.hidden).map(r=>r.dataset.publicationRaceId??r.dataset.comparisonRace).sort();
      const expected=contract.precincts.find(p=>p.code==='3230').contest_ids;
      const shown=ids();
      const geographic=shown.length>0&&shown.every(id=>expected.includes(id));
      document.querySelector('#complete-filter,[data-comparison-all-races]').click();
      const allExact=JSON.stringify(ids())===JSON.stringify([...expected].sort());
      click('[data-precinct-open]');click('[data-address-mode]');
      input.value='600 4th';input.dispatchEvent(new Event('input',{bubbles:true}));await wait();
      const esc=new KeyboardEvent('keydown',{key:'Escape',bubbles:true,cancelable:true})
        ;input.dispatchEvent(esc);
      const popupEscape=esc.defaultPrevented&&document.querySelector('dialog').open;
      click('[data-precinct-cancel]');
      const cancelPreserved=new URLSearchParams(location.search).get('precinct')==='3230'
        &&input.value==='';
      const noLeak=!location.href.includes('600')
        &&localStorage.getItem('seg-precinct-v1:wa-2026-general')==='3230';
      click('[data-precinct-open]');
      const bounds=document.querySelector('dialog').getBoundingClientRect();
      const fits=bounds.left>=0&&bounds.right<=innerWidth
        &&document.documentElement.scrollWidth<=innerWidth;
      click('[data-precinct-cancel]');click('[data-precinct-clear]');
      return JSON.stringify({announced,notFirst,draftOnly,ready,committed
        ,geographic,allExact,popupEscape,cancelPreserved,noLeak,fits,
        directStillPresent:!!document.querySelector('#voting-precinct'),
        anonymous:calls.length>0&&calls.every(c=>c.method===(c.url.endsWith('?f=json')
        ?'GET':'POST')&&c.credentials==='omit'&&c.cache==='no-store'),
        clear:new URLSearchParams(location.search).get('precinct')==='all'});
    })().catch(error=>JSON.stringify({error:String(error.message)}))""".replace(
        "FIXTURE", json.dumps(fixture)
    ).replace(
        "SELECTOR",
        json.dumps("[data-publication-race-id]" if page == "guide" else "[data-comparison-race]"),
    )
    result = _evaluate_in_chrome(path, expression, viewport=(width, 1000))
    assert result.get("error") is None
    assert result and all(result.values()), result
