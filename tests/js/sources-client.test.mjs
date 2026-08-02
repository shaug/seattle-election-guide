// sources-client.mjs is the standalone sources editor's wiring, extracted from
// sources.html.j2's inline module script by issue #239. Roughly half of what
// was inline was a hand-kept copy of the guide's lens glue; that half is
// `lens-selection.mjs` now, so these tests cover what is left — the checkbox
// tree, the three links, and the failures that used to fall through in silence
// (docs/FRONTEND.md § State and URLs).

import assert from 'node:assert/strict';
import test from 'node:test';
import { SELECTION_LINK_FAILURE_NOTICE } from '../../src/election_guide/rendering/templates/lens-selection.mjs';
import { installDom } from './support/dom.mjs';
import { assertModuleGuard } from './support/module-guards.mjs';

const SOURCES_URL = 'https://seattleelections.guide/e/wa-2026-primary/sources/';
const GUIDE_PATH = '/e/wa-2026-primary/';
const PANEL_HASH = '6cd4acaa0c5e4ed0b5ddd0134d7de2af5a54c2085e7ad463f9b575b8e6dcb43f';

/** @param {Record<string, unknown>} [overrides] */
function payload(overrides = {}) {
  return /** @type {any} */ ({
    schema_version: '1.0',
    data_version: 'd119ee3107bb',
    panel_id: 'wa-2026-primary-default-sources-v4',
    panel_hash: PANEL_HASH,
    policy: { maximum_url_characters: 4096 },
    scoring: { configuration_id: 'wa-2026-primary-equal-weight' },
    guide_path: GUIDE_PATH,
    categories: [
      {
        code: 'Gprs',
        label: 'Press',
        selectable: true,
        panel_role: 'tallying',
        member_source_codes: ['strn', 'urbn'],
      },
    ],
    sources: [
      { code: 'strn', name: 'The Stranger', selectable: true, panel_role: 'consensus' },
      { code: 'urbn', name: 'The Urbanist', selectable: true, panel_role: 'consensus' },
    ],
    ...overrides,
  });
}

function sourcesMarkup() {
  return `
    <p data-sources-count></p>
    <a data-sources-save href="${GUIDE_PATH}">Save</a>
    <a data-sources-cancel href="${GUIDE_PATH}">Cancel</a>
    <a data-sources-page-reset href="${GUIDE_PATH}">Reset</a>
    <p data-payload-notice hidden></p>
    <p data-sources-notice hidden></p>
    <section data-sources-category="Gprs">
      <input type="checkbox" data-sources-category-toggle="Gprs" checked>
      <input type="checkbox" data-sources-source="strn" data-sources-category-member="Gprs" checked>
      <input type="checkbox" data-sources-source="urbn" data-sources-category-member="Gprs" checked>
    </section>`;
}

/**
 * @param {string} url
 * @param {any} [pagePayload]
 */
async function wire(url, pagePayload = payload()) {
  const document = installDom(url);
  document.body.innerHTML = sourcesMarkup();
  const { wireSourcesEditor } = await import(
    '../../src/election_guide/rendering/templates/sources-client.mjs'
  );
  wireSourcesEditor(pagePayload);
  return document;
}

/** @param {Document} document @param {string} code */
const box = (document, code) => document.querySelector(`[data-sources-source="${code}"]`);
const notice = (/** @type {Document} */ document) =>
  document.querySelector('[data-sources-notice]');

test('arriving with no fragment counts every source', async () => {
  const document = await wire(SOURCES_URL);
  assert.equal(
    document.querySelector('[data-sources-count]').textContent,
    'Counting 2 of 2 sources.',
  );
  assert.equal(document.querySelector('[data-sources-save]').getAttribute('href'), GUIDE_PATH);
  assert.equal(notice(document).hidden, true);
});

test('an incoming selection checks exactly the sources it names', async () => {
  const document = await wire(
    `${SOURCES_URL}#lens=2&mode=s&sel=strn&panel=wa-2026-primary-default-sources-v4` +
      `&ph=${PANEL_HASH.slice(0, 12)}&data=d119ee3107bb&scoring=wa-2026-primary-equal-weight`,
  );
  assert.equal(box(document, 'strn').checked, true);
  assert.equal(box(document, 'urbn').checked, false);
  assert.equal(
    document.querySelector('[data-sources-count]').textContent,
    'Counting 1 of 2 sources.',
  );
});

