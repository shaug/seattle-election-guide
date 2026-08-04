// guide-format.mjs mirrors the display strings `rendering/context.py` writes
// for the audited default. While a lens is active the client recomputes them,
// so a drift between the two sides shows a reader one quantity with two
// spellings. These are the client half of that mirror
// (docs/FRONTEND.md § Cross-language mirrors); `tests/test_rendering.py` holds
// the rendered page to the Python half.

import assert from 'node:assert/strict';
import test from 'node:test';
import {
  allSourcesSummary,
  countingSummary,
  endorsementCountLabel,
  filterStatusParts,
  hasNoMajority,
  percentageLabel,
  raceDetailAccessibleSummary,
  raceDetailSupportSummary,
  recommendationLabel,
  shareAccessibleLabel,
  supportSummary,
  supportSummaryCompact,
} from '../../src/election_guide/rendering/templates/guide-format.mjs';
import { assertModuleGuard } from './support/module-guards.mjs';

/**
 * @param {Partial<import('../../src/election_guide/rendering/templates/lens-score.mjs').RaceScore>} fields
 */
const scored = (fields) => ({
  raceId: 'r',
  grade: 'Strong',
  winnerId: 'a',
  winnerIds: ['a'],
  isTied: false,
  winnerShare: '3/4',
  explicitCount: 4,
  eligibleCount: 4,
  coveredCount: 4,
  missingCodes: [],
  noEndorsementCodes: [],
  confidenceWarningCodes: [],
  standings: [],
  ...fields,
});

const LABELS = new Map([
  ['a', 'Ada Lovelace'],
  ['b', 'Blaise Pascal'],
]);

test('a share prints as a whole percentage, rounded half up on exact arithmetic', () => {
  assert.equal(percentageLabel('3/4'), '75%');
  assert.equal(percentageLabel('1/3'), '33%');
  assert.equal(percentageLabel('2/3'), '67%');
  // The exact half is the case a float round would get wrong.
  assert.equal(percentageLabel('1/8'), '13%');
  assert.equal(percentageLabel('1/1'), '100%');
  assert.equal(percentageLabel(null), 'N/A');
});

test('the caption tally is an exact mixed number spelled with vulgar-fraction glyphs', () => {
  assert.equal(endorsementCountLabel('23'), '23');
  assert.equal(endorsementCountLabel('0'), '0');
  assert.equal(endorsementCountLabel('43/2'), '21½');
  assert.equal(endorsementCountLabel('1/3'), '⅓');
  assert.equal(endorsementCountLabel('2/3'), '⅔');
  assert.equal(endorsementCountLabel('7/4'), '1¾');
  assert.equal(endorsementCountLabel('1/7'), '⅐');
  // An unreduced tally reduces before the glyph lookup.
  assert.equal(endorsementCountLabel('4/8'), '½');
  // Twelfths have no single glyph: the fallback is numerator⁄denominator
  // (U+2044) joined to a nonzero whole part by a no-break space.
  assert.equal(endorsementCountLabel('25/12'), '2\u00a01⁄12');
});

test('no majority means at or below half, not merely below the leader', () => {
  assert.equal(hasNoMajority('1/2'), true);
  assert.equal(hasNoMajority('2/5'), true);
  assert.equal(hasNoMajority('3/5'), false);
  assert.equal(hasNoMajority(null), false);
});

test('the meter says the agreement in words, not only in tint', () => {
  assert.equal(
    shareAccessibleLabel('2/5'),
    'No majority. Consensus among explicitly endorsing sources: 40%',
  );
  assert.equal(shareAccessibleLabel('4/5'), 'Consensus among explicitly endorsing sources: 80%');
});

