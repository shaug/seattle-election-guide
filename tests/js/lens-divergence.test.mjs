import assert from 'node:assert/strict';
import test from 'node:test';

import {
  DIVERGENCE_DIMENSIONS,
  compareRaceResults,
} from '../../src/election_guide/rendering/templates/lens-divergence.mjs';

/** A minimal scoreRace()-shaped result; only the fields compareRaceResults reads. */
function raceResult(overrides = {}) {
  return {
    raceId: 'race-1',
    grade: 'A',
    winnerId: 'alice',
    winnerIds: ['alice'],
    isTied: false,
    winnerShare: '3/4',
    explicitCount: 4,
    confidenceWarningCodes: [],
    ...overrides,
  };
}

test('an identical selection reports no divergence on any dimension', () => {
  const audited = raceResult();
  const personalized = raceResult();
  const result = compareRaceResults(audited, personalized);
  for (const dimension of DIVERGENCE_DIMENSIONS) {
    assert.equal(result[dimension], false, `${dimension} must not diverge`);
  }
  assert.equal(result.anyChanged, false);
});

test('a changed leader is detected regardless of winner-id array order', () => {
  const audited = raceResult({ winnerIds: ['alice'] });
  const personalized = raceResult({ winnerId: 'bob', winnerIds: ['bob'] });
  const result = compareRaceResults(audited, personalized);
  assert.equal(result.leader, true);
  assert.equal(result.anyChanged, true);
  assert.equal(result.percentage, false);
});

test('winner sets that contain the same ids in a different order do not diverge', () => {
  const audited = raceResult({ winnerId: null, winnerIds: ['alice', 'bob'], isTied: true });
  const personalized = raceResult({ winnerId: null, winnerIds: ['bob', 'alice'], isTied: true });
  const result = compareRaceResults(audited, personalized);
  assert.equal(result.leader, false);
  assert.equal(result.tie, false);
});

test('insufficient evidence on one side alone is a recommendationState divergence', () => {
  const audited = raceResult({ grade: 'B' });
  const personalized = raceResult({
    grade: 'Insufficient',
    winnerId: null,
    winnerIds: [],
    winnerShare: null,
  });
  const result = compareRaceResults(audited, personalized);
  assert.equal(result.recommendationState, true);
  assert.equal(result.leader, true);
  assert.equal(result.percentage, true);
});

test('a grade change that stays on the ordinary side of Insufficient is not a recommendationState divergence', () => {
  const audited = raceResult({ grade: 'A' });
  const personalized = raceResult({ grade: 'C' });
  const result = compareRaceResults(audited, personalized);
  assert.equal(result.recommendationState, false);
});

test('an exact share change is detected even when the leader stays the same', () => {
  const audited = raceResult({ winnerShare: '3/4' });
  const personalized = raceResult({ winnerShare: '2/3' });
  const result = compareRaceResults(audited, personalized);
  assert.equal(result.leader, false);
  assert.equal(result.percentage, true);
});

test('a null winner share on either side alone is a percentage divergence', () => {
  const audited = raceResult({ winnerShare: null });
  const personalized = raceResult({ winnerShare: '1/2' });
  const result = compareRaceResults(audited, personalized);
  assert.equal(result.percentage, true);
});

test('a source-count change is detected independent of the leader and share', () => {
  const audited = raceResult({ explicitCount: 5 });
  const personalized = raceResult({ explicitCount: 2 });
  const result = compareRaceResults(audited, personalized);
  assert.equal(result.sourceCount, true);
  assert.equal(result.leader, false);
  assert.equal(result.percentage, false);
});

test('a tie on only one side is a tie divergence even with the same winner set', () => {
  const audited = raceResult({ isTied: false, winnerId: 'alice', winnerIds: ['alice'] });
  const personalized = raceResult({ isTied: true, winnerId: null, winnerIds: ['alice', 'bob'] });
  const result = compareRaceResults(audited, personalized);
  assert.equal(result.tie, true);
  // The winner set genuinely changed too (bob joined), so this case also
  // exercises leader changing alongside tie in the same comparison.
  assert.equal(result.leader, true);
});

test('a warning-code set change is detected regardless of order', () => {
  const audited = raceResult({ confidenceWarningCodes: ['aaaa', 'bbbb'] });
  const personalized = raceResult({ confidenceWarningCodes: ['bbbb', 'aaaa'] });
  assert.equal(compareRaceResults(audited, personalized).warning, false);

  const changed = raceResult({ confidenceWarningCodes: ['cccc'] });
  assert.equal(compareRaceResults(audited, changed).warning, true);
});

test('every defined divergence dimension is exercised by at least one case above', () => {
  // A guard against silently dropping a dimension from DIVERGENCE_DIMENSIONS
  // without updating this file: every named dimension must be independently
  // toggleable to true by some pair of inputs.
  const base = raceResult();
  const toggles = {
    leader: raceResult({ winnerId: 'zed', winnerIds: ['zed'] }),
    recommendationState: raceResult({ grade: 'Insufficient', winnerId: null, winnerIds: [] }),
    percentage: raceResult({ winnerShare: '1/9' }),
    sourceCount: raceResult({ explicitCount: 99 }),
    tie: raceResult({ isTied: true, winnerIds: ['alice', 'zed'], winnerId: null }),
    warning: raceResult({ confidenceWarningCodes: ['zzzz'] }),
  };
  for (const dimension of DIVERGENCE_DIMENSIONS) {
    assert.equal(
      compareRaceResults(base, toggles[dimension])[dimension],
      true,
      `${dimension} was not exercised`,
    );
  }
});
