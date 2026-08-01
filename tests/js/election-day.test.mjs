import assert from 'node:assert/strict';
import test from 'node:test';

import { electionDayStatement } from '../../src/election_guide/rendering/templates/election-day.mjs';

const NAMES = { full: 'Tuesday, August 4, 2026', short: 'Tuesday, August 4' };

test('far from the election the server rendering already stands', () => {
  const statement = electionDayStatement(30, NAMES);
  assert.equal(statement.tone, 'default');
  // Null means "leave the DOM alone": the tense-neutral statement the server
  // wrote is correct, so a reader with no JavaScript sees the same thing.
  assert.equal(statement.html, null);
  assert.equal(statement.action, true);
});

test('inside the escalation window the wording counts down', () => {
  const statement = electionDayStatement(3, NAMES);
  assert.equal(statement.tone, 'soon');
  assert.match(statement.html, /Election day is in 3 days/);
  assert.match(statement.html, /Tuesday, August 4/);
});

test('tomorrow reads as a word, not a number', () => {
  // Intl.RelativeTimeFormat with numeric:'auto' is why this is not "in 1 day".
  assert.match(electionDayStatement(1, NAMES).html, /Election day is tomorrow/);
});

test('the boundary of the escalation window is inclusive', () => {
  assert.equal(electionDayStatement(7, NAMES).tone, 'soon');
  assert.equal(electionDayStatement(8, NAMES).tone, 'default');
});

test('election day itself escalates its words, not its surface', () => {
  const statement = electionDayStatement(0, NAMES);
  // Same tone as the days before it: DESIGN.md's differ/amber family already
  // means "attention", and a third colour tier would have amended the table.
  assert.equal(statement.tone, 'soon');
  assert.match(statement.html, /Election day is today/);
  assert.match(statement.html, /ballots due by 8pm/);
});

test('after the election the banner changes tense instead of vanishing', () => {
  const statement = electionDayStatement(-1, NAMES);
  assert.equal(statement.tone, 'past');
  assert.match(statement.html, /This election was held Tuesday, August 4, 2026\./);
  // The call to action goes; the statement of which election this is stays, so
  // an archived guide is never thinner than the live page about its own
  // identity. This slot is where results land later.
  assert.equal(statement.action, false);
  assert.doesNotMatch(statement.html, /Election day is/);
});

test('a long-past election reads the same as a just-past one', () => {
  assert.equal(electionDayStatement(-900, NAMES).tone, 'past');
  assert.equal(electionDayStatement(-900, NAMES).action, false);
});
