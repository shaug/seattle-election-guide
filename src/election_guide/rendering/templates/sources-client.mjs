// The standalone sources editor's page wiring: what used to be
// sources.html.j2's inline module script (issue #239).
//
// No scoring engine reaches this page — it only ever reads and writes a
// selection through the shared fragment codec. Roughly half of what was inline
// here was a hand-kept copy of the guide's own lens glue; that half is now
// `lens-selection.mjs`, which both pages import, so the two cannot drift.

import { createLensRouter } from './lens-route.mjs';
import {
  raceTargetFrom,
  resolveSelectedCodes,
  SELECTION_LINK_FAILURE_NOTICE,
  selectionFragment,
} from './lens-selection.mjs';
import { decodeLensFragment, lensContext } from './lens-url.mjs';

/** What a reader is told when the link they arrived on could not be read. */
const UNREADABLE_LINK_NOTICE =
  'The link you followed could not be read, so every source starts counted.';

/**
 * Wire the sources editor.
 *
 * @param {SourcesPayload} payload
 */
export function wireSourcesEditor(payload) {
  const router = createLensRouter();
  const context = lensContext(payload, payload.data_version);
  const guidePath = payload.guide_path;

  const memberCodesByCategoryCode = new Map(
    payload.categories.map((category) => [category.code, category.member_source_codes]),
  );

  /** @type {Map<string, HTMLInputElement[]>} */
  const sourceInputsByCode = new Map();
  /** @type {NodeListOf<HTMLInputElement>} */
  (document.querySelectorAll('[data-sources-source]')).forEach((input) => {
    const code = /** @type {string} */ (input.dataset.sourcesSource);
    if (!sourceInputsByCode.has(code)) sourceInputsByCode.set(code, []);
    /** @type {HTMLInputElement[]} */ (sourceInputsByCode.get(code)).push(input);
  });
  /** @param {string} code */
  const isCodeChecked = (code) => sourceInputsByCode.get(code)?.[0]?.checked ?? false;
  /**
   * @param {string} code
   * @param {boolean} checked
   */
  const syncSourceCode = (code, checked) => {
    for (const input of sourceInputsByCode.get(code) ?? []) input.checked = checked;
  };
  // Issue 124: a comparison source renders no checkbox at all, so every input
  // this page has is a tallying one.
  const tallyingCodes = [...sourceInputsByCode.keys()];
  const checkedTallyingCodes = () => tallyingCodes.filter(isCodeChecked).sort();

  const categoryToggleInputs = /** @type {HTMLInputElement[]} */ ([
    ...document.querySelectorAll('[data-sources-category-toggle]'),
  ]);
  /** @param {string} categoryCode */
  const membersOfCategory = (categoryCode) =>
    /** @type {HTMLInputElement[]} */ ([
      ...document.querySelectorAll(
        `[data-sources-source][data-sources-category-member="${categoryCode}"]`,
      ),
    ]);
  const updateCategoryToggleStates = () => {
    categoryToggleInputs.forEach((toggle) => {
      const categoryCode = /** @type {string} */ (toggle.dataset.sourcesCategoryToggle);
      const members = membersOfCategory(categoryCode);
      const checkedCount = members.filter((member) => member.checked).length;
      toggle.checked = checkedCount === members.length;
      toggle.indeterminate = checkedCount > 0 && checkedCount < members.length;
    });
  };

  const countLine = document.querySelector('[data-sources-count]');
  // "Counting", not "Viewing": a checked source counts toward the computed
  // results — nothing here is merely displayed (issue 115, item D17).
  const updateCount = () => {
    if (countLine) {
      countLine.textContent = `Counting ${checkedTallyingCodes().length} of ${tallyingCodes.length} sources.`;
    }
  };

  const notice = /** @type {HTMLElement|null} */ (document.querySelector('[data-sources-notice]'));
  /** @param {string|null} text */
  const showNotice = (text) => {
    if (!notice) return;
    notice.hidden = text === null;
    notice.textContent = text ?? '';
  };

  const saveLink = /** @type {HTMLAnchorElement|null} */ (
    document.querySelector('[data-sources-save]')
  );

  const refreshSelectionUi = () => {
    updateCategoryToggleStates();
    updateCount();
    if (!saveLink) return;
    // Save carries the edited selection back to the guide, matching the guide's
    // own Sources link: the audited default (every tallying source checked)
    // elides the fragment entirely. A rejected encode used to fall through to
    // the bare guide path in silence, losing the reader's edit without saying
    // so (docs/FRONTEND.md § State and URLs).
    const result = selectionFragment({
      selectedCodes: checkedTallyingCodes(),
      tallyingCodes,
      raceTarget: incomingRaceTarget,
      context,
    });
    if (result.status === 'rejected') showNotice(SELECTION_LINK_FAILURE_NOTICE);
    else if (notice?.textContent === SELECTION_LINK_FAILURE_NOTICE) showNotice(null);
    const fragment =
      result.status === 'ok' ? result.fragment : incomingRaceTarget ? `#${incomingRaceTarget}` : '';
    saveLink.href = `${guidePath}${fragment}`;
  };

  /**
   * Apply a decoded selection to every checkbox: a category code expands to its
   * current member codes, unioned with any directly named source codes.
   * Anything else stays unchecked. Shared with the guide.
   *
   * @param {import('./lens-url.mjs').LensState|null} selection
   */
  const applySelection = (selection) => {
    const effective = new Set(
      resolveSelectedCodes(selection, memberCodesByCategoryCode, [...sourceInputsByCode.keys()]),
    );
    for (const code of sourceInputsByCode.keys()) {
      syncSourceCode(code, effective.has(code));
    }
    refreshSelectionUi();
  };

  // Read the incoming selection once, on load, and keep the raw fragment
  // verbatim so Cancel can restore exactly what the reader arrived with.
  const incomingFragment = router.fragment();
  const incomingDecoded = decodeLensFragment(incomingFragment, context);
  const usable = incomingDecoded.status === 'valid' || incomingDecoded.status === 'stale_version';
  const incomingRaceTarget = raceTargetFrom(incomingDecoded, usable ? incomingDecoded.state : null);
  if (usable) {
    applySelection(incomingDecoded.state);
  } else {
    // `absent` and `legacy` fragments carry no selection to apply, so the
    // checkboxes stand as the server rendered them: every tallying source
    // checked. A `malformed` one is a failure, and says so rather than looking
    // like an ordinary default landing.
    if (
      incomingDecoded.status === 'malformed' &&
      incomingDecoded.reason !== 'unrecognized_fragment'
    ) {
      showNotice(UNREADABLE_LINK_NOTICE);
    }
    refreshSelectionUi();
  }

  /** @type {NodeListOf<HTMLInputElement>} */
  (document.querySelectorAll('[data-sources-source]')).forEach((input) => {
    input.addEventListener('change', () => {
      syncSourceCode(/** @type {string} */ (input.dataset.sourcesSource), input.checked);
      refreshSelectionUi();
    });
  });
  categoryToggleInputs.forEach((toggle) => {
    toggle.addEventListener('change', () => {
      const categoryCode = /** @type {string} */ (toggle.dataset.sourcesCategoryToggle);
      for (const member of membersOfCategory(categoryCode)) {
        syncSourceCode(/** @type {string} */ (member.dataset.sourcesSource), toggle.checked);
      }
      refreshSelectionUi();
    });
  });

  // Cancel and Reset never depend on the edited selection, so their target is
  // fixed once, here, rather than recomputed on every change.
  const cancelLink = /** @type {HTMLAnchorElement|null} */ (
    document.querySelector('[data-sources-cancel]')
  );
  if (cancelLink) cancelLink.href = `${guidePath}${incomingFragment}`;
  const resetLink = /** @type {HTMLAnchorElement|null} */ (
    document.querySelector('[data-sources-page-reset]')
  );
  if (resetLink) resetLink.href = guidePath;
}
