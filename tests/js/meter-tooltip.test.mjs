// meter-tooltip.mjs wires the segmented meter's per-block tooltip
// (docs/METER_V2.md, The discovery model). These tests exercise the document
// listeners the module attaches, not real pointer input — happy-dom has no
// layout engine, so `getBoundingClientRect()` returns zeroes throughout, and
// what these pin is that the right event opens and closes the tooltip with
// the right block's data, not where it lands on screen.

import assert from 'node:assert/strict';
import test from 'node:test';
import { installDom } from './support/dom.mjs';
import { assertModuleGuard } from './support/module-guards.mjs';

const document = installDom();
const { wireMeterTooltips } = await import(
  '../../src/election_guide/rendering/templates/meter-tooltip.mjs'
);

wireMeterTooltips();

/** @param {string} source @param {string} decision */
function block(source, decision, meter = null) {
  const element = document.createElement('div');
  element.className = 'meter-block meter-block-solid';
  element.dataset.meterSource = source;
  element.dataset.meterDecision = decision;
  if (!meter) {
    meter = document.createElement('div');
    meter.className = 'screen-meter';
    document.body.append(meter);
  }
  meter.append(element);
  return element;
}

/** @param {Element} target @param {string} type */
function fire(target, type) {
  target.dispatchEvent(new Event(type, { bubbles: true }));
}

function touch(target, type, x = 30, y = 50, count = 1) {
  const point = { identifier: 1, clientX: x, clientY: y, target };
  const event = new Event(type, { bubbles: true, cancelable: true });
  Object.assign(event, {
    touches: type === 'touchend' || type === 'touchcancel' ? [] : Array(count).fill(point),
    changedTouches: [point],
  });
  target.dispatchEvent(event);
  return event;
}

function tooltipVisible() {
  return document.querySelector('.meter-tooltip')?.hidden === false;
}

test.beforeEach(() => {
  document.dispatchEvent(new Event('touchcancel'));
  document.body.replaceChildren();
  const tooltip = document.querySelector('.meter-tooltip');
  tooltip?.remove();
});

test('hovering a block opens the tooltip with its source and decision', () => {
  const the = block('The Stranger', 'Endorsed Jamie Pedersen');
  fire(the, 'pointerover');

  const tooltip = document.querySelector('.meter-tooltip');
  assert.ok(tooltip, 'no tooltip element was created');
  assert.equal(tooltip.hidden, false);
  assert.equal(tooltip.querySelector('.meter-tooltip-source').textContent, 'The Stranger');
  assert.equal(tooltip.textContent, 'The StrangerEndorsed Jamie Pedersen');
  assert.equal(the.parentElement.classList.contains('meter-inspecting'), true);
});

test('leaving the block closes the tooltip', () => {
  const the = block('The Stranger', 'Endorsed Jamie Pedersen');
  fire(the, 'pointerover');
  fire(the, 'pointerout');

  assert.equal(document.querySelector('.meter-tooltip').hidden, true);
  assert.equal(the.parentElement.classList.contains('meter-inspecting'), false);
});

test('Escape closes an open tooltip', () => {
  const the = block('The Urbanist', 'Endorsed Nilu Jenks');
  fire(the, 'pointerover');
  document.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape' }));

  assert.equal(document.querySelector('.meter-tooltip').hidden, true);
  fire(the, 'pointerout');
  assert.equal(the.parentElement.classList.contains('meter-inspecting'), false);
});

test('a short touch and its compatibility click leave the resting meter alone', () => {
  const the = block('King County Democrats', 'Endorsed Nilu Jenks');
  touch(the, 'touchstart');
  touch(the, 'touchend');
  fire(the, 'click');
  assert.equal(tooltipVisible(), false);
});

test('tapping outside an open tooltip closes it', () => {
  const the = block('King County Democrats', 'Endorsed Nilu Jenks');
  fire(the, 'pointerover');

  const elsewhere = document.createElement('div');
  document.body.append(elsewhere);
  fire(elsewhere, 'click');

  assert.equal(document.querySelector('.meter-tooltip').hidden, true);
});

test('holding reveals a source, gliding hit-tests the finger, and release restores rest', (t) => {
  t.mock.timers.enable({ apis: ['setTimeout'] });
  const first = block('The Stranger', 'Endorsed Jamie Pedersen');
  const meter = first.parentElement;
  const second = block('The Urbanist', 'Split: Pedersen + Jenks — ½ each', meter);
  const half = document.createElement('span');
  second.append(half);
  t.mock.method(document, 'elementFromPoint', () => half);

  const start = touch(first, 'touchstart');
  assert.equal(start.defaultPrevented, false, 'a new touch must allow scrolling');
  assert.equal(tooltipVisible(), false);
  t.mock.timers.tick(400);
  assert.equal(tooltipVisible(), true);
  assert.equal(
    document.querySelector('.meter-tooltip').textContent,
    'The StrangerEndorsed Jamie Pedersen',
  );
  assert.equal(meter.classList.contains('meter-inspecting'), true);

  // Native touch targets stay on the original block throughout the gesture.
  const move = touch(first, 'touchmove', 100);
  assert.equal(move.defaultPrevented, true, 'inspection must not scroll the page');
  assert.equal(
    document.querySelector('.meter-tooltip').textContent,
    'The UrbanistSplit: Pedersen + Jenks — ½ each',
  );
  touch(first, 'touchend', 100);
  assert.equal(tooltipVisible(), false);
  assert.equal(meter.classList.contains('meter-inspecting'), false);
  fire(first, 'click');
  assert.equal(tooltipVisible(), false, 'the compatibility click must not reopen the tooltip');
});

