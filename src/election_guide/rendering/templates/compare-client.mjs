// Interactive comparison-page glue. State is admitted and serialized only by
// compare-url.mjs; cell arithmetic is owned only by compare-signals.mjs.
import { readClientPayload } from './client-payload.mjs';
import { migrateCompareState } from './compare-migrate.mjs';
import { cellAgreement, createColumnSignalEngine, rowDiffers } from './compare-signals.mjs';
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
   * The denominator default is numeric because the array is already numeric:
   * an integer rational such as `3` splits to one element. `'1'` divided the
   * same after coercion, so this reads as it always behaved.
   *
   * @param {string|null|undefined} rational
   */
  const percentage = (rational) => {
    if (rational == null) return '';
    const [top, bottom = 1] = String(rational).split('/').map(Number);
    const value = (top / bottom) * 100;
    return `${Number.isInteger(value) ? value : value.toFixed(1)}%`;
  };

  let state = {
    columns: [...payload.default_columns],
    differencesOnly: false,
    contestedOnly: false,
    section: 'all',
  };
  let disclosure = '';
  /** @type {string|null} */
  let lastLocationKey = null;
  const locationKey = () =>
    `${window.location.pathname}${window.location.search}${window.location.hash}`;

  function stateFromLocation() {
    const decoded = decodeCompareFragment(window.location.hash, context);
    if (decoded.status === 'valid') {
      state = { ...decoded.state, columns: [...decoded.state.columns] };
      if (state.columns.length < 2) state.columns = [...payload.default_columns];
      disclosure = '';
    } else if (decoded.status === 'absent') {
      state = {
        columns: [...payload.default_columns],
        differencesOnly: false,
        contestedOnly: false,
        section: 'all',
      };
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
    render();
  }

  /**
   * @param {string} value
   * @param {string} text
   * @param {string} current
   * @param {ReadonlySet<string>} used
   * @returns {HTMLOptionElement}
   */
  function option(value, text, current, used) {
    const element = document.createElement('option');
    element.value = value;
    element.textContent = text;
    element.selected = value === current;
    element.disabled = used.has(value) && value !== current;
    return element;
  }

  /**
   * Which control the next render should return focus to, so a change made
   * from the keyboard does not drop the reader back at the top of the page.
   *
   * @typedef {{ kind: 'picker'|'title', index: number }} FocusTarget
   */

  /**
   * @param {string} signal
   * @param {number} index
   * @param {HTMLButtonElement} title
   * @returns {HTMLSelectElement}
   */
  function pickerFor(signal, index, title) {
    const select = document.createElement('select');
    select.className = 'comparison-column-picker';
    select.dataset.comparisonColumn = String(index);
    select.setAttribute(
      'aria-label',
      index === 0
        ? `Change reference, currently ${labelFor(signal)}`
        : `Change ${labelFor(signal)} comparison`,
    );
    const used = new Set(state.columns);

    const publishedGroup = document.createElement('optgroup');
    publishedGroup.label = 'Published result';
    publishedGroup.append(option(ALL_SOURCES_TOKEN, 'All sources', signal, used));
    select.append(publishedGroup);

    const categoryGroup = document.createElement('optgroup');
    categoryGroup.label = 'Categories';
    for (const category of categories) {
      const suffix = isComparison(category.code) ? ' (Comparison only)' : '';
      categoryGroup.append(option(category.code, `${category.label}${suffix}`, signal, used));
    }
    select.append(categoryGroup);

    for (const category of categories) {
      const group = document.createElement('optgroup');
      group.label = isComparison(category.code)
        ? `${category.label} (Comparison only)`
        : category.label;
      const members = category.member_source_codes
        .filter((code) => sources.has(code))
        .sort((left, right) => labelFor(left).localeCompare(labelFor(right)));
      for (const member of members) {
        const suffix = isComparison(member) ? ' (Comparison only)' : '';
        group.append(option(member, `${labelFor(member)}${suffix}`, signal, used));
      }
      if (members.length) select.append(group);
    }
    select.addEventListener('change', () => {
      const next = [...state.columns];
      next[index] = select.value;
      if (new Set(next).size !== next.length) return;
      state.columns = next;
      if (writeState()) render({ kind: 'title', index });
    });
    let closing = false;
    /** @param {boolean} restoreFocus */
    const closeEditor = (restoreFocus) => {
      if (closing || !select.isConnected) return;
      closing = true;
      select.replaceWith(title);
      syncTitleHeights();
      if (restoreFocus) window.setTimeout(() => title.focus(), 0);
    };
    select.addEventListener('keydown', (event) => {
      if (event.key !== 'Escape') return;
      event.preventDefault();
      event.stopPropagation();
      closeEditor(true);
    });
    select.addEventListener('blur', () => closeEditor(false));
    return select;
  }

  /**
   * @param {string} signal
   * @param {number} index
   * @returns {HTMLButtonElement}
   */
  function titleFor(signal, index) {
    const title = document.createElement('button');
    title.type = 'button';
    title.className = 'comparison-column-title comparison-column-title-action';
    title.dataset.comparisonTitle = String(index);
    title.setAttribute(
      'aria-label',
      index === 0
        ? `Change reference, currently ${labelFor(signal)}`
        : `Change ${labelFor(signal)} comparison`,
    );
    title.textContent = labelFor(signal);
    title.addEventListener('click', () => {
      const picker = pickerFor(signal, index, title);
      title.replaceWith(picker);
      syncTitleHeights();
      picker.focus();
    });
    return title;
  }

  function syncTitleHeights() {
    head.style.removeProperty('--comparison-title-height');
    const titles = [...head.querySelectorAll('.comparison-column-title')];
    if (!titles.length) return;
    const titleHeight = Math.max(...titles.map((title) => title.scrollHeight));
    head.style.setProperty('--comparison-title-height', `${titleHeight}px`);
  }

  /** @param {FocusTarget|null} target */
  function restoreHeadFocus(target) {
    if (!target) return;
    const selector =
      target.kind === 'picker'
        ? `[data-comparison-column="${target.index}"]`
        : `[data-comparison-title="${target.index}"]`;
    /** @type {HTMLElement|null} */ (head.querySelector(selector))?.focus();
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
   * @param {readonly string[]} visible
   * @param {FocusTarget|null} focusTarget
   */
  function renderHead(visible, focusTarget) {
    table.style.setProperty('--comparison-column-count', String(visible.length));
    head.replaceChildren();
    const row = document.createElement('tr');
    const race = document.createElement('th');
    race.scope = 'col';
    const raceLabel = document.createElement('span');
    raceLabel.className = 'comparison-column-label';
    raceLabel.textContent = 'Race';
    race.append(raceLabel);
    row.append(race);
    visible.forEach((signal, index) => {
      const cell = document.createElement('th');
      cell.scope = 'col';
      cell.dataset.columnSignal = signal;
      const heading = document.createElement('div');
      heading.className = 'comparison-column-heading';
      const title = titleFor(signal, index);
      heading.append(title);
      if (focusTarget?.kind === 'picker' && focusTarget.index === index) {
        title.replaceWith(pickerFor(signal, index, title));
      }
      const actions = document.createElement('span');
      actions.className = 'comparison-column-actions';
      if (state.columns.length > 2) {
        const remove = document.createElement('button');
        remove.type = 'button';
        remove.className = 'comparison-column-remove';
        remove.dataset.comparisonRemove = String(index);
        remove.setAttribute('aria-label', `Remove ${labelFor(signal)}`);
        remove.title = `Remove ${labelFor(signal)}`;
        const removeIcon = document.createElement('span');
        removeIcon.className = 'comparison-column-action-icon';
        removeIcon.setAttribute('aria-hidden', 'true');
        removeIcon.textContent = '×';
        remove.append(removeIcon);
        remove.addEventListener('click', () => {
          state.columns = state.columns.filter((_, columnIndex) => columnIndex !== index);
          const focusIndex = Math.min(index, state.columns.length - 1);
          if (writeState()) render({ kind: 'title', index: focusIndex });
        });
        actions.append(remove);
      }
      if (index === state.columns.length - 1 && state.columns.length < 3) {
        const add = document.createElement('button');
        add.type = 'button';
        add.className = 'comparison-column-add';
        add.setAttribute('aria-label', 'Add comparison column');
        add.title = 'Add comparison column';
        const addIcon = document.createElement('span');
        addIcon.className = 'comparison-column-action-icon';
        addIcon.setAttribute('aria-hidden', 'true');
        addIcon.textContent = '+';
        add.append(addIcon);
        add.addEventListener('click', () => {
          const available = nextUnusedSignal();
          if (!available) return;
          state.columns = [...state.columns, available];
          if (writeState()) render({ kind: 'picker', index: state.columns.length - 1 });
        });
        actions.append(add);
      }
      if (actions.childElementCount > 0) heading.append(actions);
      else heading.classList.add('comparison-column-plain');
      cell.append(heading);
      row.append(cell);
    });
    head.append(row);
    syncTitleHeights();
    restoreHeadFocus(focusTarget);
  }

  /**
   * @param {string} signal
   * @param {import('./compare-signals.mjs').ComparisonCell} cell
   * @param {ComparisonDisplayRace} display
   * @param {import('./compare-signals.mjs').ComparisonCell} reference
   * @param {boolean} isReference
   * @returns {HTMLTableCellElement}
   */
  function cellFor(signal, cell, display, reference, isReference) {
    const labels = candidateLabels(display);
    const element = document.createElement('td');
    element.className = 'comparison-cell';
    element.dataset.columnSignal = signal;
    element.dataset.columnLabel = labelFor(signal);
    element.dataset.cellKind = cell.kind;
    const agreement = isReference ? 'reference' : cellAgreement(cell, reference);
    element.dataset.agreement = agreement;
    const picks = document.createElement('span');
    picks.className = 'comparison-cell-picks';
    picks.textContent =
      cell.kind === 'outside_scope'
        ? 'Outside district'
        : cell.leadingPickIds?.map((id) => labels[id]).join(' / ') || '—';
    if (cell.kind === 'blank') picks.title = 'No endorsement published';
    element.append(picks);
    if (cell.share != null) {
      const meta = document.createElement('span');
      meta.className = 'comparison-cell-meta';
      const count =
        cell.kind === 'aggregate'
          ? `${cell.endorsingCount} of ${cell.memberCount} sources`
          : `${cell.endorsingCount} sources`;
      meta.textContent = `${percentage(cell.share)} · ${count}`;
      element.append(meta);
    }
    return element;
  }

  /**
   * @typedef {object} SectionRow
   * @property {ComparisonDisplayRace} display
   * @property {PersonalizationRace} race
   * @property {import('./compare-signals.mjs').ComparisonCell[]} configuredCells
   * @property {boolean} differs
   */

  /** @param {readonly string[]} visible */
  function renderBody(visible) {
    table.querySelectorAll('tbody').forEach((body) => {
      body.remove();
    });
    /** @type {Map<string, { label: string, displays: SectionRow[] }>} */
    const sections = new Map();
    let total = 0;
    let differCount = 0;
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
        section = { label: display.section_label, displays: [] };
        sections.set(display.section_id, section);
      }
      section.displays.push({ display, race, configuredCells, differs });
    }
    let shown = 0;
    for (const [sectionId, section] of sections) {
      const body = document.createElement('tbody');
      body.dataset.comparisonSection = sectionId;
      const heading = document.createElement('tr');
      heading.className = 'comparison-section-heading';
      const headingCell = document.createElement('th');
      headingCell.scope = 'rowgroup';
      headingCell.colSpan = visible.length + 1;
      headingCell.textContent = section.label;
      heading.append(headingCell);
      body.append(heading);
      for (const item of section.displays) {
        // `race` stays on the row record for the lit-html conversion of this
        // table to render from (#238); this loop only needs the display
        // labels and the cells.
        const { display, configuredCells, differs } = item;
        shown += 1;
        const row = document.createElement('tr');
        row.dataset.comparisonRace = display.race_id;
        row.dataset.rowDiffers = String(differs);
        const raceHeading = document.createElement('th');
        raceHeading.scope = 'row';
        raceHeading.className = 'comparison-race';
        const link = document.createElement('a');
        link.href = `../#race-${display.race_id}`;
        link.textContent = display.race_label;
        raceHeading.append(link);
        if (differs) {
          const differsLabel = document.createElement('span');
          differsLabel.className = 'comparison-race-differs';
          differsLabel.textContent = 'Differs';
          raceHeading.append(differsLabel);
        }
        row.append(raceHeading);
        const reference = configuredCells[0];
        visible.forEach((signal, index) => {
          row.append(cellFor(signal, configuredCells[index], display, reference, index === 0));
        });
        body.append(row);
      }
      table.append(body);
    }
    if (shown === 0) {
      const body = document.createElement('tbody');
      const row = document.createElement('tr');
      row.className = 'comparison-empty';
      const cell = document.createElement('td');
      cell.colSpan = visible.length + 1;
      const allAgree = state.differencesOnly && total > 0 && differCount === 0;
      const message = document.createElement('p');
      message.textContent = allAgree
        ? 'These signals agree in every race they share under the current filters.'
        : 'No races match the current filters.';
      cell.append(message);
      const reset = document.createElement('button');
      reset.type = 'button';
      reset.className = 'comparison-reset';
      reset.textContent = allAgree ? 'Show all rows' : 'Reset filters';
      reset.addEventListener('click', () => {
        state.differencesOnly = false;
        if (!allAgree) {
          state.contestedOnly = false;
          state.section = 'all';
        }
        if (writeState('replace')) render();
      });
      cell.append(reset);
      row.append(cell);
      body.append(row);
      table.append(body);
    }
    status.textContent = `${shown} of ${total} races shown · ${differCount} differ`;
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

  /** @param {FocusTarget|null} [focusTarget] */
  function render(focusTarget = null) {
    const visible = state.columns;
    notice.hidden = disclosure === '';
    notice.textContent = disclosure;
    renderHead(visible, focusTarget);
    renderBody(visible);
    syncControls();
    window.requestAnimationFrame(syncComparisonScrollHint);
  }

  sectionFilter.addEventListener('change', () => {
    state.section = sectionFilter.value;
    if (writeState('replace')) render();
  });
  toggleInput('[data-comparison-full]').addEventListener('change', () => {
    state.differencesOnly = false;
    if (writeState('replace')) render();
  });
  toggleInput('[data-comparison-differences]').addEventListener('change', () => {
    state.differencesOnly = true;
    if (writeState('replace')) render();
  });
  toggleInput('[data-comparison-all-races]').addEventListener('change', () => {
    state.contestedOnly = false;
    if (writeState('replace')) render();
  });
  toggleInput('[data-comparison-contested]').addEventListener('change', () => {
    state.contestedOnly = true;
    if (writeState('replace')) render();
  });
  /** @type {NodeListOf<HTMLAnchorElement>} */
  (document.querySelectorAll('.comparison-presets a')).forEach((link) => {
    link.addEventListener('click', (event) => {
      const decoded = decodeCompareFragment(link.hash, context);
      if (decoded.status !== 'valid') return;
      event.preventDefault();
      state = { ...decoded.state };
      if (writeState()) render();
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
  render();
}