test('the category toggle goes indeterminate when only some members count', async () => {
  const document = await wire(SOURCES_URL);
  const urbn = box(document, 'urbn');
  urbn.checked = false;
  urbn.dispatchEvent(new Event('change'));

  const toggle = document.querySelector('[data-sources-category-toggle]');
  assert.equal(toggle.checked, false);
  assert.equal(toggle.indeterminate, true);
});

test('the category toggle sets every member at once', async () => {
  const document = await wire(SOURCES_URL);
  const toggle = document.querySelector('[data-sources-category-toggle]');
  toggle.checked = false;
  toggle.dispatchEvent(new Event('change'));

  assert.equal(box(document, 'strn').checked, false);
  assert.equal(box(document, 'urbn').checked, false);
  assert.equal(
    document.querySelector('[data-sources-count]').textContent,
    'Counting 0 of 2 sources.',
  );
});

test('Save carries the edited selection back to the guide', async () => {
  const document = await wire(SOURCES_URL);
  const urbn = box(document, 'urbn');
  urbn.checked = false;
  urbn.dispatchEvent(new Event('change'));

  const href = document.querySelector('[data-sources-save]').getAttribute('href');
  assert.ok(href.startsWith(`${GUIDE_PATH}#`));
  assert.match(href, /sel=strn/);
});

test('Cancel restores exactly the fragment the reader arrived with', async () => {
  const incoming = '#race-mayor';
  const document = await wire(`${SOURCES_URL}${incoming}`);
  assert.equal(
    document.querySelector('[data-sources-cancel]').getAttribute('href'),
    `${GUIDE_PATH}${incoming}`,
  );
  assert.equal(
    document.querySelector('[data-sources-page-reset]').getAttribute('href'),
    GUIDE_PATH,
  );
});

// The silent loss this ticket fixes: a rejected encode used to fall through to
// the bare guide path, so Save published a link that dropped the reader's edit
// without saying so.
test('a selection too large to encode says so instead of dropping the edit', async () => {
  const document = await wire(SOURCES_URL, payload({ policy: { maximum_url_characters: 10 } }));
  const urbn = box(document, 'urbn');
  urbn.checked = false;
  urbn.dispatchEvent(new Event('change'));

  assert.equal(notice(document).hidden, false);
  assert.equal(notice(document).textContent, SELECTION_LINK_FAILURE_NOTICE);
  // The checkboxes still hold the edit; only the link could not carry it.
  assert.equal(box(document, 'strn').checked, true);
  assert.equal(box(document, 'urbn').checked, false);
});

test('the failure notice clears once the selection can be written again', async () => {
  const document = await wire(SOURCES_URL, payload({ policy: { maximum_url_characters: 10 } }));
  const urbn = box(document, 'urbn');
  urbn.checked = false;
  urbn.dispatchEvent(new Event('change'));
  assert.equal(notice(document).hidden, false);

  urbn.checked = true;
  urbn.dispatchEvent(new Event('change'));
  assert.equal(notice(document).hidden, true);
});

test('an unreadable incoming link is reported, not quietly ignored', async () => {
  const document = await wire(`${SOURCES_URL}#lens=9&mode=s&sel=strn`);
  assert.equal(notice(document).hidden, false);
  assert.match(notice(document).textContent, /could not be read/);
  // Falling back to the audited default is still the right resolution.
  assert.equal(box(document, 'strn').checked, true);
  assert.equal(box(document, 'urbn').checked, true);
});

// The skip link and any other plain in-page anchor decode the same way as a
// malformed lens, and must not manufacture a notice.
test('an ordinary in-page anchor is not a failure', async () => {
  const document = await wire(`${SOURCES_URL}#sources-main`);
  assert.equal(notice(document).hidden, true);
});

test('the module keeps client state out of storage', () => {
  assertModuleGuard('sources-client.mjs');
});
