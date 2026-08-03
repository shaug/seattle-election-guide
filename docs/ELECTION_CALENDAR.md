# Election operations calendar

Washington's election cadence is statutory and predictable. The recurring risk
to this project has never been a bad build; it is missing a data-gathering
window that cannot be reopened. `config/calendar/elections.yaml` makes that
cycle a tracked artifact rather than something remembered.

The calendar is a planning artifact. It is not a site feature, and nothing in
it is rendered today.

## The cadence

Washington holds special elections on the second Tuesday in February and the
fourth Tuesday in April, its primary on the first Tuesday in August, and its
general election on the first Tuesday after the first Monday in November. Those
dates are fixed in statute, which is why elections can be declared here years
ahead of the ballot that fills them.

The dates that matter to this project hang off election day at known distances.
Ballots are mailed no later than eighteen days before it. County canvassing
boards certify roughly three weeks after a general election and about two weeks
after a primary or special. Candidate filing week falls in May, and it settles
the field for both the August primary and the November general.

## What the calendar declares

An election declares its identity — a stable ID, its type, its scope, its date,
and its state. A milestone declares which election it belongs to, a stable ID
unique within that election, a `kind` from a closed vocabulary, and
`offset_days` from its election's date. A milestone may also name the `workflow`
that carries it out and a `reference` document that explains how.

```yaml
- election_id: wa-2026-general
  id: initialize-election
  kind: initialize_election
  offset_days: -75
  workflow: election init
  reference: docs/ELECTION_INITIALIZATION.md
```

`workflow` names a real pipeline command — `election init`,
`inventory import-initialized`, `sources snapshot`, `collect refresh`,
`release build`, `evidence capture` — so a milestone hands its work to
something that exists. `tests/test_calendar.py` resolves every declared
workflow against the CLI and every reference against the repository, so a
renamed command or a moved document fails the suite rather than the cycle.

## How offsets are chosen

Offsets are counted from election day, which is why the anchor milestone sits
at zero. Three of them are statutory and should not drift: ballots mail at
`-18`, certification at `+21` after a general and `+15` after a primary or
special, and the post-certification capture the day after. The rest are this
project's working-backward conventions, chosen so each step has room before the
one it feeds:

- **Initialization** opens the cycle. For a primary it lands about four months
  out, before filing week. For a general it lands seventy-five days out, just
  after the primary certifies — a general's ballot cannot be initialized before
  the primary decides who is on it.
- **The official inventory import** follows initialization within a week.
- **The source panel freezes** about two months out, and collection opens a few
  days later, so the panel is settled before any endorsement is gathered.
- **The guide publishes** the day ballots mail. Publishing earlier serves a
  ballot no one is holding; publishing later wastes the week voters decide.
- **Refresh points** at `-11` and `-4` catch late endorsements without
  reopening collection. Short cycles carry only the final one.
- **The retrospective** lands thirty days out, after certification has settled
  what actually happened.

Specials carry measures placed by resolution rather than candidates, so they
have no filing week and a shorter runway: initialization at `-60` and the panel
frozen at `-30`.

Statutory anchors are the calendar's best current reading of the law, not a
substitute for it. Reconfirm each cycle's real dates against the Secretary of
State's and King County Elections' published calendars when the election is
initialized, and correct the offsets here if they disagree.

## Results capture

Every declared election must schedule both results captures: one on election
night and one after certification. These are the windows the epic exists to
protect — unofficial election-night returns are overwritten as later drops
land, and neither snapshot can be reconstructed afterward. Validation rejects
any election missing either one, and rejects a post-certification capture dated
before its own certification.

## What validation rejects

`make check` and CI both run:

```bash
uv run election-guide calendar validate config/calendar/elections.yaml
```

It fails on an offset that contradicts its milestone's kind — a certification
before election day, an election-day milestone that is not at zero, a mailing
that happens afterward — and on an offset outside a two-year planning horizon.
It fails on a milestone naming an election the calendar does not declare, on a
repeated election ID, and on a repeated milestone ID within one election. It
fails on an election with no election-day milestone or with two, on a missing
results capture, and on any field the schema does not declare.

## Tracking milestones as issues

A declared milestone is inert until someone sees it. The `Calendar` workflow
runs daily and opens one issue per milestone falling inside a lead window,
defaulting to twenty-one days:

```bash
uv run election-guide calendar track config/calendar/elections.yaml --dry-run
```

Each issue follows the repository's task template, carries the election, the
date, and the command that does the work, is labeled `type: ops` and
`area: operations`, and is attached to a GitHub milestone named for its
election. A milestone already past its date is never opened; an issue for work
nobody can still do is worse than none.

The last line of every generated issue is its marker —
`calendar-milestone: <election-id>/<milestone-id>`. That marker is the entire
idempotence mechanism. Each run reads the markers of every existing issue, open
**and closed**, and skips the milestones already represented, so a daily
schedule never accumulates duplicates and a completed milestone is not
reopened.

The marker is derived from identity, never from a date, so a milestone whose
date moves is still recognized as already tracked and does not get a second
issue. Nothing rewrites the first one: creation is the only operation this
workflow performs. **If you move a declared date after its issue is open, fix
that issue by hand** — its title and acceptance line still carry the date it
was opened with.

The listing that finds those markers filters by the `type: ops` label rather
than searching for the marker text. GitHub's issue search ranks by relevance
over an eventually consistent index, so it can both match unrelated issues and
omit one created moments earlier — which is exactly when a second run would
duplicate it.

That makes the label a precondition of the no-duplicate guarantee: **a
generated issue must keep its `type: ops` label.** Strip it and the next run
stops seeing that issue's marker and reopens the milestone, once a day, for as
long as it stays inside the window. The label the run reads and the label it
writes are one constant in the code, so they cannot drift apart on their own.

`--dry-run` still queries GitHub, so it prints what the real run would create
rather than what the calendar contains.

## Adding an election

Append the election, then its milestones, then run the validator. Copy the
milestone set from the nearest election of the same type and adjust only what
its dates require; the shape is meant to be repetitive, because a milestone
silently absent from one cycle is exactly the failure this file prevents.

Keep the file in date order. An election added far enough ahead carries the
full set.

### Adding an election whose runway has passed

An election already under way is the one case where the full set is wrong.
Declare only the milestones still ahead of it and leave the earlier ones out.
A milestone is a commitment to do work on a date; backfilling one that has
already come and gone schedules work nobody can perform, and the tracking
workflow that reads this file would have to filter it back out.

The 2026 August primary is the worked example. It was added two days before its
election and carries four milestones — election day, the election-night
capture, certification, and the post-certification capture — because those were
the only ones left. Its initialization, inventory import, panel freeze,
collection window, mailing, and publication had all already happened.

Judge the boundary by what remains, not by the milestone's kind: an election
added a month out keeps its refresh points and drops its panel freeze.

## What the calendar does not declare

No display strings, no banner semantics, and no copy. Decision D5 in
`docs/SITE_OPERATIONS_PLAN.md` resolved that the calendar should model election
identity, dates, and offsets cleanly enough for a renderer to read later,
while leaving that seam open rather than committing to it. A milestone's `kind`
and ID are stable enough to key voter-facing text against; that text belongs on
the rendering side, not here.

The retrospective milestone therefore declares a date and a reference to
`docs/POST_ELECTION_RETROSPECTIVE.md`, and no wording of its own. A reference
names where the work is written down; it is not copy about the milestone.
