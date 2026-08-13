# Post-election results

Design for epic #208, ratified 2026-08-02. This document records what "finalizing an election"
means for this site: how certified results enter the data, how the archive states them, and the
boundaries that keep the feature small. Rendered mockups for every surface described here live at
`docs/design/RESULTS_FINALIZATION_2026-08-02.html`.

Ingestion mechanics — the adapter that turns an official results publication into
`data/results/` — are deliberately not designed here. That is the next design step, and the data
model below is its contract. That step landed with #284 (below).

## Posture: close the record

The site's purpose is in the name: it helps voters vote. Results are a secondary feature, and
"secondary" was sized deliberately. The site ingests **certified results only**, once per
election, and each archived race then states how it completed. While ballots are being counted,
the site links out to the counting authority and ingests nothing. The site never becomes a
results tracker: King County's own site is always fresher, tracking demands deploys exactly when
attention is scarcest, and Washington's late ballot drops make early numbers most misleading
precisely when traffic is highest.

Two framing constraints bind everything this design renders:

- **Trends, not performance.** The site does not predict outcomes and is not scored against
  them. Results are facts about how a race completed — never accuracy, never a track record.
  Language implying prediction or a grade is out of scope (Epic G, decision D4).
- **Outcomes never displace recommendations.** The site is about who *should* win — and should
  have won. Reality is a secondary consideration, rendered as context beneath the
  recommendation, never as the headline. An archived guide records what the guide said.
  *(Clarified 2026-08-13 by #354: "beneath the recommendation" governs standing, not document
  order. The race-detail page states the complete certified result above its recommendation
  because that result is the one fact on the page no reader's source selection can change —
  and the recommendation still keeps its own heading, tone, and meter, and the result never
  becomes the page's headline. Nothing about which of the two the site is for has moved. See
  "The race-detail page's certified result" below.)*

## The results lifecycle

Washington votes by mail with postmark-day validity, so the count is a process. The model needs
three states after election day, and only one of them publishes numbers:

| State       | Window                        | What the site does                                    |
| ----------- | ----------------------------- | ----------------------------------------------------- |
| `counting`  | election night → certification | Links out to the counting authority; ingests nothing |
| `certified` | county canvass onward          | The one ingest, review, and deploy                   |
| `amended`   | recount or amended canvass     | A superseding re-ingest, logged as a correction      |

Two evidence captures bracket the window, both declared as calendar milestones (O11) because the
windows are unrecoverable:

- **Election night** (~8:15 p.m.): the county's first tabulation, captured as evidence only.
  It is never rendered — later drops overwrite it, and archiving a misleading number as if it
  were an answer works against the site's posture. Revisit only if a real need appears.
- **Certification** (county canvass; roughly two weeks after a primary, three after a general):
  the published dataset. One adapter run, one review, one deploy through the normal approval
  gate. This is the finalization moment.

## Data model

One results file per election, produced by a collection adapter carrying the same
evidence-capture, hashing, and provenance discipline as endorsements (`docs/EVIDENCE_CAPTURE.md`,
`docs/COLLECTION.md`):

```yaml
# data/results/wa-2026-primary.yaml
election_id: wa-2026-primary
status: certified          # counting | certified | amended
certified_on: 2026-08-19
authority: King County Elections
captures:
  - kind: election_night   # evidence only, never rendered
    captured_at: 2026-08-04T20:35:00-07:00
    evidence: data/manifests/evidence/capture-kc-results-….json
  - kind: certified
    captured_at: 2026-08-20T16:05:00-07:00
    evidence: data/manifests/evidence/capture-kc-results-….json
races:
  - race_id: king-county-council-8
    ballots_counted: 61234
    outcomes:
      - choice_id: king-county-council-8--teresa-mosqueda
        votes: 33189
        share: 0.542
        advanced: true     # the choice that prevailed (see below)
```

