// Canonical fragment codec for the versioned personalized source lens.
//
// State lives in the URL fragment so a shared link never reaches a server in a
// normal request. The codec is pure: it validates and rewrites tokens but never
// scores, never expands a category into its members, and never touches the DOM.
// Category membership is resolved at scoring time so a category link follows
// current membership.

export const LENS_SCHEMA_VERSION = '2';
export const TOKEN_LENGTH = 4;
export const LEGACY_RACE_PREFIX = 'race-';

const TOKEN_PATTERN = /^[0-9A-Za-z]{4}$/;
const CATEGORY_PREFIX = 'G';
const HASH_PREFIX_LENGTH = 12;

/**
 * The version bindings, token catalogs, and limits one fragment is read and
 * written against.
 *
 * @typedef {object} LensContext
 * @property {string} panelId
 * @property {string} panelHashPrefix
 * @property {string} dataVersion
 * @property {string} scoringId
 * @property {number} maximumUrlCharacters
 * @property {Map<string, PersonalizationCategory>} categories
 * @property {Map<string, PersonalizationSource>} sources
 */

/**
 * The four published identifiers a fragment carries so a stale link is
 * recognizable as stale. Read from the fragment, so every field may be absent.
 *
 * @typedef {object} LensBinding
 * @property {string|null} panelId
 * @property {string|null} panelHashPrefix
 * @property {string|null} dataVersion
 * @property {string|null} scoringId
 */

/**
 * Lens state in its decoded, canonical form.
 *
 * @typedef {object} LensState
 * @property {'a'|'s'} mode
 * @property {string|null} raceTarget
 * @property {string[]} categoryCodes
 * @property {string[]} sourceCodes
 */

/** Why a token or fragment could not be admitted. */
/**
 * @typedef {'malformed_token'|'unknown_token'|'case_confusable_token'
 *   |'forbidden_token'|'oversized'|'unrecognized_fragment'|'repeated_parameter'
 *   |'unsupported_schema'|'unknown_mode'|'ragged_selection'|'missing_binding'
 *   |'audited_mode_carries_selection'} LensFailureReason
 */

/**
 * Exactly one status per decode.
 *
 * @typedef {{ status: 'absent' }
 *   | { status: 'legacy', raceTarget: string }
 *   | { status: 'valid', state: LensState, binding: LensBinding }
 *   | { status: 'stale_version', state: LensState, binding: LensBinding }
 *   | { status: 'malformed', reason: LensFailureReason, [key: string]: unknown }
 * } LensDecodeResult
 */

/**
 * @typedef {{ status: 'ok', fragment: string }
 *   | { status: 'rejected', reason: LensFailureReason, [key: string]: unknown }
 * } LensEncodeResult
 */

/**
 * Read the version bindings and limits a fragment is written against.
 *
 * @param {Personalization} personalization
 * @param {string} dataVersion
 * @returns {LensContext}
 */
export function lensContext(personalization, dataVersion) {
  /** @type {Map<string, PersonalizationCategory>} */
  const categories = new Map();
  /** @type {Map<string, PersonalizationSource>} */
  const sources = new Map();
  for (const category of personalization.categories) {
    categories.set(category.code, category);
  }
  for (const source of personalization.sources) {
    sources.set(source.code, source);
  }
  return {
    panelId: personalization.panel_id,
    panelHashPrefix: personalization.panel_hash.slice(0, HASH_PREFIX_LENGTH),
    dataVersion,
    scoringId: personalization.scoring.configuration_id,
    maximumUrlCharacters: personalization.policy.maximum_url_characters,
    categories,
    sources,
  };
}

/**
 * @param {string} token
 * @returns {boolean}
 */
function isCategoryToken(token) {
  return token.startsWith(CATEGORY_PREFIX);
}

/**
 * The one canonical form: split on the reserved prefix, sort within each group.
 *
 * @param {readonly string[]} tokens
 * @returns {{ categoryCodes: string[], sourceCodes: string[] }}
 */
