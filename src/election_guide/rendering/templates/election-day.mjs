// Slot 4 of the shell grammar (issue 192): the election-day banner's only moving
// part. The server renders a tense-neutral statement ("Election day: Tuesday,
// August 4, 2026") because every published guide is a frozen file that stays at
// its address after the election and cannot know today's date. This escalates
// that statement as the date nears, then rewrites it in the past tense once the
// election has happened, so an archived guide stops issuing a call to action
// while still saying which election it is.
//
// `Intl.RelativeTimeFormat` is the platform's own friendly-date formatter. This
// project ships hand-written ES modules with no bundler, and should not gain a
// dependency for a job the browser already does.

// Inside this many days the banner escalates to the attention surface. The
// differ/amber family already means "attention" in DESIGN.md § Color, so no new
// hue is introduced; past this window the banner stays on the neutral surface.
const ESCALATION_WINDOW_DAYS = 7;

/**
 * @param {string} electionIso
 * @param {Date} now
 * @returns {number}
 */
function calendarDaysUntil(electionIso, now) {
  // Compare calendar days in local time, not elapsed hours: "today" must mean
  // the reader's today, and an election 20 hours away is still tomorrow.
  const [year, month, day] = electionIso.split('-').map(Number);
  const election = new Date(year, month - 1, day);
  const today = new Date(now.getFullYear(), now.getMonth(), now.getDate());
  // `getTime()` rather than subtracting the dates directly: identical at
  // runtime (subtraction calls `valueOf`), but the arithmetic is declared.
  return Math.round((election.getTime() - today.getTime()) / 86400000);
}

/**
 * The banner's tone and copy for a given distance from election day.
 *
 * @param {number} daysUntil
 * @param {{ full: string, short: string }} phrasing
 * @returns {{ tone: 'past'|'soon'|'default', html: string|null, action: boolean }}
 */
export function electionDayStatement(daysUntil, { full, short }) {
  if (daysUntil < 0) {
    return { tone: 'past', html: `<b>This election was held ${full}.</b>`, action: false };
  }
  if (daysUntil === 0) {
    return {
      tone: 'soon',
      html: '<b>Election day is today</b> &mdash; ballots due by 8pm',
      action: true,
    };
  }
  if (daysUntil <= ESCALATION_WINDOW_DAYS) {
    const relative = new Intl.RelativeTimeFormat('en', { numeric: 'auto' }).format(
      daysUntil,
      'day',
    );
    return {
      tone: 'soon',
      html: `<b>Election day is ${relative}</b> &mdash; ${short}`,
      action: true,
    };
  }
  // Far out: the server's tense-neutral rendering is already right.
  return { tone: 'default', html: null, action: true };
}

/** @param {Date} [now] */
export function wireElectionDay(now = new Date()) {
  const banner = document.querySelector('[data-election-day]');
  if (!banner) return;
  // The three attributes are written together by the banner's Jinja template,
  // so a rendered banner always carries all of them. Asserted rather than
  // coerced: a banner missing them is a template defect that should keep
  // throwing here, not quietly format the string "null".
  const statement = electionDayStatement(
    calendarDaysUntil(/** @type {string} */ (banner.getAttribute('data-election-day')), now),
    {
      full: /** @type {string} */ (banner.getAttribute('data-election-day-full')),
      short: /** @type {string} */ (banner.getAttribute('data-election-day-short')),
    },
  );

  banner.classList.remove('election-day-soon', 'election-day-past');
  if (statement.tone !== 'default') banner.classList.add(`election-day-${statement.tone}`);

  if (statement.html !== null) {
    const when = banner.querySelector('[data-election-day-when]');
    if (when) when.innerHTML = statement.html;
  }
  if (!statement.action) {
    banner.querySelector('.election-day-action')?.remove();
    banner.querySelector('.election-day-separator')?.remove();
  }
}
