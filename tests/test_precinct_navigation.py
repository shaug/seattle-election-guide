"""Real navigation regressions: query membership and source/fragment state travel together."""

import functools
import json
import threading
from collections.abc import Iterator
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

from election_guide.inventory.importer import read_inventory
from election_guide.inventory.precinct_ballot import CATALOG_PATH, read_precinct_catalog
from election_guide.publication.models import PublicationViewModel
from election_guide.rendering.config import read_rendering_configuration
from election_guide.rendering.documents import (
    render_comparison_document,
    render_html_document,
    render_sources_document,
)
from tests.address_lookup_fixtures import without_live_address_requests
from tests.test_precinct_rendering import general_view as general_view
from tests.test_rendering import _evaluate_in_chrome  # pyright: ignore[reportPrivateUsage]


@pytest.fixture
def navigation_site(
    tmp_path: Path, general_view: PublicationViewModel
) -> Iterator[tuple[Path, str]]:
    root = Path(__file__).resolve().parents[1]
    pages = {
        "": render_html_document(
            general_view, read_rendering_configuration(root / "config/rendering/guide.yaml")
        ),
        "sources/": render_sources_document(
            general_view, public_site_url="https://seattleelections.guide"
        ),
        "comparisons/": render_comparison_document(
            general_view, public_site_url="https://seattleelections.guide"
        ),
    }
    for suffix, html in pages.items():
        path = tmp_path / "e/wa-2026-general" / suffix / "index.html"
        path.parent.mkdir(parents=True, exist_ok=True)
        # Test-only storage failure in every newly navigated child document.
        html = html.replace(
            "<head>",
            "<head><script>if(parent.blockStorage)Object.defineProperty(window,"
            "'localStorage',{get(){throw new Error('blocked by test')}});</script>",
            1,
        )
        path.write_text(without_live_address_requests(html))
    harness = tmp_path / "harness.html"
    harness.write_text('<!doctype html><iframe id="page"></iframe>')
    handler = functools.partial(SimpleHTTPRequestHandler, directory=str(tmp_path))
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield harness, f"http://127.0.0.1:{server.server_port}/harness.html"
    finally:
        server.shutdown()
        thread.join()
        server.server_close()


HARNESS = """
const frame=document.querySelector('#page');
const load=url=>new Promise(resolve=>{
  frame.onload=()=>setTimeout(resolve,20);
  if(frame.contentWindow.location.href===new URL(url,location.href).href)
    frame.contentWindow.location.reload();
  else frame.src=url;
});
const doc=()=>frame.contentDocument;
const win=()=>frame.contentWindow;
const ids=()=>[...doc().querySelectorAll('[data-publication-race-id], [data-comparison-race]')]
  .filter(r=>!r.hidden).map(r=>r.dataset.publicationRaceId??r.dataset.comparisonRace).sort();
const click=selector=>new Promise(resolve=>{
  frame.onload=()=>setTimeout(resolve,20);doc().querySelector(selector).click();
});
const failures=[];
const equal=(actual,expected,label)=>{
  if(JSON.stringify(actual)!==JSON.stringify(expected))failures.push({label,actual,expected});
};
const key='seg-precinct-v1:wa-2026-general';
"""


