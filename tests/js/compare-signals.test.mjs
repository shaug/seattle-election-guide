import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import test from 'node:test';

import { assertModuleGuard } from './support/module-guards.mjs';
import {
  BLANK_CELL,
  OUTSIDE_SCOPE_CELL,
  cellAgreement,
  createColumnSignalEngine,
  leadSetsIntersect,
  rowDiffers,
} from '../../src/election_guide/rendering/templates/compare-signals.mjs';

const sources = [
  { code: 'aaaa', panel_role: 'consensus', selectable: true },
  { code: 'bbbb', panel_role: 'consensus', selectable: true },
  { code: 'cccc', panel_role: 'consensus', selectable: true },
  { code: 'ld11', panel_role: 'consensus', selectable: true },
  { code: 'ld32', panel_role: 'consensus', selectable: true },
  { code: 'stim', panel_role: 'comparison', selectable: true },
  { code: 'nend', panel_role: 'consensus', selectable: true },
  { code: 'ncov', panel_role: 'consensus', selectable: true },
  { code: 'unav', panel_role: 'consensus', selectable: true },
  { code: 'unvr', panel_role: 'consensus', selectable: true },
];

const categories = [
  {
    code: 'Gall',
    panel_role: 'tallying',
    selectable: true,
    member_source_codes: ['aaaa', 'bbbb', 'cccc'],
  },
  {
    code: 'Gdem',
    panel_role: 'tallying',
    selectable: true,
    member_source_codes: ['aaaa', 'ld11', 'ld32'],
  },
  {
    code: 'Gmix',
    panel_role: 'tallying',
    selectable: true,
    member_source_codes: ['aaaa', 'bbbb', 'stim'],
  },
  {
    code: 'Gcmp',
    panel_role: 'comparison',
    selectable: true,
    member_source_codes: ['stim'],
  },
];

const personalization = {
  policy: { comparison_source_codes: ['stim'] },
  sources,
  categories,
  scoring: {
    minimum_explicit_sources: 2,
    grades: [
      { grade: 'A+', minimum_share: '9/10', minimum_explicit_sources: 4 },
      { grade: 'A', minimum_share: '3/4' },
      { grade: 'B', minimum_share: '3/5' },
      { grade: 'C', minimum_share: '9/20' },
      { grade: 'D', minimum_share: '0' },
    ],
  },
};

const race = {
  race_id: 'fixture-race',
  candidate_order: ['alpha', 'beta'],
  eligible_source_codes: [
    'aaaa',
    'bbbb',
    'cccc',
    'ld11',
    'stim',
    'nend',
    'ncov',
    'unav',
    'unvr',
  ],
  cells: [
    {
      source_code: 'aaaa',
      state: 'endorsement',
      allocation: { alpha: '1' },
      confidence_warning: false,
    },
    {
      source_code: 'bbbb',
      state: 'multi_endorsement',
      allocation: { alpha: '1/2', beta: '1/2' },
      confidence_warning: false,
    },
    {
      source_code: 'cccc',
      state: 'endorsement',
      allocation: { beta: '1' },
      confidence_warning: false,
    },
    {
      source_code: 'ld11',
      state: 'endorsement',
      allocation: { beta: '1' },
      confidence_warning: false,
    },
    {
      source_code: 'stim',
      state: 'endorsement',
      allocation: { beta: '1' },
      confidence_warning: false,
    },
    { source_code: 'nend', state: 'no_endorsement', allocation: {}, confidence_warning: false },
    { source_code: 'ncov', state: 'not_covered', allocation: {}, confidence_warning: false },
    { source_code: 'unav', state: 'unavailable', allocation: {}, confidence_warning: false },
    { source_code: 'unvr', state: 'unverified', allocation: {}, confidence_warning: false },
  ],
};

const comparisons = {
  display_index: [
    {
      race_id: race.race_id,
      baseline: {
        leading_pick_ids: ['beta'],
        share: '7/13',
        explicit_source_count: 13,
      },
    },
  ],
};

const engine = createColumnSignalEngine(personalization, comparisons);

test('gall resolves the published all-sources result verbatim', () => {
  assert.deepEqual(engine.resolveColumn('gall', race), {
    kind: 'baseline',
    leadingPickIds: ['beta'],
    share: '7/13',
    endorsingCount: 13,
  });
});

test('direct and comparison cells preserve the published exact allocation', () => {
  assert.deepEqual(engine.resolveColumn('bbbb', race), {
    kind: 'direct',
    sourceCode: 'bbbb',
    leadingPickIds: ['alpha', 'beta'],
    allocation: { alpha: '1/2', beta: '1/2' },
  });
  assert.deepEqual(engine.resolveColumn('stim', race), {
    kind: 'comparison',
    sourceCode: 'stim',
    leadingPickIds: ['beta'],
    allocation: { beta: '1' },
  });
  assert.deepEqual(engine.resolveColumn('Gcmp', race), engine.resolveColumn('stim', race));
});

