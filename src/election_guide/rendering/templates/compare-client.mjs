// Interactive comparison-page glue. State is admitted and serialized only by
// compare-url.mjs; cell arithmetic is owned only by compare-signals.mjs; the
// table's markup is owned only by compare-table.mjs.
//
// This module is wiring: it holds the view-model state, listens, and hands lit
// a view model. The two regions it owns are taken over on different terms
// (docs/FRONTEND.md § Rendering, "the region-takeover idiom"):
//
//   head  Taken over at boot, because the column controls live in it and the
//         audited baseline cannot render them.
//   body  Left as the server rendered it until the state stops being the
//         audited default. Most visits never change it, and those visits now
//         do no work on the largest region of the page.
//
// Takeover is one-way. Once lit owns a region, returning to the audited default
// re-renders it from the audited view model rather than putting the server's
// markup back — `compare-markup-parity.test.mjs` is what makes those two the
// same thing.
import { render } from 'lit-html';
import { readClientPayload } from './client-payload.mjs';
import { migrateCompareState } from './compare-migrate.mjs';
import { cellAgreement, createColumnSignalEngine, rowDiffers } from './compare-signals.mjs';
import { comparisonBodyTemplate, comparisonHeadTemplate } from './compare-table.mjs';
import {
  ALL_SOURCES_TOKEN,
  compareContext,
  decodeCompareFragment,
  encodeCompareFragment,
} from './compare-url.mjs';

/**
 * The Comparisons page renders all of these before its entry runs, so each
 * lookup is asserted rather than guarded. Only the bindings element is
 * genuinely optional — the page is inert without a payload.
 *
 * @template {Element} T
 * @param {string} selector
 * @returns {T}
 */
function required(selector) {
  return /** @type {T} */ (document.querySelector(selector));
}

