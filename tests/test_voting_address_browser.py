"""Real production bundles with deterministic public-civic GIS transport, never live lookup."""

import json
from pathlib import Path

import pytest

from election_guide.publication.models import PublicationViewModel
from election_guide.rendering.browser import _CdpSocket  # pyright: ignore[reportPrivateUsage]
from election_guide.rendering.config import read_rendering_configuration
from election_guide.rendering.documents import render_comparison_document, render_html_document
from tests.test_precinct_navigation import (
    HARNESS,
    navigation_site,  # noqa: F401 # pyright: ignore[reportUnusedImport]
)
from tests.test_precinct_rendering import general_view  # noqa: F401 # pyright: ignore[reportUnusedImport]
from tests.test_rendering import _evaluate_in_chrome  # pyright: ignore[reportPrivateUsage]

ROOT = Path(__file__).resolve().parents[1]


def _address_transport_mock() -> str:
    fixture = json.loads((ROOT / "tests/fixtures/address/public-civic.json").read_text())
    return (
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
        if(url.endsWith('/suggest')) {
          if(window.suggestionMode==='failure') throw new Error('synthetic unavailable');
          const values=window.suggestionMode==='long'
            ?Array.from({length:5},(_,i)=>({text:selected+' '+('Long building label ').repeat(8)+i,
              magicKey:'synthetic-'+i,isCollection:false}))
            :window.suggestionMode==='empty'?[]:[{text:selected,
              magicKey:'public-fixture',isCollection:false}];
          response={suggestions:values};
        }
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


@pytest.mark.parametrize("page", ["guide", "compare"])
@pytest.mark.parametrize("width,height", [(390, 844), (1280, 1000), (390, 400)])
def test_address_selection_preserves_real_dialog_commit_and_geographic_views(
    tmp_path: Path,
    general_view: PublicationViewModel,  # noqa: F811
    page: str,
    width: int,
    height: int,
) -> None:
    html = (
        render_html_document(
            general_view, read_rendering_configuration(ROOT / "config/rendering/guide.yaml")
        )
        if page == "guide"
        else render_comparison_document(
            general_view,
            public_site_url="https://seattleelections.guide",
            project_url=read_rendering_configuration(
                ROOT / "config/rendering/guide.yaml"
            ).project_url,
        )
    )
    path = tmp_path / "address.html"
    mock = _address_transport_mock()
    path.write_text(html.replace("<head>", "<head><script>" + mock + "</script>", 1))

    def keyboard(cdp: _CdpSocket, session: str) -> None:
        def evaluate(script: str) -> None:
            result = cdp.command(
                "Runtime.evaluate", {"expression": script, "awaitPromise": True}, session_id=session
            )
            assert "exceptionDetails" not in result, result

        def press(name: str, code: int, modifiers: int = 0) -> None:
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

        evaluate("""(async()=>{
          document.querySelector('[data-precinct-open]').click();
          const input=document.querySelector('#voting-precinct');
          window.nativeInputVisited=false;window.nativeContained=true;
        })()""")
        press("Tab", 9, 8)
        evaluate("""window.nativeInfoFocus=document.activeElement.matches('a.precinct-info')&&
          getComputedStyle(document.activeElement).outlineStyle!=='none'&&
          parseFloat(getComputedStyle(document.activeElement).outlineWidth)>=2;""")
        press("Tab", 9)
        evaluate("""(async()=>{
          const input=document.querySelector('#voting-precinct');
          window.nativeInfoFocus&&=document.activeElement===input;
          input.value='323';input.dispatchEvent(new Event('input',{bubbles:true}));
          await new Promise(done=>setTimeout(done,400));
        })()""")
        cdp.command(
            "Emulation.setDeviceMetricsOverride",
            {"width": width, "height": 320, "deviceScaleFactor": 1, "mobile": width < 500},
            session_id=session,
        )
        evaluate("""(async()=>{
          await new Promise(requestAnimationFrame);await new Promise(requestAnimationFrame);
          const d=document.querySelector('dialog').getBoundingClientRect();
          const l=document.querySelector('[data-ballot-options]').getBoundingClientRect();
          const v=window.visualViewport;
          window.nativeViewportFit=d.top>=v.offsetTop&&d.bottom<=v.offsetTop+v.height&&
            l.top>=d.top&&l.bottom<=Math.min(d.bottom,
              document.querySelector('.precinct-actions').getBoundingClientRect().top)-8&&
            document.querySelector('dialog').style.getPropertyValue(
              '--precinct-viewport-height')===v.height+'px';
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
        evaluate("""(async()=>{
          const input=document.querySelector('#voting-precinct');input.focus();
          input.value='323';input.dispatchEvent(new Event('input',{bubbles:true}));
          await new Promise(done=>setTimeout(done,400));
        })()""")
        pointer = cdp.command(
            "Runtime.evaluate",
            {
                "expression": """(()=>{const e=document.querySelector('[role=option]');
              const r=e.getBoundingClientRect();return {x:r.x+r.width/2,y:r.y+10}})()""",
                "returnByValue": True,
            },
            session_id=session,
        )["result"]["value"]
        for kind in ["mousePressed", "mouseReleased"]:
            cdp.command(
                "Input.dispatchMouseEvent",
                {"type": kind, **pointer, "button": "left", "clickCount": 1},
                session_id=session,
            )
        evaluate("""window.nativePointerDraft=document.querySelector('dialog').open&&
          !document.querySelector('[data-precinct-submit]').disabled&&
          document.activeElement.id==='voting-precinct';""")
        press("Escape", 27)
        evaluate("""(async()=>{
          await new Promise(done=>setTimeout(done,0));
          window.nativeDialogEscape=!document.querySelector('dialog').open;
          window.nativeFocusReturned=document.activeElement===
            document.querySelector('[data-precinct-open]');
        })()""")
        cdp.command(
            "Emulation.setDeviceMetricsOverride",
            {"width": width, "height": height, "deviceScaleFactor": 1, "mobile": width < 500},
            session_id=session,
        )
        evaluate("""(async()=>{await new Promise(requestAnimationFrame);
          await new Promise(requestAnimationFrame)})()""")

        evaluate("""(async()=>{
          document.querySelector('[data-precinct-open]').click();
          const input=document.querySelector('#voting-precinct');input.value='3230';
          input.dispatchEvent(new Event('input',{bubbles:true}));
          document.querySelector('[role=option][data-kind=precinct][data-code="3230"]').click();
          document.querySelector('[data-precinct-submit]').click();
          // Native dialog close dispatches a later focus-return event. Wait for it
          // before starting a separate keyboard interaction with Ballot.
          await new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve)));
          const select=document.querySelector('#race-filter,[data-comparison-section-filter]');
          const trigger=document.querySelector('[data-filter-open=ballot]');
          trigger.focus();
          window.nativeBallotFocused=document.activeElement===trigger;
          const r=trigger.getBoundingClientRect();
          window.nativeBallotHitTarget=r.width>=40&&r.height>=40&&r.top>=0&&
            r.bottom<=innerHeight&&trigger.contains(document.elementFromPoint(r.x+r.width/2,r.y+r.height/2));
        })()""")
        press("Enter", 13)
        evaluate("""window.nativeBallotFocused&&=document.querySelector('#compact-ballot-dialog').open&&
          document.activeElement===document.querySelector(
            '#race-filter,[data-comparison-section-filter]');""")
        # Native select type-ahead: Federal is the only F-prefixed option.
        cdp.command(
            "Input.dispatchKeyEvent",
            {"type": "keyDown", "key": "f", "code": "KeyF", "windowsVirtualKeyCode": 70},
            session_id=session,
        )
        cdp.command(
            "Input.dispatchKeyEvent",
            {"type": "char", "text": "f", "unmodifiedText": "f"},
            session_id=session,
        )
        cdp.command(
            "Input.dispatchKeyEvent",
            {"type": "keyUp", "key": "f", "code": "KeyF", "windowsVirtualKeyCode": 70},
            session_id=session,
        )
        still_open = cdp.command(
            "Runtime.evaluate",
            {
                "expression": "document.querySelector('#compact-ballot-dialog').open",
                "returnByValue": True,
            },
            session_id=session,
        )["result"]["value"]
        if still_open:
            press("Enter", 13)
        evaluate("""(()=>{
          const select=document.querySelector('#race-filter,[data-comparison-section-filter]');
          const ids=[...document.querySelectorAll('[data-publication-race-id],'+
            '[data-comparison-race]')].filter(r=>!r.hidden);
          window.nativeBallotScope=select.value;
          window.nativeBallotWorks=window.nativeBallotFocused&&!select.disabled&&
            select.value==='federal'&&ids.length===1&&
            (ids[0].dataset.publicationRaceId??ids[0].dataset.comparisonRace)==='us-house-7';
          document.querySelector('[data-precinct-clear]').click();
          select.value='all';select.dispatchEvent(new Event('change',{bubbles:true}));
        })()""")

    expression = """(async () => {
      const calls=window.addressCalls;
      const contract=JSON.parse(document.querySelector('[data-client-payload]').textContent)
        .precinct_ballot;
      const wait=()=>new Promise(done=>setTimeout(done,400));
      const click=selector=>document.querySelector(selector).click();
      const before=location.search;
      click('[data-precinct-open]');
      const input=document.querySelector('#voting-precinct');
      const rect=()=>{const r=document.querySelector('dialog').getBoundingClientRect();
        return [r.x,r.y,r.width,r.height]};
      const baseline=rect();
      const statusContainer=document.querySelector('[data-precinct-status]');
      let stableGeometry=true,containedPopup=true,overlaysContent=true,longScrolls=false;
      let actionsClear=true,compactActions=true,actionsStable=true;
      const initialActionTop=document.querySelector('.precinct-actions')
        .getBoundingClientRect().top;
      const measurements=[];
      const geometry=()=>{
        const action=document.querySelector('.precinct-actions').getBoundingClientRect();
        actionsStable&&=Math.abs(action.top-initialActionTop)<1;
        const field=input.getBoundingClientRect();
        const rootFont=parseFloat(getComputedStyle(document.documentElement).fontSize);
        // Leave at most two rem beyond the maximum twelve-rem overlay, rather
        // than stretching an unused status area far below that surface.
        if(innerHeight>480) compactActions&&=action.top-field.bottom<=14*rootFont;
        measurements.push({state:window.suggestionMode??'initial',dialog:rect(),
          actionTop:action.top,inputBottom:field.bottom});
        stableGeometry&&=rect().every((n,i)=>Math.abs(n-baseline[i])<1);
        const list=document.querySelector('[data-ballot-options]');
        if(!list.hidden){
          const r=list.getBoundingClientRect();
          const d=document.querySelector('dialog').getBoundingClientRect();
          containedPopup&&=r.left>=d.left&&r.right<=d.right&&r.top>=d.top&&r.bottom<=d.bottom;
          actionsClear&&=r.bottom<=action.top-8;
          measurements.at(-1).listBottom=r.bottom;
          const privacy=document.querySelector('.address-privacy').getBoundingClientRect();
          const hit=document.elementFromPoint(r.left+r.width/2,r.top+Math.min(15,r.height/2));
          overlaysContent&&=getComputedStyle(list).position==='absolute'&&r.top<privacy.bottom&&
            list.contains(hit);
        }
      };
      geometry();
      for(const mode of ['normal','long','empty','failure']){
        window.suggestionMode=mode;
        input.value='Public civic '+mode;input.dispatchEvent(new Event('input',{bubbles:true}));
        geometry();await wait();geometry();
        if(mode==='long'){
          const list=document.querySelector('[data-ballot-options]');
          list.scrollTop=list.scrollHeight;longScrolls=list.scrollTop>0;
          geometry();
        }
      }
      window.suggestionMode='normal';
      input.value='323';input.dispatchEvent(new Event('input',{bubbles:true}));await wait();
      geometry();
      const options=[...document.querySelectorAll('[role=option]')];
      const mixed=options.some(o=>o.dataset.kind==='precinct')&&
        options.some(o=>o.dataset.kind==='address');
      const singleEditor=document.querySelectorAll('[data-precinct-control] dialog input').length===1&&
        input.getAttribute('role')==='combobox'&&!document.querySelector('datalist')&&
        !document.querySelector('[data-address-mode],[data-direct-mode]')&&
        document.querySelectorAll('dialog a').length===1;
      const info=document.querySelector('dialog a.precinct-info');
      const countyInfo=!!info&&info.href===
        'https://experience.arcgis.com/experience/1374a449f39f4cd098643466dab0826a'&&
        info.target==='_blank'&&info.rel==='noopener noreferrer'&&
        info.getAttribute('aria-label')===
          'Find your precinct on the county map (opens in a new tab)'&&
        info.title===info.getAttribute('aria-label')&&
        !info.href.includes(input.value);
      const footerIcon=document.querySelector(
        '.site-footer-actions a[aria-label="How this works"] svg');
      const modalIcon=info?.querySelector('svg');
      const sharedInfoIcon=!!modalIcon&&!!footerIcon&&modalIcon.outerHTML===footerIcon.outerHTML;
      const ir=info?.getBoundingClientRect();
      const dr=document.querySelector('dialog').getBoundingClientRect();
      const infoGeometry=!!ir&&ir.width>=44&&ir.height>=44&&ir.right<=dr.right&&
        ir.left>=dr.left+dr.width/2&&ir.top>=dr.top&&ir.bottom<=input.getBoundingClientRect().top;
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
        .textContent.toLowerCase().includes('suggestions');
      const enter=new KeyboardEvent('keydown',{key:'Enter',bubbles:true,cancelable:true});
      input.dispatchEvent(enter);
      const notFirst=enter.defaultPrevented&&
        document.querySelector('[data-precinct-submit]').disabled;
      input.dispatchEvent(new KeyboardEvent('keydown',{
        key:'ArrowUp',bubbles:true,cancelable:true}));
      input.dispatchEvent(new KeyboardEvent('keydown',{
        key:'Enter',bubbles:true,cancelable:true}));await wait();
      const draftOnly=location.search===before&&document.querySelector('dialog').open;
      geometry();
      const addressSuccessCopy=statusContainer.textContent==='Precinct: SEA 34-3230';
      const ready=!document.querySelector('[data-precinct-submit]').disabled;
      click('[data-precinct-submit]');
      const committed=new URLSearchParams(location.search).get('precinct')==='3230';
      const precinctShown=document.querySelector('[data-precinct-name]')
        .textContent==='SEA 34-3230';
      const filterRect=()=>{const r=document.querySelector('.filter-control-bar')
        .getBoundingClientRect();
        const button=document.querySelector('[data-precinct-open]').getBoundingClientRect();
        return [r.x,r.y,r.width,r.height,button.width,button.height]};
      const addressFilterRect=filterRect();
      const summaryFits=document.documentElement.scrollWidth<=innerWidth;
      const ids=()=>[...document.querySelectorAll(SELECTOR)].filter(r=>!r.hidden)
        .map(r=>r.dataset.publicationRaceId??r.dataset.comparisonRace).sort();
      const expected=contract.precincts.find(p=>p.code==='3230').contest_ids;
      const geographic=ids().length>0&&ids().every(id=>expected.includes(id));
      document.querySelector('#complete-filter,[data-comparison-all-races]').click();
      const allExact=JSON.stringify(ids())===JSON.stringify([...expected].sort());
      click('[data-precinct-open]');
      const reopenedPrecinct=input.value==='SEA 34-3230';
      input.value='323';input.dispatchEvent(new Event('input',{bubbles:true}));await wait();
      const esc=new KeyboardEvent('keydown',{key:'Escape',bubbles:true,cancelable:true});
      input.dispatchEvent(esc);
      const popupEscape=esc.defaultPrevented&&document.querySelector('dialog').open;
      click('[data-precinct-cancel]');
      const cancelPreserved=new URLSearchParams(location.search).get('precinct')==='3230'&&
        input.value===''&&document.querySelector('[data-precinct-name]')
          .textContent==='SEA 34-3230';
      const noLeak=!location.href.includes('600')&&
        localStorage.getItem('seg-precinct-v1:wa-2026-general')==='3230';
      const traverse=direction=>new Promise((resolve,reject)=>{
        const timeout=setTimeout(()=>reject(new Error('missing real '+direction)),2000);
        window.addEventListener('popstate',()=>{clearTimeout(timeout);setTimeout(resolve,20)},
          {once:true});history[direction]();
      });
      history.pushState({},'',location.href);
      click('[data-precinct-clear]');
      await traverse('back');
      const backPrecinct=document.querySelector('[data-precinct-name]')
        .textContent==='SEA 34-3230'&&
        new URLSearchParams(location.search).get('precinct')==='3230';
      await traverse('forward');
      const forwardClear=new URLSearchParams(location.search).get('precinct')==='all'&&
        document.querySelector('[data-precinct-clear]')===null;
      await traverse('back');
      const historyLabel=document.querySelector('[data-precinct-name]').textContent==='SEA 34-3230';
      click('[data-precinct-clear]');click('[data-precinct-open]');
      input.value='3230';input.dispatchEvent(new Event('input',{bubbles:true}));
      document.querySelector('[role=option][data-kind=precinct][data-code="3230"]').click();
      geometry();
      const announcement=statusContainer.querySelector('.visually-hidden');
      const directSuccessSilent=!!announcement&&
        statusContainer.textContent.replace(announcement.textContent,'').trim()===''&&
        announcement.textContent.includes('SEA 34-3230')&&
        getComputedStyle(announcement).position==='absolute'&&
        announcement.getBoundingClientRect().width<=1;
      const persistentLiveStatus=
        document.querySelector('[data-precinct-status]')===statusContainer&&
        statusContainer.getAttribute('role')==='status'&&
        statusContainer.getAttribute('aria-live')==='polite'&&!statusContainer.hidden&&
        statusContainer.getBoundingClientRect().height>0;
      click('[data-precinct-submit]');
      const localWorks=new URLSearchParams(location.search).get('precinct')==='3230'&&
        document.querySelector('[data-precinct-name]').textContent==='SEA 34-3230';
      const directFilterRect=filterRect();
      const sameFilterGeometry=addressFilterRect.every((v,i)=>Math.abs(v-directFilterRect[i])<1);
      measurements.push({state:'address-applied',filter:addressFilterRect},
        {state:'direct-applied',filter:directFilterRect});
      click('[data-precinct-clear]');
      return JSON.stringify({nativeBallotHitTarget:window.nativeBallotHitTarget,
        nativeBallotWorks:window.nativeBallotWorks,
        nativeBallotFocused:window.nativeBallotFocused,
        nativeBallotScope:window.nativeBallotScope,nativeInfoFocus:window.nativeInfoFocus,
        nativeViewportFit:window.nativeViewportFit,
        nativePointerDraft:window.nativePointerDraft,
        stableGeometry,containedPopup,overlaysContent,longScrolls,actionsClear,compactActions,actionsStable,sharedInfoIcon,
        mixed,singleEditor,countyInfo,infoGeometry,labelsFit,fits,announced,notFirst,draftOnly,
        ready,addressSuccessCopy,directSuccessSilent,persistentLiveStatus,
        committed,precinctShown,reopenedPrecinct,sameFilterGeometry,backPrecinct,forwardClear,summaryFits,geographic,allExact,popupEscape,cancelPreserved,noLeak,
        historyLabel,localWorks,nativePopupEscape:window.nativePopupEscape,
        nativeDialogEscape:window.nativeDialogEscape,nativeInputVisited:window.nativeInputVisited,
        nativeContained:window.nativeContained,nativeFocusReturned:window.nativeFocusReturned,
        anonymous:calls.length>0&&calls.every(c=>
          c.method===(c.url.endsWith('?f=json')?'GET':'POST')&&
          c.credentials==='omit'&&c.cache==='no-store'),
        clear:new URLSearchParams(location.search).get('precinct')==='all',measurements});
    })().catch(error=>JSON.stringify({error:String(error.message)}))""".replace(
        "SELECTOR",
        json.dumps("[data-publication-race-id]" if page == "guide" else "[data-comparison-race]"),
    )
    result = _evaluate_in_chrome(path, expression, viewport=(width, height), interact=keyboard)
    assert result.get("error") is None
    (tmp_path / "dialog-geometry.json").write_text(json.dumps(result, sort_keys=True))
    print(json.dumps({"page": page, "viewport": [width, height], **result}, sort_keys=True))
    measurements = result.pop("measurements", [])
    assert result and all(result.values()), json.dumps(
        {**result, "measurements": measurements}, sort_keys=True
    )


def test_address_applied_precinct_survives_real_reload(
    navigation_site: tuple[Path, str],  # noqa: F811
) -> None:
    path, url = navigation_site
    for suffix in ["", "comparisons/"]:
        page = path.parent / "e/wa-2026-general" / suffix / "index.html"
        page.write_text(
            page.read_text().replace(
                "</script>", "</script><script>" + _address_transport_mock() + "</script>", 1
            )
        )
    expression = (
        "(async()=>{"
        + HARNESS
        + """
