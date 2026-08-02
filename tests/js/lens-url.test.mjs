import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';
import { fileURLToPath } from 'node:url';
import {
  decodeLensFragment,
  encodeLensFragment,
  LENS_SCHEMA_VERSION,
  lensContext,
} from '../../src/election_guide/rendering/templates/lens-url.mjs';
import { assertModuleGuard } from './support/module-guards.mjs';

const PANEL_HASH = '6cd4acaa0c5e4ed0b5ddd0134d7de2af5a54c2085e7ad463f9b575b8e6dcb43f';

/** A published payload shaped like the committed personalization contract. */
function personalization(overrides = {}) {
  return {
    panel_id: 'wa-2026-primary-default-sources-v4',
    panel_hash: PANEL_HASH,
    scoring: { configuration_id: 'wa-2026-primary-equal-weight' },
    policy: { maximum_url_characters: 4096 },
    categories: [
      { id: 'labor', code: 'Glab', selectable: true, panel_role: 'tallying' },
      { id: 'environmental', code: 'Genv', selectable: true, panel_role: 'tallying' },
      { id: 'comparison', code: 'Gcmp', selectable: true, panel_role: 'comparison' },
    ],
    sources: [
      { id: 'the-stranger', code: 'strn', selectable: true, panel_role: 'consensus' },
      { id: 'the-urbanist', code: 'urbn', selectable: true, panel_role: 'consensus' },
      { id: 'mlk-labor', code: 'mlkl', selectable: true, panel_role: 'consensus' },
      {
        id: 'seattle-times-editorial-board',
        code: 'stim',
        selectable: true,
        panel_role: 'comparison',
      },
    ],
    ...overrides,
  };
}

function context(overrides) {
  return lensContext(personalization(overrides), 'd119ee3107bb');
}

function encoded(state, ctx = context()) {
  const result = encodeLensFragment(state, ctx);
  assert.equal(result.status, 'ok', `expected encodable state, got ${JSON.stringify(result)}`);
  return result.fragment;
}

test('the published policy governs the sharing-size limit', () => {
  assert.equal(context().maximumUrlCharacters, 4096);
});

test('an audited state carrying only a comparison token is the plain baseline', () => {
  const fragment = encoded({ mode: 'a', sourceCodes: ['stim'] });
  const decoded = decodeLensFragment(fragment, context());

  assert.equal(decoded.status, 'valid');
  assert.equal(decoded.state.mode, 'a');
  assert.deepEqual(decoded.state.categoryCodes, []);
  assert.deepEqual(decoded.state.sourceCodes, []);
});

test('a comparison token is dropped from a personalized state, not rejected', () => {
  for (const withComparison of [true, false]) {
    const sourceCodes = withComparison ? ['strn', 'stim'] : ['strn'];
    const state = { mode: 's', categoryCodes: ['Glab'], sourceCodes };
    const decoded = decodeLensFragment(encoded(state), context());

    assert.equal(decoded.status, 'valid');
    assert.equal(decoded.state.mode, 's');
    assert.deepEqual(decoded.state.categoryCodes, ['Glab']);
    assert.deepEqual(decoded.state.sourceCodes, ['strn']);
  }
});

test('the fragment records the schema, mode, and version bindings', () => {
  const fragment = encoded({ mode: 's', sourceCodes: ['strn'] });
  const parameters = new URLSearchParams(fragment);

  assert.equal(parameters.get('lens'), LENS_SCHEMA_VERSION);
  assert.equal(parameters.get('mode'), 's');
  assert.equal(parameters.get('panel'), 'wa-2026-primary-default-sources-v4');
  assert.equal(parameters.get('ph'), PANEL_HASH.slice(0, 12));
  assert.equal(parameters.get('data'), 'd119ee3107bb');
  assert.equal(parameters.get('scoring'), 'wa-2026-primary-equal-weight');
  assert.equal(parameters.get('times'), null, 'the standalone Times flag no longer exists');
  assert.equal(parameters.get('sel'), 'strn');
});

