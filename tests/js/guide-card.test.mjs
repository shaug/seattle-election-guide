// guide-card.mjs is the race card's lens-aware markup. It is a computing
// module — view model in, template out — so it takes the purity tier of the
// shared guard and is testable in the lightweight DOM
// (docs/FRONTEND.md § Testing).
//
// What these tests pin is the shape the audited Jinja template also produces,
// value by value: the classes and the `style` attribute the meter carries, the
// pill's `hidden`, and the fact that the card foot renders nothing at all for
// an ordinary audited race rather than empty elements waiting to be filled in.
// The whole-region agreement is `guide-markup-parity.test.mjs`'s claim; these
// are the branches that test does not reach with the published dataset.

import assert from 'node:assert/strict';
import test from 'node:test';
import { installDom } from './support/dom.mjs';
import { assertModuleGuard } from './support/module-guards.mjs';

// The DOM first, then lit-html and anything that reaches it: see dom.mjs.
const document = installDom();
const { render } = await import('lit-html');
const {
  candidateMeterTemplate,
  candidateMeterViews,
  raceContextTemplate,
  raceFootTemplate,
  raceResultTemplate,
} = await import('../../src/election_guide/rendering/templates/guide-card.mjs');

/** @param {unknown} template */
function rendered(template) {
  const host = document.createElement('div');
  document.body.replaceChildren(host);
  render(template, host);
  return host;
}

/**
 * @param {number|null} fillPercent
 * @param {boolean} [noMajority]
 * @returns {import('../../src/election_guide/rendering/templates/guide-card.mjs').ShareMeterView}
 */
// `lowFill`/`degraded` are explicit arguments rather than something this
// fixture derives. Both thresholds live in meterView (guide-card.mjs), which
// every meter on the site shares; a fixture that recomputed them would agree
// with whatever production chose and pin nothing. What this file checks is
// that the template honours the decision; `guide-lens.test.mjs` checks that
// the low-fill decision is made at 30%.
const meter = (fillPercent, { lowFill = false, noMajority = false, degraded = false } = {}) => ({
  label: fillPercent === null ? 'N/A' : `${fillPercent}%`,
  fillPercent,
  lowFill,
  noMajority,
  degraded,
  accessibleLabel: 'Ada Lovelace 3 of 4 endorsements',
  blocks:
    fillPercent === null
      ? []
      : [
          {
            type: 'solid',
            width: 1,
            style: '--meter-w:1; --meter-c:var(--teal)',
            band_start: false,
            band_end: false,
            tongue_corner_start: false,
            tongue_corner_end: false,
            source_label: 'The Stranger',
            decision: 'Endorsed Ada Lovelace',
          },
        ],
});

test('a share with no value renders the NA meter and no blocks', () => {
  const host = rendered(raceResultTemplate({ recommendation: 'No consensus', meter: meter(null) }));
  const box = host.querySelector('.screen-meter');

  assert.equal(box.getAttribute('class'), 'screen-meter screen-meter-na');
  assert.equal(box.hasAttribute('style'), false);
  assert.equal(box.querySelector('strong').textContent, 'N/A');
  assert.equal(box.querySelectorAll('.meter-block').length, 0);
});

test('a share with a value renders its blocks and the resting percent', () => {
  const host = rendered(raceResultTemplate({ recommendation: 'Ada', meter: meter(75) }));
  const box = host.querySelector('.screen-meter');

  assert.equal(box.getAttribute('style'), '--meter-fill: 75%');
  assert.equal(box.getAttribute('tabindex'), '0', 'the meter is its own one tab stop');
  const block = box.querySelector('.meter-block');
  assert.equal(block.getAttribute('class'), 'meter-block meter-block-solid');
  assert.equal(block.getAttribute('style'), '--meter-w:1; --meter-c:var(--teal)');
  assert.equal(block.getAttribute('data-meter-source'), 'The Stranger');
  assert.equal(block.getAttribute('data-meter-decision'), 'Endorsed Ada Lovelace');
  // The block carries no text of its own — the container's own text stays
  // exactly the resting percent, which is what the rendered-HTML validator
  // (rendering/validation.py) holds the "share" display role to.
  assert.equal(block.textContent, '');
  assert.equal(box.querySelector('strong').textContent, '75%');
});

