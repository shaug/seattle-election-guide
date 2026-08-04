// A race page's candidate sections, as lit-html templates over view-model
// state (docs/FRONTEND.md § Rendering).
//
// The region is `[data-race-candidates]`: every candidate who was endorsed,
// each with the rows of the sources that endorsed them. The listings below it —
// no endorsement, needs verification, and the collapsed "did not cover this
// race" — are not a projection of the reader's selection (a deselected source
// still did not cover the race), so they stay exactly as the server rendered
// them and lit never touches them.
//
// Written lit-native rather than ported. The dialog this replaced rendered the
// same content imperatively — reordering server sections, patching text nodes,
// toggling twin elements — and docs/FRONTEND.md § Adoption's sequencing rule
// says this ticket writes its rendering on the lit foundation instead of
// carrying that renderer forward.
//
// Pure: view model in, template out.

import { html, nothing } from 'lit-html';
import { repeat } from 'lit-html/directives/repeat.js';

/**
 * One endorsing source's row, as the payload publishes it plus whether the
 * reader's current selection counts it.
 *
 * Everything except `notCounted` is carried by `RaceSourceRow`, because a
 * client that renders markup needs every value that markup carries and reads
 * none of it back out of the server's copy (docs/FRONTEND.md, The data
 * contract).
 *
 * @typedef {object} SourceRowView
 * @property {string} code
 * @property {string} name
 * @property {string} category
 * @property {string} categoryLabel
 * @property {string} state
 * @property {string} panelRole
 * @property {string|null} detailLabel
 * @property {string|null} evidenceUrl
 * @property {boolean} notCounted
 */

/**
 * One candidate's section.
 *
 * `meter` and `kicker` are non-null on exactly the tied leaders, which is what
 * the audited template expresses by rendering neither for anyone else: a share
 * is worth stating in a heading only where it is contested.
 *
 * `inHeadline` marks the one candidate the page headline already names, which
 * is the sole leader when there is one. That section renders no heading at all,
 * because the headline is its heading and a page names a candidate once. A tie
 * has no such candidate: every tied leader renders here instead, each with the
 * `kicker` and `meter` that mark it, and none of them in the headline's green.
 *
 * No section carries a count. The sources that endorsed this candidate are the
 * rows directly below the heading, so a number naming how many of them there
 * are would restate the list it sits on.
 *
 * @typedef {object} CandidateSectionView
 * @property {string} candidateId
 * @property {string} label
 * @property {boolean} isLeader
 * @property {boolean} inHeadline
 * @property {string|null} kicker
 * @property {import('./guide-card.mjs').ShareMeterView|null} meter
 * @property {readonly SourceRowView[]} rows
 */

/**
 * The per-candidate meter's class list, in the order the audited template
 * writes it.
 *
 * A second chrome from the same view model as the headline meter's
 * (`guide-card.mjs`), not a second policy: whether a share is absent, low, or
 * short of a majority is decided once, so the two meters on a race page cannot
 * disagree about one number (I56).
 *
 * @param {import('./guide-card.mjs').ShareMeterView} meter
 * @returns {string}
 */
function detailMeterClasses(meter) {
  if (meter.fillPercent === null) return 'race-detail-meter race-detail-meter-na';
  return (
    'race-detail-meter' +
    (meter.noMajority ? ' meter-no-majority' : '') +
    (meter.lowFill ? ' meter-low-fill' : '')
  );
}

/**
 * @param {import('./guide-card.mjs').ShareMeterView} meter
 */
function detailMeterTemplate(meter) {
  return html`<div
    class=${detailMeterClasses(meter)}
    style=${meter.fillPercent === null ? nothing : `--meter-fill: ${meter.fillPercent}%`}
    role="img"
    aria-label=${meter.accessibleLabel}
  ><strong>${meter.label}</strong></div>`;
}

/**
 * The row's interior, which is a link exactly when there is a receipt to link.
 *
 * @param {SourceRowView} row
 */
function sourceRowBody(row) {
  const meta = html`<div class="race-detail-source-meta"><span
      class="race-detail-category-badge"
    >${row.categoryLabel}</span>${
      row.detailLabel === null
        ? nothing
        : html`<span class="race-detail-source-status">${row.detailLabel}</span>`
    }${
      // I56: an unselected source's row stays in place as evidence, marked as
      // not counted rather than removed. It is rendered only when it applies,
      // rather than shipped empty and revealed — the empty twin the audited
      // markup used to carry is exactly what a lit region removes the need for
      // (docs/FRONTEND.md § Rendering, "one element per value, not a pair").
      row.notCounted
        ? html`<span class="race-detail-source-not-counted">Not counted</span>`
        : nothing
    }</div>`;
  const inner = html`<strong>${row.name}</strong>${meta}`;
  return row.evidenceUrl === null
    ? html`<div class="race-detail-source-row">${inner}</div>`
    : html`<a
        class="race-detail-source-row"
        href=${row.evidenceUrl}
        target="_blank"
        rel="noopener"
      >${inner}</a>`;
}

/**
 * @param {string} candidateId
 * @param {SourceRowView} row
 */
function sourceRowTemplate(candidateId, row) {
  return html`<li
    data-race-detail-source-code=${row.code}
    data-source-category=${row.category}
    data-source-state=${row.state}
    data-source-role=${row.panelRole}
    data-source-group="candidate"
    data-endorsed-candidate-id=${candidateId}
    class=${row.notCounted ? 'race-detail-source-row-not-counted' : nothing}
  >${sourceRowBody(row)}</li>`;
}

/**
 * @param {CandidateSectionView} candidate
 */
function candidateSectionTemplate(candidate) {
  return html`<section
    class=${
      candidate.inHeadline
        ? 'race-detail-candidate race-detail-candidate-leader race-detail-candidate-headlined'
        : candidate.isLeader
          ? 'race-detail-candidate race-detail-candidate-tied'
          : 'race-detail-candidate'
    }
    data-race-detail-candidate-id=${candidate.candidateId}
  >${
    candidate.inHeadline
      ? nothing
      : html`<div class="race-detail-candidate-heading"><div
            class="race-detail-candidate-title"
          >${
            candidate.kicker === null ? nothing : html`<p>${candidate.kicker}</p>`
          }<h4>${candidate.label}</h4></div>${
            candidate.meter === null
              ? nothing
              : html`<div class="race-detail-candidate-metrics">${detailMeterTemplate(
                  candidate.meter,
                )}</div>`
          }</div>`
  }<ul class="race-detail-source-list">${repeat(
    candidate.rows,
    (row) => row.code,
    (row) => sourceRowTemplate(candidate.candidateId, row),
  )}</ul></section>`;
}

/**
 * Every candidate section, in the order the current result puts them.
 *
 * Keyed by candidate id, because this is the one list on the page whose order
 * actually changes: a lens can promote a challenger past the audited leader,
 * and an unkeyed render would rebuild every section rather than move it
 * (docs/FRONTEND.md § Rendering).
 *
 * @param {readonly CandidateSectionView[]} candidates
 */
export function candidateSectionsTemplate(candidates) {
  return repeat(
    candidates,
    (candidate) => candidate.candidateId,
    (candidate) => candidateSectionTemplate(candidate),
  );
}
