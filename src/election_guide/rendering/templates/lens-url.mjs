// Canonical fragment codec for the versioned personalized source lens.
//
// State lives in the URL fragment so a shared link never reaches a server in a
// normal request. The codec is pure: it validates and rewrites tokens but never
// scores, never expands a category into its members, and never touches the DOM.
// Category membership is resolved at scoring time so a category link follows
// current membership.
//
// The structural checks this shares with the comparison codec — token
// admission, the four version bindings, the sharing limit — live in
// `fragment-codec.mjs`. What stays here is what makes this fragment the lens's:
// its two modes, its category-before-source ordering, its legacy `#race-…`
// permalinks, and the comparison tokens issue 124 retired.

import {
  classifyCatalogToken,
  codecContext,
  isCategoryToken,
  isCurrentBinding,
  missingBindingParameter,
  openFragment,
  readBinding,
  repeatedParameter,
  scanTokens,
  sizedFragment,
  writeBinding,
} from './fragment-codec.mjs';

export const LENS_SCHEMA_VERSION = '2';
export const LEGACY_RACE_PREFIX = 'race-';

/**
 * The published identity a fragment is read and written against.
 *
 * @typedef {import('./fragment-codec.mjs').CodecBindings} LensBindings
 */

/**
 * @typedef {import('./fragment-codec.mjs').CodecContext} LensContext
 */

/**
 * @typedef {import('./fragment-codec.mjs').CodecBinding} LensBinding
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
 * @typedef {{ status: 'malformed', reason: LensFailureReason, [key: string]: unknown }
 * } LensMalformed
 */

/**
 * @typedef {{ status: 'rejected', reason: LensFailureReason, [key: string]: unknown }
 * } LensRejected
 */

/**
 * Exactly one status per decode.
 *
 * @typedef {{ status: 'absent' }
 *   | { status: 'legacy', raceTarget: string }
 *   | { status: 'valid', state: LensState, binding: LensBinding }
 *   | { status: 'stale_version', state: LensState, binding: LensBinding }
 *   | LensMalformed
 * } LensDecodeResult
 */

/**
 * @typedef {{ status: 'ok', fragment: string } | LensRejected} LensEncodeResult
 */

/**
 * Read the version bindings and limits a fragment is written against.
 *
 * @param {LensBindings} bindings
 * @param {string} dataVersion
 * @returns {LensContext}
 */
export function lensContext(bindings, dataVersion) {
  return codecContext(bindings, dataVersion);
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
 * @returns {LensMalformed}
 */
function invalid(reason, detail) {
  return { status: 'malformed', reason, ...detail };
}

/**
 * @param {LensFailureReason} reason
 * @param {Record<string, unknown>} [detail]
 * @returns {LensRejected}
 */
function rejected(reason, detail) {
  return { status: 'rejected', reason, ...detail };
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
  const opened = openFragment(fragment, context, invalid);
  if (opened.decoded !== undefined) return opened.decoded;
  const raw = opened.raw;
  if (!raw.includes('=')) {
    return raw.startsWith(LEGACY_RACE_PREFIX)
      ? { status: 'legacy', raceTarget: raw }
      : invalid('unrecognized_fragment');
  }

  const parameters = new URLSearchParams(raw);
  const repeated = repeatedParameter(parameters);
  if (repeated !== null) return invalid('repeated_parameter', { parameter: repeated });
  if (parameters.get('lens') !== LENS_SCHEMA_VERSION) {
    return invalid('unsupported_schema', { lens: parameters.get('lens') });
  }

  const mode = parameters.get('mode');
  if (mode !== 'a' && mode !== 's') return invalid('unknown_mode', { mode });

  const scanned = scanTokens(parameters.get('sel') ?? '', invalid);
  if (scanned.error !== undefined) return scanned.error;
  const tokens = withoutComparisonTokens(scanned.tokens, context);

  const binding = readBinding(parameters);
  const missing = missingBindingParameter(binding);
  if (missing !== null) return invalid('missing_binding', { parameter: missing });

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
  if (!isCurrentBinding(binding, context)) {
    return { status: 'stale_version', state: { ...common, ...partitionTokens(tokens) }, binding };
  }

  for (const token of tokens) {
    const classified = classifyCatalogToken(token, context);
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
 * The `race` segment of any fragment, whatever else the fragment carries.
 *
 * The race-detail hash routing (issues 62/73) predates the lens (issue 86) and
 * both live in the same fragment, so the guide needs the race id out of a
 * fragment this codec may otherwise be unable to admit — a mid-migration
 * `stale_version` link, or one that fails classification. That is why this is
 * not `decodeLensFragment(...).state.raceTarget`: it reads the one segment the
 * race routing owns and judges nothing else. Issue #136 made that routing a
 * one-way forward to the race's own page, and this is what tells the guide
 * which page to forward to. It is still the codec's to own, because it is
 * fragment parsing (docs/FRONTEND.md § State and URLs: no second script parses
 * the hash by hand).
 *
 * @param {string|null|undefined} fragment
 * @returns {string} The race target, or `''` when the fragment names none.
 */
export function fragmentRaceTarget(fragment) {
  const raw = decodeFragment(fragment);
  if (raw === '') return '';
  if (!raw.includes('=')) return raw;
  return new URLSearchParams(raw).get('race') ?? '';
}

/**
 * The same fragment with only its `race` segment rewritten.
 *
 * Every other segment — the lens's own selection tokens and version bindings
 * included — is left exactly as found, so opening, closing, or sharing a race
 * never disturbs an active lens (issue 142). A fragment with no `=` (no active
 * lens, an existing `#race-…` permalink, or a plain in-page anchor) reduces to
 * the bare target, matching the pre-lens behavior of those permalinks.
 *
 * @param {string|null|undefined} fragment
 * @param {string|null} target
 * @returns {string} A fragment including its leading `#`, or `''` for none.
 */
export function withRaceTarget(fragment, target) {
  const raw = decodeFragment(fragment);
  if (raw.includes('=')) {
    const parameters = new URLSearchParams(raw);
    if (target) parameters.set('race', target);
    else parameters.delete('race');
    return `#${parameters.toString()}`;
  }
  return target ? `#${target}` : '';
}

/**
 * One fragment, percent-decoded and stripped of its `#`.
 *
 * A fragment that is not valid percent-encoding decodes to nothing rather than
 * throwing: the two readers above both treated a `URIError` as "names no race",
 * and a fragment this malformed carries no segment either of them can honor.
 *
 * @param {string|null|undefined} fragment
 * @returns {string}
 */
function decodeFragment(fragment) {
  try {
    return decodeURIComponent(String(fragment ?? '').replace(/^#/, ''));
  } catch {
    return '';
  }
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
    const classified = classifyCatalogToken(token, context);
    if (!classified.ok) {
      return rejected(classified.reason, { token: classified.token });
    }
    if (mode === 'a') {
      return rejected('audited_mode_carries_selection', { token });
    }
    if (!tokens.includes(token)) tokens.push(token);
  }
  const { categoryCodes, sourceCodes } = partitionTokens(tokens);

  const parameters = new URLSearchParams();
  parameters.set('lens', LENS_SCHEMA_VERSION);
  parameters.set('mode', mode);
  writeBinding(parameters, context);
  const selection = [...categoryCodes, ...sourceCodes].join('');
  if (selection !== '') parameters.set('sel', selection);
  if (state.raceTarget) parameters.set('race', state.raceTarget);

  return sizedFragment(parameters, context, rejected);
}
