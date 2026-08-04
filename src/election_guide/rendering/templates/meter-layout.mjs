// The segmented meter's layout, mirroring `meter_layout_blocks` in
// `rendering/context.py`.
//
// Meter v2 is one block per endorsement, grouped into runs by candidate in
// standings order, with each split placed at the boundary between its
// candidates' runs (docs/METER_V2.md, Splits: placement and the tongue rule).
// The two renderers read cells in different orders — the server iterates
// `race.source_cells` in active-source order, the lens payload delivers sorted
// transport codes — so the ordering rules below are the whole of what makes the
// two produce identical markup, and `tests/mirrors.json` carries the golden
// cases that hold them together.
//
// Pure by construction: records in, records out, no DOM. The block records use
// the server's own field names rather than a camelCase restatement, so a
// surface reads one spelling wherever a block reaches it (docs/FRONTEND.md, The
// data contract: one identifier space).

import { Rational } from './lens-score.mjs';

/**
 * One tallying source cell, as the meter counts it. The fields are the
 * published `SourceCell`'s; a cell naming nobody carries no block and no
 * denominator weight.
 *
 * @typedef {object} MeterEndorsement
 * @property {string} source_label
 * @property {string[]} candidate_ids
 * @property {string[]} candidate_labels
 */

/**
 * One rectangle of the meter. `type` is `solid` or `split`; `width` is in
 * units, one endorsement to a unit; `candidate_ids` is in standings order, top
 * to bottom for a split. The band flags mark a band's first and last split, and
 * the tongue flags mark where that edge actually rounds — a band edge at the
 * meter's own outer edge stays square.
 *
 * @typedef {object} MeterBlock
 * @property {string} type
 * @property {number} width
 * @property {string[]} candidate_ids
 * @property {string} source_label
 * @property {boolean} band_start
 * @property {boolean} band_end
 * @property {boolean} tongue_corner_start
 * @property {boolean} tongue_corner_end
 */

/**
 * Character-by-character ordering, matching the Python side's `<`.
 *
 * The two are the same order for every label this data carries and every one
 * it plausibly could: JavaScript compares UTF-16 code units and Python compares
 * code points, which agree across the whole Basic Multilingual Plane and invert
 * only for a supplementary-plane character weighed against U+E000–U+FFFF. That
 * limit is written down rather than left implied, because the next sort to
 * reach for this helper may not be sorting people's names.
 *
 * @param {string} left
 * @param {string} right
 * @returns {number}
 */
function compareText(left, right) {
  if (left === right) return 0;
  return left < right ? -1 : 1;
}

/**
 * Two splits' candidate lists by standings rank, element-wise then by length —
 * Python's tuple comparison, which is what the server sorts them with.
 *
 * @param {string[]} left
 * @param {string[]} right
 * @param {Record<string, number>} rank
 * @returns {number}
 */
function compareMembership(left, right, rank) {
  const shared = Math.min(left.length, right.length);
  for (let index = 0; index < shared; index += 1) {
    const difference = rank[left[index]] - rank[right[index]];
    if (difference !== 0) return difference;
  }
  return left.length - right.length;
}

/**
 * The endorsed candidates, leader first, as the meter orders their runs.
 *
 * Units, not source counts: a split allocates 1/n to each candidate it names,
 * so the tally is exact rational arithmetic and never a float. Equal units are
 * broken by display label and then by id, using the plain comparison above
 * rather than a locale collation — the tie-break exists so two implementations
 * reach one run order, so it has to be an order both of them spell the same
 * way.
 *
 * @param {MeterEndorsement[]} endorsements
 * @returns {string[]}
 */
