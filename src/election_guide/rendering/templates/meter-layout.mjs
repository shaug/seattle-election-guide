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

import { endorsementCountLabel } from './guide-format.mjs';
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
 * Each candidate's exact endorsement tally: 1/n to each candidate a split
 * names (docs/METER_V2.md, Counting and the denominator). Units, not source
 * counts, and never a float.
 *
 * Mirrors `meter_units` in `rendering/context.py`. Public because the meter's
 * caption and its accessible name both need one candidate's exact tally
 * without walking the block list back apart.
 *
 * @param {MeterEndorsement[]} endorsements
 * @returns {Map<string, Rational>}
 */
export function meterUnits(endorsements) {
  /** @type {Map<string, Rational>} */
  const units = new Map();
  for (const endorsement of endorsements) {
    if (endorsement.candidate_ids.length === 0) continue;
    const share = new Rational(1n, BigInt(endorsement.candidate_ids.length));
    for (const candidateId of endorsement.candidate_ids) {
      const running = units.get(candidateId);
      units.set(candidateId, running ? running.add(share) : share);
    }
  }
  return units;
}

/**
 * Each candidate's display label, as the cells that name them spell it.
 *
 * Mirrors `meter_candidate_labels` in `rendering/context.py`.
 *
 * @param {MeterEndorsement[]} endorsements
 * @returns {Map<string, string>}
 */
export function meterCandidateLabels(endorsements) {
  /** @type {Map<string, string>} */
  const labels = new Map();
  for (const endorsement of endorsements) {
    endorsement.candidate_ids.forEach((candidateId, position) => {
      labels.set(candidateId, endorsement.candidate_labels[position]);
    });
  }
  return labels;
}

/**
 * The endorsed candidates, leader first, as the meter orders their runs.
 *
 * Units, not source counts (see `meterUnits`): a split allocates 1/n to each
 * candidate it names, so the tally is exact rational arithmetic and never a
 * float. Equal units are broken by display label and then by id, using the
 * plain comparison above rather than a locale collation — the tie-break
 * exists so two implementations reach one run order, so it has to be an order
 * both of them spell the same way.
 *
 * Mirrors `meter_standings` in `rendering/context.py`. Public — beyond block
 * layout, this is also the meter's color assignment's and accessible name's
 * own rank order, so every consumer reads one order rather than three.
 *
 * @param {MeterEndorsement[]} endorsements
 * @returns {string[]}
 */
export function meterStandings(endorsements) {
  const units = meterUnits(endorsements);
  const labels = meterCandidateLabels(endorsements);
  return [...units.keys()].sort(
    (leftId, rightId) =>
      /** @type {Rational} */ (units.get(rightId)).compare(
        /** @type {Rational} */ (units.get(leftId)),
      ) ||
      compareText(
        /** @type {string} */ (labels.get(leftId)),
        /** @type {string} */ (labels.get(rightId)),
      ) ||
      compareText(leftId, rightId),
  );
}

/**
 * One race's cells, as the segmented meter counts them — the client's side of
 * the admission rule `meter_endorsements` in `rendering/context.py` names
 * (`RaceScore.meterCells`, built from `METER_COUNTED_STATES` in
 * `lens-score.mjs`). `sourceNameByCode` and `candidateLabelById` resolve the
 * identifiers a cell carries (`source_code`, `candidate_ids`) to the display
 * strings a block and its tooltip need — a cell does not carry them itself,
 * the same reason `meter_endorsements` looks a source's name up rather than
 * finding it on the cell (docs/FRONTEND.md, The data contract).
 *
 * @param {import('./lens-score.mjs').MeterCell[]} cells
 * @param {ReadonlyMap<string, string>} sourceNameByCode
 * @param {ReadonlyMap<string, string>} candidateLabelById
 * @returns {MeterEndorsement[]}
 */
