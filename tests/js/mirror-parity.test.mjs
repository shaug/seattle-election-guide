// The client half of every cross-language mirror, held to the server's own
// output (docs/FRONTEND.md § Cross-language mirrors).
//
// `tests/mirrors.json` is the inventory of what is still implemented in both
// languages; `tests/mirror_parity.py` runs the server implementations over real
// publication bundles and boundary shares and commits the results as
// `fixtures/mirror-parity.json`. This file feeds each case's input to the
// client and asserts the server's answer came back.
//
// Nothing here writes an expected string. A case this file cannot dispatch
// fails, and a mirror the inventory promises cases for but the fixture has none
// of fails in `tests/test_mirrors.py`, so neither half can quietly stop
// covering the other.

import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';
import { fileURLToPath } from 'node:url';
import { rowDiffers } from '../../src/election_guide/rendering/templates/compare-signals.mjs';
import { comparisonPercentageLabel } from '../../src/election_guide/rendering/templates/compare-table.mjs';
import {
  compareContext,
  encodeCompareFragment,
} from '../../src/election_guide/rendering/templates/compare-url.mjs';
import {
  countingSummary,
  hasNoMajority,
  percentageLabel,
  raceDetailAccessibleSummary,
  raceDetailSupportSummary,
  recommendationLabel,
  shareAccessibleLabel,
  supportSummary,
  supportSummaryCompact,
} from '../../src/election_guide/rendering/templates/guide-format.mjs';
import { tallyingSourceCodes } from '../../src/election_guide/rendering/templates/lens-selection.mjs';

const FIXTURE = JSON.parse(
  readFileSync(fileURLToPath(new URL('./fixtures/mirror-parity.json', import.meta.url)), 'utf8'),
);

/**
 * The scoring result the display mirrors read, filled out from the fields a
 * case carries. The formatters touch only these, so the rest of `RaceScore` is
 * absent rather than invented.
 *
 * @param {Record<string, unknown>} fields
 */
const scored = (fields) => /** @type {any} */ ({ standings: [], ...fields });

/** @param {Record<string, string>} labels */
const labelMap = (labels) => new Map(Object.entries(labels));

/**
 * The payload the server embedded in one of the committed audited pages, read
 * the way the page's own entry reads it.
 *
 * @param {string} page
 */
function auditedPayload(page) {
  const html = readFileSync(fileURLToPath(new URL(`./fixtures/${page}`, import.meta.url)), 'utf8');
  const match = html.match(/<script[^>]*data-client-payload[^>]*>([\s\S]*?)<\/script>/);
  assert.ok(match, `${page} carries no client payload`);
  return JSON.parse(match[1]);
}

/**
 * One client call per inventory entry. The keys are `tests/mirrors.json`'s
 * mirror names, so an entry with no runner here cannot be marked
 * `parity-fixture` without this file failing on its first case.
 *
 * @type {Record<string, (input: any) => unknown>}
 */
const RUNNERS = {
  'share-percentage-label': ({ share }) => percentageLabel(share),
  // The same client function, asserted for the share the server has no
  // number for. Its own mirror because the server writes that branch as a
  // template literal rather than as the `percentage_label` field.
  'meter-unavailable-label': ({ share }) => percentageLabel(share),
  'no-majority': ({ share }) => hasNoMajority(share),
  'share-accessible-label': ({ share }) => shareAccessibleLabel(share),
  'support-summary': ({ scored: race }) => supportSummary(scored(race)),
  'support-summary-compact': ({ scored: race }) => supportSummaryCompact(scored(race)),
  'recommendation-label': ({ scored: race, labels }) =>
    recommendationLabel(scored(race), labelMap(labels)),
  'race-detail-support-summary': ({ scored: race, leaderCount }) =>
    raceDetailSupportSummary(scored(race), null, leaderCount),
  'race-detail-accessible-summary': ({ scored: race, labels, leaderCount }) =>
    raceDetailAccessibleSummary(scored(race), labelMap(labels), null, leaderCount),
  'counting-summary': ({ selectedCount, tallyingCount, personalized }) =>
    countingSummary(selectedCount, tallyingCount, personalized),
  'comparison-percentage-label': ({ share }) => comparisonPercentageLabel(share),
  'comparison-row-differs': ({ cells }) => rowDiffers(cells),
  'tallying-source-count': ({ page }) => tallyingSourceCodes(auditedPayload(page).sources).length,
  // The codec is asked for the fragment the way the page asks for it: a context
  // built from the payload the server embedded, so the binding the client
  // writes is the binding that page published. A rejected encode returns its
  // reason rather than a fragment, which fails the comparison loudly instead of
  // comparing undefined with a string.
  'compare-fragment-encoding': ({ page, columns }) => {
    const payload = auditedPayload(page);
    const context = compareContext(
      payload.personalization,
      payload.data_version,
      payload.comparisons,
      payload.default_columns,
    );
    const encoded = encodeCompareFragment({ columns }, context);
    return encoded.status === 'ok' ? encoded.fragment : `${encoded.status}: ${encoded.reason}`;
  },
};

test('the parity fixture is the one this build understands', () => {
  assert.equal(FIXTURE.schema_version, '1.0');
  assert.ok(FIXTURE.cases.length > 0, 'the fixture has no cases');
});

test('every mirror the fixture covers has a client runner', () => {
  const covered = [...new Set(FIXTURE.cases.map((item) => item.mirror))].sort();
  const missing = covered.filter((mirror) => !(mirror in RUNNERS));
  assert.deepEqual(
    missing,
    [],
    `mirror-parity.json covers ${missing.join(', ')}, which no runner in this file calls. ` +
      'A generated case nobody asserts is not a parity fixture (docs/FRONTEND.md ' +
      '§ Cross-language mirrors).',
  );
  const unused = Object.keys(RUNNERS).filter((mirror) => !covered.includes(mirror));
  assert.deepEqual(
    unused,
    [],
    `${unused.join(', ')} has a runner but no case. Regenerate the fixture with ` +
      '`uv run python -m tests.mirror_parity`.',
  );
});

for (const [index, item] of FIXTURE.cases.entries()) {
  test(`${item.mirror}: ${item.source}`, () => {
    const run = RUNNERS[item.mirror];
    assert.ok(run, `case ${index} names the unknown mirror ${item.mirror}`);
    assert.deepEqual(
      run(item.input),
      item.expected,
      `${item.mirror} disagrees with the server for ${JSON.stringify(item.input)}. ` +
        `${item.note} The expectation came from ${item.source}, so the client is what moved.`,
    );
  });
}
