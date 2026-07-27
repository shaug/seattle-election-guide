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

function retiredEntry(personalization, kind, code) {
  return personalization.retired_codes.find((item) => item.kind === kind && item.code === code);
}

/**
 * Resolve one category token against the current panel.
 *
 * Any outcome other than a currently selectable category with at least one
 * current member is unresolvable: the category's old meaning cannot be
 * safely re-expressed as "these current members" when there are none, or
 * when we cannot identify it at all, so the caller must reject the whole
 * migration rather than guess. When origin history is available the
 * resolved entry also reports which current members are new and which
 * origin members are gone, so a caller can disclose the change rather than
 * silently broadening or narrowing what an equal-weighted selection meant.
 */
function resolveCategoryToken(code, personalization, originSnapshot) {
  const current = personalization.categories.find((item) => item.code === code);
  if (current !== undefined && current.selectable && current.member_source_codes.length > 0) {
    const result = { code, status: 'current' };
    const origin = originSnapshot?.categories.find((item) => item.code === code);
    if (origin !== undefined) {
      const originMembers = new Set(origin.member_source_codes);
      const currentMembers = new Set(current.member_source_codes);
      result.addedMemberCodes = current.member_source_codes
        .filter((member) => !originMembers.has(member))
        .sort();
      result.removedMemberCodes = origin.member_source_codes
        .filter((member) => !currentMembers.has(member))
        .sort();
    }
    return result;
  }
  const retired = retiredEntry(personalization, 'category', code);
  if (retired !== undefined) {
    return { code, status: 'retired', formerId: retired.former_id, reason: retired.reason };
  }
  if (current !== undefined) {
    // Selectable but empty, or found and not selectable: identified, but it
    // can no longer stand for the selection it once represented.
    return { code, status: 'unresolved' };
  }
  return { code, status: 'unknown' };
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
 * same as not having one): it refines the report by distinguishing a source
 * that existed at the origin panel and was quietly dropped from one that was
 * never real, and by naming which current category members are new and
 * which origin members are gone. Nothing in this module requires it to
 * migrate correctly, since the current panel's cumulative retired-code
 * tombstones already resolve every prior retirement on their own.
 */
export function migrateLensState(staleDecode, personalization, originSnapshot = null) {
  const { state, binding } = staleDecode;
  const origin =
    originSnapshot !== null && originSnapshot.panel_id === binding.panelId ? originSnapshot : null;

  const categoryResults = state.categoryCodes.map((code) =>
    resolveCategoryToken(code, personalization, origin),
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
