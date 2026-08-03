// The guide's and the sources editor's one address-bar owner
// (docs/FRONTEND.md § State and URLs: each page's codec module is the sole
// reader and writer of `location`; no second script parses the hash by hand,
// and no handler edits `location` around the codec).
//
// The codec proper is `lens-url.mjs`, which is pure and therefore cannot touch
// `location` at all. This module is the other half of that ownership: it is the
// only place either page reads `location` or calls `history`, and every
// fragment it reads or writes is parsed and composed by the codec rather than
// by hand. Both pages' glue asks this module for state and hands it state back;
// none of it names `location` itself.
//
// This is not the only such owner: Comparisons has `compare-route.mjs`, because
// the rule is one owner per fragment rather than one owner for all of them.
// `LOCATION_OWNERS` in `tests/js/lens-route.test.mjs` is the registry of every
// owner and every recorded exception, with the argument for each — and the
// sweep beside it is what fails when a module joins the list without joining
// the registry. It is deliberately not restated here: the sweep strips comments
// before scanning, so a second copy of the list is one nothing can keep honest.

import { fragmentRaceTarget, withRaceTarget } from './lens-url.mjs';

/**
 * @typedef {object} LensRouter
 * @property {() => string} fragment The live fragment, `#` included.
 * @property {() => string} raceTarget The race the fragment names, or `''`.
 * @property {() => unknown} historyState
 * @property {() => string} controlSearch The live query string, `?` included.
 * @property {(search: string) => void} replaceControlSearch
 * @property {() => void} clearFragment
 * @property {(target: string|null) => void} replaceRaceTarget
 * @property {(target: string, state: Record<string, unknown>) => void} pushRaceTarget
 * @property {() => void} back
 * @property {(target: string|null) => string} absoluteRaceLink
 * @property {(listener: () => void) => void} onFragmentChange
 * @property {(listener: () => void) => void} onHistoryChange
 */

/**
 * The address-bar owner for one page.
 *
 * @returns {LensRouter}
 */
export function createLensRouter() {
  /** The page's own address with no fragment: what a cleared fragment leaves. */
  const bareAddress = () => `${window.location.pathname}${window.location.search}`;

  /**
   * Replace the current entry, preserving whatever state it already carries.
   *
   * `history.state` is passed through on every replace rather than dropped: the
   * race dialog stores its own `raceDetail` marker there, and a replace that
   * cleared it would make the next Back press stop restoring the dialog.
   *
   * @param {string} address
   */
  const replace = (address) => history.replaceState(history.state, '', address);

  return {
    fragment: () => window.location.hash,
    raceTarget: () => fragmentRaceTarget(window.location.hash),
    historyState: () => history.state,
    controlSearch: () => window.location.search,

    replaceControlSearch(search) {
      replace(`${window.location.pathname}${search}${window.location.hash}`);
    },

    /** Drop the fragment entirely: what an unreadable link resolves to. */
    clearFragment() {
      replace(bareAddress());
    },

    /** Rewrite only the race segment in place, leaving any lens untouched. */
    replaceRaceTarget(target) {
      replace(`${bareAddress()}${withRaceTarget(window.location.hash, target)}`);
    },

    pushRaceTarget(target, state) {
      history.pushState(state, '', withRaceTarget(window.location.hash, target));
    },

    back() {
      history.back();
    },

    /**
     * The shareable address for one race.
     *
     * Composed from the live address rather than copied off it, so the link
     * reproduces the active lens even when the dialog's own hash state was
     * reached by a path the share button cannot assume (issue 142).
     */
    absoluteRaceLink(target) {
      const link = new URL(window.location.href);
      link.hash = withRaceTarget(window.location.hash, target);
      return link.toString();
    },

    onFragmentChange(listener) {
      window.addEventListener('hashchange', listener);
    },

    onHistoryChange(listener) {
      window.addEventListener('popstate', listener);
    },
  };
}
