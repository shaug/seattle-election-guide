// The Comparisons page's one address-bar owner (docs/FRONTEND.md § State and
// URLs: each page's codec module is the sole reader and writer of `location`;
// no second script parses the hash by hand, and no handler edits `location`
// around the codec).
//
// The codec proper is `compare-url.mjs`, which is pure and therefore cannot
// touch `location` at all. This module is the other half of that ownership,
// exactly as `lens-route.mjs` is for the guide and the sources editor: it is
// the only place this page reads `location` or calls `history`, and it parses
// nothing. Every fragment it hands out is decoded by the codec, and every
// fragment it writes was composed by the codec.
//
// One owner per fragment, not one owner for all of them: the guide's router is
// deliberately not shared with this page, because the two fragments are
// different schemas read against different contexts.

/**
 * @typedef {object} CompareRouter
 * @property {() => string} fragment The live fragment, `#` included.
 * @property {() => string} key The whole address, as one comparable string.
 * @property {(fragment: string, mode: 'push'|'replace') => void} write
 * @property {() => void} clearFragment
 * @property {(listener: () => void) => void} onFragmentChange
 * @property {(listener: () => void) => void} onHistoryChange
 */

/** What this page's own history entries are marked with. */
const COMPARISON_ENTRY = { comparison: true };

/**
 * The address-bar owner for the Comparisons page.
 *
 * @returns {CompareRouter}
 */
export function createCompareRouter() {
  /** The page's own address with no fragment: what a cleared fragment leaves. */
  const bareAddress = () => `${window.location.pathname}${window.location.search}`;

  return {
    fragment: () => window.location.hash,

    /**
     * The whole address as one string.
     *
     * The page compares this against the address it last wrote, so that its
     * own `pushState` does not read back as a reader navigating. It is a
     * comparison key, not a parse: no segment of it is interpreted here or by
     * the caller.
     */
    key: () => `${window.location.pathname}${window.location.search}${window.location.hash}`,

    /**
     * Put one codec-composed fragment in the address bar.
     *
     * @param {string} fragment The codec's fragment, with no leading `#`.
     * @param {'push'|'replace'} mode
     */
    write(fragment, mode) {
      const target = `${bareAddress()}#${fragment}`;
      if (mode === 'replace') history.replaceState(COMPARISON_ENTRY, '', target);
      else history.pushState(COMPARISON_ENTRY, '', target);
    },

    /**
     * Drop the fragment entirely: what an unreadable link resolves to.
     *
     * Replacing rather than pushing, and preserving whatever state the entry
     * already carries, so that clearing a bad link neither adds a Back step
     * nor discards the marker the entry was created with.
     */
    clearFragment() {
      history.replaceState(history.state, '', bareAddress());
    },

    onFragmentChange(listener) {
      window.addEventListener('hashchange', listener);
    },

    onHistoryChange(listener) {
      window.addEventListener('popstate', listener);
    },
  };
}
