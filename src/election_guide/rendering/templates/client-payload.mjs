// The one way a page admits its embedded JSON payload (docs/FRONTEND.md, The
// data contract). Every page publishes exactly one
// `<script type="application/json" data-client-payload>` element, built by
// `rendering/payload.py`; this module parses it, validates the schema version,
// and refuses to hand back anything else.
//
// A payload this build does not understand is not a recoverable condition: the
// server already rendered the complete audited baseline, so the honest outcome
// is to leave that baseline alone and say so. Silence, or a page enhanced with
// half a contract, is the defect the rule names.

/** The payload schema this build understands. Mirrors
 * `CLIENT_PAYLOAD_SCHEMA_VERSION` in `rendering/payload.py`, which is the
 * version every published payload carries. */
export const CLIENT_PAYLOAD_SCHEMA_VERSION = '1.0';

/** What a reader is told when the payload cannot be used. */
export const PAYLOAD_NOTICE =
  'This page could not read its published data, so it shows the audited results only.';

export const PAYLOAD_SELECTOR = '[data-client-payload]';

/** Where each page renders the notice above, hidden until it is needed. */
export const PAYLOAD_NOTICE_SELECTOR = '[data-payload-notice]';

/**
 * Parse one payload element's text.
 *
 * @param {string | null | undefined} text
 * @returns {{ status: 'ok', payload: Record<string, unknown> }
 *   | { status: 'absent' }
 *   | { status: 'malformed' }
 *   | { status: 'unsupported_schema', schemaVersion: unknown }}
 */
export function parseClientPayload(text) {
  if (text === null || text === undefined || text.trim() === '') return { status: 'absent' };
  /** @type {unknown} */
  let parsed;
  try {
    parsed = JSON.parse(text);
  } catch {
    return { status: 'malformed' };
  }
  if (parsed === null || typeof parsed !== 'object' || Array.isArray(parsed)) {
    return { status: 'malformed' };
  }
  const payload = /** @type {Record<string, unknown>} */ (parsed);
  // Validated at parse time, before any caller can act on a field: a payload
  // written by a newer build may have moved or dropped anything below it.
  if (payload.schema_version !== CLIENT_PAYLOAD_SCHEMA_VERSION) {
    return { status: 'unsupported_schema', schemaVersion: payload.schema_version };
  }
  return { status: 'ok', payload };
}

/**
 * Read the page's payload, or reveal its notice and report the failure.
 *
 * Returns `null` rather than throwing so each page can degrade the way its own
 * structure allows; every caller's obligation is the same, to do no DOM work
 * on a `null`.
 *
 * `unknown` rather than a union of the three page payloads: the caller knows
 * which page it is wiring and asserts the generated declaration it expects,
 * exactly as it would after a bare `JSON.parse`.
 *
 * @param {Document} doc
 * @returns {unknown}
 */
export function readClientPayload(doc) {
  const element = doc.querySelector(PAYLOAD_SELECTOR);
  const outcome = parseClientPayload(element?.textContent);
  if (outcome.status === 'ok') return outcome.payload;
  const notice = doc.querySelector(PAYLOAD_NOTICE_SELECTOR);
  if (notice instanceof HTMLElement) {
    notice.hidden = false;
    notice.textContent = PAYLOAD_NOTICE;
  }
  return null;
}

/**
 * The same read, for a caller that cannot decline to continue.
 *
 * A page's bootstrap runs at the top level of a module script, where there is
 * no `return` to take: throwing is what stops evaluation before the first DOM
 * write, so the reader keeps the complete audited page the server sent instead
 * of a page enhanced with half a contract. The notice is already on screen by
 * the time this throws, so the failure is reported to the reader, not only to
 * the console.
 *
 * @param {Document} doc
 * @returns {unknown}
 */
export function requireClientPayload(doc) {
  const payload = readClientPayload(doc);
  if (payload === null) throw new Error('unusable client payload: the page stays audited');
  return payload;
}
