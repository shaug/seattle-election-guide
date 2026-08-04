// The selection logic every lens-aware page shares.
//
// The guide, a race page, and the standalone sources editor answer the same
// questions about a lens — which sources a decoded selection actually names,
// whether that is still the audited default, what an incoming link resolves to
// and what the reader should be told about it, and what fragment carries the
// selection to the next page. Until issue #239 each page answered them with its
// own copy of the same code inside its own `<script>` block. One module, one
// implementation, tested once in Node.
//
// What is deliberately *not* here is any page's wiring. This module shares a
// vocabulary, not an engine, in exactly the sense `fragment-codec.mjs` does for
// the two codecs: each page still reads its own address, renders its own
// regions, and decides its own boot order, because those differ and expressing
// the difference as configuration would cost more than the sharing saves.
//
// Pure: it maps codes to codes and hands back an outcome. Nothing here touches
// a checkbox, a link, or `location`; the pages' own wiring does that.

import { migrateLensState } from './lens-migrate.mjs';
import { encodeLensFragment } from './lens-url.mjs';

/** What a reader is told when the link they followed cannot be read at all. */
export const UNREADABLE_LINK_NOTICE =
  'This link could not be read, so it shows the audited consensus.';

/** ...and when it was written against an earlier published data version. */
export const MIGRATED_LINK_NOTICE =
  'This link was written for an earlier published data version. It was migrated to the current ' +
  'panel, so results may differ from the original link.';

/**
 * What a reader is told when their selection cannot be written into a link.
 *
 * The rule this satisfies: a decode *or encode* failure produces a
 * reader-visible notice, never a silent fallthrough (docs/FRONTEND.md § State
 * and URLs). Before issue #239 both pages dropped a rejected encode on the
 * floor and quietly published a link to the audited guide instead, so a reader
 * who followed it lost the selection they were looking at with no indication
 * that anything had happened.
 */
export const SELECTION_LINK_FAILURE_NOTICE =
  'Your source selection could not be written into a link, so this link shows the audited ' +
  'results instead. Your selection on this page is unchanged.';

/**
 * @typedef {object} LensSelection
 * @property {string[]} [categoryCodes]
 * @property {string[]} [sourceCodes]
 * @property {string|null} [raceTarget]
 */

/**
 * The source codes a decoded selection actually names.
 *
 * A category code expands to its *current* member codes, so a link shared
 * before issue 97's per-source selection existed still follows the panel as it
 * is published today; directly named source codes union with those. Anything
 * the panel does not publish is dropped, and the result keeps the panel's own
 * order rather than the link's.
 *
 * @param {LensSelection|null|undefined} selection
 * @param {ReadonlyMap<string, readonly string[]>} memberCodesByCategoryCode
 * @param {readonly string[]} panelSourceCodes Every code the panel publishes,
 *   in published order.
 * @returns {string[]}
 */
export function resolveSelectedCodes(selection, memberCodesByCategoryCode, panelSourceCodes) {
  const fromCategories = (selection?.categoryCodes ?? []).flatMap(
    (code) => memberCodesByCategoryCode.get(code) ?? [],
  );
  const named = new Set([...fromCategories, ...(selection?.sourceCodes ?? [])]);
  return panelSourceCodes.filter((code) => named.has(code));
}

/**
 * The codes of the sources that count toward a score, in published order.
 *
 * A source tallies unless its panel role is `comparison` — issue 124 retired
 * the comparison treatment, and such a source is published only so the codec
 * can recognize a pre-removal link's token and ignore it. Stated once here
 * because both halves of the guide need the same answer and must not be able
 * to disagree: the banner's "Counting N of M" and the Sources link's decision
 * to carry a lens fragment are the same judgement.
 *
 * @param {readonly { code: string, panel_role: string }[]} panelSources
 * @returns {string[]}
 */
export function tallyingSourceCodes(panelSources) {
  return panelSources
    .filter((source) => source.panel_role !== 'comparison')
    .map((source) => source.code);
}

/**
 * The audited default: every tallying source counted.
 *
 * Represented by the absence of a lens fragment (issue 97's "every checkbox
 * starts checked" design), so a link naming nothing reaches exactly this state.
 *
 * @param {readonly string[]} selectedCodes
 * @param {readonly string[]} tallyingCodes
 * @returns {boolean}
 */
export function isDefaultSelection(selectedCodes, tallyingCodes) {
  return selectedCodes.length === tallyingCodes.length;
}

/**
 * @typedef {{ status: 'ok', fragment: string }
 *   | { status: 'rejected', reason: string }
 * } SelectionFragmentResult
 */

