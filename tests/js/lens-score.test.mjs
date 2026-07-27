import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import test from 'node:test';

import {
  Rational,
  resolveSelection,
  scoreRace,
  scoreSelection,
} from '../../src/election_guide/rendering/templates/lens-score.mjs';

const fixture = JSON.parse(
  readFileSync(fileURLToPath(new URL('./fixtures/lens-parity.json', import.meta.url)), 'utf8'),
);
const personalization = fixture.personalization;

/** The published support map, in the shape the audited engine reports it. */
function supportMap(race) {
  return Object.fromEntries(race.standings.map((item) => [item.candidateId, item.supportPoints]));
}

test('the fixture was generated from the audited engine', () => {
  assert.equal(fixture.schema_version, '1.0');
  assert.ok(fixture.cases.length >= 12, 'every named acceptance case must be present');
  assert.equal(personalization.races.length, 32);
});

test('generated fixtures match the Python scoring engine exactly', () => {
  for (const scenario of fixture.cases) {
    const actual = scoreSelection(personalization, scenario.selection);

    assert.deepEqual(
      actual.sourceCodes,
      scenario.effective_source_codes,
      `${scenario.name}: effective sources diverged`,
    );
    assert.equal(
      actual.races.length,
      scenario.races.length,
      `${scenario.name}: race count diverged`,
    );

    // The published payload is in display order; the audited report is in
    // inventory order, so parity is keyed by race rather than by position.
    const byRaceId = new Map(actual.races.map((race) => [race.raceId, race]));
    for (const expected of scenario.races) {
      const race = byRaceId.get(expected.race_id);
      const where = `${scenario.name} / ${expected.race_id}`;

      assert.ok(race !== undefined, `${where}: race missing from the lens result`);
      assert.equal(race.grade, expected.grade, `${where}: grade diverged`);
      assert.equal(race.isTied, expected.is_tied, `${where}: tie state diverged`);
      assert.equal(
        race.winnerId,
        expected.winner_candidate_id,
        `${where}: winner diverged`,
      );
      assert.deepEqual(
        race.winnerIds,
        [...expected.winner_candidate_ids].sort(),
        `${where}: winner set diverged`,
      );
      assert.equal(
        race.winnerShare,
        expected.winner_share,
        `${where}: exact winning share diverged`,
      );
      assert.deepEqual(
        supportMap(race),
        expected.candidate_support,
        `${where}: exact candidate support diverged`,
      );
      assert.equal(
        race.explicitCount,
        expected.explicit_endorsement_count,
        `${where}: explicit count diverged`,
      );
      assert.equal(
        race.eligibleCount,
        expected.eligible_source_count,
        `${where}: eligible count diverged`,
      );
      assert.equal(
        race.coveredCount,
        expected.source_coverage_count,
        `${where}: coverage count diverged`,
      );
      assert.equal(
        race.noEndorsementCodes.length,
        expected.no_endorsement_count,
        `${where}: no-endorsement count diverged`,
      );
      assert.equal(
        race.missingCodes.length,
        expected.missing_source_count,
        `${where}: missing count diverged`,
      );
    }
  }
});

test('the full selectable panel reproduces the audited published consensus', () => {
  const scenario = fixture.cases.find((item) => item.name === 'full-panel');
  const actual = scoreSelection(personalization, scenario.selection);

  assert.equal(actual.sourceCodes.length, 42, 'every consensus source participates');
  const byRaceId = new Map(actual.races.map((race) => [race.raceId, race]));
  for (const expected of scenario.races) {
    const race = byRaceId.get(expected.race_id);
    assert.equal(race.grade, expected.grade, `${expected.race_id}: grade diverged`);
    assert.equal(race.winnerShare, expected.winner_share, `${expected.race_id}: share diverged`);
  }
});

test('the Seattle Times cannot contribute even when selected', () => {
  const comparisonCodes = personalization.policy.comparison_source_codes;
  assert.ok(comparisonCodes.length > 0, 'the panel must publish a comparison source');

  const resolved = resolveSelection({ sourceCodes: [...comparisonCodes, 'strn'] }, personalization);
  for (const code of comparisonCodes) {
    assert.equal(resolved.sourceCodes.includes(code), false);
    assert.equal(resolved.ignoredCodes.includes(code), true);
  }
});

