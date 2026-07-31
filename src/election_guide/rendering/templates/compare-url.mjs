// Canonical fragment codec for the election-scoped comparison page.
//
// Like lens-url.mjs, this module is pure: it validates fragment state but never
// scores, fetches, or touches the DOM. Unlike the lens codec, comparison column
// tokens deliberately retain their configured order because the first column is
// the baseline against which the remaining columns are compared.

export const COMPARE_SCHEMA_VERSION = '1';
export const ALL_SOURCES_TOKEN = 'gall';
export const COMPARE_TOKEN_LENGTH = 4;

const TOKEN_PATTERN = /^[0-9A-Za-z]{4}$/;
const CATEGORY_PREFIX = 'G';
const RESERVED_PREFIX = 'g';
const HASH_PREFIX_LENGTH = 12;
const MIN_COLUMNS = 2;
const MAX_COLUMNS = 3;

/** Read the version bindings, token catalogs, filters, and limits for a fragment. */
export function compareContext(
  personalization,
  dataVersion,
  comparisons,
  defaultColumns = [ALL_SOURCES_TOKEN, 'strn', 'stim'],
) {
  const categories = new Map();
  const sources = new Map();
  const sectionIds = new Set();
  for (const category of personalization.categories) categories.set(category.code, category);
  for (const source of personalization.sources) sources.set(source.code, source);
  for (const race of comparisons.display_index) sectionIds.add(race.section_id);
  return {
    panelId: personalization.panel_id,
    panelHashPrefix: personalization.panel_hash.slice(0, HASH_PREFIX_LENGTH),
    dataVersion,
    scoringId: personalization.scoring.configuration_id,
    maximumUrlCharacters: personalization.policy.maximum_url_characters,
    categories,
    sources,
    sectionIds,
    defaultColumns: [...defaultColumns],
  };
}

function invalid(reason, detail = {}) {
  return { status: 'malformed', reason, ...detail };
}

function rejected(reason, detail = {}) {
  return { status: 'rejected', reason, ...detail };
}

function confusableReason(token, known) {
  const folded = token.toLowerCase();
  for (const code of known.keys()) {
    if (code.toLowerCase() === folded) return 'case_confusable_token';
  }
  return 'unknown_token';
}

function classifyToken(token, context) {
  if (!TOKEN_PATTERN.test(token)) return { ok: false, reason: 'malformed_token', token };
  if (token === ALL_SOURCES_TOKEN) return { ok: true, token };
  if (token.startsWith(RESERVED_PREFIX)) {
    return { ok: false, reason: 'reserved_token', token };
  }
  const known = token.startsWith(CATEGORY_PREFIX) ? context.categories : context.sources;
  const entry = known.get(token);
  if (entry === undefined) return { ok: false, reason: confusableReason(token, known), token };
  if (!entry.selectable) return { ok: false, reason: 'forbidden_token', token };
  return { ok: true, token };
}

function orderedUnique(tokens) {
  const unique = [];
  for (const token of tokens) {
    if (!unique.includes(token)) unique.push(token);
  }
  return unique;
}

function validateColumnCount(columns, failure) {
  if (columns.length < MIN_COLUMNS || columns.length > MAX_COLUMNS) {
    return failure('column_count', {
      count: columns.length,
      minimum: MIN_COLUMNS,
      maximum: MAX_COLUMNS,
    });
  }
  return null;
}

function parseColumns(selection, failure) {
  if (selection.length % COMPARE_TOKEN_LENGTH !== 0) {
    return { error: failure('ragged_selection', { length: selection.length }) };
  }
  const tokens = [];
  for (let index = 0; index < selection.length; index += COMPARE_TOKEN_LENGTH) {
    const token = selection.slice(index, index + COMPARE_TOKEN_LENGTH);
    if (!TOKEN_PATTERN.test(token)) {
      return { error: failure('malformed_token', { token }) };
    }
    if (token.startsWith(RESERVED_PREFIX) && token !== ALL_SOURCES_TOKEN) {
      return { error: failure('reserved_token', { token }) };
    }
    tokens.push(token);
  }
  const columns = orderedUnique(tokens);
  return { columns, error: validateColumnCount(columns, failure) };
}

