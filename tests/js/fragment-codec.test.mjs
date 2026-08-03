// The shared codec vocabulary, tested where it lives rather than only through
// the two codecs that speak it.
//
// The page suites (lens-url.test.mjs, compare-url.test.mjs) still own every
// rule about their own fragments and are unchanged by the extraction. What is
// tested here is what neither page suite can state on its own: that a rule has
// exactly one behavior for both callers, and the two places where the shared
// code has to be careful because a page depends on the ordering — the scan's
// leftmost-failure rule, and case-confusable ranking ahead of unknown.

import assert from 'node:assert/strict';
import test from 'node:test';
import {
  classifyCatalogToken,
  codecContext,
  isCategoryToken,
  isCurrentBinding,
  isWellFormedToken,
  missingBindingParameter,
  openFragment,
  orderedUnique,
  readBinding,
  repeatedParameter,
  scanTokens,
  sizedFragment,
  TOKEN_LENGTH,
  writeBinding,
} from '../../src/election_guide/rendering/templates/fragment-codec.mjs';
import { assertModuleGuard } from './support/module-guards.mjs';

const PANEL_HASH = '6cd4acaa0c5e4ed0b5ddd0134d7de2af5a54c2085e7ad463f9b575b8e6dcb43f';

function bindings(overrides = {}) {
  return {
    panel_id: 'wa-2026-primary-default-sources-v4',
    panel_hash: PANEL_HASH,
    scoring: { configuration_id: 'wa-2026-primary-equal-weight' },
    policy: { maximum_url_characters: 4096 },
    categories: [
      { code: 'Glab', selectable: true, panel_role: 'tallying' },
      { code: 'Gxcl', selectable: false, panel_role: 'tallying' },
    ],
    sources: [
      { code: 'strn', selectable: true, panel_role: 'consensus' },
      { code: 'excl', selectable: false, panel_role: 'consensus' },
    ],
    ...overrides,
  };
}

const context = (overrides = {}) => codecContext(bindings(overrides), 'd119ee3107bb');

/** A decode-side failure factory, shaped like the one each codec passes in. */
const malformed = (reason, detail = {}) => ({ status: 'malformed', reason, ...detail });
/** An encode-side one, which is the same shape under the other status. */
const refused = (reason, detail = {}) => ({ status: 'rejected', reason, ...detail });

test('a context carries the published identity, the limit, and both catalogs', () => {
  const codec = context();
  assert.equal(codec.panelId, 'wa-2026-primary-default-sources-v4');
  assert.equal(codec.panelHashPrefix, PANEL_HASH.slice(0, 12));
  assert.equal(codec.panelHashPrefix.length, 12);
  assert.equal(codec.dataVersion, 'd119ee3107bb');
  assert.equal(codec.scoringId, 'wa-2026-primary-equal-weight');
  assert.equal(codec.maximumUrlCharacters, 4096);
  assert.deepEqual([...codec.categories.keys()], ['Glab', 'Gxcl']);
  assert.deepEqual([...codec.sources.keys()], ['strn', 'excl']);
});

test('a token is well formed at exactly the published width and alphabet', () => {
  for (const token of ['strn', 'Glab', 'gall', '0aZ9']) {
    assert.equal(isWellFormedToken(token), true, token);
    assert.equal(token.length, TOKEN_LENGTH);
  }
  for (const token of ['str', 'strnn', '', 'st!m', 'st m', 'st-m', 'stém']) {
    assert.equal(isWellFormedToken(token), false, JSON.stringify(token));
  }
});

test('the reserved uppercase prefix is what separates the two catalogs', () => {
  assert.equal(isCategoryToken('Glab'), true);
  assert.equal(isCategoryToken('strn'), false);
  // Case matters: lowercase `g` is Comparisons' own namespace, not a category.
  assert.equal(isCategoryToken('gall'), false);
});

