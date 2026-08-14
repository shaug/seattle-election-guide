// race-detail.mjs renders a race page's candidate sections from view-model
// state (docs/FRONTEND.md § Rendering).
//
// `race-markup-parity.test.mjs` holds this template to the Jinja one for every
// shape the published ballot actually contains. What is here is the rest: a
// row with no receipt and the not-counted marking a lens produces, plus the
// keyed-rendering claim, which needs a render that *changes* the list and so
// cannot be made against a fixture at all.
//
// `CandidateSectionView` now carries its own `meter` — the race's own
// headline meter retired, and every candidate's own section gained one
// instead (docs/METER_V2.md, Chrome geometry: "The headline meter's own
// fate"; #325). `candidateMeterTemplate` (guide-card.mjs), which draws it, is
// its own module's test's claim (guide-card.test.mjs); what is pinned here is
// only that this template wires it into each section correctly.

import assert from 'node:assert/strict';
import test from 'node:test';
import { installDom } from './support/dom.mjs';
import { assertModuleGuard } from './support/module-guards.mjs';

const document = installDom('https://seattleelections.guide/e/wa-2026-primary/races/mayor/');
const { render } = await import('lit-html');
const { candidateSectionsTemplate } = await import(
  '../../src/election_guide/rendering/templates/race-detail.mjs'
);

/**
 * @param {Partial<import('../../src/election_guide/rendering/templates/race-detail.mjs').SourceRowView>} overrides
 */
function row(overrides = {}) {
  return {
    code: 'strn',
    name: 'The Stranger Election Control Board',
    category: 'progressive_general',
    categoryLabel: 'Progressive editorial and general',
    state: 'endorsement',
    panelRole: 'consensus',
    detailLabel: null,
    evidenceUrl: 'https://example.test/endorsements',
    notCounted: false,
    ...overrides,
  };
}

/**
 * @param {Partial<import('../../src/election_guide/rendering/templates/guide-card.mjs').CandidateMeterView>} overrides
 */
function meter(overrides = {}) {
  return {
    na: false,
    blocks: [],
    contexts: [],
    accessibleLabel: 'Ada Lovelace: 1 of 1 endorsements',
    countLabel: '1',
    totalLabel: '1',
    percentageLabel: '100%',
    ...overrides,
  };
}

/**
 * @param {Partial<import('../../src/election_guide/rendering/templates/race-detail.mjs').CandidateSectionView>} overrides
 */
function candidate(overrides = {}) {
  return {
    candidateId: 'ada',
    label: 'Ada Lovelace',
    isLeader: true,
    kicker: 'Leading choice',
    meter: meter(),
    rows: [row()],
    resultChipLabel: null,
    ...overrides,
  };
}

/** @param {readonly any[]} candidates */
function draw(candidates) {
  const host = document.createElement('div');
  render(candidateSectionsTemplate(candidates), host);
  return host;
}

test('a leading choice carries its kicker and its own section meter', () => {
  const host = draw([candidate()]);

  assert.equal(host.querySelector('.race-detail-candidate-title p').textContent, 'Leading choice');
  // v1's per-candidate mini-meter never comes back — meter v2's own section
  // meter (below) replaced its job (docs/METER_V2.md, Chrome geometry; #325).
  assert.equal(host.querySelector('.race-detail-meter'), null);
  assert.equal(host.querySelector('.race-detail-candidate-metrics'), null);
  const meterEl = host.querySelector('.race-detail-candidate-meter .screen-meter-section');
  assert.ok(meterEl, 'every candidate section carries its own meter now');
  assert.equal(meterEl.getAttribute('data-meter-candidate-id'), 'ada');
  assert.equal(meterEl.getAttribute('aria-label'), 'Ada Lovelace: 1 of 1 endorsements');
  assert.equal(host.querySelector('.race-detail-candidate-count b').textContent, '1');
  assert.equal(host.querySelector('.race-detail-candidate-pct').textContent, '100%');
});

test('a candidate who is not leading renders no kicker', () => {
  const host = draw([candidate({ isLeader: false, kicker: null })]);

  assert.equal(host.querySelector('.race-detail-candidate-title p'), null);
  assert.equal(
    host.querySelector('section').getAttribute('class'),
    'race-detail-candidate',
    'only the leading candidate takes the leader treatment',
  );
});

// The certified heading chip (docs/RESULTS.md, Rendering § The race-detail
// page; #287) — not reachable via the committed race-markup-parity fixture,
// since no results file is committed yet (#284's own scope), so this module's
// hand-built coverage is the only place a non-null `result` renders at all
// until then.
//
// The share and its bar are not a candidate section's to render any more:
// #370 moved them into the page's own complete RESULT block, above the lens
// bar and outside every lens region, which the server renders once and this
// module never sees. A section renders the chip and nothing else of a result.
test('an advancing candidate carries a chip after its name', () => {
  const host = draw([candidate({ isLeader: false, kicker: null, resultChipLabel: 'Advances' })]);

  const chip = host.querySelector('.race-detail-candidate-title h4 .race-detail-result-chip');
  assert.ok(chip, 'the chip renders immediately in the section heading, after the name');
  assert.equal(chip.textContent, 'Advances');
  assert.equal(
    host.querySelector('.race-detail-candidate-title h4').textContent.trim(),
    'Ada Lovelace Advances',
    'the chip follows the name, not the other way around',
  );

  // The heading is followed straight by the source list: nothing renders a
  // share between them (#370).
  const heading = host.querySelector('.race-detail-candidate-heading');
  assert.equal(heading.nextElementSibling, host.querySelector('.race-detail-source-list'));
  assert.equal(host.querySelector('.race-detail-candidate-result'), null);
  assert.equal(host.querySelector('.race-detail-result-bar'), null);
  assert.equal(host.querySelector('.race-detail-result-share'), null);
});

