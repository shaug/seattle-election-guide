import assert from 'node:assert/strict';
import test from 'node:test';
import { migrateCompareState } from '../../src/election_guide/rendering/templates/compare-migrate.mjs';
import {
  compareContext,
  decodeCompareFragment,
  encodeCompareFragment,
} from '../../src/election_guide/rendering/templates/compare-url.mjs';
import { assertModuleGuard } from './support/module-guards.mjs';

const ORIGIN = {
  panel_id: 'panel-v1',
  panel_hash: 'aaaaaaaaaaaa0000000000000000000000000000000000000000000000000000',
  scoring: { configuration_id: 'score-v1' },
  policy: { maximum_url_characters: 4096 },
  categories: [
    { id: 'labor', code: 'Glab', selectable: true },
    { id: 'urbanism', code: 'Gurb', selectable: true },
  ],
  sources: [
    { id: 'the-stranger', code: 'strn', selectable: true },
    { id: 'seattle-times', code: 'stim', selectable: true },
    { id: 'retired-source', code: 'zret', selectable: true },
  ],
  retired_codes: [],
};

const CURRENT = {
  panel_id: 'panel-v2',
  panel_hash: 'bbbbbbbbbbbb0000000000000000000000000000000000000000000000000000',
  scoring: { configuration_id: 'score-v2' },
  policy: { maximum_url_characters: 4096 },
  categories: [{ id: 'labor', code: 'Glab', selectable: true }],
  sources: [
    { id: 'the-stranger', code: 'strn', selectable: true },
    { id: 'seattle-times', code: 'stim', selectable: true },
  ],
  retired_codes: [
    { kind: 'source', code: 'zret', former_id: 'retired-source', reason: 'Closed.' },
    { kind: 'category', code: 'Gurb', former_id: 'urbanism', reason: 'Retired.' },
  ],
};

const COMPARISONS = {
  display_index: [{ race_id: 'city-attorney', section_id: 'city-of-seattle' }],
};

function stale(columns, state = {}) {
  const originContext = compareContext(ORIGIN, 'data-v1', COMPARISONS);
  const encoded = encodeCompareFragment(
    {
      columns,
      differencesOnly: false,
      contestedOnly: false,
      section: 'all',
      ...state,
    },
    originContext,
  );
  assert.equal(encoded.status, 'ok');
  const currentContext = compareContext(CURRENT, 'data-v2', COMPARISONS);
  const decoded = decodeCompareFragment(encoded.fragment, currentContext);
  assert.equal(decoded.status, 'stale_version');
  return { decoded, currentContext };
}

test('surviving columns migrate in their original order with persistent disclosure status', () => {
  const { decoded, currentContext } = stale(['stim', 'Glab', 'strn'], {
    differencesOnly: true,
    contestedOnly: true,
    section: 'city-of-seattle',
  });
  const result = migrateCompareState(decoded, CURRENT, currentContext);
  assert.equal(result.status, 'migrated');
  assert.equal(result.disclosureStatus, 'stale_version_migrated');
  assert.deepEqual(result.state, {
    columns: ['stim', 'Glab', 'strn'],
    differencesOnly: true,
    contestedOnly: true,
    section: 'city-of-seattle',
  });
});

test('a retired reference falls back rather than silently promoting another column', () => {
  const { decoded, currentContext } = stale(['zret', 'strn', 'stim']);
  const result = migrateCompareState(decoded, CURRENT, currentContext);
  assert.equal(result.status, 'fallback');
  assert.equal(result.reason, 'unresolvable_reference');
  assert.deepEqual(result.state.columns, ['gall', 'strn', 'stim']);
  assert.deepEqual(result.report.columns[0], {
    code: 'zret',
    kind: 'source',
    status: 'retired',
    formerId: 'retired-source',
    reason: 'Closed.',
  });
});

test('a retired non-reference source drops without changing the reference', () => {
  const { decoded, currentContext } = stale(['strn', 'zret', 'stim']);
  const result = migrateCompareState(decoded, CURRENT, currentContext);
  assert.equal(result.status, 'migrated');
  assert.deepEqual(result.state.columns, ['strn', 'stim']);
  assert.equal(result.report.columns[1].status, 'retired');
});

test('too few surviving columns fall back atomically to defaults with persistent disclosure', () => {
  const { decoded, currentContext } = stale(['zret', 'strn']);
  const result = migrateCompareState(decoded, CURRENT, currentContext);
  assert.equal(result.status, 'fallback');
  assert.equal(result.reason, 'unresolvable_reference');
  assert.equal(result.disclosureStatus, 'stale_version_fallback');
  assert.deepEqual(result.state.columns, ['gall', 'strn', 'stim']);
});

test('a retired category forces fallback rather than silently changing aggregate meaning', () => {
  const { decoded, currentContext } = stale(['Gurb', 'strn', 'stim']);
  const result = migrateCompareState(decoded, CURRENT, currentContext);
  assert.equal(result.status, 'fallback');
  assert.equal(result.reason, 'unresolvable_reference');
  assert.equal(result.report.columns[0].status, 'retired');
  assert.deepEqual(result.state.columns, ['gall', 'strn', 'stim']);
});

