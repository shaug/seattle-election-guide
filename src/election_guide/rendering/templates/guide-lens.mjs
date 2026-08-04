// The guide's personalized rendering: every race card while a lens is active.
//
// The card is lit's (issue #248). Its three regions — the result block, the
// caption block, and the card foot — are rendered from view models built here
// and owned by `guide-card.mjs`. Takeover is lazy and one-way, as § Rendering's
// idiom requires for a region whose content is a projection of state: a visit
// that never leaves the audited default does no DOM work on any card, and the
// first divergent selection takes every card over for the rest of the page's
// life. Returning to the audited default is then a render of the audited view
// model, not a copy of the server's markup put back —
// `guide-markup-parity.test.mjs` is what makes those the same thing.
//
// The race-detail dialog this module also rendered — imperatively, and
// deliberately left so by #248 — is gone with issue #136: race detail is a page
// now, and `race-client.mjs` renders it lit-native from the same view models.
//
// Wiring, not a computing module: it holds element references and renders into
// them. The strings it renders come from `guide-format.mjs`, which is pure and
// tested against the Python renderer it mirrors.

import { render } from 'lit-html';
import {
  meterView,
  raceContextTemplate,
  raceFootTemplate,
  raceResultTemplate,
} from './guide-card.mjs';
import {
  allSourcesSummary,
  countingSummary,
  hasNoMajority,
  recommendationLabel,
  supportSummary,
  supportSummaryCompact,
} from './guide-format.mjs';
import { compareRaceResults } from './lens-divergence.mjs';
import { scoreSelection } from './lens-score.mjs';
import { isDefaultSelection, tallyingSourceCodes } from './lens-selection.mjs';

/**
 * Which tallying sources a selection actually counts, and whether that is still
 * the audited default.
 *
 * Derived once, because the banner's "Counting N of M" and the cards' own
 * personalized rendering are the same judgement. A page that decided them
 * separately could say it was counting every source while the cards showed a
 * narrowed result, which is the disagreement `lens-selection.mjs` states the
 * tallying rule once to prevent.
 *
 * @param {readonly string[]} tallyingCodes
 * @param {readonly string[]} selectedCodes
 * @returns {{ selected: string[], personalized: boolean }}
 */
function countedSelection(tallyingCodes, selectedCodes) {
  const selected = tallyingCodes.filter((code) => selectedCodes.includes(code)).sort();
  return { selected, personalized: !isDefaultSelection(selected, tallyingCodes) };
}

/** The audited insufficiency warning, as guide.html.j2 renders it. */
const AUDITED_INSUFFICIENT_NOTE = 'Too few endorsements to measure agreement.';
/** Its personalized wording: the same shortage, over the reader's own sources. */
const PERSONALIZED_INSUFFICIENT_NOTE =
  'Too few endorsements to measure agreement among your selected sources.';

/**
 * @typedef {object} GuideLens
 * @property {(selectedCodes: readonly string[]) => void} render Apply one
 *   selection to the whole page. Whether that selection diverges from the
 *   audited default is readable from the `lens-personalized` root class this
 *   sets, so it is not also returned.
 */

/**
 * Build the guide's lens renderer, or `null` when the release policy disables
 * personalization and there is nothing on the page for a lens to change.
 *
 * @param {GuidePayload} payload
 * @returns {GuideLens|null}
 */
