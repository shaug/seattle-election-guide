import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';
import { fileURLToPath } from 'node:url';
import {
  CLIENT_PAYLOAD_SCHEMA_VERSION,
  PAYLOAD_NOTICE_SELECTOR,
  PAYLOAD_SELECTOR,
  parseClientPayload,
} from '../../src/election_guide/rendering/templates/client-payload.mjs';
import { assertModuleGuard, MODULE_DIR } from './support/module-guards.mjs';

const payload = (extra = {}) =>
  JSON.stringify({ schema_version: CLIENT_PAYLOAD_SCHEMA_VERSION, data_version: '7', ...extra });

/** Every template that admits a payload through this module. */
const TEMPLATES = ['guide.html.j2', 'sources.html.j2', 'compare.html.j2'];

const templateSource = (name) => readFileSync(fileURLToPath(new URL(name, MODULE_DIR)), 'utf8');

/** `[data-x]` names the attribute `data-x`; derived, never restated. */
const attributeOf = (selector) => selector.slice(1, -1);

const occurrences = (source, attribute) =>
  source.split(new RegExp(`\\b${attribute}\\b`)).length - 1;

test('a current payload is admitted whole', () => {
  const outcome = parseClientPayload(payload({ panel_id: 'panel-1' }));
  assert.equal(outcome.status, 'ok');
  assert.equal(outcome.payload.panel_id, 'panel-1');
});

test('a payload from a newer build is refused rather than half-read', () => {
  // The rule is not "read what you recognize": a version this build does not
  // understand may have moved or dropped any field below it, so nothing under
  // schema_version is trusted (docs/FRONTEND.md § The data contract).
  const outcome = parseClientPayload(JSON.stringify({ schema_version: '2.0', data_version: '7' }));
  assert.equal(outcome.status, 'unsupported_schema');
  assert.equal(outcome.schemaVersion, '2.0');
});

test('a payload with no version at all is refused too', () => {
  const outcome = parseClientPayload(JSON.stringify({ data_version: '7' }));
  assert.equal(outcome.status, 'unsupported_schema');
  assert.equal(outcome.schemaVersion, undefined);
});

test('unparseable text is malformed, not a crash', () => {
  assert.equal(parseClientPayload('{ not json').status, 'malformed');
});

test('a payload that is not an object is malformed', () => {
  // JSON.parse succeeds on all three; none of them can carry a contract.
  assert.equal(parseClientPayload('null').status, 'malformed');
  assert.equal(parseClientPayload('[]').status, 'malformed');
  assert.equal(parseClientPayload('"1.0"').status, 'malformed');
});

test('a missing or empty element is absent, distinct from malformed', () => {
  // The page shipped without its payload element at all: the same reader
  // outcome, but a different defect, so the statuses stay apart.
  assert.equal(parseClientPayload(null).status, 'absent');
  assert.equal(parseClientPayload(undefined).status, 'absent');
  assert.equal(parseClientPayload('   ').status, 'absent');
});

test('every page renders the element this module reads, exactly once', () => {
  // The selector is a contract between a module and three templates with
  // nothing between them, the same shape guide-entry.mjs's `glue` object has:
  // rename the attribute on one side and the page is inert, with no load error
  // and nothing in `make check` to see it.
  for (const name of TEMPLATES) {
    assert.equal(
      occurrences(templateSource(name), attributeOf(PAYLOAD_SELECTOR)),
      1,
      `${name} must render exactly one ${PAYLOAD_SELECTOR} element`,
    );
  }
});

test('every page renders the notice this module reveals, exactly once', () => {
  // Half of the degradation rule is the reader-visible part: refusing the
  // payload silently is the defect, not the fix (docs/FRONTEND.md § The data
  // contract). Without the element, readClientPayload's reveal is a no-op and
  // every page degrades without saying so.
  for (const name of TEMPLATES) {
    assert.equal(
      occurrences(templateSource(name), attributeOf(PAYLOAD_NOTICE_SELECTOR)),
      1,
      `${name} must render exactly one ${PAYLOAD_NOTICE_SELECTOR} element`,
    );
  }
});

test('the module carries the shared guard', () => {
  assertModuleGuard('client-payload.mjs');
});