// I41: below ~30% fill the label would bleed onto the trailing field, so the
// low-fill guard moves it after the leader's run instead.
test('a low fill and a degraded meter each carry their own class', () => {
  const low = rendered(
    raceResultTemplate({
      recommendation: 'Ada',
      meter: meter(12, { lowFill: true, noMajority: true }),
    }),
  );
  assert.equal(
    low.querySelector('.screen-meter').getAttribute('class'),
    'screen-meter meter-no-majority meter-low-fill',
  );
  assert.equal(low.querySelector('.screen-meter').getAttribute('style'), '--meter-fill: 12%');

  const high = rendered(raceResultTemplate({ recommendation: 'Ada', meter: meter(72) }));
  assert.equal(high.querySelector('.screen-meter').getAttribute('class'), 'screen-meter');

  const degraded = rendered(
    raceResultTemplate({ recommendation: 'Ada', meter: meter(72, { degraded: true }) }),
  );
  assert.equal(
    degraded.querySelector('.screen-meter').getAttribute('class'),
    'screen-meter meter-degraded',
  );
});

test('a split block renders its two halves and no others', () => {
  const view = meter(50);
  view.blocks = [
    {
      type: 'split',
      width: 1,
      style: '--meter-w:1; --meter-ca:var(--teal); --meter-cb:var(--amber)',
      band_start: true,
      band_end: true,
      tongue_corner_start: false,
      tongue_corner_end: false,
      source_label: 'The Urbanist',
      decision: 'Split: Ada Lovelace + Blaise Pascal — ½ each',
    },
  ];
  const host = rendered(raceResultTemplate({ recommendation: 'Ada / Blaise', meter: view }));
  const block = host.querySelector('.meter-block');
  assert.equal(block.getAttribute('class'), 'meter-block meter-block-split');
  assert.equal(block.querySelectorAll('.meter-half').length, 2);
  assert.equal(block.querySelector('.meter-half-top') !== null, true);
  assert.equal(block.querySelector('.meter-half-bottom') !== null, true);
});

test('the no-majority pill is present but hidden when there is a majority', () => {
  const host = rendered(
    raceContextTemplate({ noMajority: false, support: 'Based on 3', supportCompact: '3' }),
  );
  const pill = host.querySelector('.no-majority-pill');

  assert.equal(pill.hidden, true);
  assert.equal(pill.textContent, 'No majority');
  assert.equal(host.querySelector('.support-full').textContent, 'Based on 3');
  assert.equal(host.querySelector('.support-compact').textContent, '3');
});

test('an ordinary audited card foot renders nothing at all', () => {
  const host = rendered(raceFootTemplate({ insufficientNote: null, allSources: null }));
  assert.equal(host.querySelector('.insufficient-note'), null);
  assert.equal(host.querySelector('.lens-comparison'), null);
});

// G26/G27: the tint is never the only carrier of agreement.
test('the reference bar states its agreement in words as well as in tone', () => {
  const host = rendered(
    raceFootTemplate({
      insufficientNote: 'Too few endorsements to measure agreement.',
      allSources: { summary: 'All sources: Ada · 60%', leaderChanged: true },
    }),
  );
  const bar = host.querySelector('.lens-comparison');

  assert.equal(host.querySelector('.insufficient-note').getAttribute('role'), 'note');
  assert.equal(bar.getAttribute('class'), 'lens-comparison lens-comparison-differs');
  assert.equal(bar.getAttribute('role'), 'group');
  assert.equal(
    bar.getAttribute('aria-label'),
    'All sources differ from your selection. All sources: Ada · 60%',
  );
});

test('an agreeing reference bar takes the agree tone', () => {
  const host = rendered(
    raceFootTemplate({
      insufficientNote: null,
      allSources: { summary: 'All sources: Ada · 60%', leaderChanged: false },
    }),
  );
  const bar = host.querySelector('.lens-comparison');

  assert.equal(bar.getAttribute('class'), 'lens-comparison lens-comparison-agrees');
  assert.match(bar.getAttribute('aria-label'), /^All sources agree with your selection\./);
});

