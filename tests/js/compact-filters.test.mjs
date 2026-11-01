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
// Literal approved closed faces; independent of the production presentation map.
const ballotScopes = [
  ['all', 'All ballot races', 'All ballot races'],
  ['federal', 'Federal', 'Federal'],
  ['state', 'State', 'State'],
  ['county', 'County', 'County'],
  ['state-supreme-court', 'State Supreme Court', 'State Supreme Court'],
  ['city', 'City', 'City'],
  ['other', 'Other', 'Other'],
  ['Citywide', 'Citywide', 'Citywide'],
  ['Congressional District 7', 'Congressional District 7', 'Congressional D7'],
  ['Congressional District 9', 'Congressional District 9', 'Congressional D9'],
  ['Countywide', 'Countywide', 'Countywide'],
  ['Legislative District 11', 'Legislative District 11', 'Legislative D11'],
  ['Legislative District 32', 'Legislative District 32', 'Legislative D32'],
  ['Legislative District 34', 'Legislative District 34', 'Legislative D34'],
  ['Legislative District 36', 'Legislative District 36', 'Legislative D36'],
  ['Legislative District 37', 'Legislative District 37', 'Legislative D37'],
  ['Legislative District 43', 'Legislative District 43', 'Legislative D43'],
  ['Legislative District 46', 'Legislative District 46', 'Legislative D46'],
  [
    'Metropolitan King County Council District 2',
    'Metropolitan King County Council District 2',
    'King County Council D2',
  ],
  [
    'Metropolitan King County Council District 4',
    'Metropolitan King County Council District 4',
    'King County Council D4',
  ],
  [
    'Metropolitan King County Council District 8',
    'Metropolitan King County Council District 8',
    'King County Council D8',
  ],
  ['Seattle City Council District 5', 'Seattle City Council District 5', 'Seattle City Council D5'],
  ['Statewide', 'Statewide', 'Statewide'],
  ['West Electoral District', 'West Electoral District', 'West Electoral District'],
];

test('closed Ballot summaries preserve every complete native identity and focused node', () => {
  const doc = installDom();
  doc.body.innerHTML =
    '<section data-compact-filters><div data-filter-trigger="ballot"><div class="compact-filter-trigger"><span data-filter-face="ballot" aria-hidden="true"></span><select data-filter-native="ballot"></select></div></div></section>';
  const select = doc.querySelector('select');
  const fallback = [
    ['unreviewed-scope', 'Metropolitan King County Council District 2'],
    ['Metropolitan King County Council District 2', 'Renamed full council district'],
    ['legislative District 11', 'legislative District 11'],
    ['new district', 'Unknown complete district name with a distinguishing suffix'],
  ];
  for (const [value, label, summary = label] of [...ballotScopes, ...fallback]) {
    const original = ballotScopes
      .filter(([token]) => token !== value)
      .map(([token, full]) => [token, full]);
    original.push([value, label]);
    select.replaceChildren();
    for (const [token, full] of original) {
      const option = doc.createElement('option');
      option.value = token;
      option.textContent = full;
      select.append(option);
    }
    select.value = value;
    select.focus();
    projectCompactFilters({
      scope: value,
      scopeLabel: label,
      scopeOptions: original.map(([value, label]) => ({ value, label })),
      view: 'Full',
      races: 'All',
    });
    assert.equal(doc.querySelector('.compact-ballot-scope').textContent, summary);
    assert.equal(select.value, value);
    assert.equal(select.selectedOptions[0].textContent, label);
    assert.equal(
      select.getAttribute('aria-label'),
      value === 'all' ? 'Ballot: All ballot races' : `Ballot filter active: ${label}`,
    );
    assert.equal(select.title, select.getAttribute('aria-label'));
    assert.equal(select.hasAttribute('data-active'), value !== 'all');
    assert.equal(doc.querySelector('[data-filter-face]').getAttribute('aria-hidden'), 'true');
    assert.equal(doc.querySelector('select'), select);
    assert.equal(doc.activeElement, select);
    assert.deepEqual(
      [...select.options].map((o) => [o.value, o.textContent]),
      original,
    );
  }
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
