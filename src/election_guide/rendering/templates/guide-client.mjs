// The endorsements guide's page wiring: what used to be guide.html.j2's two
// inline `<script>` blocks (issue #239).
//
// This module composes; the behavior lives in the four modules it calls. The
// composition order matters and is the order the two script blocks ran in
// before the extraction: a classic `<script>` executes at parse time and a
// `<script type="module">` is deferred, so the filters and the dialog were
// wired first and the lens second, even though the lens block came first in the
// document. Keeping that order keeps the load-time interaction between them —
// a dialog opening against a filtered-out card, a fragment the lens then
// cleans — exactly as shipped.
//
// One `{% if %}` disappeared in the move. The template used to compile two
// different scripts depending on the release policy; the payload already says
// which one applies (`personalization` is null when the lens is off), so the
// branch is a runtime one now and the template carries no logic at all.

import { wireRaceDialogs } from './guide-dialog.mjs';
import { wireGuideFilters } from './guide-filters.mjs';
import { createGuideLens } from './guide-lens.mjs';
import { migrateLensState } from './lens-migrate.mjs';
import { createLensRouter } from './lens-route.mjs';
import {
  raceTargetFrom,
  resolveSelectedCodes,
  SELECTION_LINK_FAILURE_NOTICE,
  selectionFragment,
} from './lens-selection.mjs';
import { decodeLensFragment, lensContext } from './lens-url.mjs';

const UNREADABLE_LINK_NOTICE = 'This link could not be read, so it shows the audited consensus.';
const MIGRATED_LINK_NOTICE =
  'This link was written for an earlier published data version. It was migrated to the current ' +
  'panel, so results may differ from the original link.';

/**
 * One decoded fragment resolved to live state, an explanation, and whether the
 * address bar has to be cleaned.
 *
 * @typedef {object} LensOutcome
 * @property {import('./lens-url.mjs').LensState|null} state
 * @property {string|null} notice
 * @property {boolean} cleanAddress
 */

/**
 * Wire the guide.
 *
 * @param {GuidePayload} payload
 */
