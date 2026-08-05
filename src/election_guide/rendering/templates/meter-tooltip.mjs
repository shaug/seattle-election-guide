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
// construction; Escape and a tap outside close it explicitly below.
//
// Wiring, not a computing module: it holds one DOM element and one set of
// document listeners.

const TOOLTIP_CLASS = 'meter-tooltip';

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
  document.addEventListener('pointerover', (event) => {
    const block = meterBlock(event);
    if (block) showTooltip(block);
  });
  document.addEventListener('pointerout', (event) => {
    const block = meterBlock(event);
    if (block && block === activeBlock) hideTooltip();
  });
  // Touch has no hover: a tap opens the same tooltip a pointer's hover would,
  // and a second tap — on the same block, or anywhere else — closes it
  // (WCAG 1.4.13's dismissible criterion, satisfied without waiting on Escape
  // for a device with no keyboard to raise it on).
  document.addEventListener('click', (event) => {
    const block = meterBlock(event);
    if (block === activeBlock) {
      hideTooltip();
      return;
    }
    if (block) {
      showTooltip(block);
      return;
    }
    hideTooltip();
  });
  document.addEventListener('keydown', (event) => {
    if (event.key === 'Escape' && activeBlock) hideTooltip();
  });
}
