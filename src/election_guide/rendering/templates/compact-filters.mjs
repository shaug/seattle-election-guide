// General-only compact presentation. Existing page controllers still own values.
import { html, nothing, render, svg } from 'lit-html';

/** Lucide-style outline icons; labels, not the glyphs, name each control.
 * @param {string} kind */
export function filterIcon(kind) {
  const paths = {
    precinct: svg`<path d="M20 10c0 6-8 12-8 12S4 16 4 10a8 8 0 1 1 16 0Z"/><circle cx="12" cy="10" r="2.5"/>`,
    view: svg`<path d="M2 12s3.5-7 10-7 10 7 10 7-3.5 7-10 7S2 12 2 12Z"/><circle cx="12" cy="12" r="3"/>`,
    races: svg`<path d="M3 6h18M6 12h12M9 18h6"/>`,
    ballot: svg`<path d="M8 3h8v10H8zM5 10l-2 5v6h18v-6l-2-5M3 15h18M10 7l2 2 3-3"/>`,
  };
  return html`<svg class="compact-filter-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${paths[/** @type {keyof typeof paths} */ (kind)] ?? nothing}</svg>`;
}

/** @param {string} name @param {string} value @param {string} label
 * @param {boolean} [disabled] @param {boolean} [active] @param {string} [detail] */
function trigger(name, value, label, disabled = false, active = false, detail = '') {
  return html`<button class="compact-filter-trigger" type="button" data-filter-open=${name} aria-haspopup="dialog" aria-controls=${`compact-${name}-dialog`} aria-expanded="false" aria-label=${label} title=${label} ?disabled=${disabled} ?data-active=${active}>${filterIcon(name)}<span class="compact-filter-value">${value}</span>${name === 'ballot' ? html`<span class="compact-filter-value compact-ballot-scope">${detail}</span><span class="compact-filter-dot" aria-hidden="true"></span>` : nothing}<span class="compact-filter-arrow" aria-hidden="true"></span></button>`;
}

/** Project resolved controller state without reading labels or state back from markup.
 * @param {{scope:string,scopeLabel:string,view:string,races:string,viewDisabled?:boolean}} state */
export function projectCompactFilters(state) {
  const bar = document.querySelector('[data-compact-filters]');
  if (!bar) return;
  const scopeLabel = state.scope === 'all' ? 'All ballot races' : state.scopeLabel;
  for (const [name, value, label, disabled] of [
    ['view', state.view, `View: ${state.view}`, state.viewDisabled ?? false],
    ['races', state.races, `Races: ${state.races}`, false],
    [
      'ballot',
      'Ballot',
      `Ballot${state.scope === 'all' ? '' : ' filter active'}: ${scopeLabel}`,
      false,
    ],
  ]) {
    const target = /** @type {HTMLElement|null} */ (
      bar.querySelector(`[data-filter-trigger="${name}"]`)
    );
    if (target)
      render(
        trigger(
          String(name),
          String(value),
          String(label),
          Boolean(disabled),
          name === 'ballot' && state.scope !== 'all',
          name === 'ballot' ? scopeLabel : '',
        ),
        target,
      );
  }
  for (const dialog of /** @type {NodeListOf<HTMLDialogElement>} */ (
    bar.querySelectorAll('[data-filter-editor][open]')
  ))
    dialog.close();
  bar.dispatchEvent(new Event('compact-filter-fit'));
}

