// guide-dialog.mjs is the race-detail dialog and the hash routing that opens
// and closes it, extracted from guide.html.j2's classic script by issue #239.
// Issue #136 replaces the dialog with per-race pages, so it was moved rather
// than improved; these tests pin the behavior the move had to preserve, plus
// the two rules the move enforced (the codec owns the hash, and the race label
// comes from the payload).

import assert from 'node:assert/strict';
import test from 'node:test';
import { installDom } from './support/dom.mjs';
import { assertModuleGuard } from './support/module-guards.mjs';

const GUIDE_URL = 'https://seattleelections.guide/e/wa-2026-primary/';

const PAYLOAD = /** @type {any} */ ({
  races: [
    { race_id: 'mayor', race_label: 'Seattle Mayor' },
    { race_id: 'council', race_label: 'City Council Position 8' },
  ],
});

function dialogMarkup() {
  return `
    <article id="race-mayor" data-publication-race-id="mayor">
      <a href="#race-mayor" data-race-detail-link>Mayor</a>
      <dialog data-race-detail-dialog data-race-id="mayor">
        <button type="button" data-copy-race-link="race-mayor"></button>
        <button type="button" data-close-race-detail></button>
        <p data-copy-race-status></p>
      </dialog>
    </article>
    <article id="race-council" data-publication-race-id="council">
      <a href="#race-council" data-race-detail-link>Council</a>
      <dialog data-race-detail-dialog data-race-id="council">
        <button type="button" data-copy-race-link="race-council"></button>
        <button type="button" data-close-race-detail></button>
        <p data-copy-race-status></p>
      </dialog>
    </article>`;
}

/** A filters stand-in that records whether the dialog had to clear the filter. */
function stubFilters() {
  return {
    calls: /** @type {string[]} */ ([]),
    apply() {
      this.calls.push('apply');
    },
    syncFromUrl() {
      this.calls.push('syncFromUrl');
    },
    showEveryRace() {
      this.calls.push('showEveryRace');
    },
  };
}

/** @param {string} url */
async function wire(url) {
  const document = installDom(url);
  document.body.innerHTML = dialogMarkup();
  // happy-dom implements `<dialog>` but not the modal semantics, and the module
  // only ever asks whether one is open.
  for (const dialog of document.querySelectorAll('dialog')) {
    dialog.showModal = function showModal() {
      this.open = true;
    };
    dialog.close = function close() {
      this.open = false;
    };
  }
  const { wireRaceDialogs } = await import(
    '../../src/election_guide/rendering/templates/guide-dialog.mjs'
  );
  const { createLensRouter } = await import(
    '../../src/election_guide/rendering/templates/lens-route.mjs'
  );
  const filters = stubFilters();
  const dialogs = wireRaceDialogs(PAYLOAD, createLensRouter(), filters);
  return { document, filters, dialogs };
}

/** @param {Document} document @param {string} raceId */
const dialogFor = (document, raceId) =>
  document.querySelector(`[data-race-detail-dialog][data-race-id="${raceId}"]`);

test('a race permalink opens that race on arrival', async () => {
  const { document } = await wire(`${GUIDE_URL}#race-mayor`);
  assert.equal(dialogFor(document, 'mayor').open, true);
  assert.equal(dialogFor(document, 'council').open, false);
});

test('no fragment opens nothing', async () => {
  const { document } = await wire(GUIDE_URL);
  assert.equal(dialogFor(document, 'mayor').open, false);
});

// Issue 142: an active lens leaves the hash non-empty with no dialog open, so
// the dialog must decide by the resolved race id, not by hash truthiness.
test('an active lens with no race segment opens nothing', async () => {
  const { document } = await wire(`${GUIDE_URL}#lens=2&mode=s&sel=strn`);
  assert.equal(dialogFor(document, 'mayor').open, false);
});

test('a lens fragment naming a race opens it', async () => {
  const { document } = await wire(`${GUIDE_URL}#lens=2&mode=s&sel=strn&race=race-mayor`);
  assert.equal(dialogFor(document, 'mayor').open, true);
});

test('opening a race pushes its target without disturbing the lens', async () => {
  const { document } = await wire(`${GUIDE_URL}#lens=2&mode=s&sel=strn`);
  document
    .querySelector('#race-council [data-race-detail-link]')
    .dispatchEvent(new Event('click', { bubbles: true, cancelable: true }));
  assert.match(window.location.hash, /sel=strn/);
  assert.match(window.location.hash, /race=race-council/);
  assert.equal(dialogFor(document, 'council').open, true);
  assert.deepEqual(window.history.state, { raceDetail: 'race-council' });
});

test('closing a race strips only its segment, never the lens', async () => {
  const { document } = await wire(`${GUIDE_URL}#lens=2&mode=s&sel=strn&race=race-mayor`);
  document
    .querySelector('#race-mayor [data-close-race-detail]')
    .dispatchEvent(new Event('click', { bubbles: true }));
  assert.match(window.location.hash, /sel=strn/);
  assert.ok(!window.location.hash.includes('race='));
  assert.equal(dialogFor(document, 'mayor').open, false);
});

test('a race hidden by the filter is revealed rather than opened invisibly', async () => {
  const { document, filters } = await wire(GUIDE_URL);
  document.getElementById('race-mayor').hidden = true;
  window.location.hash = '#race-mayor';
  window.dispatchEvent(new Event('hashchange'));
  assert.ok(filters.calls.includes('showEveryRace'));
});

// The read this ticket removed: the share status used to take the race label
// from the card's `[data-display-role="race-label"]` text.
test('the share status names the race from the payload, not the card', async () => {
  const { document } = await wire(`${GUIDE_URL}#race-mayor`);
  /** @type {string[]} */
  const shared = [];
  globalThis.navigator.clipboard = {
    writeText: async (/** @type {string} */ value) => {
      shared.push(value);
    },
  };
  const button = document.querySelector('#race-mayor [data-copy-race-link]');
  button.dispatchEvent(new Event('click', { bubbles: true }));
  await new Promise((resolve) => setTimeout(resolve, 0));

  assert.equal(
    document.querySelector('#race-mayor [data-copy-race-status]').textContent,
    'Link copied for Seattle Mayor',
  );
  assert.equal(shared.length, 1);
  assert.match(shared[0], /#race-mayor$/);
});

test('the module keeps client state out of storage', () => {
  assertModuleGuard('guide-dialog.mjs');
});
