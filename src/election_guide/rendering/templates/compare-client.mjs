// Interactive comparison-page glue. State is admitted and serialized only by
// compare-url.mjs; cell arithmetic is owned only by compare-signals.mjs.
const comparisonBindingsElement = document.querySelector('[data-comparison-bindings]');
if (comparisonBindingsElement) {
  const payload = JSON.parse(comparisonBindingsElement.textContent);
  const personalization = payload.personalization;
  const comparisons = payload.comparisons;
  const context = compareContext(
    personalization,
    payload.data_version,
    comparisons,
    payload.default_columns,
  );
  const engine = createColumnSignalEngine(personalization, comparisons);
  const table = document.querySelector('[data-comparison-table]');
  const head = document.querySelector('[data-comparison-head]');
  const notice = document.querySelector('[data-comparison-hidden-notice]');
  const status = document.querySelector('[data-comparison-status]');
  const sectionFilter = document.querySelector('[data-comparison-section-filter]');
  const contestedIds = new Set(payload.contested_race_ids);
  const races = new Map(personalization.races.map((race) => [race.race_id, race]));
  const displays = new Map(comparisons.display_index.map((display) => [display.race_id, display]));
  const categories = personalization.categories.filter((category) => category.selectable);
  const sources = new Map(
    personalization.sources.filter((source) => source.selectable).map((source) => [source.code, source]),
  );

  const labelFor = (signal) => {
    if (signal === ALL_SOURCES_TOKEN) return 'All sources';
    return categories.find((category) => category.code === signal)?.label
      ?? payload.source_labels[signal]
      ?? signal;
  };
  const isComparison = (signal) => {
    const category = categories.find((item) => item.code === signal);
    return category?.panel_role === 'comparison' || sources.get(signal)?.panel_role === 'comparison';
  };
  const coverageFor = (signal) => {
    if (signal === ALL_SOURCES_TOKEN) {
      const count = personalization.sources.filter((source) => source.panel_role !== 'comparison').length;
      return `Audited baseline · ${count} sources`;
    }
    const category = categories.find((item) => item.code === signal);
    if (category) return `${category.member_source_codes.length} sources, equal weight`;
    const count = payload.source_coverage[signal] ?? 0;
    return isComparison(signal)
      ? `Comparison only · endorsed in ${count} races`
      : `Endorsed in ${count} races`;
  };
  const candidateLabels = (display) => ({
    ...display.candidate_names,
    ...display.measure_response_labels,
  });
  const percentage = (rational) => {
    if (rational == null) return '';
    const [top, bottom = '1'] = String(rational).split('/').map(Number);
    const value = (top / bottom) * 100;
    return `${Number.isInteger(value) ? value : value.toFixed(1)}%`;
  };

  let state = {
    columns: [...payload.default_columns],
    differencesOnly: false,
    contestedOnly: false,
    section: 'all',
  };

  function stateFromLocation() {
    const decoded = decodeCompareFragment(window.location.hash, context);
    if (decoded.status === 'valid') state = { ...decoded.state };
    else if (decoded.status === 'absent') {
      state = {
        columns: [...payload.default_columns],
        differencesOnly: false,
        contestedOnly: false,
        section: 'all',
      };
    }
  }

  function writeState(mode = 'push') {
    const encoded = encodeCompareFragment(state, context);
    if (encoded.status !== 'ok') return false;
    const target = `${window.location.pathname}${window.location.search}#${encoded.fragment}`;
    if (mode === 'replace') history.replaceState({ comparison: true }, '', target);
    else history.pushState({ comparison: true }, '', target);
    return true;
  }

  function option(value, text, current, used) {
    const element = document.createElement('option');
    element.value = value;
    element.textContent = text;
    element.selected = value === current;
    element.disabled = used.has(value) && value !== current;
    return element;
  }

  function pickerFor(signal, index) {
    const select = document.createElement('select');
    select.className = 'comparison-column-picker';
    select.dataset.comparisonColumn = String(index);
    select.setAttribute('aria-label', `Column ${index + 1} signal`);
    const used = new Set(state.columns);
    select.append(option(ALL_SOURCES_TOKEN, 'All sources', signal, used));

    const categoryGroup = document.createElement('optgroup');
    categoryGroup.label = 'Categories';
    for (const category of categories) {
      categoryGroup.append(option(category.code, category.label, signal, used));
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
      if (writeState()) render();
    });
    return select;
  }

  function visibleColumns() {
    return state.columns.slice(0, window.matchMedia('(max-width: 720px)').matches ? 2 : 3);
  }

  function renderHead(visible) {
    head.replaceChildren();
    const row = document.createElement('tr');
    const race = document.createElement('th');
    race.scope = 'col';
    race.textContent = 'Race';
    row.append(race);
    visible.forEach((signal, index) => {
      const cell = document.createElement('th');
      cell.scope = 'col';
      cell.dataset.columnSignal = signal;
      const heading = document.createElement('div');
      heading.className = 'comparison-column-heading';
      if (index === 0) {
        const badge = document.createElement('span');
        badge.className = 'comparison-baseline-badge';
        badge.textContent = 'Baseline';
        heading.append(badge);
      }
      const pickerRow = document.createElement('div');
      pickerRow.className = 'comparison-column-heading-row';
      pickerRow.append(pickerFor(signal, index));
      if (state.columns.length > 2) {
        const remove = document.createElement('button');
        remove.type = 'button';
        remove.className = 'comparison-column-remove';
        remove.dataset.comparisonRemove = String(index);
        remove.setAttribute('aria-label', `Remove ${labelFor(signal)} column`);
        remove.textContent = 'Remove';
        remove.addEventListener('click', () => {
          state.columns = state.columns.filter((_, columnIndex) => columnIndex !== index);
          if (writeState()) render();
        });
        pickerRow.append(remove);
      }
      heading.append(pickerRow);
      const meta = document.createElement('span');
      meta.className = 'comparison-column-meta';
      meta.textContent = coverageFor(signal);
      heading.append(meta);
      cell.append(heading);
      row.append(cell);
    });
    if (state.columns.length < 3) {
      const cell = document.createElement('th');
      cell.scope = 'col';
      const add = document.createElement('button');
      add.type = 'button';
      add.className = 'comparison-column-add';
      add.textContent = 'Add column';
      add.addEventListener('click', () => {
        const preferred = ['stim', 'Glab', 'Gdem', 'Genv', 'kcdm', 'sicl', 'wslc'];
        const available = preferred.find((signal) => !state.columns.includes(signal))
          ?? [ALL_SOURCES_TOKEN, ...categories.map((item) => item.code), ...sources.keys()]
            .find((signal) => !state.columns.includes(signal));
        if (!available) return;
        state.columns = [...state.columns, available];
        if (writeState()) render();
      });
      cell.append(add);
      row.append(cell);
    }
    head.append(row);
  }

  function cellFor(signal, race, display) {
    const cell = engine.resolveColumn(signal, race);
    const labels = candidateLabels(display);
    const element = document.createElement('td');
    element.className = 'comparison-cell';
    element.dataset.columnSignal = signal;
    element.dataset.cellKind = cell.kind;
    const picks = document.createElement('span');
    picks.className = 'comparison-cell-picks';
    picks.textContent = cell.kind === 'outside_scope'
      ? 'Outside district'
      : (cell.leadingPickIds?.map((id) => labels[id]).join(' / ') || '—');
    element.append(picks);
    if (cell.share != null) {
      const meta = document.createElement('span');
      meta.className = 'comparison-cell-meta';
      const count = cell.kind === 'aggregate'
        ? `${cell.endorsingCount} of ${cell.memberCount} sources`
        : `${cell.endorsingCount} sources`;
      meta.textContent = `${percentage(cell.share)} · ${count}`;
      element.append(meta);
    }
    return element;
  }

  function renderBody(visible) {
    table.querySelectorAll('tbody').forEach((body) => body.remove());
    const sections = new Map();
    for (const display of comparisons.display_index) {
      if (state.section !== 'all' && display.section_id !== state.section) continue;
      if (state.contestedOnly && !contestedIds.has(display.race_id)) continue;
      if (!sections.has(display.section_id)) {
        sections.set(display.section_id, { label: display.section_label, displays: [] });
      }
      sections.get(display.section_id).displays.push(display);
    }
    let shown = 0;
    for (const [sectionId, section] of sections) {
      const body = document.createElement('tbody');
      body.dataset.comparisonSection = sectionId;
      const heading = document.createElement('tr');
      heading.className = 'comparison-section-heading';
      const headingCell = document.createElement('th');
      headingCell.scope = 'rowgroup';
      headingCell.colSpan = visible.length + 1 + (state.columns.length < 3 ? 1 : 0);
      headingCell.textContent = section.label;
      heading.append(headingCell);
      body.append(heading);
      for (const display of section.displays) {
        shown += 1;
        const row = document.createElement('tr');
        row.dataset.comparisonRace = display.race_id;
        const raceHeading = document.createElement('th');
        raceHeading.scope = 'row';
        raceHeading.className = 'comparison-race';
        const link = document.createElement('a');
        link.href = `../#race-${display.race_id}`;
        link.textContent = display.race_label;
        raceHeading.append(link);
        row.append(raceHeading);
        const race = races.get(display.race_id);
        for (const signal of visible) row.append(cellFor(signal, race, display));
        if (state.columns.length < 3) row.append(document.createElement('td'));
        body.append(row);
      }
      table.append(body);
    }
    if (shown === 0) {
      const body = document.createElement('tbody');
      const row = document.createElement('tr');
      row.className = 'comparison-empty';
      const cell = document.createElement('td');
      cell.colSpan = visible.length + 1 + (state.columns.length < 3 ? 1 : 0);
      cell.textContent = 'No races match the current filters.';
      row.append(cell);
      body.append(row);
      table.append(body);
    }
    status.textContent = `${shown} races shown.`;
  }

  function syncControls() {
    sectionFilter.value = state.section;
    document.querySelector('[data-comparison-complete]').setAttribute('aria-pressed', String(!state.contestedOnly));
    document.querySelector('[data-comparison-contested]').setAttribute('aria-pressed', String(state.contestedOnly));
    document.querySelector('[data-comparison-all-rows]').setAttribute('aria-pressed', String(!state.differencesOnly));
    document.querySelector('[data-comparison-differences]').setAttribute('aria-pressed', String(state.differencesOnly));
  }

  function render() {
    const visible = visibleColumns();
    const hidden = state.columns.length - visible.length;
    notice.hidden = hidden === 0;
    notice.textContent = hidden
      ? `${hidden} configured column hidden at this width. It remains configured and counted.`
      : '';
    renderHead(visible);
    renderBody(visible);
    syncControls();
  }

  sectionFilter.addEventListener('change', () => {
    state.section = sectionFilter.value;
    if (writeState()) render();
  });
  document.querySelector('[data-comparison-complete]').addEventListener('click', () => {
    state.contestedOnly = false;
    if (writeState()) render();
  });
  document.querySelector('[data-comparison-contested]').addEventListener('click', () => {
    state.contestedOnly = true;
    if (writeState()) render();
  });
  document.querySelector('[data-comparison-all-rows]').addEventListener('click', () => {
    state.differencesOnly = false;
    if (writeState()) render();
  });
  document.querySelector('[data-comparison-differences]').addEventListener('click', () => {
    // #122 owns row-difference filtering and presentation. #121 persists the
    // control state without changing which rows are presented.
    state.differencesOnly = true;
    if (writeState()) render();
  });
  document.querySelector('[data-comparison-copy]').addEventListener('click', async () => {
    const result = await shareOrCopyLink(window.location.href, document.title);
    if (result === 'copied') status.textContent = 'Link copied.';
    else if (result === 'shared') status.textContent = 'Share menu opened.';
    else if (result === 'failed') status.textContent = `Copy failed. Link: ${window.location.href}`;
  });
  document.querySelectorAll('.comparison-presets a').forEach((link) => {
    link.addEventListener('click', (event) => {
      const decoded = decodeCompareFragment(link.hash, context);
      if (decoded.status !== 'valid') return;
      event.preventDefault();
      state = { ...decoded.state };
      if (writeState()) render();
    });
  });
  window.addEventListener('popstate', () => { stateFromLocation(); render(); });
  window.addEventListener('hashchange', () => { stateFromLocation(); render(); });
  let resizeTimer;
  window.addEventListener('resize', () => {
    clearTimeout(resizeTimer);
    resizeTimer = setTimeout(render, 80);
  });

  stateFromLocation();
  render();
}