def test_sources_navigation_preserves_query_membership_without_relying_on_memory(
    navigation_site: tuple[Path, str],
) -> None:
    path, url = navigation_site
    expression = (
        "(async()=>{"
        + HARNESS
        + """
for(const mode of ['empty','blocked','different']) {
 for(const query of ['precinct=1279','precinct=all','precinct=unknown',
                     'precinct=1279&precinct=2142','precinct=2142']) {
  for(const action of ['save','cancel','page-reset']) {
   parent.blockStorage=mode==='blocked';
   localStorage.clear();if(mode==='different')localStorage.setItem(key,'2200');
   await load('/e/wa-2026-general/?'+query+'&unrelated=discard');
   // A later picker change must update both Sources links, not only boot links.
   if(query==='precinct=2142') {
    doc().querySelector('[data-precinct-open]').click();
    const input=doc().querySelector('#voting-precinct');input.value='1279';
    input.dispatchEvent(new (win().Event)('input',{bubbles:true}));
  doc().querySelector('[role=option][data-kind=precinct]')?.click();
  doc().querySelector('[role=option][data-kind=precinct]')?.click();
    doc().querySelector('[data-precinct-submit]').click();
   }
   const expectedQuery=query==='precinct=2142'?'precinct=1279':query;
   const originalIds=ids();
   const initialHash=win().location.hash;
   const originalMemory=localStorage.getItem(key);
   const sources=[...doc().querySelectorAll('[data-sources-link]')].map(a=>a.href);
   for(const href of sources)equal(new URL(href).search,'?'+expectedQuery,
     'Sources destination '+mode+query);
   await click('[data-sources-link]');
   equal(win().location.search,'?'+expectedQuery,'editor query '+mode+query);
   const boxes=[...doc().querySelectorAll('[data-sources-source]')];
   const source=boxes.find(b=>b.checked);source.checked=false;
   source.dispatchEvent(new (win().Event)('change',{bubbles:true}));
   const returnHref=doc().querySelector('[data-sources-'+action+']').href;
   const target=new URL(returnHref);
   equal(target.pathname,'/e/wa-2026-general/','complete return path');
   equal(target.search,'?'+expectedQuery,'return query '+action+mode+query);
   if(action==='cancel')equal(target.hash,initialHash,'Cancel fragment');
   if(action==='page-reset')equal(target.hash,'','Reset fragment');
   if(action==='save'&&!target.hash)failures.push({label:'Save must carry edited sources'});
   await click('[data-sources-'+action+']');
   equal(win().location.pathname+win().location.search+win().location.hash,
     target.pathname+target.search+target.hash,'actual return URL');
   equal(ids(),originalIds,'membership '+action+mode+query);
   equal(localStorage.getItem(key),originalMemory,'shared navigation does not persist query');
   const banner=doc().querySelector('[data-lens-banner-status]').textContent;
   if(action==='save'&&banner.includes('Counting all'))
     failures.push({label:'Save source preference lost'});
   const returned=win().location.href;
   await load(returned);
   equal(ids(),originalIds,'reload membership '+action+mode+query);
   equal(doc().querySelector('[data-lens-banner-status]').textContent,banner,
     'reload source preference');
   equal(win().location.href,returned,'reload URL');
  }
 }
}
return JSON.stringify({failures});})()
.catch(error=>JSON.stringify({harnessError:String(error),stack:error.stack}))"""
    )
    result = _evaluate_in_chrome(path, expression, initial_url=url)
    assert result.get("harnessError") is None, result
    assert result["failures"] == [], result


def test_comparison_history_resolves_incoming_query_before_fragment_policy(
    navigation_site: tuple[Path, str],
) -> None:
    path, url = navigation_site
    expression = (
        "(async()=>{"
        + HARNESS
        + """
for(const query of ['', 'precinct=all','precinct=unknown']) {
 parent.blockStorage=query!=='';localStorage.clear();
 await load('/e/wa-2026-general/comparisons/?'+query);
 const section=doc().querySelector('[data-comparison-section-filter]');
 section.value=[...section.options].find(o=>o.value!=='all').value;
 section.dispatchEvent(new (win().Event)('change',{bubbles:true}));
 for(const selector of ['[data-comparison-contested]','[data-comparison-differences]']) {
  doc().querySelector(selector).checked=true;
  doc().querySelector(selector).dispatchEvent(new (win().Event)('change',{bubbles:true}));
 }
 const columns=()=>[...doc().querySelectorAll('[data-comparison-head] [data-column-signal]')]
   .map(h=>h.dataset.columnSignal);
 const ordinary={url:win().location.href,ids:ids(),columns:columns(),section:section.value};
 doc().querySelector('.comparison-presets a').click();
 doc().querySelector('[data-precinct-open]').click();
    const input=doc().querySelector('#voting-precinct');input.value='1279';
 input.dispatchEvent(new (win().Event)('input',{bubbles:true}));
  doc().querySelector('[role=option][data-kind=precinct]')?.click();
  doc().querySelector('[role=option][data-kind=precinct]')?.click();
    doc().querySelector('[data-precinct-submit]').click();
 const selected={url:win().location.href,ids:ids(),columns:columns()};
 const traverse=direction=>new Promise(resolve=>{
  const timeout=setTimeout(()=>{
    failures.push({label:'missing real '+direction+' popstate'});resolve();
  },1000);
  win().addEventListener('popstate',()=>{clearTimeout(timeout);setTimeout(resolve,20);},{once:true});
  win().history[direction]();
 });
 await traverse('back');
 equal(win().location.href,ordinary.url,'Back exact historical URL '+query);
 equal(ids(),ordinary.ids,'Back ordinary membership '+query);
 equal(columns(),ordinary.columns,'Back columns '+query);
 equal(doc().querySelector('[data-comparison-section-filter]').value,
   ordinary.section,'Back section');
 equal(doc().querySelector('[data-comparison-contested]').checked,true,'Back contested');
 equal(doc().querySelector('[data-comparison-differences]').checked,true,'Back differences');
 await traverse('forward');
 equal(win().location.href,selected.url,'Forward exact selected URL');
 equal(ids(),selected.ids,'Forward selected membership');
 equal(columns(),selected.columns,'Forward columns');
 await traverse('back');await load(win().location.href);
 equal(win().location.href,ordinary.url,'reload historical URL');
 equal(ids(),ordinary.ids,'reload ordinary membership');
 equal(columns(),ordinary.columns,'reload columns');
}
return JSON.stringify({failures});})()
.catch(error=>JSON.stringify({harnessError:String(error),stack:error.stack}))"""
    )
    result = _evaluate_in_chrome(path, expression, initial_url=url)
    assert result.get("harnessError") is None, result
    assert result["failures"] == [], result


