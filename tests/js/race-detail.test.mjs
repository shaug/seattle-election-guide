// race-detail.mjs renders a race page's candidate sections from view-model
// state (docs/FRONTEND.md § Rendering).
//
// `race-markup-parity.test.mjs` holds this template to the Jinja one for every
// shape the published ballot actually contains. What is here is the rest: a
// row with no receipt and the not-counted marking a lens produces, plus the
// keyed-rendering claim, which needs a render that *changes* the list and so
// cannot be made against a fixture at all.
//
// v1's per-candidate mini-meter — the branches this file used to cover for an
// absent share, a low fill, and a no-majority tone — retired with meter v2
// (docs/METER_V2.md, Chrome geometry; #315 replaces its job on the shared
// headline bar), so `CandidateSectionView` carries no `meter` any more.

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
 * @param {Partial<import('../../src/election_guide/rendering/templates/race-detail.mjs').CandidateSectionView>} overrides
 */
function candidate(overrides = {}) {
  return {
    candidateId: 'ada',
    label: 'Ada Lovelace',
    isLeader: true,
    kicker: 'Leading choice',
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

test('a leading choice carries its kicker, and no meter of its own', () => {
  const host = draw([candidate()]);

  assert.equal(host.querySelector('.race-detail-candidate-title p').textContent, 'Leading choice');
  assert.equal(host.querySelector('.race-detail-meter'), null);
  assert.equal(host.querySelector('.race-detail-candidate-metrics'), null);
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
