import assert from 'node:assert/strict';
import test from 'node:test';

import { personalizedComparison } from '../../src/election_guide/rendering/templates/lens-comparison.mjs';

const labelById = new Map([
  ['cand-a', 'Candidate A'],
  ['cand-b', 'Candidate B'],
]);

function personalized(overrides) {
  return { grade: 'A', winnerId: 'cand-a', winnerIds: ['cand-a'], isTied: false, ...overrides };
}

test('agrees: the winning candidate matches the comparison pick', () => {
  const cell = { state: 'endorsement', allocation: { 'cand-a': '1' } };
  const result = personalizedComparison(cell, personalized(), labelById);

  assert.equal(result.tone, 'agrees');
  assert.equal(result.statusLabel, 'Times agrees');
  assert.equal(result.showChoice, false);
  assert.equal(result.ariaLabel, 'Seattle Times agrees with consensus: Candidate A');
});

test('differs: the winning candidate does not match the comparison pick', () => {
  const cell = { state: 'endorsement', allocation: { 'cand-b': '1' } };
  const result = personalizedComparison(cell, personalized(), labelById);

  assert.equal(result.tone, 'differs');
  assert.equal(result.statusLabel, 'Times differs');
  assert.equal(result.choiceLabel, 'Candidate B');
  assert.equal(result.showChoice, true);
  assert.equal(result.ariaLabel, 'Seattle Times endorses a different choice: Candidate B');
});

test('no_consensus: a tied personalized result forces no_consensus regardless of the pick', () => {
  const cell = { state: 'endorsement', allocation: { 'cand-a': '1' } };
  const result = personalizedComparison(
    cell,
    personalized({ grade: 'TIED', winnerId: null, winnerIds: ['cand-a', 'cand-b'], isTied: true }),
    labelById,
  );

  assert.equal(result.tone, 'neutral');
  // H32: the visible bar states the explanation itself — never only in an
  // aria-label — so the verb names the missing consensus.
  assert.equal(result.statusLabel, 'Times picks (no consensus)');
  assert.equal(result.choiceLabel, 'Candidate A');
  assert.equal(result.showChoice, true);
  assert.equal(
    result.ariaLabel,
    'Seattle Times endorses Candidate A; progressive sources have no consensus',
  );
});

test('no_consensus: an insufficient personalized result also forces no_consensus', () => {
  const cell = { state: 'endorsement', allocation: { 'cand-a': '1' } };
  const result = personalizedComparison(
    cell,
    personalized({ grade: 'Insufficient', winnerId: null, isTied: false }),
    labelById,
  );

  assert.equal(result.tone, 'neutral');
  assert.equal(result.statusLabel, 'Times picks (no consensus)');
});

test('no_endorsement: the comparison source explicitly made no pick', () => {
  const cell = { state: 'no_endorsement', allocation: {} };
  const result = personalizedComparison(cell, personalized(), labelById);

  assert.equal(result.tone, 'not_covered');
  assert.equal(result.statusLabel, 'Times');
  assert.equal(result.choiceLabel, 'not covered');
  assert.equal(result.ariaLabel, 'Seattle Times made no endorsement');
});

test('not_covered: the comparison source has no resolved cell at all', () => {
  const result = personalizedComparison(undefined, personalized(), labelById);

  assert.equal(result.tone, 'not_covered');
  assert.equal(result.statusLabel, 'Times');
  assert.equal(result.ariaLabel, 'Seattle Times: not covered');
});

for (const state of ['unavailable', 'unverified']) {
  test(`not_covered: an unresolved "${state}" cell collapses to not_covered`, () => {
    const cell = { state, allocation: {} };
    const result = personalizedComparison(cell, personalized(), labelById);

    assert.equal(result.tone, 'not_covered');
    assert.equal(result.choiceLabel, 'not covered');
  });
}

test('multi-candidate agreement joins every candidate label in order', () => {
  const cell = { state: 'multi_endorsement', allocation: { 'cand-a': '1/2', 'cand-b': '1/2' } };
  const result = personalizedComparison(
    cell,
    personalized({ winnerId: null, isTied: true, grade: 'TIED', winnerIds: ['cand-a', 'cand-b'] }),
    labelById,
  );

  assert.equal(result.choiceLabel, 'Candidate A / Candidate B');
});

test('the module has no DOM or network dependency', async () => {
  const { readFileSync } = await import('node:fs');
  const { fileURLToPath } = await import('node:url');
  const source = readFileSync(
    fileURLToPath(
      new URL(
        '../../src/election_guide/rendering/templates/lens-comparison.mjs',
        import.meta.url,
      ),
    ),
    'utf8',
  );
  const code = source.replace(/\/\*[\s\S]*?\*\//g, '').replace(/(^|\s)\/\/.*$/gm, '');

  for (const forbidden of ['window', 'document', 'location', 'fetch', 'navigator']) {
    assert.equal(
      new RegExp(`\\b${forbidden}\\b`).test(code),
      false,
      `${forbidden} would make this module environment-dependent`,
    );
  }
});
