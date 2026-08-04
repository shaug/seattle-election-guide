// lens-selection.mjs is the selection logic every lens-aware page shares — the
// guide, a race page, and the standalone sources editor. Before issue #239 each
// page carried its own copy inside its own `<script>` block, kept in step by
// hand; this is the one place the behavior is now specified.

import assert from 'node:assert/strict';
import test from 'node:test';
import {
  isDefaultSelection,
  MIGRATED_LINK_NOTICE,
  raceTargetFrom,
  resolveLensLink,
  resolveSelectedCodes,
  SELECTION_LINK_FAILURE_NOTICE,
  selectionFragment,
  tallyingSourceCodes,
  UNREADABLE_LINK_NOTICE,
} from '../../src/election_guide/rendering/templates/lens-selection.mjs';
import {
  decodeLensFragment,
  lensContext,
} from '../../src/election_guide/rendering/templates/lens-url.mjs';
import { assertModuleGuard } from './support/module-guards.mjs';

const PANEL_HASH = '6cd4acaa0c5e4ed0b5ddd0134d7de2af5a54c2085e7ad463f9b575b8e6dcb43f';

/** @param {Record<string, unknown>} [overrides] */
function bindings(overrides = {}) {
  return {
    panel_id: 'wa-2026-primary-default-sources-v4',
    panel_hash: PANEL_HASH,
    scoring: { configuration_id: 'wa-2026-primary-equal-weight' },
    policy: { maximum_url_characters: 4096 },
    categories: [
      {
        code: 'Glab',
        selectable: true,
        panel_role: 'tallying',
        member_source_codes: ['mlkl', 'urbn'],
      },
    ],
    sources: [
      { code: 'strn', selectable: true, panel_role: 'consensus' },
      { code: 'urbn', selectable: true, panel_role: 'consensus' },
      { code: 'mlkl', selectable: true, panel_role: 'consensus' },
    ],
    ...overrides,
  };
}

const PANEL_CODES = ['strn', 'urbn', 'mlkl'];
const MEMBERS = new Map([['Glab', ['mlkl', 'urbn']]]);

/** @param {Record<string, unknown>} [overrides] */
const context = (overrides) => lensContext(bindings(overrides), 'd119ee3107bb');

/** One lens fragment against the panel above, with `sel` and `data` variable. */
const fragment = ({ sel = '', data = 'd119ee3107bb' } = {}) =>
  `lens=2&mode=s&panel=wa-2026-primary-default-sources-v4&ph=${PANEL_HASH.slice(0, 12)}` +
  `&data=${data}&scoring=wa-2026-primary-equal-weight${sel ? `&sel=${sel}` : ''}`;

/**
 * The published contract `resolveLensLink` migrates a stale link against. It
 * names the same panel the bindings above do, with the internal ids the
 * migration resolver reads.
 */
const personalization = () => ({
  panel_id: 'wa-2026-primary-default-sources-v4',
  panel_hash: PANEL_HASH,
  panel_version: 1,
  retired_codes: [],
  policy: { maximum_url_characters: 4096, enabled: true },
  scoring: { configuration_id: 'wa-2026-primary-equal-weight' },
  categories: [
    {
      id: 'labor',
      code: 'Glab',
      label: 'Labor',
      selectable: true,
      panel_role: 'tallying',
      member_source_codes: ['mlkl', 'urbn'],
    },
  ],
  sources: [
    { id: 'the-stranger', code: 'strn', selectable: true, panel_role: 'consensus' },
    { id: 'the-urbanist', code: 'urbn', selectable: true, panel_role: 'consensus' },
    { id: 'mlk-labor', code: 'mlkl', selectable: true, panel_role: 'consensus' },
  ],
  races: [],
});

test('a category code expands to its current members, unioned with named sources', () => {
  assert.deepEqual(
    resolveSelectedCodes({ categoryCodes: ['Glab'], sourceCodes: [] }, MEMBERS, PANEL_CODES),
    ['urbn', 'mlkl'],
  );
  assert.deepEqual(
    resolveSelectedCodes({ categoryCodes: ['Glab'], sourceCodes: ['strn'] }, MEMBERS, PANEL_CODES),
    ['strn', 'urbn', 'mlkl'],
  );
});

