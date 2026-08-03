// The sources editor's selectable tree, as lit-html templates over view-model
// state (docs/FRONTEND.md § Rendering).
//
// The region is `.sources-columns`: every category a reader can actually
// select, and every checkbox inside it. The comparison-only section and the
// coverage-gap section sit outside it and stay exactly as the server rendered
// them, because neither carries any selection state to project.
//
// Why this region is taken over at boot rather than on the first change: it is
// a field of controls the reader operates, and § Rendering requires that "a
// control the reader is using must still exist after the render it triggers".
// A first takeover replaces the region's children, so a takeover triggered by
// the reader's own click would destroy the checkbox they just pressed and drop
// their focus. Taking the region at boot means every later render is a keyed
// update that keeps each input in place. `sources-markup-parity.test.mjs`
// checks the boot render against the markup the Jinja template produced, so
// the takeover is invisible.
//
// Pure: view model in, template out.

import { html, nothing } from 'lit-html';
import { live } from 'lit-html/directives/live.js';
import { repeat } from 'lit-html/directives/repeat.js';

/**
 * One source's row, as the payload publishes it plus whether it counts now.
 *
 * `participation` and `alsoIn` are carried rather than recomputed: both are
 * grammar the Python renderer owns, and § Cross-language mirrors prefers
 * carrying the computed value to maintaining a second implementation of it.
 *
 * @typedef {object} SourceRowView
 * @property {string} code
 * @property {string} name
 * @property {string} evidenceUrl
 * @property {string} participation
 * @property {readonly string[]} alsoIn
 * @property {boolean} checked
 */

/**
 * @typedef {object} SourceCategoryView
 * @property {string} code
 * @property {string} label
 * @property {boolean} checked Every member counts.
 * @property {boolean} indeterminate Some, but not all, members count.
 * @property {readonly SourceRowView[]} rows
 */

/**
 * What the tree's controls do.
 *
 * @typedef {object} SourcesTreeActions
 * @property {(code: string, checked: boolean) => void} onSource
 * @property {(code: string, checked: boolean) => void} onCategory
 */

/** @param {SourceRowView} row */
function alsoInTemplate(row) {
  if (row.alsoIn.length === 0) return nothing;
  return html`<span class="sources-also-in">also in: ${row.alsoIn.join(', ')}</span>`;
}

/**
 * One source row.
 *
 * The checkbox carries both bindings deliberately. `?checked` writes the
 * content attribute, which is what a reader viewing source sees and what the
 * markup-parity check compares; `.checked` writes the live property, which is
 * the only one that still tracks the selection after the reader has clicked
 * anything. Writing only the attribute would leave a re-render unable to undo
 * a click.
 *
 * The property goes through `live()` because a checkbox is the one binding
 * whose DOM value changes without a render: the browser sets it on a click,
 * and restores it on a back-navigation, in both cases behind lit's record of
 * what it last wrote. `live()` compares against the element instead of that
 * record, so a render always repairs a divergence rather than skipping it as
 * unchanged.
 *
 * @param {string} categoryCode
 * @param {SourceRowView} row
 * @param {SourcesTreeActions} actions
 */
function sourceRowTemplate(categoryCode, row, actions) {
  return html`<div class="sources-row" data-sources-source-row=${row.code}><label
    class="sources-check"
  ><input
      type="checkbox"
      data-sources-source=${row.code}
      data-sources-category-member=${categoryCode}
      ?checked=${row.checked}
      .checked=${live(row.checked)}
      @change=${(/** @type {Event} */ event) => {
        actions.onSource(row.code, /** @type {HTMLInputElement} */ (event.target).checked);
      }}
    ><a href=${row.evidenceUrl} target="_blank" rel="noopener">${row.name}</a></label><span
    class="sources-count"
  >${row.participation}</span>${alsoInTemplate(row)}</div>`;
}

/**
 * One category, with its all-or-nothing toggle.
 *
 * `indeterminate` has no content attribute at all, so it is a property binding
 * by necessity — the server cannot express a partly-selected category, and does
 * not have to: the audited default has every member counted. It takes `live()`
 * for the same reason the row's `checked` does, and one of its own: clicking an
 * indeterminate checkbox clears the flag in the DOM before any handler runs.
 *
 * @param {SourceCategoryView} category
 * @param {SourcesTreeActions} actions
 */
function categoryTemplate(category, actions) {
  return html`<section class="sources-category" data-sources-category=${category.code}><h2><label
    class="sources-check sources-category-check"
  ><input
        type="checkbox"
        data-sources-category-toggle=${category.code}
        ?checked=${category.checked}
        .checked=${live(category.checked)}
        .indeterminate=${live(category.indeterminate)}
        @change=${(/** @type {Event} */ event) => {
          actions.onCategory(category.code, /** @type {HTMLInputElement} */ (event.target).checked);
        }}
      ><span>${category.label}</span></label></h2>${repeat(
        category.rows,
        (row) => row.code,
        (row) => sourceRowTemplate(category.code, row, actions),
      )}</section>`;
}

/**
 * The selectable tree.
 *
 * Keyed by category and source code, so a re-render keeps every input element
 * it already made: the checkbox a reader just toggled is the same element
 * afterwards, holding the same focus (docs/FRONTEND.md § Rendering).
 *
 * @param {readonly SourceCategoryView[]} categories
 * @param {SourcesTreeActions} actions
 */
export function sourcesTreeTemplate(categories, actions) {
  return repeat(
    categories,
    (category) => category.code,
    (category) => categoryTemplate(category, actions),
  );
}
