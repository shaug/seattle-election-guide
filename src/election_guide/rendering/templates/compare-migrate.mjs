import {
  ALL_SOURCES_TOKEN,
  CERTIFIED_RESULT_TOKEN,
  certifiedResultCurrentAt,
} from './compare-url.mjs';

// Deterministic cross-version migration for comparison fragments. This module
// only resolves column identities and filters. It never scores a migrated or
// fallback state; the persistent disclosure status is part of every success.

/**
 * How one configured column resolved against the current publication.
 *
 * @typedef {object} ColumnResolution
 * @property {string} code
 * @property {'aggregate'|'category'|'source'} kind
 * @property {'current'|'retired'|'unresolved'|'unknown'} status
 * @property {string} [formerId]
 * @property {string} [reason]
 */

/**
 * @typedef {object} CompareMigrationReport
 * @property {ColumnResolution[]} columns
 * @property {{ value: string, status: 'current'|'unknown' }} section
 */

/**
 * @typedef {{ status: 'rejected',
 *     reason: 'not_stale_version'|'invalid_default_columns',
 *     report?: CompareMigrationReport }
 *   | { status: 'migrated', disclosureStatus: 'stale_version_migrated',
 *     state: import('./compare-url.mjs').CompareState, report: CompareMigrationReport }
 *   | { status: 'fallback',
 *     reason: 'unresolvable_reference'|'unresolvable_category'|'unresolvable_source'
 *       |'insufficient_current_columns',
 *     disclosureStatus: 'stale_version_fallback',
 *     state: import('./compare-url.mjs').CompareState, report: CompareMigrationReport }
 * } CompareMigrationResult
 */

/**
 * @param {PersonalizationContract} personalization
 * @param {'source'|'category'} kind
 * @param {string} code
 * @returns {PersonalizationRetiredCode|undefined}
 */
function retiredEntry(personalization, kind, code) {
  return personalization.retired_codes.find((item) => item.kind === kind && item.code === code);
}

/**
 * @param {string} code
 * @param {PersonalizationContract} personalization
 * @param {boolean} resultsAvailable
 * @param {number} index Position in the configured column order; see
 *   `compare-url.mjs` `certifiedResultCurrentAt` for why `gres` never resolves
 *   as current at the reference position (index `0`).
 * @returns {ColumnResolution}
 */
function resolveColumn(code, personalization, resultsAvailable, index) {
  if (code === ALL_SOURCES_TOKEN) return { code, kind: 'aggregate', status: 'current' };
  if (code === CERTIFIED_RESULT_TOKEN) {
    // Reserved like `gall`, but its availability is a data fact rather than a
    // catalog membership, so it resolves on the codec's own admission rule
    // rather than a second reading of it. Where that rule does not hold the
    // column is unresolved, not unknown -- the identity is real
    // (docs/RESULTS.md, Rendering § The comparison view).
    return {
      code,
      kind: 'aggregate',
      status: certifiedResultCurrentAt(resultsAvailable, index) ? 'current' : 'unresolved',
    };
  }
  if (code.startsWith('G')) {
    const current = personalization.categories.find((item) => item.code === code);
    if (current?.selectable) {
      return { code, kind: 'category', status: 'current' };
    }
    const retired = retiredEntry(personalization, 'category', code);
    if (retired !== undefined) {
      return {
        code,
        kind: 'category',
        status: 'retired',
        formerId: retired.former_id,
        reason: retired.reason,
      };
    }
    return { code, kind: 'category', status: current === undefined ? 'unknown' : 'unresolved' };
  }

  const current = personalization.sources.find((item) => item.code === code);
  if (current?.selectable) {
    return { code, kind: 'source', status: 'current' };
  }
  const retired = retiredEntry(personalization, 'source', code);
  if (retired !== undefined) {
    return {
      code,
      kind: 'source',
      status: 'retired',
      formerId: retired.former_id,
      reason: retired.reason,
    };
  }
  return { code, kind: 'source', status: current === undefined ? 'unknown' : 'unresolved' };
}

/**
 * @param {import('./compare-url.mjs').CompareState} staleState
 * @param {import('./compare-url.mjs').CompareContext} context
 * @returns {import('./compare-url.mjs').CompareState}
 */
function fallbackState(staleState, context) {
  return {
    columns: [...context.defaultColumns],
    differencesOnly: staleState.differencesOnly,
    contestedOnly: staleState.contestedOnly,
    section: context.sectionIds.has(staleState.section) ? staleState.section : 'all',
  };
}

/**
 * Resolve a `stale_version` comparison decode against the current publication.
 *
 * Retired direct sources are removed without reordering the surviving columns.
 * An identity that resolves through neither the current panel nor a tombstone,
 * an unavailable category, fewer than two surviving columns, or an invalid
 * configured default falls back atomically to the current default columns.
 * Both outcomes carry an explicit disclosure status for persistent page
 * messaging.
 *
 * @param {import('./compare-url.mjs').CompareDecodeResult} staleDecode
 * @param {PersonalizationContract} personalization
 * @param {import('./compare-url.mjs').CompareContext} context
 * @returns {CompareMigrationResult}
 */
export function migrateCompareState(staleDecode, personalization, context) {
  if (staleDecode.status !== 'stale_version') {
    return { status: 'rejected', reason: 'not_stale_version' };
  }
  const columnResults = staleDecode.state.columns.map((code, index) =>
    resolveColumn(code, personalization, context.resultsAvailable, index),
  );
  const unavailableCategory = columnResults.find(
    (result) => result.kind === 'category' && result.status !== 'current',
  );
  const unresolvedSource = columnResults.find(
    (result) =>
      result.kind === 'source' && result.status !== 'current' && result.status !== 'retired',
  );
  const columns = columnResults
    .filter((result) => result.status === 'current')
    .map((result) => result.code);
  const sectionCurrent =
    staleDecode.state.section === 'all' || context.sectionIds.has(staleDecode.state.section);
  /** @type {CompareMigrationReport} */
  const report = {
    columns: columnResults,
    section: {
      value: staleDecode.state.section,
      status: sectionCurrent ? 'current' : 'unknown',
    },
  };
  const referenceCurrent = columnResults[0]?.status === 'current';

  if (
    referenceCurrent &&
    unavailableCategory === undefined &&
    unresolvedSource === undefined &&
    columns.length >= 2 &&
    columns.length <= 3
  ) {
    return {
      status: 'migrated',
      disclosureStatus: 'stale_version_migrated',
      state: {
        columns,
        differencesOnly: staleDecode.state.differencesOnly,
        contestedOnly: staleDecode.state.contestedOnly,
        section: sectionCurrent ? staleDecode.state.section : 'all',
      },
      report,
    };
  }

  const defaults = context.defaultColumns.map((code, index) =>
    resolveColumn(code, personalization, context.resultsAvailable, index),
  );
  if (
    defaults.length < 2 ||
    defaults.length > 3 ||
    defaults.some((result) => result.status !== 'current') ||
    new Set(defaults.map((result) => result.code)).size !== defaults.length
  ) {
    return { status: 'rejected', reason: 'invalid_default_columns', report };
  }
  return {
    status: 'fallback',
    reason: !referenceCurrent
      ? 'unresolvable_reference'
      : unavailableCategory !== undefined
        ? 'unresolvable_category'
        : unresolvedSource !== undefined
          ? 'unresolvable_source'
          : 'insufficient_current_columns',
    disclosureStatus: 'stale_version_fallback',
    state: fallbackState(staleDecode.state, context),
    report,
  };
}
