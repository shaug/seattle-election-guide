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
//
// This guard once also scanned each pure module for a sibling's exported name
// used without an import — the enforcement ticket's stand-in for real type
// checking. `tsc --checkJs` now reports any free identifier as TS2304, in
// every module rather than only the pure ones, and without the regex scan's
// false positive on a local name that happens to match a sibling's export. The
// stand-in is deleted rather than kept alongside its replacement.

import assert from 'node:assert/strict';
import { readdirSync, readFileSync } from 'node:fs';
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
  'client-payload.mjs': 'wiring',
  'compare-client.mjs': 'wiring',
  'compare-entry.mjs': 'wiring',
  'compare-migrate.mjs': 'pure',
  'compare-route.mjs': 'wiring',
  'compare-signals.mjs': 'pure',
  'compare-table.mjs': 'pure',
  'compare-url.mjs': 'pure',
  'election-day.mjs': 'wiring',
  'fragment-codec.mjs': 'pure',
  'guide-card.mjs': 'pure',
  'guide-client.mjs': 'wiring',
  'guide-entry.mjs': 'wiring',
  'guide-filters.mjs': 'wiring',
  'guide-format.mjs': 'pure',
  'guide-lens.mjs': 'wiring',
  'lens-divergence.mjs': 'pure',
  'lens-migrate.mjs': 'pure',
  'lens-route.mjs': 'wiring',
  'lens-score.mjs': 'pure',
  'lens-selection.mjs': 'pure',
  'lens-url.mjs': 'pure',
  'meter-context.mjs': 'wiring',
  'meter-layout.mjs': 'pure',
  'meter-tooltip.mjs': 'wiring',
  'race-client.mjs': 'wiring',
  'race-detail.mjs': 'pure',
  'race-entry.mjs': 'wiring',
  'share-link.mjs': 'wiring',
  'shell-entry.mjs': 'wiring',
  'sources-client.mjs': 'wiring',
  'sources-entry.mjs': 'wiring',
  'sources-tree.mjs': 'pure',
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
}
