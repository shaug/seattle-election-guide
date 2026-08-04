// The guide's display strings, as the audited renderer writes them.
//
// Every function here mirrors one in `rendering/context.py`: while a lens is
// active the client recomputes the same captions, shares, and accessible
// summaries the server rendered for the audited default, and the two must agree
// word for word or a reader sees one quantity with two spellings. Extracted
// from guide.html.j2's module script by issue #239 so the mirror is a module
// that can be tested in Node against the Python side, rather than prose inside
// a template (docs/FRONTEND.md § Cross-language mirrors: a comment is not a
// contract).
//
// Pure by construction: strings in, strings out, no DOM.

import { Rational } from './lens-score.mjs';

/**
 * A share as a whole percentage, rounded half-up on exact integer arithmetic.
 *
 * Integers rather than floats for the same reason `comparison_percentage_label`
 * uses them: a float round would put the client one ulp away from the server on
 * an exact half, and the two sides would print different numbers for one share.
 *
 * @param {string|null} shareString
 * @returns {string}
 */
export function percentageLabel(shareString) {
  if (shareString === null) return 'N/A';
  const share = Rational.parse(shareString);
  const scaledNumerator = share.numerator * 100n;
  const scaledDenominator = share.denominator;
  const whole = (scaledNumerator * 2n + scaledDenominator) / (2n * scaledDenominator);
  return `${whole}%`;
}

/**
 * Whether the leading choice failed to clear half the endorsing sources.
 *
 * @param {string|null} shareString
 * @returns {boolean}
 */
export function hasNoMajority(shareString) {
  if (shareString === null) return false;
  const share = Rational.parse(shareString);
  return share.numerator * 2n <= share.denominator;
}

/**
 * The meter's spoken label. The tone tint is never the only carrier.
 *
 * A race with no share is spoken as "not available", not as the meter's visible
 * `N/A`. `screen_share_accessible_label` has always said so; this reused
 * `percentageLabel` instead and so read the abbreviation aloud, which is the
 * divergence the parity fixture found (issue #240). The visible text and the
 * spoken text are allowed to differ — an abbreviation that fits in a meter is
 * not a phrase a screen reader should announce — so the two sides agreeing is
 * the whole of the claim here.
 *
 * @param {string|null} shareString
 * @returns {string}
 */
export function shareAccessibleLabel(shareString) {
  const share = shareString === null ? 'not available' : percentageLabel(shareString);
  return (
    `${hasNoMajority(shareString) ? 'No majority. ' : ''}` +
    `Consensus among explicitly endorsing sources: ${share}`
  );
}

/** The scoring engine's per-race result, which is what every caption reads. */
/** @typedef {import('./lens-score.mjs').RaceScore} ScoredRace */

/**
 * The race's headline result.
 *
 * @param {ScoredRace} scored
 * @param {ReadonlyMap<string, string>} labels
 * @returns {string}
 */
export function recommendationLabel(scored, labels) {
  if (scored.grade === 'Insufficient') return 'Too few endorsements';
  if (scored.isTied) return scored.winnerIds.map((id) => labels.get(id) ?? id).join(' / ');
  return (scored.winnerId !== null ? labels.get(scored.winnerId) : null) ?? 'No consensus';
}

/**
 * The card's support caption.
 *
 * H38: while a lens is active the caption states how many of the currently
 * selected sources endorsed this race, out of how many are selected overall —
 * the same count the banner states — never the possessive "My sources". With no
 * lens (`selectedTotal === null`, the server-rendered caption's own text) the
 * caption is unchanged.
 *
 * @param {ScoredRace} scored
 * @param {number|null} [selectedTotal]
 * @returns {string}
 */
export function supportSummary(scored, selectedTotal = null) {
  return selectedTotal === null
    ? `Based on ${scored.explicitCount} endorsing ${scored.explicitCount === 1 ? 'source' : 'sources'}`
    : `Based on ${scored.explicitCount} of ${selectedTotal} selected sources`;
}

/**
 * H34: the compact-mode sibling caption, shortened for a denser card.
 *
 * @param {ScoredRace} scored
 * @param {number|null} [selectedTotal]
 * @returns {string}
 */
export function supportSummaryCompact(scored, selectedTotal = null) {
  return selectedTotal === null
    ? `${scored.explicitCount} sources`
    : `${scored.explicitCount} of ${selectedTotal} selected`;
}

/**
 * The quiet reference bar's text: what the full panel says about this race.
 *
 * @param {ScoredRace} audited
 * @param {ReadonlyMap<string, string>} labels
 * @returns {string}
 */
export function allSourcesSummary(audited, labels) {
  return `All sources: ${recommendationLabel(audited, labels)} · ${percentageLabel(audited.winnerShare)}`;
}

/**
 * Mirrors `race_detail_support_summary` in `rendering/context.py`.
 *
 * A single sole leader states its own contributing count against the total,
 * matching the count already shown in that candidate's section; a tie or an
 * insufficient grade falls back to the caption's own sentence, because there is
 * no single leader's count to report.
 *
 * @param {ScoredRace} scored
 * @param {number|null} selectedTotal
 * @param {number} leaderCount
 * @returns {string}
 */
export function raceDetailSupportSummary(scored, selectedTotal, leaderCount) {
  if (scored.grade === 'Insufficient' || scored.isTied)
    return supportSummary(scored, selectedTotal);
  const noun = scored.explicitCount === 1 ? 'source' : 'sources';
  const verb = scored.explicitCount === 1 ? 'agrees' : 'agree';
  return `${leaderCount} of ${scored.explicitCount} endorsing ${noun} ${verb}`;
}

/**
 * Mirrors `race_detail_accessible_summary` in `rendering/context.py`, for a race
 * page's visually-hidden `aria-describedby` text.
 *
 * @param {ScoredRace} scored
 * @param {ReadonlyMap<string, string>} labels
 * @param {number|null} selectedTotal
 * @param {number} leaderCount
 * @returns {string}
 */
export function raceDetailAccessibleSummary(scored, labels, selectedTotal, leaderCount) {
  const share =
    scored.winnerShare === null ? 'Consensus unavailable' : percentageLabel(scored.winnerShare);
  const qualifier = hasNoMajority(scored.winnerShare) ? 'No majority. ' : '';
  return (
    `${recommendationLabel(scored, labels)}. ${qualifier}${share}. ` +
    `${raceDetailSupportSummary(scored, selectedTotal, leaderCount)}.`
  );
}

/**
 * The banner's live count.
 *
 * @param {number} selectedCount
 * @param {number} tallyingCount
 * @param {boolean} personalized
 * @returns {string}
 */
export function countingSummary(selectedCount, tallyingCount, personalized) {
  return personalized
    ? `Counting ${selectedCount} of ${tallyingCount} sources.`
    : `Counting all ${tallyingCount} sources.`;
}

/**
 * The filter status line's three parts, in announcement order.
 *
 * Only the race count is visibly useful — the view and scope merely echo the
 * adjacent controls — but the aria-live announcement keeps all three so a
 * non-visual reader hears the full outcome.
 *
 * @param {object} state
 * @param {number} state.visible
 * @param {boolean} state.contestedOnly
 * @param {boolean} state.compact
 * @param {string} state.scopeLabel
 * @returns {string[]}
 */
export function filterStatusParts({ visible, contestedOnly, compact, scopeLabel }) {
  const raceNoun = contestedOnly
    ? visible === 1
      ? 'contested race'
      : 'contested races'
    : visible === 1
      ? 'race'
      : 'races';
  return [`${visible} ${raceNoun} shown`, compact ? 'Compact' : 'Full', scopeLabel];
}
