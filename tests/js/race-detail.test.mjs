// race-detail.mjs renders a race page's candidate sections from view-model
// state (docs/FRONTEND.md § Rendering).
//
// `race-markup-parity.test.mjs` holds this template to the Jinja one for every
// shape the published ballot actually contains. What is here is the rest: the
// four branches no race on that ballot reaches — an absent share, a low fill, a
// row with no receipt, and the not-counted marking a lens produces — plus the
// keyed-rendering claim, which needs a render that *changes* the list and so
// cannot be made against a fixture at all.

import assert from 'node:assert/strict';
import test from 'node:test';
import { installDom } from './support/dom.mjs';
import { assertModuleGuard } from './support/module-guards.mjs';

const document = installDom('https://seattleelections.guide/e/wa-2026-primary/races/mayor/');
const { render } = await import('lit-html');
const { candidateSectionsTemplate } = await import(
  '../../src/election_guide/rendering/templates/race-detail.mjs'
);
const { meterView } = await import('../../src/election_guide/rendering/templates/guide-card.mjs');

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
 * @param {Partial<import('../../src/election_guide/rendering/templates/race-detail.mjs').CandidateSectionView>} overrides
 */
function candidate(overrides = {}) {
  return {
    candidateId: 'ada',
    label: 'Ada Lovelace',
    isLeader: true,
    kicker: 'Leading choice',
    count: '1 of 1 endorsing sources',
    meter: meterView('3/4'),
    rows: [row()],
    ...overrides,
  };
}

/** @param {readonly any[]} candidates */
function draw(candidates) {
  const host = document.createElement('div');
  render(candidateSectionsTemplate(candidates), host);
  return host;
}

test('a leader draws the meter, its tone, and its spoken label together', () => {
  const host = draw([candidate()]);
  const meter = host.querySelector('.race-detail-meter');

  assert.ok(meter);
  assert.equal(meter.getAttribute('style'), '--meter-fill: 75%');
  assert.equal(meter.querySelector('strong').textContent, '75%');
  assert.equal(
    meter.getAttribute('aria-label'),
    'Consensus among explicitly endorsing sources: 75%',
  );
  assert.equal(host.querySelector('.race-detail-candidate-title p').textContent, 'Leading choice');
});

// The audited template writes no `style` attribute at all when there is no
// share, so neither may this one.
test('an absent share draws the N/A chrome and no fill', () => {
  const host = draw([candidate({ meter: meterView(null) })]);
  const meter = host.querySelector('.race-detail-meter');

  assert.equal(meter.getAttribute('class'), 'race-detail-meter race-detail-meter-na');
  assert.equal(meter.hasAttribute('style'), false);
  assert.equal(meter.querySelector('strong').textContent, 'N/A');
  // The visible abbreviation is not what a screen reader should hear.
  assert.equal(
    meter.getAttribute('aria-label'),
    'Consensus among explicitly endorsing sources: not available',
  );
});

// I41: below ~30% fill the label rides past the fill onto the pale track, so
// the guard renders it after the fill in muted ink instead.
test('a low fill and a no-majority share each carry their own class', () => {
  assert.equal(
    draw([candidate({ meter: meterView('1/5') })])
      .querySelector('.race-detail-meter')
      .getAttribute('class'),
    'race-detail-meter meter-no-majority meter-low-fill',
  );
  assert.equal(
    draw([candidate({ meter: meterView('1/2') })])
      .querySelector('.race-detail-meter')
      .getAttribute('class'),
    'race-detail-meter meter-no-majority',
  );
});

test('a candidate who is not leading renders neither kicker nor meter', () => {
  const host = draw([candidate({ isLeader: false, kicker: null, meter: null })]);

  assert.equal(host.querySelector('.race-detail-candidate-title p'), null);
  assert.equal(host.querySelector('.race-detail-meter'), null);
  assert.equal(
    host.querySelector('section').getAttribute('class'),
    'race-detail-candidate',
    'only the leading candidate takes the leader treatment',
  );
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
    meter: null,
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
