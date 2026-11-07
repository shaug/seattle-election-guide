import assert from 'node:assert/strict';
import test from 'node:test';
import { installDom } from './support/dom.mjs';
import { assertModuleGuard } from './support/module-guards.mjs';

// The DOM first, then the module under test: see dom.mjs.
const document = installDom();
const { electionDayStatement, wireElectionDay, wirePreliminaryRecency } = await import(
  '../../src/election_guide/rendering/templates/election-day.mjs'
);

const NAMES = { full: 'Tuesday, August 4, 2026', short: 'Tuesday, August 4' };
const RESULTS_HREF = 'https://kingcounty.gov/en/dept/elections/results';
const COUNTING = { daysUntil: 5, full: 'August 19, 2026', resultsHref: RESULTS_HREF };

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

test('past election day with no counting info still falls back to the past rewrite', () => {
  // `null` is what a banner missing `data-election-certification-date` reads
  // as (an immutable older bundle, or an election the calendar has not
  // scheduled certification for) -- exactly the shipped #192 behavior.
  const statement = electionDayStatement(-1, NAMES, null);
  assert.equal(statement.tone, 'past');
  assert.match(statement.html, /This election was held/);
});

test('past election day but before certification reads as counting', () => {
  const statement = electionDayStatement(-1, NAMES, COUNTING);
  assert.equal(statement.tone, 'counting');
  assert.match(statement.html, /Ballots are being counted/);
  assert.match(statement.html, /see the count at/);
  assert.match(statement.html, new RegExp(`href="${RESULTS_HREF}"`));
  assert.match(statement.html, />King County Elections<\/a>\./);
  assert.match(statement.html, /Results certify August 19, 2026\./);
  // No further call to action: the counting sentence names its own link.
  assert.equal(statement.action, false);
});

test('certification day itself still reads as counting', () => {
  // Symmetric with election day itself still reading as "soon", not "past":
  // the certification date has not been reached until the day is over.
  assert.equal(electionDayStatement(-1, NAMES, { ...COUNTING, daysUntil: 0 }).tone, 'counting');
});

test('once certification day has passed, counting falls back to the past rewrite', () => {
  // Never a stale counting promise once the calendar's own certification date
  // has come and gone with still no results file.
  const statement = electionDayStatement(-1, NAMES, { ...COUNTING, daysUntil: -1 });
  assert.equal(statement.tone, 'past');
  assert.match(statement.html, /This election was held Tuesday, August 4, 2026\./);
  assert.doesNotMatch(statement.html, /counted/);
});

test('counting info is irrelevant before election day', () => {
  // The counting state only ever follows the past-rewrite branch; a reader
  // arriving before election day sees the ordinary escalation regardless of
  // what the certification window looks like.
  const statement = electionDayStatement(3, NAMES, COUNTING);
  assert.equal(statement.tone, 'soon');
  assert.match(statement.html, /Election day is in 3 days/);
});

/** @param {string} html */
function installBanner(html) {
  document.body.innerHTML = html;
}

const COUNTING_ELIGIBLE_BANNER =
  '<p class="election-day" data-election-day="2026-08-04"' +
  ' data-election-day-full="Tuesday, August 4, 2026"' +
  ' data-election-day-short="Tuesday, August 4"' +
  ' data-election-certification-date="2026-08-19"' +
  ' data-election-certification-date-full="August 19, 2026"' +
  ` data-election-results-href="${RESULTS_HREF}">` +
  '<span class="election-day-when" data-election-day-when>' +
  '<b>Election day:</b> Tuesday, August 4, 2026</span>' +
  '<span class="election-day-separator" aria-hidden="true"> · </span>' +
  '<a class="election-day-action" href="https://kingcounty.gov/en/dept/elections/how-to-vote"' +
  ' target="_blank" rel="noopener">How to vote</a>' +
  '</p>';

test('wireElectionDay renders the counting state between election day and certification', () => {
  installBanner(COUNTING_ELIGIBLE_BANNER);
  wireElectionDay(new Date(2026, 7, 10)); // August 10, 2026: past election day, before certification

  const banner = /** @type {Element} */ (document.querySelector('[data-election-day]'));
  assert.equal(banner.classList.contains('election-day-counting'), true);
  const when = /** @type {Element} */ (document.querySelector('[data-election-day-when]'));
  assert.match(/** @type {string} */ (when.innerHTML), /Ballots are being counted/);
  assert.match(/** @type {string} */ (when.innerHTML), /Results certify August 19, 2026\./);
  // The counting sentence names its own link; the pre-election "How to vote"
  // action and its separator go, exactly as they already do for the past
  // rewrite (action: false).
  assert.equal(document.querySelector('.election-day-action'), null);
  assert.equal(document.querySelector('.election-day-separator'), null);
});

