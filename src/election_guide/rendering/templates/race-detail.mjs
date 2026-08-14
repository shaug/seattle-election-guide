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
import { candidateMeterTemplate } from './guide-card.mjs';

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
 * `kicker` is non-null on exactly the tied leaders, which is what the audited
 * template expresses by rendering it for nobody else.
 *
 * `inHeadline` marks the one candidate the page headline already names, which
 * is the sole leader when there is one. That section renders no heading at all,
 * because the headline is its heading and a page names a candidate once. A tie
 * has no such candidate: every tied leader renders here instead, each with the
 * `kicker` that marks it, and none of them in the headline's green.
 *
 * `meter` is this candidate's own section meter — the race's own headline
 * meter retired, and every candidate's section gained one of its own instead
 * (docs/METER_V2.md, Chrome geometry: "The headline meter's own fate"; #325).
 * v1's per-candidate mini-meter used to sit beside the tied-leader kicker;
 * meter v2 retired that chrome, and #315's shared-bar candidate-context
 * treatment that was meant to replace its job shipped, then was found
 * information-design incoherent and unshipped — this section's own static
 * meter is what #325 settled on instead.
 *
 * `resultChipLabel` is this candidate's certified outcome chip
 * (docs/RESULTS.md, Rendering § The race-detail page; #287), or null — no
 * results cover this race or this candidate, or the outcome is a trailing
 * one, which carries no chip. All three render nothing. It is the whole of a
 * result a section renders: the share and its bar belong to the page's own
 * complete RESULT block, above the lens bar and outside every lens region,
 * which the server renders once and this module never sees (#370).
 * Selection-independent, so it is a static passthrough from the payload
 * rather than something this module computes — the same reason `rows` above
 * carries every value its markup needs instead of reading it back off the
 * server's copy (docs/FRONTEND.md, The data contract).
 *
 * @typedef {object} CandidateSectionView
 * @property {string} candidateId
 * @property {string} label
 * @property {boolean} isLeader
 * @property {boolean} inHeadline
 * @property {string|null} kicker
 * @property {import('./guide-card.mjs').CandidateMeterView} meter
 * @property {readonly SourceRowView[]} rows
 * @property {string|null} resultChipLabel
 */

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
 * One candidate's own meter row: the section-scoped meter itself, left, and
 * the count/percent label the meter no longer carries beside it, right
 * (docs/METER_V2.md, Resting label; #325).
 *
 * @param {CandidateSectionView} candidate
 */
function candidateMeterRowTemplate(candidate) {
  const { meter } = candidate;
  return html`<div class="race-detail-candidate-meter"
    >${candidateMeterTemplate(candidate.candidateId, meter)}<span
      class="race-detail-candidate-count"
    ><b>${meter.countLabel}</b> of ${meter.totalLabel} endorsements<span
      class="race-detail-candidate-pct"
    >${meter.percentageLabel}</span></span></div>`;
}

/**
 * The results chip (docs/RESULTS.md, "The results chip"; #287), immediately
 * after a candidate's name in whichever heading names them. Null when there
 * is no chip to render — a trailing outcome, or no result at all.
 *
 * @param {string|null} chipLabel
 */
function resultChipTemplate(chipLabel) {
  if (chipLabel === null) return nothing;
  return html` <span class="race-detail-result-chip">${chipLabel}</span>`;
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
  ><div class="race-detail-candidate-heading">${
    candidate.inHeadline
      ? nothing
      : html`<div class="race-detail-candidate-title">${
          candidate.kicker === null ? nothing : html`<p>${candidate.kicker}</p>`
        }<h4>${candidate.label}${resultChipTemplate(candidate.resultChipLabel)}</h4></div>`
  }${candidateMeterRowTemplate(candidate)}</div><ul class="race-detail-source-list">${repeat(
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
