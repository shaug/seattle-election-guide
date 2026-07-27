// Canonical fragment codec for the versioned personalized source lens.
//
// State lives in the URL fragment so a shared link never reaches a server in a
// normal request. The codec is pure: it validates and rewrites tokens but never
// scores, never expands a category into its members, and never touches the DOM.
// Category membership is resolved at scoring time so a category link follows
// current membership.

export const LENS_SCHEMA_VERSION = '1';
export const TOKEN_LENGTH = 4;
export const LEGACY_RACE_PREFIX = 'race-';

const TOKEN_PATTERN = /^[0-9A-Za-z]{4}$/;
const CATEGORY_PREFIX = 'G';
const HASH_PREFIX_LENGTH = 12;

/** Read the version bindings and limits a fragment is written against. */
export function lensContext(personalization, dataVersion) {
  const categories = new Map();
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

function isCategoryToken(token) {
  return token.startsWith(CATEGORY_PREFIX);
}

/** The one canonical form: split on the reserved prefix, sort within each group. */
function partitionTokens(tokens) {
  return {
    categoryCodes: tokens.filter(isCategoryToken).sort(),
    sourceCodes: tokens.filter((token) => !isCategoryToken(token)).sort(),
  };
}

function classifyToken(token, context) {
  if (!TOKEN_PATTERN.test(token)) {
    return { ok: false, reason: 'malformed_token', token };
  }
  if (isCategoryToken(token)) {
    const category = context.categories.get(token);
    if (category === undefined) {
      return { ok: false, reason: confusableReason(token, context.categories), token };
    }
    if (!category.selectable) {
      return { ok: false, reason: 'forbidden_token', token };
    }
    return { ok: true, token };
  }
  const source = context.sources.get(token);
  if (source === undefined) {
    return { ok: false, reason: confusableReason(token, context.sources), token };
  }
  if (!source.selectable) {
    return { ok: false, reason: 'forbidden_token', token };
  }
  return { ok: true, token };
}

/** Distinguish a wrong-case near miss from a genuinely unknown token. */
function confusableReason(token, known) {
  const folded = token.toLowerCase();
  for (const code of known.keys()) {
    if (code.toLowerCase() === folded) return 'case_confusable_token';
  }
  return 'unknown_token';
}

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

  const times = parameters.get('times');
  if (times !== '0' && times !== '1') return invalid('unknown_times', { times });

  const selection = parameters.get('sel') ?? '';
  if (mode === 'a' && selection !== '') return invalid('audited_mode_carries_selection');
  if (selection.length % TOKEN_LENGTH !== 0) {
    return invalid('ragged_selection', { length: selection.length });
  }

  const tokens = [];
  for (let index = 0; index < selection.length; index += TOKEN_LENGTH) {
    const token = selection.slice(index, index + TOKEN_LENGTH);
    if (!TOKEN_PATTERN.test(token)) return invalid('malformed_token', { token });
    if (!tokens.includes(token)) tokens.push(token);
  }

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
  const common = {
    mode,
    showTimes: times === '1',
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
  return { status: 'valid', state: { ...common, ...partitionTokens(tokens) }, binding };
}

/**
 * Encode lens state into one canonical fragment.
 *
 * Encoding is canonical and lossless for a same-version link: decoding the
 * result reproduces the same state, and re-encoding reproduces the same string.
 */
export function encodeLensFragment(state, context) {
  const mode = state.mode === 's' ? 's' : 'a';
  const tokens = [];
  const requested = mode === 's' ? [...(state.categoryCodes ?? []), ...(state.sourceCodes ?? [])] : [];
  for (const token of requested) {
    const classified = classifyToken(token, context);
    if (!classified.ok) {
      return { status: 'rejected', reason: classified.reason, token: classified.token };
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
  parameters.set('times', state.showTimes ? '1' : '0');
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
