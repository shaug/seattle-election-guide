// The guide's personalized rendering: every card and race-detail dialog while a
// lens is active.
//
// Moved verbatim out of guide.html.j2's module script by issue #239. It is
// still imperative DOM writing, deliberately: converting these two regions to
// lit-html templates is issue #248, which is blocked on this extraction, and
// doing both at once would make neither reviewable. The one change made here is
// that the audited presentation it needs — candidate labels, the audited
// candidate order, the audited accessible summary — arrives from the payload
// (issue #236) rather than being read back out of the dialog.
//
// Wiring, not a computing module: it holds element references and writes to
// them. The strings it writes come from `guide-format.mjs`, which is pure and
// tested against the Python renderer it mirrors.

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
import { isDefaultSelection } from './lens-selection.mjs';

/**
 * Shared meter-fill policy (I40/I41): the NA state, the `--meter-fill` custom
 * property, the low-fill label-placement guard, and the accessible label.
 *
 * One card-level meter (the race's personalized share) and every dialog
 * candidate's lens-only meter (I56) apply this exact policy, so it lives here
 * rather than being hand-copied — a change to one but not the other would
 * silently desynchronize the card and dialog meters. Returns the percentage
 * label so a caller whose text lives inside the meter can reuse it.
 *
 * @param {HTMLElement} meterEl
 * @param {string|null} shareString
 * @param {string} naClass
 * @returns {string}
 */
function applyMeterFill(meterEl, shareString, naClass) {
  const label = percentageLabel(shareString);
  const fillPercent = shareString === null ? null : Number.parseInt(label, 10);
  meterEl.classList.toggle(naClass, shareString === null);
  // I41: below ~30% fill the white label bleeds onto the pale track; below that
  // threshold the low-fill guard (guide.css) renders it after the fill in muted
  // ink instead.
  meterEl.classList.toggle('meter-low-fill', fillPercent !== null && fillPercent < 30);
  meterEl.classList.toggle('meter-no-majority', hasNoMajority(shareString));
  meterEl.style.setProperty('--meter-fill', shareString === null ? '0%' : label);
  meterEl.setAttribute('aria-label', shareAccessibleLabel(shareString));
  return label;
}

/**
 * The full-panel baseline in a quiet info-bar with an agree/differ tone:
 * "differs" means the leading choice itself changed, not merely its share
 * (issue 115, G24–G27). The tint is never the only carrier — the aria-label
 * states the agreement in words.
 *
 * @param {Element} element
 * @param {import('./lens-score.mjs').RaceScore} audited
 * @param {ReadonlyMap<string, string>} labels
 * @param {boolean} leaderChanged
 */
