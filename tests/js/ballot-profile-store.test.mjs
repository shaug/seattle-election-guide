import assert from 'node:assert/strict';
import test from 'node:test';
import {
  readBallotProfile,
  writeBallotProfile,
} from '../../src/election_guide/rendering/templates/ballot-profile-store.mjs';
import { assertModuleGuard, moduleNames, moduleSource } from './support/module-guards.mjs';

test('unavailable device storage rejects instead of pretending a save succeeded', async () => {
  await assert.rejects(readBallotProfile('test'));
  await assert.rejects(writeBallotProfile('test', null));
});
test('IndexedDB has one owner and persists only the ballot profile', () => {
  const owners = moduleNames().filter((name) =>
    /\bindexedDB\b/.test(moduleSource(name).replace(/\/\/[^\n]*/g, '')),
  );
  assert.deepEqual(owners, ['ballot-profile-store.mjs']);
  const source = moduleSource('ballot-profile-store.mjs').replace(/\/\/[^\n]*/g, '');
  assert.match(source, /seg-ballot-profile/);
  assert.match(source, /store\.put\(value, electionId\)/);
  assert.doesNotMatch(source, /sourceCodes|address|latitude|longitude/);
});
test('module guard', () => assertModuleGuard('ballot-profile-store.mjs'));
