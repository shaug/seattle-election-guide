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
function boot(lookupOverride = {}, contractOverride = {}) {
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
    { ...contract, ...contractOverride },
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
test('one unified editor shows numeric precinct and address suggestions without choosing either', async () => {
  const b = boot();
  assert.equal(b.doc.querySelectorAll('input').length, 1);
  const input = b.doc.querySelector('#voting-precinct[role=combobox]');
  assert.ok(input);
  assert.equal(b.doc.querySelector('datalist'), null);
  assert.equal(b.doc.querySelector('[data-address-mode]'), null);
  assert.equal(b.doc.querySelector('[data-direct-mode]'), null);
  assert.equal(b.doc.body.textContent.includes('Find my precinct'), false);
  input.value = '323';
  input.dispatchEvent(new Event('input'));
  await new Promise((done) => setTimeout(done, 330));
  const options = [...b.doc.querySelectorAll('[role=option]')];
  assert.deepEqual(
    options.map((option) => option.dataset.kind),
    ['precinct', 'address'],
  );
  assert.match(options[0].textContent, /SEA 34-3230.*Precinct/);
  assert.match(options[1].textContent, /Public civic building.*Address/);
  assert.equal(b.doc.querySelector('[data-precinct-submit]').disabled, true);
  const enter = new KeyboardEvent('keydown', { key: 'Enter', bubbles: true, cancelable: true });
  input.dispatchEvent(enter);
  assert.equal(enter.defaultPrevented, true);
  assert.equal(b.pending.length, 0);
  options[0].click();
  assert.equal(b.query(), '?precinct=all&races=all');
  assert.equal(b.doc.querySelector('[data-precinct-submit]').disabled, false);
  b.doc.querySelector('form').dispatchEvent(new Event('submit', { cancelable: true }));
  assert.equal(b.query(), '?precinct=3230&races=all');
});
async function chooseAddress(b) {
  const input = b.doc.querySelector('[data-ballot-search]');
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
  assert.equal(b.doc.querySelector('[data-ballot-search]').value, '');
});
for (const boundary of ['cancel', 'edit', 'history', 'local-query', 'close-reopen'])
  test(`late resolution cannot revive canceled draft: ${boundary}`, async () => {
    const b = boot();
    const input = await chooseAddress(b);
    if (boundary === 'cancel' || boundary === 'close-reopen')
      b.doc.querySelector('[data-precinct-cancel]').click();
    if (boundary === 'close-reopen') b.doc.querySelector('[data-precinct-open]').click();
    if (boundary === 'history') b.history();
    if (boundary === 'local-query') {
      input.value = '323';
      input.dispatchEvent(new Event('input'));
    }
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
  const input = b.doc.querySelector('[data-ballot-search]');
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
  const input = b.doc.querySelector('[data-ballot-search]');
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
  assert.match(b.doc.querySelector('[role=listbox]').textContent, /Newer canonical/);
  assert.equal(
    b.doc.querySelector('[role=listbox]').textContent.includes('Older canonical'),
    false,
  );
  assert.equal(b.doc.querySelector('[data-precinct-submit]').disabled, true);
});

test('lookup failure retains direct precinct fallback and never prints raw errors', async () => {
  const b = boot();
  await chooseAddress(b);
  b.pending[0]({ status: 'unavailable' });
  await flush();
  assert.match(
    b.doc.querySelector('[data-precinct-status]').textContent,
    /Choose a precinct suggestion/,
  );
  const direct = b.doc.querySelector('#voting-precinct');
  direct.value = '3230';
  direct.dispatchEvent(new Event('input'));
  b.doc.querySelector('[role=option][data-kind=precinct]').click();
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
  const input = b.doc.querySelector('[data-ballot-search]');
  input.value = 'Canonical';
  input.dispatchEvent(new Event('input'));
  await new Promise((done) => setTimeout(done, 330));
  input.dispatchEvent(
    new KeyboardEvent('keydown', { key: 'ArrowUp', bubbles: true, cancelable: true }),
  );
  assert.equal(input.getAttribute('aria-activedescendant'), 'ballot-option-1');
});

test('late address suggestions preserve an active local row and cannot revive a selected precinct', async () => {
  const searches = [];
  const b = boot({ suggest: () => new Promise((done) => searches.push(done)) });
  const input = b.doc.querySelector('[data-ballot-search]');
  input.value = '323';
  input.dispatchEvent(new Event('input'));
  input.dispatchEvent(
    new KeyboardEvent('keydown', { key: 'ArrowDown', bubbles: true, cancelable: true }),
  );
  await new Promise((done) => setTimeout(done, 330));
  searches[0]([{ text: 'SEA 34-3230', magicKey: 'different-kind', isCollection: false }]);
  await flush();
  assert.equal(input.getAttribute('aria-activedescendant'), 'ballot-option-0');
  assert.deepEqual(
    [...b.doc.querySelectorAll('[role=option]')].map((o) => o.dataset.kind),
    ['precinct', 'address'],
  );
  input.dispatchEvent(
    new KeyboardEvent('keydown', { key: 'Enter', bubbles: true, cancelable: true }),
  );
  assert.equal(input.value, 'SEA 34-3230');
  assert.equal(b.pending.length, 0);
  assert.equal(b.doc.querySelector('[data-precinct-submit]').disabled, false);
  assert.equal(b.query(), '?precinct=all&races=all');
});