// #325's own per-candidate section meter: docs/METER_V2.md, Chrome geometry
// ("The headline meter's own fate") and Color ("Selected candidate: bold;
// everything else recedes" — applied statically here, per section).
test('a candidate section meter bolds its own solid block, recedes another candidate’s, and splits a shared block’s two halves', () => {
  const view = {
    na: false,
    accessibleLabel: 'Ada Lovelace: 1½ of 2 endorsements',
    countLabel: '1½',
    totalLabel: '2',
    percentageLabel: '75%',
    blocks: [
      {
        type: 'solid',
        width: 1,
        style: '--meter-w:1; --meter-c:var(--teal)',
        band_start: false,
        band_end: false,
        tongue_corner_start: false,
        tongue_corner_end: false,
        source_label: 'The Stranger',
        decision: 'Endorsed Ada Lovelace',
      },
      {
        type: 'split',
        width: 1,
        style: '--meter-w:1; --meter-ca:var(--teal); --meter-cb:var(--amber)',
        band_start: true,
        band_end: true,
        tongue_corner_start: false,
        tongue_corner_end: false,
        source_label: 'The Urbanist',
        decision: 'Split: Ada Lovelace + Blaise Pascal — ½ each',
      },
    ],
    contexts: [
      // The first block is this section's own candidate: bold, whole block.
      { block_class: ' meter-block-context', half_top_class: '', half_bottom_class: '' },
      // The second is a split this candidate's top half belongs to: the
      // block itself is not receded as one piece, but only the matching
      // half bolds — the per-half fix docs/METER_V2.md Decision #23
      // recorded for seam colors, extended here to a section's own
      // bold/recede paint.
      {
        block_class: ' meter-block-context',
        half_top_class: ' meter-half-context',
        half_bottom_class: ' meter-half-recede',
      },
    ],
  };
  const host = rendered(candidateMeterTemplate('ada', view));
  const box = host.querySelector('.screen-meter-section');

  assert.equal(box.getAttribute('class'), 'screen-meter screen-meter-section');
  assert.equal(box.getAttribute('role'), 'img');
  assert.equal(box.getAttribute('data-display-role'), 'candidate-share');
  assert.equal(box.getAttribute('data-meter-candidate-id'), 'ada');
  assert.equal(box.getAttribute('aria-label'), 'Ada Lovelace: 1½ of 2 endorsements');
  // No resting percentage inside the track any more (docs/METER_V2.md,
  // Resting label; #325) — the count and percent ride beside it instead.
  assert.equal(box.querySelector('strong'), null);

  const blocks = box.querySelectorAll('.meter-block');
  assert.equal(
    blocks[0].getAttribute('class'),
    'meter-block meter-block-solid meter-block-context',
  );
  const halves = blocks[1].querySelectorAll('.meter-half');
  assert.equal(halves[0].getAttribute('class'), 'meter-half meter-half-top meter-half-context');
  assert.equal(halves[1].getAttribute('class'), 'meter-half meter-half-bottom meter-half-recede');
});

test('a candidate with nothing to show under the active lens renders the empty N/A track', () => {
  const host = rendered(
    candidateMeterTemplate('blaise', {
      na: true,
      blocks: [],
      contexts: [],
      accessibleLabel: 'Blaise Pascal: No endorsements recorded',
      countLabel: '0',
      totalLabel: '2',
      percentageLabel: '0%',
    }),
  );
  const box = host.querySelector('.screen-meter-section');

  assert.equal(box.getAttribute('class'), 'screen-meter screen-meter-section screen-meter-na');
  assert.equal(box.querySelector('strong').textContent, 'N/A');
  assert.equal(box.querySelectorAll('.meter-block').length, 0);
});

test('candidateMeterViews builds one section meter per standing candidate, sharing the same block list', () => {
  const endorsements = [
    { source_label: 'The Stranger', candidate_ids: ['ada'], candidate_labels: ['Ada Lovelace'] },
    {
      source_label: 'The Urbanist',
      candidate_ids: ['ada', 'blaise'],
      candidate_labels: ['Ada Lovelace', 'Blaise Pascal'],
    },
  ];
  const { views, totalLabel } = candidateMeterViews(endorsements, new Set(['ada']), true);

  assert.equal(totalLabel, '2');
  assert.equal(views.size, 2);
  const ada = views.get('ada');
  const blaise = views.get('blaise');
  // Every candidate's own view reads the exact same block list — computed
  // once per race, never rederived per section (docs/METER_V2.md, Chrome
  // geometry; #325).
  assert.equal(ada.blocks, blaise.blocks);
  assert.equal(ada.countLabel, '1½');
  assert.equal(ada.percentageLabel, '75%');
  assert.equal(blaise.countLabel, '½');
  assert.equal(blaise.percentageLabel, '25%');
  // Ada's own solid block bolds; the split's top half (Ada) bolds and its
  // bottom half (Blaise) recedes, on Ada's own view.
  assert.equal(ada.contexts[0].block_class, ' meter-block-context');
  assert.equal(ada.contexts[1].half_top_class, ' meter-half-context');
  assert.equal(ada.contexts[1].half_bottom_class, ' meter-half-recede');
  // The same split's bottom half (Blaise) bolds on Blaise's own view instead,
  // and Ada's solo solid block recedes as a whole rather than half.
  assert.equal(blaise.contexts[0].block_class, '');
  assert.equal(blaise.contexts[1].half_top_class, ' meter-half-recede');
  assert.equal(blaise.contexts[1].half_bottom_class, ' meter-half-context');
});

test('the module keeps client state out of storage, and stays a computing module', () => {
  assertModuleGuard('guide-card.mjs');
});
