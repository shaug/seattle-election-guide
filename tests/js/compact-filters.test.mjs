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

test('own scope controls the native select name and decorative indicator without replacing focus', () => {
  const doc = installDom();
  doc.body.innerHTML =
    '<section data-compact-filters><div data-filter-trigger="ballot"><div class="compact-filter-trigger"><span data-filter-face="ballot" aria-hidden="true"></span><select data-filter-native="ballot"><option value="all">All ballot races</option><option value="county">County</option></select></div></div></section>';
  const state = {
    scope: 'all',
    scopeLabel: 'All Seattle ballot races',
    view: 'Compact',
    races: 'Contested',
  };
  projectCompactFilters(state);
  wireCompactFilters();
  const button = () => doc.querySelector('[data-filter-native=ballot]');
  const select = button();
  select.focus();
  assert.equal(button().hasAttribute('data-active'), false);
  select.value = 'county';
  projectCompactFilters({ ...state, scope: 'county', scopeLabel: 'County' });
  assert.equal(button().hasAttribute('data-active'), true);
  assert.match(button().getAttribute('aria-label'), /active: County/);
  assert.equal(button(), select);
  assert.equal(doc.activeElement, select);
  assert.equal(select.value, 'county');
  assert.equal(doc.querySelector('[data-filter-face]').getAttribute('aria-hidden'), 'true');
  assert.equal(doc.querySelector('.compact-ballot-scope').textContent, 'County');
  projectCompactFilters(state);
  assert.equal(button().hasAttribute('data-active'), false);
  assert.equal(button().getAttribute('aria-label'), 'Ballot: All ballot races');
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