def test_bare_guide_cross_view_history_remains_ordinary_after_memory_changes(
    navigation_site: tuple[Path, str],
) -> None:
    path, url = navigation_site
    expression = (
        "(async()=>{"
        + HARNESS
        + """
parent.blockStorage=false;localStorage.clear();
await load('/e/wa-2026-general/?view=compact');
const original={url:win().location.href,ids:ids(),
  sources:doc().querySelector('[data-lens-banner-status]').textContent};
await click('[data-precinct-link="comparisons"]');
doc().querySelector('[data-precinct-open]').click();
    const input=doc().querySelector('#voting-precinct');input.value='1279';
input.dispatchEvent(new (win().Event)('input',{bubbles:true}));
  doc().querySelector('[role=option][data-kind=precinct]')?.click();
  doc().querySelector('[role=option][data-kind=precinct]')?.click();
    doc().querySelector('[data-precinct-submit]').click();
const selected={url:win().location.href,ids:ids(),
  columns:[...doc().querySelectorAll('[data-comparison-head] [data-column-signal]')]
    .map(h=>h.dataset.columnSignal)};
equal(localStorage.getItem(key),'1279','picker saves usable memory');
const traverse=direction=>new Promise(resolve=>{
  const timeout=setTimeout(()=>{
    failures.push({label:'missing document '+direction+' navigation'});resolve();
  },3000);
  frame.onload=()=>{clearTimeout(timeout);setTimeout(resolve,20);};
  win().history[direction]();
});
await traverse('back');
equal(ids(),original.ids,'guide Back ordinary membership');
equal(win().location.href,original.url,'guide Back original URL');
equal(doc().querySelector('[data-lens-banner-status]').textContent,
  original.sources,'guide Back source choices');
await load(win().location.href);
equal(ids(),original.ids,'guide reload ordinary membership');
equal(win().location.href,original.url,'guide reload original URL');
equal(doc().querySelector('[data-lens-banner-status]').textContent,
  original.sources,'guide reload source choices');
await traverse('forward');
equal(ids(),selected.ids,'cross-view Forward selected membership');
equal(win().location.href,selected.url,'cross-view Forward selected URL');
equal([...doc().querySelectorAll('[data-comparison-head] [data-column-signal]')]
  .map(h=>h.dataset.columnSignal),selected.columns,'cross-view Forward columns');
return JSON.stringify({failures});})()
.catch(error=>JSON.stringify({harnessError:String(error),stack:error.stack}))"""
    )
    result = _evaluate_in_chrome(path, expression, initial_url=url)
    assert result.get("harnessError") is None, result
    assert result["failures"] == [], result


