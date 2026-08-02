// The Comparisons table's markup, as lit-html templates over view-model state
// (docs/FRONTEND.md § Rendering).
//
// This module is pure in the guard's sense and in the useful sense: it names no
// environment identifier, holds no state, and reads nothing out of the DOM. It
// receives a view model and a set of callbacks and returns a template. That is
// what lets `compare-markup-parity.test.mjs` render the body with the audited
// view model in a lightweight DOM and diff the result against the region the
// Jinja template rendered — the two must agree, so neither side may drift.
//
// The head is deliberately not part of that parity claim. It carries the column
// controls, which the audited baseline cannot render without advertising
// buttons that do nothing without JavaScript; the server renders the same
// column labels as static text instead. § Rendering records the boundary.

import { html, nothing } from 'lit-html';
import { repeat } from 'lit-html/directives/repeat.js';

/**
 * One option in a column picker.
 *
 * @typedef {object} ComparisonOptionView
 * @property {string} value
 * @property {string} label
 * @property {boolean} selected
 * @property {boolean} disabled
 */

/**
 * @typedef {object} ComparisonOptionGroupView
 * @property {string} label
 * @property {ComparisonOptionView[]} options
 */

/**
 * One column heading. `editing` is state, not DOM: the picker replaces the
 * title because the view model says so, never because a handler swapped nodes.
 *
 * @typedef {object} ComparisonColumnView
 * @property {string} signal
 * @property {number} index
 * @property {string} title
 * @property {string} controlLabel
 * @property {boolean} editing
 * @property {ComparisonOptionGroupView[]} groups
 * @property {string|null} removeLabel
 * @property {boolean} canAdd
 */

/**
 * @typedef {object} ComparisonHeadView
 * @property {ComparisonColumnView[]} columns
 */

/**
 * What the head's controls do. Held apart from the view model so the template
 * stays data-in, markup-out.
 *
 * @typedef {object} ComparisonHeadActions
 * @property {(index: number) => void} onEdit
 * @property {(index: number, value: string) => void} onChoose
 * @property {(index: number) => void} onCancel
 * @property {(index: number) => void} onDismiss
 * @property {(index: number) => void} onRemove
 * @property {() => void} onAdd
 */

/**
 * One rendered cell. Every field the server projects onto the cell is carried
 * here, because the client's markup for a region must be the server's markup
 * for that region.
 *
 * @typedef {object} ComparisonCellView
 * @property {string} signal
 * @property {string} columnLabel
 * @property {string} kind
 * @property {string} agreement
 * @property {readonly string[]} leadingPickIds
 * @property {string|null} share
 * @property {number|null} explicitSourceCount
 * @property {readonly string[]} choiceLabels
 * @property {string|null} meta
 */

/**
 * @typedef {object} ComparisonRowView
 * @property {string} raceId
 * @property {string} raceLabel
 * @property {string} raceHref
 * @property {boolean} differs
 * @property {ComparisonCellView[]} cells
 */

/**
 * @typedef {object} ComparisonSectionView
 * @property {string} sectionId
 * @property {string} sectionLabel
 * @property {ComparisonRowView[]} rows
 */

/**
 * @typedef {object} ComparisonEmptyView
 * @property {string} message
 * @property {string} action
 */

/**
 * @typedef {object} ComparisonBodyView
 * @property {ComparisonSectionView[]} sections
 * @property {number} columnCount
 * @property {ComparisonEmptyView|null} empty
 */

/**
 * The server writes this attribute with Python's `json.dumps`, whose default
 * item separator carries a space. Matching it here is not cosmetic: the parity
 * test compares attribute values, so a bare `JSON.stringify` would be a real
 * disagreement between the two renderings of the same cell.
 *
 * @param {readonly string[]} ids
 * @returns {string}
 */
function pickIdsAttribute(ids) {
  return `[${ids.map((id) => JSON.stringify(id)).join(', ')}]`;
}

/**
 * The picks line. Three shapes, exactly as the Jinja template writes them —
 * including the inner `<span title>` for a blank cell, which is what carries
 * the explanation to a pointer user.
 *
 * @param {ComparisonCellView} cell
 */
function picks(cell) {
  if (cell.kind === 'outside_scope') return html`Outside district`;
  if (cell.choiceLabels.length === 0) {
    return html`<span title="No endorsement published">&mdash;</span>`;
  }
  return html`${cell.choiceLabels.join(' / ')}`;
}

/** @param {ComparisonCellView} cell */
function cellTemplate(cell) {
  return html`<td
    class="comparison-cell"
    data-column-signal=${cell.signal}
    data-column-label=${cell.columnLabel}
    data-cell-kind=${cell.kind}
    data-agreement=${cell.agreement}
    data-leading-pick-ids=${pickIdsAttribute(cell.leadingPickIds)}
    data-share=${cell.share ?? nothing}
    data-explicit-source-count=${cell.explicitSourceCount ?? nothing}
  ><span class="comparison-cell-picks">${picks(cell)}</span>${
    cell.meta === null ? nothing : html`<span class="comparison-cell-meta">${cell.meta}</span>`
  }</td>`;
}

