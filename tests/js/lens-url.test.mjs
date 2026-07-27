import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import test from 'node:test';

import {
  LENS_SCHEMA_VERSION,
  decodeLensFragment,
  encodeLensFragment,
  lensContext,
} from '../../src/election_guide/rendering/templates/lens-url.mjs';

const PANEL_HASH = '6cd4acaa0c5e4ed0b5ddd0134d7de2af5a54c2085e7ad463f9b575b8e6dcb43f';

/** A published payload shaped like the committed personalization contract. */
function personalization(overrides = {}) {
  return {
    panel_id: 'wa-2026-primary-default-sources-v3',
    panel_hash: PANEL_HASH,
    scoring: { configuration_id: 'wa-2026-primary-equal-weight' },
    policy: { maximum_url_characters: 4096 },
    categories: [
      { id: 'labor', code: 'Glab', selectable: true },
      { id: 'environmental', code: 'Genv', selectable: true },
      { id: 'comparison', code: 'Gcmp', selectable: false },
    ],
    sources: [
      { id: 'the-stranger', code: 'strn', selectable: true },
      { id: 'the-urbanist', code: 'urbn', selectable: true },
      { id: 'mlk-labor', code: 'mlkl', selectable: true },
      { id: 'seattle-times-editorial-board', code: 'stim', selectable: false },
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

test('an audited state with the Times shown is representable', () => {
  const fragment = encoded({ mode: 'a', showTimes: true });
  const decoded = decodeLensFragment(fragment, context());

  assert.equal(decoded.status, 'valid');
  assert.equal(decoded.state.mode, 'a');
  assert.equal(decoded.state.showTimes, true);
  assert.deepEqual(decoded.state.categoryCodes, []);
  assert.deepEqual(decoded.state.sourceCodes, []);
});

test('a personalized state is representable with and without the Times', () => {
  for (const showTimes of [true, false]) {
    const state = { mode: 's', categoryCodes: ['Glab'], sourceCodes: ['strn'], showTimes };
    const decoded = decodeLensFragment(encoded(state), context());

    assert.equal(decoded.status, 'valid');
    assert.equal(decoded.state.mode, 's');
    assert.equal(decoded.state.showTimes, showTimes);
    assert.deepEqual(decoded.state.categoryCodes, ['Glab']);
    assert.deepEqual(decoded.state.sourceCodes, ['strn']);
  }
});

test('the fragment records the schema, mode, version bindings, and Times flag', () => {
  const fragment = encoded({ mode: 's', sourceCodes: ['strn'], showTimes: false });
  const parameters = new URLSearchParams(fragment);

  assert.equal(parameters.get('lens'), LENS_SCHEMA_VERSION);
  assert.equal(parameters.get('mode'), 's');
  assert.equal(parameters.get('panel'), 'wa-2026-primary-default-sources-v3');
  assert.equal(parameters.get('ph'), PANEL_HASH.slice(0, 12));
  assert.equal(parameters.get('data'), 'd119ee3107bb');
  assert.equal(parameters.get('scoring'), 'wa-2026-primary-equal-weight');
  assert.equal(parameters.get('times'), '0');
  assert.equal(parameters.get('sel'), 'strn');
});

test('same-version encoding is canonical and lossless', () => {
  const state = {
    mode: 's',
    categoryCodes: ['Glab', 'Genv'],
    sourceCodes: ['urbn', 'strn'],
    showTimes: true,
    raceTarget: 'us-house-7',
  };
  const fragment = encoded(state);
  const decoded = decodeLensFragment(fragment, context());

  assert.equal(decoded.status, 'valid');
  assert.deepEqual(decoded.state, {
    mode: 's',
    categoryCodes: ['Genv', 'Glab'],
    sourceCodes: ['strn', 'urbn'],
    showTimes: true,
    raceTarget: 'us-house-7',
  });
  assert.equal(encoded(decoded.state), fragment);
});

test('category tokens are ordered before source tokens regardless of input order', () => {
  const fragment = encoded({
    mode: 's',
    categoryCodes: ['Glab'],
    sourceCodes: ['strn', 'mlkl'],
    showTimes: false,
  });

  assert.equal(new URLSearchParams(fragment).get('sel'), 'Glabmlklstrn');
});

test('exact duplicates are removed while direct and category intent is preserved', () => {
  const decoded = decodeLensFragment(
    encoded({
      mode: 's',
      categoryCodes: ['Glab', 'Glab'],
      sourceCodes: ['mlkl', 'mlkl', 'strn'],
      showTimes: false,
    }),
    context(),
  );

  assert.equal(decoded.status, 'valid');
  assert.deepEqual(decoded.state.categoryCodes, ['Glab']);
  assert.deepEqual(decoded.state.sourceCodes, ['mlkl', 'strn']);
});

test('a category selection is not expanded into its members', () => {
  const decoded = decodeLensFragment(
    encoded({ mode: 's', categoryCodes: ['Glab'], showTimes: false }),
    context(),
  );

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
    const state = { mode: 's', ...selection, showTimes: false };
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
    'lens=1&mode=s&panel=wa-2026-primary-default-sources-v3&ph=6cd4acaa0c5e' +
      '&data=d119ee3107bb&scoring=wa-2026-primary-equal-weight&sel=strnurb&times=0',
    context(),
  );

  assert.equal(decoded.status, 'malformed');
  assert.equal(decoded.reason, 'ragged_selection');
});

test('an unknown token cannot be scored', () => {
  const decoded = decodeLensFragment(encoded({ mode: 's' }).replace('times=0', 'sel=zzzz&times=0'), context());

  assert.equal(decoded.status, 'malformed');
  assert.equal(decoded.reason, 'unknown_token');
  assert.equal(decoded.token, 'zzzz');
});

test('a case-confusable token is rejected rather than silently matched', () => {
  const decoded = decodeLensFragment(
    encoded({ mode: 's' }).replace('times=0', 'sel=STRN&times=0'),
    context(),
  );

  assert.equal(decoded.status, 'malformed');
  assert.equal(decoded.reason, 'case_confusable_token');
  assert.equal(decoded.token, 'STRN');
});

test('the comparison source cannot be selected', () => {
  const decoded = decodeLensFragment(
    encoded({ mode: 's' }).replace('times=0', 'sel=stim&times=0'),
    context(),
  );

  assert.equal(decoded.status, 'malformed');
  assert.equal(decoded.reason, 'forbidden_token');

  const rejected = encodeLensFragment({ mode: 's', sourceCodes: ['stim'] }, context());
  assert.equal(rejected.status, 'rejected');
  assert.equal(rejected.reason, 'forbidden_token');
});

test('a nonselectable category cannot be selected', () => {
  const rejected = encodeLensFragment({ mode: 's', categoryCodes: ['Gcmp'] }, context());

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

test('audited mode may not carry a selection', () => {
  const decoded = decodeLensFragment(
    'lens=1&mode=a&panel=wa-2026-primary-default-sources-v3&ph=6cd4acaa0c5e' +
      '&data=d119ee3107bb&scoring=wa-2026-primary-equal-weight&sel=strn&times=0',
    context(),
  );

  assert.equal(decoded.status, 'malformed');
  assert.equal(decoded.reason, 'audited_mode_carries_selection');
});

test('an unsupported schema version cannot be scored', () => {
  const decoded = decodeLensFragment(encoded({ mode: 'a' }).replace('lens=1', 'lens=2'), context());

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
  const fragment = encoded({ mode: 's', sourceCodes: ['strn'], showTimes: false });
  const successor = context({ panel_id: 'wa-2026-primary-default-sources-v4' });
  const decoded = decodeLensFragment(fragment, successor);

  assert.equal(decoded.status, 'stale_version');
  assert.equal(decoded.binding.panelId, 'wa-2026-primary-default-sources-v3');
  assert.deepEqual(decoded.state.sourceCodes, ['strn'], 'intent is preserved for migration');
});

test('a link written against other published data or scoring decodes as stale', () => {
  const fragment = encoded({ mode: 'a', showTimes: false });

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

test('the codec never reads or writes anything outside the fragment string', () => {
  const source = readFileSync(
    fileURLToPath(new URL('../../src/election_guide/rendering/templates/lens-url.mjs', import.meta.url)),
    'utf8',
  );
  const code = source.replace(/\/\*[\s\S]*?\*\//g, '').replace(/(^|\s)\/\/.*$/gm, '');

  for (const forbidden of [
    'window',
    'document',
    'location',
    'fetch',
    'XMLHttpRequest',
    'localStorage',
    'sessionStorage',
    'navigator',
  ]) {
    assert.equal(
      new RegExp(`\\b${forbidden}\\b`).test(code),
      false,
      `${forbidden} would let fragment state escape the client`,
    );
  }
});

test('the committed panel snapshot round-trips through the codec', () => {
  const catalog = JSON.parse(
    readFileSync(
      fileURLToPath(new URL('../../data/releases/wa-2026-primary/panel-snapshots.json', import.meta.url)),
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

  const selectableCategories = snapshot.categories.filter((item) => item.selectable);
  const selectableSources = snapshot.sources.filter((item) => item.selectable);
  assert.ok(selectableCategories.length > 0 && selectableSources.length > 0);

  const state = {
    mode: 's',
    categoryCodes: selectableCategories.map((item) => item.code),
    sourceCodes: selectableSources.map((item) => item.code),
    showTimes: false,
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