// One null, not three: a trailing outcome, a candidate a results file names
// no outcome for, and no results file at all all arrive here as
// `resultChipLabel: null` and all render nothing, so this section's view has
// no way to tell them apart and neither does this test (#370).
test('a candidate with no chip to render carries none', () => {
  const host = draw([candidate({ isLeader: false, kicker: null, resultChipLabel: null })]);

  assert.equal(host.querySelector('.race-detail-result-chip'), null);
  assert.equal(
    host.querySelector('.race-detail-candidate-title h4').textContent.trim(),
    'Ada Lovelace',
  );
  assert.equal(host.querySelector('.race-detail-candidate-result'), null);
});

test('the headlined candidate renders no section heading, and so no chip of its own', () => {
  // `inHeadline` renders no `.race-detail-candidate-title` at all — the page
  // headline is that candidate's own heading, and their chip renders there
  // (race.html.j2's `headline_chip_label`), not in this section.
  const host = draw([candidate({ inHeadline: true, kicker: null, resultChipLabel: 'Advances' })]);

  assert.equal(host.querySelector('.race-detail-candidate-title'), null);
  assert.equal(host.querySelector('.race-detail-result-chip'), null);
  assert.equal(host.querySelector('.race-detail-candidate-result'), null);
});

// A cell with no linkable receipt renders as a plain block, so nothing on the
// page looks like a link that goes nowhere.
test('a row with no receipt is not a link', () => {
  const host = draw([
    candidate({ rows: [row({ evidenceUrl: null, detailLabel: 'Co-endorsed' })] }),
  ]);
  const rendered = host.querySelector('.race-detail-source-row');

  assert.equal(rendered.tagName.toLowerCase(), 'div');
  assert.equal(host.querySelector('.race-detail-source-status').textContent, 'Co-endorsed');
});

test('an evidence row opens its receipt in a new tab', () => {
  const rendered = draw([candidate()]).querySelector('.race-detail-source-row');

  assert.equal(rendered.tagName.toLowerCase(), 'a');
  assert.equal(rendered.getAttribute('href'), 'https://example.test/endorsements');
  assert.equal(rendered.getAttribute('target'), '_blank');
  assert.equal(rendered.getAttribute('rel'), 'noopener');
});

// I56: an unselected source stays in place as evidence, marked as not counted,
// rather than removed — and the audited render carries no empty twin waiting
// for that mark (docs/FRONTEND.md § Rendering, one element per value).
test('an unselected source is marked in place, and the audited row carries no marker', () => {
  const audited = draw([candidate()]);
  assert.equal(audited.querySelector('.race-detail-source-not-counted'), null);
  assert.equal(audited.querySelector('li').getAttribute('class'), null);

  const lensed = draw([candidate({ rows: [row({ notCounted: true })] })]);
  assert.equal(
    lensed.querySelector('li').getAttribute('class'),
    'race-detail-source-row-not-counted',
  );
  assert.equal(lensed.querySelector('.race-detail-source-not-counted').textContent, 'Not counted');
});

test('every row publishes the attributes the rendered-HTML audit reparses', () => {
  const rendered = draw([candidate()]).querySelector('li');

  assert.equal(rendered.dataset.raceDetailSourceCode, 'strn');
  assert.equal(rendered.dataset.sourceCategory, 'progressive_general');
  assert.equal(rendered.dataset.sourceState, 'endorsement');
  assert.equal(rendered.dataset.sourceRole, 'consensus');
  assert.equal(rendered.dataset.sourceGroup, 'candidate');
  assert.equal(rendered.dataset.endorsedCandidateId, 'ada');
});

// The keyed-rendering rule: a render that *changes* the list must move the
// sections it keeps rather than rebuild them. Keyed and unkeyed rendering are
// indistinguishable while the list holds still, so this is the case that
// distinguishes them — replacing `repeat` with `.map` fails here and nowhere
// else (docs/FRONTEND.md § Rendering).
test('reordering the candidates keeps each section the same element', () => {
  const host = document.createElement('div');
  const ada = candidate();
  const blaise = candidate({
    candidateId: 'blaise',
    label: 'Blaise Pascal',
    isLeader: false,
    kicker: null,
    rows: [row({ code: 'mlkl', name: 'MLK Labor' })],
  });

  render(candidateSectionsTemplate([ada, blaise]), host);
  const first = host.querySelector('[data-race-detail-candidate-id="ada"]');
  const second = host.querySelector('[data-race-detail-candidate-id="blaise"]');

  render(candidateSectionsTemplate([blaise, ada]), host);

  assert.ok(host.querySelector('[data-race-detail-candidate-id="ada"]') === first);
  assert.ok(host.querySelector('[data-race-detail-candidate-id="blaise"]') === second);
  assert.deepEqual(
    [...host.querySelectorAll('[data-race-detail-candidate-id]')].map(
      (section) => section.dataset.raceDetailCandidateId,
    ),
    ['blaise', 'ada'],
  );
});

test('dropping a candidate keeps the surviving section the same element', () => {
  const host = document.createElement('div');
  const ada = candidate();
  const blaise = candidate({ candidateId: 'blaise', label: 'Blaise Pascal' });

  render(candidateSectionsTemplate([ada, blaise]), host);
  const survivor = host.querySelector('[data-race-detail-candidate-id="ada"]');

  render(candidateSectionsTemplate([ada]), host);

  assert.ok(host.querySelector('[data-race-detail-candidate-id="ada"]') === survivor);
  assert.equal(host.querySelectorAll('[data-race-detail-candidate-id]').length, 1);
});

test('the module computes and never touches the environment', () => {
  assertModuleGuard('race-detail.mjs');
});
