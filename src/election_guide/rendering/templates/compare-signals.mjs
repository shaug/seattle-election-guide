// Pure signal resolution for the election-scoped comparisons table.
//
// The published personalization contract owns source stances, eligibility, and
// category membership. The comparison display contract owns the audited
// all-sources baseline. Category arithmetic is delegated to lens-score.mjs so
// comparisons cannot grow a second scoring path.

import { scoreRace } from './lens-score.mjs';

const ALL_SOURCES_SIGNAL = 'gall';
const AFFIRMATIVE_STATES = new Set(['endorsement', 'multi_endorsement']);

export const BLANK_CELL = Object.freeze({ kind: 'blank' });
export const OUTSIDE_SCOPE_CELL = Object.freeze({ kind: 'outside_scope' });

function orderedAllocation(cell, race) {
  return Object.fromEntries(
    race.candidate_order
      .filter((candidateId) => Object.hasOwn(cell.allocation, candidateId))
      .map((candidateId) => [candidateId, cell.allocation[candidateId]]),
  );
}

function directCell(source, race) {
  if (!race.eligible_source_codes.includes(source.code)) return OUTSIDE_SCOPE_CELL;

  const published = race.cells.find((cell) => cell.source_code === source.code);
  if (published === undefined) {
    throw new RangeError(`race ${race.race_id} has no published cell for eligible source ${source.code}`);
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
 */
export function createColumnSignalEngine(personalization, comparisons) {
  const sources = new Map(personalization.sources.map((source) => [source.code, source]));
  const categories = new Map(
    personalization.categories.map((category) => [category.code, category]),
  );
  const displayIndex = new Map(
    comparisons.display_index.map((display) => [display.race_id, display]),
  );

  function resolveColumn(signal, race) {
    if (signal === ALL_SOURCES_SIGNAL) {
      const display = displayIndex.get(race.race_id);
      if (display === undefined) {
        throw new RangeError(`race ${race.race_id} has no comparison display baseline`);
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

export function isDataCell(cell) {
  return Array.isArray(cell.leadingPickIds) && cell.leadingPickIds.length > 0;
}

export function leadSetsIntersect(left, right) {
  if (!isDataCell(left) || !isDataCell(right)) return false;
  const rightLeads = new Set(right.leadingPickIds);
  return left.leadingPickIds.some((candidateId) => rightLeads.has(candidateId));
}

/**
 * Compare one cell with the configured baseline.
 *
 * Blank and outside-scope cells are neutral: they never claim agreement and
 * never create a difference.
 */
export function cellAgreement(cell, baseline) {
  if (!isDataCell(cell) || !isDataCell(baseline)) return 'neutral';
  return leadSetsIntersect(cell, baseline) ? 'agree' : 'differ';
}

/** True when any two data-bearing configured cells have disjoint lead sets. */
export function rowDiffers(cells) {
  const dataCells = cells.filter(isDataCell);
  for (let left = 0; left < dataCells.length; left += 1) {
    for (let right = left + 1; right < dataCells.length; right += 1) {
      if (!leadSetsIntersect(dataCells[left], dataCells[right])) return true;
    }
  }
  return false;
}
