// share-link.mjs is page wiring: attaching the masthead's Share action and
// falling back from the native share sheet to the clipboard is DOM work by
// design, so it carries the storage tier of the shared guard rather than the
// full purity tier. Its behavior belongs in a lightweight DOM
// (docs/FRONTEND.md § Testing) and gains coverage when the front-end
// architecture epic puts one in place; the guard binds it today.

import test from 'node:test';

import { assertModuleGuard } from './support/module-guards.mjs';

test('the module keeps client state out of storage', () => {
  assertModuleGuard('share-link.mjs');
});
