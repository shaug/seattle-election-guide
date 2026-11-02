import assert from 'node:assert/strict';
import test from 'node:test';
import { installDom } from './support/dom.mjs';
import { assertModuleGuard } from './support/module-guards.mjs';

const TOPICS = ['endorsements', 'sources', 'results'];
const PAGE = 'https://seattleelections.guide/e/wa-2026-general/updates/';
const { createUpdatesRouter } = await import(
  '../../src/election_guide/rendering/templates/updates-route.mjs'
);

test('topic admission canonicalizes duplicates and unknown tokens without inheriting other filters', () => {
  installDom(
    `${PAGE}?precinct=SEA&topics=results,unknown,endorsements,results&topics=sources&keep=yes#anchor`,
  );
  const router = createUpdatesRouter(TOPICS);
  assert.deepEqual(router.read(), TOPICS);
  router.replace(router.read());
  assert.equal(
    window.location.search,
    '?precinct=SEA&topics=endorsements,sources,results&keep=yes',
  );
  assert.equal(window.location.hash, '#anchor');
  router.commit([]);
  assert.equal(window.location.search, '?precinct=SEA&keep=yes');
  assert.deepEqual(router.read(), []);
});

test('unrecognized topics resolve to all and history subscriptions read the current address', () => {
  installDom(`${PAGE}?topics=unknown`);
  const router = createUpdatesRouter(TOPICS);
  assert.deepEqual(router.read(), []);
  let restored;
  const stop = router.subscribe((selected) => {
    restored = selected;
  });
  window.history.replaceState(null, '', '?topics=results');
  window.dispatchEvent(new Event('popstate'));
  assert.deepEqual(restored, ['results']);
  stop();
});

test('the topic router carries no storage capability', () =>
  assertModuleGuard('updates-route.mjs'));
