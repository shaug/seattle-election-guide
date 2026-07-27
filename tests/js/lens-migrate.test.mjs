import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';
import { fileURLToPath } from 'node:url';

import { migrateLensState } from '../../src/election_guide/rendering/templates/lens-migrate.mjs';

/**
 * A synthetic successive-panel fixture: v1 (the origin a stale link points
 * at) and v2 (the current published panel), evolved by hand to exercise
 * every migration case the acceptance criteria name. Production has only
 * ever published one panel version, so a hand-built history is the only way
 * to exercise this module at all.
 */
const ORIGIN_SNAPSHOT = {
  panel_id: 'wa-2026-primary-default-sources-v1',
  panel_version: 'v1',
  categories: [
    { id: 'labor', code: 'Glab', label: 'Labor', selectable: true, member_source_codes: ['strn'] },
    {
      id: 'urbanism',
      code: 'Gurb',
      label: 'Urbanism',
      selectable: true,
      member_source_codes: ['urbn'],
    },
  ],
  sources: [
    { id: 'the-stranger', code: 'strn', name: 'The Stranger', panel_role: 'consensus' },
    { id: 'the-urbanist', code: 'urbn', name: 'The Urbanist', panel_role: 'consensus' },
    { id: 'a-retired-outlet', code: 'zret', name: 'A Retired Outlet', panel_role: 'consensus' },
    { id: 'a-dropped-outlet', code: 'zdrp', name: 'A Dropped Outlet', panel_role: 'consensus' },
  ],
};

const CURRENT_PERSONALIZATION = {
  policy: { comparison_source_codes: ['stim'] },
  categories: [
    { id: 'labor', code: 'Glab', label: 'Labor', selectable: true, member_source_codes: ['strn'] },
    // Urbanism was retired outright: the category itself is gone.
    { id: 'comparison', code: 'Gcmp', label: 'Comparison', selectable: false, member_source_codes: [] },
  ],
  sources: [
    { id: 'the-stranger', code: 'strn', panel_role: 'consensus', selectable: true },
    // the-urbanist's code now names a comparison-only source: reclassified.
    { id: 'the-urbanist', code: 'urbn', panel_role: 'comparison', selectable: false },
    { id: 'seattle-times-editorial-board', code: 'stim', panel_role: 'comparison', selectable: false },
  ],
  retired_codes: [
    {
      code: 'zret',
      kind: 'source',
      former_id: 'a-retired-outlet',
      reason: 'Publication discontinued.',
    },
    { code: 'Gurb', kind: 'category', former_id: 'urbanism', reason: 'Category discontinued.' },
  ],
};

function staleDecode(overrides = {}) {
  return {
    status: 'stale_version',
    state: {
      mode: 's',
      categoryCodes: [],
      sourceCodes: [],
      showTimes: false,
      raceTarget: null,
      ...overrides.state,
    },
    binding: {
      panelId: 'wa-2026-primary-default-sources-v1',
      panelHashPrefix: 'aaaaaaaaaaaa',
      dataVersion: 'd1',
      scoringId: 'score-1',
      ...overrides.binding,
    },
  };
}

test('a surviving direct source migrates and is reported current', () => {
  const result = migrateLensState(
    staleDecode({ state: { sourceCodes: ['strn'] } }),
    CURRENT_PERSONALIZATION,
    ORIGIN_SNAPSHOT,
  );

  assert.equal(result.status, 'migrated');
  assert.deepEqual(result.selection.sourceCodes, ['strn']);
  assert.equal(result.report.sources[0].status, 'current');
});

test('a surviving category re-resolves without needing origin history', () => {
  const result = migrateLensState(
    staleDecode({ state: { categoryCodes: ['Glab'] } }),
    CURRENT_PERSONALIZATION,
    null,
  );

  assert.equal(result.status, 'migrated');
  assert.deepEqual(result.selection.categoryCodes, ['Glab']);
  assert.equal(result.report.historyAvailable, false);
});

test('a retired category rejects the whole migration', () => {
  const result = migrateLensState(
    staleDecode({ state: { categoryCodes: ['Gurb'], sourceCodes: ['strn'] } }),
    CURRENT_PERSONALIZATION,
    ORIGIN_SNAPSHOT,
  );

  assert.equal(result.status, 'rejected');
  assert.equal(result.reason, 'unresolvable_category');
  assert.equal(result.category, 'Gurb');
  const category = result.report.categories.find((item) => item.code === 'Gurb');
  assert.equal(category.status, 'retired');
  assert.equal(category.formerId, 'urbanism');
});

test('an unknown category rejects the whole migration and is distinguished from retired', () => {
  const result = migrateLensState(
    staleDecode({ state: { categoryCodes: ['Gzzz'] } }),
    CURRENT_PERSONALIZATION,
    ORIGIN_SNAPSHOT,
  );

  assert.equal(result.status, 'rejected');
  assert.equal(result.reason, 'unresolvable_category');
  assert.equal(result.report.categories[0].status, 'unknown');
});

test('a category that became nonselectable is unresolved, not silently dropped', () => {
  const result = migrateLensState(
    staleDecode({ state: { categoryCodes: ['Gcmp'] } }),
    CURRENT_PERSONALIZATION,
    null,
  );

  assert.equal(result.status, 'rejected');
  assert.equal(result.report.categories[0].status, 'unresolved');
});

