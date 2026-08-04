// race-entry.mjs is a race page's client entry (docs/FRONTEND.md § Modules).

import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';
import { fileURLToPath } from 'node:url';
import * as entry from '../../src/election_guide/rendering/templates/race-entry.mjs';
import { assertModuleGuard } from './support/module-guards.mjs';

const TEMPLATE = fileURLToPath(
  new URL('../../src/election_guide/rendering/templates/race.html.j2', import.meta.url),
);

test('the entry offers exactly the one invocation its template makes', () => {
  assert.deepEqual(Object.keys(entry), ['boot']);
  assert.equal(typeof entry.boot, 'function');
});

test('the template reaches the bundle only through that invocation', () => {
  const source = readFileSync(TEMPLATE, 'utf8');
  assert.ok(
    source.includes('RacePage.boot();'),
    'race.html.j2 no longer invokes the entry it inlines',
  );
  assert.ok(
    !source.includes('RacePage.glue'),
    'race.html.j2 destructures the entry. The page has one entry point, and its behavior ' +
      'lives in modules (docs/FRONTEND.md § Modules).',
  );
});

test('the module keeps client state out of storage', () => {
  assertModuleGuard('race-entry.mjs');
});
