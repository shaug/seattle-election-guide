# Preliminary official results refresh (#696)

Preliminary means unofficial count-so-far. Complete jurisdiction coverage does not mean
counting or reporting has finished. Never publish King County's share as a statewide or
multi-county total. This runbook does not reopen #535 or perform future #692/#693 early.

## Admission

1. Start from the registered official authority and actually offered publication links.
   Verify election, jurisdiction and unofficial/certified status. Preserve actual response
   bodies, URLs, redirects, status and check clocks; stop actual access denials without a
   different actor, user-agent, login, host or guessed endpoint workaround.
2. Preserve new official bytes through the normal `election-guide evidence capture` writer,
   in the tracked official evidence store. Keep every original capture unchanged. A new
   retrieval is not a new publisher count time, and export generation is not count-as-of.
3. Prove every frozen race's full official contest scope and choice mapping. Statewide and
   cross-county races need their complete authoritative count-so-far. Prefer the official
   aggregate; never sum selected counties or infer scope from empty `crossCounties`.
4. Bind each tally to its actual publisher count timestamp, or explicitly labeled export
   generation when count time is absent, and original capture. Verify
   reported update schedules and certification status/timing separately for each authority.
   County November24 and existing calendar tickets do not prove State certification timing.
5. Preserve all named choices and separate write-ins. Percentages use named-choice votes.
   The countline uses authority-stated contest ballots/votes, or a tagged complete-choice
   vote sum when the State supplies no total. Never derive ballots by adding candidate votes.
6. Validate the strict preliminary document, frozen inventory and all retained evidence
   with `uv run --offline --frozen election-guide results validate <results-file>`.
   Unsupported/missing geography, clock or choices blocks admission. A partial County-only
   candidate cannot be marked complete. A production data file requires these proofs; historical schema fixtures are not
   production data or current-data approval.

## Refresh and failures

### Explicit autonomous acquisition interface

The fixed reviewed November 3 feeds can be fetched without a user download:

```sh
uv run --offline --frozen election-guide results acquire-preliminary county --live
uv run --offline --frozen election-guide results acquire-preliminary statewide --live
```

Each permitted invocation makes one request through the existing identifying SEG Python HTTP
transport. The results-only profile has a 128 MiB byte budget, a 60-second total deadline
and no redirect following. The ordinary endorsement collector retains its 25 MiB budget.
There is no automatic retry or alternate-client fallback. A real denial/error writes an
unavailable manifest and exits unsuccessfully. Successful supported JSON is retained in
the tracked official evidence store with the actual HTTP status, retrieval clock and hash;
`capture_method: json` does not claim a browser read or a manual user download.

An acquisition command never writes `data/results`, changes a publisher count timestamp,
certifies an election or publishes the site. Its caller must stop on failure. A retained
401/403 or unreviewed redirect holds subsequent invocations for that exact source/URL;
another scheduler tick cannot release it. A legitimate reviewed access disposition is
required. Scheduling and protected publication are not activated
by these commands. See the [November 6 client experiment](../audits/2026-11-06-preliminary-http-clients.md)
for observed client differences and remaining data-admission limits.

### Autonomous delivery requirement and current capability

`results prepare-refresh config/results/wa-2026-general-preliminary.yaml
--inventory-path data/normalized/wa-2026-general-inventory.json --live` validates the
seed mapping before any request, locks the whole transaction, preflights every source hold,
captures once per source, rebinds exact IDs/names and atomically prepares the full snapshot.
A real failed acquisition preserves old counts and appends its actual unavailable manifest.
Schema, identity, classification or timestamp regressions stop admission without manufacturing
an HTTP failure. The State uses its full aggregate; County sources require inventory ancestry
contained in King County. Lower corrected counts are not clamped.

The hourly workflow remains opt-in: `PRELIMINARY_RESULTS_REFRESH_ENABLED` must equal `true`.
It runs only from protected main and only on a first run attempt. The job token has repository
and Actions read access. The existing archive GitHub App token requests only contents and
pull-request write; it requests no workflow-write permission. Activation follows normal review
and deployment of this implementation, not a local script or an unreviewed branch.

Each eligible tick checks the fixed `codex/preliminary-results-refresh` branch and its PR first. After an ordinary upstream merge,
a completed squash candidate whose entire tree equals current main starts a fresh
refresh. The merge retains branch ancestry for the next normal fast-forward push;
a real unmerged difference remains recovery work with no new source acquisition.
An open PR suppresses new source requests until its review/delivery is complete. A pushed
candidate missing its PR is recovered without reacquiring sources. Normal merge conflicts stop
for reconciliation; there is no force push, client fallback, self-approval or self-merge.