def test_general_boot_binds_resolved_query_once_and_retains_explicit_precedence(
    navigation_site: tuple[Path, str],
) -> None:
    path, url = navigation_site
    expression = (
        "(async()=>{"
        + HARNESS
        + """
for(const page of ['', 'comparisons/']) {
 parent.blockStorage=true;
 await load('/e/wa-2026-general/'+page+'?precinct=all');
 const ordinary=ids();
 await load('/e/wa-2026-general/'+page+'?precinct=1279');
 const selected=ids();
 for(const mode of ['empty','valid','stale','blocked']) {
  for(const query of ['', 'precinct=all','precinct=1279','precinct=unknown',
                      'precinct=','precinct=1279&precinct=2142']) {
   localStorage.clear();
   const remembered=mode==='valid'?'1279':mode==='stale'?'99999':null;
   if(remembered)localStorage.setItem(key,remembered);
   parent.blockStorage=mode==='blocked';
   await load('/e/wa-2026-general/'+page+'?other=retained'+(query?'&'+query:''));
   const resolved=query||('precinct='+(mode==='valid'?'1279':'all'));
   equal(win().location.search,'?other=retained&'+resolved,'boot query '+page+mode+query);
   const expected=query==='precinct=1279'||(!query&&mode==='valid')?selected:ordinary;
   equal(ids(),expected,'boot membership '+page+mode+query);
   equal(localStorage.getItem(key),remembered,'boot does not persist URL '+mode+query);
   const booted=win().location.href;
   await load(booted);
   equal(win().location.href,booted,'boot reload exact URL');
   equal(ids(),expected,'boot reload membership');
  }
 }
}
return JSON.stringify({failures});})()
.catch(error=>JSON.stringify({harnessError:String(error),stack:error.stack}))"""
    )
    result = _evaluate_in_chrome(path, expression, initial_url=url)
    assert result.get("harnessError") is None, result
    assert result["failures"] == [], result


def test_applied_precinct_failures_are_exposed_and_follow_current_query(
    navigation_site: tuple[Path, str],
) -> None:
    path, url = navigation_site
    expression = (
        "(async()=>{"
        + HARNESS
        + """
parent.blockStorage=false;localStorage.clear();
for(const page of ['', 'comparisons/']) {
 for(const query of ['precinct=unknown','precinct=1279&precinct=2142']) {
  await load('/e/wa-2026-general/'+page+'?'+query);
  const observe=()=>{
   const notice=doc().querySelector('[data-precinct-applied-notice]');
   const box=notice?.getBoundingClientRect();
   return {visible:Boolean(notice&&!notice.hidden&&box?.width&&box?.height&&
     win().getComputedStyle(notice).visibility==='visible'),
    exposed:Boolean(notice&&notice.getAttribute('role')==='status'&&
     notice.getAttribute('aria-live')==='polite'&&
     !notice.closest('[hidden],[inert],[aria-hidden="true"],dialog:not([open])')),
    text:notice?.textContent.trim()??'',closed:!doc().querySelector('dialog').open};
  };
  let observed=observe();
  equal(observed.visible,true,'invalid notice visible without opening '+page+query);
  equal(observed.exposed,true,'invalid notice accessibly exposed '+page+query);
  equal(observed.closed,true,'invalid editor remains closed');
  equal(observed.text.includes('not recognized')&&observed.text.includes('ordinary'),
    true,'honest ordinary fallback explanation');
  // Retain the invalid entry, then use the actual modal to commit a valid choice.
  win().history.pushState({},'',win().location.href);
  doc().querySelector('[data-precinct-open]').click();
  const input=doc().querySelector('#voting-precinct');input.value='1279';
  input.dispatchEvent(new (win().Event)('input',{bubbles:true}));
  doc().querySelector('[role=option][data-kind=precinct]')?.click();
  doc().querySelector('[data-precinct-submit]').click();
  observed=observe();
  equal(observed.visible,false,'valid selection clears visible error');
  equal(observed.text,'','valid selection clears error text');
  await load(win().location.href);
  equal(observe().visible,false,'valid reload has no error');
  doc().querySelector('[data-precinct-clear]').click();
  equal(observe().visible,false,'Clear has no error');
  equal(observe().text,'','Clear has no stale text');
  const traverse=direction=>new Promise(resolve=>{
   const timeout=setTimeout(()=>{
    failures.push({label:'missing notice history '+direction});resolve();
   },1000);
   win().addEventListener('popstate',()=>{
    clearTimeout(timeout);setTimeout(resolve,20);
   },{once:true});
   win().history[direction]();
  });
  await traverse('back');
  equal(observe().visible,true,'Back restores visible invalid warning');
  equal(observe().exposed,true,'Back restores exposed invalid warning');
  await load(win().location.href);
  equal(observe().visible,true,'invalid reload remains visible');
  equal(observe().exposed,true,'invalid reload remains exposed');
  await traverse('forward');
  equal(observe().visible,false,'ordinary Forward clears visible error');
  equal(observe().text,'','ordinary Forward clears stale text');
 }
}
return JSON.stringify({failures});})()
.catch(error=>JSON.stringify({harnessError:String(error),stack:error.stack}))"""
    )
    result = _evaluate_in_chrome(path, expression, initial_url=url)
    assert result.get("harnessError") is None, result
    assert result["failures"] == [], result


