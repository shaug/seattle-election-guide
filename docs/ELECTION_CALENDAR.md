# Election operations calendar

Washington's election cadence is statutory and predictable. The recurring risk
to this project has never been a bad build; it is missing a data-gathering
window that cannot be reopened. `config/calendar/elections.yaml` makes that
cycle a tracked artifact rather than something remembered.

The calendar is primarily a planning artifact. It also carries explicitly
informational statutory anchors when a historical date is necessary to keep
policy truthful. It is not itself a site feature.

## The cadence

Washington holds special elections on the second Tuesday in February and the
fourth Tuesday in April, its primary on the first Tuesday in August, and its
general election on the first Tuesday after the first Monday in November. Those
dates are fixed in statute, which is why elections can be declared here years
ahead of the ballot that fills them.

The dates that matter to this project hang off election day at known distances.
A qualifying voter may obtain a special absentee ballot up to ninety days
before a primary or general election; regular overseas and service ballots are
issued earlier than the domestic mass mailing; domestic ballots are mailed no
later than eighteen days before election day. County canvassing boards certify
roughly three weeks after a general election and about two weeks after a primary
or special. Candidate filing week falls in May, and it settles the field for
both the August primary and the November general.

## What the calendar declares

An election declares its identity — a stable ID, its type, its scope, its date,
and its state. A milestone declares which election it belongs to, a stable ID
unique within that election, a `kind` from a closed vocabulary, and
`offset_days` from its election's date. A milestone may also name the `workflow`
that carries it out and a `reference` document that explains how. Dates default
to `date_status: planned`; set `date_status: actual` only when evidence verifies
that a historical event occurred on a different date from its missed target.

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
at zero. The ballot dates are distinct contracts: qualifying special-absentee
availability can begin at `-90` for a primary or general, the regular
overseas/service issuance follows the election's official calendar (`-46` for
the declared primary/general cycles and `-30` for the declared specials), and
`ballots_mail` is the domestic mass-mail deadline at `-18`. Certification is
at `+21` after a general and `+14` after a primary or special (RCW 29A.60.190),
with the post-certification capture the day after.
Every election declared with its full collection runway must carry the regular
overseas/service anchor; a primary or general also carries the qualifying
special-absentee edge. Its planned `guide_publishes` date cannot be later than
regular overseas/service issuance; an `actual` date may be later only to record
a verified missed target truthfully.
The rest are this project's working-backward conventions, chosen so each step
has room before the one it feeds:

- **Initialization** opens the cycle. For a primary it lands about four months
  out, before filing week. For a general it lands seventy-five days out, just
  after the primary certifies — a general's ballot cannot be initialized before
  the primary decides who is on it.
- **The official inventory import** follows initialization within a week.
- **The source panel freezes** before collection, which opens with enough room
  to finish before regular overseas/service issuance. Primary/general cycles
  use the longer runway; the shorter special cycle freezes at `-42`, opens at
  `-40`, and issues regular overseas/service ballots at `-30`.
- **The guide publishes** as soon as it can truthfully cover a settled ballot,
  and no later than the first scheduled regular ballot issuance. Absolute
  special-absentee availability may precede that target: for the 2026 general,
  the 90-day date was 2026-08-05, one day after the primary and before the
  general-election field settled at primary certification. The practical
  publication target was therefore the 2026-09-18 overseas/service issuance,
  not the 2026-10-16 domestic mailing. Because that target was missed,
  the internal `guide_publishes` deadline stays on 2026-09-18 while the public
  `guide_published` occurrence records the verified actual publication on
  2026-10-03.
- **Refresh points** catch late endorsements after publication without
  reopening collection. The 2026 general adds a comprehensive pre-domestic
  deadline at `-19` (2026-10-15), followed by the existing `-11` and `-4`
  checkpoints. Short cycles carry only the final one.
- **The retrospective** lands thirty days out, after certification has settled
  what actually happened.

Specials carry measures placed by resolution rather than candidates, so they
have no filing week and a shorter runway: initialization at `-60` and the panel
frozen at `-42`.

Statutory anchors are the calendar's best current reading of the law, not a
substitute for it. Reconfirm each cycle's real dates against the Secretary of
State's and King County Elections' published calendars when the election is
initialized, and correct the offsets here if they disagree.