test('same-version encoding is canonical and lossless', () => {
  const state = {
    mode: 's',
    categoryCodes: ['Glab', 'Genv'],
    sourceCodes: ['urbn', 'strn'],
    raceTarget: 'us-house-7',
  };
  const fragment = encoded(state);
  const decoded = decodeLensFragment(fragment, context());

  assert.equal(decoded.status, 'valid');
  assert.deepEqual(decoded.state, {
    mode: 's',
    categoryCodes: ['Genv', 'Glab'],
    sourceCodes: ['strn', 'urbn'],
    raceTarget: 'us-house-7',
  });
  assert.equal(encoded(decoded.state), fragment);
});

test('category tokens are ordered before source tokens regardless of input order', () => {
  const fragment = encoded({
    mode: 's',
    categoryCodes: ['Glab'],
    sourceCodes: ['strn', 'mlkl'],
  });

  assert.equal(new URLSearchParams(fragment).get('sel'), 'Glabmlklstrn');
});

test('exact duplicates are removed while direct and category intent is preserved', () => {
  const decoded = decodeLensFragment(
    encoded({
      mode: 's',
      categoryCodes: ['Glab', 'Glab'],
      sourceCodes: ['mlkl', 'mlkl', 'strn'],
    }),
    context(),
  );

  assert.equal(decoded.status, 'valid');
  assert.deepEqual(decoded.state.categoryCodes, ['Glab']);
  assert.deepEqual(decoded.state.sourceCodes, ['mlkl', 'strn']);
});

test('a category selection is not expanded into its members', () => {
  const decoded = decodeLensFragment(encoded({ mode: 's', categoryCodes: ['Glab'] }), context());

  assert.deepEqual(decoded.state.categoryCodes, ['Glab']);
  assert.deepEqual(decoded.state.sourceCodes, []);
});

test('empty, individual-only, category-only, and mixed selections round-trip', () => {
  const selections = [
    { categoryCodes: [], sourceCodes: [] },
    { categoryCodes: [], sourceCodes: ['strn', 'urbn'] },
    { categoryCodes: ['Genv', 'Glab'], sourceCodes: [] },
    { categoryCodes: ['Glab'], sourceCodes: ['strn'] },
  ];
  for (const selection of selections) {
    const state = { mode: 's', ...selection };
    const decoded = decodeLensFragment(encoded(state), context());

    assert.equal(decoded.status, 'valid');
    assert.deepEqual(decoded.state.categoryCodes, [...selection.categoryCodes].sort());
    assert.deepEqual(decoded.state.sourceCodes, [...selection.sourceCodes].sort());
  }
});

test('sel is parsed in four-character chunks', () => {
  const decoded = decodeLensFragment(
    encoded({ mode: 's', categoryCodes: ['Glab'], sourceCodes: ['strn', 'urbn'] }),
    context(),
  );

  assert.deepEqual(decoded.state.categoryCodes, ['Glab']);
  assert.deepEqual(decoded.state.sourceCodes, ['strn', 'urbn']);
});

test('a ragged selection cannot be scored', () => {
  const decoded = decodeLensFragment(
    'lens=2&mode=s&panel=wa-2026-primary-default-sources-v4&ph=6cd4acaa0c5e' +
      '&data=d119ee3107bb&scoring=wa-2026-primary-equal-weight&sel=strnurb',
    context(),
  );

  assert.equal(decoded.status, 'malformed');
  assert.equal(decoded.reason, 'ragged_selection');
});

test('an unknown token cannot be scored', () => {
  const decoded = decodeLensFragment(`${encoded({ mode: 's' })}&sel=zzzz`, context());

  assert.equal(decoded.status, 'malformed');
  assert.equal(decoded.reason, 'unknown_token');
  assert.equal(decoded.token, 'zzzz');
});

test('a case-confusable token is rejected rather than silently matched', () => {
  const decoded = decodeLensFragment(`${encoded({ mode: 's' })}&sel=STRN`, context());

  assert.equal(decoded.status, 'malformed');
  assert.equal(decoded.reason, 'case_confusable_token');
  assert.equal(decoded.token, 'STRN');
});