Before source work the job retains intent, restores the exact previous completion state and
preserves held denial manifests. Missing/uncertain prior state stops before requests. A known
blocked admission also stops later ticks; certification, schema and mapping errors are not fake
HTTP failures. Successful unchanged checks preserve count clocks and need no election-information
Update. Changed counts/source reporting metadata or genuine unavailable observations receive a
truthful append-only results Update, preserving all earlier text. The historical migration
contract retains every complete pinned entry while allowing later substantive results
updates. Before staging, the publisher requires the entire previous Updates file to
remain an exact byte prefix, including any earlier automatic entries.

The job prepares the normal release request and runs the complete `make check`, then stages
only the General results, its Updates, the normal hosting proposal and new immutable official
bytes/manifests. Code, Primary changes, replaced captures, missing/symlinked files and files over
GitHub's 100 MiB limit stop before push. One ordinary branch push and draft PR hand off the
candidate; the exact source/CI/review/admission and normal production gates still apply. A
pending PR or a configured cron is not evidence of a completed production refresh. Preserve
actual run, candidate and deployment evidence before declaring the autonomous requirement met.

The scheduled acquisition is hourly at minute17 UTC. It is not browser polling. The fixed
source deadlines/byte budgets and no-retry rules remain unchanged. The last verified production
snapshot remains available while review, source access or admission is blocked. Automatic
publication cannot certify results or substitute County-only counts for complete jurisdictions.

#696 requires supported autonomous acquisition, admission, scheduled refresh and normal
protected publication. The local producer commands below are component interfaces; an
operator-triggered daily recipe, a requested user download or an unexecuted schedule does
not complete that requirement. Before activation, bind legitimate publisher-supported
machine access and prove the complete jurisdiction map, count clocks/status and actual
authority update schedules. No scheduled job may retry a held denial through a different
client, identity, route or host. Retain the existing snapshot and unavailable/stale state.
Transport/provider integration and end-to-end scheduled publication remain unverified
until those bindings and the actual normal gates execute successfully.

The local producer consumes an explicitly reviewed mapping and already captured bytes:

```sh
uv run --offline --frozen election-guide results ingest-preliminary <mapping.yaml> \
  --inventory-path data/normalized/wa-2026-general-inventory.json
uv run --offline --frozen election-guide results validate data/results/wa-2026-general.yaml
```

`PreliminaryAdmissionPlan` binds each source format, registered authority and immutable
capture; every inventory race then binds its exact source contest ID/name, jurisdiction,
whole-scope proof and every named source choice ID/name to the frozen ballot choice.
There is no name-only discovery or partial-inventory production mode. The parser preserves
unknown fields: the statewide Media Export's `createdAt` is generation time, not count-as-of.
Its missing official-status flag stays null; SEG's output remains explicitly uncertified.
An explicit true official-status flag blocks preliminary admission. The approved timestamp
wording states generation and missing count time. Missing authority totals use only a tagged
sum of the complete mapped choice rows, never an inferred ballot count or a claimed stated total.
An existing certified file cannot be overwritten with preliminary results.

The autonomous capture/admission/diff/review/publication sequence follows official announced
releases, grounding its cadence in publisher evidence. It must use the repository's normal
append-only candidate and protected release gates. No live client polling or direct upload
may bypass those gates. The manual component commands are also available for diagnosis.
Compare every named count/share, reporting state, coverage and source clock. A lower corrected
count is a reviewable revision, not a value to silently clamp or discard. A timestamp regression
or changed election/schema/scope must stop new admission and preserve the previous snapshot.

Retain the last admitted whole-jurisdiction counts on a later access/refresh failure, with
their original count-as-of and explicit stale/unavailable status. Do not replace them with
zero, advance their publisher clock, erase endorsement facts or manufacture a successful
check. A successful unchanged official recheck can update verification time separately; it
cannot advance count-as-of. All changed count/share information passes normal exact-head
checks, substantive Election Updates, independent review and protected release gates.

Record a genuine failed retrieval with the normal evidence-unavailable writer, then attach
that retained unavailable manifest with:

```sh
uv run --offline --frozen election-guide results record-refresh-failure \
  data/results/wa-2026-general.yaml <unavailable-manifest.json>
```

The source identity and actual check clock must match the manifest. This is not a way to
label a mapping/validation error as an HTTP failure. Counts and their publisher timestamps
remain unchanged. A later successful capture can clear the visible warning while keeping
failure history. The displayed verification time ages to **Stale** after 24 hours; a later
failed retrieval displays **Refresh unavailable**. Reader-side aging makes no requests,
writes no storage and cannot certify data. The count-as-of remains visible throughout.
None of these result checks refreshes endorsement publisher-access clocks or `data_as_of`.

## Certification

A calendar date is never evidence of certification. Capture the authority's actual formal
certification publication at the proper future window, verify complete coverage and reconcile
authority-specific dates/status. Use the certified/amended ingestion contract; do not relabel
preliminary tallies or rewrite historical captures. Preliminary data cannot satisfy the
calendar's certified-results ingestion milestone. Keep #692/#693 scope accurate when actual
authority evidence establishes any needed follow-up correction.
