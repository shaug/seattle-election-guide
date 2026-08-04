// The endorsements guide's page wiring: what used to be guide.html.j2's two
// inline `<script>` blocks (issue #239).
//
// This module composes; the behavior lives in the modules it calls. The
// composition order matters and is the order the two script blocks ran in
// before the extraction: a classic `<script>` executes at parse time and a
// `<script type="module">` is deferred, so the filters were wired first and the
// lens second, even though the lens block came first in the document.
//
// One `{% if %}` disappeared in the move. The template used to compile two
// different scripts depending on the release policy; the payload already says
// which one applies (`personalization` is null when the lens is off), so the
// branch is a runtime one now and the template carries no logic at all.
//
// What this module renders is the lens strip's text in the sticky header
// (issue #248): the banner's live count and the notice below it. Both are
// `aria-live` elements the server renders and lit renders *into*, never
// replaces — see the note beside their lookup below.
//
// The race-detail dialog it also wired is gone (issue #136). What is left of it
// here is one forward: a `#race-…` link shared while the dialog existed still
// names a race, and it now names a page.

import { html, nothing, render } from 'lit-html';
import { wireGuideFilters } from './guide-filters.mjs';
import { createGuideLens, lensCountingSummary } from './guide-lens.mjs';
import { createLensRouter } from './lens-route.mjs';
import {
  resolveLensLink,
  resolveSelectedCodes,
  SELECTION_LINK_FAILURE_NOTICE,
  selectionFragment,
  tallyingSourceCodes,
} from './lens-selection.mjs';
import {
  decodeLensFragment,
  fragmentRaceTarget,
  LEGACY_RACE_PREFIX,
  lensContext,
} from './lens-url.mjs';

/**
 * Forward a fragment that names a race to that race's own page (issue #136).
 *
 * Both shapes a race target can arrive in are the same target: the bare
 * `#race-…` permalink the dialog published, and the `race=` segment a lens link
 * carries beside its selection — which is also what the sources editor's Save
 * writes when a reader edits their sources from a race page. The codec reads
 * either, so this reads neither by hand.
 *
 * The target is resolved against the published races rather than pasted into an
 * address: a fragment naming no race of this election leaves the reader on the
 * guide, which is where they already are.
 *
 * @param {GuidePayload} payload
 * @param {import('./lens-route.mjs').LensRouter} router
 * @returns {boolean} Whether the page is leaving.
 */
function forwardToRacePage(payload, router) {
  const target = fragmentRaceTarget(router.fragment());
  if (!target.startsWith(LEGACY_RACE_PREFIX)) return false;
  const raceId = target.slice(LEGACY_RACE_PREFIX.length);
  const race = payload.races.find((item) => item.race_id === raceId);
  if (race === undefined) return false;
  router.redirectToRacePage(race.race_path);
  return true;
}

/**
 * Wire the guide.
 *
 * @param {GuidePayload} payload
 */