for(const suffix of ['', 'comparisons/']) {
 localStorage.clear();
 await load('/e/wa-2026-general/'+suffix+'?precinct=all');
 doc().querySelector('[data-precinct-open]').click();
 const input=doc().querySelector('#voting-precinct');
 input.value='Public civic';
 input.dispatchEvent(new (win().Event)('input',{bubbles:true}));
 await new Promise(resolve=>setTimeout(resolve,400));
 doc().querySelector('[role=option][data-kind=address]').click();
 await new Promise(resolve=>setTimeout(resolve,100));
 equal(doc().querySelector('[data-precinct-submit]').disabled,false,'resolved address ready');
 doc().querySelector('[data-precinct-submit]').click();
 equal(doc().querySelector('[data-precinct-name]').textContent,'SEA 34-3230','address applied');
 const scope=()=>doc().querySelector('#race-filter,[data-comparison-section-filter]');
 const choices=()=>[...scope().options].map(o=>o.value);
 const addressChoices=choices();
 scope().value='city';
 scope().dispatchEvent(new (win().Event)('change',{bubbles:true}));
 const selectedIds=ids();
 const selectedURL=win().location.href;
 await load(selectedURL);
 equal(win().location.href,selectedURL,'real reload URL');
 equal(ids(),selectedIds,'real reload membership');
 equal(doc().querySelector('[data-precinct-name]').textContent,'SEA 34-3230','reload precinct');
 doc().querySelector('[data-precinct-open]').click();
 equal(doc().querySelector('#voting-precinct').value,'SEA 34-3230','reload reopened precinct');
 doc().querySelector('[data-precinct-cancel]').click();
 doc().querySelector('[data-precinct-open]').click();
 const direct=doc().querySelector('#voting-precinct');direct.value='3230';
 direct.dispatchEvent(new (win().Event)('input',{bubbles:true}));
 doc().querySelector('[role=option][data-kind=precinct][data-code="3230"]').click();
 doc().querySelector('[data-precinct-submit]').click();
 equal(choices(),addressChoices,'same address/direct options');
 equal(scope().value,'city','same address/direct valid scope');
 equal(ids(),selectedIds,'same address/direct scoped rows');
}
return JSON.stringify({failures});})()
.catch(error=>JSON.stringify({harnessError:String(error),stack:error.stack}))"""
    )
    result = _evaluate_in_chrome(path, expression, initial_url=url)
    assert result.get("harnessError") is None, result
    assert result["failures"] == [], result
