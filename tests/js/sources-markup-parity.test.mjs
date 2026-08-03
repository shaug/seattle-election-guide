// The markup-parity check docs/FRONTEND.md § Rendering calls for, applied to
// the sources editor's selectable tree (issue #248), on the harness issue #238
// built.
//
// The tree is the third case of the takeover idiom, and the one this page
// exists to demonstrate: it is a field of controls, so lit takes it at boot
// rather than on the reader's first click — a takeover triggered by that click
// would destroy the checkbox they are holding. Taking it at boot means the
// parity claim is made against the boot render itself, which is the strongest
// form of it: the very first thing lit does to the page has to be indeed
// indistinguishable from what the server sent.
//
// The comparison-only section and the coverage-gaps section are outside the
// region and are asserted to be untouched, because "the region" is a claim
// about a boundary as much as about markup.

import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';
import { fileURLToPath } from 'node:url';
import { installDom } from './support/dom.mjs';
import { assertMarkupParity } from './support/markup-parity.mjs';

// Must match tests/page_parity.py's SOURCES_PAGE_URL: it is what the fixture's
// relative links resolve against.
const PAGE_URL = 'https://seattleelections.guide/e/wa-2026-primary/sources/';

const AUDITED_PAGE = readFileSync(
  fileURLToPath(new URL('./fixtures/sources-audited-page.html', import.meta.url)),
  'utf8',
);

// The DOM first, then lit-html and anything that reaches it: see dom.mjs.
const document = installDom(PAGE_URL);
const { wireSourcesEditor } = await import(
  '../../src/election_guide/rendering/templates/sources-client.mjs'
);
const { readClientPayload } = await import(
  '../../src/election_guide/rendering/templates/client-payload.mjs'
);

document.write(AUDITED_PAGE);

const payload = /** @type {SourcesPayload} */ (readClientPayload(document));
assert.ok(payload, 'the audited sources fixture carries no readable payload');

/** @param {string} selector */
function required(selector) {
  const element = document.querySelector(selector);
  assert.ok(element, `the audited sources fixture has no ${selector}`);
  return element;
}

/**
 * A detached copy of one region's children, so the server's markup survives the
 * render that replaces it.
 *
 * @param {Element} region
 */
function detachedCopy(region) {
  const container = document.createElement('div');
  for (const child of [...region.childNodes]) container.append(child.cloneNode(true));
  return container;
}

const tree = required('[data-sources-tree]');
const count = required('[data-sources-count]');
const auditedTree = detachedCopy(tree);
const auditedCount = detachedCopy(count);
const comparisonSection = required('.sources-category-comparison');
const coverageGaps = document.querySelector('.screen-coverage-gaps');
const outsideTheRegion = [comparisonSection, coverageGaps].filter((element) => element !== null);
assert.ok(outsideTheRegion.length > 0, 'the fixture has nothing outside the region to protect');

wireSourcesEditor(payload);

test('the boot render of the tree is the tree the Jinja template rendered', () => {
  assertMarkupParity({
    region: "the sources editor's selectable tree",
    client: tree,
    server: auditedTree,
    base: PAGE_URL,
  });
});

test('the boot render of the count line is the line the Jinja template rendered', () => {
  assertMarkupParity({
    region: "the sources editor's count line",
    client: count,
    server: auditedCount,
    base: PAGE_URL,
  });
});

test('nothing outside the region is touched', () => {
  for (const element of outsideTheRegion) {
    assert.ok(
      element.isConnected && element.parentElement !== null,
      'a section outside the selection region was removed by the takeover',
    );
    assert.equal(
      element.querySelectorAll('[data-sources-source]').length,
      0,
      'a section outside the selection region acquired a checkbox',
    );
  }
});

// A source selectable under two categories renders a row under each and is
// still one source to count. The published panel has one, so the count line
// and the row count genuinely differ here, and a count taken over rows rather
// than over codes would be wrong on the real page.
test('the audited default counts every source it renders, once each', () => {
  const boxes = [...tree.querySelectorAll('[data-sources-source]')];
  assert.ok(boxes.length > 1, 'the audited sources fixture rendered no checkboxes');
  assert.ok(
    boxes.every((box) => /** @type {HTMLInputElement} */ (box).checked),
    'the audited default is every source counted',
  );

  const rows = payload.tree.flatMap((category) => category.sources.map((source) => source.code));
  const unique = new Set(rows);
  assert.equal(boxes.length, rows.length);
  assert.ok(
    unique.size < rows.length,
    'the published panel no longer shares a source between two categories',
  );
  assert.equal(count.textContent, `Counting ${unique.size} of ${unique.size} sources.`);
});