/**
 * The fragment that carries one selection, or an explicit rejection.
 *
 * `status: 'rejected'` is the whole point of this function's shape. The codec
 * can refuse an encode — an oversized selection is the reachable case — and the
 * callers used to turn that refusal into an empty string, which is
 * indistinguishable from "nothing to carry". A caller now has to decide what to
 * tell the reader, and both pages tell them.
 *
 * The audited default encodes to no lens fragment at all, only the race target
 * the reader is on, because that is what the default *means* in this scheme.
 *
 * @param {object} options
 * @param {readonly string[]} options.selectedCodes
 * @param {readonly string[]} options.tallyingCodes
 * @param {string|null} options.raceTarget
 * @param {import('./lens-url.mjs').LensContext} options.context
 * @returns {SelectionFragmentResult}
 */
export function selectionFragment({ selectedCodes, tallyingCodes, raceTarget, context }) {
  if (isDefaultSelection(selectedCodes, tallyingCodes)) {
    return { status: 'ok', fragment: raceTarget ? `#${raceTarget}` : '' };
  }
  const encoded = encodeLensFragment(
    { mode: 's', categoryCodes: [], sourceCodes: [...selectedCodes], raceTarget },
    context,
  );
  if (encoded.status !== 'ok') return { status: 'rejected', reason: encoded.reason };
  return { status: 'ok', fragment: `#${encoded.fragment}` };
}

/**
 * One decoded fragment resolved to live state, an explanation, and whether the
 * address bar has to be cleaned.
 *
 * @typedef {object} LensLinkOutcome
 * @property {import('./lens-url.mjs').LensState|null} state
 * @property {string|null} notice
 * @property {boolean} cleanAddress
 */

/**
 * Resolve one decoded fragment to live lens state plus a persistent
 * explanation, when one is warranted.
 *
 * A same-version link needs neither migration nor an explanation. A
 * `stale_version` link is resolved through issue 78's migration resolver, with
 * no origin snapshot: nothing about correct resolution depends on one (a
 * surviving code always names the same source or category it always did), it
 * only refines "removed" versus "unknown" reporting these pages do not surface.
 * A migration that must reject falls back to audited. Every other non-lens
 * status (`absent`, `legacy`, or an ordinary in-page anchor the codec does not
 * recognize, such as the skip link) carries no lens explanation at all, so
 * clicking around a page never manufactures one.
 *
 * With the lens disabled there is nothing to migrate a stale link into and
 * nothing on the page acts on a selection, so the decode runs only so that an
 * unreadable fragment is recognized — and reported. It used to be cleaned from
 * the address bar in silence, which the rule forbids (docs/FRONTEND.md § State
 * and URLs: a decode failure produces a reader-visible notice *and* a cleaned
 * address bar).
 *
 * @param {import('./lens-url.mjs').LensDecodeResult} decoded
 * @param {PersonalizationContract|null} personalization
 * @returns {LensLinkOutcome}
 */
export function resolveLensLink(decoded, personalization) {
  const unreadable = decoded.status === 'malformed' && decoded.reason !== 'unrecognized_fragment';
  if (personalization === null) {
    const usable = decoded.status === 'valid' || decoded.status === 'stale_version';
    return {
      state: usable ? decoded.state : null,
      notice: unreadable ? UNREADABLE_LINK_NOTICE : null,
      cleanAddress: unreadable,
    };
  }
  if (decoded.status === 'valid') {
    return { state: decoded.state, notice: null, cleanAddress: false };
  }
  if (decoded.status === 'stale_version') {
    const migration = migrateLensState(decoded, personalization, null);
    if (migration.status === 'migrated') {
      return { state: migration.selection, notice: MIGRATED_LINK_NOTICE, cleanAddress: false };
    }
    return {
      state: null,
      notice:
        'This link could not be migrated to the current published panel ' +
        `(category ${migration.category} is no longer available), so it shows the audited consensus.`,
      cleanAddress: true,
    };
  }
  if (!unreadable) return { state: null, notice: null, cleanAddress: false };
  return { state: null, notice: UNREADABLE_LINK_NOTICE, cleanAddress: true };
}

/**
 * The race the reader is on, given one decode and whatever state it resolved to.
 *
 * A `legacy` fragment *is* the race target and carries no selection to resolve;
 * every other shape carries the target inside the state, so a fragment that
 * resolved to no state names no race either. Shared because both pages need the
 * same answer: the guide to keep its Sources links pointing at the race being
 * read, the editor to send Save back to it.
 *
 * @param {import('./lens-url.mjs').LensDecodeResult} decoded
 * @param {LensSelection|null|undefined} resolvedState The state the page
 *   accepted, which is not always `decoded.state` — a stale link that fails
 *   migration decodes to a state the guide then declines to use.
 * @returns {string|null}
 */
export function raceTargetFrom(decoded, resolvedState) {
  if (decoded.status === 'legacy') return decoded.raceTarget;
  return resolvedState?.raceTarget ?? null;
}