export function wireGuide(payload) {
  const router = createLensRouter();
  // Before anything renders: this load is a navigation away, and taking cards
  // over or rewriting the address bar first would be work done on a page the
  // reader never sees.
  if (forwardToRacePage(payload, router)) return;
  wireGuideFilters(payload, router);

  const personalization = payload.personalization;
  const context = lensContext(payload, payload.data_version);
  const lens = createGuideLens(payload);
  const memberCodesByCategoryCode = new Map(
    payload.categories.map((category) => [category.code, category.member_source_codes]),
  );
  const panelSourceCodes = payload.sources.map((source) => source.code);
  const tallyingCodes = tallyingSourceCodes(payload.sources);

  /**
   * The lens strip's two announcing elements, which stay the server's.
   *
   * lit renders their text; it never renders the elements themselves. A live
   * region announces a change only if it was already in the accessibility tree
   * when the change happened, so an element lit created — even one render
   * earlier, in the same task — would announce nothing, and every notice this
   * page raises is a boot-time one. Keeping the parser's elements is what makes
   * the announcement work, and it is the same shape the sources page's count
   * line uses (docs/FRONTEND.md § Rendering).
   */
  const bannerStatus = /** @type {HTMLElement|null} */ (
    document.querySelector('[data-lens-banner-status]')
  );
  const lensNotice = /** @type {HTMLElement|null} */ (document.querySelector('[data-lens-notice]'));
  /** The server's own text, dropped once so lit can own these two text nodes. */
  for (const region of [bannerStatus, lensNotice]) region?.replaceChildren();

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
  /** A persistent explanation of how this load resolved its link, when warranted. */
  /** @type {string|null} */
  let notice = null;

  const readFragment = () =>
    resolveLensLink(decodeLensFragment(router.fragment(), context), personalization);

  /**
   * Where the Sources link should carry the reader: the page they would edit
   * their selection on, holding the selection they are looking at.
   *
   * It carries no race target. A guide address that named one is a race page's
   * address now and this load has already left for it (`forwardToRacePage`), so
   * the only reader who reaches here is on the guide itself — and Save should
   * return them to the guide. The race pages carry their own target, which is
   * how Save returns a reader to the race they were reading.
   *
   * A rejected encode — an oversized selection is the reachable case — used to
   * fall through to the bare guide path, so the reader followed a link that
   * silently dropped what they had chosen. It now says so
   * (docs/FRONTEND.md § State and URLs).
   */
  const sourcesHref = () => {
    const result = selectionFragment({
      selectedCodes,
      tallyingCodes,
      raceTarget: null,
      context,
    });
    if (result.status === 'rejected') notice = SELECTION_LINK_FAILURE_NOTICE;
    return `${payload.sources_page_path}${result.status === 'ok' ? result.fragment : ''}`;
  };

  /**
   * Render the lens strip's text, and point every Sources link at the selection
   * the reader is looking at.
   *
   * Neither Sources link is lit's. The one in the strip and the one in the
   * shell band (`shell.py` renders it on every page) are both server markup,
   * and both take the same plain href assignment. The loop re-queries rather
   * than caching, so a link the page gains later is not missed.
   */
  const renderChrome = () => {
    const href = sourcesHref();
    if (bannerStatus) render(html`${lensCountingSummary(payload, selectedCodes)}`, bannerStatus);
    if (lensNotice) {
      lensNotice.hidden = notice === null;
      render(html`${notice ?? nothing}`, lensNotice);
    }
    for (const link of /** @type {HTMLAnchorElement[]} */ ([
      ...document.querySelectorAll('[data-sources-link]'),
    ])) {
      link.href = href;
    }
  };

  /**
   * Apply a decoded (or migrated) selection. Every path that can change what
   * the reader has selected — the initial load, a later hashchange — ends here.
   *
   * @param {import('./lens-url.mjs').LensState|null} selection
   */
  const applySelection = (selection) => {
    selectedCodes = resolveSelectedCodes(selection, memberCodesByCategoryCode, panelSourceCodes);
    notice = null;
    lens?.render(selectedCodes);
    renderChrome();
  };

  // Computed once, from the page's initial address: a persistent migration or
  // invalid-link explanation describes how this load resolved a shared link,
  // not an ongoing in-page navigation, so later hashchange events (including
  // the skip link, which the codec deliberately does not recognize as
  // lens-shaped) never manufacture or overwrite it.
  const initial = readFragment();
  // applySelection clears any existing notice, so the state is applied before
  // the notice below is set, not after — otherwise this very notice would erase
  // itself on the same load that produced it.
  if (initial.state !== null) applySelection(initial.state);
  else lens?.render(selectedCodes);
  if (initial.notice) notice = initial.notice;
  if (initial.cleanAddress) {
    // A malformed or unmigratable link resolves to the audited consensus; clear
    // it from the address bar so a reload or copy reproduces that resolved state
    // instead of failing the same way again. Clearing it replaces the history
    // entry rather than navigating.
    router.clearFragment();
  }
  renderChrome();

  // A plain in-page anchor (the skip link) also fires hashchange; only a
  // genuine lens-shaped change re-applies a selection.
  router.onFragmentChange(() => {
    const outcome = readFragment();
    if (outcome.state) applySelection(outcome.state);
    else renderChrome();
  });
}
