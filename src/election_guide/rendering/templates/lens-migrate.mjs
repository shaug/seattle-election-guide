// Deterministic cross-version migration for a shared personalized lens link.
//
// A `stale_version` decode from lens-url.mjs preserves the raw tokens a link
// carried, but nothing has yet checked those tokens against the CURRENT
// panel. This module does exactly that: it resolves each token to a current,
// live, selectable identity, or explains why it cannot, and returns either a
// normalized current-version selection or a reason the whole link must fall
// back to the audited baseline instead of a partial personalized score.
//
// This module presents nothing and calls no other lens module: it is a pure
// function from (stale decode, current payload, optional origin history) to
// one migration result. Wiring it into a page, encoding the result back into
// a shareable link, and scoring it are each owned elsewhere.

const CATEGORY_PREFIX = 'G';

function isCategoryCode(code) {
  return code.startsWith(CATEGORY_PREFIX);
}

function retiredEntry(personalization, kind, code) {
  return personalization.retired_codes.find((item) => item.kind === kind && item.code === code);
}

/**
 * Resolve one category token against the current panel.
 *
 * Any outcome other than a currently selectable category is unresolvable: the
 * category's old meaning cannot be safely re-expressed as "these current
 * members", so the caller must reject the whole migration rather than guess.
 */
function resolveCategoryToken(code, personalization) {
  const current = personalization.categories.find((item) => item.code === code);
  if (current !== undefined && current.selectable) {
    return { code, status: 'current' };
  }
  const retired = retiredEntry(personalization, 'category', code);
  if (retired !== undefined) {
    return { code, status: 'retired', formerId: retired.former_id, reason: retired.reason };
  }
  return { code, status: current === undefined ? 'unknown' : 'unresolved' };
}

/**
 * Resolve one direct source token against the current panel.
 *
 * Unlike a category, a source that no longer resolves only narrows the
 * migrated selection; it never forces a fallback to audited. Source codes
 * are permanent once issued, so a surviving code always names the same
 * source it always did.
 */
function resolveSourceToken(code, personalization, originSnapshot) {
  const current = personalization.sources.find((item) => item.code === code);
  if (current !== undefined && current.selectable) {
    return { code, status: 'current' };
  }
  if (current !== undefined) {
    return { code, status: 'reclassified', currentRole: current.panel_role };
  }
  const retired = retiredEntry(personalization, 'source', code);
  if (retired !== undefined) {
    return { code, status: 'retired', formerId: retired.former_id, reason: retired.reason };
  }
  if (originSnapshot === null) {
    return { code, status: 'unavailable' };
  }
  const origin = originSnapshot.sources.find((item) => item.code === code);
  return { code, status: origin === undefined ? 'unknown' : 'removed' };
}

/**
 * Migrate a `stale_version` decode to the current published version.
 *
 * `originSnapshot`, if supplied, must be the panel snapshot named by the
 * stale link's own binding (mismatched or absent snapshots are treated the
 * same as not having one): it refines the source report by distinguishing a
 * source that existed at the origin panel and was quietly dropped from one
 * that was never real, but nothing in this module requires it to migrate
 * correctly, since the current panel's cumulative retired-code tombstones
 * already resolve every prior retirement on their own.
 */
export function migrateLensState(staleDecode, personalization, originSnapshot = null) {
  const { state, binding } = staleDecode;
  const origin =
    originSnapshot !== null && originSnapshot.panel_id === binding.panelId ? originSnapshot : null;

  const categoryResults = state.categoryCodes.map((code) =>
    resolveCategoryToken(code, personalization),
  );
  const unresolvedCategory = categoryResults.find((result) => result.status !== 'current');
  const sourceResults = state.sourceCodes.map((code) =>
    resolveSourceToken(code, personalization, origin),
  );
  const report = {
    historyAvailable: origin !== null,
    categories: categoryResults,
    sources: sourceResults,
  };

  if (unresolvedCategory !== undefined) {
    return {
      status: 'rejected',
      reason: 'unresolvable_category',
      category: unresolvedCategory.code,
      report,
    };
  }

  return {
    status: 'migrated',
    selection: {
      mode: state.mode,
      categoryCodes: categoryResults.map((result) => result.code).sort(),
      sourceCodes: sourceResults
        .filter((result) => result.status === 'current')
        .map((result) => result.code)
        .sort(),
      showTimes: state.showTimes,
      raceTarget: state.raceTarget,
    },
    report,
  };
}
