// compare-entry.mjs is the Comparisons page's client entry: its import graph
// is the whole of that page's client code, and compare.html.j2 does nothing
// but inline the bundle and invoke `boot` (docs/FRONTEND.md § Modules).

import assert from 'node:assert/strict';
import test from 'node:test';

import { assertModuleGuard } from './support/module-guards.mjs';
import { boot } from '../../src/election_guide/rendering/templates/compare-entry.mjs';

test('the entry offers exactly the one invocation its template makes', () => {
  assert.equal(typeof boot, 'function');
});

test('the module keeps client state out of storage', () => {
  assertModuleGuard('compare-entry.mjs');
});