test('moving before the hold cancels inspection and keeps native scrolling available', (t) => {
  t.mock.timers.enable({ apis: ['setTimeout'] });
  const the = block('The Stranger', 'Endorsed Jamie Pedersen');
  touch(the, 'touchstart');
  const move = touch(the, 'touchmove', 30, 80);
  t.mock.timers.tick(1000);
  assert.equal(move.defaultPrevented, false);
  assert.equal(tooltipVisible(), false);
});

test('a small move before activation inspects the source currently under the finger', (t) => {
  t.mock.timers.enable({ apis: ['setTimeout'] });
  const first = block('The Stranger', 'Endorsed Jamie Pedersen');
  const second = block('The Urbanist', 'Endorsed Nilu Jenks', first.parentElement);
  t.mock.method(document, 'elementFromPoint', () => second);
  touch(first, 'touchstart');
  touch(first, 'touchmove', 36);
  t.mock.timers.tick(400);
  assert.equal(document.querySelector('.meter-tooltip-source').textContent, 'The Urbanist');
});

test('touch pointer boundary events do not bypass the hold', () => {
  const the = block('The Stranger', 'Endorsed Jamie Pedersen');
  const over = new Event('pointerover', { bubbles: true });
  Object.assign(over, { pointerType: 'touch' });
  the.dispatchEvent(over);
  assert.equal(tooltipVisible(), false);
});

test('touch suppresses sticky hover until a real pointer returns', () => {
  const the = block('The Stranger', 'Endorsed Jamie Pedersen');
  fire(the, 'pointerover');
  touch(the, 'touchstart');
  assert.equal(the.parentElement.classList.contains('meter-inspecting'), false);
  touch(the, 'touchend');
  assert.equal(the.parentElement.classList.contains('meter-touch'), true);
  fire(the, 'pointerover');
  assert.equal(the.parentElement.classList.contains('meter-touch'), false);
  assert.equal(tooltipVisible(), true);
});

for (const ending of ['touchend', 'touchcancel', 'escape', 'blur']) {
  test(`${ending} cancels both pending and active holds`, (t) => {
    t.mock.timers.enable({ apis: ['setTimeout'] });
    const the = block('The Stranger', 'Endorsed Jamie Pedersen');
    const end = () => {
      if (ending === 'escape') {
        document.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape' }));
      } else if (ending === 'blur') {
        window.dispatchEvent(new Event('blur'));
      } else {
        touch(the, ending);
      }
    };
    touch(the, 'touchstart');
    end();
    t.mock.timers.tick(1000);
    assert.equal(tooltipVisible(), false);
    touch(the, 'touchstart');
    t.mock.timers.tick(400);
    assert.equal(tooltipVisible(), true);
    end();
    assert.equal(tooltipVisible(), false);
    assert.equal(the.parentElement.classList.contains('meter-inspecting'), false);
  });
}

test('inspection stays on the original meter and can resume after sliding outside it', (t) => {
  t.mock.timers.enable({ apis: ['setTimeout'] });
  const the = block('The Stranger', 'Endorsed Jamie Pedersen');
  const other = block('The Urbanist', 'Endorsed Nilu Jenks');
  const hit = t.mock.method(document, 'elementFromPoint', () => other);
  touch(the, 'touchstart');
  t.mock.timers.tick(400);
  touch(the, 'touchmove', 100);
  assert.equal(tooltipVisible(), false);
  hit.mock.mockImplementation(() => the);
  touch(the, 'touchmove');
  assert.equal(tooltipVisible(), true);
  touch(the, 'touchend');
});

test('a second finger cancels inspection without blocking pinch gestures', (t) => {
  t.mock.timers.enable({ apis: ['setTimeout'] });
  const the = block('The Stranger', 'Endorsed Jamie Pedersen');
  touch(the, 'touchstart');
  t.mock.timers.tick(400);
  const secondFinger = touch(the, 'touchstart', 35, 50, 2);
  assert.equal(secondFinger.defaultPrevented, false);
  assert.equal(tooltipVisible(), false);
  t.mock.timers.tick(1000);
  assert.equal(tooltipVisible(), false);
});

test('a block with no source data opens nothing', () => {
  const bare = document.createElement('div');
  bare.className = 'meter-block meter-block-solid';
  document.body.append(bare);
  fire(bare, 'pointerover');

  assert.equal(document.querySelector('.meter-tooltip'), null);
});

test('the module keeps client state out of storage, and is wiring, not a computing module', () => {
  assertModuleGuard('meter-tooltip.mjs');
});
