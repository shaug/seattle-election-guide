// compare-route.mjs is the Comparisons page's one address-bar owner
// (docs/FRONTEND.md § State and URLs). The sweep that proves nothing else on
// the page touches `location` lives in lens-route.test.mjs, which owns the
// recorded list for every page; these tests are the router's own behavior.

import assert from 'node:assert/strict';
import test from 'node:test';
import { installDom } from './support/dom.mjs';
import { assertModuleGuard } from './support/module-guards.mjs';

const PAGE = 'https://seattleelections.guide/e/wa-2026-primary/comparisons/';

/** @param {string} url */
async function router(url) {
  installDom(url);
  const { createCompareRouter } = await import(
    '../../src/election_guide/rendering/templates/compare-route.mjs'
  );
  return createCompareRouter();
}

test('the router reads the live fragment without interpreting it', async () => {
  const route = await router(`${PAGE}#cmp=1&cols=gallstrn`);
  assert.equal(route.fragment(), '#cmp=1&cols=gallstrn');
});

test('the address key distinguishes one entry from another', async () => {
  const route = await router(`${PAGE}?print=1#cmp=1`);
  assert.equal(route.key(), '/e/wa-2026-primary/comparisons/?print=1#cmp=1');
});

test('a written fragment keeps the path and the query', async () => {
  const route = await router(`${PAGE}?print=1#cmp=1&cols=gallstrn`);
  route.write('cmp=1&cols=gallstim', 'replace');
  assert.equal(window.location.pathname, '/e/wa-2026-primary/comparisons/');
  assert.equal(window.location.search, '?print=1');
  assert.equal(window.location.hash, '#cmp=1&cols=gallstim');
});

test('a pushed fragment marks the entry it creates as a comparison entry', async () => {
  const route = await router(`${PAGE}#cmp=1&cols=gallstrn`);
  route.write('cmp=1&cols=gallstim', 'push');
  assert.deepEqual(history.state, { comparison: true });
  assert.equal(window.location.hash, '#cmp=1&cols=gallstim');
});

test('clearing an unusable fragment leaves the page address behind', async () => {
  const route = await router(`${PAGE}?print=1#lens=2&mode=a`);
  route.clearFragment();
  assert.equal(window.location.hash, '');
  assert.equal(window.location.pathname, '/e/wa-2026-primary/comparisons/');
  assert.equal(window.location.search, '?print=1');
});

test('clearing preserves whatever state the entry already carried', async () => {
  const route = await router(`${PAGE}#cmp=1&cols=gallstrn`);
  route.write('cmp=1&cols=gallstim', 'replace');
  route.clearFragment();
  assert.deepEqual(history.state, { comparison: true });
});

test('the module keeps client state out of storage', () => {
  assertModuleGuard('compare-route.mjs');
});