test('an unknown stale token falls back deterministically and never becomes a valid state', () => {
  const { decoded, currentContext } = stale(['zret', 'strn', 'stim']);
  decoded.state.columns[0] = 'zzzz';
  const result = migrateCompareState(decoded, CURRENT, currentContext);
  assert.equal(result.status, 'fallback');
  assert.equal(result.reason, 'unresolvable_reference');
  assert.equal(result.disclosureStatus, 'stale_version_fallback');
  assert.deepEqual(result.state.columns, ['gall', 'strn', 'stim']);
  assert.equal(result.report.columns[0].status, 'unknown');
});

test('a removed section falls back to all while preserving safely migrated columns', () => {
  const originComparisons = {
    display_index: [{ race_id: 'state-house', section_id: 'legislative' }],
  };
  const originContext = compareContext(ORIGIN, 'data-v1', originComparisons);
  const encoded = encodeCompareFragment(
    { columns: ['strn', 'stim'], section: 'legislative' },
    originContext,
  );
  const currentContext = compareContext(CURRENT, 'data-v2', COMPARISONS);
  const decoded = decodeCompareFragment(encoded.fragment, currentContext);
  const result = migrateCompareState(decoded, CURRENT, currentContext);
  assert.equal(result.status, 'migrated');
  assert.equal(result.state.section, 'all');
  assert.equal(result.report.section.status, 'unknown');
});

test('invalid current defaults reject instead of manufacturing a fallback', () => {
  const { decoded, currentContext } = stale(['zret', 'strn']);
  currentContext.defaultColumns = ['gall', 'missing'];
  const result = migrateCompareState(decoded, CURRENT, currentContext);
  assert.equal(result.status, 'rejected');
  assert.equal(result.reason, 'invalid_default_columns');
});

test('gres in a non-reference position survives migration once results are available in both versions', () => {
  const originContext = compareContext(ORIGIN, 'data-v1', COMPARISONS, undefined, true);
  const encoded = encodeCompareFragment({ columns: ['strn', 'gres', 'stim'] }, originContext);
  assert.equal(encoded.status, 'ok');
  const currentContext = compareContext(CURRENT, 'data-v2', COMPARISONS, undefined, true);
  const decoded = decodeCompareFragment(encoded.fragment, currentContext);
  assert.equal(decoded.status, 'stale_version');
  const result = migrateCompareState(decoded, CURRENT, currentContext);
  assert.equal(result.status, 'migrated');
  assert.deepEqual(result.state.columns, ['strn', 'gres', 'stim']);
});

test('an unresolved gres drops from a stale link without blocking migration of its surviving columns', () => {
  const originContext = compareContext(ORIGIN, 'data-v1', COMPARISONS, undefined, true);
  const encoded = encodeCompareFragment({ columns: ['strn', 'gres', 'stim'] }, originContext);
  assert.equal(encoded.status, 'ok');
  // The current publication carries no certified results file (or, in
  // principle, one a correction somehow withdrew) -- gres resolves like an
  // aggregate whose current membership excludes it, not like an unknown code.
  const currentContext = compareContext(CURRENT, 'data-v2', COMPARISONS, undefined, false);
  const decoded = decodeCompareFragment(encoded.fragment, currentContext);
  assert.equal(decoded.status, 'stale_version');
  const result = migrateCompareState(decoded, CURRENT, currentContext);
  assert.equal(result.status, 'migrated');
  assert.deepEqual(result.state.columns, ['strn', 'stim']);
  assert.equal(result.report.columns[1].status, 'unresolved');
});

test('gres at the reference position falls back rather than becoming the reference', () => {
  // The codec itself now refuses to *encode* gres at index 0 at any version
  // (compare-url.mjs classifyToken's own index guard), so this simulates a
  // hand-built or malformed link rather than one this codec ever wrote --
  // the same technique 'an unknown stale token falls back deterministically'
  // above uses to reach a shape the encoder cannot produce. Built from a real
  // stale decode with gres in a legal position, then rearranged, so every
  // other field (binding, filters) still comes from a genuine round trip.
  const originContext = compareContext(ORIGIN, 'data-v1', COMPARISONS, undefined, true);
  const encoded = encodeCompareFragment({ columns: ['strn', 'gres', 'stim'] }, originContext);
  assert.equal(encoded.status, 'ok');
  const currentContext = compareContext(CURRENT, 'data-v2', COMPARISONS, undefined, true);
  const decoded = decodeCompareFragment(encoded.fragment, currentContext);
  assert.equal(decoded.status, 'stale_version');
  decoded.state.columns = ['gres', 'strn', 'stim'];
  const result = migrateCompareState(decoded, CURRENT, currentContext);
  assert.equal(result.status, 'fallback');
  assert.equal(result.reason, 'unresolvable_reference');
  assert.deepEqual(result.state.columns, ['gall', 'strn', 'stim']);
  assert.equal(result.report.columns[0].status, 'unresolved');
});

test('migration rejects a same-version decode', () => {
  const currentContext = compareContext(CURRENT, 'data-v2', COMPARISONS);
  const encoded = encodeCompareFragment({ columns: ['gall', 'strn'] }, currentContext);
  const decoded = decodeCompareFragment(encoded.fragment, currentContext);
  assert.deepEqual(migrateCompareState(decoded, CURRENT, currentContext), {
    status: 'rejected',
    reason: 'not_stale_version',
  });
});

test('the module stays pure', () => {
  assertModuleGuard('compare-migrate.mjs');
});
