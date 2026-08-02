import assert from 'node:assert/strict';
import test from 'node:test';
import {
  ALL_SOURCES_TOKEN,
  COMPARE_SCHEMA_VERSION,
  compareContext,
  decodeCompareFragment,
  encodeCompareFragment,
} from '../../src/election_guide/rendering/templates/compare-url.mjs';
import {
  decodeLensFragment,
  encodeLensFragment,
  lensContext,
} from '../../src/election_guide/rendering/templates/lens-url.mjs';
import { assertModuleGuard } from './support/module-guards.mjs';

const PANEL_HASH = '6cd4acaa0c5e4ed0b5ddd0134d7de2af5a54c2085e7ad463f9b575b8e6dcb43f';

function personalization(overrides = {}) {
  return {
    panel_id: 'wa-2026-primary-default-sources-v4',
    panel_hash: PANEL_HASH,
    scoring: { configuration_id: 'wa-2026-primary-equal-weight' },
    policy: { maximum_url_characters: 4096 },
    categories: [
      { id: 'labor', code: 'Glab', selectable: true },
      { id: 'environmental', code: 'Genv', selectable: true },
    ],
    sources: [
      { id: 'the-stranger', code: 'strn', selectable: true },
      { id: 'the-urbanist', code: 'urbn', selectable: true },
      { id: 'mlk-labor', code: 'mlkl', selectable: true },
      { id: 'seattle-times-editorial-board', code: 'stim', selectable: true },
    ],
    retired_codes: [],
    ...overrides,
  };
}

function comparisons() {
  return {
    display_index: [
      { race_id: 'city-attorney', section_id: 'city-of-seattle' },
      { race_id: 'us-house-7', section_id: 'congressional' },
    ],
  };
}

function context(overrides = {}) {
  const payload = personalization(overrides);
  return compareContext(payload, 'd119ee3107bb', comparisons());
}

function encoded(state, ctx = context()) {
  const result = encodeCompareFragment(state, ctx);
  assert.equal(result.status, 'ok', `expected encodable state, got ${JSON.stringify(result)}`);
  return result.fragment;
}

test('the comparison fragment records its schema, ordered columns, and full binding', () => {
  const fragment = encoded({
    columns: [ALL_SOURCES_TOKEN, 'strn', 'stim'],
    differencesOnly: true,
    contestedOnly: true,
    section: 'city-of-seattle',
  });
  const parameters = new URLSearchParams(fragment);
  assert.equal(parameters.get('cmp'), COMPARE_SCHEMA_VERSION);
  assert.equal(parameters.get('cols'), 'gallstrnstim');
  assert.equal(parameters.get('panel'), 'wa-2026-primary-default-sources-v4');
  assert.equal(parameters.get('ph'), PANEL_HASH.slice(0, 12));
  assert.equal(parameters.get('data'), 'd119ee3107bb');
  assert.equal(parameters.get('scoring'), 'wa-2026-primary-equal-weight');
  assert.equal(parameters.get('diff'), '1');
  assert.equal(parameters.get('races'), 'contested');
  assert.equal(parameters.get('show'), 'city-of-seattle');
});

test('property-tested valid states decode losslessly and re-encode canonically', () => {
  let seed = 0x119;
  const random = () => {
    seed = (seed * 1664525 + 1013904223) >>> 0;
    return seed / 2 ** 32;
  };
  const tokens = ['gall', 'strn', 'stim', 'urbn', 'mlkl', 'Glab', 'Genv'];
  const sections = ['all', 'city-of-seattle', 'congressional'];
  for (let iteration = 0; iteration < 500; iteration += 1) {
    const shuffled = [...tokens].sort(() => random() - 0.5);
    const columns = shuffled.slice(0, random() < 0.5 ? 2 : 3);
    const state = {
      columns,
      differencesOnly: random() < 0.5,
      contestedOnly: random() < 0.5,
      section: sections[Math.floor(random() * sections.length)],
    };
    const fragment = encoded(state);
    const decoded = decodeCompareFragment(fragment, context());
    assert.equal(decoded.status, 'valid');
    assert.deepEqual(decoded.state, state);
    assert.equal(encoded(decoded.state), fragment);
  }
});

test('column order and reference-first identity round-trip without sorting', () => {
  for (const columns of [
    ['strn', 'gall'],
    ['stim', 'Glab', 'strn'],
    ['Genv', 'urbn', 'gall'],
  ]) {
    const decoded = decodeCompareFragment(encoded({ columns }), context());
    assert.equal(decoded.status, 'valid');
    assert.deepEqual(decoded.state.columns, columns);
    assert.equal(decoded.state.columns[0], columns[0]);
  }
});