/** @param {ComparisonRowView} row */
function rowTemplate(row) {
  return html`<tr data-comparison-race=${row.raceId} data-row-differs=${String(row.differs)}
  ><th scope="row" class="comparison-race"><a href=${row.raceHref}>${row.raceLabel}</a>${
    row.differs ? html`<span class="comparison-race-differs">Differs</span>` : nothing
  }</th>${repeat(row.cells, (cell) => cell.signal, cellTemplate)}</tr>`;
}

/**
 * @param {ComparisonSectionView} section
 * @param {number} columnCount
 */
function sectionTemplate(section, columnCount) {
  return html`<tbody data-comparison-section=${section.sectionId}
  ><tr class="comparison-section-heading"><th scope="rowgroup" colspan=${columnCount + 1}>${
    section.sectionLabel
  }</th></tr>${repeat(section.rows, (row) => row.raceId, rowTemplate)}</tbody>`;
}

/**
 * The table's row groups.
 *
 * Rendered into the `<table>` itself, after the caption and head, which is
 * where a `<tbody>` belongs and which leaves the head's own render root alone.
 * Keys are the section and race identifiers, so a re-render that keeps a row
 * keeps that row's elements — the reason focus and scroll position survive a
 * filter change without anything being restored afterwards.
 *
 * @param {ComparisonBodyView} view
 * @param {() => void} onReset
 */
export function comparisonBodyTemplate(view, onReset) {
  if (view.empty !== null) {
    return html`<tbody><tr class="comparison-empty"><td colspan=${view.columnCount + 1}
      ><p>${view.empty.message}</p><button
        type="button"
        class="comparison-reset"
        @click=${onReset}
      >${view.empty.action}</button></td></tr></tbody>`;
  }
  return repeat(
    view.sections,
    (section) => section.sectionId,
    (section) => sectionTemplate(section, view.columnCount),
  );
}

/**
 * @param {ComparisonColumnView} column
 * @param {ComparisonHeadActions} actions
 */
function pickerTemplate(column, actions) {
  return html`<select
    class="comparison-column-picker"
    data-comparison-column=${String(column.index)}
    aria-label=${column.controlLabel}
    @change=${(/** @type {Event} */ event) => {
      actions.onChoose(column.index, /** @type {HTMLSelectElement} */ (event.target).value);
    }}
    @keydown=${(/** @type {KeyboardEvent} */ event) => {
      if (event.key !== 'Escape') return;
      event.preventDefault();
      event.stopPropagation();
      actions.onCancel(column.index);
    }}
    @blur=${() => actions.onDismiss(column.index)}
  >${repeat(
    column.groups,
    (group) => group.label,
    (group) =>
      html`<optgroup label=${group.label}>${repeat(
        group.options,
        (option) => option.value,
        (option) => html`<option
        value=${option.value}
        ?selected=${option.selected}
        ?disabled=${option.disabled}
      >${option.label}</option>`,
      )}</optgroup>`,
  )}</select>`;
}

/**
 * @param {ComparisonColumnView} column
 * @param {ComparisonHeadActions} actions
 */
function titleTemplate(column, actions) {
  return html`<button
    type="button"
    class="comparison-column-title comparison-column-title-action"
    data-comparison-title=${String(column.index)}
    aria-label=${column.controlLabel}
    @click=${() => actions.onEdit(column.index)}
  >${column.title}</button>`;
}

/**
 * @param {ComparisonColumnView} column
 * @param {ComparisonHeadActions} actions
 */
function columnActionsTemplate(column, actions) {
  if (column.removeLabel === null && !column.canAdd) return nothing;
  return html`<span class="comparison-column-actions">${
    column.removeLabel === null
      ? nothing
      : html`<button
          type="button"
          class="comparison-column-remove"
          data-comparison-remove=${String(column.index)}
          aria-label=${column.removeLabel}
          title=${column.removeLabel}
          @click=${() => actions.onRemove(column.index)}
        ><span class="comparison-column-action-icon" aria-hidden="true">&times;</span></button>`
  }${
    column.canAdd
      ? html`<button
          type="button"
          class="comparison-column-add"
          aria-label="Add comparison column"
          title="Add comparison column"
          @click=${() => actions.onAdd()}
        ><span class="comparison-column-action-icon" aria-hidden="true">+</span></button>`
      : nothing
  }</span>`;
}

/**
 * @param {ComparisonColumnView} column
 * @param {ComparisonHeadActions} actions
 */
function columnTemplate(column, actions) {
  const plain = column.removeLabel === null && !column.canAdd;
  return html`<th scope="col" data-column-signal=${column.signal}><div
    class=${plain ? 'comparison-column-heading comparison-column-plain' : 'comparison-column-heading'}
  >${
    column.editing ? pickerTemplate(column, actions) : titleTemplate(column, actions)
  }${columnActionsTemplate(column, actions)}</div></th>`;
}

/**
 * The header row.
 *
 * Keyed by column signal rather than position, so changing one column leaves
 * the others' elements in place: the control a reader is holding survives the
 * render its own change triggered, with no focus restored afterwards.
 *
 * @param {ComparisonHeadView} view
 * @param {ComparisonHeadActions} actions
 */
export function comparisonHeadTemplate(view, actions) {
  return html`<tr><th scope="col"><span class="comparison-column-label">Race</span></th>${repeat(
    view.columns,
    (column) => column.signal,
    (column) => columnTemplate(column, actions),
  )}</tr>`;
}
