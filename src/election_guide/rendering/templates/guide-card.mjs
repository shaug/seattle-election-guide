// The race card's lens-aware markup, as lit-html templates over view-model
// state (docs/FRONTEND.md § Rendering).
//
// Three regions, one per element the server already renders as a container:
//
//   result   `.screen-race-result` — the recommendation and the share meter.
//   context  `.screen-race-context` — the no-majority pill and both captions.
//   foot     `.race-card-foot` — the insufficiency note and the All-sources
//            reference bar, the two blocks that sit below the card's link.
//
// Each one replaced a pair of twin elements: the server used to render the
// audited value and an empty lens-only sibling beside it, and CSS chose between
// them on `html.lens-personalized`. One element now carries whichever value is
// current, because the template that renders the audited view model and the
// template that renders the personalized one are the same template. That is
// what `guide-markup-parity.test.mjs` checks, and it is the only reason the
// audited restore can be a render rather than a saved copy of the server's
// markup.
//
// Pure in the guard's sense and in the useful sense: view model in, template
// out. Every string it renders comes from `guide-format.mjs`, which mirrors
// `rendering/context.py` and is tested against it.

import { html, nothing } from 'lit-html';
import { hasNoMajority, percentageLabel } from './guide-format.mjs';
import { Rational } from './lens-score.mjs';
import {
  meterAccessibleLabel,
  meterBlockRenders,
  meterCandidateChips,
  meterCandidateColors,
  meterCandidateLabels,
  meterLayoutBlocks,
  meterStandings,
  meterUnits,
} from './meter-layout.mjs';

// Minimum block width (docs/METER_V2.md, Edge states): below ~3px per block,
// per-block seams drop and the meter degrades to plain candidate runs.
// Mirrors `_METER_DEGRADE_MAX_BLOCKS` in `rendering/context.py` — see that
// constant for why one conservative threshold covers every chrome.
const METER_DEGRADE_MAX_BLOCKS = Math.floor(120 / 3);

/**
 * The segmented meter, as both renderers describe it (docs/METER_V2.md).
 *
 * `fillPercent` is null exactly when there is no share to show — the N/A
 * state — in which case `blocks` is empty and the audited template writes no
 * `style` attribute, so neither may this one.
 *
 * @typedef {object} ShareMeterView
 * @property {string} label
 * @property {number|null} fillPercent
 * @property {boolean} lowFill
 * @property {boolean} noMajority
 * @property {boolean} degraded
 * @property {string} accessibleLabel
 * @property {import('./meter-layout.mjs').MeterBlockRender[]} blocks
 * @property {import('./meter-layout.mjs').MeterCandidateChip[]} chips Empty
 *   for the N/A state. Only the race page renders these today (docs/METER_V2.md,
 *   the mockup's chips section; #315); every other chrome computes and ignores them,
 *   the same way it already ignores fields it has no use for.
 */

/**
 * @typedef {object} RaceResultView
 * @property {string} recommendation
 * @property {ShareMeterView} meter
 */

/**
 * @typedef {object} RaceContextView
 * @property {boolean} noMajority
 * @property {string} support
 * @property {string} supportCompact
 */

/**
 * The All-sources reference bar (G26/G27): a quiet info bar whose tint states
 * agreement and whose label states it in words, because the tint is never the
 * only carrier.
 *
 * @typedef {object} AllSourcesView
 * @property {string} summary
 * @property {boolean} leaderChanged
 */

/**
 * @typedef {object} RaceFootView
 * @property {string|null} insufficientNote
 * @property {AllSourcesView|null} allSources
 */

