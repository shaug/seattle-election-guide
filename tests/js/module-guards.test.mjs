// The guard is only worth having if nothing escapes it. Four modules were
// unguarded before the guard became one mechanism, so this test sweeps every
// module on disk: each has declared a tier, each has a test file, and the
// guard holds for all of them (docs/FRONTEND.md § Testing).

import assert from 'node:assert/strict';
import { existsSync, readdirSync, readFileSync } from 'node:fs';
import { join, relative, sep } from 'node:path';
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
// Nothing can construct that window without importing the package, so reading
// specifiers is the complete question to ask of a file.
//
// Which files get asked is the other half, and it has to match the suite's own
// reach: `make check-js` runs `node --test 'tests/js/**/*.test.mjs'`, a
// recursive glob, so a sweep that listed one directory would run green over a
// test in a subdirectory that Node had just executed. The listing below is
// recursive for that reason.
const DOM_PACKAGE = 'happy-dom';
const DOM_INSTALLER = 'support/dom.mjs';
// Every way an ES module can name another module, because a scan that covers
// some of them is a scan an author evades without meaning to. Enumerated rather
// than approximated: each form below was written into a test file and confirmed
// to fail the sweep.
//
//   FROM_CLAUSE   `import d from 'x'`, `import {a} from 'x'`, `import * as n
//                 from 'x'`, and the `export … from 'x'` re-exports, which name
//                 a module exactly as an import does. `[^;]` rather than
//                 `[^;\n]` because a multi-line `import {\n  Window,\n} from …`
//                 is what a formatter produces the moment the list grows, and a
//                 scan stopping at the newline would stop seeing the imports
//                 most likely to exist. Requiring `from` is what keeps
//                 `export const X = 'not-a-package'` out.
//   BARE_IMPORT   `import 'x'`, which has no `from` at all.
//   DYNAMIC       `import('x')`. This one matters more here than elsewhere:
//                 `await import(...)` is how every test in this directory loads
//                 its module under test after `installDom()`, so it is the form
//                 an author would reach for by habit.
//
// `require` is not covered and does not need to be: these are `.mjs` files,
// where it is not defined.
const FROM_CLAUSE = /(?:^|\n)\s*(?:import|export)\b[^;]*?\bfrom\s*['"]([^'"]+)['"]/.source;
const BARE_IMPORT = /(?:^|\n)\s*import\s*['"]([^'"]+)['"]/.source;
const DYNAMIC_IMPORT = /\bimport\s*\(\s*['"]([^'"]+)['"]/.source;
const IMPORT_SPECIFIER = new RegExp(`${FROM_CLAUSE}|${BARE_IMPORT}|${DYNAMIC_IMPORT}`, 'g');

/**
 * The package a specifier names, ignoring any subpath into it.
 *
 * `happy-dom/lib/index.js` resolves and constructs a working Window — the
 * package publishes no `exports` map to stop it — so comparing whole specifiers
 * would let a deep import install a second DOM while the sweep read the name it
 * was looking for and did not find it. A relative specifier names no package.
 *
 * @param {string} specifier
 */
function packageOf(specifier) {
  if (specifier.startsWith('.') || specifier.startsWith('/')) return null;
  const segments = specifier.split('/');
  return specifier.startsWith('@') ? segments.slice(0, 2).join('/') : segments[0];
}

/** @param {string} source */
function importedPackages(source) {
  // One group per alternative, so whichever form matched is the one to read.
  return [...source.matchAll(IMPORT_SPECIFIER)]
    .map((match) => packageOf(match[1] ?? match[2] ?? match[3]))
    .filter((name) => name !== null);
}

/** Every `.mjs` under tests/js, at any depth, as a path relative to it. */
function sweptFiles() {
  const here = fileURLToPath(new URL('.', import.meta.url));
  return readdirSync(here, { recursive: true, withFileTypes: true })
    .filter((entry) => entry.isFile() && entry.name.endsWith('.mjs'))
    .map((entry) => relative(here, join(entry.parentPath, entry.name)).split(sep).join('/'))
    .filter((name) => name !== DOM_INSTALLER)
    .sort();
}

test('every file that installs a DOM is the one installer', () => {
  const here = fileURLToPath(new URL('.', import.meta.url));
  const offenders = sweptFiles().filter((name) =>
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

test('the DOM sweep reaches as deep as the test runner does', () => {
  // `node --test 'tests/js/**/*.test.mjs'` is recursive, so a sweep that listed
  // one directory would have run green over a file Node had just executed. The
  // listing has to be the same shape as the glob, and this is what says so.
  const swept = sweptFiles();
  assert.ok(swept.includes('support/module-guards.mjs'), 'the sweep did not descend into support/');
  assert.ok(swept.every((name) => name.endsWith('.mjs')));
  assert.ok(!swept.includes(DOM_INSTALLER), 'the one installer must be the one exemption');
  // Every file the suite runs is a file the sweep read.
  for (const name of readdirSync(fileURLToPath(new URL('.', import.meta.url)))) {
    if (name.endsWith('.test.mjs')) assert.ok(swept.includes(name), `${name} was not swept`);
  }
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
  // A subpath into the package is still the package. happy-dom publishes no
  // `exports` map, so `happy-dom/lib/index.js` resolves and constructs a working
  // Window; comparing whole specifiers would have read the name it was looking
  // for, not found it, and passed.
  assert.deepEqual(importedPackages(`import { Window } from '${DOM_PACKAGE}/lib/index.js';\n`), [
    DOM_PACKAGE,
  ]);
  assert.deepEqual(importedPackages(`await import('${DOM_PACKAGE}/lib/window/Window.js');\n`), [
    DOM_PACKAGE,
  ]);
  // The forms with no `from` clause and no default binding. A side-effect
  // import and a re-export both name a module, and a scan built only around
  // `import … from` reads neither.
  assert.deepEqual(importedPackages(`import '${DOM_PACKAGE}';\n`), [DOM_PACKAGE]);
  assert.deepEqual(importedPackages(`import '${DOM_PACKAGE}/lib/index.js';\n`), [DOM_PACKAGE]);
  assert.deepEqual(importedPackages(`export { Window } from '${DOM_PACKAGE}';\n`), [DOM_PACKAGE]);
  assert.deepEqual(importedPackages(`export * from '${DOM_PACKAGE}';\n`), [DOM_PACKAGE]);
  assert.deepEqual(importedPackages(`export * as dom from '${DOM_PACKAGE}';\n`), [DOM_PACKAGE]);
  assert.deepEqual(importedPackages(`import * as dom from '${DOM_PACKAGE}';\n`), [DOM_PACKAGE]);
  assert.deepEqual(importedPackages(`import d, { Window } from '${DOM_PACKAGE}';\n`), [
    DOM_PACKAGE,
  ]);
  // Requiring a `from` is what keeps an ordinary exported string out: this
  // module exports the package name itself.
  assert.deepEqual(importedPackages(`export const NAME = '${DOM_PACKAGE}';\n`), []);
  // A scoped package keeps both of its segments, so the two halves of one name
  // cannot be read as a package and a subpath.
  assert.deepEqual(importedPackages("import x from '@scope/pkg/deep.js';\n"), ['@scope/pkg']);
  assert.ok(!importedPackages("import test from 'node:test';\n").includes(DOM_PACKAGE));
  // A relative specifier names no package, so support/dom.mjs's own callers are
  // not mistaken for one.
  assert.deepEqual(importedPackages("await import('./support/dom.mjs');\n"), []);
  assert.deepEqual(importedPackages("import { x } from '../../src/thing.mjs';\n"), []);
  // A mention in prose is not an import, which is why the sweep reads
  // specifiers: this very file names the package many times.
  assert.deepEqual(importedPackages(`// we do not import ${DOM_PACKAGE} here\n`), []);
});
