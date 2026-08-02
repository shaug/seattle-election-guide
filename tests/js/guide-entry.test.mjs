// guide-entry.mjs is the endorsements guide's client entry
// (docs/FRONTEND.md § Modules).
//
// The guide's page glue is still inline in guide.html.j2 and destructures the
// entry's `glue` object, so that object is a contract between a module and a
// template with nothing between them: a name dropped from one side and not the
// other is `undefined` at the first click, not a load error. The test below is
// what makes it a checked contract until issue #239 removes both sides.

import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';
import { fileURLToPath } from 'node:url';

import { assertModuleGuard } from './support/module-guards.mjs';
import { boot, glue } from '../../src/election_guide/rendering/templates/guide-entry.mjs';

const TEMPLATE = fileURLToPath(
  new URL('../../src/election_guide/rendering/templates/guide.html.j2', import.meta.url),
);

test('the entry offers the one invocation its template makes', () => {
  assert.equal(typeof boot, 'function');
});

test('every name the template destructures is one the entry hands over', () => {
  const source = readFileSync(TEMPLATE, 'utf8');
  const destructuring = source.match(/const \{([^}]*)\} = GuidePage\.glue;/);
  assert.ok(destructuring, 'guide.html.j2 no longer destructures GuidePage.glue');
  const wanted = destructuring[1].split(',').map((name) => name.trim()).filter(Boolean);
  assert.deepEqual(wanted.slice().sort(), Object.keys(glue).sort());
  for (const name of wanted) assert.equal(typeof glue[name], 'function');
});

test('the module keeps client state out of storage', () => {
  assertModuleGuard('guide-entry.mjs');
});
