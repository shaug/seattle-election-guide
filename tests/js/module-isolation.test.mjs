// docs/FRONTEND.md, Modules: every `.mjs` file is a real ES module that loads
// standalone in Node, relying on no other module's names being present through
// script concatenation or paste order.
//
// Today's pages are still assembled by concatenation, so the modules that
// cannot yet load alone are grandfathered in tests/frontend_ratchets.json with
// the exact failure they produce. That list only shrinks: a module that starts
// loading fails this test until its entry is deleted.
//
// This check cannot see the document's "imports what it references" clause — a
// free identifier is a runtime ReferenceError, never a load failure. The pure
// modules' half of that clause is guarded in support/module-guards.mjs; the
// rest arrives with `tsc --checkJs`.

import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';
import { fileURLToPath } from 'node:url';

import { MODULE_DIR, moduleNames } from './support/module-guards.mjs';

const DOCUMENT = 'docs/FRONTEND.md';

const ratchets = JSON.parse(
  readFileSync(fileURLToPath(new URL('../frontend_ratchets.json', import.meta.url)), 'utf8'),
);
const exemptions = new Map(
  ratchets.module_isolation_exemptions.map((entry) => [entry.module, entry]),
);

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
    const exemption = exemptions.get(name);

    if (!exemption) {
      assert.equal(
        failure,
        null,
        `${name} does not load on its own: ${failure?.message}. A module declares its imports ` +
          `and stands alone; it may not depend on paste order (rule: modules, ${DOCUMENT}).`,
      );
      continue;
    }

    assert.notEqual(
      failure,
      null,
      `${name} now loads standalone but is still listed in ` +
        `tests/frontend_ratchets.json. Delete its exemption in this pull request ` +
        `(rule: the allowlist only shrinks, ${DOCUMENT} § Adoption).`,
    );
    assert.ok(
      String(failure.message).includes(exemption.error),
      `${name} fails to load with "${failure.message}", not the recorded ` +
        `"${exemption.error}". An exemption covers one known defect; a different failure is a ` +
        `new violation (rule: modules, ${DOCUMENT}).`,
    );
  }
});

test('every isolation exemption names a module that exists', () => {
  const present = new Set(moduleNames());
  const stale = [...exemptions.keys()].filter((name) => !present.has(name));
  assert.deepEqual(
    stale,
    [],
    `tests/frontend_ratchets.json exempts ${stale} from standalone loading, but no such ` +
      `module exists. Delete the entry (${DOCUMENT} § Adoption).`,
  );
});
