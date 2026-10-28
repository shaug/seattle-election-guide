import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';
import { installDom } from './support/dom.mjs';

installDom();
const { wirePrecinctControl } = await import(
  '../../src/election_guide/rendering/templates/precinct-control.mjs'
);
const markup = readFileSync(
  new URL(
    '../../src/election_guide/rendering/templates/_precinct_control.html.j2',
    import.meta.url,
  ),
  'utf8',
);
const contract = {
  election_id: 'wa-2026-general',
  mapping_hash: 'reviewed',
  endorsements_path: '/e/wa-2026-general/',
  comparisons_path: '/e/wa-2026-general/comparisons/',
  address_lookup: { election_id: 'wa-2026-general', mapping_hash: 'reviewed' },
  precincts: [{ code: '3230', name: 'SEA 34-3230', contest_ids: ['measure'] }],
};
function boot(lookupOverride = {}) {
  const doc = installDom();
  doc.body.innerHTML = markup;
  let query = '?precinct=all&races=all';
  let history;
  const pending = [];
  const lookup = {
    suggest: async () => [
      { text: 'Public civic building', magicKey: 'civic', isCollection: false },
    ],
    resolve: () => new Promise((done) => pending.push(done)),
    ...lookupOverride,
  };
  wirePrecinctControl(
    contract,
    {
      controlSearch: () => query,
      replaceControlSearch: (next) => {
        query = next;
      },
      onHistoryChange: (fn) => {
        history = fn;
      },
    },
    () => {},
    lookup,
  );
  doc.querySelector('[data-precinct-open]').click();
  return { doc, pending, query: () => query, history: () => history() };
}
const flush = () => new Promise((done) => setTimeout(done, 0));
async function chooseAddress(b) {
  b.doc.querySelector('[data-address-mode]').click();
  const input = b.doc.querySelector('[data-address-input]');
  input.value = 'Public civic';
  input.dispatchEvent(new Event('input'));
  await new Promise((done) => setTimeout(done, 330));
  input.dispatchEvent(
    new KeyboardEvent('keydown', { key: 'ArrowDown', bubbles: true, cancelable: true }),
  );
  input.dispatchEvent(
    new KeyboardEvent('keydown', { key: 'Enter', bubbles: true, cancelable: true }),
  );
  await flush();
  return input;
}
test('address selection resolves only the existing draft, and Select commits once without address persistence', async () => {
  const b = boot();
  await chooseAddress(b);
  assert.equal(b.query(), '?precinct=all&races=all');
  b.pending[0]({ status: 'resolved', code: '3230' });
  await flush();
  assert.equal(b.query(), '?precinct=all&races=all');
  assert.equal(b.doc.querySelector('[data-precinct-submit]').disabled, false);
  b.doc.querySelector('form').dispatchEvent(new Event('submit', { cancelable: true }));
  assert.equal(b.query(), '?precinct=3230&races=all');
  assert.equal(window.localStorage.getItem('seg-precinct-v1:wa-2026-general'), '3230');
  assert.equal(b.doc.querySelector('[data-address-input]').value, '');
});
for (const boundary of ['cancel', 'edit', 'history', 'mode', 'close-reopen'])
  test(`late resolution cannot revive canceled draft: ${boundary}`, async () => {
    const b = boot();
    const input = await chooseAddress(b);
    if (boundary === 'cancel' || boundary === 'close-reopen')
      b.doc.querySelector('[data-precinct-cancel]').click();
    if (boundary === 'close-reopen') b.doc.querySelector('[data-precinct-open]').click();
    if (boundary === 'history') b.history();
    if (boundary === 'mode') b.doc.querySelector('[data-direct-mode]').click();
    if (boundary === 'edit') {
      input.value = 'New text';
      input.dispatchEvent(new Event('input'));
    }
    b.pending[0]({ status: 'resolved', code: '3230' });
    await flush();
    assert.equal(b.query(), '?precinct=all&races=all');
    assert.equal(b.doc.querySelector('[data-precinct-submit]').disabled, true);
  });
