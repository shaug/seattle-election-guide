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
// audited value and an empty `[data-lens-only]` sibling, and CSS chose between
// them on `html.lens-personalized`. One element now carries whichever value is
// current, because the template that renders the audited view model and the
// template that renders the personalized one are the same template. That is
// what `guide-markup-parity.test.mjs` checks, and it is the only reason the
// audited restore can be a render rather than a saved copy of the server's
// markup.
//
// Pure in the guard's sense and in the useful sense: view model in, template
// out. Every string it renders comes from `guide-format.mjs`, which mirrors
// `rendering/renderer.py` and is tested against it.

import { html, nothing } from 'lit-html';

/**
 * The share meter, as both renderers describe it.
 *
 * `fillPercent` is null exactly when there is no share to show: the audited
 * template writes no `style` attribute in that case, so neither may this one.
 *
 * @typedef {object} ShareMeterView
 * @property {string} label
 * @property {number|null} fillPercent
 * @property {boolean} lowFill
 * @property {boolean} noMajority
 * @property {string} accessibleLabel
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
 * The meter's class list, in the order the audited template writes it.
 *
 * Every decision here is already made in the view model, which the dialog's own
 * meter shares, so the card and the dialog cannot render one share two ways
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
    (meter.lowFill ? ' meter-low-fill' : '')
  );
}

/**
 * The reference bar's tone class, and its spoken label.
 *
 * Both live here, beside the view model they read, because the card renders
 * this bar through lit and the dialog still writes its copy by hand. Two
 * elements report the same agreement about the same race at the same moment,
 * and the tint is never the only carrier (G26/G27) — so the wording is the part
 * that must not drift, and it has one definition.
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
  ><strong>${meter.label}</strong></div>`;
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
