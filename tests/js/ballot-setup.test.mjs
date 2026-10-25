import assert from 'node:assert/strict';
import test from 'node:test';
import { installDom } from './support/dom.mjs';
import { assertModuleGuard } from './support/module-guards.mjs';

installDom();
const { wireBallotSetup } = await import(
  '../../src/election_guide/rendering/templates/ballot-setup.mjs'
);
const contract = {
  election_id: 'test',
  groups: [
    {
      id: 'ld',
      label: 'Legislative district',
      mode: 'district',
      options: [
        { id: 'ld1', label: 'District 1' },
        { id: 'ld2', label: 'District 2' },
      ],
    },
  ],
  races: {
    one: { jurisdiction_id: 'ld1', group_id: 'ld', shared: false },
    two: { jurisdiction_id: 'ld2', group_id: 'ld', shared: false },
  },
};
const flush = async () => {
  for (let i = 0; i < 8; i++) await Promise.resolve();
};
function setup() {
  installDom('https://example.org/e/test/');
  document.body.innerHTML = '<p data-ballot-status role="status"></p><div data-ballot-setup></div>';
}
test('district edits, browsing, and clearing preserve the live region and persist a versioned profile', async () => {
  setup();
  let state;
  const saved = [];
  const status = document.querySelector('[data-ballot-status]');
  wireBallotSetup(
    contract,
    (next) => {
      state = next;
    },
    {
      read: async () => null,
      write: async (...args) => {
        saved.push(args);
      },
    },
  );
  const select = document.querySelector('select');
  select.value = 'ld1';
  select.dispatchEvent(new Event('change'));
  assert.equal(state.active, true);
  assert.doesNotMatch(status.textContent, /Browsing all/);
  assert.equal(state.complete, true);
  assert.equal(state.membership.two, 'inapplicable');
  const controls = [...document.querySelectorAll('button')];
  controls[1].click();
  assert.equal(state.active, false);
  assert.equal(select.value, 'ld1');
  controls[2].click();
  await flush();
  assert.equal(saved.at(-1)[1], null);
  assert.equal(document.querySelector('select').value, '');
  assert.equal(document.querySelector('[data-ballot-status]'), status);
});
test('saved profiles restore across pages and invalid or stale values remain uncertain', async () => {
  setup();
  let state;
  wireBallotSetup(
    contract,
    (next) => {
      state = next;
    },
    { read: async () => ({ version: 1, mode: 'ballot', choices: { ld: 'invalid' } }) },
  );
  await flush();
  assert.equal(state.active, true);
  assert.equal(state.complete, false);
  assert.equal(state.membership.one, 'unresolved');
  setup();
  wireBallotSetup(
    contract,
    (next) => {
      state = next;
    },
    { read: async () => ({ version: 1, mode: 'ballot', choices: { ld: 'ld2' } }) },
  );
  await flush();
  assert.equal(state.membership.one, 'inapplicable');
  assert.equal(document.querySelector('select').value, 'ld2');
});
test('a late saved profile cannot overwrite a newer edit, and storage failure is visible', async () => {
  setup();
  let finish;
  let state;
  wireBallotSetup(
    contract,
    (next) => {
      state = next;
    },
    {
      read: () =>
        new Promise((resolve) => {
          finish = resolve;
        }),
      write: async () => {
        throw Error('denied');
      },
    },
  );
  const select = document.querySelector('select');
  select.value = 'ld1';
  select.dispatchEvent(new Event('change'));
  finish({ version: 1, mode: 'ballot', choices: { ld: 'ld2' } });
  await flush();
  assert.equal(state.membership.one, 'applicable');
  assert.match(
    document.querySelector('[data-ballot-status]').textContent,
    /could not be remembered/,
  );
  assert.equal(document.querySelector('select'), select);
});
test('missing archived contract keeps the server baseline', () => {
  setup();
  const root = document.querySelector('[data-ballot-setup]');
  root.textContent = 'Unavailable';
  wireBallotSetup(null, () => {
    throw Error('unexpected');
  });
  assert.equal(root.textContent, 'Unavailable');
});
test('module guard', () => assertModuleGuard('ballot-setup.mjs'));

test('geography explanation belongs to the expandable setup guidance', () => {
  setup();
  const notice = 'A reviewed geography explanation.';
  wireBallotSetup({ ...contract, inventory_notice: notice }, () => {}, { read: async () => null });
  const details = document.querySelector('[data-ballot-setup] details');
  assert.ok(details.textContent.includes(notice));
  assert.equal(details.open, false);
  details.open = true;
  assert.ok(details.textContent.includes(notice));
});

test('official lookup links preserve the open ballot setup and referrer', () => {
  setup();
  wireBallotSetup(contract, () => {}, { read: async () => null });
  const links = [...document.querySelectorAll('[data-ballot-setup] a')];
  assert.equal(links.length, 2);
  for (const link of links) {
    assert.equal(new URL(link.href).protocol, 'https:');
    assert.equal(link.target, '_blank');
    assert.ok(link.relList.contains('noopener'));
    assert.equal(link.relList.contains('noreferrer'), false);
  }
});
