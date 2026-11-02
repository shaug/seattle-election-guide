import assert from 'node:assert/strict';
import test from 'node:test';
import { installDom } from './support/dom.mjs';
import { assertModuleGuard } from './support/module-guards.mjs';

installDom();
const { wireUpdates } = await import(
  '../../src/election_guide/rendering/templates/updates-client.mjs'
);
const topics = ['endorsements', 'sources', 'results'];
const entries = [
  { key: 'a', topics: ['endorsements'] },
  { key: 'b', topics: ['endorsements', 'sources'] },
  { key: 'c', topics: ['results'] },
];
function boot(search = '', rows = entries) {
  const doc = installDom(`https://seattleelections.guide/e/wa-2026-general/updates/${search}`);
  const payload = {
    schema_version: '1.0',
    topics: topics.map((id) => ({ id, label: id })),
    entries: rows,
    count_labels: ['0 updates', '1 update', '2 updates', '3 updates'],
  };
  doc.body.innerHTML = `<div data-update-controls></div><p data-update-count role="status" aria-live="polite">${rows.length} updates</p><p data-update-empty hidden>No updates match these topics.</p><p data-payload-notice hidden></p>${rows.map((e) => `<article data-update-key="${e.key}">${e.key}</article>`).join('')}<script type="application/json" data-client-payload>${JSON.stringify(payload)}</script>`;
  wireUpdates();
  return doc;
}
function button(doc, topic) {
  return doc.querySelector(`[data-update-topic="${topic}"]`);
}

test('all eight independent OR subsets match once and all three stay selected', () => {
  for (let mask = 0; mask < 8; mask++) {
    const selected = topics.filter((_, i) => mask & (1 << i));
    const doc = boot(`?topics=${selected.join(',')}`);
    const actual = [...doc.querySelectorAll('[data-update-key]')]
      .filter((e) => !e.hidden)
      .map((e) => e.textContent);
    const expected = entries
      .filter((e) => !selected.length || e.topics.some((t) => selected.includes(t)))
      .map((e) => e.key);
    assert.deepEqual(actual, expected);
    assert.equal(
      doc.querySelector('[data-update-count]').textContent,
      `${expected.length} update${expected.length === 1 ? '' : 's'}`,
    );
    assert.deepEqual(
      [...doc.querySelectorAll('button')].map((element) => element.dataset.updateTopic),
      topics,
    );
    for (const topic of topics)
      assert.equal(
        button(doc, topic).getAttribute('aria-pressed'),
        String(selected.includes(topic)),
      );
  }
});

test('final deselection and history restore the complete log without moving focus', () => {
  const doc = boot('?keep=yes');
  const active = button(doc, 'endorsements');
  const count = doc.querySelector('[data-update-count]');
  active.focus();
  active.click();
  button(doc, 'results').click();
  assert.equal(doc.activeElement, active);
  assert.equal(button(doc, 'endorsements'), active);
  assert.equal(window.location.search, '?keep=yes&topics=endorsements,results');
  window.history.replaceState(null, '', '?keep=yes&topics=sources');
  window.dispatchEvent(new Event('popstate'));
  assert.equal(button(doc, 'sources').getAttribute('aria-pressed'), 'true');
  button(doc, 'sources').click();
  assert.equal(doc.querySelector('[data-update-count]').textContent, '3 updates');
  active.click();
  active.click();
  for (const topic of topics)
    assert.equal(button(doc, topic).getAttribute('aria-pressed'), 'false');
  assert.equal(doc.activeElement, active);
  assert.equal(doc.querySelectorAll('[data-update-key]:not([hidden])').length, 3);
  assert.equal(doc.querySelector('[data-update-count]'), count);
  assert.equal(window.location.search, '?keep=yes');
});

test('an absent topic has an honest empty result without moving focus', () => {
  const doc = boot('?topics=results', entries.slice(0, 2));
  assert.equal(doc.querySelector('[data-update-empty]').hidden, false);
  assert.equal(doc.querySelector('[data-update-count]').textContent, '0 updates');
  assert.equal(doc.querySelectorAll('button').length, 3);
  for (const element of doc.querySelectorAll('button')) assert.equal(element.childElementCount, 0);
});

test('Updates wiring has no storage capability', () => assertModuleGuard('updates-client.mjs'));
