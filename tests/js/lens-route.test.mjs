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

test('the router reads the live fragment and query', async () => {
  const route = await router(`${GUIDE_URL}?filter=city#race-mayor`);
  assert.equal(route.fragment(), '#race-mayor');
  assert.equal(route.controlSearch(), '?filter=city');
});

test('clearing the fragment leaves the path and query alone', async () => {
  const route = await router(`${GUIDE_URL}?view=compact#lens=2&mode=a`);
  route.clearFragment();
  assert.equal(window.location.pathname, '/e/wa-2026-primary/');
  assert.equal(window.location.search, '?view=compact');
  assert.equal(window.location.hash, '');
});

// Issue #136: a `#race-…` link shared while race detail was a dialog names a
// page now, and this is the one navigation the guide performs. The lens has to
// survive it — that is issue 142's contract — and the race segment has to not,
// because the path names the race from here on.
test('a race redirect carries the lens over and drops the race segment', async () => {
  const route = await router(`${GUIDE_URL}?view=compact#lens=2&mode=s&sel=strn&race=race-mayor`);
  /** @type {string[]} */
  const replaced = [];
  Object.defineProperty(window.location, 'replace', {
    configurable: true,
    value: (/** @type {string} */ address) => replaced.push(address),
  });

  route.redirectToRacePage('/e/wa-2026-primary/races/mayor/');

  assert.equal(replaced.length, 1);
  const [address] = replaced;
  assert.ok(address.startsWith('/e/wa-2026-primary/races/mayor/#'), address);
  assert.match(address, /lens=2/);
  assert.match(address, /sel=strn/);
  assert.ok(!address.includes('race='), address);
  // The guide's own filter and ballot view describe a list of races; the page
  // this lands on has one.
  assert.ok(!address.includes('view=compact'), address);
});

test('a race redirect from a bare permalink leaves no fragment behind', async () => {
  const route = await router(`${GUIDE_URL}#race-mayor`);
  /** @type {string[]} */
  const replaced = [];
  Object.defineProperty(window.location, 'replace', {
    configurable: true,
    value: (/** @type {string} */ address) => replaced.push(address),
  });

  route.redirectToRacePage('/e/wa-2026-primary/races/mayor/');

  assert.deepEqual(replaced, ['/e/wa-2026-primary/races/mayor/']);
});

// The rule: each page's codec module is the sole reader and writer of
// `location`; no handler edits `location` around the codec. Every owner and
// every exception is recorded here with its argument rather than left implicit,
// so adding one is a change to this list.
const LOCATION_OWNERS = {
  'lens-route.mjs':
    'The guide, its race pages, and the sources editor own their address bar here. One ' +
    'fragment schema, one owner: all three read and write the same lens fragment.',
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
