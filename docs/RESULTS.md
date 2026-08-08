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
results file, the existing past rewrite remains forever. The two new states extend the same
element and the same two color surfaces, activating only when the results file exists:

- **Counting** (amber attention family):
  "**Ballots are being counted** — see the count at King County Elections." /
  "Results certify August 19, 2026."
- **Certified** (muted past family):
  "**This election is complete.**" / "Results were certified August 19, 2026."

New-state banner text follows four rules: at most two lines; a line never breaks mid-sentence —
each line is a complete thought; links name their destination; and exactly one date appears — the
most important next one, or the last one once the election is completely over. Nothing about when
counts update; that is not how this site works.

### Race cards

A certified race card keeps its identity — office, recommendation, consensus meter — and grows a
results strip below a rule: per-candidate tally rows (name, chip, share, bar) and a provenance
line (ballots counted, authority, capture link). Between election day and certification the same
slot renders one line — a "Counting — results certify …" chip — and no numbers.

### The endorsements dialog

Two additions, no reordering — candidate order remains endorsement order, not finish order:

- A **certified strip** under the dialog header: certification date, authority, ballots counted.
- A **vote-share row** per candidate between the heading and its source list: tally bar and
  share, with the chip in the candidate heading after the name. No per-source annotations.

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
- Endorsements dialog: certified strip plus per-candidate vote row; no per-source annotations.
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
  contest does; the race-card provenance line and the endorsements-dialog certified strip (both
  above) render this figure, King County's own count, unchanged by this adapter.
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

## Open questions

- **Secretary of State ingestion** — parsing `results.votewa.gov`'s JSON export for the races
  King County's canvass cannot state the true total for (Legislative District 32, Congressional
  District 9, and the four Supreme Court Justice positions). Filed as a follow-up to #284.
- **Ballot measures** — a small mockup pass (approve-share bar, validation thresholds).
- **Amended flow detail** — decided concretely when a recount first happens.
