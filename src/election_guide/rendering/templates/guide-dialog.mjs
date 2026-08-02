// The race-detail dialog and the hash routing that opens and closes it.
//
// Extracted from guide.html.j2's classic script by issue #239, as-is: issue
// #136 replaces this dialog with per-race pages, so it is moved rather than
// improved. Three things changed in the move, each one a rule this ticket
// enforces:
//
//   * The hash is no longer hand-parsed here. `fragmentId` and
//     `raceDetailFragment` — a `decodeURIComponent` plus a `URLSearchParams`
//     each, the second of which conceded the overlap in its own comment — are
//     now `fragmentRaceTarget` and `withRaceTarget` in the codec, reached
//     through `lens-route.mjs` (docs/FRONTEND.md § State and URLs: no second
//     script parses the hash by hand).
//   * The race label for the share status comes from the payload, not from the
//     card's `[data-display-role="race-label"]` text (The data contract).
//   * `shareOrCopyLink` is imported. It used to be published onto `window` by
//     share-link.mjs because this code was in a classic script that could not
//     import it; that channel is deleted with this extraction.

import { shareOrCopyLink } from './share-link.mjs';

/**
 * @typedef {object} GuideDialogs
 * @property {(options?: { restoreFocus?: boolean }) => void} sync Open or close
 *   dialogs to match the address bar.
 */

/**
 * Wire the race-detail dialogs.
 *
 * @param {GuidePayload} payload
 * @param {import('./lens-route.mjs').LensRouter} router
 * @param {import('./guide-filters.mjs').GuideFilters} filters
 * @returns {GuideDialogs}
 */
export function wireRaceDialogs(payload, router, filters) {
  const dialogs = /** @type {HTMLDialogElement[]} */ ([
    ...document.querySelectorAll('[data-race-detail-dialog]'),
  ]);
  const raceLabels = new Map(payload.races.map((race) => [race.race_id, race.race_label]));
  /** @type {HTMLElement|null} */
  let lastTrigger = null;

  /** @param {HTMLDialogElement} dialog */
  const openerFor = (dialog) => {
    const card = dialog.closest('[data-publication-race-id]');
    if (lastTrigger && lastTrigger.closest('[data-publication-race-id]') === card) {
      return lastTrigger;
    }
    return /** @type {HTMLElement|null} */ (card?.querySelector('[data-race-detail-link]') ?? null);
  };

  /** @param {{ restoreFocus?: boolean }} [options] */
  const sync = ({ restoreFocus = false } = {}) => {
    const card = document.getElementById(router.raceTarget());
    const target = card?.matches('[data-publication-race-id]')
      ? /** @type {HTMLDialogElement|null} */ (card.querySelector('[data-race-detail-dialog]'))
      : null;
    dialogs.forEach((dialog) => {
      if (dialog !== target && dialog.open) dialog.close();
    });
    if (target && card) {
      if (card.hidden) filters.showEveryRace();
      if (!target.open) target.showModal();
      /** @type {HTMLElement|null} */ (target.querySelector('[data-close-race-detail]'))?.focus();
      return;
    }
    if (restoreFocus && lastTrigger) lastTrigger.focus();
  };

  /** @param {HTMLDialogElement} dialog */
  const requestClose = (dialog) => {
    const card = dialog.closest('[data-publication-race-id]');
    const target = card ? card.id : '';
    const state = router.historyState();
    if (
      target &&
      state !== null &&
      typeof state === 'object' &&
      /** @type {Record<string, unknown>} */ (state).raceDetail === target
    ) {
      router.back();
      return;
    }
    // Closing strips only the race segment, never an active lens selection
    // (issue 142) — hence a race-target rewrite rather than clearing the hash.
    router.replaceRaceTarget(null);
    if (dialog.open) dialog.close();
    openerFor(dialog)?.focus();
  };

  /** @type {NodeListOf<HTMLAnchorElement>} */
  (document.querySelectorAll('[data-race-detail-link]')).forEach((link) => {
    link.addEventListener('click', (event) => {
      event.preventDefault();
      lastTrigger = link;
      const target = link.hash.slice(1);
      const current = router.historyState();
      const state = current !== null && typeof current === 'object' ? current : {};
      router.pushRaceTarget(target, { ...state, raceDetail: target });
      sync();
    });
  });
  dialogs.forEach((dialog) => {
    dialog.querySelector('[data-close-race-detail]')?.addEventListener('click', () => {
      requestClose(dialog);
    });
    dialog.addEventListener('cancel', (event) => {
      event.preventDefault();
      requestClose(dialog);
    });
  });
  router.onHistoryChange(() => {
    filters.syncFromUrl();
    filters.apply({ syncUrl: false });
    // An active lens leaves the hash non-empty even with no dialog open (issue
    // 142), so whether focus should return to the trigger is decided by the
    // resolved race id, not by hash truthiness.
    sync({ restoreFocus: !router.raceTarget() });
  });
  router.onFragmentChange(() => {
    sync({ restoreFocus: !router.raceTarget() });
  });
  /** @type {NodeListOf<HTMLButtonElement>} */
  (document.querySelectorAll('[data-copy-race-link]')).forEach((button) => {
    button.addEventListener('click', async () => {
      const raceId = /** @type {string} */ (button.dataset.copyRaceLink);
      const value = router.absoluteRaceLink(raceId);
      const card = /** @type {HTMLElement|null} */ (button.closest('[data-publication-race-id]'));
      const raceLabel = raceLabels.get(card?.dataset.publicationRaceId ?? '');
      const copyStatus = button
        .closest('[data-race-detail-dialog]')
        ?.querySelector('[data-copy-race-status]');
      const result = await shareOrCopyLink(value, raceLabel || document.title);
      if (copyStatus && result === 'copied') {
        copyStatus.textContent = `Link copied for ${raceLabel || 'this race'}`;
      } else if (copyStatus && result === 'shared') {
        copyStatus.textContent = `Share menu opened for ${raceLabel || 'this race'}`;
      } else if (copyStatus && result === 'failed') {
        copyStatus.textContent = `Copy failed. Link: ${value}`;
      }
      button.focus();
    });
  });

  sync();
  return { sync };
}