test('a forced comparison code cannot be scored in any race that publishes one', () => {
  const comparisonCodes = personalization.policy.comparison_source_codes;

  // The payload really does publish scorable comparison cells, so this is the
  // path that matters: a caller assembling codes without resolveSelection.
  const scorable = personalization.races.filter((race) =>
    race.cells.some(
      (cell) =>
        comparisonCodes.includes(cell.source_code) &&
        ['endorsement', 'multi_endorsement'].includes(cell.state),
    ),
  );
  assert.ok(scorable.length > 0, 'the comparison source must publish at least one endorsement');

  for (const race of scorable) {
    const forced = scoreRace(race, comparisonCodes, personalization);

    assert.equal(forced.explicitCount, 0, `${race.race_id}: a comparison cell was scored`);
    assert.equal(forced.eligibleCount, 0, `${race.race_id}: a comparison cell entered eligibility`);
    assert.equal(forced.coveredCount, 0, `${race.race_id}: a comparison cell entered coverage`);
    assert.deepEqual(forced.standings, [], `${race.race_id}: comparison support appeared`);
    assert.equal(forced.winnerShare, null);
    assert.equal(forced.grade, 'Insufficient');
  }
});

test('forcing the comparison code alongside real sources changes nothing', () => {
  const comparisonCodes = personalization.policy.comparison_source_codes;
  const audited = fixture.cases.find((item) => item.name === 'full-panel');
  const clean = scoreSelection(personalization, audited.selection);
  const forced = clean.sourceCodes.concat(comparisonCodes);

  for (const race of personalization.races) {
    const withTimes = scoreRace(race, forced, personalization);
    const without = scoreRace(race, clean.sourceCodes, personalization);

    assert.deepEqual(
      withTimes,
      without,
      `${race.race_id}: the comparison source altered a personalized result`,
    );
  }
});

test('many-to-many and direct-plus-category inclusion never double-count', () => {
  const labor = personalization.categories.find((item) => item.code === 'Glab');
  const member = labor.member_source_codes[0];

  const viaCategory = resolveSelection({ categoryCodes: ['Glab'] }, personalization);
  const viaBoth = resolveSelection(
    { categoryCodes: ['Glab', 'Gdem'], sourceCodes: [member, member] },
    personalization,
  );

  assert.equal(new Set(viaCategory.sourceCodes).size, viaCategory.sourceCodes.length);
  assert.equal(new Set(viaBoth.sourceCodes).size, viaBoth.sourceCodes.length);
  assert.ok(viaCategory.sourceCodes.includes(member));

  const overlapping = personalization.sources.filter(
    (item) => item.selection_category_ids.length > 1 && item.selectable,
  );
  assert.ok(overlapping.length > 0, 'the panel must exercise many-to-many membership');

  const scored = scoreSelection(personalization, {
    categoryCodes: ['Glab', 'Gdem'],
    sourceCodes: [member],
  });
  for (const race of scored.races) {
    assert.ok(
      race.explicitCount <= race.eligibleCount,
      `${race.raceId}: a source contributed more than once`,
    );
  }
});

test('an ineligible district source cannot reach another district race', () => {
  const scenario = fixture.cases.find((item) => item.name === 'wrong-district');
  const selected = scenario.selection.sourceCodes;
  const actual = scoreSelection(personalization, scenario.selection);

  const contributing = actual.races.filter((race) => race.explicitCount > 0);
  assert.ok(contributing.length > 0, 'the district sources must score their own races');
  assert.ok(
    contributing.length < actual.races.length,
    'district sources must not reach every race',
  );

  for (const published of personalization.races) {
    const eligible = new Set(published.eligible_source_codes);
    const ineligible = selected.filter((code) => !eligible.has(code));
    if (ineligible.length === 0) continue;

    // Selecting only the ineligible codes for this race must score nothing at all.
    const forced = scoreRace(published, ineligible, personalization);
    assert.equal(
      forced.explicitCount,
      0,
      `${published.race_id}: ${ineligible.join(',')} contributed to another district`,
    );
    assert.deepEqual(forced.standings, [], `${published.race_id}: ineligible support appeared`);
    assert.equal(forced.grade, 'Insufficient');
    assert.equal(forced.eligibleCount, 0);
  }
});