test('direct intent survives even when a sibling category is unresolvable', () => {
  // The rejection is whole-migration per the acceptance criterion ("a partial
  // personalized score" must not be produced), but the report still shows the
  // direct source resolved cleanly, proving its resolution never depended on
  // the category's fate.
  const result = migrateLensState(
    staleDecode({ state: { categoryCodes: ['Gzzz'], sourceCodes: ['strn'] } }),
    CURRENT_PERSONALIZATION,
    null,
  );

  assert.equal(result.status, 'rejected');
  const source = result.report.sources.find((item) => item.code === 'strn');
  assert.equal(source.status, 'current');
});

test('a reclassified source is dropped and reported with its current role', () => {
  const result = migrateLensState(
    staleDecode({ state: { sourceCodes: ['strn', 'urbn'] } }),
    CURRENT_PERSONALIZATION,
    ORIGIN_SNAPSHOT,
  );

  assert.equal(result.status, 'migrated');
  assert.deepEqual(result.selection.sourceCodes, ['strn']);
  const reclassified = result.report.sources.find((item) => item.code === 'urbn');
  assert.equal(reclassified.status, 'reclassified');
  assert.equal(reclassified.currentRole, 'comparison');
});

test('a retired source is dropped and reported through its tombstone', () => {
  const result = migrateLensState(
    staleDecode({ state: { sourceCodes: ['zret', 'strn'] } }),
    CURRENT_PERSONALIZATION,
    ORIGIN_SNAPSHOT,
  );

  assert.equal(result.status, 'migrated');
  assert.deepEqual(result.selection.sourceCodes, ['strn']);
  const retired = result.report.sources.find((item) => item.code === 'zret');
  assert.equal(retired.status, 'retired');
  assert.equal(retired.formerId, 'a-retired-outlet');
});

test('a source dropped without a tombstone is "removed" when origin history is available', () => {
  const result = migrateLensState(
    staleDecode({ state: { sourceCodes: ['zdrp'] } }),
    CURRENT_PERSONALIZATION,
    ORIGIN_SNAPSHOT,
  );

  assert.equal(result.status, 'migrated');
  assert.deepEqual(result.selection.sourceCodes, []);
  assert.equal(result.report.sources[0].status, 'removed');
});

test('the same dropped source is only "unavailable" without origin history', () => {
  const result = migrateLensState(
    staleDecode({ state: { sourceCodes: ['zdrp'] } }),
    CURRENT_PERSONALIZATION,
    null,
  );

  assert.equal(result.report.sources[0].status, 'unavailable');
  assert.equal(result.report.historyAvailable, false);
});

test('a source never published at any version is "unknown" given origin history', () => {
  const result = migrateLensState(
    staleDecode({ state: { sourceCodes: ['zzzz'] } }),
    CURRENT_PERSONALIZATION,
    ORIGIN_SNAPSHOT,
  );

  assert.equal(result.report.sources[0].status, 'unknown');
});

test('an origin snapshot naming a different panel is treated as absent', () => {
  const mismatched = { ...ORIGIN_SNAPSHOT, panel_id: 'wa-2026-primary-default-sources-v9' };
  const result = migrateLensState(
    staleDecode({ state: { sourceCodes: ['zdrp'] } }),
    CURRENT_PERSONALIZATION,
    mismatched,
  );

  assert.equal(result.report.historyAvailable, false);
  assert.equal(result.report.sources[0].status, 'unavailable');
});

test('an empty audited-mode selection migrates trivially', () => {
  const result = migrateLensState(
    staleDecode({ state: { mode: 'a', categoryCodes: [], sourceCodes: [], showTimes: true } }),
    CURRENT_PERSONALIZATION,
    ORIGIN_SNAPSHOT,
  );

  assert.equal(result.status, 'migrated');
  assert.deepEqual(result.selection, {
    mode: 'a',
    categoryCodes: [],
    sourceCodes: [],
    showTimes: true,
    raceTarget: null,
  });
});

test('the migrated selection preserves the race target and Times flag', () => {
  const result = migrateLensState(
    staleDecode({ state: { sourceCodes: ['strn'], showTimes: true, raceTarget: 'us-house-7' } }),
    CURRENT_PERSONALIZATION,
    ORIGIN_SNAPSHOT,
  );

  assert.equal(result.selection.showTimes, true);
  assert.equal(result.selection.raceTarget, 'us-house-7');
});

test('many-to-many category and direct selection both resolve independently', () => {
  const result = migrateLensState(
    staleDecode({ state: { categoryCodes: ['Glab'], sourceCodes: ['strn'] } }),
    CURRENT_PERSONALIZATION,
    ORIGIN_SNAPSHOT,
  );

  // Deduplication of the resulting effective source set is resolveSelection's
  // job (issue 77), not this module's: migration only decides which raw
  // tokens still carry forward, so 'strn' legitimately appears both as a
  // surviving direct pick and as a member of the surviving 'Glab' category.
  assert.equal(result.status, 'migrated');
  assert.deepEqual(result.selection.categoryCodes, ['Glab']);
  assert.deepEqual(result.selection.sourceCodes, ['strn']);
});

test('the module has no DOM, network, or sibling-lens dependency', () => {
  const source = readFileSync(
    fileURLToPath(
      new URL('../../src/election_guide/rendering/templates/lens-migrate.mjs', import.meta.url),
    ),
    'utf8',
  );
  const code = source.replace(/\/\*[\s\S]*?\*\//g, '').replace(/(^|\s)\/\/.*$/gm, '');

  for (const forbidden of [
    'window',
    'document',
    'location',
    'fetch',
    'localStorage',
    'decodeLensFragment',
    'encodeLensFragment',
    'scoreSelection',
  ]) {
    assert.equal(new RegExp(`\\b${forbidden}\\b`).test(code), false, `unexpected ${forbidden}`);
  }
});
