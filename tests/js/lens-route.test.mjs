// lens-route.mjs is the guide's and the sources editor's one address-bar owner
// (docs/FRONTEND.md § State and URLs). The sweep at the bottom is the check
// that rule was missing: before issue #239 the guide reached for `location` in
// fourteen places across two script blocks, two of which hand-parsed the hash.

import assert from 'node:assert/strict';
import test from 'node:test';
import { installDom } from './support/dom.mjs';
import { assertModuleGuard, moduleNames, moduleSource } from './support/module-guards.mjs';

const GUIDE_URL = 'https://seattleelections.guide/e/wa-2026-primary/';

/** @param {string} url */
async function router(url) {
  installDom(url);
  const { createLensRouter } = await import(
    '../../src/election_guide/rendering/templates/lens-route.mjs'
  );
  return createLensRouter();
}

test('the router reads the live fragment, query, and history state', async () => {
  const route = await router(`${GUIDE_URL}?filter=city#race-mayor`);
  assert.equal(route.fragment(), '#race-mayor');
  assert.equal(route.controlSearch(), '?filter=city');
  assert.equal(route.raceTarget(), 'race-mayor');
});

test('the race target comes out of a lens fragment as well as a bare anchor', async () => {
  const route = await router(`${GUIDE_URL}#lens=2&mode=s&sel=strn&race=race-council`);
  assert.equal(route.raceTarget(), 'race-council');
});

test('a fragment naming no race names no race', async () => {
  const route = await router(`${GUIDE_URL}#lens=2&mode=s&sel=strn`);
  assert.equal(route.raceTarget(), '');
});

test('clearing the fragment leaves the path and query alone', async () => {
  const route = await router(`${GUIDE_URL}?view=compact#lens=2&mode=a`);
  route.clearFragment();
  assert.equal(window.location.pathname, '/e/wa-2026-primary/');
  assert.equal(window.location.search, '?view=compact');
  assert.equal(window.location.hash, '');
});

test('rewriting the race segment leaves an active lens exactly as found', async () => {
  const route = await router(`${GUIDE_URL}#lens=2&mode=s&sel=strn&race=race-mayor`);
  route.replaceRaceTarget('race-council');
  assert.match(window.location.hash, /lens=2/);
  assert.match(window.location.hash, /sel=strn/);
  assert.match(window.location.hash, /race=race-council/);

  route.replaceRaceTarget(null);
  assert.match(window.location.hash, /lens=2/);
  assert.match(window.location.hash, /sel=strn/);
  assert.ok(!window.location.hash.includes('race='));
});

test('closing a race with no lens active leaves no fragment behind', async () => {
  const route = await router(`${GUIDE_URL}#race-mayor`);
  route.replaceRaceTarget(null);
  assert.equal(window.location.hash, '');
});

test('a replace preserves the history state the dialog stores in it', async () => {
  const route = await router(`${GUIDE_URL}#race-mayor`);
  route.pushRaceTarget('race-mayor', { raceDetail: 'race-mayor' });
  route.replaceControlSearch('?view=compact');
  assert.deepEqual(route.historyState(), { raceDetail: 'race-mayor' });
});

test('the shareable race link is composed from the live address', async () => {
  const route = await router(`${GUIDE_URL}#lens=2&mode=s&sel=strn`);
  const link = route.absoluteRaceLink('race-mayor');
  assert.ok(link.startsWith('https://seattleelections.guide/e/wa-2026-primary/'));
  assert.match(link, /sel=strn/);
  assert.match(link, /race=race-mayor/);
});

// The rule: each page's codec module is the sole reader and writer of
// `location`; no handler edits `location` around the codec. Every owner and
// every exception is recorded here with its argument rather than left implicit,
// so adding one is a change to this list.
const LOCATION_OWNERS = {
  'lens-route.mjs': 'The guide and sources editor own their address bar here.',
  'compare-route.mjs':
    'The Comparisons page owns its address bar here. One owner per fragment, not one ' +
    'owner for every fragment: this page reads a different schema against a different ' +
    'context, decoded by its own codec, compare-url.mjs.',
  'share-link.mjs':
    'The masthead Share action copies the address verbatim; no segment of it is ' +
    'interpreted, so there is no fragment for a codec to own.',
};

test('only the recorded owners read or write location or history', () => {
  const offenders = moduleNames().filter((name) => {
    if (name in LOCATION_OWNERS) return false;
    const code = moduleSource(name)
      .replace(/\/\*[\s\S]*?\*\//g, '')
      .replace(/(^|\s)\/\/.*$/gm, '');
    return /\blocation\b/.test(code) || /\bhistory\b/.test(code);
  });
  assert.deepEqual(
    offenders,
    [],
    `${offenders.join(', ')} reads or writes location or history. Route it through the page's ` +
      `codec-owned router, or record it in LOCATION_OWNERS with its argument (rule: the codec ` +
      `is the sole reader and writer of location, docs/FRONTEND.md § State and URLs).`,
  );
});

test('every recorded owner still exists, so the list cannot go stale', () => {
  const present = new Set(moduleNames());
  for (const name of Object.keys(LOCATION_OWNERS)) {
    assert.ok(present.has(name), `${name} is recorded as a location owner but no longer exists.`);
  }
});

test('the module keeps client state out of storage', () => {
  assertModuleGuard('lens-route.mjs');
});