test('the headline names the leader, the tie, or the absence of evidence', () => {
  assert.equal(recommendationLabel(scored({}), LABELS), 'Ada Lovelace');
  assert.equal(
    recommendationLabel(scored({ isTied: true, winnerIds: ['a', 'b'] }), LABELS),
    'Ada Lovelace / Blaise Pascal',
  );
  assert.equal(
    recommendationLabel(scored({ grade: 'Insufficient' }), LABELS),
    'Too few endorsements',
  );
  assert.equal(recommendationLabel(scored({ winnerId: null }), LABELS), 'No consensus');
  // An id the payload has no label for still names something, never `undefined`.
  assert.equal(recommendationLabel(scored({ winnerId: 'z' }), LABELS), 'No consensus');
});

test('the caption counts selected sources only while a lens is active (H38)', () => {
  assert.equal(supportSummary(scored({ explicitCount: 4 })), 'Based on 4 endorsing sources');
  assert.equal(supportSummary(scored({ explicitCount: 1 })), 'Based on 1 endorsing source');
  assert.equal(supportSummary(scored({ explicitCount: 3 }), 9), 'Based on 3 of 9 selected sources');
  // Never the possessive "My sources".
  assert.ok(!supportSummary(scored({}), 9).includes('My sources'));
});

test('the compact caption is the short form of the same sentence (H34)', () => {
  assert.equal(supportSummaryCompact(scored({ explicitCount: 4 })), '4 sources');
  assert.equal(supportSummaryCompact(scored({ explicitCount: 3 }), 9), '3 of 9 selected');
});

test('the reference bar states the full panel result', () => {
  assert.equal(
    allSourcesSummary(scored({ winnerShare: '1/2' }), LABELS),
    'All sources: Ada Lovelace · 50%',
  );
});

test('the dialog summary reports the leader against the endorsing total', () => {
  assert.equal(
    raceDetailSupportSummary(scored({ explicitCount: 4 }), 9, 3),
    '3 of 4 endorsing sources agree',
  );
  assert.equal(
    raceDetailSupportSummary(scored({ explicitCount: 1 }), 9, 1),
    '1 of 1 endorsing source agrees',
  );
  // A tie or an insufficient grade has no single leader's count to report, so
  // it falls back to the caption's own sentence.
  assert.equal(
    raceDetailSupportSummary(scored({ isTied: true, explicitCount: 4 }), 9, 0),
    'Based on 4 of 9 selected sources',
  );
  assert.equal(
    raceDetailSupportSummary(scored({ grade: 'Insufficient', explicitCount: 1 }), 9, 0),
    'Based on 1 of 9 selected sources',
  );
});

test('the accessible summary carries the result, the qualifier, and the count', () => {
  assert.equal(
    raceDetailAccessibleSummary(scored({ winnerShare: '2/5', explicitCount: 5 }), LABELS, 9, 2),
    'Ada Lovelace. No majority. 40%. 2 of 5 endorsing sources agree.',
  );
  assert.equal(
    raceDetailAccessibleSummary(scored({ winnerShare: null, explicitCount: 5 }), LABELS, 9, 2),
    'Ada Lovelace. Consensus unavailable. 2 of 5 endorsing sources agree.',
  );
});

test('the banner says how many sources count, and whether that is all of them', () => {
  assert.equal(countingSummary(9, 9, false), 'Counting all 9 sources.');
  assert.equal(countingSummary(4, 9, true), 'Counting 4 of 9 sources.');
});

test('the filter status announces the count, the view, and the scope', () => {
  assert.deepEqual(
    filterStatusParts({ visible: 12, contestedOnly: false, compact: false, scopeLabel: 'All' }),
    ['12 races shown', 'Full', 'All'],
  );
  assert.deepEqual(
    filterStatusParts({ visible: 1, contestedOnly: true, compact: true, scopeLabel: 'City' }),
    ['1 contested race shown', 'Compact', 'City'],
  );
  assert.deepEqual(
    filterStatusParts({ visible: 3, contestedOnly: true, compact: false, scopeLabel: 'City' })[0],
    '3 contested races shown',
  );
});

test('the module computes and touches nothing', () => {
  assertModuleGuard('guide-format.mjs');
});