`ballots_counted` is the authority's own count of ballots that carried the contest (its
`BallotsWith Contest` figure, for King County's certified CSV export); `share` is a choice's votes
over the *declared* (non-write-in) vote total, so a race's shares sum to ~1 whatever its write-in
tally is. See "Ingestion mechanics," Write-in votes, for why these are three separate totals.

`advanced` marks the choice that prevailed, for every race type — the rendered label is read off
it together with the race type and with *which* choice carries it: a primary's "Advances", a
general's "Elected", a measure's "Approved" when its `Yes` choice carries the flag and "Rejected"
when its `No` choice does. There is deliberately no separate rejection field; a rejected measure
is simply one whose `No` prevailed.

Validation asserts every `choice_id` exists in the frozen ballot inventory, shares sum to ~1 per
race, and an `amended` file cites the capture it supersedes — which is what feeds the corrections
page automatically.

The general election never consumes primary results. They are separate elections; the county's
official general inventory is the sole source of truth for who is on that ballot. Results
corroborate; they do not seed.

## Rendering

One principle governs every surface: results render as a **state, not an option**. There is no
toggle and no new filter control. When a results file with `status: certified` (or `amended`)
exists for the election, the surfaces below render it; before that, they don't. One new rendering
state to test, not a combinatorial option.

