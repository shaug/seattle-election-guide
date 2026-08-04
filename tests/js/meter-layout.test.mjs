// The segmented meter's layout, held to the shape its two renderers depend on.
//
// `mirror-parity.test.mjs` already asserts every golden case against the server
// implementation, so nothing here restates an expectation. What this file adds
// is the part a deep-equality comparison cannot see — that the two languages
// agree on the record itself, byte for byte — and the mutations the goldens
// cannot perform on themselves: feeding the same cells in a different order,
// and showing that the heuristic the mockup uses for band edges answers a case
// in the fixture differently.

import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';
import { fileURLToPath } from 'node:url';
import { meterLayoutBlocks } from '../../src/election_guide/rendering/templates/meter-layout.mjs';
import { assertModuleGuard } from './support/module-guards.mjs';

const FIXTURE = JSON.parse(
  readFileSync(fileURLToPath(new URL('./fixtures/mirror-parity.json', import.meta.url)), 'utf8'),
);

/** Every golden case for this mirror, as the generator emitted them. */
const CASES = FIXTURE.cases.filter((item) => item.mirror === 'meter-layout-blocks');

/** One case by the source line that names it. */
function shaped(name) {
  const found = CASES.find((item) => item.source === `meter_layout_blocks on the ${name} shape`);
  assert.ok(found, `the fixture carries no ${name} shape; regenerate it with tests.mirror_parity`);
  return found;
}

test('meter-layout.mjs computes without touching the environment', () => {
  assertModuleGuard('meter-layout.mjs');
});

test('the fixture reaches this module at all', () => {
  assert.ok(CASES.length > 0, 'no meter-layout-blocks cases; the mirror would prove nothing');
});

// `mirror-parity.test.mjs` deep-equals every case already, and under
// `node:assert/strict` that is `deepStrictEqual` — a renamed field or a `width`
// that arrived as a string fails there, not here. What it cannot see is key
// *order*: two records carrying the same entries in a different order are
// deeply equal and serialize to different bytes. The ticket's acceptance is
// byte-identical goldens, so this compares the text.
test('every golden is byte-identical when the client produces it', () => {
  for (const item of CASES) {
    assert.equal(
      JSON.stringify(meterLayoutBlocks(item.input.endorsements), null, 2),
      JSON.stringify(item.expected, null, 2),
      `${item.source} serializes differently on the client. ${item.note}`,
    );
  }
});

// The whole reason this layout is one shared function: the server iterates
// `race.source_cells` in active-source order and the lens payload delivers
// cells keyed by sorted transport code, so the two callers hand the same race
// to this module in two different orders and must still reach one block list.
test('the block list does not depend on the order the cells arrive in', () => {
  for (const item of CASES) {
    const reversed = [...item.input.endorsements].reverse();
    assert.deepEqual(
      meterLayoutBlocks(reversed),
      item.expected,
      `${item.source} changed when its cells were reordered, so something in the layout is ` +
        'reading the input order rather than the canonical one.',
    );
  }
});

// docs/METER_V2.md, Splits: "Band-edge detection must be run-aware in the
// implementation; the mockup's neighbour-type heuristic is sufficient only for
// two-run bands." That is a claim about a case, so here is the case: two runs'
// splits sitting side by side, where asking "is my neighbour a split?" fuses
// two bands into one and loses two of the four edges.
test('band edges come from the run, not from the neighbouring block', () => {
  const blocks = meterLayoutBlocks(shaped('run-aware band edges').input.endorsements);
  const neighbourHeuristic = blocks.map((block, index) => ({
    band_start: block.type === 'split' && blocks[index - 1]?.type !== 'split',
    band_end: block.type === 'split' && blocks[index + 1]?.type !== 'split',
  }));

  assert.deepEqual(
    blocks.map(({ band_start, band_end }) => ({ band_start, band_end })),
    [
      { band_start: false, band_end: false },
      { band_start: false, band_end: false },
      { band_start: true, band_end: true },
      { band_start: true, band_end: true },
    ],
    'each run contributes its own band, so both splits open and close one',
  );
  assert.notDeepEqual(
    neighbourHeuristic,
    blocks.map(({ band_start, band_end }) => ({ band_start, band_end })),
    'the neighbour heuristic agreed here, so this case no longer distinguishes the two rules ' +
      'and the rule the mockup is documented as failing is going untested.',
  );
});

// The other half of the tongue rule: a band edge at the meter's own outer edge
// is not a tongue tip, because there is no colour beyond it for a curve to
// meet. The same shape carries it — its last block ends the meter.
test('a tongue reaching the meter its own edge stays square', () => {
  const blocks = meterLayoutBlocks(shaped('run-aware band edges').input.endorsements);
  const last = blocks[blocks.length - 1];
  assert.equal(last.band_end, true);
  assert.equal(last.tongue_corner_end, false);
  assert.equal(last.tongue_corner_start, true, 'its other edge is interior and does round');
});

test('an unscored race lays out no blocks at all', () => {
  assert.deepEqual(meterLayoutBlocks([]), []);
});
