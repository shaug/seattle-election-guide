import assert from 'node:assert/strict';
import test from 'node:test';
import {
  availableBallotScopes,
  makeBallotScopeProjector,
} from '../../src/election_guide/rendering/templates/ballot-scopes.mjs';
import { installDom } from './support/dom.mjs';
import { assertModuleGuard } from './support/module-guards.mjs';

test('scope availability uses covered eligibility, including empty-visible scopes', () => {
  const scopes = [
    { value: 'all', contest_ids: ['mayor', 'initiative', 'uncontested'] },
    { value: 'city', contest_ids: ['mayor'] },
    { value: 'state', contest_ids: ['initiative', 'uncontested'] },
  ];
  assert.deepEqual([...availableBallotScopes(scopes, new Set(['initiative']))], ['all', 'state']);
  assert.deepEqual([...availableBallotScopes(scopes, new Set(['uncontested']))], ['all', 'state']);
  assert.deepEqual([...availableBallotScopes(scopes, new Set())], ['all']);
  assert.deepEqual([...availableBallotScopes(scopes, null)], ['all', 'city', 'state']);
});

test('scope projection restores original option groups and preserves select focus', () => {
  const doc = installDom();
  doc.body.innerHTML = `<select><option value="all">All</option>
    <optgroup label="Local"><option value="city">City</option></optgroup>
    <optgroup label="State"><option value="state">State</option></optgroup></select>`;
  const select = doc.querySelector('select');
  const original = [...select.options];
  const groups = [...select.querySelectorAll('optgroup')];
  const project = makeBallotScopeProjector(select);
  select.value = 'city';
  select.focus();
  project(new Set(['all', 'state']));
  assert.equal(select.value, 'all');
  assert.equal(doc.activeElement, select);
  assert.equal(select.querySelectorAll('optgroup').length, 1);
  assert.equal(select.querySelector('optgroup'), groups[1]);
  select.value = 'state';
  project(new Set(['all', 'city', 'state']));
  assert.equal(select.value, 'state');
  assert.equal(doc.activeElement, select);
  assert.deepEqual([...select.options], original);
  assert.deepEqual([...select.querySelectorAll('optgroup')], groups);
});

test('the module keeps client state out of storage', () => {
  assertModuleGuard('ballot-scopes.mjs');
});
