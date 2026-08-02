// Deterministic per-race divergence detection between one audited baseline and
// one personalized selection.
//
// This module presents nothing and calls no other lens module: it is a pure
// comparison over two lens-score.mjs scoreRace() results for the same race.
// The audited baseline is not re-derived here; the caller computes it by
// scoring the full selectable panel with no direct picks, which reproduces
// the published audited consensus exactly (lens-score.mjs's own tested
// contract), so a divergence can never drift from a second, independently
// maintained copy of the audited values.

/** The six structured dimensions a personalized card discloses a difference in. */
export const DIVERGENCE_DIMENSIONS = Object.freeze(
  /** @type {const} */ ([
    'leader',
    'recommendationState',
    'percentage',
    'sourceCount',
    'tie',
    'warning',
  ]),
);

/**
 * @typedef {(typeof DIVERGENCE_DIMENSIONS)[number]} DivergenceDimension
 */

/**
 * Which dimensions differ, plus whether any of them do.
 *
 * @typedef {Record<DivergenceDimension, boolean> & { anyChanged: boolean }} Divergence
 */

/**
 * @param {readonly string[]} codes
 * @returns {string}
 */
function sortedJoin(codes) {
  return [...codes].sort().join('|');
}

/**
 * Compare one audited scoreRace() result against one personalized result for
 * the same race, across every defined divergence dimension.
 *
 * - `leader`: the winning candidate set changed.
 * - `recommendationState`: one side has a recommendation and the other has
 *   insufficient evidence.
 * - `percentage`: the exact winning share changed (including appearing or
 *   disappearing entirely).
 * - `sourceCount`: the number of sources with an explicit endorsement changed.
 * - `tie`: the race is tied on one side and not the other.
 * - `warning`: the set of sources carrying a confidence warning changed.
 *
 * Typed against `scoreRace`'s result without importing the module: this
 * comparison stays independent of the scoring engine at runtime, and a
 * type-only reference keeps it that way while still binding the two shapes.
 *
 * @param {import('./lens-score.mjs').RaceScore} audited
 * @param {import('./lens-score.mjs').RaceScore} personalized
 * @returns {Divergence}
 */
export function compareRaceResults(audited, personalized) {
  const changed = {
    leader: sortedJoin(audited.winnerIds) !== sortedJoin(personalized.winnerIds),
    recommendationState:
      (audited.grade === 'Insufficient') !== (personalized.grade === 'Insufficient'),
    percentage: (audited.winnerShare ?? null) !== (personalized.winnerShare ?? null),
    sourceCount: audited.explicitCount !== personalized.explicitCount,
    tie: audited.isTied !== personalized.isTied,
    warning:
      sortedJoin(audited.confidenceWarningCodes) !==
      sortedJoin(personalized.confidenceWarningCodes),
  };
  return { ...changed, anyChanged: DIVERGENCE_DIMENSIONS.some((dimension) => changed[dimension]) };
}
