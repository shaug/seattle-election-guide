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

// The single-glyph vulgar fractions Unicode offers, keyed by the reduced
// fractional part (`numerator/denominator`) each renders. Everything else
// falls back inside `endorsementCountLabel`.
const VULGAR_FRACTION_GLYPHS = new Map([
  ['1/2', '½'],
  ['1/3', '⅓'],
  ['2/3', '⅔'],
  ['1/4', '¼'],
  ['3/4', '¾'],
  ['1/5', '⅕'],
  ['2/5', '⅖'],
  ['3/5', '⅗'],
  ['4/5', '⅘'],
  ['1/6', '⅙'],
  ['5/6', '⅚'],
  ['1/7', '⅐'],
  ['1/8', '⅛'],
  ['3/8', '⅜'],
  ['5/8', '⅝'],
  ['7/8', '⅞'],
  ['1/9', '⅑'],
  ['1/10', '⅒'],
]);

/**
 * An exact endorsement tally as a mixed number: "21½", "⅓", "7".
 *
 * Mirrors `endorsement_count_label` in `rendering/context.py`. Meter v2's
 * caption states the count, not the percent, and a split endorsement makes
 * the tally an exact rational (docs/METER_V2.md, Counting), so this renders
 * the published `numerator/denominator` form over bigint arithmetic — never a
 * float — as its whole part plus a vulgar-fraction glyph. A fractional part
 * with no single glyph, reachable the moment splits compound past the glyph
 * table (a quarter plus a third is 7/12), renders as numerator⁄denominator
 * with the U+2044 fraction slash, joined to a nonzero whole part by a
 * no-break space: "2 7⁄12".
 *
 * @param {string} countString
 * @returns {string}
 */
export function endorsementCountLabel(countString) {
  const count = Rational.parse(countString);
  const whole = count.numerator / count.denominator;
  const rest = count.numerator % count.denominator;
  if (rest === 0n) return `${whole}`;
  const glyph = VULGAR_FRACTION_GLYPHS.get(`${rest}/${count.denominator}`);
  if (glyph !== undefined) return whole === 0n ? glyph : `${whole}${glyph}`;
  const fallback = `${rest}⁄${count.denominator}`;
  return whole === 0n ? fallback : `${whole}\u00a0${fallback}`;
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
 * The caption's pre-v2 wording, kept as the fallback for a tie or a race with
 * no single recommended choice: there is no one candidate's count to lead the
 * sentence with, so the sentence states only the denominator, as it always did
 * (docs/METER_V2.md, Caption). Shared by `supportSummary` and
 * `raceDetailSupportSummary`, exactly as their Python mirrors share
 * `_meter_support_summary_fallback`.
 *
 * @param {number} explicitCount
 * @param {number|null} selectedTotal
 * @returns {string}
 */
function meterSupportSummaryFallback(explicitCount, selectedTotal) {
  return selectedTotal === null
    ? `Based on ${explicitCount} endorsing ${explicitCount === 1 ? 'source' : 'sources'}`
    : `Based on ${explicitCount} of ${selectedTotal} selected sources`;
}

/**
 * The meter's own caption (I39), stating the recommended choice's exact
 * endorsement count rather than only the denominator (docs/METER_V2.md,
 * Caption — decided in #314, revised in #314's own review): "21½ of 23
 * endorsements". The caption never repeats the recommended choice's name —
 * every card that renders it already carries that name one row up, in the
 * same headline `recommendationLabel` fills, so a name here would only
 * restate what the reader already read. A tie or a race with no single
 * recommended choice falls back to the caption's older wording.
 *
 * H38: while a lens is active the denominator is how many of the currently
 * selected sources are counted overall — the same count the banner states —
 * never the possessive "My sources".
 *
 * Mirrors `screen_support_summary` in `rendering/context.py`. `leaderUnits` is
 * the recommended choice's exact tally from `meterUnits`, or `null` when
 * there is no single choice to attribute it to — the caller already has both,
 * from building the same race's meter.
 *
 * @param {import('./lens-score.mjs').Rational|null} leaderUnits
 * @param {number} explicitCount
 * @param {number|null} [selectedTotal]
 * @returns {string}
 */
export function supportSummary(leaderUnits, explicitCount, selectedTotal = null) {
  if (leaderUnits === null) return meterSupportSummaryFallback(explicitCount, selectedTotal);
  const count = endorsementCountLabel(leaderUnits.toString());
  return selectedTotal === null
    ? `${count} of ${explicitCount} endorsements`
    : `${count} of ${selectedTotal} selected sources`;
}

/**
 * H34: the compact-mode sibling caption, shortened for a denser card — the
 * name drops too, because the card's own heading already carries it.
 *
 * Mirrors `screen_support_summary_compact` in `rendering/context.py`.
 *
 * @param {import('./lens-score.mjs').Rational|null} leaderUnits
 * @param {number} explicitCount
 * @param {number|null} [selectedTotal]
 * @returns {string}
 */
export function supportSummaryCompact(leaderUnits, explicitCount, selectedTotal = null) {
  if (leaderUnits === null) {
    return selectedTotal === null
      ? `${explicitCount} sources`
      : `${explicitCount} of ${selectedTotal} selected`;
  }
  const count = endorsementCountLabel(leaderUnits.toString());
  return selectedTotal === null
    ? `${count} of ${explicitCount} endorsements`
    : `${count} of ${selectedTotal} selected`;
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
    return meterSupportSummaryFallback(scored.explicitCount, selectedTotal);
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
