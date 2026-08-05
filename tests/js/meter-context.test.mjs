// meter-context.mjs wires the race page's candidate-context treatment
// (docs/METER_V2.md, Color; The discovery model; #315): clicking a chip
// selects that candidate's blocks on the shared headline meter, clicking it
// again deselects, and clicking a different chip moves the selection. These
// tests build the same shape `_meter.html.j2`'s `meter_chips`/`meter_block`
// macros and their lit twins (`race-detail.mjs`, `guide-card.mjs`) render —
// a `[data-race-headline]` holding a `.screen-meter` of `.meter-block`s
// alongside a `.meter-chips` list — and exercise the document listener the
// module attaches, not those templates themselves.

import assert from 'node:assert/strict';
import test from 'node:test';
import { installDom } from './support/dom.mjs';
import { assertModuleGuard } from './support/module-guards.mjs';

const document = installDom();
const { wireMeterContext } = await import(
  '../../src/election_guide/rendering/templates/meter-context.mjs'
);

wireMeterContext();

/**
 * A `[data-race-headline]` containing one meter, whose blocks each carry the
 * candidate id(s) named, and one chip per distinct candidate.
 *
 * @param {readonly [string, string[]][]} blockSpecs One entry per block: the
 *   block's own dataset key is irrelevant here, only which candidate(s) it
 *   names.
 */
function headline(blockSpecs) {
  const root = document.createElement('div');
  root.dataset.raceHeadline = '';
  const meter = document.createElement('div');
  meter.className = 'screen-meter';
  for (const [, candidateIds] of blockSpecs) {
    const block = document.createElement('span');
    block.className = 'meter-block meter-block-solid';
    block.dataset.meterCandidates = candidateIds.join(',');
    meter.append(block);
  }
  const chips = document.createElement('ul');
  chips.className = 'meter-chips';
  const seen = new Set();
  for (const [, candidateIds] of blockSpecs) {
    for (const candidateId of candidateIds) {
      if (seen.has(candidateId)) continue;
      seen.add(candidateId);
      const chip = document.createElement('button');
      chip.dataset.meterChip = '';
      chip.dataset.meterCandidate = candidateId;
      chip.setAttribute('aria-pressed', 'false');
      chips.append(chip);
    }
  }
  root.append(meter, chips);
  document.body.append(root);
  return { root, meter, chips };
}

/** @param {Element} target */
function click(target) {
  target.dispatchEvent(new Event('click', { bubbles: true }));
}

test.beforeEach(() => {
  document.body.replaceChildren();
});

test('selecting a chip presses it, bolds its own blocks, and puts the meter in context', () => {
  const { meter, chips } = headline([
    ['a', ['cand-a']],
    ['b', ['cand-b']],
  ]);
  const [chipA] = chips.querySelectorAll('[data-meter-chip]');
  const [blockA, blockB] = meter.querySelectorAll('.meter-block');

  click(chipA);

  assert.equal(chipA.getAttribute('aria-pressed'), 'true');
  assert.equal(meter.classList.contains('meter-context'), true);
  assert.equal(blockA.classList.contains('meter-block-context'), true);
  assert.equal(blockB.classList.contains('meter-block-context'), false);
});

test("a split block carries two candidate ids, and either one's chip selects it", () => {
  const { meter, chips } = headline([
    ['a', ['cand-a']],
    ['split', ['cand-a', 'cand-b']],
  ]);
  const [, chipB] = chips.querySelectorAll('[data-meter-chip]');
  const [blockA, blockSplit] = meter.querySelectorAll('.meter-block');

  click(chipB);

  assert.equal(blockA.classList.contains('meter-block-context'), false);
  assert.equal(blockSplit.classList.contains('meter-block-context'), true);
});

test('pressing the same chip again clears the context — deselecting restores rest', () => {
  const { meter, chips } = headline([['a', ['cand-a']]]);
  const [chipA] = chips.querySelectorAll('[data-meter-chip]');

  click(chipA);
  click(chipA);

  assert.equal(chipA.getAttribute('aria-pressed'), 'false');
  assert.equal(meter.classList.contains('meter-context'), false);
  assert.equal(
    meter.querySelector('.meter-block').classList.contains('meter-block-context'),
    false,
  );
});

test('selecting a second chip moves the context, deselecting the first', () => {
  const { meter, chips } = headline([
    ['a', ['cand-a']],
    ['b', ['cand-b']],
  ]);
  const [chipA, chipB] = chips.querySelectorAll('[data-meter-chip]');
  const [blockA, blockB] = meter.querySelectorAll('.meter-block');

  click(chipA);
  click(chipB);

  assert.equal(chipA.getAttribute('aria-pressed'), 'false');
  assert.equal(chipB.getAttribute('aria-pressed'), 'true');
  assert.equal(blockA.classList.contains('meter-block-context'), false);
  assert.equal(blockB.classList.contains('meter-block-context'), true);
});

test('a click outside any chip does nothing', () => {
  const { meter } = headline([['a', ['cand-a']]]);
  const elsewhere = document.createElement('div');
  document.body.append(elsewhere);

  click(elsewhere);

  assert.equal(meter.classList.contains('meter-context'), false);
});

test('the module keeps client state out of storage, and is wiring, not a computing module', () => {
  assertModuleGuard('meter-context.mjs');
});