/** Attach the interactive comparison table to a rendered Comparisons page. */
export function wireComparisons() {
  // A payload this build cannot read leaves the server-rendered comparison
  // table exactly as it is, behind the notice readClientPayload reveals
  // (docs/FRONTEND.md, The data contract).
  const admitted = readClientPayload(document);
  if (admitted === null) return;
  const payload = /** @type {ComparisonsPayload} */ (admitted);
  const personalization = payload.personalization;
  const comparisons = payload.comparisons;
  const context = compareContext(
    personalization,
    payload.data_version,
    comparisons,
    payload.default_columns,
  );
  const engine = createColumnSignalEngine(personalization, comparisons);
  /** @type {HTMLTableElement} */
  const table = required('[data-comparison-table]');
  /** @type {HTMLElement} */
  const head = required('[data-comparison-head]');
  /** @type {HTMLElement} */
  const grid = required('[data-comparison-grid]');
  /** @type {HTMLElement} */
  const scrollHint = required('[data-comparison-scroll-hint]');
  /** @type {HTMLElement} */
  const notice = required('[data-comparison-hidden-notice]');
  /** @type {HTMLElement} */
  const status = required('[data-comparison-status]');
  /** @type {HTMLSelectElement} */
  const sectionFilter = required('[data-comparison-section-filter]');
  /** @type {HTMLElement} */
  const stickyControls = required('[data-sticky-controls]');
  const contestedIds = new Set(payload.contested_race_ids);
  const races = new Map(personalization.races.map((race) => [race.race_id, race]));
  const categories = personalization.categories.filter((category) => category.selectable);
  const sources = new Map(
    personalization.sources
      .filter((source) => source.selectable)
      .map((source) => [source.code, source]),
  );

  function syncStickyControlsHeight() {
    document.documentElement.style.setProperty(
      '--sticky-controls-height',
      `${stickyControls.getBoundingClientRect().height}px`,
    );
  }
  syncStickyControlsHeight();
  new ResizeObserver(syncStickyControlsHeight).observe(stickyControls);

  function syncComparisonScrollHint() {
    grid.style.setProperty('--comparison-scroll-left', `${grid.scrollLeft}px`);
    const maximum = Math.max(0, grid.scrollWidth - grid.clientWidth);
    const hasOverflow = maximum > 2;
    scrollHint.hidden = !hasOverflow;
    grid.tabIndex = hasOverflow ? 0 : -1;
    if (!hasOverflow) {
      scrollHint.textContent = '';
      scrollHint.removeAttribute('data-scroll-position');
      return;
    }
    const atStart = grid.scrollLeft <= 2;
    const atEnd = grid.scrollLeft >= maximum - 2;
    const position = atStart ? 'start' : atEnd ? 'end' : 'middle';
    scrollHint.dataset.scrollPosition = position;
    scrollHint.textContent =
      position === 'start'
        ? 'More columns →'
        : position === 'end'
          ? '← More columns'
          : '← More columns →';
  }
  grid.addEventListener('scroll', syncComparisonScrollHint, { passive: true });
  new ResizeObserver(syncComparisonScrollHint).observe(grid);

  /** @param {string} signal */
  const labelFor = (signal) => {
    if (signal === ALL_SOURCES_TOKEN) return 'All sources';
    return (
      categories.find((category) => category.code === signal)?.label ??
      payload.source_labels[signal] ??
      signal
    );
  };
  /** @param {string} signal */
  const isComparison = (signal) => {
    const category = categories.find((item) => item.code === signal);
    return (
      category?.panel_role === 'comparison' || sources.get(signal)?.panel_role === 'comparison'
    );
  };
  /** @param {ComparisonDisplayRace} display */
  const candidateLabels = (display) => ({
    ...display.candidate_names,
    ...display.measure_response_labels,
  });
  /**
   * The audited renderer's percentage, mirrored.
   *
   * `comparison_percentage_label` scales the share as a rational, prints a
   * whole percentage with no decimal, and otherwise rounds to one place
   * half-to-even. `toFixed` rounds halves away from zero instead, which made
   * the same 9/16 share read 56.2% on the audited page and 56.3% the moment a
   * reader touched it. The markup-parity test found that; the arithmetic here
   * stays on integers so the two sides cannot drift apart again over a float
   * (docs/FRONTEND.md § Cross-language mirrors).
   *
   * The denominator default is numeric because the array is already numeric:
   * an integer rational such as `3` splits to one element.
   *
   * @param {string|null|undefined} rational
   */
  const percentage = (rational) => {
    if (rational == null) return '';
    const [top, bottom = 1] = String(rational).split('/').map(Number);
    if ((top * 100) % bottom === 0) return `${(top * 100) / bottom}%`;
    const tenths = top * 1000;
    const whole = Math.floor(tenths / bottom);
    const doubled = 2 * (tenths - whole * bottom);
    const rounded = doubled > bottom || (doubled === bottom && whole % 2 !== 0) ? whole + 1 : whole;
    return `${(rounded / 10).toFixed(1)}%`;
  };

  const auditedDefault = () => ({
    columns: [...payload.default_columns],
    differencesOnly: false,
    contestedOnly: false,
    section: 'all',
  });

  let state = auditedDefault();
  /**
   * Which column, if any, is showing its picker instead of its title. State,
   * not DOM: the render decides which control exists, so no handler swaps
   * nodes and nothing has to be put back afterwards.
   *
   * @type {number|null}
   */
  let editingColumn = null;
  /**
   * Whether lit has taken each region over from the server. One-way: after the
   * first takeover the audited default is re-rendered from the audited view
   * model, never handed back to the server's markup.
   */
  let headTakenOver = false;
  let bodyTakenOver = false;
  let disclosure = '';
  /** @type {string|null} */
  let lastLocationKey = null;
  const locationKey = () =>
    `${window.location.pathname}${window.location.search}${window.location.hash}`;

  /** True while the reader is still looking at exactly what the server rendered. */
  function showingAuditedDefault() {
    const audited = auditedDefault();
    return (
      !state.differencesOnly &&
      !state.contestedOnly &&
      state.section === audited.section &&
      state.columns.length === audited.columns.length &&
      state.columns.every((signal, index) => signal === audited.columns[index])
    );
  }

  function stateFromLocation() {
    const decoded = decodeCompareFragment(window.location.hash, context);
    if (decoded.status === 'valid') {
      state = { ...decoded.state, columns: [...decoded.state.columns] };
      if (state.columns.length < 2) state.columns = [...payload.default_columns];
      disclosure = '';
    } else if (decoded.status === 'absent') {
      state = auditedDefault();
      disclosure = '';
    } else if (decoded.status === 'stale_version') {
      const migration = migrateCompareState(decoded, personalization, context);
      if (migration.status === 'migrated' || migration.status === 'fallback') {
        state = { ...migration.state, columns: [...migration.state.columns] };
        disclosure =
          migration.status === 'migrated'
            ? 'This comparison link was updated for the current source list.'
            : 'This comparison link could not be restored completely, so the default comparison is shown.';
        writeState('replace');
      }
    }
  }

  function writeState(mode = 'push') {
    const encoded = encodeCompareFragment(state, context);
    if (encoded.status !== 'ok') return false;
    const target = `${window.location.pathname}${window.location.search}#${encoded.fragment}`;
    if (mode === 'replace') history.replaceState({ comparison: true }, '', target);
    else history.pushState({ comparison: true }, '', target);
    lastLocationKey = locationKey();
    return true;
  }

  function syncFromLocation() {
    if (locationKey() === lastLocationKey) return;
    stateFromLocation();
    lastLocationKey = locationKey();
    editingColumn = null;
    renderPage();
  }

  /**
   * The options one picker offers, grouped as the control presents them.
   *
   * @param {string} signal
   * @returns {import('./compare-table.mjs').ComparisonOptionGroupView[]}
   */
  function groupsFor(signal) {
    const used = new Set(state.columns);
    /**
     * @param {string} value
     * @param {string} text
     * @returns {import('./compare-table.mjs').ComparisonOptionView}
     */
    const option = (value, text) => ({
      value,
      label: text,
      selected: value === signal,
      disabled: used.has(value) && value !== signal,
    });

    const groups = [
      { label: 'Published result', options: [option(ALL_SOURCES_TOKEN, 'All sources')] },
      {
        label: 'Categories',
        options: categories.map((category) =>
          option(
            category.code,
            `${category.label}${isComparison(category.code) ? ' (Comparison only)' : ''}`,
          ),
        ),
      },
    ];
    for (const category of categories) {
      const members = category.member_source_codes
        .filter((code) => sources.has(code))
        .sort((left, right) => labelFor(left).localeCompare(labelFor(right)));
      if (!members.length) continue;
      groups.push({
        label: isComparison(category.code) ? `${category.label} (Comparison only)` : category.label,
        options: members.map((member) =>
          option(member, `${labelFor(member)}${isComparison(member) ? ' (Comparison only)' : ''}`),
        ),
      });
    }
    return groups;
  }

  /** @returns {import('./compare-table.mjs').ComparisonHeadView} */
  function headView() {
    return {
      columns: state.columns.map((signal, index) => ({
        signal,
        index,
        title: labelFor(signal),
        controlLabel:
          index === 0
            ? `Change reference, currently ${labelFor(signal)}`
            : `Change ${labelFor(signal)} comparison`,
        editing: editingColumn === index,
        groups: editingColumn === index ? groupsFor(signal) : [],
        removeLabel: state.columns.length > 2 ? `Remove ${labelFor(signal)}` : null,
        canAdd: index === state.columns.length - 1 && state.columns.length < 3,
      })),
    };
  }

  function nextUnusedSignal() {
    const preferred = ['stim', 'Glab', 'Gdem', 'Genv', 'kcdm', 'sicl', 'wslc'];
    return (
      preferred.find((signal) => !state.columns.includes(signal)) ??
      [...categories.map((item) => item.code), ...sources.keys()].find(
        (signal) => !state.columns.includes(signal),
      )
    );
  }

  /**
   * The only focus calls left in this module, and each one moves focus to a
   * control that did not exist before the render: a picker the reader just
   * opened, or the title that replaced the picker they were in. Focus on a
   * control that survives a render is not touched, because lit's keyed
   * rendering keeps that element (docs/FRONTEND.md § Rendering).
   *
   * @param {'title'|'picker'} kind
   * @param {number} index
   */
  function focusHeadControl(kind, index) {
    const selector =
      kind === 'picker'
        ? `[data-comparison-column="${index}"]`
        : `[data-comparison-title="${index}"]`;
    /** @type {HTMLElement|null} */ (head.querySelector(selector))?.focus();
  }

  /** @type {import('./compare-table.mjs').ComparisonHeadActions} */
  const headActions = {
    onEdit(index) {
      editingColumn = index;
      renderHead();
      focusHeadControl('picker', index);
    },
    onChoose(index, value) {
      const next = [...state.columns];
      next[index] = value;
      if (new Set(next).size !== next.length) return;
      state.columns = next;
      editingColumn = null;
      if (writeState()) {
        renderPage();
        focusHeadControl('title', index);
      }
    },
    onCancel(index) {
      if (editingColumn !== index) return;
      editingColumn = null;
      renderHead();
      // Deliberately asynchronous: the keydown that closed the picker is still
      // being dispatched on an element lit has already removed, and focusing
      // during that dispatch is what the previous implementation had to defer
      // too.
      window.setTimeout(() => focusHeadControl('title', index), 0);
    },
    onDismiss(index) {
      // Focus has already moved on; closing the picker must not chase it.
      if (editingColumn !== index) return;
      editingColumn = null;
      renderHead();
    },
    onRemove(index) {
      state.columns = state.columns.filter((_, columnIndex) => columnIndex !== index);
      editingColumn = null;
      const focusIndex = Math.min(index, state.columns.length - 1);
      if (writeState()) {
        renderPage();
        focusHeadControl('title', focusIndex);
      }
    },
    onAdd() {
      const available = nextUnusedSignal();
      if (available === undefined) return;
      state.columns = [...state.columns, available];
      editingColumn = state.columns.length - 1;
      if (writeState()) {
        renderPage();
        focusHeadControl('picker', state.columns.length - 1);
      }
    },
  };

  function syncTitleHeights() {
    head.style.removeProperty('--comparison-title-height');
    const titles = [...head.querySelectorAll('.comparison-column-title')];
    if (!titles.length) return;
    const titleHeight = Math.max(...titles.map((title) => title.scrollHeight));
    head.style.setProperty('--comparison-title-height', `${titleHeight}px`);
  }

  function renderHead() {
    table.style.setProperty('--comparison-column-count', String(state.columns.length));
    if (!headTakenOver) {
      // The audited head is static text; the interactive one replaces it once,
      // and lit owns the region from here.
      head.replaceChildren();
      headTakenOver = true;
    }
    render(comparisonHeadTemplate(headView(), headActions), head);
    syncTitleHeights();
  }

  /**
   * @param {string} signal
   * @param {import('./compare-signals.mjs').ComparisonCell} cell
   * @param {ComparisonDisplayRace} display
   * @param {import('./compare-signals.mjs').ComparisonCell} reference
   * @param {boolean} isReference
   * @returns {import('./compare-table.mjs').ComparisonCellView}
   */
  function cellView(signal, cell, display, reference, isReference) {
    const labels = candidateLabels(display);
    const leadingPickIds = cell.leadingPickIds ?? [];
    const share = cell.share ?? null;
    const meta =
      share === null
        ? null
        : `${percentage(share)} · ${
            cell.kind === 'aggregate'
              ? `${cell.endorsingCount} of ${cell.memberCount} sources`
              : `${cell.endorsingCount} sources`
          }`;
    return {
      signal,
      columnLabel: labelFor(signal),
      kind: cell.kind,
      agreement: isReference ? 'reference' : cellAgreement(cell, reference),
      leadingPickIds,
      share,
      explicitSourceCount: cell.endorsingCount ?? null,
      choiceLabels: leadingPickIds.map((id) => labels[id]),
      meta,
    };
  }

  /**
   * The row groups the current state selects, plus the counts the status line
   * reports. Pure with respect to the DOM: this is the whole of what the body
   * template needs.
   *
   * @returns {{ view: import('./compare-table.mjs').ComparisonBodyView, status: string,
   *   allAgree: boolean }}
   */
  function bodyView() {
    /** @type {Map<string, import('./compare-table.mjs').ComparisonSectionView>} */
    const sections = new Map();
    let total = 0;
    let differCount = 0;
    let shown = 0;
    for (const display of comparisons.display_index) {
      if (state.section !== 'all' && display.section_id !== state.section) continue;
      if (state.contestedOnly && !contestedIds.has(display.race_id)) continue;
      total += 1;
      // Every display row names a published race: both come from the same
      // payload, and the comparison contract is built from `personalization`.
      const race = /** @type {PersonalizationRace} */ (races.get(display.race_id));
      const configuredCells = state.columns.map((signal) => engine.resolveColumn(signal, race));
      const differs = rowDiffers(configuredCells);
      if (differs) differCount += 1;
      if (state.differencesOnly && !differs) continue;
      let section = sections.get(display.section_id);
      if (section === undefined) {
        section = {
          sectionId: display.section_id,
          sectionLabel: display.section_label,
          rows: [],
        };
        sections.set(display.section_id, section);
      }
      const reference = configuredCells[0];
      shown += 1;
      section.rows.push({
        raceId: display.race_id,
        raceLabel: display.race_label,
        raceHref: `../#race-${display.race_id}`,
        differs,
        cells: state.columns.map((signal, index) =>
          cellView(signal, configuredCells[index], display, reference, index === 0),
        ),
      });
    }
    const allAgree = state.differencesOnly && total > 0 && differCount === 0;
    return {
      view: {
        sections: [...sections.values()],
        columnCount: state.columns.length,
        empty:
          shown > 0
            ? null
            : {
                message: allAgree
                  ? 'These signals agree in every race they share under the current filters.'
                  : 'No races match the current filters.',
                action: allAgree ? 'Show all rows' : 'Reset filters',
              },
      },
      status: `${shown} of ${total} races shown · ${differCount} differ`,
      allAgree,
    };
  }

  function renderBody() {
    // The audited default is already on the page. Until the reader asks for
    // something else, this region does no DOM work at all.
    if (!bodyTakenOver && showingAuditedDefault()) return;
    const { view, status: statusText, allAgree } = bodyView();
    if (!bodyTakenOver) {
      for (const body of [...table.querySelectorAll('tbody')]) body.remove();
      bodyTakenOver = true;
    }
    render(
      comparisonBodyTemplate(view, () => {
        state.differencesOnly = false;
        if (!allAgree) {
          state.contestedOnly = false;
          state.section = 'all';
        }
        if (writeState('replace')) renderPage();
      }),
      table,
    );
    status.textContent = statusText;
  }

  /**
   * The four filter toggles sit in the static controls bar, outside every
   * region a render replaces, and are looked up on demand exactly as before.
   *
   * @param {string} selector
   * @returns {HTMLInputElement}
   */
  const toggleInput = (selector) =>
    /** @type {HTMLInputElement} */ (document.querySelector(selector));

  function syncControls() {
    sectionFilter.value = state.section;
    toggleInput('[data-comparison-full]').checked = !state.differencesOnly;
    toggleInput('[data-comparison-differences]').checked = state.differencesOnly;
    toggleInput('[data-comparison-all-races]').checked = !state.contestedOnly;
    toggleInput('[data-comparison-contested]').checked = state.contestedOnly;
  }

  // Everything one state change implies: both regions, the controls, the hint.
  function renderPage() {
    notice.hidden = disclosure === '';
    notice.textContent = disclosure;
    renderHead();
    renderBody();
    syncControls();
    window.requestAnimationFrame(syncComparisonScrollHint);
  }

  sectionFilter.addEventListener('change', () => {
    state.section = sectionFilter.value;
    if (writeState('replace')) renderPage();
  });
  toggleInput('[data-comparison-full]').addEventListener('change', () => {
    state.differencesOnly = false;
    if (writeState('replace')) renderPage();
  });
  toggleInput('[data-comparison-differences]').addEventListener('change', () => {
    state.differencesOnly = true;
    if (writeState('replace')) renderPage();
  });
  toggleInput('[data-comparison-all-races]').addEventListener('change', () => {
    state.contestedOnly = false;
    if (writeState('replace')) renderPage();
  });
  toggleInput('[data-comparison-contested]').addEventListener('change', () => {
    state.contestedOnly = true;
    if (writeState('replace')) renderPage();
  });
  /** @type {NodeListOf<HTMLAnchorElement>} */
  (document.querySelectorAll('.comparison-presets a')).forEach((link) => {
    link.addEventListener('click', (event) => {
      const decoded = decodeCompareFragment(link.hash, context);
      if (decoded.status !== 'valid') return;
      event.preventDefault();
      state = { ...decoded.state };
      if (writeState()) renderPage();
    });
  });
  window.addEventListener('popstate', syncFromLocation);
  window.addEventListener('hashchange', syncFromLocation);
  /** @type {number|undefined} */
  let resizeTimer;
  window.addEventListener('resize', () => {
    clearTimeout(resizeTimer);
    resizeTimer = setTimeout(() => {
      syncTitleHeights();
      syncComparisonScrollHint();
    }, 80);
  });

  stateFromLocation();
  lastLocationKey = locationKey();
  renderPage();
}
