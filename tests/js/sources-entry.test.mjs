// sources-entry.mjs is the standalone sources editor's client entry
// (docs/FRONTEND.md § Modules). Like the guide, its page glue is still inline
// and destructures the entry's `glue` object, so the same contract between
// module and template is checked here until issue #239 removes both sides.

import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';
import { fileURLToPath } from 'node:url';
import { boot, glue } from '../../src/election_guide/rendering/templates/sources-entry.mjs';
import { assertModuleGuard } from './support/module-guards.mjs';

const TEMPLATE = fileURLToPath(
  new URL('../../src/election_guide/rendering/templates/sources.html.j2', import.meta.url),
);

test('the entry offers the one invocation its template makes', () => {
  assert.equal(typeof boot, 'function');
});

test('every name the template destructures is one the entry hands over', () => {
  const source = readFileSync(TEMPLATE, 'utf8');
  const destructuring = source.match(/const \{([^}]*)\} = SourcesPage\.glue;/);
  assert.ok(destructuring, 'sources.html.j2 no longer destructures SourcesPage.glue');
  const wanted = destructuring[1]
    .split(',')
    .map((name) => name.trim())
    .filter(Boolean);
  assert.deepEqual(wanted.slice().sort(), Object.keys(glue).sort());
  for (const name of wanted) assert.equal(typeof glue[name], 'function');
});

test('the module keeps client state out of storage', () => {
  assertModuleGuard('sources-entry.mjs');
});