test('the result keeps the panel order, not the link order', () => {
  assert.deepEqual(resolveSelectedCodes({ sourceCodes: ['mlkl', 'strn'] }, MEMBERS, PANEL_CODES), [
    'strn',
    'mlkl',
  ]);
});

test('a code the panel no longer publishes is dropped, not carried', () => {
  assert.deepEqual(resolveSelectedCodes({ sourceCodes: ['strn', 'gone'] }, MEMBERS, PANEL_CODES), [
    'strn',
  ]);
  assert.deepEqual(resolveSelectedCodes({ categoryCodes: ['Gxxx'] }, MEMBERS, PANEL_CODES), []);
});

test('no selection at all selects nothing, and never throws', () => {
  assert.deepEqual(resolveSelectedCodes(null, MEMBERS, PANEL_CODES), []);
  assert.deepEqual(resolveSelectedCodes(undefined, MEMBERS, PANEL_CODES), []);
  assert.deepEqual(resolveSelectedCodes({}, MEMBERS, PANEL_CODES), []);
});

// One definition of the tallying rule: both halves of the guide read it, and a
// disagreement between them would show a banner claiming every source counts
// while the Sources link published a narrowed selection.
test('a source tallies unless its panel role is comparison', () => {
  assert.deepEqual(
    tallyingSourceCodes([
      { code: 'strn', panel_role: 'consensus' },
      { code: 'stim', panel_role: 'comparison' },
      { code: 'urbn', panel_role: 'consensus' },
    ]),
    ['strn', 'urbn'],
  );
});

test('the tallying codes keep the panel’s published order', () => {
  assert.deepEqual(tallyingSourceCodes(bindings().sources), PANEL_CODES);
});

test('a panel of nothing but comparison sources tallies nothing', () => {
  assert.deepEqual(tallyingSourceCodes([{ code: 'stim', panel_role: 'comparison' }]), []);
});

test('the audited default is every tallying source, and encodes to no lens', () => {
  assert.equal(isDefaultSelection(PANEL_CODES, PANEL_CODES), true);
  assert.equal(isDefaultSelection(['strn'], PANEL_CODES), false);

  assert.deepEqual(
    selectionFragment({
      selectedCodes: PANEL_CODES,
      tallyingCodes: PANEL_CODES,
      raceTarget: null,
      context: context(),
    }),
    { status: 'ok', fragment: '' },
  );
});

test('the audited default still carries the race the reader is on', () => {
  assert.deepEqual(
    selectionFragment({
      selectedCodes: PANEL_CODES,
      tallyingCodes: PANEL_CODES,
      raceTarget: 'race-mayor',
      context: context(),
    }),
    { status: 'ok', fragment: '#race-mayor' },
  );
});

test('a narrowed selection encodes to a lens fragment the codec can read back', () => {
  const result = selectionFragment({
    selectedCodes: ['strn', 'mlkl'],
    tallyingCodes: PANEL_CODES,
    raceTarget: 'race-mayor',
    context: context(),
  });
  assert.equal(result.status, 'ok');
  const decoded = decodeLensFragment(result.fragment, context());
  assert.equal(decoded.status, 'valid');
  assert.deepEqual(decoded.state.sourceCodes, ['mlkl', 'strn']);
  assert.equal(decoded.state.raceTarget, 'race-mayor');
});

// The rule this covers: an encode failure is surfaced, never dropped
// (docs/FRONTEND.md § State and URLs). Both pages used to turn this exact
// refusal into an empty string, which is indistinguishable from "the reader
// chose nothing" — so the link silently published the audited guide instead.
test('a selection too large for the published limit is rejected, not silently emptied', () => {
  const result = selectionFragment({
    selectedCodes: ['strn', 'mlkl'],
    tallyingCodes: PANEL_CODES,
    raceTarget: null,
    context: context({ policy: { maximum_url_characters: 10 } }),
  });
  assert.equal(result.status, 'rejected');
  assert.equal(result.reason, 'oversized');
});