export function createGuideLens(payload) {
  const personalization = payload.personalization;
  if (personalization === null) return null;

  const root = document.documentElement;
  const tallyingCodes = tallyingSourceCodes(payload.sources);

  // Locating each race's render target is projection, not state: the id is the
  // payload's own `race_id`, and nothing is read back out of the card.
  const raceCards = new Map(
    /** @type {HTMLElement[]} */ ([...document.querySelectorAll('[data-publication-race-id]')]).map(
      (card) => [/** @type {string} */ (card.dataset.publicationRaceId), card],
    ),
  );
  // Every per-race presentation value comes from the payload, which publishes
  // exactly what the server rendered.
  const candidateLabelsByRaceId = new Map(
    payload.races.map((race) => [
      race.race_id,
      new Map(race.candidates.map((candidate) => [candidate.candidate_id, candidate.label])),
    ]),
  );
  // The full selectable panel with no direct picks reproduces the published
  // audited consensus exactly (lens-score.mjs's own tested contract), so scoring
  // it once gives every card a structured baseline to diff against instead of a
  // second, independently maintained copy of the audited values.
  const auditedByRaceId = new Map(
    scoreSelection(personalization, {
      categoryCodes: personalization.categories
        .filter((category) => category.selectable)
        .map((category) => category.code),
      sourceCodes: [],
    }).races.map((race) => [race.raceId, race]),
  );

  /**
   * Whether lit has taken the cards over from the server. One-way, and
   * page-wide rather than per-card: one divergent selection changes every
   * card's caption (it names the selected total), so there is no state in
   * which some cards are the server's and others are lit's.
   */
  let cardsTakenOver = false;

  /**
   * One card's three regions, as view models.
   *
   * `selectedTotal` is null for the audited view model, which is what makes
   * the captions read "Based on N endorsing sources" — the server's own
   * wording — rather than naming a selection the reader does not have.
   *
   * @param {string} raceId
   * @param {import('./lens-score.mjs').RaceScore} scored
   * @param {number|null} selectedTotal
   * @param {import('./guide-card.mjs').AllSourcesView|null} allSources
   */
  const cardViews = (raceId, scored, selectedTotal, allSources) => {
    const labels = candidateLabelsByRaceId.get(raceId) ?? new Map();
    return {
      result: {
        recommendation: recommendationLabel(scored, labels),
        meter: meterView(scored.winnerShare),
      },
      context: {
        noMajority: hasNoMajority(scored.winnerShare),
        support: supportSummary(scored, selectedTotal),
        supportCompact: supportSummaryCompact(scored, selectedTotal),
      },
      foot: {
        insufficientNote:
          scored.grade !== 'Insufficient'
            ? null
            : selectedTotal === null
              ? AUDITED_INSUFFICIENT_NOTE
              : PERSONALIZED_INSUFFICIENT_NOTE,
        allSources,
      },
    };
  };

  /**
   * Render one card's regions.
   *
   * @param {Element} card
   * @param {ReturnType<typeof cardViews>} views
   */
  const renderCard = (card, views) => {
    const result = /** @type {HTMLElement|null} */ (card.querySelector('[data-lens-result]'));
    const context = /** @type {HTMLElement|null} */ (card.querySelector('[data-lens-context]'));
    const foot = /** @type {HTMLElement|null} */ (card.querySelector('[data-lens-foot]'));
    if (!cardsTakenOver) {
      // Takeover is one-way and explicit: the server's markup is dropped once,
      // and lit owns these three regions from now on. Without this, lit would
      // render its own copy after the server's rather than in place of it.
      for (const region of [result, context, foot]) region?.replaceChildren();
    }
    if (result) render(raceResultTemplate(views.result), result);
    if (context) render(raceContextTemplate(views.context), context);
    if (foot) render(raceFootTemplate(views.foot), foot);
  };

  /**
   * Put the cards back to the audited default.
   *
   * They are re-rendered only if lit ever took them over: until then the
   * server's own markup is still there and is already this, which is the whole
   * of what "the default audited view does zero DOM work" buys.
   */
  const restoreAudited = () => {
    if (!cardsTakenOver) return;
    raceCards.forEach((card, raceId) => {
      const audited = auditedByRaceId.get(raceId);
      if (audited) renderCard(card, cardViews(raceId, audited, null, null));
    });
  };

  return {
    render(selectedCodes) {
      const { selected, personalized } = countedSelection(tallyingCodes, selectedCodes);
      root.classList.toggle('lens-personalized', personalized);
      if (!personalized) {
        // A lens that no longer applies (every source reselected) must restore
        // the audited default's own values — nothing else runs once
        // !personalized, so without this a prior lens's numbers would linger
        // after it clears.
        restoreAudited();
        return;
      }
      const results = scoreSelection(personalization, {
        categoryCodes: [],
        sourceCodes: selected,
      });
      const personalizedByRaceId = new Map(results.races.map((race) => [race.raceId, race]));
      raceCards.forEach((card, raceId) => {
        const scored = personalizedByRaceId.get(raceId);
        const audited = auditedByRaceId.get(raceId);
        if (!scored || !audited) return;
        const labels = candidateLabelsByRaceId.get(raceId) ?? new Map();
        const divergence = compareRaceResults(audited, scored);
        // The compact audited comparison renders only when this race actually
        // diverges, so an unchanged race stays free of redundant audited detail.
        const allSources = divergence.anyChanged
          ? { summary: allSourcesSummary(audited, labels), leaderChanged: divergence.leader }
          : null;
        renderCard(card, cardViews(raceId, scored, results.sourceCodes.length, allSources));
      });
      // After the loop, so the first divergent render is the one that clears
      // every card's server markup.
      cardsTakenOver = true;
    },
  };
}

/**
 * The banner's live count for one selection.
 *
 * The banner is page chrome rather than a card, so `guide-client.mjs` owns its
 * region; this is the one lens computation that region needs, kept here beside
 * the selection logic it shares.
 *
 * @param {GuidePayload} payload
 * @param {readonly string[]} selectedCodes
 * @returns {string}
 */
export function lensCountingSummary(payload, selectedCodes) {
  const tallyingCodes = tallyingSourceCodes(payload.sources);
  const { selected, personalized } = countedSelection(tallyingCodes, selectedCodes);
  return countingSummary(selected.length, tallyingCodes.length, personalized);
}