test('exact duplicate columns are removed before enforcing the two-to-three column limit', () => {
  const decoded = decodeCompareFragment(encoded({ columns: ['gall', 'strn', 'gall'] }), context());
  assert.deepEqual(decoded.state.columns, ['gall', 'strn']);
  for (const columns of [['gall'], ['gall', 'strn', 'stim', 'urbn']]) {
    const result = encodeCompareFragment({ columns }, context());
    assert.equal(result.status, 'rejected');
    assert.equal(result.reason, 'column_count');
  }
});

test('gmin and every other lowercase-g token reject distinctly as reserved', () => {
  for (const token of ['gmin', 'gzzz', 'gALL']) {
    const decode = decodeCompareFragment(
      encoded({ columns: ['gall', 'strn'] }).replace('gallstrn', `gall${token}`),
      context(),
    );
    assert.equal(decode.status, 'malformed');
    assert.equal(decode.reason, 'reserved_token');
    assert.equal(decode.token, token);
    const encode = encodeCompareFragment({ columns: ['gall', token] }, context());
    assert.equal(encode.status, 'rejected');
    assert.equal(encode.reason, 'reserved_token');
  }
});

test('unknown, case-confusable, forbidden, malformed, and ragged tokens reject deterministically', () => {
  const base = encoded({ columns: ['gall', 'strn'] });
  for (const [selection, reason] of [
    ['gallzzzz', 'unknown_token'],
    ['gallSTRN', 'case_confusable_token'],
    ['gallstr', 'ragged_selection'],
  ]) {
    const decoded = decodeCompareFragment(base.replace('gallstrn', selection), context());
    assert.equal(decoded.status, 'malformed');
    assert.equal(decoded.reason, reason);
  }
  const forbidden = context({
    sources: [...personalization().sources, { id: 'excluded', code: 'excl', selectable: false }],
  });
  assert.equal(
    decodeCompareFragment(base.replace('gallstrn', 'gallexcl'), forbidden).reason,
    'forbidden_token',
  );
});

test('filters round-trip and invalid filter values reject', () => {
  const state = {
    columns: ['gall', 'stim'],
    differencesOnly: true,
    contestedOnly: true,
    section: 'congressional',
  };
  assert.deepEqual(decodeCompareFragment(encoded(state), context()).state, state);
  const base = encoded({ columns: ['gall', 'stim'] });
  assert.equal(decodeCompareFragment(`${base}&diff=0`, context()).reason, 'unknown_toggle');
  assert.equal(decodeCompareFragment(`${base}&races=all`, context()).reason, 'unknown_filter');
  assert.equal(decodeCompareFragment(`${base}&show=missing`, context()).reason, 'unknown_section');
});

test('cross-version links preserve ordered intent for migration before token admission', () => {
  const fragment = encoded({
    columns: ['stim', 'Glab', 'strn'],
    differencesOnly: true,
    section: 'city-of-seattle',
  });
  const successor = context({ panel_id: 'wa-2026-primary-default-sources-v5' });
  const decoded = decodeCompareFragment(fragment, successor);
  assert.equal(decoded.status, 'stale_version');
  assert.deepEqual(decoded.state.columns, ['stim', 'Glab', 'strn']);
  assert.equal(decoded.state.differencesOnly, true);
  assert.equal(decoded.state.section, 'city-of-seattle');
});

test('oversized fragments reject in both directions', () => {
  const tight = context({ policy: { maximum_url_characters: 64 } });
  const encode = encodeCompareFragment({ columns: ['gall', 'strn'] }, tight);
  assert.equal(encode.status, 'rejected');
  assert.equal(encode.reason, 'oversized');
  const decode = decodeCompareFragment('a'.repeat(65), tight);
  assert.equal(decode.status, 'malformed');
  assert.equal(decode.reason, 'oversized');
});

test('lens and comparison fragments reject cleanly on the other page', () => {
  const lensCtx = lensContext(personalization(), 'd119ee3107bb');
  const lens = encodeLensFragment({ mode: 's', sourceCodes: ['strn'] }, lensCtx);
  assert.equal(lens.status, 'ok');
  const compareDecode = decodeCompareFragment(lens.fragment, context());
  assert.equal(compareDecode.status, 'malformed');
  assert.equal(compareDecode.reason, 'not_for_this_page');

  const comparison = encoded({ columns: ['gall', 'strn'] });
  const lensDecode = decodeLensFragment(comparison, lensCtx);
  assert.equal(lensDecode.status, 'malformed');
  assert.equal(lensDecode.reason, 'unsupported_schema');
});

test('the codec stays pure', () => {
  assertModuleGuard('compare-url.mjs');
});
