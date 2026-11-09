import assert from 'node:assert/strict';
import test from 'node:test';
import {
  ballotQuery,
  readContestedOnly,
  readPrecinctSelection,
  resolvePrecinct,
  supportedPrecinctContract,
  withContestedOnly,
  withPrecinct,
} from '../../src/election_guide/rendering/templates/precinct-ballot.mjs';
import { assertModuleGuard } from './support/module-guards.mjs';

const contract = {
  schema_version: '1.0',
  election_id: 'wa-2026-general',
  mapping_hash: 'checked',
  precincts: [{ code: '1279', name: 'SEA 46-1279', contest_ids: ['measure', 'candidate'] }],
};
test('precinct query admits only one explicit reviewed choice', () => {
  assert.equal(readPrecinctSelection('', contract).status, 'absent');
  assert.equal(readPrecinctSelection('?precinct=all', contract).status, 'all');
  assert.equal(readPrecinctSelection('?precinct=1279', contract).code, '1279');
  for (const query of ['?precinct=unknown', '?precinct=', '?precinct=1279&precinct=all'])
    assert.equal(readPrecinctSelection(query, contract).status, 'invalid');
  assert.deepEqual([...resolvePrecinct(contract, '1279').contestIds], ['measure', 'candidate']);
  assert.equal(resolvePrecinct(contract, 'unknown').status, 'invalid');
  assert.equal(resolvePrecinct(contract, null).contestIds, null);
  assert.equal(withPrecinct('?view=compact', '1279'), '?view=compact&precinct=1279');
  assert.equal(withPrecinct('?precinct=1279', null), '?precinct=all');
});
test('precinct resolution is pure', () => assertModuleGuard('precinct-ballot.mjs'));

test('race mode distinguishes a general default from an explicit override', () => {
  assert.equal(readContestedOnly('', true), true);
  assert.equal(readContestedOnly('?races=all', true), false);
  assert.equal(readContestedOnly('?races=contested', true), true);
  for (const query of ['?races=unknown', '?races=', '?races=all&races=contested'])
    assert.equal(readContestedOnly(query, true), true);
  assert.equal(readContestedOnly(''), false);
  assert.equal(withContestedOnly('?precinct=2502', false, true), '?precinct=2502&races=all');
  assert.equal(withContestedOnly('?precinct=2502&races=all', true, true), '?precinct=2502');
  assert.equal(withContestedOnly('', true), '?races=contested');
  assert.equal(withContestedOnly('?races=contested', false), '');
});

test('ballot navigation carries only its owned keys and retains explicit invalid choices', () => {
  assert.equal(
    ballotQuery('?view=compact&precinct=2502&races=all&unrelated=1'),
    '?precinct=2502&races=all',
  );
  assert.equal(
    ballotQuery('?precinct=2502&precinct=all&races=all&races=contested'),
    '?precinct=2502&precinct=all&races=all&races=contested',
  );
  assert.equal(ballotQuery('?view=compact'), '');
});

const primary = {
  schema_version: '1.0',
  election_id: 'wa-2026-primary',
  mapping_hash: 'b'.repeat(64),
  address_lookup: null,
  supplement: {
    schema_version: '1.0',
    election_id: 'wa-2026-primary',
    mapping_hash: 'b'.repeat(64),
    source_git_commit: 'a'.repeat(40),
    artifact_sha256: 'c'.repeat(64),
  },
};
test('Primary capability refuses future or incomplete identity without enabling General address context', () => {
  assert.equal(supportedPrecinctContract(primary), true);
  const cases = [
    { ...primary, schema_version: '2.0' },
    { ...primary, supplement: { ...primary.supplement, schema_version: '2.0' } },
    { ...primary, supplement: null },
    { ...primary, supplement: { ...primary.supplement, election_id: 'wa-2026-general' } },
    { ...primary, supplement: { ...primary.supplement, mapping_hash: 'd'.repeat(64) } },
    { ...primary, supplement: { ...primary.supplement, source_git_commit: 'bad' } },
    { ...primary, address_lookup: { election_id: 'wa-2026-general' } },
  ];
  for (const value of cases) assert.equal(supportedPrecinctContract(value), false);
});
