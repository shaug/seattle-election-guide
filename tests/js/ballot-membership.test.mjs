import assert from 'node:assert/strict';
import test from 'node:test';
import {
  admitProfile,
  resolveBallot,
} from '../../src/election_guide/rendering/templates/ballot-membership.mjs';
import { assertModuleGuard } from './support/module-guards.mjs';

export const contract = {
  election_id: 'test-election',
  groups: [
    {
      id: 'leg',
      label: 'Legislative district',
      mode: 'district',
      options: [
        { id: 'ld1', label: '1' },
        { id: 'ld2', label: '2' },
      ],
    },
    { id: 'court', label: 'Court', mode: 'membership', options: [{ id: 'court', label: 'Court' }] },
  ],
  races: {
    shared: { shared: true, group_id: null, jurisdiction_id: 'state' },
    one: { shared: false, group_id: 'leg', jurisdiction_id: 'ld1' },
    two: { shared: false, group_id: 'leg', jurisdiction_id: 'ld2' },
    court: { shared: false, group_id: 'court', jurisdiction_id: 'court' },
  },
};
test('partial profiles retain uncertain decisions and independent district questions', () => {
  const result = resolveBallot(contract, { leg: 'ld1' });
  assert.equal(result.complete, false);
  assert.deepEqual(result.membership, {
    shared: 'applicable',
    one: 'applicable',
    two: 'inapplicable',
    court: 'unresolved',
  });
});
test('unlisted districts remain unresolved and never reorder input', () => {
  const result = resolveBallot(contract, { leg: 'other', court: 'no' });
  assert.equal(result.complete, false);
  assert.deepEqual(result.membership, {
    shared: 'applicable',
    one: 'unresolved',
    two: 'unresolved',
    court: 'inapplicable',
  });
  const reversed = {
    ...contract,
    races: Object.fromEntries(Object.entries(contract.races).reverse()),
  };
  assert.deepEqual(
    resolveBallot(reversed, { leg: 'ld1', court: 'yes' }).membership,
    resolveBallot(contract, { leg: 'ld1', court: 'yes' }).membership,
  );
});
test('invalid values and wrong-group identifiers stay unresolved', () => {
  assert.deepEqual(admitProfile(contract, { leg: 'court', court: 'ld1', junk: 'ld1' }), {});
  assert.equal(resolveBallot(contract, { leg: 'court' }).membership.one, 'unresolved');
});
test('missing rules fail open as unresolved at the consumer, never from endorsement data', () => {
  assert.equal(resolveBallot(contract, {}).membership.shared, 'applicable');
  assert.equal(resolveBallot(contract, {}).membership.missing, undefined);
});
test('module is pure', () => assertModuleGuard('ballot-membership.mjs'));

test('named districts without contests are complete; reviewed outside-target rules stay excluded', () => {
  const catalog = structuredClone(contract);
  catalog.groups[0].options.push({ id: 'ld3', label: '3 (no current contest)' });
  catalog.races.outside = {
    shared: false,
    outside_target: true,
    group_id: null,
    jurisdiction_id: 'ld4',
  };
  const result = resolveBallot(catalog, { leg: 'ld3', court: 'no' });
  assert.equal(result.complete, true);
  assert.equal(result.membership.one, 'inapplicable');
  assert.equal(result.membership.two, 'inapplicable');
  assert.equal(result.membership.outside, 'inapplicable');
  assert.equal(result.membership.shared, 'applicable');
});
