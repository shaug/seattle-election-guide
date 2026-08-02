// Pure signal resolution for the election-scoped comparisons table.
//
// The published personalization contract owns source stances, eligibility, and
// category membership. The comparison display contract owns the published
// all-sources result. Category arithmetic is delegated to lens-score.mjs so
// comparisons cannot grow a second scoring path.

import { scoreRace } from './lens-score.mjs';

const ALL_SOURCES_SIGNAL = 'gall';
const AFFIRMATIVE_STATES = new Set(['endorsement', 'multi_endorsement']);

/**
 * One resolved table cell. The five kinds are disjoint: `blank` and
 * `outside_scope` carry no data and are never compared, while `direct`,
 * `comparison`, `aggregate`, and `baseline` all carry a lead set.
 *
 * Consumers probe `leadingPickIds`, `share`, `endorsingCount`, and
 * `memberCount` before narrowing by kind — `isDataCell` decides the kind from
 * the first, and the table renders a meta line from the rest. So every kind
 * declares all four, present-and-undefined where it has no such value, rather
 * than omitting them and forcing a `kind` switch the code does not perform.
 *
 * @typedef {object} EmptyCell
 * @property {'blank'|'outside_scope'} kind
 * @property {undefined} [leadingPickIds]
 * @property {undefined} [share]
 * @property {undefined} [endorsingCount]
 * @property {undefined} [memberCount]
 */

/**
 * @typedef {object} DirectCell
 * @property {'direct'|'comparison'} kind
 * @property {string} sourceCode
 * @property {string[]} leadingPickIds
 * @property {Record<string, string>} allocation
 * @property {undefined} [share]
 * @property {undefined} [endorsingCount]
 * @property {undefined} [memberCount]
 */

/**
 * @typedef {object} AggregateCell
 * @property {'aggregate'} kind
 * @property {string} categoryCode
 * @property {string[]} leadingPickIds
 * @property {string|null} share
 * @property {number} endorsingCount
 * @property {number} memberCount
 * @property {Record<string, string>} allocation
 */

/**
 * @typedef {object} BaselineCell
 * @property {'baseline'} kind
 * @property {string[]} leadingPickIds
 * @property {string|null} share
 * @property {number} endorsingCount
 * @property {undefined} [memberCount]
 */

/** @typedef {EmptyCell|DirectCell|AggregateCell|BaselineCell} ComparisonCell */

/** A cell that carries a lead set, and so can agree or differ. */
/** @typedef {DirectCell|AggregateCell|BaselineCell} DataCell */

/** @type {EmptyCell} */
export const BLANK_CELL = Object.freeze({ kind: 'blank' });
/** @type {EmptyCell} */
export const OUTSIDE_SCOPE_CELL = Object.freeze({ kind: 'outside_scope' });

/**
 * @param {PersonalizationCell} cell
 * @param {PersonalizationRace} race
 * @returns {Record<string, string>}
 */
function orderedAllocation(cell, race) {
  return Object.fromEntries(
    race.candidate_order
      .filter((candidateId) => Object.hasOwn(cell.allocation, candidateId))
      .map((candidateId) => [candidateId, cell.allocation[candidateId]]),
  );
}

/**
 * @param {PersonalizationSource} source
 * @param {PersonalizationRace} race
 * @returns {DirectCell|EmptyCell}
 */
function directCell(source, race) {
  if (!race.eligible_source_codes.includes(source.code)) return OUTSIDE_SCOPE_CELL;

  const published = race.cells.find((cell) => cell.source_code === source.code);
  if (published === undefined) {
    throw new RangeError(
      `race ${race.race_id} has no published cell for eligible source ${source.code}`,
    );
  }
  if (!AFFIRMATIVE_STATES.has(published.state)) return BLANK_CELL;

  const allocation = orderedAllocation(published, race);
  return {
    kind: source.panel_role === 'comparison' ? 'comparison' : 'direct',
    sourceCode: source.code,
    leadingPickIds: Object.keys(allocation),
    allocation,
  };
}

/**
 * @param {PersonalizationCategory} category
 * @param {PersonalizationRace} race
 * @param {PersonalizationContract} personalization
 * @returns {AggregateCell|EmptyCell}
 */
