// Slot 4 of the shell grammar (issue 192): the election-day banner's only moving
// part. The server renders a tense-neutral statement ("Election day: Tuesday,
// August 4, 2026") because every published guide is a frozen file that stays at
// its address after the election and cannot know today's date. This escalates
// that statement as the date nears, then rewrites it in the past tense once the
// election has happened, so an archived guide stops issuing a call to action
// while still saying which election it is.
//
// Issue #285 adds one more transition, still driven by the reader's own clock
// rather than any live count: once election day has passed, if the calendar's
// certification date has not yet been reached, the banner reads as "counting"
// instead of falling straight to the past rewrite. The certified state itself
// needs no client logic at all -- `shell.election_day_banner_html` renders it
// directly, server-side, once a certified or amended results file exists,
// because that fact does not depend on today's date the way "how far from
// election day" does.
//
// Issue #286 reuses this exact same trigger for a second surface: a
// candidate race card's own counting note. It is not a second banner and
// carries no election-day/certification-date attributes of its own --
// `wireRaceResultsCounting` below reads the banner's already-rendered
// attributes and only ever toggles each note's `hidden` attribute, because
// every race card on one page shares the one election-wide window.
//
// `Intl.RelativeTimeFormat` is the platform's own friendly-date formatter. This
// project ships hand-written ES modules with no bundler, and should not gain a
// dependency for a job the browser already does.

// Inside this many days the banner escalates to the attention surface. The
// differ/amber family already means "attention" in DESIGN.md § Color, so no new
// hue is introduced; past this window the banner stays on the neutral surface.
const ESCALATION_WINDOW_DAYS = 7;

// Every off-site link this module writes opens in a new tab and keeps the
// referrer, matching `shell.EXTERNAL_LINK_ATTRIBUTES` -- the site's one rule
// for links that leave it, so a reader checking the count keeps their place
// in the guide.
const EXTERNAL_LINK_ATTRIBUTES = ' target="_blank" rel="noopener"';

/**
 * @param {string} iso
 * @param {Date} now
 * @returns {number}
 */
function calendarDaysUntil(iso, now) {
  // Compare calendar days in local time, not elapsed hours: "today" must mean
  // the reader's today, and a date 20 hours away is still tomorrow.
  const [year, month, day] = iso.split('-').map(Number);
  const target = new Date(year, month - 1, day);
  const today = new Date(now.getFullYear(), now.getMonth(), now.getDate());
  // `getTime()` rather than subtracting the dates directly: identical at
  // runtime (subtraction calls `valueOf`), but the arithmetic is declared.
  return Math.round((target.getTime() - today.getTime()) / 86400000);
}

/**
 * The banner's tone and copy for a given distance from election day.
 *
 * @param {number} daysUntil
 * @param {{ full: string, short: string }} phrasing
 * @param {{ daysUntil: number, full: string, resultsHref: string }|null} [counting]
 *   The certification window, when the page carries a calendar certification
 *   date and no results file has been ingested yet (`null` otherwise, e.g. an
 *   immutable older bundle or an election the calendar has not scheduled
 *   certification for). `daysUntil` is the reader's distance from that date,
 *   computed the same way as the election-day `daysUntil` above.
 * @returns {{ tone: 'past'|'soon'|'default'|'counting', html: string|null, action: boolean }}
 */
export function electionDayStatement(daysUntil, { full, short }, counting = null) {
  if (daysUntil < 0) {
    // The certification date has not yet been reached: ballots are still
    // being counted, and the site links out rather than tracking them
    // (docs/RESULTS.md, "The results lifecycle"). Once that date passes with
    // still no results file, this falls through to the past rewrite below --
    // never a stale counting promise.
    if (counting !== null && counting.daysUntil >= 0) {
      return {
        tone: 'counting',
        html:
          '<b>Ballots are being counted</b> &mdash; see the count at ' +
          `<a href="${counting.resultsHref}"${EXTERNAL_LINK_ATTRIBUTES}>King County Elections</a>.` +
          `<br>Results certify ${counting.full}.`,
        action: false,
      };
    }
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
  // Absent entirely once results are certified (`shell.election_day_banner_html`
  // renders that state directly): nothing here needs to run, since a certified
  // fact does not change with the reader's clock.
  if (!banner) return;
  // The three attributes are written together by the banner's Jinja template,
  // so a rendered banner always carries all of them. Asserted rather than
  // coerced: a banner missing them is a template defect that should keep
  // throwing here, not quietly format the string "null".
  const certificationDate = banner.getAttribute('data-election-certification-date');
  const counting =
    certificationDate === null
      ? null
      : {
          daysUntil: calendarDaysUntil(certificationDate, now),
          full: /** @type {string} */ (
            banner.getAttribute('data-election-certification-date-full')
          ),
          resultsHref: /** @type {string} */ (banner.getAttribute('data-election-results-href')),
        };
  const statement = electionDayStatement(
    calendarDaysUntil(/** @type {string} */ (banner.getAttribute('data-election-day')), now),
    {
      full: /** @type {string} */ (banner.getAttribute('data-election-day-full')),
      short: /** @type {string} */ (banner.getAttribute('data-election-day-short')),
    },
    counting,
  );

  banner.classList.remove('election-day-soon', 'election-day-past', 'election-day-counting');
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

/**
 * Reveal every candidate race card's counting note (issue #286) once the
 * reader's own clock falls inside the same counting window `wireElectionDay`
 * computes for the banner above -- election day passed, the calendar's
 * certification date not yet reached (docs/RESULTS.md, Rendering § Race
 * cards). The server renders each note's full text unconditionally inside a
 * `hidden` wrapper only when it is possibly correct (no results file yet, a
 * known certification date, a candidate race -- `guide.html.j2`), so this
 * never injects text, only decides whether today says the window is open.
 * One election per guide page, so one decision reveals every card's note.
 *
 * @param {Date} [now]
 */
export function wireRaceResultsCounting(now = new Date()) {
  const slots = document.querySelectorAll('[data-race-counting]');
  if (slots.length === 0) return;
  // The banner's own attributes (`election_day_banner_html`), not a second
  // copy on every card: `data-election-certification-date` is present only
  // when the calendar knows a certification date and no results file has
  // rendered the certified banner state instead -- exactly the two facts
  // `guide.html.j2` already checked before rendering any note to reveal.
  const banner = document.querySelector('[data-election-day]');
  const electionDay = banner?.getAttribute('data-election-day') ?? null;
  const certificationDate = banner?.getAttribute('data-election-certification-date') ?? null;
  if (electionDay === null || certificationDate === null) return;
  const isCounting =
    calendarDaysUntil(electionDay, now) < 0 && calendarDaysUntil(certificationDate, now) >= 0;
  if (!isCounting) return;
  for (const slot of slots) /** @type {HTMLElement} */ (slot).hidden = false;
}
