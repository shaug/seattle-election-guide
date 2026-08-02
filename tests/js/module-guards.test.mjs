// The guard is only worth having if nothing escapes it. Four modules were
// unguarded before the guard became one mechanism, so this test sweeps every
// module on disk: each has declared a tier, each has a test file, and the
// guard holds for all of them (docs/FRONTEND.md § Testing).

import assert from 'node:assert/strict';
import { existsSync } from 'node:fs';
import test from 'node:test';
import { fileURLToPath } from 'node:url';

import { MODULE_KINDS, assertModuleGuard, moduleNames } from './support/module-guards.mjs';

const DOCUMENT = 'docs/FRONTEND.md';

test('every client module declares which guard tier it belongs to', () => {
  assert.deepEqual(
    Object.keys(MODULE_KINDS).sort(),
    moduleNames(),
    `MODULE_KINDS in support/module-guards.mjs does not match the modules on disk. Declare a ` +
      `new module as 'pure' or 'wiring', and drop a deleted one (${DOCUMENT} § Testing).`,
  );
});

// Each module's own test calls `assertModuleGuard` too, so a violation is
// reported where the module is worked on. This sweep runs the guard again
// rather than reading those test files for the call: a text match would pass a
// skipped test and fail an equivalent one, which is no guarantee at all.
test('the guard holds for every client module, and every module is tested', () => {
  for (const name of moduleNames()) {
    const testName = name.replace(/\.mjs$/, '.test.mjs');
    assert.ok(
      existsSync(fileURLToPath(new URL(`./${testName}`, import.meta.url))),
      `${name} has no tests/js/${testName}. Every module is tested in Node, and its test ` +
        `carries the shared guard (${DOCUMENT} § Testing).`,
    );
    assertModuleGuard(name);
  }
});
