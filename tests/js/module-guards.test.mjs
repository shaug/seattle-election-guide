// The guard is only worth having if nothing escapes it. Four modules were
// unguarded before the guard became one mechanism, so this test sweeps every
// module on disk: each has declared a tier, each has a test file, and the
// guard holds for all of them (docs/FRONTEND.md § Testing).

import assert from 'node:assert/strict';
import { existsSync, readdirSync, readFileSync } from 'node:fs';
import test from 'node:test';
import { fileURLToPath } from 'node:url';

import { assertModuleGuard, MODULE_KINDS, moduleNames } from './support/module-guards.mjs';

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

// "A test that needs a DOM calls `installDom` rather than building its own, so
// there is one answer to what a client module may assume exists" was the half
// of the render-fixture rule with nothing holding it: support/dom.mjs existed
// and every test happened to use it. A second window would have installed a
// different global set silently, and the failure it caused would have surfaced
// as a render bug some frames away rather than as this (#245).
//
// The sweep reads each file's *import specifiers* rather than its text. A
// textual scan for the package name matched this file, because naming the
// package is what a scanner for it has to do — and the fix for that is not an
// exemption for the scanner, which is how a check comes to be blind to itself.
// Nothing can construct that window without importing the package, so the
// structural question is also the complete one.
const DOM_PACKAGE = 'happy-dom';
const DOM_INSTALLER = 'support/dom.mjs';
// Two forms, because this suite writes both. `[^;]` rather than `[^;\n]` in the
// static form: a multi-line `import {\n  Window,\n} from '…'` is what a
// formatter produces the moment the list grows, and a scan stopping at the
// newline would stop seeing exactly the imports most likely to exist. The
// dynamic `import('…')` alternative matters more here than it would elsewhere —
// `await import(...)` is how every test in this directory loads the module under
// test after `installDom()`, so it is the form an author would reach for, not an
// exotic one. No import statement holds a semicolon before its `from`.
const STATIC_IMPORT = /(?:^|\n)\s*import\s[^;]*?from\s*['"]([^'"]+)['"]/.source;
const DYNAMIC_IMPORT = /import\s*\(\s*['"]([^'"]+)['"]/.source;
const IMPORT_SPECIFIER = new RegExp(`${STATIC_IMPORT}|${DYNAMIC_IMPORT}`, 'g');

/** @param {string} source */
function importedPackages(source) {
  // One group per alternative, so whichever form matched is the one to read.
  return [...source.matchAll(IMPORT_SPECIFIER)].map((match) => match[1] ?? match[2]);
}

test('every file that installs a DOM is the one installer', () => {
  const here = fileURLToPath(new URL('.', import.meta.url));
  const files = [
    ...readdirSync(here)
      .filter((name) => name.endsWith('.test.mjs'))
      .map((name) => name),
    ...readdirSync(`${here}support`).map((name) => `support/${name}`),
  ].filter((name) => name !== DOM_INSTALLER);

  const offenders = files.filter((name) =>
    importedPackages(readFileSync(here + name, 'utf8')).includes(DOM_PACKAGE),
  );

  assert.deepEqual(
    offenders,
    [],
    `${offenders.join(', ')} imports ${DOM_PACKAGE} directly and so builds its own DOM. A test ` +
      `that needs one calls installDom() from ${DOM_INSTALLER}, so there is one answer to what ` +
      `a client module may assume exists — and so lit-html is imported after a document exists, ` +
      `which is the ordering that helper is for (rule: render functions get Node tests against ` +
      `view-model fixtures, ${DOCUMENT} § Testing).`,
  );
});

test('the DOM sweep can actually see an import of the package', () => {
  // The sweep is only worth having if it observes the thing it forbids. This
  // is the mutation the real check cannot perform on itself.
  assert.deepEqual(importedPackages(`import { Window } from '${DOM_PACKAGE}';\n`), [DOM_PACKAGE]);
  assert.deepEqual(importedPackages(`import {\n  Window,\n} from '${DOM_PACKAGE}';\n`), [
    DOM_PACKAGE,
  ]);
  assert.deepEqual(importedPackages(`import Dom from "${DOM_PACKAGE}";\n`), [DOM_PACKAGE]);
  // The dynamic form, which is how every test here loads its module under test
  // and so the one an author evading this would reach for without meaning to.
  assert.deepEqual(importedPackages(`const { Window } = await import('${DOM_PACKAGE}');\n`), [
    DOM_PACKAGE,
  ]);
  assert.deepEqual(importedPackages(`await import(\n  "${DOM_PACKAGE}",\n);\n`), [DOM_PACKAGE]);
  assert.ok(!importedPackages("import test from 'node:test';\n").includes(DOM_PACKAGE));
  assert.ok(!importedPackages("await import('./support/dom.mjs');\n").includes(DOM_PACKAGE));
  // A mention in prose is not an import, which is why the sweep reads
  // specifiers: this very file names the package three times.
  assert.deepEqual(importedPackages(`// we do not import ${DOM_PACKAGE} here\n`), []);
});