function aggregateCell(category, race, personalization) {
  const score = scoreRace(race, category.member_source_codes, personalization);
  if (score.explicitCount === 0) return BLANK_CELL;

  return {
    kind: 'aggregate',
    categoryCode: category.code,
    leadingPickIds: score.winnerIds,
    share: score.winnerShare,
    endorsingCount: score.explicitCount,
    memberCount: score.eligibleCount,
    allocation: Object.fromEntries(
      score.standings.map((standing) => [standing.candidateId, standing.supportPoints]),
    ),
  };
}

/**
 * Bind the pure resolver to one validated publication payload.
 *
 * The returned resolveColumn(signal, race) method is the downstream contract:
 * race is one entry from personalization.races and signal is a current source
 * code, category code, or the reserved `gall` sentinel.
 *
 * @param {PersonalizationContract} personalization
 * @param {ComparisonsContract} comparisons
 * @returns {{ resolveColumn: (signal: string, race: PersonalizationRace) => ComparisonCell }}
 */
export function createColumnSignalEngine(personalization, comparisons) {
  const sources = new Map(personalization.sources.map((source) => [source.code, source]));
  const categories = new Map(
    personalization.categories.map((category) => [category.code, category]),
  );
  const displayIndex = new Map(
    comparisons.display_index.map((display) => [display.race_id, display]),
  );

  /**
   * @param {string} signal
   * @param {PersonalizationRace} race
   * @returns {ComparisonCell}
   */
  function resolveColumn(signal, race) {
    if (signal === ALL_SOURCES_SIGNAL) {
      const display = displayIndex.get(race.race_id);
      if (display === undefined) {
        throw new RangeError(`race ${race.race_id} has no published all-sources result`);
      }
      return {
        kind: 'baseline',
        leadingPickIds: [...display.baseline.leading_pick_ids],
        share: display.baseline.share,
        endorsingCount: display.baseline.explicit_source_count,
      };
    }

    const category = categories.get(signal);
    if (category !== undefined) {
      if (category.panel_role === 'comparison') {
        if (category.member_source_codes.length !== 1) {
          throw new RangeError(`comparison category ${signal} must have exactly one member`);
        }
        const source = sources.get(category.member_source_codes[0]);
        if (source === undefined) {
          throw new RangeError(`comparison category ${signal} references an unknown source`);
        }
        return directCell(source, race);
      }
      return aggregateCell(category, race, personalization);
    }

    const source = sources.get(signal);
    if (source !== undefined) {
      return directCell(source, race);
    }
    throw new RangeError(`unknown comparison signal ${signal}`);
  }

  return Object.freeze({ resolveColumn });
}

/**
 * @param {ComparisonCell} cell
 * @returns {cell is DataCell}
 */
export function isDataCell(cell) {
  return Array.isArray(cell.leadingPickIds) && cell.leadingPickIds.length > 0;
}

/**
 * @param {ComparisonCell} left
 * @param {ComparisonCell} right
 * @returns {boolean}
 */
export function leadSetsIntersect(left, right) {
  if (!isDataCell(left) || !isDataCell(right)) return false;
  const rightLeads = new Set(right.leadingPickIds);
  return left.leadingPickIds.some((candidateId) => rightLeads.has(candidateId));
}

/**
 * Compare one cell with the configured reference.
 *
 * Blank and outside-scope cells are neutral: they never claim agreement and
 * never create a difference.
 *
 * @param {ComparisonCell} cell
 * @param {ComparisonCell} reference
 * @returns {'neutral'|'agree'|'differ'}
 */
export function cellAgreement(cell, reference) {
  if (!isDataCell(cell) || !isDataCell(reference)) return 'neutral';
  return leadSetsIntersect(cell, reference) ? 'agree' : 'differ';
}

/**
 * True when any configured comparison has a disjoint lead set from the reference.
 *
 * @param {readonly ComparisonCell[]} cells
 * @returns {boolean}
 */
export function rowDiffers(cells) {
  const [reference, ...comparisons] = cells;
  return comparisons.some((cell) => cellAgreement(cell, reference) === 'differ');
}