// Issue 124 retired the guide-side comparison. A link written before that
// removal may still name a comparison source or its category; the codec
// ignores those tokens and replays everything else exactly.
test('a comparison token is silently ignored, never rejected', () => {
  for (const token of ['stim', 'Gcmp']) {
    const decoded = decodeLensFragment(
      `${encoded({ mode: 's', sourceCodes: ['strn'] })}${token}`,
      context(),
    );

    assert.equal(decoded.status, 'valid');
    assert.deepEqual(decoded.state.categoryCodes, []);
    assert.deepEqual(decoded.state.sourceCodes, ['strn']);
  }

  // An unknown token is still a real error: only a published comparison
  // identity is dropped.
  const unknown = decodeLensFragment(`${encoded({ mode: 's' })}&sel=zzzz`, context());
  assert.equal(unknown.status, 'malformed');
  assert.equal(unknown.reason, 'unknown_token');
});

test('a comparison token never survives re-encoding', () => {
  const result = encodeLensFragment(
    { mode: 's', categoryCodes: ['Gcmp'], sourceCodes: ['strn', 'stim'] },
    context(),
  );

  assert.equal(result.status, 'ok');
  assert.equal(new URLSearchParams(result.fragment).get('sel'), 'strn');
});

test('audited mode still refuses an ordinary selection', () => {
  const rejected = decodeLensFragment(`${encoded({ mode: 'a' })}&sel=strn`, context());
  assert.equal(rejected.status, 'malformed');
  assert.equal(rejected.reason, 'audited_mode_carries_selection');
  assert.equal(rejected.token, 'strn');

  const encodeRejected = encodeLensFragment({ mode: 'a', sourceCodes: ['strn'] }, context());
  assert.equal(encodeRejected.status, 'rejected');
  assert.equal(encodeRejected.reason, 'audited_mode_carries_selection');

  // A comparison token is dropped first, so an audited link that carried
  // only one still encodes as the plain audited baseline.
  const comparisonOnly = encodeLensFragment({ mode: 'a', sourceCodes: ['stim'] }, context());
  assert.equal(comparisonOnly.status, 'ok');
  assert.equal(new URLSearchParams(comparisonOnly.fragment).get('sel'), null);
});

test('a nonselectable category cannot be selected', () => {
  const inactive = context({
    categories: [
      ...personalization().categories,
      { id: 'inactive', code: 'Gzzq', selectable: false, panel_role: 'tallying' },
    ],
  });

  const rejected = encodeLensFragment({ mode: 's', categoryCodes: ['Gzzq'] }, inactive);
  assert.equal(rejected.status, 'rejected');
  assert.equal(rejected.reason, 'forbidden_token');

  const decoded = decodeLensFragment(`${encoded({ mode: 's' }, inactive)}&sel=Gzzq`, inactive);
  assert.equal(decoded.status, 'malformed');
  assert.equal(decoded.reason, 'forbidden_token');
});

test('an excluded source cannot be selected', () => {
  const withExcluded = context({
    sources: [
      ...personalization().sources,
      { id: 'excluded-outlet', code: 'excl', selectable: false, panel_role: 'excluded' },
    ],
  });

  const rejected = encodeLensFragment({ mode: 's', sourceCodes: ['excl'] }, withExcluded);
  assert.equal(rejected.status, 'rejected');
  assert.equal(rejected.reason, 'forbidden_token');
});

test('an oversized fragment cannot be scored', () => {
  const tight = context({ policy: { maximum_url_characters: 64 } });
  const rejected = encodeLensFragment({ mode: 's', sourceCodes: ['strn'] }, tight);

  assert.equal(rejected.status, 'rejected');
  assert.equal(rejected.reason, 'oversized');
  assert.equal(rejected.limit, 64);

  const decoded = decodeLensFragment('a'.repeat(65), tight);
  assert.equal(decoded.status, 'malformed');
  assert.equal(decoded.reason, 'oversized');
});