@pytest.mark.parametrize("start_page", ["", "comparisons/"])
def test_race_mode_override_remains_geographic_and_survives_voter_navigation(
    navigation_site: tuple[Path, str], general_view: PublicationViewModel, start_page: str
) -> None:
    path, url = navigation_site
    root = Path(__file__).resolve().parents[1]
    inventory = read_inventory(root / "data/normalized/wa-2026-general-inventory.json")
    catalog = read_precinct_catalog(CATALOG_PATH, inventory)
    public_ids = {r.id for s in general_view.guide_sections for r in s.races}
    expected = {}
    for code in ["2502", "1279", "all"]:
        area = next((p for p in catalog.precincts if p.code == code), None)
        races = [
            r
            for r in inventory.races
            if r.id in public_ids and (area is None or r.jurisdiction_id in area.jurisdiction_ids)
        ]
        expected[code] = {
            "all": sorted(r.id for r in races),
            "contested": sorted(
                r.id
                for r in races
                if r.race_type == "measure"
                or sum(c.choice_type == "candidate" for c in r.choices) >= 2
            ),
        }
    expression = (
        (
            "(async()=>{"
            + HARNESS
            + """
parent.blockStorage=false;localStorage.clear();
const expected=EXPECTED;
const mode=()=>{
 const comparison=Boolean(doc().querySelector('[data-comparison-all-races]'));
 return {all:doc().querySelector(comparison?'[data-comparison-all-races]':'#complete-filter'),
   contested:doc().querySelector(comparison?'[data-comparison-contested]':'#contested-filter')};
};
const check=(code,which,label)=>{
 equal(ids(),expected[code][which],label+' exact IDs');
 equal(mode()[which].checked,true,label+' checked');
 equal(mode().all.disabled||mode().contested.disabled,false,label+' buttons enabled');
 const status=doc().querySelector('[data-comparison-status],#filter-status').textContent.trim();
 equal(status.startsWith(String(expected[code][which].length)),true,label+' truthful count');
};
const choose=code=>{
 doc().querySelector('[data-precinct-open]').click();
 const input=doc().querySelector('#voting-precinct');input.value=code;
 input.dispatchEvent(new (win().Event)('input',{bubbles:true}));
  doc().querySelector('[role=option][data-kind=precinct]')?.click();
 doc().querySelector('[data-precinct-submit]').click();
};
await load('/e/wa-2026-general/START');
check('all','contested','ordinary default');
await load('/e/wa-2026-general/START?precinct=2502');
check('2502','contested','selected default');
mode().all.click();check('2502','all','All override');
equal(new URLSearchParams(win().location.search).get('races'),'all','explicit All URL');
await load(win().location.href);check('2502','all','All reload');
const before=win().location.href;
doc().querySelector('[data-precinct-open]').click();
const input=doc().querySelector('#voting-precinct');input.value='1279';
input.dispatchEvent(new (win().Event)('input',{bubbles:true}));
  doc().querySelector('[role=option][data-kind=precinct]')?.click();
doc().querySelector('[data-precinct-cancel]').click();
equal(win().location.href,before,'Cancel retains All URL');check('2502','all','Cancel');
choose('1279');check('1279','all','new precinct preserves override');
choose('2502');check('2502','all','2502 preserves override');
const origin=win().location.href;
const target=win().location.pathname.endsWith('/comparisons/')?'endorsements':'comparisons';
await click('[data-precinct-link="'+target+'"]');
check('2502','all','cross-view All');
mode().contested.click();check('2502','contested','Contested responds');
const destination=win().location.href;
const traverse=direction=>new Promise(resolve=>{
 const timeout=setTimeout(()=>{
  failures.push({label:'missing mode history '+direction});resolve();
 },2000);
 const done=()=>{clearTimeout(timeout);setTimeout(resolve,20);};
 frame.onload=done;win().addEventListener('popstate',done,{once:true});win().history[direction]();
});
await traverse('back');equal(win().location.href,origin,'Back restores All URL');
check('2502','all','Back All');await load(win().location.href);
check('2502','all','Back reload All');
await traverse('forward');equal(win().location.href,destination,'Forward restores Contested URL');
check('2502','contested','Forward Contested');
doc().querySelector('[data-precinct-clear]').click();check('all','contested','Clear default mode');
mode().all.click();check('all','all','ordinary All');
choose('2502');check('2502','all','All retained across Select');
for(const action of ['save','cancel','page-reset']) {
 await click('nav a[href*="/sources/"]');
 const box=doc().querySelector('[data-sources-source]');box.checked=!box.checked;
 box.dispatchEvent(new (win().Event)('change',{bubbles:true}));
 await click('[data-sources-'+action+']');
 check('2502','all','Sources '+action+' preserves ballot mode');
}
return JSON.stringify({failures,counts:expected});})()
.catch(error=>JSON.stringify({harnessError:String(error),stack:error.stack}))"""
        )
        .replace("EXPECTED", json.dumps(expected))
        .replace("START", start_page)
    )
    result = _evaluate_in_chrome(path, expression, initial_url=url)
    assert result.get("harnessError") is None, result
    assert result["failures"] == [], result