export function wireGuide(payload) {
  const router = createLensRouter();
  const filters = wireGuideFilters(payload, router);
  wireRaceDialogs(payload, router, filters);

  const personalization = payload.personalization;
  const context = lensContext(payload, payload.data_version);
  const lens = createGuideLens(payload);
  const memberCodesByCategoryCode = new Map(
    payload.categories.map((category) => [category.code, category.member_source_codes]),
  );
  const panelSourceCodes = payload.sources.map((source) => source.code);
  const tallyingCodes = payload.sources
    .filter((source) => source.panel_role !== 'comparison')
    .map((source) => source.code);

  const lensNotice = /** @type {HTMLElement|null} */ (document.querySelector('[data-lens-notice]'));
  const sourcesLinks = /** @type {HTMLAnchorElement[]} */ ([
    ...document.querySelectorAll('[data-sources-link]'),
  ]);

  /** @param {string|null} text */
  const showLensNotice = (text) => {
    if (!lensNotice) return;
    lensNotice.hidden = text === null;
    lensNotice.textContent = text ?? '';
  };

  /**
   * Which sources currently count (issue 108): the guide has no interactive
   * selection UI of its own — a reader edits their selection on the dedicated
   * sources page and returns with a new URL — so this is tracked directly
   * rather than read off checkbox state. It starts at the audited default,
   * which is every tallying source.
   *
   * @type {string[]}
   */
  let selectedCodes = [...tallyingCodes];

  /**
   * Resolve one decoded fragment to live lens state plus a persistent
   * explanation, when one is warranted.
   *
   * A same-version link needs neither migration nor an explanation. A
   * `stale_version` link is resolved through issue 78's migration resolver,
   * with no origin snapshot: nothing about correct resolution depends on one (a
   * surviving code always names the same source or category it always did), it
   * only refines "removed" versus "unknown" reporting this guide does not
   * surface. A migration that must reject falls back to audited. Every other
   * non-lens status (`absent`, `legacy`, or an ordinary in-page anchor the codec
   * does not recognize, such as the skip link) carries no lens explanation at
   * all, so clicking around the page never manufactures one.
   *
   * With the lens disabled there is nothing to migrate a stale link into and
   * nothing on the page acts on a selection, so the decode runs only so that an
   * unreadable fragment is recognized — and, since issue #239, reported. It
   * used to be cleaned from the address bar in silence, which the rule forbids
   * (docs/FRONTEND.md § State and URLs: a decode failure produces a
   * reader-visible notice *and* a cleaned address bar).
   *
   * @param {import('./lens-url.mjs').LensDecodeResult} decoded
   * @returns {LensOutcome}
   */
  const resolve = (decoded) => {
    const unreadable = decoded.status === 'malformed' && decoded.reason !== 'unrecognized_fragment';
    if (personalization === null) {
      const usable = decoded.status === 'valid' || decoded.status === 'stale_version';
      return {
        state: usable ? decoded.state : null,
        notice: unreadable ? UNREADABLE_LINK_NOTICE : null,
        cleanAddress: unreadable,
      };
    }
    if (decoded.status === 'valid') {
      return { state: decoded.state, notice: null, cleanAddress: false };
    }
    if (decoded.status === 'stale_version') {
      const migration = migrateLensState(decoded, personalization, null);
      if (migration.status === 'migrated') {
        return { state: migration.selection, notice: MIGRATED_LINK_NOTICE, cleanAddress: false };
      }
      return {
        state: null,
        notice:
          'This link could not be migrated to the current published panel ' +
          `(category ${migration.category} is no longer available), so it shows the audited consensus.`,
        cleanAddress: true,
      };
    }
    if (!unreadable) return { state: null, notice: null, cleanAddress: false };
    return { state: null, notice: UNREADABLE_LINK_NOTICE, cleanAddress: true };
  };

  /** The race the reader is currently on, as the live fragment resolves today. */
  const currentRaceTarget = () => {
    const decoded = decodeLensFragment(router.fragment(), context);
    return raceTargetFrom(decoded, resolve(decoded).state);
  };

  /**
   * Point every Sources link at the page the reader would edit their selection
   * on, carrying the selection they are looking at.
   *
   * A rejected encode — an oversized selection is the reachable case — used to
   * fall through to the bare guide path, so the reader followed a link that
   * silently dropped what they had chosen. It now says so
   * (docs/FRONTEND.md § State and URLs).
   */
  const updateSourcesLinks = () => {
    const raceTarget = currentRaceTarget();
    const result = selectionFragment({ selectedCodes, tallyingCodes, raceTarget, context });
    if (result.status === 'rejected') showLensNotice(SELECTION_LINK_FAILURE_NOTICE);
    const fragment = result.status === 'ok' ? result.fragment : raceTarget ? `#${raceTarget}` : '';
    const href = `${payload.sources_page_path}${fragment}`;
    sourcesLinks.forEach((link) => {
      link.href = href;
    });
  };

  /**
   * Apply a decoded (or migrated) selection. Every path that can change what
   * the reader has selected — the initial load, a later hashchange — ends here.
   *
   * @param {import('./lens-url.mjs').LensState|null} selection
   */
  const applySelection = (selection) => {
    selectedCodes = resolveSelectedCodes(selection, memberCodesByCategoryCode, panelSourceCodes);
    showLensNotice(null);
    lens?.render(selectedCodes);
    updateSourcesLinks();
  };

  // Computed once, from the page's initial address: a persistent migration or
  // invalid-link explanation describes how this load resolved a shared link,
  // not an ongoing in-page navigation, so later hashchange events (including
  // the skip link, which the codec deliberately does not recognize as
  // lens-shaped) never manufacture or overwrite it.
  const initial = resolve(decodeLensFragment(router.fragment(), context));
  // applySelection clears any existing notice, so the state is applied before
  // the notice below is set, not after — otherwise this very notice would erase
  // itself on the same load that produced it.
  if (initial.state !== null) applySelection(initial.state);
  else lens?.render(selectedCodes);
  if (initial.notice) showLensNotice(initial.notice);
  if (initial.cleanAddress) {
    // A malformed or unmigratable link resolves to the audited consensus; clear
    // it from the address bar so a reload or copy reproduces that resolved state
    // instead of failing the same way again.
    router.clearFragment();
  }
  updateSourcesLinks();

  // A plain in-page anchor (the skip link) also fires hashchange, and so does
  // opening or closing a race-detail dialog; the Sources link's target always
  // needs the current race target regardless, but only a genuine lens-shaped
  // change also re-applies a selection.
  router.onFragmentChange(() => {
    updateSourcesLinks();
    const state = resolve(decodeLensFragment(router.fragment(), context)).state;
    if (!state) return;
    applySelection(state);
  });
}
