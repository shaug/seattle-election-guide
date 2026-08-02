import assert from 'node:assert/strict';
import test from 'node:test';
import { migrateLensState } from '../../src/election_guide/rendering/templates/lens-migrate.mjs';
import { assertModuleGuard } from './support/module-guards.mjs';

/**
 * A synthetic successive-panel fixture: v1 (the origin a stale link points
 * at) and v2 (the current published panel), evolved by hand to exercise
 * every migration case the acceptance criteria name. Production has only
 * ever published one panel version, so a hand-built history is the only way
 * to exercise this module at all.
 */
// The registry admits exactly one comparison-role source per panel
// (SourceRegistry.validate_registry), so a legal successive-panel pair must
// keep that count invariant across versions. v1's sole comparison source is
// 'stim'; the panel's comparison slot passes to 'urbn' by v2, so 'stim'
// simply falls out of the published sources list (an "excluded" source is
// never published, matching how excluded-role sources work today).
const ORIGIN_SNAPSHOT = {
  panel_id: 'wa-2026-primary-default-sources-v1',
  panel_version: 'v1',
  categories: [
    {
      id: 'labor',
      code: 'Glab',
      label: 'Labor',
      selectable: true,
      member_source_codes: ['strn', 'zdrp'],
    },
    {
      id: 'urbanism',
      code: 'Gurb',
      label: 'Urbanism',
      selectable: true,
      member_source_codes: ['urbn'],
    },
    {
      id: 'environmental',
      code: 'Genv',
      label: 'Environmental',
      selectable: true,
      member_source_codes: ['zret'],
    },
    {
      id: 'comparison',
      code: 'Gcmp',
      label: 'Comparison',
      selectable: false,
      member_source_codes: [],
    },
  ],
  sources: [
    { id: 'the-stranger', code: 'strn', name: 'The Stranger', panel_role: 'consensus' },
    { id: 'the-urbanist', code: 'urbn', name: 'The Urbanist', panel_role: 'consensus' },
    { id: 'a-retired-outlet', code: 'zret', name: 'A Retired Outlet', panel_role: 'consensus' },
    { id: 'a-dropped-outlet', code: 'zdrp', name: 'A Dropped Outlet', panel_role: 'consensus' },
    {
      id: 'seattle-times-editorial-board',
      code: 'stim',
      name: 'The Seattle Times',
      panel_role: 'comparison',
    },
  ],
};

