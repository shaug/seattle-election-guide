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
import {
  meterAccessibleLabel,
  meterBlockDecision,
  meterBlockRenders,
  meterCandidateColors,
  meterEndorsementsFromCells,
  meterLayoutBlocks,
  meterStandings,
} from '../../src/election_guide/rendering/templates/meter-layout.mjs';
import { assertModuleGuard } from './support/module-guards.mjs';

const FIXTURE = JSON.parse(
  readFileSync(fileURLToPath(new URL('./fixtures/mirror-parity.json', import.meta.url)), 'utf8'),
);

/** Every golden case for this mirror, as the generator emitted them. */
const CASES = FIXTURE.cases.filter((item) => item.mirror === 'meter-layout-blocks');
const COLOR_CASES = FIXTURE.cases.filter((item) => item.mirror === 'meter-candidate-colors');
const RENDER_CASES = FIXTURE.cases.filter((item) => item.mirror === 'meter-block-renders');

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

// docs/METER_V2.md, Color: a pool that runs out steps toward the track rather
// than repeating a swatch, so two candidates in one meter never share a color.
// `mirror-parity.test.mjs` proves the byte-identical string for every fixture
// case already; what this adds is the property the stepping exists for.
test('color-pool exhaustion never repeats a swatch', () => {
  for (const item of COLOR_CASES) {
    const colors = meterCandidateColors(
      item.input.standings,
      new Set(item.input.leaderIds),
      item.input.hasMajority,
    );
    assert.equal(
      new Set(colors.values()).size,
      colors.size,
      `${item.source}: two candidates share one color`,
    );
  }
});

test('a solid block reads Endorsed; a split states the share by name', () => {
  const labels = new Map([
    ['jamie', 'Jamie Pedersen'],
    ['hawk', 'Jaime Michelle Hawk'],
    ['diaz', 'Mike Diaz'],
    ['third', 'A Third Candidate'],
  ]);
  assert.equal(
    meterBlockDecision({ type: 'solid', candidate_ids: ['jamie'] }, labels),
    'Endorsed Jamie Pedersen',
  );
  assert.equal(
    meterBlockDecision({ type: 'split', candidate_ids: ['hawk', 'diaz'] }, labels),
    'Split: Jaime Michelle Hawk + Mike Diaz — ½ each',
  );
  // Decision log #21: an n-way split beyond two states the literal ratio, not
  // a vulgar-fraction glyph — the tooltip names the split, it does not restate
  // the caption's exact arithmetic.
  assert.equal(
    meterBlockDecision({ type: 'split', candidate_ids: ['hawk', 'diaz', 'third'] }, labels),
    'Split: Jaime Michelle Hawk + Mike Diaz + A Third Candidate — 1/3 each',
  );
});

test('the N/A state has no standings and its own accessible name', () => {
  assert.equal(meterAccessibleLabel([], new Map(), new Map()), 'No endorsements recorded');
});

test('every block render is byte-identical to its golden, style string included', () => {
  for (const item of RENDER_CASES) {
    const colors = new Map(Object.entries(item.input.colors));
    const labels = new Map(Object.entries(item.input.labels));
    assert.equal(
      JSON.stringify(meterBlockRenders(item.input.blocks, colors, labels), null, 2),
      JSON.stringify(item.expected, null, 2),
      `${item.source} serializes differently on the client. ${item.note}`,
    );
  }
});

// `meterEndorsementsFromCells` is the client's own side of the admission rule
// (`meter_endorsements` in `rendering/context.py`, docs/METER_V2.md § Counting
// and the denominator): it has no server counterpart of the same shape — the
// server resolves a `SourceCell`, the client resolves a scored `MeterCell` —
// so this is exercised directly rather than through the fixture.
test('a scored cell resolves to a MeterEndorsement by its code and candidate ids', () => {
  const sourceNameByCode = new Map([['strn', 'The Stranger']]);
  const candidateLabelById = new Map([['jenks', 'Nilu Jenks']]);
  const endorsements = meterEndorsementsFromCells(
    [{ source_code: 'strn', candidate_ids: ['jenks'] }],
    sourceNameByCode,
    candidateLabelById,
  );
  assert.deepEqual(endorsements, [
    { source_label: 'The Stranger', candidate_ids: ['jenks'], candidate_labels: ['Nilu Jenks'] },
  ]);
});

test('a no-endorsement cell carries no candidates and so no block or weight', () => {
  const endorsements = meterEndorsementsFromCells(
    [{ source_code: 'strn', candidate_ids: [] }],
    new Map([['strn', 'The Stranger']]),
    new Map(),
  );
  assert.deepEqual(meterStandings(endorsements), []);
  assert.deepEqual(meterLayoutBlocks(endorsements), []);
});
