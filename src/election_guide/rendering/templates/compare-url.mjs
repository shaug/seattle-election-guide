// Canonical fragment codec for the election-scoped comparison page.
//
// Like lens-url.mjs, this module is pure: it validates fragment state but never
// scores, fetches, or touches the DOM. Unlike the lens codec, comparison column
// tokens deliberately retain their configured order because the first column is
// the reference against which the remaining columns are compared.
//
// The structural checks this shares with the lens codec — token admission, the
// four version bindings, the sharing limit — live in `fragment-codec.mjs`.
// What stays here is what makes this fragment Comparisons': ordered columns,
// the two-to-three column bound, the reserved lowercase-`g` namespace whose
// only member so far is `gall`, the filter parameters, and the refusal to read
// a lens link.

import {
  classifyCatalogToken,
  codecContext,
  isCurrentBinding,
  isWellFormedToken,
  missingBindingParameter,
  openFragment,
  orderedUnique,
  readBinding,
  repeatedParameter,
  scanTokens,
  sizedFragment,
  writeBinding,
} from './fragment-codec.mjs';

export const COMPARE_SCHEMA_VERSION = '1';
export const ALL_SOURCES_TOKEN = 'gall';

const RESERVED_PREFIX = 'g';
const MIN_COLUMNS = 2;
const MAX_COLUMNS = 3;

/**
 * The version bindings, token catalogs, filters, and limits one comparison
 * fragment is read and written against.
 *
 * @typedef {import('./fragment-codec.mjs').CodecContext
 *   & { sectionIds: Set<string>, defaultColumns: string[] }} CompareContext
 */

/**
 * @typedef {import('./fragment-codec.mjs').CodecBinding} CompareBinding
 */

/**
 * Comparison state in its decoded form. Column order is meaningful: the first
 * column is the reference the rest are compared against.
 *
 * @typedef {object} CompareState
 * @property {string[]} columns
 * @property {boolean} differencesOnly
 * @property {boolean} contestedOnly
 * @property {string} section
 */

/**
 * @typedef {'malformed_token'|'unknown_token'|'case_confusable_token'
 *   |'forbidden_token'|'reserved_token'|'oversized'|'unrecognized_fragment'
 *   |'repeated_parameter'|'unsupported_schema'|'not_for_this_page'
 *   |'ragged_selection'|'column_count'|'unknown_toggle'|'unknown_filter'
 *   |'missing_binding'|'unknown_section'|'invalid_state'} CompareFailureReason
 */

/**
 * @typedef {{ status: 'malformed', reason: CompareFailureReason, [key: string]: unknown }
 * } CompareMalformed
 */

/**
 * @typedef {{ status: 'rejected', reason: CompareFailureReason, [key: string]: unknown }
 * } CompareRejected
 */

/**
 * @typedef {{ status: 'absent' }
 *   | { status: 'valid', state: CompareState, binding: CompareBinding }
 *   | { status: 'stale_version', state: CompareState, binding: CompareBinding }
 *   | CompareMalformed
 * } CompareDecodeResult
 */

/**
 * Both codecs share their structural checks but report failure differently:
 * decoding produces `malformed`, encoding produces `rejected`.
 *
 * @template {CompareMalformed|CompareRejected} T
 * @typedef {(reason: CompareFailureReason, detail?: Record<string, unknown>) => T} FailureFactory
 */

/**
 * Read the version bindings, token catalogs, filters, and limits for a fragment.
 *
 * @param {PersonalizationContract} personalization
 * @param {string} dataVersion
 * @param {ComparisonsContract} comparisons
 * @param {string[]} [defaultColumns]
 * @returns {CompareContext}
 */
export function compareContext(
  personalization,
  dataVersion,
  comparisons,
  defaultColumns = [ALL_SOURCES_TOKEN, 'strn', 'stim'],
) {
  /** @type {Set<string>} */
  const sectionIds = new Set();
  for (const race of comparisons.display_index) sectionIds.add(race.section_id);
  return {
    ...codecContext(personalization, dataVersion),
    sectionIds,
    defaultColumns: [...defaultColumns],
  };
}

/**
 * @param {CompareFailureReason} reason
 * @param {Record<string, unknown>} [detail]
 * @returns {CompareMalformed}
 */
function invalid(reason, detail = {}) {
  return { status: 'malformed', reason, ...detail };
}

/**
 * @param {CompareFailureReason} reason
 * @param {Record<string, unknown>} [detail]
 * @returns {CompareRejected}
 */
