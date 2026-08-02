// shell-entry.mjs is the client entry the shell-only documents share — the
// guide archive index and the About page, both still built from Python
// strings in hosting/pages.py (docs/FRONTEND.md § Modules).

import assert from 'node:assert/strict';
import test from 'node:test';

import { assertModuleGuard } from './support/module-guards.mjs';
import { boot } from '../../src/election_guide/rendering/templates/shell-entry.mjs';

test('the entry offers exactly the one invocation its documents make', () => {
  assert.equal(typeof boot, 'function');
});

test('the module keeps client state out of storage', () => {
  assertModuleGuard('shell-entry.mjs');
});