def test_comparison_anchor_history_adopts_query_race_mode_without_resetting_columns(
    navigation_site: tuple[Path, str], general_view: PublicationViewModel
) -> None:
    """An ordinary anchor must not suppress the incoming general race-mode query."""
    path, url = navigation_site
    root = Path(__file__).resolve().parents[1]
    inventory = read_inventory(root / "data/normalized/wa-2026-general-inventory.json")
    public_ids = {race.id for section in general_view.guide_sections for race in section.races}
    expected = {
        "all": sorted(public_ids),
        "contested": sorted(
            race.id
            for race in inventory.races
            if race.id in public_ids
            and (
                race.race_type == "measure"
                or sum(choice.choice_type == "candidate" for choice in race.choices) >= 2
            )
        ),
    }
    expression = (
        "(async()=>{"
        + HARNESS
        + """
parent.blockStorage=false;localStorage.clear();
const expected=EXPECTED;
const observations=[];
const columns=()=>[...doc().querySelectorAll(
 '[data-comparison-head] [data-column-signal]')].map(el=>el.dataset.columnSignal);
const check=(which,label)=>{
 const all=doc().querySelector('[data-comparison-all-races]');
 const contested=doc().querySelector('[data-comparison-contested]');
 const status=doc().querySelector('[data-comparison-status]').textContent.trim();
 observations.push({label,url:win().location.href,all:all.checked,
  contested:contested.checked,ids:ids(),status,columns:columns()});
 equal(ids(),expected[which],label+' exact IDs');
 equal(all.checked,which==='all',label+' All selected');
 equal(contested.checked,which==='contested',label+' Contested selected');
 equal(status.startsWith(String(expected[which].length)+' of '),true,label+' count');
 equal(new URLSearchParams(win().location.search).get('races'),
  which==='all'?'all':null,label+' query mode');
};
const traverse=direction=>new Promise((resolve,reject)=>{
 const timeout=setTimeout(()=>reject(new Error('anchor history '+direction+' timed out')),2000);
 const done=()=>{clearTimeout(timeout);setTimeout(resolve,20);};
 frame.onload=done;win().addEventListener('popstate',done,{once:true});
 win().history[direction]();
});
await load('/e/wa-2026-general/comparisons/?precinct=all#comparison-main');
const anchor=win().location.href;
check('contested','initial ordinary anchor');
equal(columns(),['gall','strn','stim'],'initial default columns');
doc().querySelector('.comparison-presets a').click();
check('contested','preset retains default mode');
equal(columns(),['strn','stim'],'preset columns');
doc().querySelector('[data-comparison-all-races]').click();
check('all','explicit All after preset');
const override=win().location.href;
await traverse('back');
equal(win().location.href,anchor,'Back retains ordinary anchor URL');
check('contested','Back to ordinary anchor');
equal(columns(),['strn','stim'],'ordinary anchor keeps current columns');
await traverse('forward');
equal(win().location.href,override,'Forward restores override URL');
check('all','Forward to explicit All');
equal(columns(),['strn','stim'],'Forward restores preset columns');
await traverse('back');
equal(win().location.href,anchor,'second Back retains ordinary anchor URL');
check('contested','second Back to ordinary anchor');
await load(win().location.href);
equal(win().location.href,anchor,'reload retains ordinary anchor URL');
check('contested','reload ordinary anchor');
equal(columns(),['gall','strn','stim'],'reload ordinary anchor uses default columns');
return JSON.stringify({failures,observations,expected});})()
.catch(error=>JSON.stringify({harnessError:String(error),stack:error.stack}))
"""
    ).replace("EXPECTED", json.dumps(expected))
    result = _evaluate_in_chrome(path, expression, initial_url=url)
    (path.parent / "anchor-history-result.json").write_text(json.dumps(result, indent=2) + "\n")
    assert result.get("harnessError") is None, result
    assert result["failures"] == [], result