function partitionTokens(tokens) {
  return {
    categoryCodes: tokens.filter(isCategoryToken).sort(),
    sourceCodes: tokens.filter((token) => !isCategoryToken(token)).sort(),
  };
}

/**
 * @typedef {{ ok: true, token: string }
 *   | { ok: false, reason: LensFailureReason, token: string }
 * } TokenClassification
 */

/**
 * @param {string} token
 * @param {LensContext} context
 * @returns {TokenClassification}
 */
function classifyToken(token, context) {
  if (!TOKEN_PATTERN.test(token)) {
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
 * Whether a known token names a comparison-role category or source.
 *
 * Issue 124 retired the guide's per-race comparison, so such a token now names
 * nothing this codec can express. It is dropped rather than rejected (see
 * `withoutComparisonTokens`), and an unknown token is not one of these — it
 * still fails classification.
 *
 * @param {string} token
 * @param {LensContext} context
 * @returns {boolean}
 */
function isComparisonToken(token, context) {
  const known = isCategoryToken(token) ? context.categories : context.sources;
  return known.get(token)?.panel_role === 'comparison';
}

/**
 * Drop every comparison token, keeping the rest in order.
 *
 * A link shared before issue 124 could carry one (for example `stim`, "also
 * show the Times"). The comparison it asked for no longer exists, but the rest
 * of the link is still a valid selection, so the token is silently ignored and
 * everything else replays exactly. Codes are permanent once issued, so a token
 * naming a comparison source in the current panel named the same source when
 * the link was written — which is why this is safe to apply to a
 * `stale_version` link too, before its tokens are otherwise interpreted.
 *
 * @param {readonly string[]} tokens
 * @param {LensContext} context
 * @returns {string[]}
 */
function withoutComparisonTokens(tokens, context) {
  return tokens.filter((token) => !isComparisonToken(token, context));
}

/**
 * @param {LensFailureReason} reason
 * @param {Record<string, unknown>} [detail]
 * @returns {LensDecodeResult}
 */
function invalid(reason, detail) {
  return { status: 'malformed', reason, ...detail };
}

/**
 * Decode one location fragment.
 *
 * Returns exactly one status: `absent` for no fragment, `legacy` for an
 * existing `#race-…` permalink, `valid` for a same-version lens link,
 * `stale_version` for a lens link written against another published version,
 * or `malformed` for anything that must not be scored.
 *
 * @param {string|null|undefined} fragment
 * @param {LensContext} context
 * @returns {LensDecodeResult}
 */
export function decodeLensFragment(fragment, context) {
  const raw = String(fragment ?? '').replace(/^#/, '');
  if (raw === '') return { status: 'absent' };
  if (raw.length > context.maximumUrlCharacters) {
    return invalid('oversized', { length: raw.length });
  }
  if (!raw.includes('=')) {
    return raw.startsWith(LEGACY_RACE_PREFIX)
      ? { status: 'legacy', raceTarget: raw }
      : invalid('unrecognized_fragment');
  }

  const parameters = new URLSearchParams(raw);
  for (const key of parameters.keys()) {
    if (parameters.getAll(key).length > 1) return invalid('repeated_parameter', { parameter: key });
  }
  if (parameters.get('lens') !== LENS_SCHEMA_VERSION) {
    return invalid('unsupported_schema', { lens: parameters.get('lens') });
  }

  const mode = parameters.get('mode');
  if (mode !== 'a' && mode !== 's') return invalid('unknown_mode', { mode });

  const selection = parameters.get('sel') ?? '';
  if (selection.length % TOKEN_LENGTH !== 0) {
    return invalid('ragged_selection', { length: selection.length });
  }

  /** @type {string[]} */
  const parsed = [];
  for (let index = 0; index < selection.length; index += TOKEN_LENGTH) {
    const token = selection.slice(index, index + TOKEN_LENGTH);
    if (!TOKEN_PATTERN.test(token)) return invalid('malformed_token', { token });
    if (!parsed.includes(token)) parsed.push(token);
  }
  const tokens = withoutComparisonTokens(parsed, context);

  const binding = {
    panelId: parameters.get('panel'),
    panelHashPrefix: parameters.get('ph'),
    dataVersion: parameters.get('data'),
    scoringId: parameters.get('scoring'),
  };
  for (const [key, value] of Object.entries(binding)) {
    if (value === null || value === '') return invalid('missing_binding', { parameter: key });
  }

  const raceTarget = parameters.get('race');
  // Annotated because a narrowed literal widens back to `string` once it is a
  // mutable object property, which would lose the two-mode guarantee above.
  /** @type {Pick<LensState, 'mode'|'raceTarget'>} */
  const common = {
    mode,
    raceTarget: raceTarget === null || raceTarget === '' ? null : raceTarget,
  };

  // Resolve the version before consulting the current panel. A link written
  // against another published version is stale even when its codes no longer
  // exist here, and #78 needs its binding and original tokens to migrate it.
  const currentVersion =
    binding.panelId === context.panelId &&
    binding.panelHashPrefix === context.panelHashPrefix &&
    binding.dataVersion === context.dataVersion &&
    binding.scoringId === context.scoringId;
  if (!currentVersion) {
    return { status: 'stale_version', state: { ...common, ...partitionTokens(tokens) }, binding };
  }

  for (const token of tokens) {
    const classified = classifyToken(token, context);
    if (!classified.ok) return invalid(classified.reason, { token: classified.token });
  }
  // Audited mode restricts nothing (there is nothing to restrict), so any
  // surviving token would imply a restricted audited score, which does not
  // exist. Comparison tokens are already gone by here, so an audited link that
  // carried only those decodes as the plain audited baseline it now means.
  if (mode === 'a' && tokens.length > 0) {
    return invalid('audited_mode_carries_selection', { token: tokens[0] });
  }
  return { status: 'valid', state: { ...common, ...partitionTokens(tokens) }, binding };
}

/**
 * Encode lens state into one canonical fragment.
 *
 * Encoding is canonical and lossless for a same-version link: decoding the
 * result reproduces the same state, and re-encoding reproduces the same string.
 *
 * @param {Partial<LensState>} state
 * @param {LensContext} context
 * @returns {LensEncodeResult}
 */
export function encodeLensFragment(state, context) {
  const mode = state.mode === 's' ? 's' : 'a';
  /** @type {string[]} */
  const tokens = [];
  const requested = withoutComparisonTokens(
    [...(state.categoryCodes ?? []), ...(state.sourceCodes ?? [])],
    context,
  );
  for (const token of requested) {
    const classified = classifyToken(token, context);
    if (!classified.ok) {
      return { status: 'rejected', reason: classified.reason, token: classified.token };
    }
    if (mode === 'a') {
      return { status: 'rejected', reason: 'audited_mode_carries_selection', token };
    }
    if (!tokens.includes(token)) tokens.push(token);
  }
  const { categoryCodes, sourceCodes } = partitionTokens(tokens);

  const parameters = new URLSearchParams();
  parameters.set('lens', LENS_SCHEMA_VERSION);
  parameters.set('mode', mode);
  parameters.set('panel', context.panelId);
  parameters.set('ph', context.panelHashPrefix);
  parameters.set('data', context.dataVersion);
  parameters.set('scoring', context.scoringId);
  const selection = [...categoryCodes, ...sourceCodes].join('');
  if (selection !== '') parameters.set('sel', selection);
  if (state.raceTarget) parameters.set('race', state.raceTarget);

  const fragment = parameters.toString();
  if (fragment.length > context.maximumUrlCharacters) {
    return {
      status: 'rejected',
      reason: 'oversized',
      length: fragment.length,
      limit: context.maximumUrlCharacters,
    };
  }
  return { status: 'ok', fragment };
}
