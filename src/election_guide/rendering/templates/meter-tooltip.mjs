// The segmented meter's per-block tooltip (docs/METER_V2.md, The discovery
// model), wired once for the whole page rather than once per meter: every
// block on every meter carries its source and decision as data attributes
// (`meter-layout.mjs`'s `MeterBlockRender`), so one shared tooltip element and
// one set of document-level listeners serves every meter a page renders,
// including one lit takes over after the reader diverges from the audited
// default.
//
// Blocks are presentational and carry no ARIA of their own — the meter's
// `role="img"` name is the full standings, and descendants of `role="img"`
// are pruned by assistive technology regardless (docs/METER_V2.md, The
// discovery model's accessibility model). This tooltip is therefore a
// sighted-pointer and touch-only affordance; a keyboard-only reader reaches
// the same evidence from the race page's own source lists, which is why the
// meter's one tab stop reveals seams rather than moving a focus ring block to
// block.
//
// Not a live region: WCAG 1.4.13 asks that added content be dismissible
// (Escape), hoverable, and persistent, not that it be announced. The tooltip
// is `pointer-events: none` (meter-*.css), so the pointer is never "on" it in
// a way that could dismiss it, which is what makes it hoverable by
// construction; Escape and leaving the block close it explicitly below.
//
// Wiring, not a computing module: it holds one DOM element and one set of
// document listeners.

const TOOLTIP_CLASS = 'meter-tooltip';
const HOLD_MS = 350;
const HOLD_SLOP = 8;

/** @type {HTMLElement|null} */
let tooltipElement = null;
/** @type {Element|null} */
let activeBlock = null;

/**
 * The one shared tooltip element, created on first use and reused after —
 * `document.body.contains` rather than a bare truthiness check, so the
 * element is rebuilt if the page (or a test's own DOM reset) ever removed it
 * out from under this module's reference.
 *
 * @returns {HTMLElement}
 */
function ensureTooltip() {
  if (tooltipElement && document.body.contains(tooltipElement)) return tooltipElement;
  const element = document.createElement('div');
  element.className = TOOLTIP_CLASS;
  element.hidden = true;
  document.body.append(element);
  tooltipElement = element;
  return element;
}

/**
 * @param {HTMLElement} tooltip
 * @param {Element} block
 */
function positionTooltip(tooltip, block) {
  const blockRect = block.getBoundingClientRect();
  tooltip.style.left = '0px';
  tooltip.style.top = '0px';
  const tooltipRect = tooltip.getBoundingClientRect();
  const x = Math.min(
    Math.max(8, blockRect.left + blockRect.width / 2 - tooltipRect.width / 2),
    window.innerWidth - tooltipRect.width - 8,
  );
  const belowY = blockRect.bottom + 8;
  const aboveY = blockRect.top - tooltipRect.height - 8;
  tooltip.style.left = `${x}px`;
  tooltip.style.top = `${aboveY < 8 ? belowY : aboveY}px`;
}

/** @param {Element} block */
function showTooltip(block) {
  const source = /** @type {HTMLElement} */ (block).dataset.meterSource;
  const decision = /** @type {HTMLElement} */ (block).dataset.meterDecision;
  if (!source) return;
  const tooltip = ensureTooltip();
  const sourceLine = document.createElement('div');
  sourceLine.className = 'meter-tooltip-source';
  sourceLine.textContent = source;
  const decisionLine = document.createElement('div');
  decisionLine.textContent = decision ?? '';
  tooltip.replaceChildren(sourceLine, decisionLine);
  tooltip.hidden = false;
  activeBlock = block;
  positionTooltip(tooltip, block);
}

function hideTooltip() {
  if (tooltipElement) tooltipElement.hidden = true;
  activeBlock = null;
}

/** @param {Event} event */
function meterBlock(event) {
  const target = /** @type {Element|null} */ (event.target);
  return target?.closest instanceof Function ? target.closest('.meter-block') : null;
}

