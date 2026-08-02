// sources-entry.mjs is the standalone sources editor's client entry
// (docs/FRONTEND.md § Modules). Like the guide's, it handed its template a
// `glue` object until issue #239 moved the page's behavior into modules; `boot`
// is now its whole surface.

import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';
import { fileURLToPath } from 'node:url';
import * as entry from '../../src/election_guide/rendering/templates/sources-entry.mjs';
import { assertModuleGuard } from './support/module-guards.mjs';

const TEMPLATE = fileURLToPath(
  new URL('../../src/election_guide/rendering/templates/sources.html.j2', import.meta.url),
);

test('the entry offers exactly the one invocation its template makes', () => {
  assert.deepEqual(Object.keys(entry), ['boot']);
  assert.equal(typeof entry.boot, 'function');
});

test('the template reaches the bundle only through that invocation', () => {
  const source = readFileSync(TEMPLATE, 'utf8');
  assert.ok(
    source.includes('SourcesPage.boot();'),
    'sources.html.j2 no longer invokes the entry it inlines',
  );
  assert.ok(
    !source.includes('SourcesPage.glue'),
    'sources.html.j2 destructures the entry again. The page has one entry point, and its ' +
      'behavior lives in modules (docs/FRONTEND.md § Modules).',
  );
});

test('the module keeps client state out of storage', () => {
  assertModuleGuard('sources-entry.mjs');
});
