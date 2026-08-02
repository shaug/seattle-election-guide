// The markup-parity check docs/FRONTEND.md § Rendering calls for, and the
// evidence for the region-takeover idiom the same section records.
//
// Both claims are made against the audited page itself — `tests/compare_parity.py`
// renders it and commits the result — rather than against a hand-written
// fixture, because the rule is about the real server output:
//
//   1. Booting the page at the audited default does no work on the row groups.
//      The elements the server rendered are still the very same elements.
//   2. Once a filter takes the region over, returning to the audited default
//      re-renders it — and what lit renders is what the Jinja template
//      rendered, node for node, attribute for attribute.
//
// Together those are the idiom: the server owns the audited baseline, lit takes
// a region only when interaction needs it, and the audited restore is a render
// of the audited view model rather than a copy of the server's markup kept
// around.

import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';
import { fileURLToPath } from 'node:url';
import { installDom } from './support/dom.mjs';
import { assertMarkupParity } from './support/markup-parity.mjs';

// Must match tests/compare_parity.py's PAGE_URL: it is what the fixture's
// relative links resolve against.
const PAGE_URL = 'https://seattleelections.guide/e/wa-2026-primary/comparisons/';

const AUDITED_PAGE = readFileSync(
  fileURLToPath(new URL('./fixtures/compare-audited-page.html', import.meta.url)),
  'utf8',
);

// The DOM first, then lit-html and anything that reaches it: see dom.mjs.
const document = installDom(PAGE_URL);
const { wireComparisons } = await import(
  '../../src/election_guide/rendering/templates/compare-client.mjs'
);

document.write(AUDITED_PAGE);

const table = /** @type {HTMLTableElement} */ (document.querySelector('[data-comparison-table]'));
assert.ok(table, 'the audited fixture has no comparison table');

/** @param {HTMLTableElement} source */
function rowGroups(source) {
  return [...source.querySelectorAll('tbody')];
}

/**
 * A detached container holding copies of the row groups, so the audited markup
 * survives the render that replaces it.
 *
 * @param {Element[]} bodies
 */
function detachedCopy(bodies) {
  const container = document.createElement('table');
  for (const body of bodies) container.append(body.cloneNode(true));
  return container;
}

const auditedBodies = rowGroups(table);
const auditedRegion = detachedCopy(auditedBodies);
const firstAuditedBody = auditedBodies[0];
assert.ok(firstAuditedBody, 'the audited fixture rendered no row groups');

wireComparisons();

test('booting at the audited default leaves the row groups exactly as rendered', () => {
  assert.ok(
    rowGroups(table)[0] === firstAuditedBody,
    'the client rebuilt the row groups at the audited default. The server renders the ' +
      'complete audited baseline and the default view does no DOM work on it ' +
      '(rule: rendering, docs/FRONTEND.md).',
  );
  assert.equal(rowGroups(table).length, auditedBodies.length);
});

test('the head is taken over at boot, because its controls cannot be audited markup', () => {
  const head = document.querySelector('[data-comparison-head]');
  assert.ok(head);
  assert.ok(
    head.querySelector('[data-comparison-title="0"]'),
    'the column controls the reader interacts with should exist after boot',
  );
});

/** @param {string} selector */
function toggle(selector) {
  const input = /** @type {HTMLInputElement} */ (document.querySelector(selector));
  assert.ok(input, `the audited fixture has no ${selector}`);
  input.checked = true;
  input.dispatchEvent(new Event('change', { bubbles: true }));
}

test('the audited restore is a render, and it reproduces the audited markup', () => {
  // Take the region over, then ask for the audited default back.
  toggle('[data-comparison-differences]');
  assert.ok(
    rowGroups(table)[0] !== firstAuditedBody,
    'filtering should have taken the row groups over from the server',
  );

  toggle('[data-comparison-full]');

  assertMarkupParity({
    region: "the Comparisons table's row groups",
    client: detachedCopy(rowGroups(table)),
    server: auditedRegion,
    base: PAGE_URL,
  });
});
