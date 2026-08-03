// The vocabulary both page fragment codecs are written in.
//
// `lens-url.mjs` and `compare-url.mjs` carry different state under different
// schemas, but they ask the same structural questions in the same words: what
// a token looks like, whether the current panel still admits one, which four
// published identifiers pin a link to a version, whether a fragment repeats a
// parameter, and how long one may be. Each codec answered them in its own copy
// until now, and the copies had already begun to differ in wording where they
// agreed in behavior — one spells its failure factory with a default the other
// omits; one reads its four binding parameters inline where the other had
// named the same four reads.
//
// What is deliberately *not* here matters as much. There is no page-schema
// object and no generic decode driver. The two pages' real differences — token
// ordering, column bounds, filter parameters, mode handling, the reserved
// lowercase-`g` namespace, cross-page schema rejection — are most of each
// codec, and turning them into data would cost more than the sharing saves
// while moving a page's rules out of the page's own codec. This is a
// vocabulary the codecs are written in, not an engine they are configured on:
// each still reads top to bottom as the fragment grammar it owns
// (docs/FRONTEND.md, State and URLs).
//
// Failure shapes stay with the caller. Both codecs report the same structural
// problems, but decoding produces `malformed` where encoding produces
// `rejected`, and each page names reasons this module has never heard of. So
// every helper here that can fail takes the caller's own failure factory and
// hands back whatever that factory built.
//
// This module is pure, like the two codecs it serves: no DOM, no `location`,
// no storage. The address bar belongs to `lens-route.mjs` and
// `compare-route.mjs`.

export const TOKEN_LENGTH = 4;

// The pattern spells its own length rather than composing one from
// TOKEN_LENGTH: a literal regex is what both codecs carried, and building one
// at runtime would trade a readable constant for a constructed pattern.
const TOKEN_PATTERN = /^[0-9A-Za-z]{4}$/;
const CATEGORY_PREFIX = 'G';
const HASH_PREFIX_LENGTH = 12;

/**
 * What either codec needs to know about one category or source: whether a link
 * may name it, and what role the panel publishes it in.
 *
 * Declared structurally rather than as `PersonalizationCategory` /
 * `PersonalizationSource`, because the guide hands its codec a page payload
 * whose `LensCategory` / `LensSource` carry these two fields under the same
 * names but not the rest of the personalization contract. Neither codec reads
 * the rest, so requiring it would be a type asserting more than the code does.
 *
 * @typedef {object} CodecTokenBinding
 * @property {boolean} selectable
 * @property {string} panel_role
 */

/**
 * The published contract a context is read out of.
 *
 * @typedef {object} CodecBindings
 * @property {string} panel_id
 * @property {string} panel_hash
 * @property {{ configuration_id: string }} scoring
 * @property {{ maximum_url_characters: number }} policy
 * @property {readonly (CodecTokenBinding & { code: string })[]} categories
 * @property {readonly (CodecTokenBinding & { code: string })[]} sources
 */

/**
 * The version bindings, token catalogs, and limits one fragment is read and
 * written against. A page whose fragment carries more than this extends it.
 *
 * @typedef {object} CodecContext
 * @property {string} panelId
 * @property {string} panelHashPrefix
 * @property {string} dataVersion
 * @property {string} scoringId
 * @property {number} maximumUrlCharacters
 * @property {Map<string, CodecTokenBinding>} categories
 * @property {Map<string, CodecTokenBinding>} sources
 */

/**
 * The four published identifiers every fragment carries so that a stale link
 * is recognizable as stale. Read out of a fragment, so every field may be
 * absent.
 *
 * @typedef {object} CodecBinding
 * @property {string|null} panelId
 * @property {string|null} panelHashPrefix
 * @property {string|null} dataVersion
 * @property {string|null} scoringId
 */

/** The failure reasons this module names. Each page's own union is wider. */
/**
 * @typedef {'malformed_token'|'unknown_token'|'case_confusable_token'
 *   |'forbidden_token'|'oversized'|'repeated_parameter'|'missing_binding'
 *   |'ragged_selection'} CodecFailureReason
 */