/** Wire ephemeral native editors and measure the actual bar after fonts/load/resize. */
export function wireCompactFilters() {
  const bar = /** @type {HTMLElement|null} */ (document.querySelector('[data-compact-filters]'));
  const view = document.defaultView;
  if (!bar || !view) return;
  /** Clamp the editor's real box to the current visual viewport.
   * @param {HTMLDialogElement} dialog @param {Element} opener */
  const placeEditor = (dialog, opener) => {
    const viewport = view.visualViewport;
    const left = viewport?.offsetLeft ?? 0;
    const top = viewport?.offsetTop ?? 0;
    const width = viewport?.width ?? document.documentElement.clientWidth;
    const height = viewport?.height ?? document.documentElement.clientHeight;
    /** @param {string} name @param {number} value */
    const set = (name, value) => {
      const pixels = `${value}px`;
      if (dialog.style.getPropertyValue(name) !== pixels) dialog.style.setProperty(name, pixels);
    };
    set('--filter-width', Math.max(0, Math.min(320, width - 16)));
    set('--filter-height', Math.max(0, height - 16));
    const anchor = opener.getBoundingClientRect();
    const box = dialog.getBoundingClientRect();
    set('--filter-left', Math.max(left + 8, Math.min(anchor.left, left + width - box.width - 8)));
    set(
      '--filter-top',
      Math.max(top + 8, Math.min(anchor.bottom + 3, top + height - box.height - 8)),
    );
  };
  const placeOpenEditors = () => {
    const dialogs = /** @type {NodeListOf<HTMLDialogElement>} */ (
      bar.querySelectorAll('[data-filter-editor][open]')
    );
    for (const dialog of dialogs) {
      const opener = bar.querySelector(`[data-filter-open="${dialog.dataset.filterEditor}"]`);
      if (opener) placeEditor(dialog, opener);
    }
    return dialogs.length > 0;
  };
  // Anchor movement need not emit a resize event (for example a transform).
  // Track only while a modal is open; unchanged geometry produces no writes.
  let frame = 0;
  const trackEditors = () => {
    frame = 0;
    if (placeOpenEditors()) frame = view.requestAnimationFrame(trackEditors);
  };
  const fit = () => {
    // Measure the wide candidates unshrunk. The compact code is already vetted
    // against the catalog; no ellipsis or slicing is used to manufacture fit.
    bar.dataset.cues = 'arrows';
    bar.dataset.precinctDisplay = 'full';
    bar.dataset.ballotDetail = 'full';
    bar.dataset.spacing = 'normal';
    bar.style.removeProperty('--compact-filter-padding');
    const required = () =>
      [...bar.querySelectorAll('.compact-filter-trigger')].reduce(
        (sum, el) => sum + el.getBoundingClientRect().width,
        0,
      );
    const separators = bar.querySelectorAll('.compact-filter-slot').length;
    const available = bar.getBoundingClientRect().width - separators;
    if (required() > available) bar.dataset.ballotDetail = 'compact';
    if (required() > available) bar.dataset.precinctDisplay = 'short';
    if (required() > available) bar.dataset.cues = 'underlines';
    // Underlines alone may still overflow with a supported fallback font.
    // Reclaim only the padding needed; labels, icons and target minima stay put.
    if (required() > available) {
      const count = bar.querySelectorAll('.compact-filter-trigger').length;
      const padding = Math.max(0, 2 - Math.ceil((required() - available) / (2 * count)));
      bar.style.setProperty('--compact-filter-padding', `${padding}px`);
    }
    if (required() > available) bar.dataset.spacing = 'tight';
    const controls = bar.querySelector('.compact-filter-controls');
    const count = bar.querySelector('.filter-control-status');
    bar.dataset.countLine = 'separate';
    if (
      controls &&
      count &&
      controls.getBoundingClientRect().width + 2 * (count.getBoundingClientRect().width + 12) <=
        bar.getBoundingClientRect().width
    )
      bar.dataset.countLine = 'inline';
    placeOpenEditors();
  };
  /** @param {HTMLDialogElement} dialog */
  const restore = (dialog) => {
    const name = dialog.dataset.filterEditor;
    const opener = /** @type {HTMLButtonElement|null} */ (
      bar.querySelector(`[data-filter-open="${name}"]`)
    );
    opener?.setAttribute('aria-expanded', 'false');
    opener?.focus();
  };
  bar.addEventListener('click', (event) => {
    const opener = /** @type {Element|null} */ (event.target)?.closest('[data-filter-open]');
    if (!opener) return;
    const dialog = /** @type {HTMLDialogElement|null} */ (
      bar.querySelector(`#${opener.getAttribute('aria-controls')}`)
    );
    if (!dialog) return;
    /** @type {HTMLElement} */ (opener).focus();
    opener.setAttribute('aria-expanded', 'true');
    dialog.showModal();
    placeEditor(dialog, opener);
    if (!frame) frame = view.requestAnimationFrame(trackEditors);
    /** @type {HTMLElement|null} */ (
      dialog.querySelector(
        'input:checked:not(:disabled),select:not(:disabled),[data-filter-cancel]',
      )
    )?.focus();
  });
  for (const dialog of /** @type {NodeListOf<HTMLDialogElement>} */ (
    bar.querySelectorAll('[data-filter-editor]')
  )) {
    const dismiss = () => {
      dialog.close();
      restore(dialog);
    };
    dialog.querySelector('[data-filter-cancel]')?.addEventListener('click', dismiss);
    dialog.addEventListener('change', dismiss);
    dialog.addEventListener('cancel', (event) => {
      event.preventDefault();
      dismiss();
    });
    // Native close already returns focus. A delayed close event must not steal
    // it from another trigger the reader has since reached.
    dialog.addEventListener('close', () => {
      if (!bar.querySelector('[data-filter-editor][open]')) {
        view.cancelAnimationFrame(frame);
        frame = 0;
      }
      if (!dialog.open)
        bar
          .querySelector(`[data-filter-open="${dialog.dataset.filterEditor}"]`)
          ?.setAttribute('aria-expanded', 'false');
    });
  }
  bar.addEventListener('compact-filter-fit', fit);
  const observer = new ResizeObserver(fit);
  observer.observe(bar);
  document.fonts?.ready.then(fit);
  fit();
}
