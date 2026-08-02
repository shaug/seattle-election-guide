// The one guard every client module's test applies (docs/FRONTEND.md).
//
// Before this helper the modules carried seven hand-written and mutually
// divergent identifier lists, four modules carried none, and none of them
// checked `cookie`. The identifier set lives here once so that a rule the
// document states — "No localStorage, no sessionStorage, no cookies" — is
// asserted the same way everywhere, and so that tightening it tightens every
// module at once.
//
// Two tiers, chosen by what a module is for:
//
//   pure    Everything below. A module that computes — a codec, a scoring
//           engine, a migration, a comparison — touches no environment at all
//           (docs/FRONTEND.md § Testing: pure modules get a purity guard).
//   wiring  Storage only. A module whose whole job is attaching behavior to
//           the page necessarily names DOM identifiers; the persistence rule
//           still binds it (docs/FRONTEND.md § State and URLs).

import assert from 'node:assert/strict';
import { readFileSync, readdirSync } from 'node:fs';
import { fileURLToPath } from 'node:url';

const DOCUMENT = 'docs/FRONTEND.md';

export const MODULE_DIR = new URL(
  '../../../src/election_guide/rendering/templates/',
  import.meta.url,
);

/** The URL fragment is the only client persistence (§ State and URLs). */
const STORAGE_IDENTIFIERS = ['localStorage', 'sessionStorage', 'cookie'];

/** Everything a computing module must not reach for (§ Testing). */
const PURITY_IDENTIFIERS = [
  // DOM
  'window',
  'document',
  'location',
  'history',
  'navigator',
  // network
  'fetch',
  'XMLHttpRequest',
  'WebSocket',
  'EventSource',
  // viewport
  'matchMedia',
  'innerWidth',
  'innerHeight',
  'visualViewport',
  // host: these modules ship inlined into a page, where neither exists
  'process',
  'require',
];

/**
 * What each client module is, and therefore which tier guards it. A module
 * absent from this map fails `module-guards.test.mjs`, so a new module makes
 * this choice deliberately rather than arriving unguarded.
 */
export const MODULE_KINDS = {
  'compare-client.mjs': 'wiring',
  'compare-migrate.mjs': 'pure',
  'compare-signals.mjs': 'pure',
  'compare-url.mjs': 'pure',
  'election-day.mjs': 'wiring',
  'lens-divergence.mjs': 'pure',
  'lens-migrate.mjs': 'pure',
  'lens-score.mjs': 'pure',
  'lens-url.mjs': 'pure',
  'share-link.mjs': 'wiring',
};

export function moduleNames() {
  return readdirSync(fileURLToPath(MODULE_DIR))
    .filter((name) => name.endsWith('.mjs'))
    .sort();
}

export function moduleSource(moduleName) {
  return readFileSync(fileURLToPath(new URL(moduleName, MODULE_DIR)), 'utf8');
}

/** Source with comments removed, so a rule named in prose is not a violation. */
function executableSource(moduleName) {
  return moduleSource(moduleName)
    .replace(/\/\*[\s\S]*?\*\//g, '')
    .replace(/(^|\s)\/\/.*$/gm, '');
}

function mentions(code, identifier) {
  return new RegExp(`\\b${identifier}\\b`).test(code);
}

function exportedNames(source) {
  const names = new Set();
  for (const [, name] of source.matchAll(
    /^export\s+(?:async\s+)?(?:function|const|let|var|class)\s+([A-Za-z_$][\w$]*)/gm,
  )) {
    names.add(name);
  }
  for (const [, clause] of source.matchAll(/^export\s*\{([^}]*)\}/gm)) {
    for (const specifier of clause.split(',')) {
      const name = specifier.trim().split(/\s+as\s+/).pop()?.trim();
      if (name) names.add(name);
    }
  }
  return names;
}

function importedNames(source) {
  const names = new Set();
  for (const [, clause] of source.matchAll(/import\s*\{([^}]*)\}\s*from/g)) {
    for (const specifier of clause.split(',')) {
      const name = specifier.trim().split(/\s+as\s+/)[0]?.trim();
      if (name) names.add(name);
    }
  }
  return names;
}

/**
 * Assert one module against its tier.
 *
 * Called from the module's own test so the failure lands where the module is
 * worked on; `module-guards.test.mjs` separately proves every module has such
 * a call, so no module can quietly go unguarded.
 */
export function assertModuleGuard(moduleName) {
  const kind = MODULE_KINDS[moduleName];
  assert.ok(
    kind,
    `${moduleName} has no entry in MODULE_KINDS. Declare whether it is a computing module or ` +
      `page wiring so the right guard applies (${DOCUMENT} § Testing).`,
  );

  const code = executableSource(moduleName);

  for (const identifier of STORAGE_IDENTIFIERS) {
    assert.equal(
      mentions(code, identifier),
      false,
      `${moduleName} references ${identifier}. The URL fragment is the only client ` +
        `persistence (rule: state and URLs, ${DOCUMENT}).`,
    );
  }

  if (kind !== 'pure') return;

  for (const identifier of PURITY_IDENTIFIERS) {
    assert.equal(
      mentions(code, identifier),
      false,
      `${moduleName} references ${identifier}, which makes it environment-dependent. ` +
        `A computing module is testable in plain Node (rule: pure modules get a purity ` +
        `guard, ${DOCUMENT} § Testing).`,
    );
  }

  // A pure module that names a sibling's export without importing it is
  // relying on paste order — the concatenation defect § Modules forbids. This
  // replaces the sibling names the old ad-hoc lists spelled out one at a time.
  const imported = importedNames(moduleSource(moduleName));
  for (const sibling of moduleNames()) {
    if (sibling === moduleName) continue;
    for (const name of exportedNames(moduleSource(sibling))) {
      if (imported.has(name)) continue;
      assert.equal(
        mentions(code, name),
        false,
        `${moduleName} references ${name} from ${sibling} without importing it. A module ` +
          `imports what it references and never relies on another's names being present ` +
          `through concatenation (rule: modules, ${DOCUMENT}).`,
      );
    }
  }
}
