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
function block(source, decision) {
  const element = document.createElement('div');
  element.className = 'meter-block meter-block-solid';
  element.dataset.meterSource = source;
  element.dataset.meterDecision = decision;
  document.body.append(element);
  return element;
}

/** @param {Element} target @param {string} type */
function fire(target, type) {
  target.dispatchEvent(new Event(type, { bubbles: true }));
}

test.beforeEach(() => {
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
});

test('leaving the block closes the tooltip', () => {
  const the = block('The Stranger', 'Endorsed Jamie Pedersen');
  fire(the, 'pointerover');
  fire(the, 'pointerout');

  assert.equal(document.querySelector('.meter-tooltip').hidden, true);
});

test('Escape closes an open tooltip', () => {
  const the = block('The Urbanist', 'Endorsed Nilu Jenks');
  fire(the, 'pointerover');
  document.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape' }));

  assert.equal(document.querySelector('.meter-tooltip').hidden, true);
});

test('tapping a block opens it, and a second tap closes it — the touch path', () => {
  const the = block('King County Democrats', 'Endorsed Nilu Jenks');
  fire(the, 'click');
  assert.equal(document.querySelector('.meter-tooltip').hidden, false);

  fire(the, 'click');
  assert.equal(document.querySelector('.meter-tooltip').hidden, true);
});

test('tapping outside an open tooltip closes it', () => {
  const the = block('King County Democrats', 'Endorsed Nilu Jenks');
  fire(the, 'click');

  const elsewhere = document.createElement('div');
  document.body.append(elsewhere);
  fire(elsewhere, 'click');

  assert.equal(document.querySelector('.meter-tooltip').hidden, true);
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
