import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';
import { installDom } from './support/dom.mjs';
import { assertModuleGuard } from './support/module-guards.mjs';

const PRECINCT_MARKUP = readFileSync(
  new URL(
    '../../src/election_guide/rendering/templates/_precinct_control.html.j2',
    import.meta.url,
  ),
  'utf8',
)
  .replace(
    '{{ precinct_lookup_href }}',
    'https://experience.arcgis.com/experience/1374a449f39f4cd098643466dab0826a',
  )
  .replaceAll('{{ opens_in_new_tab }}', ' (opens in a new tab)');
installDom();
const { wirePrecinctControl } = await import(
  '../../src/election_guide/rendering/templates/precinct-control.mjs'
);
const contract = {
  schema_version: '1.0',
  election_id: 'wa-2026-general',
  mapping_hash: 'checked',
  endorsements_path: '/inspection/endorsements/',
  comparisons_path: '/inspection/comparison/',
  precincts: [{ code: '1279', name: 'SEA 46-1279', contest_ids: ['measure', 'candidate'] }],
};
function boot(search = '', saved = null) {
  const document = installDom();
  document.body.innerHTML =
    '<a data-precinct-link="endorsements"></a><a data-precinct-link="comparisons"></a>' +
    PRECINCT_MARKUP;
  if (saved) window.localStorage.setItem('seg-precinct-v1:wa-2026-general', saved);
  let query = search;
  let listener;
  const calls = [];
  const router = {
    controlSearch: () => query,
    replaceControlSearch: (s) => {
      query = s;
    },
    onHistoryChange: (fn) => {
      listener = fn;
    },
  };
  wirePrecinctControl(contract, router, (ids, reset) =>
    calls.push({ ids: ids && [...ids], reset }),
  );
  return {
    document,
    calls,
    query: () => query,
    history: (s) => {
      query = s;
      listener();
    },
  };
}
test('explicit all/invalid URL outranks remembered precinct and never claims a matched ballot', () => {
  for (const search of ['?precinct=all', '?precinct=unknown', '?precinct=1279&precinct=all']) {
    const b = boot(search, '1279');
    assert.equal(b.calls.at(-1).ids, null);
    if (search.includes('unknown'))
      assert.match(
        b.document.querySelector('[data-precinct-applied-notice]').textContent,
        /not recognized/,
      );
    const notice = b.document.querySelector('[data-precinct-applied-notice]');
    assert.equal(notice.hidden, search === '?precinct=all');
    assert.equal(notice.closest('dialog'), null);
  }
});
test('restore, exact search choice, clear, reload link and history preserve truthful selection', () => {
  const b = boot('', '1279');
  assert.deepEqual(b.calls.at(-1).ids, ['measure', 'candidate']);
  assert.equal(b.query(), '?precinct=1279');
  b.document.querySelector('[data-precinct-clear]').click();
  assert.equal(b.query(), '?precinct=all');
  assert.deepEqual(b.calls.at(-1), { ids: null, reset: true });
  b.document.querySelector('[data-precinct-open]').click();
  const input = b.document.querySelector('input');
  input.value = 'SEA 46-1279';
  input.dispatchEvent(new Event('input'));
  b.document.querySelector('[role=option][data-kind=precinct]').click();
  b.document
    .querySelector('[data-precinct-form]')
    .dispatchEvent(new Event('submit', { cancelable: true }));
  assert.deepEqual(b.calls.at(-1).ids, ['measure', 'candidate']);
  assert.equal(b.query(), '?precinct=1279');
  b.history('?precinct=all');
  assert.equal(b.calls.at(-1).ids, null);
  assert.equal(input.value, '');
});
test('one labelled combobox and styled list has one named static county information link', () => {
  const b = boot();
  assert.equal(b.document.querySelectorAll('input[role=combobox]').length, 1);
  assert.equal(b.document.querySelector('datalist'), null);
  assert.ok(b.document.querySelector('[role=listbox]'));
  assert.equal(b.document.querySelector('label').htmlFor, b.document.querySelector('input').id);
  const info = b.document.querySelector('dialog a.precinct-info');
  assert.ok(info);
  assert.equal(b.document.querySelectorAll('dialog a').length, 1);
  assert.equal(
    info.href,
    'https://experience.arcgis.com/experience/1374a449f39f4cd098643466dab0826a',
  );
  assert.equal(info.target, '_blank');
  assert.equal(info.rel, 'noopener noreferrer');
  assert.equal(
    info.getAttribute('aria-label'),
    'Find your precinct on the county map (opens in a new tab)',
  );
  assert.equal(info.title, info.getAttribute('aria-label'));
  b.document.querySelector('[data-precinct-open]').click();
  const input = b.document.querySelector('input');
  input.value = 'Transient address text';
  input.dispatchEvent(new Event('input'));
  assert.equal(
    info.href,
    'https://experience.arcgis.com/experience/1374a449f39f4cd098643466dab0826a',
  );
});
test('control is wiring with no storage/address ownership', () =>
  assertModuleGuard('precinct-control.mjs'));

test('navigation consumes complete server-owned paths without reconstructing election routes', () => {
  const b = boot('?precinct=1279');
  const link = (key) => b.document.querySelector(`[data-precinct-link="${key}"]`);
  assert.equal(
    link('endorsements').getAttribute('href'),
    '/inspection/endorsements/?precinct=1279',
  );
  assert.equal(link('comparisons').getAttribute('href'), '/inspection/comparison/?precinct=1279');
  b.document.querySelector('[data-precinct-clear]').click();
  assert.equal(link('comparisons').getAttribute('href'), '/inspection/comparison/?precinct=all');
});

test('compact precinct identity abbreviates only unique reviewed Seattle names', () => {
  const b = boot('?precinct=1279');
  const opener = b.document.querySelector('[data-precinct-open]');
  assert.equal(opener.getAttribute('aria-label'), 'Precinct: SEA 46-1279');
  assert.equal(opener.querySelector('[data-precinct-short]').textContent, '46-1279');
  assert.equal(opener.querySelector('[data-precinct-name]').textContent, 'SEA 46-1279');
  opener.click();
  assert.equal(opener.getAttribute('aria-expanded'), 'true');
  b.document.querySelector('[data-precinct-cancel]').click();
  assert.equal(opener.getAttribute('aria-expanded'), 'false');
  assert.equal(b.document.activeElement, opener);
});