function rejected(reason, detail = {}) {
  return { status: 'rejected', reason, ...detail };
}

/**
 * Whether a token is this page's own rather than the catalogs'.
 *
 * Lowercase `g` is reserved for aggregate columns the page defines itself.
 * `gall` is the only one so far; every other spelling is refused rather than
 * looked up, so adding a second aggregate never has to reinterpret a link that
 * already guessed at its name.
 *
 * @param {string} token
 * @returns {boolean}
 */
function isReservedToken(token) {
  return token.startsWith(RESERVED_PREFIX) && token !== ALL_SOURCES_TOKEN;
}

/**
 * @param {string} token
 * @param {CompareContext} context
 * @returns {import('./fragment-codec.mjs').CodecTokenClassification
 *   | { ok: false, reason: 'reserved_token', token: string }}
 */
function classifyToken(token, context) {
  if (!isWellFormedToken(token)) return { ok: false, reason: 'malformed_token', token };
  if (token === ALL_SOURCES_TOKEN) return { ok: true, token };
  if (isReservedToken(token)) return { ok: false, reason: 'reserved_token', token };
  return classifyCatalogToken(token, context);
}

/**
 * @template {CompareMalformed|CompareRejected} T
 * @param {readonly string[]} columns
 * @param {FailureFactory<T>} failure
 * @returns {T|null}
 */
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

/**
 * Decode-side only, so the failure type is concrete rather than generic.
 *
 * @param {string} selection
 * @param {FailureFactory<CompareMalformed>} failure
 * @returns {{ columns: string[], error?: undefined }
 *   | { columns?: undefined, error: CompareMalformed }}
 */
function parseColumns(selection, failure) {
  const scanned = scanTokens(selection, failure, (token) =>
    isReservedToken(token) ? failure('reserved_token', { token }) : null,
  );
  if (scanned.error !== undefined) return { error: scanned.error };
  const countError = validateColumnCount(scanned.tokens, failure);
  if (countError !== null) return { error: countError };
  return { columns: scanned.tokens };
}

/**
 * Decode-side only, like `parseColumns`: the failure type is concrete.
 *
 * @param {URLSearchParams} parameters
 * @param {FailureFactory<CompareMalformed>} failure
 * @returns {{ state: Omit<CompareState, 'columns'>, error?: undefined }
 *   | { state?: undefined, error: CompareMalformed }}
 */
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

/**
 * Decode one comparison-page location fragment.
 *
 * The status taxonomy mirrors lens-url.mjs: `absent`, `valid`,
 * `stale_version`, or `malformed`. A stale state has passed structural checks
 * but has not been admitted against the current panel and must never be scored.
 *
 * @param {string|null|undefined} fragment
 * @param {CompareContext} context
 * @returns {CompareDecodeResult}
 */
export function decodeCompareFragment(fragment, context) {
  const opened = openFragment(fragment, context, invalid);
  if (opened.decoded !== undefined) return opened.decoded;
  const raw = opened.raw;
  if (!raw.includes('=')) return invalid('unrecognized_fragment');

  const parameters = new URLSearchParams(raw);
  const repeated = repeatedParameter(parameters);
  if (repeated !== null) return invalid('repeated_parameter', { parameter: repeated });
  if (parameters.get('cmp') !== COMPARE_SCHEMA_VERSION) {
    if (parameters.has('lens')) return invalid('not_for_this_page', { schema: 'lens' });
    return invalid('unsupported_schema', { cmp: parameters.get('cmp') });
  }

  const parsedColumns = parseColumns(parameters.get('cols') ?? '', invalid);
  if (parsedColumns.error) return parsedColumns.error;
  const parsedFilters = parseFilters(parameters, invalid);
  if (parsedFilters.error) return parsedFilters.error;

  const binding = readBinding(parameters);
  const missing = missingBindingParameter(binding);
  if (missing !== null) return invalid('missing_binding', { parameter: missing });
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
 *
 * @param {Partial<CompareState>} state
 * @param {CompareContext} context
 * @returns {{ status: 'ok', fragment: string } | CompareRejected}
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
  writeBinding(parameters, context);
  if (state.differencesOnly === true) parameters.set('diff', '1');
  if (state.contestedOnly === true) parameters.set('races', 'contested');
  if (section !== 'all') parameters.set('show', section);

  return sizedFragment(parameters, context, rejected);
}
