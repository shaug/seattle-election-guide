// A voter's districts control contest membership, never their source selection.
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';
import { installDom } from './support/dom.mjs';

installDom('https://seattleelections.guide/');
const { wireGuide } = await import('../../src/election_guide/rendering/templates/guide-client.mjs');
const { wireComparisons } = await import(
  '../../src/election_guide/rendering/templates/compare-client.mjs'
);
const { lensContext, encodeLensFragment } = await import(
  '../../src/election_guide/rendering/templates/lens-url.mjs'
);
const { compareContext, encodeCompareFragment } = await import(
  '../../src/election_guide/rendering/templates/compare-url.mjs'
);
const { scoreRace } = await import('../../src/election_guide/rendering/templates/lens-score.mjs');

for (const surface of ['guide', 'compare']) {
  test(`${surface}: changing voter district preserves an explicitly selected out-of-district source`, () => {
    const markup = readFileSync(
      new URL(`./fixtures/${surface}-audited-page.html`, import.meta.url),
      'utf8',
    );
    const document = installDom('https://seattleelections.guide/e/wa-2026-primary/');
    document.write(markup);
    const payloadNode = document.querySelector('[data-client-payload]');
    const payloadBytes = payloadNode.textContent;
    const payload = JSON.parse(payloadBytes);
    const selected = ['ld37', 'strn'];
    const encoded =
      surface === 'guide'
        ? encodeLensFragment(
            { mode: 's', categoryCodes: [], sourceCodes: selected },
            lensContext(payload.personalization, payload.data_version),
          )
        : encodeCompareFragment(
            {
              columns: ['ld37', 'Gdem', 'gall'],
              differencesOnly: false,
              contestedOnly: false,
              section: 'all',
            },
            compareContext(payload.personalization, payload.data_version, payload.comparisons, [
              'ld37',
              'Gdem',
              'gall',
            ]),
          );
    assert.equal(encoded.status, 'ok');
    history.replaceState(null, '', `#${encoded.fragment}`);
    if (surface === 'guide') wireGuide(payload);
    else wireComparisons();

    const race = payload.personalization.races.find(
      (race) =>
        payload.ballot_membership.races[race.race_id]?.shared &&
        race.cells.some(
          (cell) => cell.source_code === 'ld37' && Object.keys(cell.allocation).length > 0,
        ),
    );
    assert.ok(race, 'the fixture must contain a shared contest endorsed by LD 37');
    const inputs = structuredClone(race);
    const score = scoreRace(race, selected, payload.personalization);
    assert.ok(score.meterCells.some((cell) => cell.source_code === 'ld37'));
    assert.ok(score.explicitCount > 0);
    const groupIndex = payload.ballot_membership.groups.findIndex(
      (group) => group.id === 'legislative_district',
    );
    assert.ok(groupIndex >= 0);
    const select = document.querySelectorAll('[data-ballot-setup] select')[groupIndex];
    const snapshot = () => {
      const row =
        surface === 'guide'
          ? document.querySelector(`[data-publication-race-id="${race.race_id}"]`)
          : document.querySelector(`[data-comparison-race="${race.race_id}"]`);
      assert.ok(row && !row.hidden, 'the shared contest must remain visible');
      return {
        text: row.textContent.replace(/\s+/g, ' ').trim(),
        data: [...row.querySelectorAll('[data-column-signal], [data-meter-source]')].map(
          (node) => ({ ...node.dataset }),
        ),
        selection: window.location.hash,
      };
    };
    select.value = 'legislative-district-43';
    select.dispatchEvent(new Event('change'));
    const before = snapshot();
    select.value = 'legislative-district-46';
    select.dispatchEvent(new Event('change'));
    assert.deepEqual(
      snapshot(),
      before,
      'source columns, contributing counts, and rendered consensus must remain unchanged',
    );
    assert.deepEqual(
      race,
      inputs,
      'source eligibility, cells, and exact allocations must remain unchanged',
    );
    assert.deepEqual(
      scoreRace(race, selected, payload.personalization),
      score,
      'computed consensus must remain unchanged',
    );
    assert.equal(payloadNode.textContent, payloadBytes);
    assert.match(
      window.location.hash,
      /ld37/,
      'explicit source selection must survive district changes',
    );
  });
}
