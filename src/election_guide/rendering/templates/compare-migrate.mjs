import { ALL_SOURCES_TOKEN } from './compare-url.mjs';

// Deterministic cross-version migration for comparison fragments. This module
// only resolves column identities and filters. It never scores a migrated or
// fallback state; the persistent disclosure status is part of every success.

function retiredEntry(personalization, kind, code) {
  return personalization.retired_codes.find((item) => item.kind === kind && item.code === code);
}

function resolveColumn(code, personalization) {
  if (code === ALL_SOURCES_TOKEN) return { code, kind: 'aggregate', status: 'current' };
  if (code.startsWith('G')) {
    const current = personalization.categories.find((item) => item.code === code);
    if (current !== undefined && current.selectable) {
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
  if (current !== undefined && current.selectable) {
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
 * Retired or otherwise unavailable direct sources are removed without
 * reordering the surviving columns. An unavailable category, fewer than two
 * surviving columns, or an invalid configured default falls back atomically to
 * the current default columns. Both outcomes carry an explicit disclosure
 * status for persistent page messaging.
 */
export function migrateCompareState(staleDecode, personalization, context) {
  if (staleDecode.status !== 'stale_version') {
    return { status: 'rejected', reason: 'not_stale_version' };
  }
  const columnResults = staleDecode.state.columns.map((code) =>
    resolveColumn(code, personalization),
  );
  const unavailableCategory = columnResults.find(
    (result) => result.kind === 'category' && result.status !== 'current',
  );
  const columns = columnResults
    .filter((result) => result.status === 'current')
    .map((result) => result.code);
  const sectionCurrent =
    staleDecode.state.section === 'all' || context.sectionIds.has(staleDecode.state.section);
  const report = {
    columns: columnResults,
    section: {
      value: staleDecode.state.section,
      status: sectionCurrent ? 'current' : 'unknown',
    },
  };

  if (unavailableCategory === undefined && columns.length >= 2 && columns.length <= 3) {
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

  const defaults = context.defaultColumns.map((code) => resolveColumn(code, personalization));
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
    reason: unavailableCategory === undefined ? 'insufficient_current_columns' : 'unresolvable_category',
    disclosureStatus: 'stale_version_fallback',
    state: fallbackState(staleDecode.state, context),
    report,
  };
}
