// Client-side mirror of the audited Times/comparison presentation
// (`PublicationComparison` in `publication/models.py`), recomputed against a
// personalized lens result.
//
// UI polish issue 132 (H31): the server bakes the Times agree/differ tone and
// verb in against the audited result and never recomputes it when a lens
// changes the displayed leader, so the bar can read "agrees" while visibly
// differing from the number beside it. This module recomputes the same
// tone/verb against the *displayed* (personalized) result instead, using
// exactly the same status vocabulary and wording the server's own properties
// produce, so toggling a lens on and off never changes the wording for an
// unchanged race.
//
// This module presents nothing and touches no DOM: it is a pure function of
// one comparison source's published cell plus one scoreRace() result.

/** The five statuses the audited engine itself distinguishes for a comparison. */
const NOT_COVERED_CELL_STATES = new Set(['not_covered', 'unavailable', 'unverified']);

const TONE_BY_STATUS = Object.freeze({
  agrees: 'agrees',
  differs: 'differs',
  no_endorsement: 'not_covered',
  not_covered: 'not_covered',
  no_consensus: 'neutral',
});

const NO_RECOMMENDATION_GRADES = new Set(['TIED', 'Insufficient']);

/**
 * Resolve the comparison source's own status against a personalized result,
 * mirroring `_comparison_result` in `scoring/engine.py` exactly: a tied or
 * insufficient personalized result forces `no_consensus` regardless of what
 * the comparison source itself picked, just as the audited engine passes no
 * winner id through in that case.
 */
function resolveStatus(cell, personalized) {
  if (cell === undefined || NOT_COVERED_CELL_STATES.has(cell.state)) {
    return { status: 'not_covered', candidateIds: [] };
  }
  if (cell.state === 'no_endorsement') {
    return { status: 'no_endorsement', candidateIds: [] };
  }
  const candidateIds = Object.keys(cell.allocation);
  const winnerId = NO_RECOMMENDATION_GRADES.has(personalized.grade) ? null : personalized.winnerId;
  if (winnerId === null) return { status: 'no_consensus', candidateIds };
  return { status: candidateIds.includes(winnerId) ? 'agrees' : 'differs', candidateIds };
}

function labelForStatus(status) {
  if (status === 'agrees') return 'Times agrees';
  if (status === 'differs') return 'Times differs';
  // H32: a bare "Times · <name>" cannot be told apart from an unlabeled
  // agree/differ state, so the verb itself names the missing consensus —
  // the visible bar must carry the same explanation the aria-label does.
  if (status === 'no_consensus') return 'Times picks (no consensus)';
  return 'Times';
}

function choiceLabelFor(candidateIds, labelById) {
  if (candidateIds.length === 0) return 'not covered';
  return candidateIds.map((candidateId) => labelById.get(candidateId) ?? candidateId).join(' / ');
}

function ariaLabelFor(status, choiceLabel) {
  if (status === 'agrees') return `Seattle Times agrees with consensus: ${choiceLabel}`;
  if (status === 'differs') return `Seattle Times endorses a different choice: ${choiceLabel}`;
  if (status === 'no_consensus') {
    return `Seattle Times endorses ${choiceLabel}; progressive sources have no consensus`;
  }
  if (status === 'no_endorsement') return 'Seattle Times made no endorsement';
  return 'Seattle Times: not covered';
}

/**
 * Recompute one comparison source's presentation against a personalized
 * `scoreRace()` result.
 *
 * @param {object|undefined} cell one race's `PersonalizationCell` for the
 *   comparison source (`race.cells.find((item) => item.source_code === code)`),
 *   or `undefined` if the source has no published cell for this race.
 * @param {object} personalized a `scoreRace()` result for the same race.
 * @param {Map<string, string>} labelById candidate id -> display label.
 */
export function personalizedComparison(cell, personalized, labelById) {
  const { status, candidateIds } = resolveStatus(cell, personalized);
  const choiceLabel = choiceLabelFor(candidateIds, labelById);
  return {
    tone: TONE_BY_STATUS[status],
    statusLabel: labelForStatus(status),
    choiceLabel,
    showChoice: status !== 'agrees',
    ariaLabel: ariaLabelFor(status, choiceLabel),
  };
}
