// compare-client.mjs is the Comparisons page's wiring: attaching the
// interactive table, its pickers, and its filters is DOM work by design, so it
// carries the storage tier of the shared guard rather than the full purity
// tier. It declares its real imports and loads standalone now that
// compare-entry.mjs bundles it, so its behavior coverage is no longer blocked
// on the bundler — it waits on a lightweight DOM (docs/FRONTEND.md § Testing).
//
// What the rest of this file covers is the rule that decode and encode failures
// are surfaced (docs/FRONTEND.md § State and URLs). Every way this page can
// fail to read or write its link is exercised against the audited page the
// server actually renders, because the defect the rule names is a failure the
// reader is never told about — and a status with no branch is indistinguishable
// from one the page decided to ignore.

import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';
import { fileURLToPath } from 'node:url';
import { installDom } from './support/dom.mjs';
import { assertModuleGuard } from './support/module-guards.mjs';

// Must match tests/compare_parity.py's PAGE_URL: it is what the fixture's
// relative links resolve against.
const PAGE = 'https://seattleelections.guide/e/wa-2026-primary/comparisons/';

const AUDITED_PAGE = readFileSync(
  fileURLToPath(new URL('./fixtures/compare-audited-page.html', import.meta.url)),
  'utf8',
);

// The DOM first, then lit-html and anything that reaches it: see dom.mjs.
installDom(PAGE);
const { wireComparisons } = await import(
  '../../src/election_guide/rendering/templates/compare-client.mjs'
);
const { compareContext, encodeCompareFragment } = await import(
  '../../src/election_guide/rendering/templates/compare-url.mjs'
);

/**
 * Boot the audited page at one address, optionally with an edited payload.
 *
 * The payload is data, not code: a published panel that stops offering a
 * source, or one whose configured defaults no longer resolve, is a payload this
 * page has to survive. Editing it is how the failure paths are reached without
 * inventing a page the server does not render.
 *
 * @param {object} [options]
 * @param {string} [options.fragment] The fragment to arrive on, `#` included.
 * @param {(payload: any) => void} [options.editPayload]
 * @returns {Document}
 */
function boot({ fragment = '', editPayload } = {}) {
  const document = installDom(`${PAGE}${fragment}`);
  document.write(AUDITED_PAGE);
  if (editPayload !== undefined) {
    const element = /** @type {Element} */ (document.querySelector('[data-client-payload]'));
    const payload = JSON.parse(/** @type {string} */ (element.textContent));
    editPayload(payload);
    element.textContent = JSON.stringify(payload);
  }
  wireComparisons();
  return document;
}

/** The payload the fixture publishes, read without wiring the page. */
function auditedPayload() {
  const document = installDom(PAGE);
  document.write(AUDITED_PAGE);
  const element = /** @type {Element} */ (document.querySelector('[data-client-payload]'));
  return JSON.parse(/** @type {string} */ (element.textContent));
}

/** @param {Document} document */
function notice(document) {
  const element = /** @type {HTMLElement} */ (
    document.querySelector('[data-comparison-hidden-notice]')
  );
  return { text: element.textContent, hidden: element.hidden };
}

/** @param {Document} document */
function columns(document) {
  return [...document.querySelectorAll('[data-comparison-head] [data-column-signal]')].map(
    (heading) => /** @type {HTMLElement} */ (heading).dataset.columnSignal,
  );
}

/**
 * @param {any} payload
 * @param {string} dataVersion
 * @param {string[]} configuredColumns
 */
function fragmentFor(payload, dataVersion, configuredColumns) {
  const context = compareContext(
    payload.personalization,
    dataVersion,
    payload.comparisons,
    configuredColumns,
  );
  const encoded = encodeCompareFragment(
    { columns: configuredColumns, differencesOnly: false, contestedOnly: false, section: 'all' },
    context,
  );
  assert.equal(encoded.status, 'ok', 'the fragment this test needs could not be written');
  return `#${encoded.fragment}`;
}

/** A link this publication accepts. */
const currentFragment = (payload, configuredColumns) =>
  fragmentFor(payload, payload.data_version, configuredColumns);

/**
 * A structurally valid link written against a publication this page has moved
 * on from: what a reader who saved a link before the last data update holds.
 */
const staleFragment = (payload, configuredColumns) =>
  fragmentFor(payload, 'a-published-version-ago', configuredColumns);

/**
 * The same, naming a reference this publication cannot resolve at all.
 *
 * Substituted rather than encoded, because the codec refuses to write a token
 * it does not know — which is the point: only a link written elsewhere, before
 * the identity went away, can carry one.
 *
 * @param {any} payload
 */
const unresolvableStaleFragment = (payload) =>
  staleFragment(payload, ['strn', 'stim']).replace('cols=strnstim', 'cols=zzzzstrn');

/** A panel that has stopped offering the source the Add control reaches for. */
function withdrawStranger(payload) {
  for (const source of payload.personalization.sources) {
    if (source.code === 'stim') source.selectable = false;
  }
}

test('wiring the page is a call the entry makes, not a module side effect', () => {
  assert.equal(typeof wireComparisons, 'function');
});