/**
 * One share, as every meter v2 chrome describes it (docs/METER_V2.md).
 *
 * One policy for the NA state, the fill percentage, the low-fill guard, the
 * no-majority tone, the block layout, and the accessible label, because a
 * card meter and a race page's headline meter must never disagree about the
 * same share (I40/I41/I56). It lives here, beside `ShareMeterView`, rather
 * than in either page's wiring, so both pages read one definition.
 *
 * `shareString` is the winner's own share (the resting percent); `endorsements`
 * is this race's `MeterEndorsement[]`, built by the caller from whichever
 * source it has — the audited card's own cells, or the personalized cells a
 * lens selects; `leaderIds` is the tie-aware leader set (`support_leader_
 * candidate_ids` server-side, `RaceScore.winnerIds` client-side), which
 * decides each candidate's color the same way the race's own no-majority/tie
 * decision does (I56).
 *
 * @param {string|null} shareString
 * @param {import('./meter-layout.mjs').MeterEndorsement[]} endorsements
 * @param {ReadonlySet<string>} leaderIds
 * @returns {ShareMeterView}
 */
export function meterView(shareString, endorsements, leaderIds) {
  const label = percentageLabel(shareString);
  // The N/A state (docs/METER_V2.md, Edge states) is decided by `shareString`
  // alone and forces empty blocks and the N/A accessible name regardless of
  // what `endorsements` would otherwise lay out — the audited template's N/A
  // branch renders no blocks at all, so a view that claimed blocks anyway
  // would describe a meter no renderer draws.
  if (shareString === null) {
    return {
      label,
      fillPercent: null,
      lowFill: false,
      noMajority: false,
      degraded: false,
      accessibleLabel: 'No endorsements recorded',
      blocks: [],
      chips: [],
    };
  }
  const fillPercent = Number.parseInt(label, 10);
  const noMajority = hasNoMajority(shareString);
  const standings = meterStandings(endorsements);
  const units = meterUnits(endorsements);
  const labels = meterCandidateLabels(endorsements);
  const colors = meterCandidateColors(standings, leaderIds, !noMajority);
  const blocks = meterLayoutBlocks(endorsements);
  return {
    label,
    fillPercent,
    // I41: below ~30% fill the white label bleeds onto the pale track, so the
    // low-fill guard (guide-race.css) renders it after the resting run
    // instead. Decided once, here, because one CSS rule applies the guard to
    // every meter chrome.
    lowFill: fillPercent < 30,
    noMajority,
    degraded: blocks.length > METER_DEGRADE_MAX_BLOCKS,
    accessibleLabel: meterAccessibleLabel(standings, units, labels),
    blocks: meterBlockRenders(blocks, colors, labels),
    chips: meterCandidateChips(standings, units, labels, colors),
  };
}

/**
 * The recommended choice's exact endorsement tally, for the caption
 * (docs/METER_V2.md, Caption). Mirrors `_meter_leader_units` in
 * `rendering/context.py` — `null` when there is no single choice to
 * attribute it to (a tie, or no winner), matching that function's own guard.
 *
 * @param {import('./lens-score.mjs').RaceScore} scored
 * @param {import('./meter-layout.mjs').MeterEndorsement[]} endorsements
 * @returns {import('./lens-score.mjs').Rational|null}
 */
export function meterLeaderUnits(scored, endorsements) {
  if (scored.isTied || scored.winnerId === null) return null;
  return meterUnits(endorsements).get(scored.winnerId) ?? Rational.zero();
}

/**
 * The meter's class list, in the order the audited template writes it.
 *
 * Every decision here is already made in `meterView`, which a race page's own
 * meter reads too, so no two meters on the site can render one share two ways
 * (I56).
 *
 * @param {ShareMeterView} meter
 * @returns {string}
 */
function meterClasses(meter) {
  if (meter.fillPercent === null) return 'screen-meter screen-meter-na';
  return (
    'screen-meter' +
    (meter.noMajority ? ' meter-no-majority' : '') +
    (meter.lowFill ? ' meter-low-fill' : '') +
    (meter.degraded ? ' meter-degraded' : '')
  );
}

/**
 * One block's class list, in the order the audited template writes it.
 *
 * @param {import('./meter-layout.mjs').MeterBlockRender} block
 * @returns {string}
 */
function meterBlockClasses(block) {
  return (
    `meter-block meter-block-${block.type}` +
    (block.tongue_corner_start ? ' meter-tongue-start' : '') +
    (block.tongue_corner_end ? ' meter-tongue-end' : '')
  );
}

