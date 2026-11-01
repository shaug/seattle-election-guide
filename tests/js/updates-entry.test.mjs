import assert from 'node:assert/strict';
import test from 'node:test';
import { installDom } from './support/dom.mjs';
import { assertModuleGuard } from './support/module-guards.mjs';

installDom();
const { boot } = await import('../../src/election_guide/rendering/templates/updates-entry.mjs');

test('the Updates entry preserves the existing calendar-derived election shell', () => {
  const doc = installDom();
  doc.body.innerHTML = `<p class="election-day" data-election-day="2026-10-01"
    data-election-day-full="October 1, 2026" data-election-day-short="October 1">
    <span data-election-day-when>Election day: October 1, 2026.</span>
    <a class="election-day-action" href="https://county.example/vote">How to vote</a></p>`;
  const OriginalDate = globalThis.Date;
  globalThis.Date = new Proxy(OriginalDate, {
    construct(target, args) {
      return Reflect.construct(target, args.length ? args : ['2026-11-01T12:00:00Z']);
    },
  });
  try {
    boot();
    assert.equal(doc.querySelector('.election-day').classList.contains('election-day-past'), true);
    assert.match(
      doc.querySelector('[data-election-day-when]').textContent,
      /This election was held/,
    );
    assert.equal(doc.querySelector('.election-day-action'), null);
  } finally {
    globalThis.Date = OriginalDate;
  }
});

test('the Updates entry leaves an already certified banner unchanged', () => {
  const doc = installDom();
  doc.body.innerHTML =
    '<p class="election-day election-day-past">This election is complete. Results were certified August 18, 2026.</p>';
  const before = doc.body.innerHTML;
  boot();
  assert.equal(doc.body.innerHTML, before);
});

test('the Updates entry has no storage capability', () => assertModuleGuard('updates-entry.mjs'));
