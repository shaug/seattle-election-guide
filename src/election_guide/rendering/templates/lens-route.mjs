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

import { withRaceTarget } from './lens-url.mjs';

/**
 * @typedef {object} LensRouter
 * @property {() => string} fragment The live fragment, `#` included.
 * @property {() => string} controlSearch The live query string, `?` included.
 * @property {(search: string) => void} replaceControlSearch
 * @property {() => void} clearFragment
 * @property {(path: string) => void} redirectToRacePage
 * @property {(listener: () => void) => void} onFragmentChange
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
   * `history.state` is passed through on every replace rather than dropped:
   * nothing on these pages writes it today, but a replace that cleared it would
   * silently discard whatever a future caller had put there.
   *
   * @param {string} address
   */
  const replace = (address) => history.replaceState(history.state, '', address);

  return {
    fragment: () => window.location.hash,
    controlSearch: () => window.location.search,

    replaceControlSearch(search) {
      replace(`${window.location.pathname}${search}${window.location.hash}`);
    },

    /** Drop the fragment entirely: what an unreadable link resolves to. */
    clearFragment() {
      replace(bareAddress());
    },

    /**
     * Leave the guide for a race's own page (issue #136).
     *
     * A `#race-…` link shared before race detail became a page still names a
     * race, and this is where that link now goes. The lens travels with it: the
     * fragment is carried over with only its race segment removed, since the
     * path names the race from here on (issue 142). The guide's own control
     * query does not travel — a filter and a ballot view describe a list of
     * races, and there is one race on the page this lands on.
     *
     * `replace` rather than an assignment, so the address that no longer names
     * a page is not left in the reader's history for Back to return to.
     *
     * @param {string} path
     */
    redirectToRacePage(path) {
      window.location.replace(`${path}${withRaceTarget(window.location.hash, null)}`);
    },

    onFragmentChange(listener) {
      window.addEventListener('hashchange', listener);
    },
  };
}