test('a link that decodes cleanly is shown with nothing to explain', () => {
  const document = boot({ fragment: currentFragment(auditedPayload(), ['gall', 'strn']) });
  assert.deepEqual(columns(document), ['gall', 'strn']);
  assert.deepEqual(notice(document), { text: '', hidden: true });
});

test('an unreadable link is named, cleaned away, and resolved to the default', () => {
  // `cols` is not a whole number of tokens, so the codec reports `malformed`
  // before it reaches any column identity.
  const document = boot({ fragment: '#cmp=1&cols=gallstr&panel=x&ph=y&data=z&scoring=w' });
  assert.deepEqual(notice(document), {
    text: 'This comparison link could not be read, so the default comparison is shown.',
    hidden: false,
  });
  assert.equal(window.location.hash, '');
  assert.deepEqual(columns(document), ['gall', 'strn', 'stim']);
});

test('a link written for the guide is not silently ignored on this page', () => {
  const document = boot({ fragment: '#lens=1&mode=a&panel=saved-panel&ph=abcdef123456' });
  assert.equal(notice(document).hidden, false);
  assert.equal(window.location.hash, '');
  assert.deepEqual(columns(document), ['gall', 'strn', 'stim']);
});

test('an ordinary in-page anchor is left alone and explains nothing', () => {
  // The skip link is not a comparison link, and the codec says so by name, so
  // using it neither manufactures an explanation nor disturbs the address bar.
  const document = boot({ fragment: '#comparison-main' });
  assert.deepEqual(notice(document), { text: '', hidden: true });
  assert.equal(window.location.hash, '#comparison-main');
});

test('a stale link that migrates says so and is rewritten to what it became', () => {
  const document = boot({ fragment: staleFragment(auditedPayload(), ['strn', 'stim']) });
  assert.deepEqual(notice(document), {
    text: 'This comparison link was updated for the current source list.',
    hidden: false,
  });
  assert.deepEqual(columns(document), ['strn', 'stim']);
  assert.ok(window.location.hash.includes('cols=strnstim'));
  assert.ok(!window.location.hash.includes('a-published-version-ago'));
});

test('a stale link that only partly survives says which part did not', () => {
  const document = boot({ fragment: unresolvableStaleFragment(auditedPayload()) });
  assert.deepEqual(notice(document), {
    text:
      'This comparison link could not be restored completely, so the default comparison ' +
      'is shown.',
    hidden: false,
  });
  assert.deepEqual(columns(document), ['gall', 'strn', 'stim']);
});

test('a stale link that cannot be migrated at all is named, not swallowed', () => {
  // The configured defaults are the fallback every unrestorable link resolves
  // to, so a publication whose own defaults no longer resolve is what makes the
  // migration reject outright rather than fall back.
  const document = boot({
    fragment: unresolvableStaleFragment(auditedPayload()),
    editPayload(payload) {
      payload.default_columns = ['gall', 'zzzz'];
    },
  });
  assert.deepEqual(notice(document), {
    text:
      'This comparison link could not be updated for the current source list, so the ' +
      'default comparison is shown.',
    hidden: false,
  });
  assert.equal(window.location.hash, '');
});

test('a change the codec refuses is not applied, and the reader is told why', () => {
  // Before this was surfaced the Add control simply did nothing: the encode was
  // rejected, the render was skipped, and the reader's click vanished.
  const fragment = currentFragment(auditedPayload(), ['gall', 'strn']);
  const document = boot({ fragment, editPayload: withdrawStranger });
  assert.deepEqual(columns(document), ['gall', 'strn']);

  const add = /** @type {HTMLElement} */ (document.querySelector('.comparison-column-add'));
  assert.ok(add, 'the audited default offers no Add control to exercise');
  add.click();

  assert.deepEqual(notice(document), {
    text: 'That change could not be put into a shareable link, so the comparison is unchanged.',
    hidden: false,
  });
  assert.deepEqual(columns(document), ['gall', 'strn']);
  assert.equal(window.location.hash, fragment);
});

test('a refused change leaves no half-applied column behind', () => {
  const document = boot({
    fragment: currentFragment(auditedPayload(), ['gall', 'strn']),
    editPayload: withdrawStranger,
  });
  /** @type {HTMLElement} */ (document.querySelector('.comparison-column-add')).click();
  // No third column exists, so nothing renders a picker for one: the reader is
  // looking at the two columns they had.
  assert.equal(document.querySelectorAll('[data-comparison-column]').length, 0);
  assert.equal(document.querySelectorAll('[data-comparison-title]').length, 2);
});

test('the next change that does take clears the explanation of the one that did not', () => {
  const document = boot({
    fragment: currentFragment(auditedPayload(), ['gall', 'strn']),
    editPayload: withdrawStranger,
  });
  /** @type {HTMLElement} */ (document.querySelector('.comparison-column-add')).click();
  assert.equal(notice(document).hidden, false);

  const differences = /** @type {HTMLInputElement} */ (
    document.querySelector('[data-comparison-differences]')
  );
  differences.checked = true;
  differences.dispatchEvent(new Event('change'));

  assert.deepEqual(notice(document), { text: '', hidden: true });
  assert.ok(window.location.hash.includes('diff=1'));
});

test('the module keeps client state out of storage', () => {
  assertModuleGuard('compare-client.mjs');
});