/**
 * How one codec reports a structural failure: `malformed` when decoding,
 * `rejected` when encoding. A page's own factory accepts a wider reason union
 * than this module ever passes it.
 *
 * @template T
 * @typedef {(reason: CodecFailureReason, detail?: Record<string, unknown>) => T} FailureFactory
 */

/**
 * @typedef {{ ok: true, token: string }
 *   | { ok: false, reason: CodecFailureReason, token: string }
 * } CodecTokenClassification
 */

/**
 * Read the version bindings, token catalogs, and limits a fragment is written
 * against.
 *
 * @param {CodecBindings} bindings
 * @param {string} dataVersion
 * @returns {CodecContext}
 */
export function codecContext(bindings, dataVersion) {
  /** @type {Map<string, CodecTokenBinding>} */
  const categories = new Map();
  /** @type {Map<string, CodecTokenBinding>} */
  const sources = new Map();
  for (const category of bindings.categories) categories.set(category.code, category);
  for (const source of bindings.sources) sources.set(source.code, source);
  return {
    panelId: bindings.panel_id,
    panelHashPrefix: bindings.panel_hash.slice(0, HASH_PREFIX_LENGTH),
    dataVersion,
    scoringId: bindings.scoring.configuration_id,
    maximumUrlCharacters: bindings.policy.maximum_url_characters,
    categories,
    sources,
  };
}

/**
 * Whether a token is spelled the way every published code is spelled.
 *
 * @param {string} token
 * @returns {boolean}
 */
export function isWellFormedToken(token) {
  return TOKEN_PATTERN.test(token);
}

/**
 * Whether a token names a category rather than a source. The two catalogs are
 * disjoint by construction: a category code carries the reserved prefix.
 *
 * @param {string} token
 * @returns {boolean}
 */
export function isCategoryToken(token) {
  return token.startsWith(CATEGORY_PREFIX);
}

/**
 * Admit one token against the current panel: well formed, published here, and
 * still selectable.
 *
 * A page with its own token namespace applies that first and reaches this for
 * everything the catalogs own, so the well-formedness test runs twice on that
 * page. That is the cost of each page keeping its own rejection order, which
 * is reader-visible: the leftmost broken token is the one a notice names.
 *
 * @param {string} token
 * @param {CodecContext} context
 * @returns {CodecTokenClassification}
 */
export function classifyCatalogToken(token, context) {
  if (!isWellFormedToken(token)) {
    return { ok: false, reason: 'malformed_token', token };
  }
  const known = isCategoryToken(token) ? context.categories : context.sources;
  const entry = known.get(token);
  if (entry === undefined) {
    return { ok: false, reason: confusableReason(token, known), token };
  }
  if (!entry.selectable) {
    return { ok: false, reason: 'forbidden_token', token };
  }
  return { ok: true, token };
}

/**
 * Distinguish a wrong-case near miss from a genuinely unknown token.
 *
 * @param {string} token
 * @param {ReadonlyMap<string, unknown>} known
 * @returns {'case_confusable_token'|'unknown_token'}
 */
function confusableReason(token, known) {
  const folded = token.toLowerCase();
  for (const code of known.keys()) {
    if (code.toLowerCase() === folded) return 'case_confusable_token';
  }
  return 'unknown_token';
}

/**
 * Open one location fragment for reading: `#` stripped, an absent fragment
 * recognized, and the published sharing limit applied before anything is
 * parsed.
 *
 * @template T
 * @param {string|null|undefined} fragment
 * @param {CodecContext} context
 * @param {FailureFactory<T>} failure
 * @returns {{ raw: string, decoded?: undefined }
 *   | { raw?: undefined, decoded: { status: 'absent' }|T }}
 */