test('wireElectionDay falls back to the past rewrite once certification has passed', () => {
  installBanner(COUNTING_ELIGIBLE_BANNER);
  wireElectionDay(new Date(2026, 7, 25)); // August 25, 2026: past the certification date

  const banner = /** @type {Element} */ (document.querySelector('[data-election-day]'));
  assert.equal(banner.classList.contains('election-day-past'), true);
  assert.equal(banner.classList.contains('election-day-counting'), false);
  const when = /** @type {Element} */ (document.querySelector('[data-election-day-when]'));
  assert.match(
    /** @type {string} */ (when.innerHTML),
    /This election was held Tuesday, August 4, 2026\./,
  );
});

test('wireElectionDay leaves a certified banner alone', () => {
  // `shell.election_day_banner_html` renders the certified state directly and
  // drops `data-election-day` entirely, so the script has nothing to find.
  installBanner(
    '<p class="election-day election-day-past">' +
      '<span class="election-day-when"><b>This election is complete.</b>' +
      '<br>Results were certified August 19, 2026.</span></p>',
  );
  assert.doesNotThrow(() => wireElectionDay(new Date(2026, 7, 25)));
  assert.equal(document.querySelector('[data-election-day]'), null);
  assert.match(/** @type {string} */ (document.body.innerHTML), /This election is complete\./);
});

test('the module keeps client state out of storage', () => {
  assertModuleGuard('election-day.mjs');
});

const PRELIMINARY_RECENCY = {
  race_id: 'race-a',
  checked_at: '2026-11-04T05:00:00Z',
  checked_at_label: 'Nov 3, 9:00:00 p.m. PST',
  refresh_unavailable: false,
  stale_after_seconds: 86400,
};

function installPreliminaryTarget() {
  installBanner(
    '<p>Unofficial · Nov 3, 8:00 p.m. PST</p>' +
      '<span data-preliminary-recency="race-a">Last checked Nov 3, 9:00:00 p.m. PST</span>',
  );
}

test('a preliminary count ages by its check clock without changing its publisher timestamp', () => {
  installPreliminaryTarget();
  wirePreliminaryRecency([PRELIMINARY_RECENCY], new Date('2026-11-05T05:00:00Z'));
  assert.match(document.body.textContent, /Stale · last checked Nov 3, 9:00:00 p.m. PST/);
  assert.match(document.body.textContent, /Unofficial · Nov 3, 8:00 p.m. PST/);
});

test('a failed refresh stays unavailable instead of becoming a fresh count', () => {
  installPreliminaryTarget();
  wirePreliminaryRecency(
    [{ ...PRELIMINARY_RECENCY, refresh_unavailable: true }],
    new Date('2026-11-04T06:00:00Z'),
  );
  assert.match(document.body.textContent, /Refresh unavailable · last checked/);
});

test('an untrusted reader clock cannot make a future preliminary check look fresh', () => {
  installPreliminaryTarget();
  wirePreliminaryRecency([PRELIMINARY_RECENCY], new Date('2026-11-04T04:00:00Z'));
  assert.match(document.body.textContent, /Check time unavailable/);
});

test('a failed-refresh flag cannot bypass invalid preliminary check metadata', () => {
  for (const invalid of [
    { checked_at: 'invalid' },
    { stale_after_seconds: 0 },
    { checked_at_label: '' },
  ]) {
    installPreliminaryTarget();
    wirePreliminaryRecency(
      [{ ...PRELIMINARY_RECENCY, refresh_unavailable: true, ...invalid }],
      new Date('2026-11-04T06:00:00Z'),
    );
    const element = document.querySelector('[data-preliminary-recency]');
    assert.ok(element);
    assert.equal(element.textContent, 'Check time unavailable', JSON.stringify(invalid));
  }
});

test('preliminary recency uses admitted values and only reads target identity from markup', () => {
  installBanner(
    '<span data-preliminary-recency="race-a" data-preliminary-check-at="2099-01-01" data-preliminary-refresh-failed="true">Audited baseline</span>',
  );
  wirePreliminaryRecency(
    [
      {
        race_id: 'race-a',
        checked_at: '2026-11-04T05:00:00Z',
        checked_at_label: 'Nov 3, 9:00:00 p.m. PST',
        refresh_unavailable: false,
        stale_after_seconds: 86400,
      },
    ],
    new Date('2026-11-04T06:00:00Z'),
  );
  assert.equal(document.body.textContent, 'Last checked Nov 3, 9:00:00 p.m. PST');
});

test('an unusable page payload leaves preliminary freshness on its audited baseline', async () => {
  for (const name of ['guide-entry.mjs', 'race-entry.mjs']) {
    installBanner(
      '<span data-preliminary-recency="race-a" data-preliminary-check-at="2026-11-04T05:00:00Z" ' +
        'data-preliminary-checked-label="Nov 3, 9:00:00 p.m. PST" data-preliminary-stale-after="86400">Audited baseline</span>' +
        '<script type="application/json" data-client-payload>{"schema_version":"unsupported"}</script>',
    );
    const { boot } = await import(`../../src/election_guide/rendering/templates/${name}`);
    assert.throws(() => boot(), /unusable client payload/);
    assert.equal(
      document.querySelector('[data-preliminary-recency]')?.textContent,
      'Audited baseline',
      name,
    );
  }
});