**The election-day banner's counting state is the one exception, and it is deliberate, not a
gap.** The counting window ingests nothing (Posture: close the record), so no counting-status file
ever exists to gate on — a rendering rule keyed on file existence alone would leave that window
with nothing to render. The banner's counting state instead derives from dates the page already
carries: election day has passed (the shipped #192 past-rewrite condition) and the calendar's
certification date has not yet been reached. Every other surface, and the banner's own certified
state, still gate on the results file exactly as above (#285, "The election-day banner").

Vote share and endorsement share never share a component. The endorsement meter keeps its
meaning everywhere; vote share is always a slim navy-on-track tally bar, and every bar in a view
runs on the same full-width scale so shares compare honestly across candidates.

### The results chip

One chip communicates the outcome: sky on navy (`--sky` on `--navy`), a lightened tint of the
site's own navy, deliberately outside the agree/differ tone families — neither good nor bad,
fact. It renders immediately after the candidate's name on every surface. Its label follows the
race type:

- **Advances** — a top-two primary.
- **Elected** — a certified general winner. ("Won" reads like sport; "Elected" survives judges
  and school boards.) Standing proposal, not yet exercised.
- **Approved / Rejected** — ballot measures, matching the certification's own language.
  Rejected keeps the same sky tint; it is still just a fact.

At narrow widths the layouts stack rather than invent anything new: a candidate heading's two
sides wrap (kicker, name, chip first; metrics following), and when the name and chip cannot share
a line, the chip wraps beneath the name.

### The election-day banner

The shipped banner (#192: tense-neutral server rendering, amber escalation inside seven days,
past-tense rewrite — `shell.py`, `election-day.mjs`) is **out of scope and unchanged**. With no
results file and no certification date known, the existing past rewrite remains forever. The two
new states extend the same element and the same two color surfaces, but they activate on two
different triggers (#285, "Trigger model"), not on the results file alone:

- **Counting** (amber attention family) — no file to gate on, so this one derives from dates the
  page already carries: election day has passed (the existing #192 past-rewrite condition) and the
  calendar's certification date has not yet been reached. If that date passes with still no
  certified file, the banner falls back to the existing past rewrite rather than a stale counting
  promise:
  "**Ballots are being counted** — see the count at King County Elections." /
  "Results certify August 19, 2026."
- **Certified** (muted past family) — gates on the certified results file existing, as every other
  surface in this document does:
  "**This election is complete.**" / "Results were certified August 19, 2026."

**Trigger model.** The certification date comes from the calendar's `certification` milestone for
this election (`config/calendar/elections.yaml`), carried into the page the same way `election_date`
already is (`PublicationMetadata.certification_date`). The certified state's date is the results
file's own `certified_on`, not the calendar date — the two usually agree, but only the file's date
is ever displayed once it exists. Ratified with the maintainer at implementation time (#285); this
is the settled answer to the gap the design review found, not an open question.

New-state banner text follows four rules: at most two lines; a line never breaks mid-sentence —
each line is a complete thought; links name their destination; and exactly one date appears — the
most important next one, or the last one once the election is completely over. Nothing about when
counts update; that is not how this site works.

### Race cards

A certified race card keeps its identity — office, recommendation, consensus meter — and grows a
results strip below a rule: per-candidate tally rows (name, chip, share, bar) and a provenance
line (ballots counted, authority, capture link). Between election day and certification, a
candidate race card renders unchanged — no counting indicator of any kind. The election-day
banner alone carries the counting-window message (see "The election-day banner" above); repeating
it on every race card was redundant, not reinforcing, and #344 removed the interim per-card note
this section originally described.

### The race-detail page

Ratified when this surface was still the guide's own endorsements dialog; #136 moved it to its own
address, and it is named for what it is now.

The page states **the complete certified result once, under the race header and above the lens
bar** — every choice on the ballot in finish order, each with its share, its bar, and its chip,
over the provenance line. Below the lens bar the page is endorsements, unchanged: the recommendation
headline, then one section per endorsed candidate in endorsement order, each carrying its own meter,
its own source list, and its chip after the name. No per-source annotations.

This supersedes the original ratification's two additions — a one-line certified strip plus a
vote-share row inside each candidate's section (#287) — which #354 replaced once it was found that
a candidate no source endorsed has no section to carry a result, so a winner nobody endorsed
appeared nowhere on the page at all. The strip does not survive alongside the block; its date,
authority, and ballot count are the block's own provenance line. See "The race-detail page's
certified result" below for the reasoning and the decisions it settles.

### The comparison view

The comparison page's native grammar is choosing columns, so results join `/compare/` as another
addable column — the one surface where showing results is a reader's choice, because column
selection is that page's idiom. The state gate still governs availability: the column picker
offers "Certified result" only when the results file exists. Cells speak the table's own
language — choice labels on the picks line, shares and certification status on the meta line.

One hard rule from the framing: the result column is **excluded from agreement**. Its cells
never tint agree or differ, and it never contributes to a row's "Differs" marker. The page
states what happened next to what sources said; it does not score one against the other.

## The corrections page

Scoped with this epic (decision D2) because both features are the archive talking about itself
after publication. Corrections are **per-election**: a top-line page with the same affordances
and structure as any other major page, at the election's own path, rendered — and linked in the
nav — only when that election actually has corrections. Anything that crosses elections is a site
matter and belongs to the changelog (O8), not to Corrections.

The editorial line: a correction is **anything that changes what a published page asserts**.
Routine pre-election data refreshes don't qualify; changed recommendations, retracted
endorsements, and amended results do. An amended results file cites the capture it supersedes,
and that citation is the page's entry. Tagline: *"We get it right, eventually."*

## Decisions record (2026-08-02)

- Posture B, close the record: certified results only; the site never tracks the count.
- Election-night numbers are captured as evidence and rendered nowhere.
- Outcomes never displace recommendations.
- Results render as a state, not an option — no new controls.
- Endorsements dialog (the race-detail page, since #136): certified strip plus per-candidate vote
  row; no per-source annotations. *(Superseded 2026-08-13 by #354 — the strip and the vote row
  became one complete result block above the lens bar; see that addendum below. The "no per-source
  annotations" half stands.)*
- Results join the comparison view as an addable column, excluded from agreement computation.
- Measures say Approved / Rejected.
- Corrections are per-election top-line pages, existing only when corrections exist;
  cross-election fixes go to the changelog.
- The general never consumes primary results.
- Trends across elections are entirely out of scope. Nothing here anticipates them beyond the
  certified data existing.
- The pre-election banner is untouched; new banner states are terse (two lines, whole sentences,
  named links, exactly one date).

## Ingestion mechanics (2026-08-07 addendum, #284)

The adapter turning a captured certified export into `data/results/<election-id>.yaml` is
`election_guide.results.ingest` (`uv run election-guide results ingest`), following
`docs/COLLECTION.md`'s fixture-first, provenance-carrying discipline via the same evidence-capture
layer as endorsement collection (`docs/EVIDENCE_CAPTURE.md`; `election_guide.authorities`, #281).
Two decisions this ticket's scope named:

**Parse target.** The retained 2026-08-04 election-night capture bytes this ticket's own
precondition pointed to are not present in this checkout (established investigating #281; every
file actually under `data/snapshots/sha256/` predates the capture and belongs to unrelated
endorsement evidence). Rather than re-run that investigation, this session settled the parse
target with a live re-fetch for design purposes only (distinct from this PR's own fixture test,
which runs offline against committed bytes) — `wa-2026-primary` was still counting as of
2026-08-07, so King County's and the Secretary of State's results pages were live and fetchable,
and an export's *shape* (columns, structure) is stable across a count in progress even though its
*numbers* are not. That fetch confirmed and extended the election-night postmortem's discoveries
(`docs/runbooks/results-capture-election-night.md`):

- King County's certified export is a quoted CSV (`webresults-<date>.csv`, e.g.
  `https://cdn.kingcounty.gov/-/media/king-county/depts/elections/results/2026/08/webresults-<date>.csv`)
  with one row per contest/choice pair and columns `Contest`, `Choice`, `Votes`, and
  `BallotsWith Contest` (among others). Vote and ballot counts are comma-thousands-formatted
  strings (`"214,135"`); a `Write-in` choice row is always present and is excluded from
  ballot-choice resolution (see "Write-in votes" below). This is the adapter's parse target: it is
  directly machine-readable, requires no PDF text extraction or rendered-page scraping, and each
  of the 32 publication-eligible wa-2026-primary races' contest labels observed in that live
  export resolves correctly. Those observed labels are committed in
  `REAL_CONTEST_LABEL_BY_RACE_ID` and re-run offline by
  `test_resolve_race_matches_every_publication_eligible_race_label`
  (`tests/test_results.py`): the test proves the resolver maps them to the right races, while
  their fidelity to King County's export rests on the capture-time observation recorded with
  them.
- The Secretary of State's `results.votewa.gov` JSON export
  (`/results/public/api/elections/washington/<election-yyyymmdd>/data`) remains live and
  structured as the postmortem described. This adapter does not parse it — see "County scope"
  below for why that is deferred rather than silently worked around.
- Resolving a CSV contest label to a race ID cannot use fuzzy text similarity
  (`election_guide.normalization.matching`, built for endorsement-claim matching): King County's
  own contest names differ only by an embedded district number ("Legislative District No. 1
  Representative Position No. 1" vs "No. 11" vs "No. 32"), and fuzzy scoring rates those as close
  matches. The adapter instead builds an exact, normalized phrase set per race from the
  inventory's own office/district/position fields and aliases and requires one exact match; the
  same committed test resolves all 32 of the observed labels, and the fixture test resolves every
  candidate name in the captured excerpt, with zero ambiguous or unmatched results. An export
  contest that matches zero or more than one race is never guessed at — the adapter aborts.

**County scope.** King County's certified canvass states King County's own tally for a contest,
not that contest's true total. That is the same total for every race whose district lies wholly
within King County — every county and city race in the inventory, the legislative districts fully
contained in King County (11, 34, 36, 37, 43, 46), and Congressional District 7. It is **not** the
true total for a race whose district crosses a county line: the four statewide Washington Supreme
Court Justice positions, Legislative District 32 (the state's 2021 redistricting maps place it
partly in King County and partly in Snohomish County), and Congressional District 9 (King, Pierce,
and Thurston counties). For those specific races, the Secretary of State's results are the
true-total source, and parsing its JSON export is real, separate work this ticket does not do (no
acceptance criterion here needs a cross-county race's true total). The adapter therefore requires
an explicit `--race-id` allowlist (`results ingest` refuses to run without one — there is
deliberately no every-publication-eligible-race default, so an operator cannot omit the flag and
get a silent partial-county tally) rather than including whatever a King-County-sourced capture
happens to contain: the live
wa-2026-primary run omits the cross-county races from the King-County-sourced ingest until a
Secretary-of-State-scoped adapter exists to state their true totals, tracked as a follow-up
rather than fabricated here.

**Write-in votes.** A write-in row is never a ballot choice — this schema enumerates only the
choices the frozen inventory carries. The adapter keeps three totals distinct rather than
collapsing them into one:

- `ballots_counted` is King County's own `BallotsWith Contest` figure for the contest, taken
  directly from the export column of that name — the number of ballots whose ballot style
  carried the contest, not a re-derivation from the vote rows. It is larger than the sum of
  recorded votes whenever the contest had any overvoted or undervoted ballot, which every real
  contest does; both provenance lines — the race card's and the race-detail page's result block
  (both above) — render this figure, King County's own count, unchanged by this adapter.
- Each declared choice's `share` is its votes over the *declared* (non-write-in) vote total —
  a third total, distinct from both `ballots_counted` and the raw vote sum.

Declared shares therefore sum to ~1 by construction, and `SHARE_SUM_TOLERANCE`
(`results/models.py`) only ever absorbs the adapter's own fourth-decimal rounding. Computing
`share` against a write-in-inclusive vote total instead would make declared shares sum to one
minus the write-in share, so any race whose write-ins passed a single point would fail the
schema's tolerance and abort the entire multi-race ingest run. That is not a rare anomaly: six of
this election's publication-eligible races (`ld-11-state-representative-2`,
`ld-34-state-representative-1`, `ld-34-state-senator`, `ld-36-state-representative-1`,
`ld-36-state-representative-2`, `ld-43-state-representative-2`) have exactly one declared
candidate, and a write-in is a voter's only alternative there.

## Ballot measures (2026-08-08 addendum, #289)

Ratified with the maintainer against live-rendered mockups extending
`docs/design/RESULTS_FINALIZATION_2026-08-02.html` (a Yes-wins "Approved" case and a No-wins
"Rejected" case, both shown and signed off).

A measure's two choices — `Yes` and `No` — render through the **exact same tally-row component**
every candidate race already uses ("Race cards" above): two rows on the shared navy/gray bar
scale, sorted by share descending, identically to a candidate race with two choices. There is no
new UI mechanism, no new template block, and no new CSS class for measures.

The winning row (`advanced: true`) carries the same chip already named in "The results chip":
**Approved** when the winning choice is "Yes", **Rejected** when the winning choice is "No" — both
in the same neutral sky-on-navy tone as every other results chip, never red/green valence,
consistent with the site's "neither good nor bad, fact" framing. A rejected measure's "No" row
therefore sorts above "Yes" by the same share-descending rule a candidate race uses — flagged and
accepted as part of ratification, not an oversight.

**No validation thresholds are rendered anywhere, and no threshold data is added to the schema.**
The Approved/Rejected chip states a fact taken directly from the authority's own certification —
the same posture already used for `advanced` on candidate races: the site states what the county
certified, not what supermajority or threshold rule produced it. This resolves what "Open
questions" previously tracked as the ballot-measures mockup pass (now removed from that list
below), without exercising the "if thresholds are to be rendered" branch of #289's own scope note
— there is no threshold field to source, so no #283 schema follow-up is needed.

Same provenance line (ballots counted · authority · capture link) and same "Certified ·
`<date>`" badge as candidate cards — nothing measure-specific there either. This applies
identically wherever the certified results data renders: the race card and the race-detail
page render it through the shared tally-row component exactly as above ("Race cards", #286;
"The race-detail page", #287); the comparison column renders the same underlying data through
its own cell grammar rather than the tally-row markup ("The comparison view" above, #288) — reuse
everywhere, not race-card-only, but each surface keeps its own established presentation idiom.

Implemented by #348: `race_results_view`'s former `race.race_type == "measure"` short-circuit is
removed, and a measure-specific chip-label branch (reading the winning choice's own label off the
outcome set) sits alongside the existing primary/general branch — reusing every surface's existing
rendering path exactly as ratified above, with no new UI mechanism on any of the three surfaces.

## The race-detail page's certified result (2026-08-13 addendum, #354)

Ratified with the maintainer against live-rendered mockups built from real committed data with a
synthesized results file attached, so every surface compared was the production DOM rather than a
drawing: `docs/design/RACE_DETAIL_RESULTS_2026-08-12.html`.

**The defect.** A candidate section exists only for a candidate some source endorsed
(`candidate_endorsement_groups`; `docs/METER_V2.md` decision 25, "no section, in either model"), and
#287 hung each certified share inside one of those sections. A choice nobody endorsed therefore had
nowhere to render its result — so a race whose winner drew no endorsement stated three losing
shares and never named the winner, and a rejected measure's winning "No" never appeared. There is
no point publishing results at all if the winner might be missing from them.

**The design.** The certified strip grows into the complete result, in the slot it already held:
under the race header, above the lens bar, above every candidate. It is the race card's own RESULT
block (`.race-results`, "Race cards" above) — eyebrow, "Certified · `<date>`" badge, one tally
row per outcome in finish order with chip, share, and bar on one shared full-width scale, then the
provenance line (ballots counted, authority, capture link). The per-candidate vote-share row is
removed; each candidate section keeps its chip. The block is left-adjusted on the race name's own
edge and capped so a bar stays readable on a wide page.

**Why above the recommendation, and why that does not break "outcomes never displace
recommendations."** The result precedes the recommendation without replacing it: the "Leading
choice" headline keeps its position, tone, and meter directly under the lens bar. Placement is
forced from both sides. A race card can carry its result below its meter because a card is compact
and nothing is buried; the race page is long, and a result placed after the endorsements hides the
one thing a reader most needs. And nothing can be inserted between the headline and the first
candidate section, because those two are one candidate's heading and body — the headline *is* the
leading choice's heading (`docs/DESIGN.md`, "A name appears once per page") and their meter opens
the section below it.

**The organizing principle this settles**, which the page already encoded before it was named:
`race.html.j2` renders the certified strip outside every lens-owned region, gated on `race_results`
alone rather than on the personalization policy, because it is "a permanent fact the reader's source
selection never changes." The lens bar is therefore a real boundary, and results belong above it:

- **Above the lens bar** — facts no reader's selection can change: the race, the complete
  certified result, its provenance.
- **Below the lens bar** — what the reader's chosen sources said, complete only with respect to
  that selection.

The endorsement region does not need to be complete; it shows who was endorsed by the sources the
reader cares about. The result is the same fact for every reader. That difference in kind, not a
placement preference, is why the two regions sit where they do.

**Decisions this settles:**

- **The chip renders in both regions.** It rides its tally row above the bar and stays after each
  candidate's name below it, as #287 ratified. The boundary sorts what a lens can change, not what
  may be stated twice; a reader scanning names below the bar should not have to scroll back up to
  learn who advanced.
- **Two orders, deliberately.** The tally runs in finish order, the sections in endorsement order,
  and both are visible at once. More than the order differs: **the tally names choices that have no
  section below it at all**, which is the entire reason it exists.
- **Named twice is accepted.** A candidate with both a tally row and a section appears twice on one
  page. `docs/DESIGN.md`'s rule is about *headings* — the headline remains the sole heading for
  the leading choice, and a tally row is not a heading — and the race card already does this.
- **The counting window needs nothing.** No results file exists, so neither the block nor the strip
  renders and the page reads as it did before election day; the election-day banner alone carries
  the counting message (#344). Intermediate results would reopen this, and the site does not publish
  them ("Posture: close the record").
- **Measures inherit it unchanged.** A measure's Yes/No choices are its outcomes, so both render as
  tally rows in the block with Approved/Rejected on the winner ("Ballot measures" above, #289/#348).
  The rejected side is now stated, which it was not before.

**Implementation note.** The block's rules (`.race-results*`) live in `guide.css` today, which race
pages do not ship. They move to `guide-race.css` — a correction rather than a new home:
`rendering/stylesheets.py`'s own docstring already describes that sheet as the group only the guide
and a race page render, "the result block, the one meter, the reference bar," and
`.race-detail-result-chip` already sits there for the same reason. Duplicating them into `race.css`
would put one component's paint in two sheets. Because `guide-race.css` composes *before*
`guide.css`, the move changes cascade order, so the guide's own rendered output has to be verified
unchanged rather than assumed.

**Out of scope, raised alongside:** the race page's lens bar is not `position: sticky`, unlike the
guide's own identical strip (#369). A race-page date bar was raised and is undesigned.

## The corrections page's implementation (2026-08-08 addendum, #290)

Storage path (decided by this ticket, per its own scope no separate ratification needed):
**one file per election at `data/corrections/<election-id>.yaml`**, loaded by
`election_guide.corrections.load_rendering_corrections` the same way `data/results/<election-id>
.yaml` is loaded by `election_guide.results.load_rendering_results` (`election_guide.corrections`,
`docs/RESULTS.md`, "Data model" above). Each entry carries a `corrected_on` date, a `headline`,
a `body`, and an optional list of `provenance` `{label, url}` links, rendered newest first:

```yaml
# data/corrections/wa-2026-primary.yaml
schema_version: "1.0"
election_id: wa-2026-primary
entries:
  - corrected_on: 2026-08-27
    headline: "Amended result, State Representative (LD 32, Pos. 1)."
    body: >-
      The county's amended canvass moved the second advancing candidate after a machine
      recount. The certified figures published August 19 have been replaced; both captures
      remain in the archive.
    provenance:
      - label: "capture 9f3c…e2"
        url: https://…
      - label: "capture 41ab…77"
        url: https://…
  - corrected_on: 2026-07-22
    headline: "Corrected an endorsement attribution."
    body: >-
      The 46th District Democrats' sole endorsement in the County Assessor race was
      attributed to the wrong candidate for roughly six hours on July 21. The guide's
      recommendation was unaffected.
```

`provenance` is deliberately a generic labeled-link list rather than a structure naming
"capture" or "supersedes": the amended-results auto-entry that consumes #283's own
`ElectionResults.supersedes` citation is an explicit follow-up **after** #283 lands, not built
here (endorsement-correction entries need no results data). A generic `{label, url}` pair is
exactly the shape that follow-up can populate with two capture links without this schema
changing shape underneath it.

`PublicationViewModel` grows an optional `corrections` field (schema version 1.12 → 1.13), loaded
by `release.builder.build_release` the same way `results` is. The corrections page renders — and
is linked in the nav, right after Comparisons — only while the election's file exists and carries
at least one entry: the same "state, not option" posture every other results-era surface in this
document follows. `hosting.pages` stages `e/<election-id>/corrections/index.html` under that same
gate; no file, no page, no link. The page itself is a full page in the election's own chrome
(same shell, same election-scoped footer) with no interactive client region — corrections are
authored, dated prose, so it carries the same shared shell script every static site-wide page
does rather than a dedicated client entry module.

## Open questions

- **Secretary of State ingestion** — parsing `results.votewa.gov`'s JSON export for the races
  King County's canvass cannot state the true total for (Legislative District 32, Congressional
  District 9, and the four Supreme Court Justice positions). Not built by #284 and no tracked
  issue exists yet for it — file or pick up that follow-up before those races' true totals are
  needed (`docs/runbooks/results-certified-ingest.md`, Escalation).
- **Amended flow detail** — decided concretely when a recount first happens.