test('an unsupported schema version cannot be scored', () => {
  const decoded = decodeLensFragment(encoded({ mode: 'a' }).replace('lens=2', 'lens=3'), context());

  assert.equal(decoded.status, 'malformed');
  assert.equal(decoded.reason, 'unsupported_schema');
});

test('a fragment written under the prior (Times-flag) schema fails to decode', () => {
  const legacyStyleFragment =
    'lens=1&mode=a&panel=wa-2026-primary-default-sources-v4&ph=6cd4acaa0c5e' +
    '&data=d119ee3107bb&scoring=wa-2026-primary-equal-weight&times=1';
  const decoded = decodeLensFragment(legacyStyleFragment, context());

  assert.equal(decoded.status, 'malformed');
  assert.equal(decoded.reason, 'unsupported_schema');
});

test('a missing mode cannot be scored', () => {
  const decoded = decodeLensFragment(encoded({ mode: 'a' }).replace('&mode=a', ''), context());

  assert.equal(decoded.status, 'malformed');
  assert.equal(decoded.reason, 'unknown_mode');
});

test('a missing version binding cannot be scored', () => {
  const decoded = decodeLensFragment(
    encoded({ mode: 'a' }).replace('&scoring=wa-2026-primary-equal-weight', ''),
    context(),
  );

  assert.equal(decoded.status, 'malformed');
  assert.equal(decoded.reason, 'missing_binding');
  assert.equal(decoded.parameter, 'scoringId');
});

test('a repeated parameter cannot be scored', () => {
  const decoded = decodeLensFragment(`${encoded({ mode: 'a' })}&mode=s`, context());

  assert.equal(decoded.status, 'malformed');
  assert.equal(decoded.reason, 'repeated_parameter');
});

test('a link written against another panel decodes as stale rather than valid', () => {
  const fragment = encoded({ mode: 's', sourceCodes: ['strn'] });
  const successor = context({ panel_id: 'wa-2026-primary-default-sources-v5' });
  const decoded = decodeLensFragment(fragment, successor);

  assert.equal(decoded.status, 'stale_version');
  assert.equal(decoded.binding.panelId, 'wa-2026-primary-default-sources-v4');
  assert.deepEqual(decoded.state.sourceCodes, ['strn'], 'intent is preserved for migration');
});

test('a cross-version link stays stale when its codes no longer exist', () => {
  const fragment = encoded({
    mode: 's',
    categoryCodes: ['Glab'],
    sourceCodes: ['strn', 'urbn'],
  });
  const successor = context({
    panel_id: 'wa-2026-primary-default-sources-v5',
    sources: personalization().sources.filter((item) => item.code !== 'urbn'),
  });
  const decoded = decodeLensFragment(fragment, successor);

  assert.equal(decoded.status, 'stale_version', 'a retired code must not look like garbage');
  assert.equal(decoded.binding.panelId, 'wa-2026-primary-default-sources-v4');
  assert.deepEqual(decoded.state.categoryCodes, ['Glab']);
  assert.deepEqual(decoded.state.sourceCodes, ['strn', 'urbn'], 'original intent survives for #78');
});

test('a cross-version link stays stale when a code became nonselectable', () => {
  const fragment = encoded({ mode: 's', sourceCodes: ['strn', 'urbn'] });
  const successor = context({
    panel_id: 'wa-2026-primary-default-sources-v5',
    sources: personalization().sources.map((item) =>
      item.code === 'urbn' ? { ...item, selectable: false } : item,
    ),
  });
  const decoded = decodeLensFragment(fragment, successor);

  assert.equal(decoded.status, 'stale_version');
  assert.deepEqual(decoded.state.sourceCodes, ['strn', 'urbn']);
});

test('a cross-version link keeps structural validation', () => {
  const successor = context({ panel_id: 'wa-2026-primary-default-sources-v5' });
  const decoded = decodeLensFragment(
    'lens=2&mode=s&panel=wa-2026-primary-default-sources-v4&ph=6cd4acaa0c5e' +
      '&data=d119ee3107bb&scoring=wa-2026-primary-equal-weight&sel=strnurb',
    successor,
  );

  assert.equal(decoded.status, 'malformed', 'a ragged selection is malformed at any version');
  assert.equal(decoded.reason, 'ragged_selection');
});