export function openFragment(fragment, context, failure) {
  const raw = String(fragment ?? '').replace(/^#/, '');
  if (raw === '') return { decoded: { status: 'absent' } };
  if (raw.length > context.maximumUrlCharacters) {
    return { decoded: failure('oversized', { length: raw.length }) };
  }
  return { raw };
}

/**
 * The first parameter a fragment spells more than once, or null.
 *
 * A repeat is refused rather than resolved: reading one of the two would
 * decode a state whose author may have meant the other.
 *
 * @param {URLSearchParams} parameters
 * @returns {string|null}
 */
export function repeatedParameter(parameters) {
  for (const key of parameters.keys()) {
    if (parameters.getAll(key).length > 1) return key;
  }
  return null;
}

/**
 * The version identifiers a fragment carries.
 *
 * @param {URLSearchParams} parameters
 * @returns {CodecBinding}
 */
export function readBinding(parameters) {
  return {
    panelId: parameters.get('panel'),
    panelHashPrefix: parameters.get('ph'),
    dataVersion: parameters.get('data'),
    scoringId: parameters.get('scoring'),
  };
}

/**
 * The name of the first binding field a link left out, or null when all four
 * are there. A fragment missing one cannot be judged current or stale, so it
 * is neither.
 *
 * @param {CodecBinding} binding
 * @returns {string|null}
 */
export function missingBindingParameter(binding) {
  for (const [key, value] of Object.entries(binding)) {
    if (value === null || value === '') return key;
  }
  return null;
}

/**
 * Whether a fragment's binding names the version this context publishes.
 *
 * @param {CodecBinding} binding
 * @param {CodecContext} context
 * @returns {boolean}
 */
export function isCurrentBinding(binding, context) {
  return (
    binding.panelId === context.panelId &&
    binding.panelHashPrefix === context.panelHashPrefix &&
    binding.dataVersion === context.dataVersion &&
    binding.scoringId === context.scoringId
  );
}

/**
 * Write the four published identifiers into a fragment being composed.
 *
 * @param {URLSearchParams} parameters
 * @param {CodecContext} context
 * @returns {void}
 */
export function writeBinding(parameters, context) {
  parameters.set('panel', context.panelId);
  parameters.set('ph', context.panelHashPrefix);
  parameters.set('data', context.dataVersion);
  parameters.set('scoring', context.scoringId);
}

/**
 * The same tokens with later exact duplicates dropped and order preserved.
 *
 * @param {readonly string[]} tokens
 * @returns {string[]}
 */
export function orderedUnique(tokens) {
  /** @type {string[]} */
  const unique = [];
  for (const token of tokens) {
    if (!unique.includes(token)) unique.push(token);
  }
  return unique;
}

/**
 * Split a packed selection into its fixed-width tokens, deduplicated in place.
 *
 * `reject` is the caller's own per-token rule, and it runs inside the scan
 * rather than after it. The page that has one — Comparisons, whose reserved
 * lowercase-`g` namespace is not the catalogs' to judge — reports the leftmost
 * token breaking any rule; running its rule in a second pass would report a
 * later token's problem ahead of an earlier token's.
 *
 * @template T
 * @param {string} selection
 * @param {FailureFactory<T>} failure
 * @param {(token: string) => T|null} [reject]
 * @returns {{ tokens: string[], error?: undefined }
 *   | { tokens?: undefined, error: T }}
 */
export function scanTokens(selection, failure, reject) {
  if (selection.length % TOKEN_LENGTH !== 0) {
    return { error: failure('ragged_selection', { length: selection.length }) };
  }
  /** @type {string[]} */
  const tokens = [];
  for (let index = 0; index < selection.length; index += TOKEN_LENGTH) {
    const token = selection.slice(index, index + TOKEN_LENGTH);
    if (!isWellFormedToken(token)) return { error: failure('malformed_token', { token }) };
    const rejection = reject === undefined ? null : reject(token);
    if (rejection !== null) return { error: rejection };
    tokens.push(token);
  }
  return { tokens: orderedUnique(tokens) };
}

/**
 * Finish one composed fragment, refusing a state too long to share.
 *
 * @template T
 * @param {URLSearchParams} parameters
 * @param {CodecContext} context
 * @param {FailureFactory<T>} failure
 * @returns {{ status: 'ok', fragment: string }|T}
 */
export function sizedFragment(parameters, context, failure) {
  const fragment = parameters.toString();
  if (fragment.length > context.maximumUrlCharacters) {
    return failure('oversized', { length: fragment.length, limit: context.maximumUrlCharacters });
  }
  return { status: 'ok', fragment };
}