test('classification admits a selectable published token and refuses the rest', () => {
  const codec = context();
  assert.deepEqual(classifyCatalogToken('strn', codec), { ok: true, token: 'strn' });
  assert.deepEqual(classifyCatalogToken('Glab', codec), { ok: true, token: 'Glab' });
  for (const [token, reason] of [
    ['st!m', 'malformed_token'],
    ['zzzz', 'unknown_token'],
    ['excl', 'forbidden_token'],
    ['Gxcl', 'forbidden_token'],
  ]) {
    assert.deepEqual(classifyCatalogToken(token, codec), { ok: false, reason, token }, token);
  }
});

test('a wrong-case near miss is named as confusable rather than unknown', () => {
  const codec = context();
  // Both catalogs, and both directions of the fold, so the rule is not one
  // catalog's or one casing's.
  for (const token of ['STRN', 'Strn', 'sTrN', 'GLAB', 'GLAb']) {
    assert.equal(classifyCatalogToken(token, codec).reason, 'case_confusable_token', token);
  }
  // A near miss is only a near miss when something folds onto it.
  assert.equal(classifyCatalogToken('ZZZZ', codec).reason, 'unknown_token');
});

test('a token is ranked for confusion only inside the catalog its prefix names', () => {
  // `glab` folds onto the category `Glab`, but its own prefix says source, so
  // it is looked up among sources and is simply unknown there. Ranking it
  // across both catalogs would call it a near miss for a code no source link
  // could ever have named.
  const codec = context({
    categories: [{ code: 'Glab', selectable: true, panel_role: 'tallying' }],
    sources: [{ code: 'zzzz', selectable: true, panel_role: 'consensus' }],
  });
  assert.equal(classifyCatalogToken('glab', codec).reason, 'unknown_token');
  assert.equal(classifyCatalogToken('GLAB', codec).reason, 'case_confusable_token');
});

test('opening a fragment strips the hash, recognizes absence, and applies the limit', () => {
  const codec = context();
  for (const absent of ['', '#', null, undefined]) {
    assert.deepEqual(
      openFragment(absent, codec, malformed).decoded,
      { status: 'absent' },
      JSON.stringify(absent),
    );
  }
  assert.deepEqual(openFragment('#a=b', codec, malformed), { raw: 'a=b' });
  // Only the leading hash goes; nothing else is interpreted or decoded here.
  assert.deepEqual(openFragment('a=b#c', codec, malformed), { raw: 'a=b#c' });

  const tight = context({ policy: { maximum_url_characters: 4 } });
  assert.deepEqual(openFragment('#abcd', tight, malformed), { raw: 'abcd' });
  assert.deepEqual(openFragment('#abcde', tight, malformed).decoded, {
    status: 'malformed',
    reason: 'oversized',
    length: 5,
  });
  // The limit measures the fragment, not the `#` a page put in front of it.
  assert.equal(openFragment('abcde', tight, malformed).decoded.length, 5);
});

test('the caller decides what a failure is called', () => {
  const tight = context({ policy: { maximum_url_characters: 1 } });
  assert.equal(openFragment('#ab', tight, malformed).decoded.status, 'malformed');
  assert.equal(openFragment('#ab', tight, refused).decoded.status, 'rejected');
});

test('a repeated parameter is reported by name, and a distinct one is not', () => {
  assert.equal(repeatedParameter(new URLSearchParams('a=1&b=2')), null);
  assert.equal(repeatedParameter(new URLSearchParams('a=1&b=2&a=3')), 'a');
  // Repetition, not equality: two spellings of the same value still repeat.
  assert.equal(repeatedParameter(new URLSearchParams('a=1&a=1')), 'a');
  assert.equal(repeatedParameter(new URLSearchParams('')), null);
});

test('the four version identifiers round-trip through a fragment', () => {
  const codec = context();
  const parameters = new URLSearchParams();
  writeBinding(parameters, codec);
  assert.deepEqual([...parameters.keys()], ['panel', 'ph', 'data', 'scoring']);

  const binding = readBinding(parameters);
  assert.deepEqual(binding, {
    panelId: codec.panelId,
    panelHashPrefix: codec.panelHashPrefix,
    dataVersion: codec.dataVersion,
    scoringId: codec.scoringId,
  });
  assert.equal(missingBindingParameter(binding), null);
  assert.equal(isCurrentBinding(binding, codec), true);
});

