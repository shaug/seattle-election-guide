// compare-client.mjs is the Comparisons page's wiring: attaching the
// interactive table, its pickers, and its filters is DOM work by design, so it
// carries the storage tier of the shared guard rather than the full purity
// tier. It declares its real imports and loads standalone now that
// compare-entry.mjs bundles it, so its behavior coverage is no longer blocked
// on the bundler — it waits on a lightweight DOM (docs/FRONTEND.md § Testing).

import assert from 'node:assert/strict';
import test from 'node:test';
import { wireComparisons } from '../../src/election_guide/rendering/templates/compare-client.mjs';
import { assertModuleGuard } from './support/module-guards.mjs';

test('wiring the page is a call the entry makes, not a module side effect', () => {
  assert.equal(typeof wireComparisons, 'function');
});

test('the module keeps client state out of storage', () => {
  assertModuleGuard('compare-client.mjs');
});