/**
 * Wire the segmented meter's per-block tooltip. Idempotent — calling it more
 * than once (a page's entry script boots once, but a test may wire a fresh
 * document) attaches the listeners again rather than tracking a guard flag,
 * because the alternative is a module-level flag a test can never reset.
 */
export function wireMeterTooltips() {
  /** @type {{meter: Element, block: Element|null, x: number, y: number, revealed: boolean, timer: ReturnType<typeof setTimeout>}|null} */
  let hold = null;

  function cancelHold() {
    if (!hold) return;
    clearTimeout(hold.timer);
    hold.meter.classList.remove('meter-inspecting');
    hold = null;
    hideTooltip();
  }

  document.addEventListener('pointerover', (event) => {
    if (event.pointerType === 'touch') return;
    const block = meterBlock(event);
    if (block) {
      const meter = block.closest('.screen-meter');
      meter?.classList.remove('meter-touch');
      // A secondary mouse can hover even when the primary input is touch.
      meter?.classList.add('meter-inspecting');
      showTooltip(block);
    }
  });
  document.addEventListener('pointerout', (event) => {
    if (event.pointerType === 'touch') return;
    const block = meterBlock(event);
    block?.closest('.screen-meter')?.classList.remove('meter-inspecting');
    if (block && block === activeBlock) hideTooltip();
  });
  // Do not let a compatibility click turn a short touch into inspection or
  // reopen a tooltip after release. Pointer inspection is hover-driven.
  document.addEventListener('click', (event) => {
    if (!meterBlock(event)) hideTooltip();
  });

  document.addEventListener(
    'touchstart',
    (event) => {
      cancelHold();
      hideTooltip();
      if (event.touches.length !== 1) return;
      const block = meterBlock(event);
      const meter = block?.closest('.screen-meter');
      if (!block || !meter) return;
      meter.classList.add('meter-touch');
      meter.classList.remove('meter-inspecting');
      const finger = event.touches[0];
      hold = {
        meter,
        block,
        x: finger.clientX,
        y: finger.clientY,
        revealed: false,
        timer: setTimeout(() => {
          if (!hold || !meter.isConnected) {
            cancelHold();
            return;
          }
          hold.revealed = true;
          meter.classList.add('meter-inspecting');
          if (hold.block?.isConnected) showTooltip(hold.block);
        }, HOLD_MS),
      };
    },
    { passive: true },
  );

  // Touch events retain their original target while the finger moves. Hit-test
  // the current coordinates instead. Pointer events alone cannot arbitrate a
  // hold versus scrolling: touch-action is fixed at the start of the gesture.
  document.addEventListener(
    'touchmove',
    (event) => {
      if (!hold) return;
      if (event.touches.length !== 1 || !event.cancelable || !hold.meter.isConnected) {
        cancelHold();
        return;
      }
      const finger = event.touches[0];
      if (
        !hold.revealed &&
        Math.hypot(finger.clientX - hold.x, finger.clientY - hold.y) > HOLD_SLOP
      ) {
        cancelHold();
        return;
      }
      if (hold.revealed) event.preventDefault();
      const block = document
        .elementFromPoint(finger.clientX, finger.clientY)
        ?.closest('.meter-block');
      hold.block = block && block.closest('.screen-meter') === hold.meter ? block : null;
      if (!hold.revealed) return;
      if (hold.block) {
        if (hold.block !== activeBlock) showTooltip(hold.block);
      } else {
        hideTooltip();
      }
    },
    { passive: false },
  );
  document.addEventListener('touchend', cancelHold);
  document.addEventListener('touchcancel', cancelHold);
  document.addEventListener('scroll', cancelHold, { capture: true, passive: true });
  document.addEventListener('contextmenu', (event) => {
    if (hold) event.preventDefault();
  });
  window.addEventListener('blur', cancelHold);
  document.addEventListener('visibilitychange', () => {
    if (document.hidden) cancelHold();
  });
  document.addEventListener('keydown', (event) => {
    if (event.key === 'Escape') {
      cancelHold();
      hideTooltip();
    }
  });
}