test('a selection naming a token the panel forbids is rejected with its reason', () => {
  const result = selectionFragment({
    selectedCodes: ['strn', 'nope'],
    tallyingCodes: PANEL_CODES,
    raceTarget: null,
    context: context(),
  });
  assert.equal(result.status, 'rejected');
  assert.equal(result.reason, 'unknown_token');
});

test('the rejection notice tells the reader what happened to their selection', () => {
  assert.match(SELECTION_LINK_FAILURE_NOTICE, /could not be written into a link/);
  assert.match(SELECTION_LINK_FAILURE_NOTICE, /audited results/);
  // It must also say the page itself is unchanged, or a reader would think
  // their edit had been discarded.
  assert.match(SELECTION_LINK_FAILURE_NOTICE, /unchanged/);
});

test('a legacy permalink is itself the race target', () => {
  const decoded = decodeLensFragment('#race-mayor', context());
  assert.equal(decoded.status, 'legacy');
  assert.equal(raceTargetFrom(decoded, null), 'race-mayor');
});

test('every other shape takes the race from the state the page accepted', () => {
  const decoded = decodeLensFragment('', context());
  assert.equal(decoded.status, 'absent');
  assert.equal(raceTargetFrom(decoded, null), null);
  assert.equal(raceTargetFrom(decoded, { raceTarget: 'race-council' }), 'race-council');
  // A state the page declined to use names no race either, which is what keeps
  // an unmigratable link from carrying its race forward.
  assert.equal(raceTargetFrom(decoded, undefined), null);
});

// docs/FRONTEND.md § State and URLs: a decode failure produces a
// reader-visible notice *and* a cleaned address bar. Both halves, or neither —
// which is the shape three pages now share rather than restate (issue #136).
test('a link this build cannot read is reported and cleaned away', () => {
  const outcome = resolveLensLink(
    decodeLensFragment(`#${fragment({ sel: 'zzzz' })}`, context()),
    personalization(),
  );

  assert.equal(outcome.state, null);
  assert.equal(outcome.notice, UNREADABLE_LINK_NOTICE);
  assert.equal(outcome.cleanAddress, true);
});

test('a same-version link needs neither migration nor an explanation', () => {
  const outcome = resolveLensLink(
    decodeLensFragment(`#${fragment({ sel: 'strn' })}`, context()),
    personalization(),
  );

  assert.equal(outcome.notice, null);
  assert.equal(outcome.cleanAddress, false);
  assert.deepEqual(outcome.state?.sourceCodes, ['strn']);
});

test('a link written against an earlier published version is migrated, and says so', () => {
  const outcome = resolveLensLink(
    decodeLensFragment(`#${fragment({ sel: 'strn', data: 'older-version' })}`, context()),
    personalization(),
  );

  assert.equal(outcome.notice, MIGRATED_LINK_NOTICE);
  assert.equal(outcome.cleanAddress, false);
  assert.deepEqual(outcome.state?.sourceCodes, ['strn']);
});

// An ordinary in-page anchor — the skip link — is not a lens link and must not
// manufacture an explanation for one.
test('an ordinary anchor carries no explanation at all', () => {
  const outcome = resolveLensLink(decodeLensFragment('#guide-races', context()), personalization());

  assert.equal(outcome.state, null);
  assert.equal(outcome.notice, null);
  assert.equal(outcome.cleanAddress, false);
});

// With the lens disabled there is nothing to migrate into and nothing acts on a
// selection, so the decode runs only so that an unreadable fragment is still
// recognized — and reported.
test('an unreadable link is reported even with the lens disabled', () => {
  const outcome = resolveLensLink(
    decodeLensFragment(`#${fragment({ sel: 'zzzz' })}`, context()),
    null,
  );

  assert.equal(outcome.notice, UNREADABLE_LINK_NOTICE);
  assert.equal(outcome.cleanAddress, true);
});

test('the module computes and touches nothing', () => {
  assertModuleGuard('lens-selection.mjs');
});
