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
runs every six hours and opens one issue per milestone falling inside a lead
window, defaulting to twenty-one days:

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
**and closed**, and skips the milestones already represented, so a repeating
schedule never accumulates duplicates and a completed milestone is not
reopened.

The marker is derived from identity, never from a date, so a milestone whose
date moves is still recognized as already tracked and does not get a second
issue. Nothing rewrites the first one: creation is the only operation this
workflow performs. **If you move a declared date after its issue is open, fix
that issue by hand** — its title and acceptance line still carry the date it
was opened with.

When you edit a generated issue, **leave the marker as the body's last
non-empty line.** The run recognizes an issue by that line and nothing else, so
a note appended below it would otherwise make the issue invisible. Edit above
the marker, or move it back to the end.

If that does happen, the run says so rather than quietly opening a second
issue. Before creating anything it checks whether an existing issue's title
already names the milestone; a title that claims a milestone no marker was
found for means the two disagree, so the run skips that one, names the issue to
look at, and exits non-zero. The other milestones are still opened. A title is
never what makes a milestone count as tracked — only the marker is — because a
human who copied a generated title could otherwise cost a real milestone its
reminder.

The listing that finds those markers reads **every** issue in the repository,
open and closed, and takes the marker only from each body's final line. Reading
everything means the labels a generated issue carries are for triage alone —
strip them and the issue is still seen, so idempotence does not depend on
anyone's triage habits. Taking only the final line means an issue that quotes a
marker while discussing this system cannot suppress a real milestone.

It is deliberately not a text search. GitHub's issue search ranks by relevance
over an eventually consistent index, so it can both match unrelated issues and
omit one created moments earlier — which is exactly when a second run would
duplicate it. The listing fails loudly if it ever reaches its size limit,
because a silently dropped marker is a duplicate issue.

**Why every six hours.** A scheduled workflow on GitHub is best effort: runs are
delayed under load and sometimes dropped, and the top of the hour is the most
congested slot there is — one run in that slot fired forty-five minutes late.
The lead window keeps a milestone eligible for three weeks, but that only
protects the issue eventually existing. It does not protect the reminder
arriving in time, and a milestone due today is worth nothing tomorrow. Four
attempts a day at an off-the-hour minute cost nothing, because re-running
creates nothing.

`--dry-run` still queries GitHub, so it prints what the real run would create
rather than what the calendar contains.

## Watching for the promised artifact

A tracking issue is a reminder, and a reminder nobody acts on closes just as
quietly as one nobody reads. The other half of the `Calendar` workflow runs on
the same schedule and asks the opposite question: the window has closed — did
the work actually land?

```bash
uv run election-guide calendar watch config/calendar/elections.yaml --dry-run
```

It reads what the repository holds, and for each past-due milestone whose kind
promises a checkable artifact it decides whether one exists:

| Milestone kind                       | Promised artifact                                                            | Recognized by                                                                        |
| ------------------------------------ | ----------------------------------------------------------------------------- | -------------------------------------------------------------------------------------- |
| `results_capture_election_night`     | an evidence manifest in `data/manifests/evidence/`                             | date in the window, a **counting authority**'s `source_id`, title carrying `election-night results` |
| `results_capture_post_certification` | an evidence manifest in `data/manifests/evidence/`                             | date in the window, a **counting authority**'s `source_id`, title carrying `certified`            |
| `refresh`                            | an evidence manifest, **or** a refresh event in `data/collection/refreshes/`   | date in the window, a `source_id` that is **not** a counting authority's                          |

The check is deterministic — a scheduled job reading the calendar and the tree,
with no agent involved — and it neither dispatches work nor closes anything.

Most other kinds are a date to act on rather than work that leaves a record,
so the check has nothing to look for. **`collection_opens` is the exception,
and it is deliberately unchecked for now.** It carries the same
`workflow: collect refresh` and the same runbook as the `refresh` milestones,
and its sweep is the one with the real deadline
(`docs/runbooks/endorsement-discovery-sweep.md`) — so an opening sweep that
never ran still passes silently here. It is left out because a sweep's first
captures land over the weeks after collection opens rather than inside a
seven-day window, so checking it on those terms would escalate work that is
under way. Giving it a window of its own is worth doing; it needs its own
decision about how wide, which is issue #384.

A refresh accepts either record because a sweep leaves whichever its sources
allowed. `collect refresh` writes a refresh event, but most of the 2026
primary's panel was captured directly and left evidence manifests instead —
`docs/runbooks/endorsement-discovery-sweep.md` writes its own verification
around those. Demanding the event alone would escalate a sweep that did happen;
accepting either still catches the window where nothing did.

