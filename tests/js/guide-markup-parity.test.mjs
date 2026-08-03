// The markup-parity check docs/FRONTEND.md § Rendering calls for, applied to
// the guide's lens regions (issue #248), on the harness issue #238 built.
//
// Every claim is made against the audited page itself — `tests/page_parity.py`
// renders it and commits the result — rather than against a hand-written
// fixture, because the rule is about the real server output.
//
// The guide's card regions are the content-projection half of the takeover
// idiom: booting at the audited default does no work on them at all; a
// divergent selection takes them over; returning to the default re-renders
// them, and what lit renders is what Jinja rendered, node for node.
//
// The lens strip above them is deliberately not a region at all, and this file
// pins that too — see the test below.

import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';
import { fileURLToPath } from 'node:url';
import { installDom } from './support/dom.mjs';
import { assertMarkupParity } from './support/markup-parity.mjs';

// Must match tests/page_parity.py's GUIDE_PAGE_URL: it is what the fixture's
// relative links resolve against.
const PAGE_URL = 'https://seattleelections.guide/e/wa-2026-primary/';

const AUDITED_PAGE = readFileSync(
  fileURLToPath(new URL('./fixtures/guide-audited-page.html', import.meta.url)),
  'utf8',
);

// The DOM first, then lit-html and anything that reaches it: see dom.mjs.
const document = installDom(PAGE_URL);
const { wireGuide } = await import('../../src/election_guide/rendering/templates/guide-client.mjs');
const { readClientPayload } = await import(
  '../../src/election_guide/rendering/templates/client-payload.mjs'
);

document.write(AUDITED_PAGE);

const payload = /** @type {GuidePayload} */ (readClientPayload(document));
assert.ok(payload, 'the audited guide fixture carries no readable payload');

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

/** @param {string} selector */
function required(selector) {
  const element = document.querySelector(selector);
  assert.ok(element, `the audited guide fixture has no ${selector}`);
  return element;
}

const bannerStatus = required('[data-lens-banner-status]');
const lensNotice = required('[data-lens-notice]');
const auditedStatusText = bannerStatus.textContent;

const REGIONS = ['[data-lens-result]', '[data-lens-context]', '[data-lens-foot]'];

/**
 * Every card on the published page, not one of them: the branches that differ
 * between races — an absent share, a no-majority tone, a low fill, an
 * insufficient grade — are exactly where the two renderers can disagree, and
 * the whole ballot is what covers them. This is the check that caught a real
 * rounding difference when issue #238 first ran it on the Comparisons table.
 *
 * @type {{ raceId: string, card: Element, audited: Map<string, Element> }[]}
 */
const cards = [...document.querySelectorAll('[data-publication-race-id]')].map((card) => ({
  raceId: /** @type {string} */ (/** @type {HTMLElement} */ (card).dataset.publicationRaceId),
  card,
  audited: new Map(
    REGIONS.map((selector) => {
      const region = card.querySelector(selector);
      assert.ok(region, `a rendered card has no ${selector} region`);
      return [selector, detachedCopy(region)];
    }),
  ),
}));
assert.ok(cards.length > 1, 'the audited guide fixture rendered no race cards');
const raceId = cards[0].raceId;
const auditedResultChild = required('[data-lens-result]').firstElementChild;

wireGuide(payload);

test('booting at the audited default leaves every card region untouched', () => {
  assert.ok(
    required('[data-lens-result]').firstElementChild === auditedResultChild,
    'the client rebuilt a card region at the audited default. The server renders the ' +
      'complete audited baseline and the default view does no DOM work on it ' +
      '(rule: rendering, docs/FRONTEND.md).',
  );
});

// The lens strip is not a takeover at all: its two announcing elements stay the
// server's for the life of the page, and lit renders only the text inside them,
// because a live region announces a change only if it was already in the
// accessibility tree when the change happened (docs/FRONTEND.md § Rendering).
// There is therefore no region to diff — the stronger claim is that the very
// same elements are still there, still saying what the server said.
test("booting leaves the strip's announcing elements exactly where they were", () => {
  assert.ok(required('[data-lens-banner-status]') === bannerStatus);
  assert.ok(required('[data-lens-notice]') === lensNotice);
  assert.equal(bannerStatus.getAttribute('aria-live'), 'polite');
  assert.equal(lensNotice.getAttribute('aria-live'), 'polite');
  assert.equal(bannerStatus.textContent, auditedStatusText);
  assert.equal(lensNotice.hidden, true);
});

/** Drive the page to a selection that is not the audited default, and back. */
function goTo(fragment) {
  window.location.hash = fragment;
  window.dispatchEvent(new Event('hashchange'));
}

/**
 * A same-version selection fragment naming exactly `codes`.
 *
 * @param {readonly string[]} codes
 */
const selectionFragment = (codes) =>
  `#lens=2&mode=s&panel=${payload.panel_id}&ph=${payload.panel_hash.slice(0, 12)}` +
  `&data=${payload.data_version}&scoring=${payload.scoring.configuration_id}` +
  `&sel=${codes.join('')}&race=${raceId}`;

test('the audited restore is a render, and it reproduces the audited card markup', () => {
  // One source dropped is enough to leave the audited default; which one does
  // not matter, because the claim is about the restore rather than the result.
  const codes = payload.sources
    .filter((source) => source.panel_role !== 'comparison' && source.selectable)
    .map((source) => source.code);
  assert.ok(codes.length > 1, 'the audited guide fixture publishes too few tallying sources');

  goTo(selectionFragment(codes.slice(1)));
  assert.ok(
    required('[data-lens-result]').firstElementChild !== auditedResultChild,
    'a divergent selection should have taken the card regions over from the server',
  );

  // Back to the audited default. A link naming every tallying source is what
  // the reader gets from the sources page's Reset, and is the only thing that
  // clears a lens: an absent fragment carries no selection to apply, so it
  // leaves the one already on the page alone.
  goTo(selectionFragment(codes));

  for (const { raceId: id, card, audited } of cards) {
    for (const selector of REGIONS) {
      const region = card.querySelector(selector);
      assert.ok(region);
      assertMarkupParity({
        region: `the ${id} card's ${selector} region`,
        client: region,
        server: /** @type {Element} */ (audited.get(selector)),
        base: PAGE_URL,
      });
    }
  }
});