function applyAllSourcesSignal(element, audited, labels, leaderChanged) {
  const summary = allSourcesSummary(audited, labels);
  element.textContent = summary;
  element.classList.toggle('lens-comparison-differs', leaderChanged);
  element.classList.toggle('lens-comparison-agrees', !leaderChanged);
  element.setAttribute(
    'aria-label',
    `${leaderChanged ? 'All sources differ from your selection' : 'All sources agree with your selection'}. ${summary}`,
  );
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
 *   selection to the whole page.
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
  const lensBanner = document.querySelector('[data-lens-banner]');
  const lensBannerStatus = document.querySelector('[data-lens-banner-status]');
  const tallyingCodes = payload.sources
    .filter((source) => source.panel_role !== 'comparison')
    .map((source) => source.code);

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
   * Apply one race's personalized result to its card and detail dialog.
   *
   * The personalized recommendation, share, source count, and insufficient-
   * evidence state always render while a lens is active; the compact audited
   * comparison and the dialog's own audited reference line render only when this
   * race actually diverges, so an unchanged race stays free of redundant
   * audited detail.
   *
   * @param {string} raceId
   * @param {Element} card
   * @param {ReadonlyMap<string, import('./lens-score.mjs').RaceScore>} personalizedByRaceId
   * @param {readonly string[]} resolvedSourceCodes
   */
  const renderRaceLens = (raceId, card, personalizedByRaceId, resolvedSourceCodes) => {
    const personalized = personalizedByRaceId.get(raceId);
    const audited = auditedByRaceId.get(raceId);
    if (!personalized || !audited) return;
    const labels = candidateLabelsByRaceId.get(raceId) ?? new Map();
    const divergence = compareRaceResults(audited, personalized);

    const recommendationEl = card.querySelector('[data-lens-recommendation]');
    if (recommendationEl) recommendationEl.textContent = recommendationLabel(personalized, labels);
    const shareEl = card.querySelector('[data-lens-share-text]');
    if (shareEl) shareEl.textContent = percentageLabel(personalized.winnerShare);
    const shareMeter = /** @type {HTMLElement|null} */ (card.querySelector('[data-lens-share]'));
    if (shareMeter) applyMeterFill(shareMeter, personalized.winnerShare, 'screen-meter-na');
    const noMajorityEl = /** @type {HTMLElement|null} */ (
      card.querySelector('[data-lens-no-majority]')
    );
    if (noMajorityEl) noMajorityEl.hidden = !hasNoMajority(personalized.winnerShare);
    const selectedTotal = resolvedSourceCodes.length;
    const supportEl = card.querySelector('[data-lens-support]');
    if (supportEl) supportEl.textContent = supportSummary(personalized, selectedTotal);
    const supportCompactEl = card.querySelector('[data-lens-support-compact]');
    if (supportCompactEl) {
      supportCompactEl.textContent = supportSummaryCompact(personalized, selectedTotal);
    }
    const insufficientEl = /** @type {HTMLElement|null} */ (
      card.querySelector('[data-lens-insufficient]')
    );
    if (insufficientEl) insufficientEl.hidden = personalized.grade !== 'Insufficient';
    const comparisonEl = /** @type {HTMLElement|null} */ (
      card.querySelector('[data-lens-comparison]')
    );
    if (comparisonEl) {
      comparisonEl.hidden = !divergence.anyChanged;
      if (divergence.anyChanged) {
        applyAllSourcesSignal(comparisonEl, audited, labels, divergence.leader);
      }
    }
    const race = raceDataById.get(raceId);

    // Race detail: I56 — every computed number in the dialog (per-candidate
    // counts, shares, meters, and the leading-choice kicker) must equal the lens
    // numbers on the main page while a lens is active; no quantity may appear
    // with two values. Unselected sources stay visible as evidence, marked as
    // not counted, rather than hidden.
    const auditedDetailEl = /** @type {HTMLElement|null} */ (
      card.querySelector('[data-lens-detail-audited]')
    );
    if (auditedDetailEl) {
      auditedDetailEl.hidden = !divergence.anyChanged;
      if (divergence.anyChanged) {
        applyAllSourcesSignal(auditedDetailEl, audited, labels, divergence.leader);
      }
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
          const label = applyMeterFill(lensMeterEl, share, 'race-detail-meter-na');
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

  return {
    render(selectedCodes) {
      const tallyingSelection = tallyingCodes.filter((code) => selectedCodes.includes(code)).sort();
      const personalized = !isDefaultSelection(tallyingSelection, tallyingCodes);
      root.classList.toggle('lens-personalized', personalized);
      if (lensBanner instanceof HTMLElement) lensBanner.hidden = false;
      if (lensBannerStatus) {
        lensBannerStatus.textContent = countingSummary(
          tallyingSelection.length,
          tallyingCodes.length,
          personalized,
        );
      }
      if (!personalized) {
        // A lens that no longer applies (every source reselected) must restore
        // the audited default's own candidate order and accessible summary —
        // nothing else runs renderRaceLens once !personalized, so without this a
        // prior lens's arrangement would linger after it clears.
        raceCards.forEach((card, raceId) => {
          applyCandidateOrder(card, defaultCandidateOrderByRaceId.get(raceId) ?? []);
          const summaryEl = card.querySelector('[data-race-detail-summary]');
          if (summaryEl) summaryEl.textContent = defaultAccessibleSummaryByRaceId.get(raceId) ?? '';
        });
        return;
      }
      const results = scoreSelection(personalization, {
        categoryCodes: [],
        sourceCodes: tallyingSelection,
      });
      const personalizedByRaceId = new Map(results.races.map((race) => [race.raceId, race]));
      raceCards.forEach((card, raceId) => {
        renderRaceLens(raceId, card, personalizedByRaceId, results.sourceCodes);
      });
    },
  };
}
