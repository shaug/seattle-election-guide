// guide-filters.mjs is the guide's Ballot / View / Races controls, extracted
// from guide.html.j2's classic script by issue #239. Its two pure halves — the
// query-string mapping — are tested directly; the wiring is exercised in a
// lightweight DOM (docs/FRONTEND.md § Testing).

import assert from 'node:assert/strict';
import test from 'node:test';
import {
  readControlState,
  writeControlState,
} from '../../src/election_guide/rendering/templates/guide-filters.mjs';
import { installDom } from './support/dom.mjs';
import { assertModuleGuard } from './support/module-guards.mjs';

const SCOPES = new Set(['all', 'city', 'ld-43']);

const FILTER_SCOPES = [
  { value: 'all', label: 'All Seattle ballot races' },
  { value: 'city', label: 'City of Seattle' },
  { value: 'ld-43', label: 'Legislative District 43' },
];

test('an absent, unknown, or unrecognized control value resolves to its default', () => {
  assert.deepEqual(readControlState('', SCOPES), {
    scope: 'all',
    view: 'full',
    raceSet: 'complete',
  });
  assert.deepEqual(readControlState('?filter=nowhere&view=huge&races=some', SCOPES), {
    scope: 'all',
    view: 'full',
    raceSet: 'complete',
  });
});

test('a recognized control value is honored', () => {
  assert.deepEqual(readControlState('?filter=ld-43&view=compact&races=contested', SCOPES), {
    scope: 'ld-43',
    view: 'compact',
    raceSet: 'contested',
  });
});

test('every default is written as absence, so the audited address stays bare', () => {
  assert.equal(
    writeControlState('?filter=city&view=compact&races=contested', {
      scope: 'all',
      view: 'full',
      raceSet: 'complete',
    }),
    '',
  );
});

test('a non-default state round-trips through the query string', () => {
  const state = { scope: 'city', view: 'compact', raceSet: 'contested' };
  assert.deepEqual(readControlState(writeControlState('', state), SCOPES), state);
});

test('a parameter this page does not own survives a control write', () => {
  const written = writeControlState('?utm_source=mailer', {
    scope: 'city',
    view: 'full',
    raceSet: 'complete',
  });
  assert.equal(new URLSearchParams(written).get('utm_source'), 'mailer');
  assert.equal(new URLSearchParams(written).get('filter'), 'city');
});

/** A guide page with two races, one of them contested and city-scoped. */
function guideMarkup() {
  return `
    <select id="race-filter">
      <option value="all">All Seattle ballot races</option>
      <option value="city">City of Seattle</option>
      <option value="ld-43">Legislative District 43</option>
    </select>
    <input type="radio" name="ballot-view" value="full" checked>
    <input type="radio" name="ballot-view" value="compact">
    <input type="radio" name="race-set" value="complete" id="complete-filter" checked>
    <input type="radio" name="race-set" value="contested">
    <p id="filter-status"></p>
    <section data-filter-section="local">
      <article id="race-mayor" data-publication-race-id="mayor" data-contested="true"
        data-filter-tokens='["city"]'></article>
    </section>
    <section data-filter-section="state">
      <article id="race-ld" data-publication-race-id="ld" data-contested="false"
        data-filter-tokens='["ld-43"]'></article>
    </section>`;
}

/** @param {string} url */
async function wire(url) {
  const document = installDom(url);
  document.body.innerHTML = guideMarkup();
  const { wireGuideFilters } = await import(
    '../../src/election_guide/rendering/templates/guide-filters.mjs'
  );
  const { createLensRouter } = await import(
    '../../src/election_guide/rendering/templates/lens-route.mjs'
  );
  const payload = /** @type {any} */ ({ filter_scopes: FILTER_SCOPES });
  return { document, filters: wireGuideFilters(payload, createLensRouter()) };
}

const GUIDE_URL = 'https://seattleelections.guide/e/wa-2026-primary/';

test('the audited default shows every race and writes nothing to the address', async () => {
  const { document } = await wire(GUIDE_URL);
  assert.equal(document.getElementById('race-mayor').hidden, false);
  assert.equal(document.getElementById('race-ld').hidden, false);
  assert.equal(window.location.search, '');
  assert.match(document.querySelector('#filter-status').textContent, /2 races shown/);
});

test('the controls load from the address bar on arrival', async () => {
  const { document } = await wire(`${GUIDE_URL}?filter=city&races=contested&view=compact`);
  assert.equal(document.getElementById('race-mayor').hidden, false);
  assert.equal(document.getElementById('race-ld').hidden, true);
  assert.equal(document.documentElement.classList.contains('compact-ballot-mode'), true);
  assert.equal(document.documentElement.dataset.ballotView, 'compact');
});

// The read this ticket removed: the status line used to take the scope from
// `select.selectedOptions[0].textContent` (docs/FRONTEND.md, The data
// contract). The payload names it now, so the status is right even for a scope
// whose option text the page has not rendered the way the client expects.
test('the status line names the scope from the payload, not the select', async () => {
  const { document } = await wire(`${GUIDE_URL}?filter=ld-43`);
  const status = document.querySelector('#filter-status').textContent;
  assert.match(status, /1 race shown/);
  assert.match(status, /Legislative District 43/);
});

test('a section with no visible race is hidden with them', async () => {
  const { document } = await wire(`${GUIDE_URL}?filter=city`);
  assert.equal(document.querySelector('[data-filter-section="local"]').hidden, false);
  assert.equal(document.querySelector('[data-filter-section="state"]').hidden, true);
});

test('changing a control writes the state to the address bar', async () => {
  const { document } = await wire(GUIDE_URL);
  const select = document.querySelector('#race-filter');
  select.value = 'city';
  select.dispatchEvent(new Event('change'));
  assert.equal(new URLSearchParams(window.location.search).get('filter'), 'city');
});

test('showing every race clears the filter, so a linked race is reachable', async () => {
  const { document, filters } = await wire(`${GUIDE_URL}?filter=city`);
  assert.equal(document.getElementById('race-ld').hidden, true);
  filters.showEveryRace();
  assert.equal(document.getElementById('race-ld').hidden, false);
  assert.equal(document.querySelector('#race-filter').value, 'all');
});

test('the module keeps client state out of storage', () => {
  assertModuleGuard('guide-filters.mjs');
});
