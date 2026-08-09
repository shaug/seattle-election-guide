// Interactive comparison-page glue. State is admitted and serialized only by
// compare-url.mjs; the address bar it lives in is touched only by
// compare-route.mjs; cell arithmetic is owned only by compare-signals.mjs; the
// table's markup is owned only by compare-table.mjs. This module names neither
// `location` nor `history` (docs/FRONTEND.md § State and URLs).
//
// Every way the page can fail to read or write its link ends in something the
// reader can see. A decode this build cannot use, a migration that cannot
// resolve, and a change the codec refuses each resolve to a stated outcome —
// text, an address bar that is cleaned or left alone, and a defined state —
// rather than to nothing at all.
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
import { createCompareRouter } from './compare-route.mjs';
import { cellAgreement, createColumnSignalEngine, rowDiffers } from './compare-signals.mjs';
import {
  comparisonBodyTemplate,
  comparisonHeadTemplate,
  comparisonPercentageLabel,
} from './compare-table.mjs';
import {
  ALL_SOURCES_TOKEN,
  CERTIFIED_RESULT_TOKEN,
  compareContext,
  decodeCompareFragment,
  encodeCompareFragment,
} from './compare-url.mjs';

/**
 * What a reader is told when the link they arrived on says nothing this page
 * can read. Each of these ends the same way — with what is on the screen now —
 * because a notice that only reports a failure leaves the reader guessing what
 * they are looking at (docs/FRONTEND.md § State and URLs; docs/DESIGN.md
 * § Voice).
 */
const UNREADABLE_LINK_NOTICE =
  'This comparison link could not be read, so the default comparison is shown.';
const MIGRATED_LINK_NOTICE = 'This comparison link was updated for the current source list.';
const PARTIAL_LINK_NOTICE =
  'This comparison link could not be restored completely, so the default comparison is shown.';
const UNMIGRATABLE_LINK_NOTICE =
  'This comparison link could not be updated for the current source list, so the default ' +
  'comparison is shown.';

/**
 * And what they are told when a change they just made cannot be written into a
 * link. The change is not applied, because a comparison the address bar cannot
 * name is one no reload, copy, or Back press could reproduce.
 */
