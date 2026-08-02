// compare-client.mjs is the Comparisons page's entry: it reads the DOM at
// module scope, so it carries the storage tier of the shared guard rather than
// the full purity tier, and it is the one module grandfathered out of
// standalone loading in tests/frontend_ratchets.json. The guard is a source
// scan, so it binds this module even though the module cannot be imported
// here. Behavior coverage follows the bundler, which is what makes this module
// loadable at all (docs/FRONTEND.md § Modules, § Testing).

import test from 'node:test';

import { assertModuleGuard } from './support/module-guards.mjs';

test('the module keeps client state out of storage', () => {
  assertModuleGuard('compare-client.mjs');
});
