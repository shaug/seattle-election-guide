// General-only compact presentation. Existing page controllers still own values.
import { html, nothing, render, svg } from 'lit-html';

/** Presentation-only complete value families; controllers retain selection ownership.
 * @type {WeakMap<Element, {full:string[],short:string[]}>} */
const precinctFamilies = new WeakMap();
/** @type {WeakMap<Element, string[]>} */
const ballotFamilies = new WeakMap();

/** @param {string[]} full @param {string[]} short */
export function reservePrecinctValues(full, short) {
  const bar = document.querySelector('[data-compact-filters]');
  if (bar)
    precinctFamilies.set(bar, { full: ['Precinct', ...full], short: ['Precinct', ...short] });
}

/** Clamp any native filter editor without owning its draft or dismissal.
 * @param {HTMLDialogElement} dialog @param {Element} opener
 * @param {number} [preferredWidth] */
export function placeFilterEditor(dialog, opener, preferredWidth = 320) {
  const view = dialog.ownerDocument.defaultView;
  if (!view) return;
  const viewport = view.visualViewport;
  const left = viewport?.offsetLeft ?? 0;
  const top = viewport?.offsetTop ?? 0;
  const width = viewport?.width ?? dialog.ownerDocument.documentElement.clientWidth;
  const height = viewport?.height ?? dialog.ownerDocument.documentElement.clientHeight;
  /** @param {string} name @param {number} value */
  const set = (name, value) => {
    const pixels = `${value}px`;
    if (dialog.style.getPropertyValue(name) !== pixels) dialog.style.setProperty(name, pixels);
  };
  set('--filter-width', Math.max(0, Math.min(preferredWidth, width - 16)));
  set('--filter-height', Math.max(0, height - 16));
  const anchor = opener.getBoundingClientRect();
  const box = dialog.getBoundingClientRect();
  set('--filter-left', Math.max(left + 8, Math.min(anchor.left, left + width - box.width - 8)));
  set(
    '--filter-top',
    Math.max(top + 8, Math.min(anchor.bottom + 3, top + height - box.height - 8)),
  );
}

/** Measure the complete families in the actual font and current cue/identity mode.
 * A hidden multiline probe measures the widest complete value, without canvas
 * font approximations, truncation, selected-value sizing or fixed breakpoints.
 * @param {HTMLElement} bar */
function reserveControlWidths(bar) {
  for (const button of bar.querySelectorAll('.compact-filter-trigger')) {
    const probe = /** @type {HTMLElement} */ (button.cloneNode(true));
    probe.setAttribute('aria-hidden', 'true');
    probe.setAttribute('tabindex', '-1');
    probe.style.cssText =
      'position:absolute;visibility:hidden;pointer-events:none;overflow:hidden;width:max-content;';
    const precinct = button.hasAttribute('data-precinct-open');
    const control = /** @type {HTMLSelectElement|null} */ (
      button.querySelector('[data-filter-native]')
    );
    const role = control?.dataset.filterNative;
    if (precinct) probe.classList.add('precinct-selected');
    const families = precinctFamilies.get(bar);
    const options = control ? [...control.options].map((option) => option.textContent ?? '') : [];
    for (const value of probe.querySelectorAll('.compact-filter-value')) {
      let family = options;
      if (precinct)
        family =
          (value.classList.contains('precinct-short') ? families?.short : families?.full) ?? [];
      if (role === 'ballot')
        family = value.classList.contains('compact-ballot-scope')
          ? (ballotFamilies.get(bar) ?? [])
          : ['Ballot'];
      value.textContent = [...family, value.textContent ?? ''].join('\n');
      /** @type {HTMLElement} */ (value).style.whiteSpace = 'pre';
    }
    button.parentElement?.append(probe);
    // Keep layout's fractional precision: rounding each track up can invent
    // overflow even when the complete families fit the actual container.
    const width = probe.getBoundingClientRect().width;
    probe.remove();
    /** @type {HTMLElement} */ (button).style.width = `${width}px`;
  }
}

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

/** Decorative closed face; the real select owns pointer, keyboard and accessibility.
 * @param {string} name @param {string} value @param {string} detail */
function filterFace(name, value, detail) {
  return html`${filterIcon(name)}<span class="compact-filter-value">${value}</span>${name === 'ballot' ? html`<span class="compact-filter-value compact-ballot-scope">${detail}</span><span class="compact-filter-dot" aria-hidden="true"></span>` : nothing}<span class="compact-filter-arrow" aria-hidden="true"></span>`;
}

/** Project resolved controller state without reading labels or state back from markup.
 * @param {{scope:string,scopeLabel:string,view:string,races:string,viewDisabled?:boolean,scopeLabels?:string[]}} state */
export function projectCompactFilters(state) {
  const bar = document.querySelector('[data-compact-filters]');
  if (!bar) return;
  const scopeLabel = state.scope === 'all' ? 'All ballot races' : state.scopeLabel;
  ballotFamilies.set(bar, state.scopeLabels ?? [scopeLabel]);
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
    const target = /** @type {HTMLSpanElement|null} */ (
      bar.querySelector(`span[data-filter-face="${name}"]`)
    );
    const select = /** @type {HTMLSelectElement|null} */ (
      bar.querySelector(`[data-filter-native="${name}"]`)
    );
    if (target && select) {
      render(filterFace(String(name), String(value), name === 'ballot' ? scopeLabel : ''), target);
      select.disabled = Boolean(disabled);
      select.setAttribute('aria-label', String(label));
      select.title = String(label);
      const wrapper = select.closest('.compact-filter-trigger');
      wrapper?.setAttribute('aria-label', String(label));
      const active = name === 'ballot' && state.scope !== 'all';
      wrapper?.toggleAttribute('data-active', active);
      select.toggleAttribute('data-active', active);
    }
  }
  bar.dispatchEvent(new Event('compact-filter-fit'));
}

/** Measure the actual native-control bar after fonts/load/resize. */
export function wireCompactFilters() {
  const bar = /** @type {HTMLElement|null} */ (document.querySelector('[data-compact-filters]'));
  const view = document.defaultView;
  if (!bar || !view) return;
  const fit = () => {
    // Measure the wide candidates unshrunk. The compact code is already vetted
    // against the catalog; no ellipsis or slicing is used to manufacture fit.
    bar.dataset.cues = 'arrows';
    bar.dataset.precinctDisplay = 'full';
    bar.dataset.ballotDetail = 'full';
    bar.dataset.spacing = 'normal';
    bar.style.removeProperty('--compact-filter-padding');
    const required = () => {
      reserveControlWidths(bar);
      return [...bar.querySelectorAll('.compact-filter-trigger')].reduce(
        (sum, el) => sum + el.getBoundingClientRect().width,
        0,
      );
    };
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
    if (required() > available) bar.dataset.spacing = 'stacked';
    reserveControlWidths(bar);
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
  };
  bar.addEventListener('compact-filter-fit', fit);
  const observer = new ResizeObserver(fit);
  observer.observe(bar);
  document.fonts?.ready.then(fit);
  fit();
}
