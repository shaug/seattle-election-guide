"""Real production bundles with deterministic public-civic GIS transport, never live lookup."""

import json
from pathlib import Path

import pytest

from election_guide.publication.models import PublicationViewModel
from election_guide.rendering.browser import _CdpSocket  # pyright: ignore[reportPrivateUsage]
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

    def keyboard(cdp: _CdpSocket, session: str) -> None:
        def evaluate(script: str) -> None:
            result = cdp.command(
                "Runtime.evaluate", {"expression": script, "awaitPromise": True}, session_id=session
            )
            assert "exceptionDetails" not in result, result

        def press(name: str, code: int) -> None:
            for kind in ["keyDown", "keyUp"]:
                cdp.command(
                    "Input.dispatchKeyEvent",
                    {"type": kind, "key": name, "windowsVirtualKeyCode": code},
                    session_id=session,
                )

        evaluate("""(async()=>{
          document.querySelector('[data-precinct-open]').click();
          const input=document.querySelector('#voting-precinct');
          input.value='323';input.dispatchEvent(new Event('input',{bubbles:true}));
          await new Promise(done=>setTimeout(done,400));
          window.nativeInputVisited=false;window.nativeContained=true;
        })()""")
        press("Escape", 27)
        evaluate("""window.nativePopupEscape=document.querySelector('dialog').open&&
          document.querySelector('[role=listbox]').hidden;""")
        for _ in range(6):
            press("Tab", 9)
            evaluate("""window.nativeInputVisited ||= document.activeElement===
              document.querySelector('#voting-precinct');
              window.nativeContained &&=
                document.querySelector('dialog').contains(document.activeElement);""")
        press("Escape", 27)
        evaluate("""(async()=>{
          await new Promise(done=>setTimeout(done,0));
          window.nativeDialogEscape=!document.querySelector('dialog').open;
          window.nativeFocusReturned=document.activeElement===
            document.querySelector('[data-precinct-open]');
        })()""")

    expression = """(async () => {
      const fixture=FIXTURE;
      const calls=window.addressCalls;
      const contract=JSON.parse(document.querySelector('[data-client-payload]').textContent)
        .precinct_ballot;
      const selected=fixture.candidate.candidates[0].address;
      const wait=()=>new Promise(done=>setTimeout(done,400));
      const click=selector=>document.querySelector(selector).click();
      const before=location.search;
      click('[data-precinct-open]');
      const input=document.querySelector('#voting-precinct');
      input.value='323';input.dispatchEvent(new Event('input',{bubbles:true}));await wait();
      const options=[...document.querySelectorAll('[role=option]')];
      const mixed=options.some(o=>o.dataset.kind==='precinct')&&
        options.some(o=>o.dataset.kind==='address');
      const singleEditor=document.querySelectorAll('dialog input').length===1&&
        input.getAttribute('role')==='combobox'&&!document.querySelector('datalist')&&
        !document.querySelector('[data-address-mode],[data-direct-mode]')&&
        !document.querySelector('dialog a');
      const labelsFit=options.every(option=>{
        const text=option.querySelector('.ballot-option-text').getBoundingClientRect();
        const label=option.querySelector('.ballot-option-type');
        const r=label.getBoundingClientRect(),row=option.getBoundingClientRect();
        return r.left>=text.right&&r.right<=row.right&&
          parseFloat(getComputedStyle(label).fontSize)<parseFloat(getComputedStyle(option).fontSize);
      });
      const bounds=document.querySelector('dialog').getBoundingClientRect();
      const fits=bounds.left>=0&&bounds.right<=innerWidth&&
        document.documentElement.scrollWidth<=innerWidth;
      const announced=document.querySelector('[data-precinct-status]')
        .textContent.includes('suggestions');
      const enter=new KeyboardEvent('keydown',{key:'Enter',bubbles:true,cancelable:true});
      input.dispatchEvent(enter);
      const notFirst=enter.defaultPrevented&&
        document.querySelector('[data-precinct-submit]').disabled;
      input.dispatchEvent(new KeyboardEvent('keydown',{
        key:'ArrowUp',bubbles:true,cancelable:true}));
      input.dispatchEvent(new KeyboardEvent('keydown',{
        key:'Enter',bubbles:true,cancelable:true}));await wait();
      const draftOnly=location.search===before&&document.querySelector('dialog').open;
      const ready=!document.querySelector('[data-precinct-submit]').disabled;
      click('[data-precinct-submit]');
      const committed=new URLSearchParams(location.search).get('precinct')==='3230';
      const addressShown=document.querySelector('[data-precinct-open]').textContent===selected;
      const summaryFits=document.documentElement.scrollWidth<=innerWidth;
      const ids=()=>[...document.querySelectorAll(SELECTOR)].filter(r=>!r.hidden)
        .map(r=>r.dataset.publicationRaceId??r.dataset.comparisonRace).sort();
      const expected=contract.precincts.find(p=>p.code==='3230').contest_ids;
      const geographic=ids().length>0&&ids().every(id=>expected.includes(id));
      document.querySelector('#complete-filter,[data-comparison-all-races]').click();
      const allExact=JSON.stringify(ids())===JSON.stringify([...expected].sort());
      click('[data-precinct-open]');
      input.value='323';input.dispatchEvent(new Event('input',{bubbles:true}));await wait();
      const esc=new KeyboardEvent('keydown',{key:'Escape',bubbles:true,cancelable:true});
      input.dispatchEvent(esc);
      const popupEscape=esc.defaultPrevented&&document.querySelector('dialog').open;
      click('[data-precinct-cancel]');
      const cancelPreserved=new URLSearchParams(location.search).get('precinct')==='3230'&&
        input.value===''&&document.querySelector('[data-precinct-open]').textContent===selected;
      const noLeak=!location.href.includes('600')&&
        localStorage.getItem('seg-precinct-v1:wa-2026-general')==='3230';
      window.dispatchEvent(new Event('popstate'));
      const historyLabel=document.querySelector('[data-precinct-open]').textContent==='SEA 34-3230';
      click('[data-precinct-clear]');click('[data-precinct-open]');
      input.value='3230';input.dispatchEvent(new Event('input',{bubbles:true}));
      document.querySelector('[role=option][data-kind=precinct][data-code="3230"]').click();
      click('[data-precinct-submit]');
      const localWorks=new URLSearchParams(location.search).get('precinct')==='3230'&&
        document.querySelector('[data-precinct-open]').textContent==='SEA 34-3230';
      click('[data-precinct-clear]');
      return JSON.stringify({mixed,singleEditor,labelsFit,fits,announced,notFirst,draftOnly,
        ready,committed,addressShown,summaryFits,geographic,allExact,popupEscape,cancelPreserved,noLeak,
        historyLabel,localWorks,nativePopupEscape:window.nativePopupEscape,
        nativeDialogEscape:window.nativeDialogEscape,nativeInputVisited:window.nativeInputVisited,
        nativeContained:window.nativeContained,nativeFocusReturned:window.nativeFocusReturned,
        anonymous:calls.length>0&&calls.every(c=>
          c.method===(c.url.endsWith('?f=json')?'GET':'POST')&&
          c.credentials==='omit'&&c.cache==='no-store'),
        clear:new URLSearchParams(location.search).get('precinct')==='all'});
    })().catch(error=>JSON.stringify({error:String(error.message)}))""".replace(
        "FIXTURE", json.dumps(fixture)
    ).replace(
        "SELECTOR",
        json.dumps("[data-publication-race-id]" if page == "guide" else "[data-comparison-race]"),
    )
    result = _evaluate_in_chrome(path, expression, viewport=(width, 1000), interact=keyboard)
    assert result.get("error") is None
    assert result and all(result.values()), json.dumps(result, sort_keys=True)