/**
 * One block: a bare presentational rectangle (docs/METER_V2.md, The
 * discovery model's accessibility model — blocks carry no ARIA of their own),
 * with the source and decision a hover or focus tooltip reads from its data
 * attributes rather than from static text, so the meter's spoken text stays
 * exactly the resting percent (or "N/A") and nothing more.
 *
 * @param {import('./meter-layout.mjs').MeterBlockRender} block
 */
function meterBlockTemplate(block) {
  return html`<span
    class=${meterBlockClasses(block)}
    style=${block.style}
    data-meter-source=${block.source_label}
    data-meter-decision=${block.decision}
    data-meter-candidates=${block.candidate_ids.join(',')}
  >${
    block.type === 'split'
      ? html`<span class="meter-half meter-half-top"></span><span
          class="meter-half meter-half-bottom"
        ></span>`
      : nothing
  }</span>`;
}

/**
 * The reference bar's tone class, and its spoken label.
 *
 * Both live here, beside the view model they read, because the card and a race
 * page's headline render the same bar about the same race, and the tint is
 * never the only carrier (G26/G27) — so the wording is the part that must not
 * drift, and it has one definition.
 *
 * @param {boolean} leaderChanged
 * @returns {string}
 */
export function allSourcesToneClass(leaderChanged) {
  return leaderChanged ? 'lens-comparison-differs' : 'lens-comparison-agrees';
}

/**
 * @param {AllSourcesView} view
 * @returns {string}
 */
export function allSourcesAccessibleLabel(view) {
  const agreement = view.leaderChanged
    ? 'All sources differ from your selection'
    : 'All sources agree with your selection';
  return `${agreement}. ${view.summary}`;
}

/**
 * The card's primary block: the headline result and the share meter.
 *
 * @param {RaceResultView} view
 */
export function raceResultTemplate(view) {
  const { meter } = view;
  return html`<h3 data-display-role="recommendation">${view.recommendation}</h3><div
    class=${meterClasses(meter)}
    style=${meter.fillPercent === null ? nothing : `--meter-fill: ${meter.fillPercent}%`}
    role="img"
    data-display-role="share"
    aria-label=${meter.accessibleLabel}
    tabindex="0"
  >${
    meter.fillPercent === null
      ? html`<strong>N/A</strong>`
      : html`${meter.blocks.map(meterBlockTemplate)}<strong>${meter.label}</strong>`
  }</div>`;
}

/**
 * The caption block directly under the meter row (I39).
 *
 * Both captions always render; `.support-compact` and `.support-full` are
 * chosen by `html.compact-ballot-mode` in CSS, not by this template, so a
 * ballot-view change does not need a re-render.
 *
 * @param {RaceContextView} view
 */
export function raceContextTemplate(view) {
  return html`<p class="no-majority-pill" ?hidden=${!view.noMajority}>No majority</p><p
    class="support-line support-full"
    data-display-role="support"
  >${view.support}</p><p
    class="support-line support-compact"
    data-display-role="support"
  >${view.supportCompact}</p>`;
}

/**
 * The card foot (I39): the insufficiency note, then the All-sources reference
 * bar, never interleaved with the caption above.
 *
 * Both are absent from the audited default unless the audited grade is itself
 * Insufficient — which is why the server renders nothing here for most cards,
 * and why this template renders nothing for them too. A bare `<p>` is
 * name-prohibited in ARIA, so the agree/differ label needs `role="group"` to
 * be exposed.
 *
 * @param {RaceFootView} view
 */
export function raceFootTemplate(view) {
  return html`${
    view.insufficientNote === null
      ? nothing
      : html`<div class="insufficient-note" role="note" data-display-role="insufficient-warning"
        >${view.insufficientNote}</div>`
  }${
    view.allSources === null
      ? nothing
      : html`<p
          class=${`lens-comparison ${allSourcesToneClass(view.allSources.leaderChanged)}`}
          role="group"
          aria-label=${allSourcesAccessibleLabel(view.allSources)}
        >${view.allSources.summary}</p>`
  }`;
}