export function meterEndorsementsFromCells(cells, sourceNameByCode, candidateLabelById) {
  return cells.map((cell) => ({
    source_label: sourceNameByCode.get(cell.source_code) ?? cell.source_code,
    candidate_ids: cell.candidate_ids,
    candidate_labels: cell.candidate_ids.map(
      (candidateId) => candidateLabelById.get(candidateId) ?? candidateId,
    ),
  }));
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

/**
 * One block, with everything a template needs to paint it.
 *
 * @typedef {object} MeterBlockRender
 * @property {string} type
 * @property {number} width
 * @property {string} style
 * @property {boolean} band_start
 * @property {boolean} band_end
 * @property {boolean} tongue_corner_start
 * @property {boolean} tongue_corner_end
 * @property {string} source_label
 * @property {string} decision
 */

// Color (docs/METER_V2.md, Color): every value below is a CSS value string,
// not a literal color, so a block's paint is always a reference to a
// `base.css` token.
const METER_TIE_COLORS = ['var(--amber)', 'var(--meter-tie-deep)'];
const METER_TRAIL_COLORS = [
  'var(--meter-trail-slate)',
  'var(--meter-trail-taupe)',
  'var(--meter-trail-plum)',
];

/**
 * A color from a fixed pool, or — once the pool runs out — the pool's last
 * color stepped progressively toward the track, so two candidates in one
 * meter never share a swatch (docs/METER_V2.md, Color).
 *
 * Mirrors `_meter_stepped_color` in `rendering/context.py`.
 *
 * @param {readonly string[]} pool
 * @param {number} index
 * @returns {string}
 */
function meterSteppedColor(pool, index) {
  if (index < pool.length) return pool[index];
  const step = index - pool.length + 1;
  const percent = Math.max(30, 100 - 22 * step);
  return `color-mix(in srgb, ${pool[pool.length - 1]} ${percent}%, var(--meter-track))`;
}

/**
 * Each standing candidate's block color (docs/METER_V2.md, Color).
 *
 * Mirrors `meter_candidate_colors` in `rendering/context.py`. `leaderIds` is
 * the tie-aware leader set the scoring engine already decided (the audited
 * `support_leader_candidate_ids`, or a scored race's `winnerIds`), reused
 * rather than re-derived from `standings` so the meter's colors cannot
 * disagree with the race's own no-majority/tie decision (I56).
 *
 * @param {readonly string[]} standings
 * @param {ReadonlySet<string>} leaderIds
 * @param {boolean} hasMajority
 * @returns {Map<string, string>}
 */
export function meterCandidateColors(standings, leaderIds, hasMajority) {
  /** @type {Map<string, string>} */
  const colors = new Map();
  let tieIndex = 0;
  let trailIndex = 0;
  for (const candidateId of standings) {
    if (leaderIds.has(candidateId)) {
      if (leaderIds.size > 1) {
        colors.set(candidateId, meterSteppedColor(METER_TIE_COLORS, tieIndex));
        tieIndex += 1;
      } else {
        colors.set(candidateId, hasMajority ? 'var(--teal)' : 'var(--amber)');
      }
    } else {
      colors.set(candidateId, meterSteppedColor(METER_TRAIL_COLORS, trailIndex));
      trailIndex += 1;
    }
  }
  return colors;
}

/**
 * One block's tooltip decision line (docs/METER_V2.md, The discovery model).
 *
 * Mirrors `meter_block_decision` in `rendering/context.py`.
 *
 * @param {MeterBlock} block
 * @param {ReadonlyMap<string, string>} labels
 * @returns {string}
 */
export function meterBlockDecision(block, labels) {
  const names = block.candidate_ids.map((candidateId) => labels.get(candidateId) ?? candidateId);
  if (block.type === 'solid') return `Endorsed ${names[0]}`;
  const share = names.length === 2 ? '½ each' : `1/${names.length} each`;
  return `Split: ${names.join(' + ')} — ${share}`;
}

/**
 * A same-candidate seam: the fill mixed 88% with the seam pole
 * (docs/METER_V2.md, Seams). Mirrors `_meter_seam_tint`.
 *
 * @param {string} color
 * @returns {string}
 */
function meterSeamTint(color) {
  return `color-mix(in srgb, ${color} 88%, var(--meter-seam-pole))`;
}

/**
 * A cross-candidate seam: the 50/50 blend of the two facing colors, mixed 86%
 * with the seam pole (docs/METER_V2.md, Seams). Mirrors `_meter_seam_bridge`.
 *
 * @param {string} left
 * @param {string} right
 * @returns {string}
 */
function meterSeamBridge(left, right) {
  return (
    `color-mix(in srgb, color-mix(in srgb, ${left} 50%, ${right} 50%) 86%, ` +
    'var(--meter-seam-pole))'
  );
}

/**
 * The color a block's left-hand seam reads against: a solid block's own
 * color, or a split's higher-ranked (top) half. Mirrors
 * `_meter_block_leading_color`.
 *
 * @param {MeterBlock} block
 * @param {ReadonlyMap<string, string>} colors
 * @returns {string}
 */
function meterBlockLeadingColor(block, colors) {
  return /** @type {string} */ (colors.get(block.candidate_ids[0]));
}

/**
 * Every block's paint, seam, and tooltip data, in rendered order
 * (docs/METER_V2.md, Splits: placement and the tongue rule; Seams).
 *
 * Mirrors `meter_block_renders` in `rendering/context.py`; see
 * `MeterBlockRender` there for why `style` is the complete inline attribute
 * value rather than a set of parts a template assembles itself.
 *
 * @param {MeterBlock[]} blocks
 * @param {ReadonlyMap<string, string>} colors
 * @param {ReadonlyMap<string, string>} labels
 * @returns {MeterBlockRender[]}
 */
export function meterBlockRenders(blocks, colors, labels) {
  /** @type {MeterBlockRender[]} */
  const renders = [];
  /** @type {MeterBlock|null} */
  let previous = null;
  for (const block of blocks) {
    const declarations = [`--meter-w:${block.width}`];
    /** @type {string} */
    let rest;
    if (block.type === 'solid') {
      const color = /** @type {string} */ (colors.get(block.candidate_ids[0]));
      declarations.push(`--meter-c:${color}`);
      rest = color;
    } else {
      const topColor = /** @type {string} */ (colors.get(block.candidate_ids[0]));
      const bottomColor = /** @type {string} */ (colors.get(block.candidate_ids[1]));
      declarations.push(`--meter-ca:${topColor}`);
      declarations.push(`--meter-cb:${bottomColor}`);
      declarations.push(`--meter-splitline-rest:${bottomColor}`);
      declarations.push(`--meter-splitline-hover:${meterSeamBridge(topColor, bottomColor)}`);
      if (block.tongue_corner_start && block.tongue_corner_end) {
        declarations.push(
          `--meter-tongue-bg:linear-gradient(90deg, ${topColor} 0 50%, ${bottomColor} 50% 100%)`,
        );
      } else if (block.tongue_corner_start) {
        declarations.push(`--meter-tongue-bg:${topColor}`);
      } else if (block.tongue_corner_end) {
        declarations.push(`--meter-tongue-bg:${bottomColor}`);
      }
      rest = block.band_start && previous !== null ? bottomColor : topColor;
    }
    if (previous !== null) {
      const previousLeading = meterBlockLeadingColor(previous, colors);
      const currentLeading = meterBlockLeadingColor(block, colors);
      const seamRest = block.band_start ? previousLeading : rest;
      const seamHover =
        previousLeading === currentLeading
          ? meterSeamTint(previousLeading)
          : meterSeamBridge(previousLeading, currentLeading);
      declarations.push(`--meter-seam-rest:${seamRest}`);
      declarations.push(`--meter-seam-hover:${seamHover}`);
    }
    renders.push({
      type: block.type,
      width: block.width,
      style: declarations.join('; '),
      band_start: block.band_start,
      band_end: block.band_end,
      tongue_corner_start: block.tongue_corner_start,
      tongue_corner_end: block.tongue_corner_end,
      source_label: block.source_label,
      decision: meterBlockDecision(block, labels),
    });
    previous = block;
  }
  return renders;
}

/**
 * The meter's spoken name: the full standings, not the resting percentage
 * (docs/METER_V2.md, The discovery model's accessibility model). Empty
 * standings is the N/A state's own name.
 *
 * Mirrors `meter_accessible_label` in `rendering/context.py`.
 *
 * @param {readonly string[]} standings
 * @param {ReadonlyMap<string, Rational>} units
 * @param {ReadonlyMap<string, string>} labels
 * @returns {string}
 */
export function meterAccessibleLabel(standings, units, labels) {
  if (standings.length === 0) return 'No endorsements recorded';
  let total = Rational.zero();
  for (const candidateId of standings) {
    total = total.add(/** @type {Rational} */ (units.get(candidateId)));
  }
  return standings
    .map((candidateId) => {
      const candidateUnits = /** @type {Rational} */ (units.get(candidateId));
      return (
        `${labels.get(candidateId)} ${endorsementCountLabel(candidateUnits.toString())} of ` +
        `${endorsementCountLabel(total.toString())} endorsements`
      );
    })
    .join('; ');
}
