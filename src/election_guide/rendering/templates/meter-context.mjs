// The race page's candidate-context treatment (docs/METER_V2.md, Color; the
// discovery model; #315): selecting a candidate's chip puts the shared
// headline meter into an engaged state like hover — that candidate's own
// blocks go bold, every other block recedes to 30% opacity, and the resting
// percent hides (guide-race.css). A split block's two halves can each belong
// to a different candidate, so a selected candidate's own half there bolds
// while its competing half recedes on its own, rather than the whole block
// bolding just because it names the selected candidate once. Deselecting —
// pressing the same chip again — restores rest.
//
// Wired the same way the per-block tooltip is (`meter-tooltip.mjs`): one
// shared, document-level click listener rather than one per meter, because a
// meter's blocks and its chips are rebuilt by lit whenever the reader's lens
// selection changes (`race-client.mjs`), and a listener bound to a
// particular element would go stale the moment that happens. The handler
// re-queries the DOM on every click instead of caching references, which is
// also why a lens change silently drops any active context rather than
// needing to reapply it after rebuilding the region: the fresh chips and
// blocks carry no pressed or context state until the reader picks a
// candidate again, the same resting default the audited page itself renders.
//
// A chip and the blocks it controls are matched by candidate id alone —
// `data-meter-candidate` on the chip, `data-meter-candidates` (comma-joined;
// a split block names two) on each block, both written by the audited
// template and its lit twin alike (`_meter.html.j2`, `guide-card.mjs`,
// `race-detail.mjs`) — so this module carries no view model of its own, only
// wiring.

const CONTEXT_CLASS = 'meter-context';
const BLOCK_CONTEXT_CLASS = 'meter-block-context';
const HALF_CONTEXT_CLASS = 'meter-half-context';
const HALF_RECEDE_CLASS = 'meter-half-recede';

/**
 * The chip a click landed on, if any.
 *
 * @param {Event} event
 * @returns {Element|null}
 */
function chipButton(event) {
  const target = /** @type {Element|null} */ (event.target);
  return target?.closest instanceof Function ? target.closest('[data-meter-chip]') : null;
}

/**
 * Apply one candidate's context to a single block: bold if it is the
 * block's only candidate, unchanged (the whole-block `:not(.meter-block-
 * context)` rule already recedes it) if the block names neither candidate
 * the context is in, and — the case a whole-block class cannot express —
 * per-half if it names two: the matching half bolds, its competing half
 * recedes on its own, since `filter: saturate(1.5) brightness(.9)` on the
 * shared outer span would otherwise bold both halves just because one of
 * them is the selected candidate (docs/METER_V2.md, Color).
 *
 * @param {Element} block
 * @param {string|null} candidateId
 */
function applyBlockContext(block, candidateId) {
  const ids = (block.getAttribute('data-meter-candidates') ?? '').split(',');
  const matches = candidateId !== null && ids.includes(candidateId);
  block.classList.toggle(BLOCK_CONTEXT_CLASS, matches);
  const top = block.querySelector('.meter-half-top');
  const bottom = block.querySelector('.meter-half-bottom');
  if (!top || !bottom) return;
  // `candidate_ids` is ordered top first, bottom second — the same order
  // `_meter_block_facing`/`meterBlockRenders` paint the two halves in
  // (`context.py`, `meter-layout.mjs`), so `ids[0]`/`ids[1]` name them
  // without needing the halves' own markup to carry an id.
  const topMatches = matches && ids[0] === candidateId;
  const bottomMatches = matches && ids[1] === candidateId;
  top.classList.toggle(HALF_CONTEXT_CLASS, topMatches);
  top.classList.toggle(HALF_RECEDE_CLASS, matches && !topMatches);
  bottom.classList.toggle(HALF_CONTEXT_CLASS, bottomMatches);
  bottom.classList.toggle(HALF_RECEDE_CLASS, matches && !bottomMatches);
}

/**
 * Apply (or clear) one candidate's context on the meter a chip list controls.
 *
 * @param {Element} chipList
 * @param {string|null} candidateId
 */
function applyContext(chipList, candidateId) {
  for (const chip of chipList.querySelectorAll('[data-meter-chip]')) {
    const pressed =
      candidateId !== null && chip.getAttribute('data-meter-candidate') === candidateId;
    chip.setAttribute('aria-pressed', String(pressed));
  }
  const headline = chipList.closest('[data-race-headline]');
  const meter = headline?.querySelector('.screen-meter') ?? null;
  if (!meter) return;
  meter.classList.toggle(CONTEXT_CLASS, candidateId !== null);
  for (const block of meter.querySelectorAll('.meter-block')) {
    applyBlockContext(block, candidateId);
  }
}

/**
 * Clear any candidate context a headline's chips or blocks are carrying.
 *
 * `applyContext` above only runs from a click, so it never sees a lens
 * change that rebuilds `resultRegion`/`chipsRegion` through lit's
 * incremental `render()` rather than a full `replaceChildren()`
 * (`race-client.mjs`, `renderRace`'s one-time `takenOver` teardown). Lit
 * reuses a chip or block DOM node whenever its key (a candidate id) recurs
 * across renders, and only writes the attributes and classes its own
 * template expressions bind — `aria-pressed` is static markup with no
 * expression, and a `class=${…}` binding is skipped whenever the newly
 * computed string matches the last one lit wrote, which happens whenever a
 * block's shape (solid vs. split, band-edge flags) repeats at that same
 * position across two lens selections. Neither case ever un-presses a chip
 * or un-bolds a block lit itself didn't just paint over, so a context the
 * reader selected before changing their lens can survive, pointed at
 * whatever candidate now occupies that reused node — exactly the state this
 * function exists to prevent by being called after every such render, not
 * only after a click.
 *
 * @param {Element} headline The `[data-race-headline]` (or any ancestor of
 *   both a `.meter-chips` list and the `.screen-meter` it controls).
 */
export function resetMeterContext(headline) {
  for (const chip of headline.querySelectorAll('[data-meter-chip]')) {
    chip.setAttribute('aria-pressed', 'false');
  }
  const meter = headline.querySelector('.screen-meter');
  if (!meter) return;
  meter.classList.remove(CONTEXT_CLASS);
  for (const block of meter.querySelectorAll('.meter-block')) {
    block.classList.remove(BLOCK_CONTEXT_CLASS);
  }
  for (const half of meter.querySelectorAll('.meter-half-top, .meter-half-bottom')) {
    half.classList.remove(HALF_CONTEXT_CLASS, HALF_RECEDE_CLASS);
  }
}

/**
 * Wire every race page's candidate-context chips. Idempotent, like
 * `wireMeterTooltips` — one document-level listener, attached once per boot.
 */
export function wireMeterContext() {
  document.addEventListener('click', (event) => {
    const chip = chipButton(event);
    if (!chip) return;
    const chipList = chip.closest('.meter-chips');
    if (!chipList) return;
    const candidateId = chip.getAttribute('data-meter-candidate');
    const alreadySelected = chip.getAttribute('aria-pressed') === 'true';
    applyContext(chipList, alreadySelected ? null : candidateId);
  });
}