test('category aggregation preserves exact splits and complete tie lead sets', () => {
  assert.deepEqual(engine.resolveColumn('Gall', race), {
    kind: 'aggregate',
    categoryCode: 'Gall',
    leadingPickIds: ['alpha', 'beta'],
    share: '1/2',
    endorsingCount: 3,
    memberCount: 3,
    allocation: { alpha: '3/2', beta: '3/2' },
  });
});

test('multi-category membership and district eligibility use current eligible members once', () => {
  assert.deepEqual(engine.resolveColumn('Gdem', race), {
    kind: 'aggregate',
    categoryCode: 'Gdem',
    leadingPickIds: ['alpha', 'beta'],
    share: '1/2',
    endorsingCount: 2,
    memberCount: 2,
    allocation: { alpha: '1', beta: '1' },
  });
  assert.strictEqual(engine.resolveColumn('ld32', race), OUTSIDE_SCOPE_CELL);
});

test('a comparison-role code forced into a tallying category contributes nothing', () => {
  assert.deepEqual(engine.resolveColumn('Gmix', race), {
    kind: 'aggregate',
    categoryCode: 'Gmix',
    leadingPickIds: ['alpha'],
    share: '3/4',
    endorsingCount: 2,
    memberCount: 2,
    allocation: { alpha: '3/2', beta: '1/2' },
  });
});

test('all four non-affirmative states resolve to the identical blank cell', () => {
  for (const code of ['nend', 'ncov', 'unav', 'unvr']) {
    assert.strictEqual(engine.resolveColumn(code, race), BLANK_CELL);
  }
});

test('lead-set agreement handles overlap, disjoint sets, and neutral cells', () => {
  const reference = { kind: 'baseline', leadingPickIds: ['alpha', 'beta'] };
  const overlap = { kind: 'direct', leadingPickIds: ['beta'] };
  const disjoint = { kind: 'direct', leadingPickIds: ['gamma'] };

  assert.equal(leadSetsIntersect(reference, overlap), true);
  assert.equal(cellAgreement(overlap, reference), 'agree');
  assert.equal(cellAgreement(disjoint, reference), 'differ');
  assert.equal(cellAgreement(BLANK_CELL, reference), 'neutral');
  assert.equal(cellAgreement(OUTSIDE_SCOPE_CELL, reference), 'neutral');
});

test('row differences compare each configured data cell only to the reference', () => {
  const alpha = { kind: 'direct', leadingPickIds: ['alpha'] };
  const alphaBeta = { kind: 'direct', leadingPickIds: ['alpha', 'beta'] };
  const beta = { kind: 'direct', leadingPickIds: ['beta'] };
  const gamma = { kind: 'direct', leadingPickIds: ['gamma'] };

  assert.equal(rowDiffers([alpha, alphaBeta, BLANK_CELL, OUTSIDE_SCOPE_CELL]), false);
  assert.equal(rowDiffers([alpha, alphaBeta, beta]), true);
  assert.equal(rowDiffers([alphaBeta, alpha, beta]), false);
  assert.equal(rowDiffers([alpha, alphaBeta, gamma]), true);
});

test('every current-election gall cell equals the audited scoring oracle exactly', () => {
  const fixture = JSON.parse(
    readFileSync(fileURLToPath(new URL('./fixtures/lens-parity.json', import.meta.url)), 'utf8'),
  );
  const fullPanel = fixture.cases.find((item) => item.name === 'full-panel');
  const currentComparisons = {
    display_index: fullPanel.races.map((published) => ({
      race_id: published.race_id,
      baseline: {
        leading_pick_ids: published.winner_candidate_ids,
        share: published.winner_share,
        explicit_source_count: published.explicit_endorsement_count,
      },
    })),
  };
  const currentEngine = createColumnSignalEngine(fixture.personalization, currentComparisons);

  for (const published of fullPanel.races) {
    const currentRace = fixture.personalization.races.find(
      (candidate) => candidate.race_id === published.race_id,
    );
    assert.deepEqual(currentEngine.resolveColumn('gall', currentRace), {
      kind: 'baseline',
      leadingPickIds: published.winner_candidate_ids,
      share: published.winner_share,
      endorsingCount: published.explicit_endorsement_count,
    });
  }
});

test('the signal engine stays pure', () => {
  assertModuleGuard('compare-signals.mjs');
});
