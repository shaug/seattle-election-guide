// The standalone sources editor's page wiring: what used to be
// sources.html.j2's inline module script (issue #239).
//
// No scoring engine reaches this page — it only ever reads and writes a
// selection through the shared fragment codec. Roughly half of what was inline
// here was a hand-kept copy of the guide's own lens glue; that half is now
// `lens-selection.mjs`, which both pages import, so the two cannot drift.
//
// Since issue #248 the selection itself is state here rather than checkbox
// state read back out of the DOM: `sources-tree.mjs` renders the tree from a
// set of counted codes, and every change event updates the set and re-renders.
// That is the direction docs/FRONTEND.md's data contract requires — the DOM is
// write-only projection — and it is what lets the tree's audited rendering be
// diffed against the server's.

import { html, render } from 'lit-html';
import { createLensRouter } from './lens-route.mjs';
import {
  raceTargetFrom,
  resolveSelectedCodes,
  SELECTION_LINK_FAILURE_NOTICE,
  selectionFragment,
} from './lens-selection.mjs';
import { decodeLensFragment, lensContext } from './lens-url.mjs';
import { sourcesTreeTemplate } from './sources-tree.mjs';

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

  const tree = /** @type {HTMLElement|null} */ (document.querySelector('[data-sources-tree]'));
  // Issue 124: a comparison source renders no checkbox at all, and the payload's
  // tree carries only the selectable categories, so every code below is a
  // tallying one. Deduplicated, because a source selectable under two
  // categories has a row under each and is still one source to count.
  const tallyingCodes = [
    ...new Set(payload.tree.flatMap((category) => category.sources.map((source) => source.code))),
  ];
  /**
   * Which sources count. The audited default is every one of them, which is
   * exactly what the server rendered.
   *
   * @type {Set<string>}
   */
  const counted = new Set(tallyingCodes);
  const checkedTallyingCodes = () => tallyingCodes.filter((code) => counted.has(code)).sort();
  /**
   * Whether there is a selection to render at all.
   *
   * A release with the lens switched off (issues 80/81) renders a deliberately
   * non-interactive tree — a plain link per source, a plain category heading —
   * and publishes no tree for this module to render. There is nothing to take
   * over, and taking the region over anyway would put checkboxes on a page the
   * policy withheld them from.
   */
  const selectable = payload.tree.length > 0;
  /** Whether lit has replaced the server's markup with its own. One-way. */
  let takenOver = false;

  const countLine = /** @type {HTMLElement|null} */ (
    document.querySelector('[data-sources-count]')
  );
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

  /** @type {import('./sources-tree.mjs').SourcesTreeActions} */
  const actions = {
    onSource(code, checked) {
      if (checked) counted.add(code);
      else counted.delete(code);
      renderPage();
    },
    onCategory(code, checked) {
      const category = payload.tree.find((item) => item.code === code);
      for (const source of category?.sources ?? []) {
        if (checked) counted.add(source.code);
        else counted.delete(source.code);
      }
      renderPage();
    },
  };

  /** @returns {import('./sources-tree.mjs').SourceCategoryView[]} */
  const treeView = () =>
    payload.tree.map((category) => {
      const countedMembers = category.sources.filter((source) => counted.has(source.code)).length;
      return {
        code: category.code,
        label: category.label,
        checked: countedMembers === category.sources.length,
        indeterminate: countedMembers > 0 && countedMembers < category.sources.length,
        rows: category.sources.map((source) => ({
          code: source.code,
          name: source.name,
          evidenceUrl: source.evidence_url,
          participation: source.participation,
          alsoIn: source.also_in,
          checked: counted.has(source.code),
        })),
      };
    });

  /**
   * Everything one selection change implies: the tree, the count, and where
   * Save carries the reader.
   *
   * "Counting", not "Viewing": a checked source counts toward the computed
   * results — nothing here is merely displayed (issue 115, item D17).
   */
  const renderPage = () => {
    if (selectable) {
      if (!takenOver) {
        // Takeover is one-way and explicit: the server's markup for both
        // regions is dropped once, here, and lit owns them from now on
        // (docs/FRONTEND.md § Rendering). Without this, lit would render its
        // own copy after the server's rather than in place of it. It happens at
        // boot because the tree is a field of controls: a takeover triggered by
        // the reader's own click would destroy the checkbox they just pressed.
        tree?.replaceChildren();
        countLine?.replaceChildren();
        takenOver = true;
      }
      if (tree) render(sourcesTreeTemplate(treeView(), actions), tree);
      if (countLine) {
        render(
          html`Counting ${checkedTallyingCodes().length} of ${tallyingCodes.length} sources.`,
          countLine,
        );
      }
    }
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
   * Apply a decoded selection: a category code expands to its current member
   * codes, unioned with any directly named source codes. Anything else stops
   * counting. Shared with the guide.
   *
   * @param {import('./lens-url.mjs').LensState|null} selection
   */
  const applySelection = (selection) => {
    const effective = new Set(
      resolveSelectedCodes(selection, memberCodesByCategoryCode, tallyingCodes),
    );
    counted.clear();
    for (const code of tallyingCodes) {
      if (effective.has(code)) counted.add(code);
    }
  };

  // Read the incoming selection once, on load, and keep the raw fragment
  // verbatim so Cancel can restore exactly what the reader arrived with.
  const incomingFragment = router.fragment();
  const incomingDecoded = decodeLensFragment(incomingFragment, context);
  const usable = incomingDecoded.status === 'valid' || incomingDecoded.status === 'stale_version';
  const incomingRaceTarget = raceTargetFrom(incomingDecoded, usable ? incomingDecoded.state : null);
  if (usable) {
    applySelection(incomingDecoded.state);
  } else if (
    // `absent` and `legacy` fragments carry no selection to apply, so the
    // audited default stands: every tallying source counted. A `malformed` one
    // is a failure, and says so rather than looking like an ordinary default
    // landing.
    incomingDecoded.status === 'malformed' &&
    incomingDecoded.reason !== 'unrecognized_fragment'
  ) {
    showNotice(UNREADABLE_LINK_NOTICE);
  }
  renderPage();

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
