// guide-entry.mjs is the endorsements guide's client entry
// (docs/FRONTEND.md § Modules).
//
// Until issue #239 the entry also handed the template a `glue` object, because
// several hundred lines of the guide's behavior lived in guide.html.j2's own
// `<script>` blocks and called those names directly. That glue is modules now,
// so `boot` is the entry's whole surface and the template's whole content is
// one invocation of it — which is what the tests below hold it to.

import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';
import { fileURLToPath } from 'node:url';
import * as entry from '../../src/election_guide/rendering/templates/guide-entry.mjs';
import { assertModuleGuard } from './support/module-guards.mjs';

const TEMPLATE = fileURLToPath(
  new URL('../../src/election_guide/rendering/templates/guide.html.j2', import.meta.url),
);

test('the entry offers exactly the one invocation its template makes', () => {
  assert.deepEqual(Object.keys(entry), ['boot']);
  assert.equal(typeof entry.boot, 'function');
});

test('the template reaches the bundle only through that invocation', () => {
  const source = readFileSync(TEMPLATE, 'utf8');
  assert.ok(
    source.includes('GuidePage.boot();'),
    'guide.html.j2 no longer invokes the entry it inlines',
  );
  assert.ok(
    !source.includes('GuidePage.glue'),
    'guide.html.j2 destructures the entry again. The page has one entry point, and its ' +
      'behavior lives in modules (docs/FRONTEND.md § Modules).',
  );
});

test('the module keeps client state out of storage', () => {
  assertModuleGuard('guide-entry.mjs');
});