def test_sources_header_links_preserve_explicit_ballot_context_over_memory(
    navigation_site: tuple[Path, str], general_view: PublicationViewModel
) -> None:
    """Header navigation must carry the same owned ballot query as editor actions."""
    path, url = navigation_site
    root = Path(__file__).resolve().parents[1]
    inventory = read_inventory(root / "data/normalized/wa-2026-general-inventory.json")
    catalog = read_precinct_catalog(CATALOG_PATH, inventory)
    public_ids = {race.id for section in general_view.guide_sections for race in section.races}
    area = next(precinct for precinct in catalog.precincts if precinct.code == "1279")
    expected = {
        "all": sorted(public_ids),
        "1279": sorted(
            race.id
            for race in inventory.races
            if race.id in public_ids and race.jurisdiction_id in area.jurisdiction_ids
        ),
    }
    expression = (
        "(async()=>{"
        + HARNESS
        + """
const expected=EXPECTED;
const observations=[];
for(const blocked of [false,true]) {
 for(const code of ['all','1279']) {
  for(const destination of ['endorsements','comparisons']) {
   parent.blockStorage=false;localStorage.clear();localStorage.setItem(key,'2200');
   parent.blockStorage=blocked;
   const query='?precinct='+code+'&races=all';
   await load('/e/wa-2026-general/sources/'+query+'&unrelated=discard');
   const box=doc().querySelector('[data-sources-source]');box.checked=false;
   box.dispatchEvent(new (win().Event)('change',{bubbles:true}));
   const selector=destination==='endorsements'
    ? 'nav[aria-label="Site"] a:nth-of-type(1)'
    : 'nav[aria-label="Site"] a:nth-of-type(3)';
   const link=doc().querySelector(selector);
   const header=new URL(link.href);
   const target='/e/wa-2026-general/'+(destination==='comparisons'?'comparisons/':'');
   const label=destination+' '+code+' blocked='+blocked;
   equal(link.textContent,destination==='endorsements'?'Endorsements':'Comparisons',
    label+' actual header destination');
   equal(header.pathname,target,label+' renderer-owned complete path');
   equal(header.search,query,label+' header owns only ballot query');
   equal(header.hash,'',label+' header does not save source draft');
   const menu=doc().querySelector('.site-band-menu');
   if(!menu.open)menu.querySelector('summary').click();
   await click(selector);
   const comparison=destination==='comparisons';
   const all=doc().querySelector(comparison?'[data-comparison-all-races]':'#complete-filter');
   const contested=doc().querySelector(
    comparison?'[data-comparison-contested]':'#contested-filter');
   const status=doc().querySelector(comparison?'[data-comparison-status]':'#filter-status');
   observations.push({label,header:header.href,url:win().location.href,ids:ids(),
    all:all.checked,contested:contested.checked,status:status.textContent.trim(),
    precinct:doc().querySelector('[data-precinct-name]').textContent.trim()});
   equal(win().location.pathname,target,label+' actual destination');
   equal(win().location.search,query,label+' explicit query beats memory');
   equal(ids(),expected[code],label+' exact All IDs');
   equal(all.checked,true,label+' All selected');
   equal(contested.checked,false,label+' Contested not selected');
   equal(status.textContent.trim().startsWith(String(expected[code].length)),true,
    label+' truthful count');
   equal(doc().querySelector('[data-precinct-name]').textContent.trim(),
    code==='all'?'Select':'SEA 46-1279',label+' explicit precinct');
   equal(localStorage.getItem(key),'2200',label+' header does not change memory');
   if(!comparison)equal(
    doc().querySelector('[data-lens-banner-status]').textContent.includes('Counting all'),
    true,label+' unsaved source edit stays a draft');
  }
 }
}
return JSON.stringify({failures,observations,expected});})()
.catch(error=>JSON.stringify({harnessError:String(error),stack:error.stack}))
"""
    ).replace("EXPECTED", json.dumps(expected))
    result = _evaluate_in_chrome(path, expression, initial_url=url)
    (path.parent / "sources-header-result.json").write_text(json.dumps(result, indent=2) + "\n")
    assert result.get("harnessError") is None, result
    assert result["failures"] == [], result


