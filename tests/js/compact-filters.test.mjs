import assert from 'node:assert/strict';
import test from 'node:test';
import { installDom } from './support/dom.mjs';
import { assertModuleGuard } from './support/module-guards.mjs';

installDom();
const { projectCompactFilters, wireCompactFilters } = await import(
  '../../src/election_guide/rendering/templates/compact-filters.mjs'
);
const { compactPrecinctName } = await import(
  '../../src/election_guide/rendering/templates/precinct-control.mjs'
);

test('safe names retain non-Seattle prefixes, differentiating suffixes and colliding compact names', () => {
  for (const name of ['BEL 37-0001', 'SEA 37-0001 A', 'Unknown precinct']) {
    assert.equal(compactPrecinctName({ name }, [{ name }]), name);
  }
  assert.equal(
    compactPrecinctName({ name: 'SEA 37-0001' }, [{ name: 'SEA 37-0001' }, { name: '37-0001' }]),
    'SEA 37-0001',
  );
  assert.equal(compactPrecinctName({ name: 'SEA 37-0001' }, [{ name: 'SEA 37-0001' }]), '37-0001');
});

test('own scope controls the indicator, and native editor cancel restores its trigger', () => {
  const doc = installDom();
  doc.body.innerHTML =
    '<section data-compact-filters><div data-filter-trigger="view"></div><div data-filter-trigger="races"></div><div data-filter-trigger="ballot"></div><dialog id="compact-ballot-dialog" data-filter-editor="ballot"><select><option>All</option></select><button data-filter-cancel>Cancel</button></dialog></section>';
  const state = {
    scope: 'all',
    scopeLabel: 'All Seattle ballot races',
    view: 'Compact',
    races: 'Contested',
  };
  projectCompactFilters(state);
  wireCompactFilters();
  const button = () => doc.querySelector('[data-filter-open=ballot]');
  assert.equal(button().hasAttribute('data-active'), false);
  projectCompactFilters({ ...state, scope: 'county', scopeLabel: 'County' });
  assert.equal(button().hasAttribute('data-active'), true);
  assert.match(button().getAttribute('aria-label'), /active: County/);
  button().click();
  assert.equal(doc.querySelector('dialog').open, true);
  doc.querySelector('[data-filter-cancel]').click();
  assert.equal(doc.querySelector('dialog').open, false);
  assert.equal(doc.activeElement, button());
  assert.equal(button().getAttribute('aria-expanded'), 'false');
  projectCompactFilters(state);
  assert.equal(button().hasAttribute('data-active'), false);
});
test('compact filters have no storage capability', () => assertModuleGuard('compact-filters.mjs'));

test('the real catalog can shorten without losing a distinguishing code or creating collisions', async () => {
  const { readFileSync } = await import('node:fs');
  const catalog = JSON.parse(
    readFileSync(
      new URL('../../config/elections/wa-2026-general-precinct-ballots.json', import.meta.url),
      'utf8',
    ),
  ).precincts;
  const names = catalog.map((p) => compactPrecinctName(p, catalog));
  assert.equal(names.length, 1020);
  assert.equal(new Set(names).size, 1020);
  for (const p of catalog) assert.ok(names.includes(p.name.slice(4)));
});
