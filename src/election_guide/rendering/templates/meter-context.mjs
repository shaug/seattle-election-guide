// The race page's candidate-context treatment (docs/METER_V2.md, Color; the
// discovery model; #315): selecting a candidate's chip puts the shared
// headline meter into an engaged state like hover — that candidate's own
// blocks go bold, every other block recedes to 30% opacity, and the resting
// percent hides (guide-race.css). Deselecting — pressing the same chip again
// — restores rest.
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
    const ids = (block.getAttribute('data-meter-candidates') ?? '').split(',');
    block.classList.toggle(BLOCK_CONTEXT_CLASS, candidateId !== null && ids.includes(candidateId));
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