**Three rules decide identity, because a manifest declares none.** Evidence
manifests carry no election and no capture-kind field; a structured one was
tried and reverted, because adding a field to `CaptureMetadata` changes what
every already-committed manifest serializes to (`docs/EVIDENCE_CAPTURE.md`,
"Counting authorities"). So:

- the **window** supplies the election — it opens on the milestone's own date
  and closes seven days later, far narrower than the months between elections;
- the capture's **registry** supplies whose work it was, resolved by looking
  its `source_id` up in `config/authorities/default.yaml`. A results capture
  must come from a counting authority; a sweep's capture must not — the check
  reads absence from that registry rather than membership in the endorsement
  panel, so a source retired from the panel still counts for the windows it
  worked. This is not redundant with the window, because the windows overlap: a
  final refresh sits four days before election day, so its window contains
  election night, and both kinds of capture land in the same directory. Without
  the registry check, the authority's election-night capture would satisfy a
  sweep that never ran;
- the **runbooks' title convention** supplies the capture kind, which is the
  only thing separating a first count from a certified one. Both runbooks pin
  the template that carries it.

Windows are compared in Pacific time, not UTC. King County posts its first
count around 8:15 p.m., so an election-night capture is routinely stamped with
the following UTC date; comparing UTC dates would call every one of them a day
late. Only a `captured` manifest counts — an `unavailable` one records an
attempt that found nothing — and only a refresh event that did not fail.

### Escalation stages

A milestone that passes its window with nothing to show for it escalates its
tracking issue in two stages: `overdue` after seven days, and `stale` after
twenty-one. Each stage adds its own label and posts one comment saying what was
looked for and where.

The comment's last line is its marker —
`calendar-escalation: <election-id>/<milestone-id> <stage>` — read back exactly
the way tracking reads its own. That is the whole idempotence mechanism: a
schedule running four times a day comments once per stage and then stays quiet.

A run emits every stage a milestone has *passed*, not only the one it is in
now. A watch that first ran weeks late would otherwise skip `overdue` outright,
which would make what an issue says depend on when the schedule happened to
fire.

Every issue carrying the milestone's marker is escalated, not one chosen among
them — a marker is not unique in practice (this repository already holds five
issues for one milestone), and escalating one would leave the rest looking
untouched. A past-due milestone with no tracking issue at all is reported on
stderr rather than given one: opening it is `calendar track`'s job, and that
command deliberately refuses a date that has passed.

### When the work happened in another form

Some milestones are done and still cannot produce the artifact this check looks
for. A milestone declares that with `artifact_record`, naming the document that
holds its provenance instead:

```yaml
  - election_id: wa-2026-primary
    id: results-capture-election-night
    kind: results_capture_election_night
    offset_days: 0
    artifact_record: docs/runbooks/results-capture-election-night.md
```

That is the one case this repository has needed. `wa-2026-primary`'s
election-night capture ran on 2026-08-04, before the authority capture lane
(#281) existed, so it produced the runbook's postmortem table rather than
manifests — and the bytes a backfill would have read are gone
(`docs/COLLECTION.md`). Escalating it forever would be escalating completed
work.

`artifact_record` exempts a milestone permanently, so it is a claim a reviewer
has to agree with, not a way to quiet a reminder. Set it only after the work is
done and its record is genuinely a document; the tests resolve the path against
the repository, so a moved document fails the suite.

## Marking a milestone public

Most milestones are internal: a source-panel freeze or an inventory import means
nothing to a voter. A milestone carries `public: true` only when a reader would
want it in their own calendar, and the default is `false` — the published feed
is opt-in, so a new milestone kind stays internal until someone decides
otherwise rather than leaking the moment it is declared.

Three kinds are public today: `ballots_mail`, `guide_publishes`, and
`election_day`. Marking a milestone public is only half the job — the words a
reader sees live in `MILESTONE_COPY` in
`src/election_guide/publication/calendar_feed.py`, keyed by milestone kind,
because decision D5 keeps display strings out of this file. A milestone marked
public whose kind has no copy fails the build rather than publishing an untitled
event.

A public milestone also carries `revision`, starting at 1. **Bump it by hand
whenever you change a published milestone's date or its wording.** It becomes
the event's `SEQUENCE`, which is how a subscribed calendar knows it is looking
at a newer version of an event it already has. It cannot be derived: a build has
no memory of the previous one, and the same input has to produce the same bytes.
The event's identity never changes, so a moved date corrects the existing entry
instead of adding a second one.

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
