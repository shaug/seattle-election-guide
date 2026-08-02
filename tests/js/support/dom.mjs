// The lightweight DOM the Node tests render in (docs/FRONTEND.md § Testing).
//
// happy-dom rather than a headless browser: these are unit tests of render
// functions, and Chrome stays the integration layer.
//
// The DOM is installed on `globalThis` rather than passed around because that
// is where lit-html and our own page wiring look for it.
//
// `installDom()` must run *before* the module under test is imported, so a
// test file calls it and then `await import()`s rather than importing at the
// top. The reason is lit-html's `node` export condition, which Node resolves
// and esbuild — building for the browser — does not: that build decides once,
// while its module body evaluates, whether a document exists, and binds a stub
// with only `createTreeWalker` when one does not. A lit-html imported before
// this function has run can never render, and fails with a bare
// `createComment is not a function` some frames away from the cause.

import { Window } from 'happy-dom';

/** What lit-html and our own modules reach for on the global object. */
const GLOBALS = [
  'document',
  'DocumentFragment',
  'Node',
  'Element',
  'HTMLElement',
  'HTMLSelectElement',
  'HTMLOptionElement',
  'HTMLButtonElement',
  'HTMLTableElement',
  'Text',
  'Comment',
  'Event',
  'CustomEvent',
  'KeyboardEvent',
  'MutationObserver',
  'NodeFilter',
  'SVGElement',
  // Named without `window.` by the page wiring, so they have to be global.
  'history',
  'ResizeObserver',
];

/**
 * Install a fresh window's globals and return its document.
 *
 * @param {string} [url] The address the document should believe it is at,
 *   which is what relative `href` attributes resolve against.
 * @returns {Document}
 */
export function installDom(url = 'https://seattleelections.guide/e/wa-2026-primary/comparisons/') {
  const window = new Window({ url });
  for (const name of GLOBALS) {
    if (name in window) {
      // @ts-expect-error assigning browser globals onto the Node global object
      globalThis[name] = window[name];
    }
  }
  // @ts-expect-error the same, for the window itself
  globalThis.window = window;
  return /** @type {Document} */ (/** @type {unknown} */ (window.document));
}