function meterStandings(endorsements) {
  /** @type {Map<string, {units: Rational, label: string}>} */
  const tally = new Map();
  for (const endorsement of endorsements) {
    if (endorsement.candidate_ids.length === 0) continue;
    const share = new Rational(1n, BigInt(endorsement.candidate_ids.length));
    endorsement.candidate_ids.forEach((candidateId, position) => {
      const running = tally.get(candidateId);
      tally.set(candidateId, {
        units: running ? running.units.add(share) : share,
        label: endorsement.candidate_labels[position],
      });
    });
  }
  return [...tally.entries()]
    .sort(
      ([leftId, left], [rightId, right]) =>
        right.units.compare(left.units) ||
        compareText(left.label, right.label) ||
        compareText(leftId, rightId),
    )
    .map(([candidateId]) => candidateId);
}

/**
 * The segmented meter's blocks, left to right, from the cells it counts.
 *
 * Mirrors `meter_layout_blocks` in `rendering/context.py`.
 *
 * Within a run, solid blocks sort by their source's display label and the
 * splits follow, farthest partner first so the nearest partner's split touches
 * the next run. A split between non-adjacent candidates therefore lands at the
 * end of the higher-ranked candidate's run. Splits sharing a partner fall back
 * to the source label, for the same reason the solids sort by it: it is the one
 * key both sides hold. Two sources can share a display label, so the split's
 * own membership finishes the order — every key here is total, because a key
 * that ties hands the decision back to the order the cells arrived in, which is
 * the one thing this function may not do.
 *
 * Band edges are read off the run, not off the neighbouring block. Two runs'
 * splits can sit side by side — a candidate whose whole support is split halves
 * has no solids of their own — and the mockup's neighbour-type heuristic reads
 * that pair as one band, which is why it is documented as sufficient only for
 * two-run bands.
 *
 * An empty tally returns an empty list: the N/A state renders the bare track
 * and has no blocks to decide about.
 *
 * @param {MeterEndorsement[]} endorsements
 * @returns {MeterBlock[]}
 */
export function meterLayoutBlocks(endorsements) {
  const standings = meterStandings(endorsements);
  /** @type {Record<string, number>} */
  const rank = {};
  standings.forEach((candidateId, index) => {
    rank[candidateId] = index;
  });
  const counted = endorsements.filter((endorsement) => endorsement.candidate_ids.length > 0);

  /** @type {Record<string, MeterEndorsement[]>} */
  const solids = {};
  /** @type {Record<string, {ordered: string[], endorsement: MeterEndorsement}[]>} */
  const splits = {};
  for (const candidateId of standings) {
    solids[candidateId] = [];
    splits[candidateId] = [];
  }
  for (const endorsement of counted) {
    const ordered = [...endorsement.candidate_ids].sort((left, right) => rank[left] - rank[right]);
    if (ordered.length === 1) solids[ordered[0]].push(endorsement);
    else splits[ordered[0]].push({ ordered, endorsement });
  }

  /** @type {MeterBlock[]} */
  const blocks = [];
  for (const candidateId of standings) {
    const runSolids = [...solids[candidateId]].sort((left, right) =>
      compareText(left.source_label, right.source_label),
    );
    for (const endorsement of runSolids) {
      blocks.push({
        type: 'solid',
        width: 1,
        candidate_ids: [candidateId],
        source_label: endorsement.source_label,
        band_start: false,
        band_end: false,
        tongue_corner_start: false,
        tongue_corner_end: false,
      });
    }
    const band = [...splits[candidateId]].sort(
      (left, right) =>
        rank[right.ordered[1]] - rank[left.ordered[1]] ||
        compareText(left.endorsement.source_label, right.endorsement.source_label) ||
        compareMembership(left.ordered, right.ordered, rank),
    );
    band.forEach(({ ordered, endorsement }, position) => {
      const starts = position === 0;
      const ends = position === band.length - 1;
      const index = blocks.length;
      blocks.push({
        type: 'split',
        width: 1,
        candidate_ids: ordered,
        source_label: endorsement.source_label,
        band_start: starts,
        band_end: ends,
        tongue_corner_start: starts && index > 0,
        tongue_corner_end: ends && index < counted.length - 1,
      });
    });
  }
  return blocks;
}