test('a link written against other published data or scoring decodes as stale', () => {
  const fragment = encoded({ mode: 'a' });

  assert.equal(
    decodeLensFragment(fragment, lensContext(personalization(), 'aaaaaaaaaaaa')).status,
    'stale_version',
  );
  assert.equal(
    decodeLensFragment(
      fragment,
      context({ scoring: { configuration_id: 'wa-2026-primary-equal-weight-v2' } }),
    ).status,
    'stale_version',
  );
  assert.equal(
    decodeLensFragment(fragment, context({ panel_hash: `f${PANEL_HASH.slice(1)}` })).status,
    'stale_version',
  );
});

test('an existing race permalink is recognized as a legacy fragment', () => {
  for (const fragment of ['#race-us-house-7', 'race-seattle-city-council-5']) {
    const decoded = decodeLensFragment(fragment, context());

    assert.equal(decoded.status, 'legacy');
    assert.equal(decoded.raceTarget, fragment.replace(/^#/, ''));
  }
});

test('an absent fragment is neither legacy nor malformed', () => {
  for (const fragment of ['', '#', null, undefined]) {
    assert.equal(decodeLensFragment(fragment, context()).status, 'absent');
  }
});

test('a lens link may carry a race target alongside a selection', () => {
  const decoded = decodeLensFragment(
    encoded({ mode: 's', sourceCodes: ['strn'], raceTarget: 'race-us-house-7' }),
    context(),
  );

  assert.equal(decoded.status, 'valid');
  assert.equal(decoded.raceTarget, undefined);
  assert.equal(decoded.state.raceTarget, 'race-us-house-7');
});

test('the codec stays pure', () => {
  assertModuleGuard('lens-url.mjs');
});

test('the committed panel snapshot round-trips through the codec', () => {
  const catalog = JSON.parse(
    readFileSync(
      fileURLToPath(
        new URL('../../data/releases/wa-2026-primary/panel-snapshots.json', import.meta.url),
      ),
      'utf8',
    ),
  );
  const snapshot = catalog.snapshots.at(-1);
  const ctx = lensContext(
    {
      panel_id: snapshot.panel_id,
      panel_hash: snapshot.panel_hash,
      scoring: { configuration_id: 'wa-2026-primary-equal-weight' },
      policy: { maximum_url_characters: 4096 },
      categories: snapshot.categories,
      sources: snapshot.sources,
    },
    'd119ee3107bb',
  );

  // A comparison identity is selectable in the payload but inert in the
  // codec (issue 124), so the round-trip is over the tallying panel.
  const selectableCategories = snapshot.categories.filter(
    (item) => item.selectable && item.panel_role !== 'comparison',
  );
  const selectableSources = snapshot.sources.filter(
    (item) => item.selectable && item.panel_role !== 'comparison',
  );
  assert.ok(selectableCategories.length > 0 && selectableSources.length > 0);

  const state = {
    mode: 's',
    categoryCodes: selectableCategories.map((item) => item.code),
    sourceCodes: selectableSources.map((item) => item.code),
  };
  const result = encodeLensFragment(state, ctx);
  assert.equal(result.status, 'ok', 'the whole selectable panel must fit the sharing target');

  const decoded = decodeLensFragment(result.fragment, ctx);
  assert.equal(decoded.status, 'valid');
  assert.deepEqual(decoded.state.categoryCodes, [...state.categoryCodes].sort());
  assert.deepEqual(decoded.state.sourceCodes, [...state.sourceCodes].sort());

  for (const source of snapshot.sources.filter((item) => !item.selectable)) {
    assert.equal(
      encodeLensFragment({ mode: 's', sourceCodes: [source.code] }, ctx).status,
      'rejected',
      `${source.id} is not selectable and must be refused`,
    );
  }
});