For the underlying distinctions, [RCW 29A.40.050](https://app.leg.wa.gov/rcw/default.aspx?cite=29A.40.050)
and King County's [How to get your ballot](https://kingcounty.gov/en/dept/elections/how-to-vote/ballots/how-to-get-your-ballot)
page establish the qualifying 90-day special-absentee edge. King County's
[Overseas and service voters](https://cdn.kingcounty.gov/so-so/dept/elections/how-to-vote/ballots/overseas-and-service-voters)
page describes electronic delivery and the regular 45-day primary/general
schedule; electronic delivery means the issuance day itself can be a
ballot-in-hand day. The county's [2026 General Election Calendar](https://cdn.kingcounty.gov/-/media/king-county/depts/elections/for-jurisdictions/pdf/jurisdiction-manual.pdf)
records the 2026-09-18 overseas, service, and out-of-state issuance and online
ballot-material availability.

## Results capture

Every declared election must schedule both results captures: one on election
night and one after certification. These are the windows the epic exists to
protect — unofficial election-night returns are overwritten as later drops
land, and neither snapshot can be reconstructed afterward.

Every election must also declare `results_ingest` to publish the certified
results. Schedule it at the same offset as the post-certification capture,
referencing `docs/runbooks/results-certified-ingest.md` and the `results ingest`
workflow. Ingest remains human-launched, as that runbook requires. Validation
rejects an election missing any of the three milestones, a post-certification
capture before certification, or an ingest before its post-certification capture.

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
results capture or ingest, and on any field the schema does not declare.

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

| Milestone kind                       | Artifact window                                      | Promised artifact                                                          | Recognized by                                                                        |
| ------------------------------------ | ---------------------------------------------------- | --------------------------------------------------------------------------- | ------------------------------------------------------------------------------------ |
| `collection_opens`                   | through that election's `guide_publishes`, inclusive | an evidence manifest, **or** a refresh event in `data/collection/refreshes/` | date in the window, a `source_id` that is **not** a counting authority's             |
| `results_capture_election_night`     | milestone date through seven days later, inclusive   | an evidence manifest in `data/manifests/evidence/`                           | date in the window, a **counting authority**'s `source_id`, title carrying `election-night results` |
| `results_capture_post_certification` | milestone date through seven days later, inclusive   | an evidence manifest in `data/manifests/evidence/`                           | date in the window, a **counting authority**'s `source_id`, title carrying `certified` |
| `results_ingest`                      | seven days after the milestone date before escalation | a results file in `data/results/` | `data/results/<election-id>.yaml` names that election and has status `certified` or `amended` |
| `refresh`                            | milestone date through seven days later, inclusive   | an evidence manifest, **or** a refresh event in `data/collection/refreshes/` | date in the window, a `source_id` that is **not** a counting authority's             |

Results ingest is matched by election identity and published status, not a capture
timestamp. The seven-day window controls when a missing file is escalated; an
already published file satisfies the milestone, and an amended canvass continues
to satisfy it. `status: counting` does not. The watch reads results through their
existing schema reader and fails visibly on a malformed file.

The check is deterministic — a scheduled job reading the calendar and the tree,
with no agent involved — and it neither dispatches work nor closes anything.

Most other kinds are a date to act on rather than work that leaves a record,
so the check has nothing to look for. `collection_opens` is different: it opens
a sweep whose captures may land over several weeks, and the sweep runbook names
`guide_publishes` as its real deadline. Its window therefore opens on the
`collection_opens` date and closes on that election's `guide_publishes` date,
inclusive. The watch leaves work in progress alone throughout that window and
escalates an opening sweep only after publication passes with no artifact.

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

- the **window** supplies the election — it opens on the milestone's own date.
  Fixed windows close seven days later, while `collection_opens` closes on that
  election's `guide_publishes` date;
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
tracking issue in two stages. The fixed windows become `overdue` after seven
days and `stale` after twenty-one. A `collection_opens` sweep becomes `overdue`
the day after `guide_publishes`; it becomes `stale` fourteen days after that
overdue stage begins. Each stage adds its own label and posts one comment saying
what was looked for and where.

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

Four kinds are public today: `ballots_mail`, planned `guide_publishes`, actual
`guide_published`, and `election_day`. Marking a milestone public is only half the job — the words a
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

`date_status` does not change whether an event is public. It distinguishes a
future commitment from verified history so validation can enforce the regular
issuance deadline prospectively while the feed reports a missed target's actual
publication date.

`ballots_mail` is the domestic mass-mailing date, not the first date any voter
may possess a ballot. A primary or general may declare the internal
`special_absentee_ballots_available` milestone for the absolute qualifying
90-day edge and `overseas_service_ballots_mail` for the scheduled regular
issuance. A planned `guide_publishes` deadline does not wait for domestic mailing: for the 2026
general election, special-absentee availability began 2026-08-05, regular
overseas/service ballots and online materials issued 2026-09-18, and domestic
ballots mail 2026-10-16. The guide's 2026-09-18 target was missed because the
field first had to settle and the reviewed release path was not ready; the
public `guide_published` event records the actual 2026-10-03 publication while
the internal `guide_publishes` deadline remains 2026-09-18.
Keeping the specialized dates internal avoids presenting them as the date every
local voter should expect a ballot while preserving the real operational
deadlines.

## Adding an election

Append the election, then its milestones, then run the validator. Copy the
milestone set from the nearest election of the same type and adjust only what
its dates require; the shape is meant to be repetitive, because a milestone
silently absent from one cycle is exactly the failure this file prevents.

Keep the file in date order. An election added far enough ahead carries the
full set.

### Adding an election whose runway has passed

An election already under way is the one case where the full set is wrong.
Declare only the actionable milestones still ahead of it and leave earlier
actionable milestones out. An actionable milestone is a commitment to do work
on a date; backfilling one that has already come and gone schedules work nobody
can perform.

The explicit exception is an informational statutory-availability anchor whose
historical date is needed to keep policy truthful. The
`special_absentee_ballots_available` kind is informational: it may be recorded
after its date, stays private, and `calendar track` never opens an issue for it.
It records the absolute legal edge; it does not imply that a complete guide
could have published then or schedule retroactive work. The 2026 general's
2026-08-05 entry is the worked example of this exception.

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
