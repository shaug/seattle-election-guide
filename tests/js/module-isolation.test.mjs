// docs/FRONTEND.md, Modules: every `.mjs` file is a real ES module that loads
// standalone in Node, relying on no other module's names being present through
// script concatenation or paste order.
//
// The list of modules that could not yet load alone was grandfathered in
// tests/frontend_ratchets.json with the exact failure each produced. The
// bundler ticket (#234) emptied it and the epic's closeout (#245) deleted it:
// an empty allowlist is still a place to add one, so this check now reads no
// baseline and every module must load, full stop.
//
// This check cannot see the document's "imports what it references" clause — a
// free identifier is a runtime ReferenceError, never a load failure. That
// clause is now `tsc --checkJs`'s: it reports any free identifier as TS2304
// before this test ever runs.

import assert from 'node:assert/strict';
import test from 'node:test';

import { MODULE_DIR, moduleNames } from './support/module-guards.mjs';

const DOCUMENT = 'docs/FRONTEND.md';

async function loadFailure(moduleName) {
  try {
    await import(new URL(moduleName, MODULE_DIR));
    return null;
  } catch (error) {
    return error;
  }
}

test('every client module loads standalone in Node', async () => {
  for (const name of moduleNames()) {
    const failure = await loadFailure(name);
    assert.equal(
      failure,
      null,
      `${name} does not load on its own: ${failure?.message}. A module declares its imports ` +
        `and stands alone; it may not depend on paste order (rule: modules, ${DOCUMENT}). ` +
        `Nothing is exempt from this any more.`,
    );
  }
});