const UNSHAREABLE_VIEW_NOTICE =
  'That change could not be put into a shareable link, so the comparison is unchanged.';

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
    payload.results_available,
  );
  const raceResults = new Map(Object.entries(payload.race_results));
  const engine = createColumnSignalEngine(personalization, comparisons, raceResults);
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
    if (signal === CERTIFIED_RESULT_TOKEN) return 'Certified result';
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
  const router = createCompareRouter();

  /** @returns {import('./compare-url.mjs').CompareState} */
  const auditedDefault = () => ({
    columns: [...payload.default_columns],
    differencesOnly: false,
    contestedOnly: false,
    section: 'all',
  });

  /**
   * An independent copy, so that the state the address bar names and the state
   * the reader is editing are never the same array.
   *
   * @param {import('./compare-url.mjs').CompareState} value
   * @returns {import('./compare-url.mjs').CompareState}
   */
  const snapshot = (value) => ({ ...value, columns: [...value.columns] });

  let state = auditedDefault();
  /**
   * The state the address bar currently names: what a change the codec refuses
   * returns to, so the page never shows a comparison no link could reproduce.
   *
   * @type {import('./compare-url.mjs').CompareState}
   */
  let committed = auditedDefault();
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
  /**
   * How this load resolved the link it arrived on. Persistent: it describes a
   * shared link, not an ongoing in-page navigation.
   */
  let linkNotice = '';
  /**
   * Why the reader's last change did not take, when it did not. Cleared by the
   * next change that does, so it never outlives the action it explains.
   */
  let changeNotice = '';
  /** The more recent of the two is what the page says. */
  const disclosure = () => changeNotice || linkNotice;
  /** @type {string|null} */
  let writtenAddress = null;

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

  /**
   * One decoded fragment resolved to the state the page should show, what the
   * reader is told about it, and what becomes of the address it arrived in.
   *
   * A `null` state means the fragment says nothing about this comparison — the
   * skip link is one, and so is any other in-page anchor — so the page keeps
   * what it has and says nothing about it.
   *
   * @typedef {object} CompareOutcome
   * @property {import('./compare-url.mjs').CompareState|null} state
   * @property {string} notice
   * @property {'keep'|'clean'|'rewrite'} address
   */

  /**
   * Resolve one decoded fragment. Every decode status has a branch here, and
   * every branch that is not `valid` or `absent` carries an explanation: a link
   * that fails silently is the defect the rule names (docs/FRONTEND.md § State
   * and URLs).
   *
   * @param {import('./compare-url.mjs').CompareDecodeResult} decoded
   * @returns {CompareOutcome}
   */
  function resolve(decoded) {
    if (decoded.status === 'valid') {
      return { state: decoded.state, notice: '', address: 'keep' };
    }
    if (decoded.status === 'absent') {
      return { state: auditedDefault(), notice: '', address: 'keep' };
    }
    if (decoded.status === 'stale_version') {
      const migration = migrateCompareState(decoded, personalization, context);
      if (migration.status === 'rejected') {
        return { state: auditedDefault(), notice: UNMIGRATABLE_LINK_NOTICE, address: 'clean' };
      }
      return {
        state: migration.state,
        notice: migration.status === 'migrated' ? MIGRATED_LINK_NOTICE : PARTIAL_LINK_NOTICE,
        address: 'rewrite',
      };
    }
    // `malformed`. An ordinary in-page anchor is not a comparison link and the
    // codec says so by name, so clicking around the page never manufactures an
    // explanation or disturbs the address bar.
    if (decoded.reason === 'unrecognized_fragment') {
      return { state: null, notice: '', address: 'keep' };
    }
    return { state: auditedDefault(), notice: UNREADABLE_LINK_NOTICE, address: 'clean' };
  }

  /**
   * Put the current state in the address bar.
   *
   * @param {'push'|'replace'} mode
   * @returns {boolean} False when the codec refuses the state.
   */
  function writeFragment(mode) {
    const encoded = encodeCompareFragment(state, context);
    if (encoded.status !== 'ok') return false;
    router.write(encoded.fragment, mode);
    committed = snapshot(state);
    writtenAddress = router.key();
    return true;
  }

  /** Drop an unusable fragment, so a reload reproduces what the reader sees. */
  function clearFragment() {
    router.clearFragment();
    committed = snapshot(state);
    writtenAddress = router.key();
  }

  /** Adopt whatever the live address says, and do what it implies. */
  function readAddress() {
    const outcome = resolve(decodeCompareFragment(router.fragment(), context));
    if (outcome.state === null) {
      writtenAddress = router.key();
      return;
    }
    state = snapshot(outcome.state);
    linkNotice = outcome.notice;
    changeNotice = '';
    if (outcome.address === 'clean') {
      clearFragment();
      return;
    }
    // A migrated state replaces the stale link it was resolved from. If the
    // codec will not write it, nothing can carry it: the page falls back to the
    // audited default, clears the link, and says which of the two happened.
    if (outcome.address === 'rewrite' && !writeFragment('replace')) {
      state = auditedDefault();
      linkNotice = UNMIGRATABLE_LINK_NOTICE;
      clearFragment();
      return;
    }
    committed = snapshot(state);
    writtenAddress = router.key();
  }

  /**
   * Apply the change the reader just made, and render.
   *
   * A state the codec refuses is not applied. The page and the address bar stay
   * on the one state a link can reproduce, and the reader is told why their
   * change did not take — an unencodable state is a failure, and failures are
   * surfaced rather than dropped (docs/FRONTEND.md § State and URLs).
   *
   * @param {'push'|'replace'} [mode]
   * @returns {boolean}
   */
  function commit(mode = 'push') {
    if (writeFragment(mode)) {
      changeNotice = '';
      renderPage();
      return true;
    }
    state = snapshot(committed);
    editingColumn = null;
    changeNotice = UNSHAREABLE_VIEW_NOTICE;
    renderPage();
    return false;
  }

  function syncFromAddress() {
    if (router.key() === writtenAddress) return;
    readAddress();
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
    ];
    // The state gate (docs/RESULTS.md, Rendering § The comparison view): the
    // picker offers "Certified result" only while the election's certified
    // results file exists, exactly like every other results surface. Never
    // at the reference position (`editingColumn === 0`, the index this
    // picker is always rendered for -- `headView` only calls `groupsFor`
    // when `editingColumn === index`): every other column is scored
    // *against* the reference, and a `result`-kind cell is never a
    // `DataCell` (compare-signals.mjs `isDataCell`), so a `gres` reference
    // would silently neutralize agreement for the whole row, not just its
    // own column. `compare-url.mjs`'s codec enforces the same restriction,
    // so a crafted or previously shared link cannot reach it either.
    if (payload.results_available && editingColumn !== 0) {
      groups.push({
        label: 'Certified result',
        options: [option(CERTIFIED_RESULT_TOKEN, 'Certified result')],
      });
    }
    groups.push({
      label: 'Categories',
      options: categories.map((category) =>
        option(
          category.code,
          `${category.label}${isComparison(category.code) ? ' (Comparison only)' : ''}`,
        ),
      ),
    });
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
      commit();
      // The picker the reader was in has been replaced by a title either way:
      // by the column they chose, or — when the codec refused it — by the one
      // that was there before. Clamped, because a refusal restores the column
      // count as well as the columns.
      focusHeadControl('title', Math.min(index, state.columns.length - 1));
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
      commit();
      focusHeadControl('title', Math.min(index, state.columns.length - 1));
    },
    onAdd() {
      const available = nextUnusedSignal();
      if (available === undefined) return;
      state.columns = [...state.columns, available];
      editingColumn = state.columns.length - 1;
      // A refused column leaves no picker to focus, so focus goes to the last
      // title instead of chasing a control the render did not produce.
      if (commit()) focusHeadControl('picker', state.columns.length - 1);
      else focusHeadControl('title', state.columns.length - 1);
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
    // A result cell's meta line is pre-formatted by `resultCell`
    // (compare-signals.mjs): its own vote shares and certification status,
    // not the share-then-source-count grammar every other kind's meta line
    // shares (docs/RESULTS.md, Rendering § The comparison view).
    const meta =
      cell.kind === 'result'
        ? cell.meta
        : share === null
          ? null
          : `${comparisonPercentageLabel(share)} · ${
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
        commit('replace');
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
  // `syncControls` is what puts a refused change back on the screen: the
  // checkbox the reader clicked reports the state that survived, not the one
  // they asked for.
  function renderPage() {
    const text = disclosure();
    notice.hidden = text === '';
    notice.textContent = text;
    renderHead();
    renderBody();
    syncControls();
    window.requestAnimationFrame(syncComparisonScrollHint);
  }

  sectionFilter.addEventListener('change', () => {
    state.section = sectionFilter.value;
    commit('replace');
  });
  toggleInput('[data-comparison-full]').addEventListener('change', () => {
    state.differencesOnly = false;
    commit('replace');
  });
  toggleInput('[data-comparison-differences]').addEventListener('change', () => {
    state.differencesOnly = true;
    commit('replace');
  });
  toggleInput('[data-comparison-all-races]').addEventListener('change', () => {
    state.contestedOnly = false;
    commit('replace');
  });
  toggleInput('[data-comparison-contested]').addEventListener('change', () => {
    state.contestedOnly = true;
    commit('replace');
  });
  /** @type {NodeListOf<HTMLAnchorElement>} */
  (document.querySelectorAll('.comparison-presets a')).forEach((link) => {
    link.addEventListener('click', (event) => {
      // A preset this build cannot read is left to the browser, which navigates
      // to it and hands it back through the fragment listener below — where the
      // reader is told what became of it, rather than nothing happening.
      const decoded = decodeCompareFragment(link.hash, context);
      if (decoded.status !== 'valid') return;
      event.preventDefault();
      state = snapshot(decoded.state);
      commit();
    });
  });
  router.onHistoryChange(syncFromAddress);
  router.onFragmentChange(syncFromAddress);
  /** @type {number|undefined} */
  let resizeTimer;
  window.addEventListener('resize', () => {
    clearTimeout(resizeTimer);
    resizeTimer = setTimeout(() => {
      syncTitleHeights();
      syncComparisonScrollHint();
    }, 80);
  });

  readAddress();
  renderPage();
}
