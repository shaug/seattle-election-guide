// The Updates index owns only its additive topics query. Other page state is
// neither read nor inherited; unrelated parameters and fragments survive.

/** @param {string[]} topicIds */
export function createUpdatesRouter(topicIds) {
  /** @returns {string[]} */
  function read() {
    const query = new URL(window.location.href).searchParams;
    const incoming = new Set(query.getAll('topics').flatMap((value) => value.split(',')));
    return topicIds.filter((topic) => incoming.has(topic));
  }
  /** @param {string[]} selected @param {boolean} replace */
  function write(selected, replace) {
    const url = new URL(window.location.href);
    const canonical = topicIds.filter((topic) => selected.includes(topic));
    if (canonical.length) url.searchParams.set('topics', canonical.join(','));
    else url.searchParams.delete('topics');
    const address = url.href.replace(/(topics=[^&#]*)/g, (value) => value.replace(/%2C/gi, ','));
    if (address === window.location.href) return;
    if (replace) window.history.replaceState(null, '', address);
    else window.history.pushState(null, '', address);
  }
  return {
    read,
    /** @param {string[]} selected */
    replace: (selected) => write(selected, true),
    /** @param {string[]} selected */
    commit: (selected) => write(selected, false),
    /** @param {(selected: string[]) => void} listener */
    subscribe(listener) {
      const restore = () => listener(read());
      window.addEventListener('popstate', restore);
      return () => window.removeEventListener('popstate', restore);
    },
  };
}
