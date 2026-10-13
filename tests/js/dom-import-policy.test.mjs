// Exercise the repository's Biome policy through its CLI, not a second import
// scanner. An absent rule, a widened exemption, or a shallow include must fail.
import assert from 'node:assert/strict';
import { spawnSync } from 'node:child_process';
import { mkdirSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { dirname, join } from 'node:path';
import test, { after } from 'node:test';
import { fileURLToPath } from 'node:url';

const BIOME = fileURLToPath(new URL('../../node_modules/.bin/biome', import.meta.url));
const RULE = 'lint/style/noRestrictedImports';
const ROOT = mkdtempSync(join(tmpdir(), 'dom-import-policy-'));
// A disposable project keeps intentional offenders out of the real test tree.
// It reads the committed policy unchanged except for Git integration: the
// scratch project is not a Git checkout, and its files must not be ignored.
const config = JSON.parse(readFileSync(new URL('../../biome.json', import.meta.url), 'utf8'));
config.vcs.enabled = false;
writeFileSync(join(ROOT, 'biome.json'), JSON.stringify(config));
after(() => rmSync(ROOT, { recursive: true, force: true }));

function lint(source, path = 'tests/js/nested/deeper/offender.test.mjs') {
  const file = join(ROOT, path);
  mkdirSync(dirname(file), { recursive: true });
  writeFileSync(file, `${source}\n`);
  const result = spawnSync(BIOME, ['lint', '--config-path=biome.json', path], {
    cwd: ROOT,
    encoding: 'utf8',
  });
  assert.ifError(result.error);
  return { status: result.status, output: result.stdout + result.stderr };
}

for (const specifier of ['happy-dom', 'happy-dom/lib/index.js']) {
  const forms = [
    `import { Window } from '${specifier}'; export { Window };`,
    `import {\n  Window,\n} from '${specifier}'; export { Window };`,
    `import Dom from '${specifier}'; export { Dom };`,
    `import * as dom from '${specifier}'; export { dom };`,
    `import '${specifier}';`,
    `export { Window } from '${specifier}';`,
    `export * from '${specifier}';`,
    `export * as dom from '${specifier}';`,
    `await import('${specifier}');`,
    `await import(\n  '${specifier}',\n);`,
  ];
  for (const source of forms) {
    test(`the DOM import policy rejects ${source}`, () => {
      const result = lint(source);
      assert.equal(result.status, 1, result.output);
      assert.ok(result.output.includes(RULE), result.output);
      assert.ok(result.output.includes('docs/FRONTEND.md'), result.output);
    });
  }
}

test('only the exact DOM installer is exempt, at any test directory depth', () => {
  const source = "import { Window } from 'happy-dom'; export { Window };";
  assert.equal(lint(source, 'tests/js/support/dom.mjs').status, 0);
  for (const path of ['tests/js/offender.test.mjs', 'tests/js/support/nested/dom.mjs']) {
    const result = lint(source, path);
    assert.equal(result.status, 1, result.output);
    assert.ok(result.output.includes(RULE), result.output);
  }
});

test('calling the installer and mentioning the package in prose remain allowed', () => {
  const result = lint(
    "import { installDom } from './support/dom.mjs'; export { installDom };\n" +
      "// happy-dom is installed by the helper.\nexport const packageName = 'happy-dom';",
  );
  assert.equal(result.status, 0, result.output);
});