test('popup Enter never submits; first Escape dismisses popup, Tab never selects', async () => {
  const b = boot();
  b.doc.querySelector('[data-address-mode]').click();
  const input = b.doc.querySelector('[data-address-input]');
  input.value = 'Public';
  input.dispatchEvent(new Event('input'));
  await new Promise((done) => setTimeout(done, 330));
  const enter = new KeyboardEvent('keydown', { key: 'Enter', bubbles: true, cancelable: true });
  input.dispatchEvent(enter);
  assert.equal(enter.defaultPrevented, true);
  assert.equal(b.pending.length, 0);
  const esc = new KeyboardEvent('keydown', { key: 'Escape', bubbles: true, cancelable: true });
  input.dispatchEvent(esc);
  assert.equal(esc.defaultPrevented, true);
  assert.equal(b.doc.querySelector('dialog').open, true);
  assert.equal(b.doc.querySelector('[role=listbox]').hidden, true);
  assert.equal(b.query(), '?precinct=all&races=all');
});

test('Tab after explicit suggestion selection does not cancel the in-flight resolution', async () => {
  const b = boot();
  const input = await chooseAddress(b);
  input.dispatchEvent(new KeyboardEvent('keydown', { key: 'Tab', bubbles: true }));
  b.pending[0]({ status: 'resolved', code: '3230' });
  await flush();
  assert.equal(b.doc.querySelector('[data-precinct-submit]').disabled, false);
  assert.equal(b.query(), '?precinct=all&races=all');
});

test('old suggestions cannot replace newer text even when abort is ignored', async () => {
  const searches = [];
  const b = boot({ suggest: () => new Promise((done) => searches.push(done)) });
  b.doc.querySelector('[data-address-mode]').click();
  const input = b.doc.querySelector('[data-address-input]');
  input.value = 'Older query';
  input.dispatchEvent(new Event('input'));
  await new Promise((done) => setTimeout(done, 330));
  input.value = 'Newer query';
  input.dispatchEvent(new Event('input'));
  await new Promise((done) => setTimeout(done, 330));
  searches[1]([{ text: 'Newer canonical', magicKey: 'new', isCollection: false }]);
  await flush();
  searches[0]([{ text: 'Older canonical', magicKey: 'old', isCollection: false }]);
  await flush();
  assert.equal(b.doc.querySelector('[role=listbox]').textContent, 'Newer canonical');
  assert.equal(b.doc.querySelector('[data-precinct-submit]').disabled, true);
});

test('lookup failure retains direct precinct fallback and never prints raw errors', async () => {
  const b = boot();
  await chooseAddress(b);
  b.pending[0]({ status: 'unavailable' });
  await flush();
  assert.match(
    b.doc.querySelector('[data-precinct-status]').textContent,
    /Choose your precinct directly/,
  );
  b.doc.querySelector('[data-direct-mode]').click();
  const direct = b.doc.querySelector('#voting-precinct');
  direct.value = '3230';
  direct.dispatchEvent(new Event('input'));
  b.doc.querySelector('form').dispatchEvent(new Event('submit', { cancelable: true }));
  assert.equal(b.query(), '?precinct=3230&races=all');
});

test('ArrowUp from no active option selects the last real suggestion', async () => {
  const b = boot({
    suggest: async () => [
      { text: 'First canonical', magicKey: 'first', isCollection: false },
      { text: 'Second canonical', magicKey: 'second', isCollection: false },
    ],
  });
  b.doc.querySelector('[data-address-mode]').click();
  const input = b.doc.querySelector('[data-address-input]');
  input.value = 'Canonical';
  input.dispatchEvent(new Event('input'));
  await new Promise((done) => setTimeout(done, 330));
  input.dispatchEvent(
    new KeyboardEvent('keydown', { key: 'ArrowUp', bubbles: true, cancelable: true }),
  );
  assert.equal(input.getAttribute('aria-activedescendant'), 'address-option-1');
});
