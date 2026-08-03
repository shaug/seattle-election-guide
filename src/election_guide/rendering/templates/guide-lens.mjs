// The guide's personalized rendering: every card and race-detail dialog while a
// lens is active.
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
// The dialog interior is still imperative, deliberately; `renderRaceDetail`
// below says why.
//
// Wiring, not a computing module: it holds element references and renders into
// them. The strings it renders come from `guide-format.mjs`, which is pure and
// tested against the Python renderer it mirrors.

import { render } from 'lit-html';
import {
  allSourcesAccessibleLabel,
  allSourcesToneClass,
  raceContextTemplate,
  raceFootTemplate,
  raceResultTemplate,
} from './guide-card.mjs';
import {
  allSourcesSummary,
  countingSummary,
  hasNoMajority,
  percentageLabel,
  raceDetailAccessibleSummary,
  recommendationLabel,
  shareAccessibleLabel,
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
 * The share meter's view model, shared by the card and every dialog candidate.
 *
 * One policy for the NA state, the fill percentage, and the accessible label
 * (I40/I41), because the card meter and the dialog's lens-only meters must
 * never disagree about the same share. The card's is rendered from this by
 * `guide-card.mjs`; the dialog's is still applied by hand, below.
 *
 * @param {string|null} shareString
 * @returns {import('./guide-card.mjs').ShareMeterView}
 */
function meterView(shareString) {
  const label = percentageLabel(shareString);
  const fillPercent = shareString === null ? null : Number.parseInt(label, 10);
  return {
    label,
    fillPercent,
    // I41: below ~30% fill the white label bleeds onto the pale track, so the
    // low-fill guard (guide.css) renders it after the fill in muted ink
    // instead. Decided once, here, because guide.css applies the guard to the
    // card meter and the dialog meter through one rule.
    lowFill: fillPercent !== null && fillPercent < 30,
    noMajority: hasNoMajority(shareString),
    accessibleLabel: shareAccessibleLabel(shareString),
  };
}

/**
 * Apply the meter policy to a dialog meter, which lit does not own.
 *
 * @param {HTMLElement} meterEl
 * @param {string|null} shareString
 * @returns {string} The percentage label, for a caller whose text lives inside
 *   the meter.
 */
function applyMeterFill(meterEl, shareString) {
  const view = meterView(shareString);
  meterEl.classList.toggle('race-detail-meter-na', view.fillPercent === null);
  meterEl.classList.toggle('meter-low-fill', view.lowFill);
  meterEl.classList.toggle('meter-no-majority', view.noMajority);
  meterEl.style.setProperty('--meter-fill', view.fillPercent === null ? '0%' : view.label);
  meterEl.setAttribute('aria-label', view.accessibleLabel);
  return view.label;
}

/**
 * The full-panel baseline in a quiet info-bar with an agree/differ tone:
 * "differs" means the leading choice itself changed, not merely its share
 * (issue 115, G24–G27). The tint is never the only carrier — the aria-label
 * states the agreement in words.
 *
 * The card renders this shape through `guide-card.mjs`; the dialog's copy is
 * still applied by hand, so the two share the view model rather than the
 * writing of it.
 *
 * @param {Element} element
 * @param {import('./guide-card.mjs').AllSourcesView} view
 */
function applyAllSourcesSignal(element, view) {
  element.textContent = view.summary;
  element.className = `lens-comparison ${allSourcesToneClass(view.leaderChanged)}`;
  element.setAttribute('aria-label', allSourcesAccessibleLabel(view));
}

/**
 * Reorder the dialog's candidate sections in place to match `orderedIds`,
 * leaving every other child of `.race-detail-outcomes` (the reference bar, the
 * source-group listings) exactly where it is. `anchor` — the first
 * non-candidate sibling, captured once before any move — stays a stable
 * insertion point throughout: each `insertBefore` only ever relocates a
 * candidate section, never the anchor itself.
 *
 * @param {Element} card
 * @param {readonly string[]} orderedIds
 */
function applyCandidateOrder(card, orderedIds) {
  const outcomes = card.querySelector('.race-detail-outcomes');
  if (!outcomes) return;
  const sections = /** @type {HTMLElement[]} */ ([
    ...outcomes.querySelectorAll(':scope > [data-race-detail-candidate-id]'),
  ]);
  if (sections.length === 0) return;
  const sectionById = new Map(
    sections.map((section) => [section.dataset.raceDetailCandidateId, section]),
  );
  const anchor = sections[sections.length - 1].nextElementSibling;
  for (const candidateId of orderedIds) {
    const section = sectionById.get(candidateId);
    if (section) outcomes.insertBefore(section, anchor);
  }
}

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
  const defaultCandidateOrderByRaceId = new Map(
    payload.races.map((race) => [
      race.race_id,
      race.candidates.map((candidate) => candidate.candidate_id),
    ]),
  );
  const defaultAccessibleSummaryByRaceId = new Map(
    payload.races.map((race) => [race.race_id, race.audited_accessible_summary]),
  );
  const raceDataById = new Map(personalization.races.map((race) => [race.race_id, race]));

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
   * Apply one race's personalized result to the race-detail dialog.
   *
   * Still imperative, and deliberately so: issue #136 replaces the dialog with
   * real race pages and deletes this markup outright, so converting it to
   * lit-html would be writing templates for a region that is being removed
   * (docs/FRONTEND.md § Adoption records the sequencing, and #245 records the
   * carve-out). Issue #248 converted the card around it and left this half
   * alone. Do not extend it; the race page is where new detail rendering goes.
   *
   * I56: every computed number in the dialog (per-candidate counts, shares,
   * meters, and the leading-choice kicker) must equal the lens numbers on the
   * main page while a lens is active; no quantity may appear with two values.
   * Unselected sources stay visible as evidence, marked as not counted, rather
   * than hidden.
   *
   * @param {string} raceId
   * @param {Element} card
   * @param {import('./lens-score.mjs').RaceScore} personalized
   * @param {ReadonlyMap<string, string>} labels
   * @param {import('./guide-card.mjs').AllSourcesView|null} allSources
   * @param {readonly string[]} resolvedSourceCodes
   */
  const renderRaceDetail = (
    raceId,
    card,
    personalized,
    labels,
    allSources,
    resolvedSourceCodes,
  ) => {
    const race = raceDataById.get(raceId);
    const selectedTotal = resolvedSourceCodes.length;
    const auditedDetailEl = /** @type {HTMLElement|null} */ (
      card.querySelector('[data-lens-detail-audited]')
    );
    if (auditedDetailEl) {
      auditedDetailEl.hidden = allSources === null;
      if (allSources !== null) applyAllSourcesSignal(auditedDetailEl, allSources);
    }
    const resolvedSet = new Set(resolvedSourceCodes);
    const standingByCandidateId = new Map(
      personalized.standings.map((item) => [item.candidateId, item]),
    );
    const soleLeaderId =
      personalized.grade !== 'Insufficient' && !personalized.isTied ? personalized.winnerId : null;
    // Ticket #141 item 1: the dialog's candidate order must follow whichever
    // result is currently displayed, not the audited default baked into the
    // server-rendered order. `standings` is already sorted leader-first by the
    // personalized support (lens-score.mjs), so it directly supplies that order;
    // any candidate with no personalized standing at all (one whose only
    // endorsers are deselected under the active lens) keeps its original
    // relative position, appended after every scored candidate.
    const standingOrder = personalized.standings.map((item) => item.candidateId);
    const standingOrderSet = new Set(standingOrder);
    const defaultOrder = defaultCandidateOrderByRaceId.get(raceId) ?? [];
    applyCandidateOrder(card, [
      ...standingOrder,
      ...defaultOrder.filter((candidateId) => !standingOrderSet.has(candidateId)),
    ]);
    let soleLeaderContributingCount = 0;
    for (const section of /** @type {NodeListOf<HTMLElement>} */ (
      card.querySelectorAll('[data-race-detail-candidate-id]')
    )) {
      const candidateId = /** @type {string} */ (section.dataset.raceDetailCandidateId);
      const isLeader = personalized.winnerIds.includes(candidateId);
      const contributingCells = (race?.cells ?? []).filter(
        (cell) => resolvedSet.has(cell.source_code) && candidateId in cell.allocation,
      );
      const contributingCount = contributingCells.length;
      const hasSplit = contributingCells.some((cell) => cell.state === 'multi_endorsement');

      const kickerEl = /** @type {HTMLElement|null} */ (
        section.querySelector('[data-race-detail-lens-kicker]')
      );
      if (kickerEl) {
        kickerEl.hidden = !isLeader;
        const leaderStatus = personalized.isTied ? 'Tied for lead' : 'Leading choice';
        kickerEl.textContent = `${hasNoMajority(personalized.winnerShare) ? 'No majority · ' : ''}${leaderStatus}`;
      }
      const countEl = section.querySelector('[data-race-detail-lens-count]');
      if (countEl) {
        const noun = contributingCount === 1 ? 'source' : 'sources';
        countEl.textContent =
          candidateId === soleLeaderId
            ? `${contributingCount} of ${personalized.explicitCount} endorsing sources` +
              (hasSplit ? ' (co-endorsements split)' : '')
            : `${contributingCount} endorsing ${noun}`;
      }
      if (candidateId === soleLeaderId) soleLeaderContributingCount = contributingCount;
      const lensMeterEl = /** @type {HTMLElement|null} */ (
        section.querySelector('[data-race-detail-lens-meter]')
      );
      if (lensMeterEl) {
        lensMeterEl.hidden = !isLeader;
        if (isLeader) {
          const share = standingByCandidateId.get(candidateId)?.share ?? null;
          const label = applyMeterFill(lensMeterEl, share);
          const lensMeterTextEl = lensMeterEl.querySelector('[data-race-detail-lens-meter-text]');
          if (lensMeterTextEl) lensMeterTextEl.textContent = label;
        }
      }
      // I56: unselected sources stay in place as evidence, visibly de-emphasized
      // and marked as not counted, rather than removed.
      for (const row of /** @type {NodeListOf<HTMLElement>} */ (
        section.querySelectorAll('[data-endorsed-candidate-id]')
      )) {
        const notCounted = !resolvedSet.has(
          /** @type {string} */ (row.dataset.raceDetailSourceCode),
        );
        row.classList.toggle('race-detail-source-row-not-counted', notCounted);
        const notCountedEl = /** @type {HTMLElement|null} */ (
          row.querySelector('[data-race-detail-not-counted]')
        );
        if (notCountedEl) {
          notCountedEl.hidden = !notCounted;
          notCountedEl.textContent = notCounted ? 'Not counted' : '';
        }
      }
    }
    // Ticket #141 item 5: the dialog's aria-describedby summary is rendered
    // server-side once, from the audited default. Every other lens-aware dialog
    // field is recomputed above, but this visually-hidden one was not, so it
    // silently disagreed with the visible numbers for screen-reader users while
    // a lens was active. Recompute it the same way here.
    const summaryEl = card.querySelector('[data-race-detail-summary]');
    if (summaryEl) {
      summaryEl.textContent = raceDetailAccessibleSummary(
        personalized,
        labels,
        selectedTotal,
        soleLeaderContributingCount,
      );
    }
  };

  /**
   * Put the page back to the audited default.
   *
   * The card regions are re-rendered only if lit ever took them over: until
   * then the server's own markup is still there and is already this, which is
   * the whole of what "the default audited view does zero DOM work" buys. The
   * dialog's order and summary are restored unconditionally, exactly as before
   * — that half is #136's to delete, and this ticket does not change when it
   * runs.
   */
  const restoreAudited = () => {
    raceCards.forEach((card, raceId) => {
      if (cardsTakenOver) {
        const audited = auditedByRaceId.get(raceId);
        if (audited) renderCard(card, cardViews(raceId, audited, null, null));
      }
      applyCandidateOrder(card, defaultCandidateOrderByRaceId.get(raceId) ?? []);
      const summaryEl = card.querySelector('[data-race-detail-summary]');
      if (summaryEl) summaryEl.textContent = defaultAccessibleSummaryByRaceId.get(raceId) ?? '';
    });
  };

  return {
    render(selectedCodes) {
      const { selected, personalized } = countedSelection(tallyingCodes, selectedCodes);
      root.classList.toggle('lens-personalized', personalized);
      if (!personalized) {
        // A lens that no longer applies (every source reselected) must restore
        // the audited default's own values, candidate order, and accessible
        // summary — nothing else runs once !personalized, so without this a
        // prior lens's arrangement would linger after it clears.
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
        renderRaceDetail(raceId, card, scored, labels, allSources, results.sourceCodes);
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
