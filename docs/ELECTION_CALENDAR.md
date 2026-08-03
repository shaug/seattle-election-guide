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

## Adding an election

Append the election, then its milestones, then run the validator. Copy the
milestone set from the nearest election of the same type and adjust only what
its dates require; the shape is meant to be repetitive, because a milestone
silently absent from one cycle is exactly the failure this file prevents.

## What the calendar does not declare

No display strings, no banner semantics, and no copy. Decision D5 in
`docs/SITE_OPERATIONS_PLAN.md` resolved that the calendar should model election
identity, dates, and offsets cleanly enough for a renderer to read later,
while leaving that seam open rather than committing to it. A milestone's `kind`
and ID are stable enough to key voter-facing text against; that text belongs on
the rendering side, not here.

The retrospective milestone therefore declares a date and nothing else. The
checklist it will point to is tracked separately.