function parseFilters(parameters, failure) {
  const difference = parameters.get('diff');
  if (difference !== null && difference !== '1') {
    return { error: failure('unknown_toggle', { parameter: 'diff', value: difference }) };
  }
  const races = parameters.get('races');
  if (races !== null && races !== 'contested') {
    return { error: failure('unknown_filter', { parameter: 'races', value: races }) };
  }
  return {
    state: {
      differencesOnly: difference === '1',
      contestedOnly: races === 'contested',
      section: parameters.get('show') || 'all',
    },
  };
}

function bindingFrom(parameters) {
  return {
    panelId: parameters.get('panel'),
    panelHashPrefix: parameters.get('ph'),
    dataVersion: parameters.get('data'),
    scoringId: parameters.get('scoring'),
  };
}

function isCurrentBinding(binding, context) {
  return (
    binding.panelId === context.panelId &&
    binding.panelHashPrefix === context.panelHashPrefix &&
    binding.dataVersion === context.dataVersion &&
    binding.scoringId === context.scoringId
  );
}

/**
 * Decode one comparison-page location fragment.
 *
 * The status taxonomy mirrors lens-url.mjs: `absent`, `valid`,
 * `stale_version`, or `malformed`. A stale state has passed structural checks
 * but has not been admitted against the current panel and must never be scored.
 */
export function decodeCompareFragment(fragment, context) {
  const raw = String(fragment ?? '').replace(/^#/, '');
  if (raw === '') return { status: 'absent' };
  if (raw.length > context.maximumUrlCharacters) {
    return invalid('oversized', { length: raw.length });
  }
  if (!raw.includes('=')) return invalid('unrecognized_fragment');

  const parameters = new URLSearchParams(raw);
  for (const key of parameters.keys()) {
    if (parameters.getAll(key).length > 1) return invalid('repeated_parameter', { parameter: key });
  }
  if (parameters.get('cmp') !== COMPARE_SCHEMA_VERSION) {
    if (parameters.has('lens')) return invalid('not_for_this_page', { schema: 'lens' });
    return invalid('unsupported_schema', { cmp: parameters.get('cmp') });
  }

  const parsedColumns = parseColumns(parameters.get('cols') ?? '', invalid);
  if (parsedColumns.error) return parsedColumns.error;
  const parsedFilters = parseFilters(parameters, invalid);
  if (parsedFilters.error) return parsedFilters.error;

  const binding = bindingFrom(parameters);
  for (const [key, value] of Object.entries(binding)) {
    if (value === null || value === '') return invalid('missing_binding', { parameter: key });
  }
  const state = { columns: parsedColumns.columns, ...parsedFilters.state };
  if (!isCurrentBinding(binding, context)) return { status: 'stale_version', state, binding };

  for (const token of state.columns) {
    const classified = classifyToken(token, context);
    if (!classified.ok) return invalid(classified.reason, { token: classified.token });
  }
  if (state.section !== 'all' && !context.sectionIds.has(state.section)) {
    return invalid('unknown_section', { section: state.section });
  }
  return { status: 'valid', state, binding };
}

/**
 * Encode comparison state into its one canonical, order-preserving fragment.
 */
export function encodeCompareFragment(state, context) {
  const columns = orderedUnique(state.columns ?? []);
  const countError = validateColumnCount(columns, rejected);
  if (countError) return countError;
  for (const token of columns) {
    const classified = classifyToken(token, context);
    if (!classified.ok) return rejected(classified.reason, { token: classified.token });
  }
  for (const [key, value] of [
    ['differencesOnly', state.differencesOnly],
    ['contestedOnly', state.contestedOnly],
  ]) {
    if (value !== undefined && typeof value !== 'boolean') {
      return rejected('invalid_state', { field: key });
    }
  }
  const section = state.section ?? 'all';
  if (section !== 'all' && !context.sectionIds.has(section)) {
    return rejected('unknown_section', { section });
  }

  const parameters = new URLSearchParams();
  parameters.set('cmp', COMPARE_SCHEMA_VERSION);
  parameters.set('cols', columns.join(''));
  parameters.set('panel', context.panelId);
  parameters.set('ph', context.panelHashPrefix);
  parameters.set('data', context.dataVersion);
  parameters.set('scoring', context.scoringId);
  if (state.differencesOnly === true) parameters.set('diff', '1');
  if (state.contestedOnly === true) parameters.set('races', 'contested');
  if (section !== 'all') parameters.set('show', section);

  const fragment = parameters.toString();
  if (fragment.length > context.maximumUrlCharacters) {
    return rejected('oversized', {
      length: fragment.length,
      limit: context.maximumUrlCharacters,
    });
  }
  return { status: 'ok', fragment };
}