test('a local choice wins over an older in-flight address resolution', async () => {
  const b = boot();
  const input = await chooseAddress(b);
  input.value = '323';
  input.dispatchEvent(new Event('input'));
  b.doc.querySelector('[role=option][data-kind=precinct]').click();
  b.pending[0]({ status: 'resolved', code: '3230' });
  await flush();
  assert.equal(input.value, 'SEA 34-3230');
  b.doc.querySelector('form').dispatchEvent(new Event('submit', { cancelable: true }));
  assert.equal(b.doc.querySelector('[data-precinct-open]').textContent, 'SEA 34-3230');
});

test('applied address label is ephemeral; cancel retains it and history restores only precinct', async () => {
  const b = boot();
  await chooseAddress(b);
  b.pending[0]({ status: 'resolved', code: '3230' });
  await flush();
  b.doc.querySelector('form').dispatchEvent(new Event('submit', { cancelable: true }));
  assert.equal(b.doc.querySelector('[data-precinct-open]').textContent, 'Public civic building');
  assert.equal(window.localStorage.getItem('seg-precinct-v1:wa-2026-general'), '3230');
  assert.equal(b.query().includes('Public'), false);
  b.doc.querySelector('[data-precinct-open]').click();
  const input = b.doc.querySelector('[data-ballot-search]');
  assert.equal(input.value, 'Public civic building');
  input.value = 'Uncommitted query';
  input.dispatchEvent(new Event('input'));
  b.doc.querySelector('[data-precinct-cancel]').click();
  assert.equal(input.value, '');
  assert.equal(b.doc.querySelector('[data-precinct-open]').textContent, 'Public civic building');
  b.history();
  assert.equal(b.doc.querySelector('[data-precinct-open]').textContent, 'SEA 34-3230');
});

test('IME composition never looks up intermediate text or commits on Enter', async () => {
  let calls = 0;
  const b = boot({
    suggest: async () => {
      calls += 1;
      return [];
    },
  });
  const input = b.doc.querySelector('[data-ballot-search]');
  input.dispatchEvent(new Event('compositionstart'));
  input.value = 'Public';
  input.dispatchEvent(new Event('input'));
  input.dispatchEvent(
    new KeyboardEvent('keydown', { key: 'Enter', isComposing: true, bubbles: true }),
  );
  await new Promise((done) => setTimeout(done, 330));
  assert.equal(calls, 0);
  assert.equal(b.query(), '?precinct=all&races=all');
  input.dispatchEvent(new Event('compositionend'));
  await new Promise((done) => setTimeout(done, 330));
  assert.equal(calls, 1);
});

test('a detached suggestion from an older query cannot select the current draft', () => {
  const b = boot();
  const input = b.doc.querySelector('[data-ballot-search]');
  input.value = '323';
  input.dispatchEvent(new Event('input'));
  const old = b.doc.querySelector('[role=option][data-kind=precinct]');
  input.value = 'Different query';
  input.dispatchEvent(new Event('input'));
  old.click();
  assert.equal(b.doc.querySelector('[data-precinct-submit]').disabled, true);
  assert.equal(input.value, 'Different query');
  b.doc.querySelector('[data-precinct-cancel]').click();
});

test('numeric and spaced prefixes both reach suggestions after the same debounce', async () => {
  const sent = [];
  const b = boot({
    suggest: async (text) => {
      sent.push(text);
      return [];
    },
  });
  const input = b.doc.querySelector('[data-ballot-search]');
  for (const text of ['2857', '2857 n']) {
    input.value = text;
    input.dispatchEvent(new Event('input'));
    await new Promise((done) => setTimeout(done, 330));
  }
  assert.deepEqual(sent, ['2857', '2857 n']);
});

test('suggestion status omits counts and refinement prompts even for capped precinct lists', () => {
  const b = boot(
    {},
    {
      precincts: Array.from({ length: 15 }, (_, i) => ({
        code: `3${i}`,
        name: `SEA 34-3${i}`,
        contest_ids: ['measure'],
      })),
    },
  );
  const input = b.doc.querySelector('[data-ballot-search]');
  input.value = '3';
  input.dispatchEvent(new Event('input'));
  assert.equal(b.doc.querySelectorAll('[role=option]').length, 10);
  assert.doesNotMatch(
    b.doc.querySelector('[data-precinct-status]').textContent,
    /\d|refine|type more/i,
  );
});

test('empty or failed suggestions announce availability without claiming the address has no match', async () => {
  for (const suggest of [
    async () => [],
    async () => {
      throw new Error('private detail');
    },
  ]) {
    const b = boot({ suggest });
    const input = b.doc.querySelector('[data-ballot-search]');
    input.value = 'Public civic';
    input.dispatchEvent(new Event('input'));
    await new Promise((done) => setTimeout(done, 330));
    assert.equal(
      b.doc.querySelector('[data-precinct-status]').textContent,
      'No suggestions available.',
    );
  }
});
