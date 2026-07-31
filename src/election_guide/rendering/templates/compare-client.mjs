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
  const copyStatus = document.querySelector('[data-comparison-copy-status]');
  const sectionFilter = document.querySelector('[data-comparison-section-filter]');
  const contestedIds = new Set(payload.contested_race_ids);
  const races = new Map(personalization.races.map((race) => [race.race_id, race]));
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
    if (signal === ALL_SOURCES_TOKEN) return '';
    const count = comparisons.display_index.filter((display) => {
      const cell = engine.resolveColumn(signal, races.get(display.race_id));
      return (cell.leadingPickIds?.length ?? 0) > 0;
    }).length;
    return `Endorsed in ${count} races`;
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

  function withFixedBaseline(columns) {
    return [ALL_SOURCES_TOKEN, ...columns.filter((signal) => signal !== ALL_SOURCES_TOKEN)].slice(0, 3);
  }

  function stateFromLocation() {
    const decoded = decodeCompareFragment(window.location.hash, context);
    if (decoded.status === 'valid') {
      state = { ...decoded.state, columns: withFixedBaseline(decoded.state.columns) };
      if (state.columns.length < 2) state.columns = [...payload.default_columns];
    }
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
    select.setAttribute('aria-label', `Change ${labelFor(signal)} comparison`);
    const used = new Set(state.columns);

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
      if (writeState()) render();
    });
    return select;
  }

  function renderHead(visible) {
    head.replaceChildren();
    const row = document.createElement('tr');
    const race = document.createElement('th');
    race.scope = 'col';
    const raceLabel = document.createElement('span');
    raceLabel.className = 'comparison-column-label';
    raceLabel.textContent = 'Race';
    race.append(raceLabel);
    const add = document.createElement('button');
    add.type = 'button';
    add.className = 'comparison-column-add';
    add.disabled = state.columns.length >= 3;
    add.textContent = add.disabled ? 'Maximum 3 comparisons' : 'Add comparison';
    add.addEventListener('click', () => {
      const preferred = ['stim', 'Glab', 'Gdem', 'Genv', 'kcdm', 'sicl', 'wslc'];
      const available = preferred.find((signal) => !state.columns.includes(signal))
        ?? [...categories.map((item) => item.code), ...sources.keys()]
          .find((signal) => !state.columns.includes(signal));
      if (!available) return;
      state.columns = [...state.columns, available];
      if (writeState()) render();
    });
    race.append(add);
    row.append(race);
    visible.forEach((signal, index) => {
      const cell = document.createElement('th');
      cell.scope = 'col';
      cell.dataset.columnSignal = signal;
      const heading = document.createElement('div');
      heading.className = 'comparison-column-heading';
      const label = document.createElement('span');
      label.className = 'comparison-column-label';
      label.textContent = index === 0 ? 'Reference' : '\u00a0';
      if (index !== 0) label.setAttribute('aria-hidden', 'true');
      heading.append(label);
      const title = document.createElement('strong');
      title.className = 'comparison-column-title';
      title.textContent = labelFor(signal);
      heading.append(title);
      if (index === 0) {
        const spacer = document.createElement('span');
        spacer.className = 'comparison-column-heading-spacer';
        spacer.setAttribute('aria-hidden', 'true');
        heading.append(spacer);
      }
      const pickerRow = document.createElement('div');
      pickerRow.className = 'comparison-column-heading-row';
      if (index !== 0) pickerRow.append(pickerFor(signal, index));
      if (index !== 0 && state.columns.length > 2) {
        const remove = document.createElement('button');
        remove.type = 'button';
        remove.className = 'comparison-column-remove';
        remove.dataset.comparisonRemove = String(index);
        remove.setAttribute('aria-label', `Remove ${labelFor(signal)}`);
        remove.title = `Remove ${labelFor(signal)}`;
        remove.textContent = '×';
        remove.addEventListener('click', () => {
          state.columns = state.columns.filter((_, columnIndex) => columnIndex !== index);
          if (writeState()) render();
        });
        pickerRow.append(remove);
      }
      if (index !== 0) heading.append(pickerRow);
      const meta = document.createElement('span');
      meta.className = 'comparison-column-meta';
      meta.textContent = coverageFor(signal);
      heading.append(meta);
      cell.append(heading);
      row.append(cell);
    });
    head.append(row);
    head.style.removeProperty('--comparison-title-height');
    const titleHeight = Math.max(
      ...[...head.querySelectorAll('.comparison-column-title')]
        .map((title) => title.scrollHeight),
    );
    head.style.setProperty('--comparison-title-height', `${titleHeight}px`);
  }

  function cellFor(signal, cell, display, baseline, isBaseline) {
    const labels = candidateLabels(display);
    const element = document.createElement('td');
    element.className = 'comparison-cell';
    element.dataset.columnSignal = signal;
    element.dataset.columnLabel = labelFor(signal);
    element.dataset.cellKind = cell.kind;
    const agreement = isBaseline ? 'baseline' : cellAgreement(cell, baseline);
    element.dataset.agreement = agreement;
    const picks = document.createElement('span');
    picks.className = 'comparison-cell-picks';
    picks.textContent = cell.kind === 'outside_scope'
      ? 'Outside district'
      : (cell.leadingPickIds?.map((id) => labels[id]).join(' / ') || '—');
    if (cell.kind === 'blank') picks.title = 'No endorsement published';
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
    let total = 0;
    let differCount = 0;
    for (const display of comparisons.display_index) {
      if (state.section !== 'all' && display.section_id !== state.section) continue;
      if (state.contestedOnly && !contestedIds.has(display.race_id)) continue;
      total += 1;
      const race = races.get(display.race_id);
      const configuredCells = state.columns.map((signal) => engine.resolveColumn(signal, race));
      const differs = rowDiffers(configuredCells);
      if (differs) differCount += 1;
      if (state.differencesOnly && !differs) continue;
      if (!sections.has(display.section_id)) {
        sections.set(display.section_id, { label: display.section_label, displays: [] });
      }
      sections.get(display.section_id).displays.push({ display, race, configuredCells, differs });
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
        const { display, race, configuredCells, differs } = item;
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
        const baseline = configuredCells[0];
        visible.forEach((signal, index) => {
          row.append(cellFor(signal, configuredCells[index], display, baseline, index === 0));
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

  function syncControls() {
    sectionFilter.value = state.section;
    document.querySelector('[data-comparison-complete]').setAttribute('aria-pressed', String(!state.contestedOnly && !state.differencesOnly));
    document.querySelector('[data-comparison-contested]').setAttribute('aria-pressed', String(state.contestedOnly && !state.differencesOnly));
    document.querySelector('[data-comparison-differences]').setAttribute('aria-pressed', String(!state.contestedOnly && state.differencesOnly));
    document.querySelector('[data-comparison-contested-differences]').setAttribute('aria-pressed', String(state.contestedOnly && state.differencesOnly));
  }

  function render() {
    const visible = state.columns;
    notice.hidden = true;
    notice.textContent = '';
    renderHead(visible);
    renderBody(visible);
    syncControls();
  }

  sectionFilter.addEventListener('change', () => {
    state.section = sectionFilter.value;
    if (writeState('replace')) render();
  });
  document.querySelector('[data-comparison-complete]').addEventListener('click', () => {
    state.contestedOnly = false;
    state.differencesOnly = false;
    if (writeState('replace')) render();
  });
  document.querySelector('[data-comparison-contested]').addEventListener('click', () => {
    state.contestedOnly = true;
    state.differencesOnly = false;
    if (writeState('replace')) render();
  });
  document.querySelector('[data-comparison-differences]').addEventListener('click', () => {
    state.contestedOnly = false;
    state.differencesOnly = true;
    if (writeState('replace')) render();
  });
  document.querySelector('[data-comparison-contested-differences]').addEventListener('click', () => {
    state.contestedOnly = true;
    state.differencesOnly = true;
    if (writeState('replace')) render();
  });
  document.querySelector('[data-comparison-copy]').addEventListener('click', async () => {
    const result = await shareOrCopyLink(window.location.href, document.title);
    if (result === 'copied') copyStatus.textContent = 'Link copied.';
    else if (result === 'shared') copyStatus.textContent = 'Share menu opened.';
    else if (result === 'failed') copyStatus.textContent = `Copy failed. Link: ${window.location.href}`;
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