test('every one of the four identifiers is required, and each pins the version', () => {
  const codec = context();
  const written = new URLSearchParams();
  writeBinding(written, codec);

  for (const [parameter, field] of [
    ['panel', 'panelId'],
    ['ph', 'panelHashPrefix'],
    ['data', 'dataVersion'],
    ['scoring', 'scoringId'],
  ]) {
    const absent = new URLSearchParams(written);
    absent.delete(parameter);
    assert.equal(missingBindingParameter(readBinding(absent)), field, parameter);

    const empty = new URLSearchParams(written);
    empty.set(parameter, '');
    assert.equal(missingBindingParameter(readBinding(empty)), field, `${parameter} empty`);

    const other = new URLSearchParams(written);
    other.set(parameter, 'something-else');
    assert.equal(isCurrentBinding(readBinding(other), codec), false, parameter);
  }
});

test('duplicates collapse to their first appearance, order otherwise untouched', () => {
  assert.deepEqual(orderedUnique(['b', 'a', 'b', 'c', 'a']), ['b', 'a', 'c']);
  assert.deepEqual(orderedUnique([]), []);
  assert.deepEqual(orderedUnique(['a']), ['a']);
});

test('a selection is scanned in fixed-width tokens and deduplicated in place', () => {
  assert.deepEqual(scanTokens('', malformed), { tokens: [] });
  assert.deepEqual(scanTokens('strnGlab', malformed), { tokens: ['strn', 'Glab'] });
  assert.deepEqual(scanTokens('strnGlabstrn', malformed), { tokens: ['strn', 'Glab'] });
});

test('a selection that is not a whole number of tokens is ragged, not truncated', () => {
  for (const [selection, length] of [
    ['str', 3],
    ['strnG', 5],
    ['strnGlabs', 9],
  ]) {
    assert.deepEqual(scanTokens(selection, malformed).error, {
      status: 'malformed',
      reason: 'ragged_selection',
      length,
    });
  }
});

test('the scan reports the leftmost token that breaks any rule', () => {
  // A page's own rule runs inside the scan, so a reserved token before a
  // malformed one is the one named -- and after one is not. Applying the two
  // rules in separate passes would get one of these two backwards.
  const reserved = (token) =>
    token.startsWith('g') ? malformed('reserved_token', { token }) : null;

  assert.deepEqual(scanTokens('gminst!m', malformed, reserved).error, {
    status: 'malformed',
    reason: 'reserved_token',
    token: 'gmin',
  });
  assert.deepEqual(scanTokens('st!mgmin', malformed, reserved).error, {
    status: 'malformed',
    reason: 'malformed_token',
    token: 'st!m',
  });
  // Raggedness precedes both: nothing is a token until the width divides.
  assert.equal(scanTokens('gmi', malformed, reserved).error.reason, 'ragged_selection');
  // Without a caller rule, nothing beyond shape is judged here.
  assert.deepEqual(scanTokens('gmin', malformed), { tokens: ['gmin'] });
});

test('a composed fragment is refused when it is too long to share', () => {
  const parameters = new URLSearchParams({ a: '1', b: '2' });
  assert.deepEqual(sizedFragment(parameters, context(), refused), {
    status: 'ok',
    fragment: 'a=1&b=2',
  });
  assert.deepEqual(
    sizedFragment(parameters, context({ policy: { maximum_url_characters: 6 } }), refused),
    {
      status: 'rejected',
      reason: 'oversized',
      length: 7,
      limit: 6,
    },
  );
  // Exactly at the limit still shares.
  assert.equal(
    sizedFragment(parameters, context({ policy: { maximum_url_characters: 7 } }), refused).status,
    'ok',
  );
});

test('the shared core stays pure', () => {
  assertModuleGuard('fragment-codec.mjs');
});