def test_ballot_scope_with_precinct_survives_real_history_and_reload(
    navigation_site: tuple[Path, str],
) -> None:
    path, url = navigation_site
    expression = (
        "(async()=>{"
        + HARNESS
        + """
const scope=()=>doc().querySelector('#race-filter,[data-comparison-section-filter]');
const options=()=>[...scope().options].map(o=>o.value);
const change=value=>{scope().value=value;
 scope().dispatchEvent(new (win().Event)('change',{bubbles:true}));};
const choose=code=>{
 doc().querySelector('[data-precinct-open]').click();
 const input=doc().querySelector('#voting-precinct');input.value=code;
 input.dispatchEvent(new (win().Event)('input',{bubbles:true}));
 doc().querySelector('[role=option][data-kind=precinct][data-code="'+code+'"]').click();
 doc().querySelector('[data-precinct-submit]').click();
};
const traverse=direction=>new Promise((resolve,reject)=>{
 const timer=setTimeout(()=>reject(new Error('missing real '+direction)),2000);
 win().addEventListener('popstate',()=>{clearTimeout(timer);setTimeout(resolve,20)},
 {once:true});win().history[direction]();
});
const general=['all','federal','state','county','state-supreme-court','city','other'];
const guide3230=[...general,'Citywide','Congressional District 7','Countywide',
 'Legislative District 34','Metropolitan King County Council District 8',
 'Statewide','West Electoral District'];
const guide1279=[...general,'Citywide','Congressional District 7','Countywide',
 'Legislative District 46','Statewide','West Electoral District'];
const initiatives=['initiative-26-001','initiative-26-638','initiative-26-645'];
for(const compare of [false,true]) {
 localStorage.clear();
 await load('/e/wa-2026-general/'+(compare?'comparisons/':'')+'?precinct=3230&races=all');
 equal(scope().disabled,false,'selected enabled');
 equal(options(),compare?general:guide3230,'eligible options3230');
 equal(ids().length,24,'complete covered3230');
 equal(doc().querySelector('[data-filter-open=ballot]').hasAttribute('data-active'),
  false,'precinct alone has no scope dot');
 equal([...initiatives,'seattle-proposition-1-transit'].every(id=>ids().includes(id)),
   true,'all four eligible measures');
 change('state');
 equal(initiatives.every(id=>ids().includes(id)),true,'state initiatives retained');
 equal(ids().includes('supreme-court-justice-1'),!compare,'original State semantics');
 change('city');equal(ids().includes('seattle-proposition-1-transit'),true,'city measure');
 equal(ids().some(id=>initiatives.includes(id)),false,'state measures outside city scope');
 change(compare?'county':'Legislative District 34');
 equal(doc().querySelector('[data-filter-open=ballot]').hasAttribute('data-active'),
  true,'own narrowed scope has dot');
 const oldURL=win().location.href;const oldIds=ids();
 win().history.pushState({},'',oldURL);
 choose('1279');
 equal(options(),compare?general:guide1279,'eligible options1279');
 equal(scope().value,compare?'county':'all','valid retention or invalid fallback');
 equal(doc().querySelector('[data-filter-open=ballot]').hasAttribute('data-active'),
  compare,'fallback projects own scope dot');
 equal(ids().length,compare?3:23,'new precinct scope membership');
 const newURL=win().location.href;const newIds=ids();
 await traverse('back');equal(win().location.href,oldURL,'Back URL');
 equal(options(),compare?general:guide3230,'Back options');equal(ids(),oldIds,'Back rows');
 equal(scope().value,compare?'county':'Legislative District 34','Back selection');
 await traverse('forward');equal(win().location.href,newURL,'Forward URL');
 equal(options(),compare?general:guide1279,'Forward options');equal(ids(),newIds,'Forward rows');
 await load(newURL);equal(win().location.href,newURL,'reload URL');
 equal(options(),compare?general:guide1279,'reload options');equal(ids(),newIds,'reload rows');
 equal(scope().value,compare?'county':'all','reload selection');
 doc().querySelector('[data-precinct-clear]').click();
 equal(options().length,compare?7:24,'clear complete catalog');
 equal(scope().value,compare?'county':'all','clear retains valid scope');
 equal(doc().querySelector('[data-filter-open=ballot]').hasAttribute('data-active'),
  compare,'Clear preserves own scope indicator');
 equal(new URL(win().location.href).searchParams.get('precinct'),'all','clear explicit geography');
}
return JSON.stringify({failures});})()
.catch(error=>JSON.stringify({harnessError:String(error),stack:error.stack}))"""
    )
    result = _evaluate_in_chrome(path, expression, initial_url=url)
    assert result.get("harnessError") is None, result
    assert result["failures"] == [], result