test('an unknown or nonselectable code is ignored rather than scored', () => {
  const resolved = resolveSelection(
    { categoryCodes: ['Gzzz', 'Gcmp'], sourceCodes: ['zzzz', 'Glab'] },
    personalization,
  );

  assert.deepEqual(resolved.sourceCodes, []);
  assert.deepEqual(resolved.ignoredCodes, ['Gcmp', 'Glab', 'Gzzz', 'zzzz']);
});

test('shares are exact rationals, never floating point', () => {
  const third = new Rational(1n, 3n);
  const twoThirds = new Rational(2n, 3n);

  assert.equal(third.add(third).add(third).toString(), '1');
  assert.equal(third.add(twoThirds).toString(), '1');
  assert.equal(new Rational(2n, 6n).toString(), '1/3', 'rationals are always reduced');
  assert.equal(Rational.parse('1/2').divide(Rational.parse('3/2')).toString(), '1/3');

  // 1/3 + 1/3 + 1/3 is exactly 1 here, where 0.1 + 0.2 !== 0.3 in binary floating point.
  assert.equal(third.add(third).add(third).compare(new Rational(1n)), 0);
  assert.notEqual(0.1 + 0.2, 0.3);
});

test('an exact tie is resolved before any ordinary grade', () => {
  const tied = fixture.cases
    .flatMap((scenario) => scenario.races)
    .filter((race) => race.is_tied);
  assert.ok(tied.length > 0, 'the fixture must exercise tie resolution');

  for (const race of tied) {
    assert.equal(race.grade, 'TIED');
    assert.equal(race.winner_candidate_id, null);
    assert.ok(race.winner_candidate_ids.length > 1);
  }
});

test('an insufficient panel is resolved before any ordinary grade', () => {
  const empty = fixture.cases.find((item) => item.name === 'empty');
  const actual = scoreSelection(personalization, empty.selection);

  assert.deepEqual(actual.sourceCodes, []);
  for (const race of actual.races) {
    assert.equal(race.grade, 'Insufficient');
    assert.equal(race.explicitCount, 0);
    assert.equal(race.winnerShare, null);
    assert.equal(race.winnerId, null);
  }
});

test('one source cannot reach the explicit-source floor', () => {
  const single = fixture.cases.find((item) => item.name === 'single-source');
  const actual = scoreSelection(personalization, single.selection);

  assert.equal(actual.sourceCodes.length, 1);
  assert.ok(personalization.scoring.minimum_explicit_sources > 1);
  for (const race of actual.races) {
    assert.equal(race.grade, 'Insufficient');
  }
});

test('the engine has no DOM or network dependency', () => {
  const source = readFileSync(
    fileURLToPath(
      new URL('../../src/election_guide/rendering/templates/lens-score.mjs', import.meta.url),
    ),
    'utf8',
  );
  const code = source.replace(/\/\*[\s\S]*?\*\//g, '').replace(/(^|\s)\/\/.*$/gm, '');

  for (const forbidden of [
    'window',
    'document',
    'location',
    'fetch',
    'XMLHttpRequest',
    'localStorage',
    'sessionStorage',
    'navigator',
    'require',
    'process',
  ]) {
    assert.equal(
      new RegExp(`\\b${forbidden}\\b`).test(code),
      false,
      `${forbidden} would make the engine environment-dependent`,
    );
  }
});

test('the engine mutates neither the payload nor the selection', () => {
  const before = JSON.stringify(personalization);
  const selection = { categoryCodes: ['Glab'], sourceCodes: ['strn'] };
  const selectionBefore = JSON.stringify(selection);

  scoreSelection(personalization, selection);

  assert.equal(JSON.stringify(personalization), before);
  assert.equal(JSON.stringify(selection), selectionBefore);
});