const CURRENT_PERSONALIZATION = {
  policy: { comparison_source_codes: ['urbn'] },
  categories: [
    // Labor kept 'strn', gained a genuinely new selectable source 'newp',
    // and lost 'zdrp' (a source dropped without a tombstone). A comparison
    // source can never be a member of a selectable category, so the
    // reclassified 'urbn' case below is exercised only as a direct pick.
    {
      id: 'labor',
      code: 'Glab',
      label: 'Labor',
      selectable: true,
      member_source_codes: ['newp', 'strn'],
    },
    // Urbanism was retired outright: the category itself is gone.
    // Environmental's only member (zret) was retired, leaving it empty.
    {
      id: 'environmental',
      code: 'Genv',
      label: 'Environmental',
      selectable: true,
      member_source_codes: [],
    },
    {
      id: 'comparison',
      code: 'Gcmp',
      label: 'Comparison',
      selectable: false,
      member_source_codes: [],
    },
  ],
  sources: [
    { id: 'the-stranger', code: 'strn', panel_role: 'consensus', selectable: true },
    { id: 'a-new-outlet', code: 'newp', panel_role: 'consensus', selectable: true },
    // the-urbanist's code now names the panel's one comparison source: this
    // and 'stim' falling out of the sources list together keep the
    // exactly-one-comparison-source invariant true in both panel versions.
    { id: 'the-urbanist', code: 'urbn', panel_role: 'comparison', selectable: false },
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

test('an identified but nonselectable category is unresolved: a publishable one is necessarily empty', () => {
  // Gcmp is identified (found by code) but PersonalizationCategory.validate_members
  // forbids a nonselectable category from publishing any members, so this case
  // cannot be distinguished from an emptied selectable category by a
  // publishable payload; both correctly reject as 'unresolved'.
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
    staleDecode({ state: { mode: 'a', categoryCodes: [], sourceCodes: [] } }),
    CURRENT_PERSONALIZATION,
    ORIGIN_SNAPSHOT,
  );

  assert.equal(result.status, 'migrated');
  assert.deepEqual(result.selection, {
    mode: 'a',
    categoryCodes: [],
    sourceCodes: [],
    raceTarget: null,
  });
});

test('the migrated selection preserves the race target', () => {
  const result = migrateLensState(
    staleDecode({ state: { sourceCodes: ['strn'], raceTarget: 'us-house-7' } }),
    CURRENT_PERSONALIZATION,
    ORIGIN_SNAPSHOT,
  );

  assert.equal(result.selection.raceTarget, 'us-house-7');
});

test('a stale comparison-source selection (the old Times flag) migrates like any other source', () => {
  const result = migrateLensState(
    staleDecode({ state: { mode: 'a', sourceCodes: ['stim'] } }),
    CURRENT_PERSONALIZATION,
    ORIGIN_SNAPSHOT,
  );

  assert.equal(result.status, 'migrated');
  // 'stim' fell out of the published sources list between these two panel
  // versions (the fixture's comparison slot passed to 'urbn'), so it no
  // longer resolves; a source narrows the migrated selection rather than
  // rejecting the whole link, so audited mode is still representable.
  assert.deepEqual(result.selection.sourceCodes, []);
  assert.equal(result.report.sources[0].status, 'removed');
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

test('a surviving category reports which current members are new, given origin history', () => {
  const result = migrateLensState(
    staleDecode({ state: { categoryCodes: ['Glab'] } }),
    CURRENT_PERSONALIZATION,
    ORIGIN_SNAPSHOT,
  );

  assert.equal(result.status, 'migrated');
  const category = result.report.categories.find((item) => item.code === 'Glab');
  assert.equal(category.status, 'current');
  assert.deepEqual(category.addedMemberCodes, ['newp']);
  assert.deepEqual(category.removedMemberCodes, ['zdrp']);
});

test('a surviving category omits the membership diff without origin history', () => {
  // Absence means "not compared", not "unchanged": field presence tracks
  // report.historyAvailable alone.
  const result = migrateLensState(
    staleDecode({ state: { categoryCodes: ['Glab'] } }),
    CURRENT_PERSONALIZATION,
    null,
  );

  assert.equal(result.report.historyAvailable, false);
  const category = result.report.categories[0];
  assert.equal(category.status, 'current');
  assert.equal('addedMemberCodes' in category, false);
  assert.equal('removedMemberCodes' in category, false);
});

test('a category absent from a matched origin snapshot reports every current member as added', () => {
  const originWithoutLabor = {
    ...ORIGIN_SNAPSHOT,
    categories: ORIGIN_SNAPSHOT.categories.filter((item) => item.code !== 'Glab'),
  };
  const result = migrateLensState(
    staleDecode({ state: { categoryCodes: ['Glab'] } }),
    CURRENT_PERSONALIZATION,
    originWithoutLabor,
  );

  assert.equal(result.status, 'migrated');
  const category = result.report.categories[0];
  assert.equal(category.status, 'current');
  assert.deepEqual(category.addedMemberCodes, ['newp', 'strn']);
  assert.deepEqual(category.removedMemberCodes, []);
});

test('a category emptied of every member is unresolved rather than a silent empty selection', () => {
  // Genv is still selectable in the current panel, but its only member (zret)
  // was retired, so it can no longer stand for anything. This must reject
  // even with no origin history available, since it needs none to detect.
  const result = migrateLensState(
    staleDecode({ state: { categoryCodes: ['Genv'] } }),
    CURRENT_PERSONALIZATION,
    null,
  );

  assert.equal(result.status, 'rejected');
  assert.equal(result.reason, 'unresolvable_category');
  assert.equal(result.category, 'Genv');
  assert.equal(result.report.categories[0].status, 'unresolved');
});

test('a multi-code migrated selection is sorted regardless of input order', () => {
  const result = migrateLensState(
    staleDecode({ state: { sourceCodes: ['zdrp', 'zzzz', 'strn', 'newp'] } }),
    CURRENT_PERSONALIZATION,
    ORIGIN_SNAPSHOT,
  );

  assert.equal(result.status, 'migrated');
  // Two surviving codes supplied out of order must come back sorted.
  assert.deepEqual(result.selection.sourceCodes, ['newp', 'strn']);
  const statuses = Object.fromEntries(
    result.report.sources.map((item) => [item.code, item.status]),
  );
  assert.deepEqual(statuses, {
    zdrp: 'removed',
    zzzz: 'unknown',
    strn: 'current',
    newp: 'current',
  });
});

test('the module stays pure', () => {
  assertModuleGuard('lens-migrate.mjs');
});
