# Runbook: endorsement source daily verification

**Status: proposed, implementation awaiting adoption evidence (#497).** Keep this
status until real due-source native scheduled execution, complete current official factual
baseline reviews for the other five automatic sources under the October 24 SEIU 775 coverage
decision below, and later independent normal scheduled reuse have durable evidence. Fixture execution
proves the mechanism, not live publisher access or source approval. Operator dispatches and
no-due successes cannot substitute. The approved SEIU 775 exception changes only its adoption
gate; its failed checks and unresolved access follow-up remain explicit in the six-source tranche.

## Trigger and boundaries

`.github/workflows/endorsement-verification.yml` polls every six hours.
`config/verification.yaml` declares election inventories, frozen registries, and
source adapters. The scheduler expands three existing planned calendar anchors:
`collection_opens`, `overseas_service_ballots_mail`, and `election_day`. It requires
exactly one of each, in that order; it does not add daily calendar milestones.

Run weekly on the collection anchor and every seventh day thereafter, then daily
from regular overseas/service issuance through election day. The 2026 general
becomes daily on September 18, not domestic mailing on October 16. SGN uses
`daily_from_collection: true`. A late activation starts with current obligations,
then follows the original calendar cadence; it creates no historical backlog.
Missed checks after activation remain reportable after election day.

All 46 eligible current-general frozen-panel sources appear in the coverage record.
Adding another election requires its own frozen registry, inventory, and reviewed adapters in the policy;
never copy primary or previous-cycle candidate mappings into a new ballot.
Policy validation rejects duplicate elections/sources, wrong-election inputs,
unknown or ineligible sources, invalid adapters, and contradictory anchors.

## Autonomy and coverage

Level 2 (Watched): observe, compare, preserve facts, and report. Actual source reviewers
retain interpretation, transcription approval, baseline approval and ledger decisions under
existing maintainer authority. Repository review and existing automatic release/publication
controls remain in force; this detector grants no release authority. The detector does not
modify the published source decisions, source panel, scoring, or historical releases.

The first general-election tranche is:

| Source | Automatic publication check | Limitation |
|---|---|---|
| Transit Riders Union | Official WordPress archive through the September 30 boundary, both known and learned current-general articles, exact linked October graphic | Twelve fixed formal mappings from the designated October article; qualified recommendations held. Complete HTML/image fingerprints drive review. The exact expanded factual baseline was reviewed and delivered in [PR #629](https://github.com/shaug/seattle-election-guide/pull/629); later independent normal scheduled reuse remains pending. Historical failures and exact October 20 obligations remain intact. |
| Sage Leaders | Current 2026 section, excluding past-year sections | Fixed, reviewed factual mappings; changed bytes require review. |
| SEIU 775 | Washington section | Persistent HTTP 403 remains a failed check. The October 24 adoption-only coverage exception below preserves normal daily attempts and unresolved access follow-up. Fixed factual mappings and prior approvals remain intact; changed bytes require review. |
| UFCW 3000 | Complete endorsements landing page plus known/new relevant official articles | Fixed, reviewed factual mappings, including dual endorsements and publisher spelling variants. The complete 33-fact native October 25 baseline (mapping 1.0.2) was reviewed and delivered in [PR #629](https://github.com/shaug/seattle-election-guide/pull/629); later independent normal scheduled reuse remains pending. |
| Washington Working Families Party | Complete Washington candidate table from the reviewed public POST endpoint | Fixed, reviewed factual mappings; changed bytes require review. |
| Seattle Gay News | Current Seattle index plus known/new articles | Daily from collection opening. Traverse pagination to the reviewed oldest current-cycle article, then revisit every known article. |

These checks use `config/adapters/wa-2026-general/`; the older primary TRU adapter
remains separate. The factual fixtures preserve the current general mappings
reviewed in #474. They contain names and offices, not full third-party pages or
editorial prose. They do not approve the first automatic live baseline.

The six stay in the automatic-attempt lane, including an inaccessible source;
failures do not silently reduce coverage. Current operator research and fixture tests
do not establish native scheduled recovery or adoption. Preserve accepted exact-baseline
reviews and native reuse, including WFP's dated review/reuse.
Complete outstanding exact-baseline reviews and later independent native scheduled evidence;
the October 24 decision below excepts SEIU 775 only from the adoption gate. The other five
sources still require complete current official factual baselines, real normal due-source
scheduled execution and later independent normal scheduled reuse. The deployed secret-free
process still needs its own revised acceptance packet and applicable reviewed delivery verification.

All other eligible panel sources use manual review, including not-found,
restricted, social, dynamic, PDF, and image publications without an installed
adapter. Every scheduled manual obligation receives its due date in that day's
finite task. It does not count as successful verification until the actual reviewer records
the review time and durable evidence reference under existing authority. Comprehensive sweeps (#491,
#472, and later calendar checkpoints) retain their separate scope.

`verification plan` returns each lane, cadence, last successful reviewer-verified
check, next due date, and limitation. Unapproved captures and fixture runs do not
populate the successful verification date.

### Optional whole-day intervals (#589)

All 46 current sources retain their omitted settings and existing frequencies. For a new cycle
only, policy schema 1.2 accepts `refresh_interval_days: N` on a registered source: a positive
integer, not a boolean, string, fraction or zero. It cannot combine with
`daily_from_collection: true`. The existing activation records the explicit source-to-interval
map once. Adding, editing or removing an interval after activation fails before attempts/writes;
do not rewrite activation or backfill historical work. Legacy omitted settings need no pin or
historical Git object. `verification validate` checks archived pin structure/source membership;
planning and running also require its exact match to current explicit settings.

Explicit slots are collection-anchored before issuance, issuance-anchored afterward, with actual
activation, issuance and final election-day duties. A late run binds `scheduled_for` to the latest
owed configured slot while retaining the actual check time and older missed work. Repeated polling
does not invent extra intervening attempt dates or inflate the three-distinct-slot escalation.
`due`/`next_due` describe attempt work, not evidence age. `refresh_interval_days`, `scheduled_for`
and cadence `interval` appear only for explicitly configured sources.

`freshness_due_at` uses the last actual completed manual review or approved live check plus elapsed
UTC days. Failed, fixture, unapproved, handled-access and administrative observations never advance
that anchor. With omitted defaults, regular issuance shortens a future weekly deadline while
preserving earlier debt and a full 24 hours since success; SGN remains daily from collection.
When a real evaluation clock is available, `freshness_due` is true at the deadline and
`freshness_overdue` only after it. `run --checked-at` supplies its actual clock. A read-only example:

```bash
uv run election-guide verification plan config/verification.yaml \
  --as-of 2026-10-27 --as-of-at 2026-10-27T18:00:00Z
```

The clock must include a timezone and match `--as-of` in Pacific time. Omit `--as-of-at` for a
date-only plan; within-day freshness booleans are then absent. Without a genuinely timed success,
the deadline remains unknown. Do not infer a midnight success from an old dated facts document.
None of these reporting states removes canonical verified evidence, permits release vetoes,
performs publisher access, changes the current cron, or grants #497 adoption/reuse credit.

The legacy `freshness` label describes the latest observation/review/access condition, not its
elapsed age. Read `freshness_due_at`, `freshness_due` and `freshness_overdue` for age; a last
successful observation can remain the latest observation while its next freshness deadline is overdue.

## Git-backed evidence

The workflow continues `codex/endorsement-verification-state`, merges current
`main` into it, and opens/updates an ordinary evidence PR. It does not auto-merge.
Independent runs reuse that branch while the PR awaits review, so pending data
cannot disappear or be replaced with an older mainline baseline.

`data/verification/<election>/` contains immutable JSON records:

- `activation.json`: actual activation date and producing revision.
- `checks/`: scheduled slot, actual check time, mode, result, event reference.
- `refreshes/`, `extractions/`: factual comparison snapshots and immutable events.
- `manifests/`: current observed-only provenance, hashes and byte lengths with no storage reference.
- `vault/sha256/<prefix>/<digest>.json`: unchanged legacy ciphertext, never new normal-run output.
- `discovery/`: successful index/article capture links, known/listed articles, derived hash.
- `discovery-obligations/`: validated newly learned UFCW, TRU and SGN URLs bound to
  their actual observed index/landing manifest before later pagination/article work can fail.
- `approvals/`: explicit actual-reviewer attestations bound to a live factual snapshot.

`data/verification/runs/` records the exact producing revision, due coverage,
actual results, policy fingerprint, and fixture/live mode. `source_tree_dirty`
identifies a local exercise with uncommitted source; it cannot prove a deployed
revision. Git commits preserve the whole record set;
tasks link to the full committed SHA, not a moving branch or expiring artifact.
Public validation checks record identities,
source/hash/time/reference joins, factual snapshots and approvals, plus legacy envelope metadata.
No normal path decrypts historical pages or reads an evidence key.

A public factual baseline consists of endorsement facts, official URL, actual check timestamp,
actual reviewer and review timestamp. This is sufficient durable evidence; full-page reconstruction
is not required. An observed-only manifest establishes metadata/facts provenance, not retained
original bytes or publisher authorship. Every successful fetch, including unchanged bytes,
preserves its current actual URL, time and HTTP metadata. Unchanged checks reference the exact
prior factual snapshot/approval through validated source/hash links; they do not claim the
reviewer personally re-read the source on the new check date. First, changed and unapproved
baselines still require official-source review. Parse failures retain any available observations
without promoting a new baseline.

Current source responses remain transient/private and are discarded at transaction end. Normal
verification, validation, factual approval, reconciliation and independent reuse require no evidence key,
restored pages, new full-page plaintext/ciphertext or replacement service. The archive App and
ordinary GitHub issue/deployment authentication retain their existing roles. Migration preserves
all historical IDs, records, ciphertext, exact factual approvals, failures/counters and releases
unchanged; it grants no new approval, fresh source read or backdated check.

SGN's comparison artifact contains article headings and original-body hashes.
It is explicitly marked as derived/manual-upload, with no invented HTTP status.
Every actual HTTP index and article response has its own current observed-only
HTTP manifest and content fingerprint. SGN records newly learned canonical story obligations
against the current observed index before later pagination or article collection can fail,
then revisits them across independent runners and link rotation. Article URLs use stable
story IDs; a title edit cannot turn one article into two identities. Missing boundary, ambiguous/looping
pagination, inaccessible article, or exceeded bounds fails the check. Discovery
allows at most 40 index pages, 100 articles, and 64 MiB total response bytes;
each HTTP fetch retains the existing public-peer, redirect, time, and size limits.

UFCW 3000 scans only its endorsements landing page for relevant current-year
news article links, then revisits every retained article URL, including both
known October 15 initiative publications when their links are absent. It does
not follow news feeds, pagination, unrelated news, or historical article links.
Successful discovery records and separate immutable discovery obligations persist
article membership across runners. Obligations are written after bounded official
URL validation, before required articles are fetched, and link to the current
observed landing manifest. A failed fetch or parse therefore cannot erase newly
learned URLs when landing links rotate off. An obligation asserts neither a
successful complete comparison nor baseline approval. A maximum of
100 articles and 64 MiB of total response bytes bounds each check; the existing
per-request GET safeguards remain in effect. Required article fetch or parsing
failure records a failed check and retains the prior comparison baseline.

Its derived comparison transiently supplies the landing page to the existing factual
extractor and binds all complete original article URLs and content hashes; only the
facts, fingerprints and provenance survive the private temporary transaction.
Article-only edits, including corrections and withdrawals, therefore produce a
changed-byte review lead even with zero recognized decision changes. Each actual
HTTP response has a separate observed-only manifest with actual metadata;
the composite has derived/manual-upload provenance and no HTTP status. Review
the entire expanded publication and exact new snapshot before approving this
baseline. The October 18 landing-page approval cannot approve the new composite.
Fixture-controlled independent reuse does not establish live scheduled adoption.

## Results and finite review tasks

The Calendar watcher reads committed archive state independently of the source
job. It uses the pending archive branch when present, or the checked-out mainline
state after an evidence PR merges and its branch is deleted. Both workflows
share `election-maintenance` concurrency, which serializes
read/create/append across scheduled and manual runs. Local reconciliation must
also be run by one operator at a time. Use the workflow for overlapping requests.

One issue per election/Pacific day ends with
`endorsement-verification: <election>/<date>`. It uses `type: ops`,
`area: operations`, `data: endorsements`, and the election milestone. Each
comment ends with an immutable `endorsement-observation:` marker. The tracker
reads all open/closed issues and their comments directly, never search indexing.
Retries append only absent observations and reopen a completed daily task when
new work arrives. Human-authored bodies and comments are preserved.

| Result | Action |
|---|---|
| First baseline or unapproved zero diff | Official-source review of the entire publication and mappings by the actual authorized reviewer. |
| Identical bytes with approved live snapshot | Retain a successful check; no source review section. |
| Added/changed/removed decisions | Include canonical IDs and immutable event/capture references. |
| Changed bytes with zero recognized decision diff | Review wording, new/unrecognized decisions, article body, and parser coverage. Never silently trust it. |
| Fetch or parser failure | Retain the prior comparison snapshot; append the failure. |
| Missing scheduled event | Independent watcher reports the missing slot, even when the source job produced nothing. |
| Manual obligation | Review due on the explicit date; record the actual authorized reviewer and evidence when complete. |

Fixed mappings do not guess a newly named candidate. Byte changes always require
review, including when the semantic extractor cannot recognize a new decision.
An adapter correction can produce a changed canonical decision on the next
refresh. A removal is a lead to distinguish genuine withdrawal from a parser
break through official-source review. HTML extraction retains its review flag.

After three consecutive failed/missing scheduled slots, add `priority: high`
and an explicit diagnosis request. Multiple attempts in one slot count once;
a successful slot breaks the streak. First startup without any committed state
produces a current-day startup task, with no invented past checks. Three
consecutive observed startup days also escalate using the watcher’s existing
issue markers; absence of a source-job record cannot suppress the startup alert indefinitely.

Resolve each observation through a reviewed adapter correction or endorsement
change, linking the merged PR and applicable release/publication evidence. Close
the finite task after every source obligation is resolved; never use #497 or a
permanent rolling issue as the future maintenance queue.

When a reviewed change alters the published aggregate or a position page, include an
[Updates entry](../RESULTS.md#the-updates-page) in the same publication change. New endorsements
qualify even when the leading choice is unchanged. The entry explains the change and links its
evidence and affected pages; a grouped entry links the complete reviewed packet. A successful
check that changes no published content needs no entry. Follow the
[release procedure](../RELEASE.md#public-update-log) when publishing it.

## Operator procedure and recovery

Before enabling the schedule, confirm the archive App's existing contents, PR and workflow
permissions and ordinary issue-write credentials. Review the public factual baseline and its
actual approvals. There is no evidence key setup or historical-page recovery prerequisite.

Inspect coverage without fetching:

```bash
uv run election-guide verification plan config/verification.yaml --as-of 2026-10-05
uv run election-guide verification validate config/verification.yaml
```

Run a controlled offline exercise with the factual fixtures, no evidence key,
and a separate state root. Never seed production state with fixture checks.
Run the same state again on the next scheduled date and inspect baseline reuse,
then use `reconcile --dry-run` to inspect task sections without issue mutation.
Record the exact revision and `source_tree_dirty`, controlled clock/due set, first/fresh-runner
public baseline reuse, manual queue, failed/missing-slot results and routing. State fixture mode
honestly: fixture baselines remain unapproved and are not native scheduled acceptance.
The CLI requires `--live` or `--fixtures` explicitly; ordinary tests never fetch.

For a real run, use the scheduled workflow or dispatch it. A failed source is
retried at the next scheduled slot. Inspect the archive PR and day's task. If a
job stops before committing, the next run starts from the last committed state;
the independent watcher reports the missed slot. If issue writes fail after the
archive push, repeat reconciliation against that SHA: markers prevent duplicates.
If the archive branch is accidentally removed, restore its latest verified commit
from the evidence PR/mainline before resuming. Preserve pending captures and
attestations; do not restart from an older baseline.

For factual baseline review, check out the current archive branch and validate its public
records. Compare the exact snapshot's facts and complete supported mappings against the current
official publication, including new/unrecognized wording, article membership and required images.
Use legitimate source access; a blocked fetch, failed parser or missing required article is a
failure/limitation, never a successful acknowledgement. Review/fix normal source-fetch errors
within the existing public-peer, redirect, time and size bounds. No old page restoration is needed.
Record the actual reviewer (human or explicitly delegated), actual time and official-source
review reference, then commit the attestation through normal PR review:

```bash
uv run election-guide verification approve-baseline data/verification/wa-2026-general \
  --snapshot-id <extraction-id> --reviewer <reviewer> --reviewed-at <actual-UTC-time> \
  --evidence <durable-spot-check-reference>
```

Fixture snapshots cannot receive live approval. For manual obligations use
`verification acknowledge-manual` with election root, `--source-id`,
`--scheduled-for`, `--reviewer`, `--reviewed-at`, and `--evidence`, then review and
commit that attestation with the actual actor/time. Neither command approves an endorsement ledger edit.

`verification reconcile` requires `--repository`, exact `--revision`, and
`--as-of`. Mutation verifies that local archive bytes exactly match that commit
before publishing links. `--watch` adds missing checks; `--dry-run` prints the
proposed sections without GitHub writes and permits an uncommitted local exercise.

Failed checks can report a fixed operation stage and failure category, with a validated
HTTP status where available. These bounded diagnostics retain no arbitrary exception
text and do not by themselves establish a cause, recovery or source approval.

## Approved future access disposition (#589, partial milestone)

Apply [the canonical source-access policy](../../SOURCE_POLICY.md#verified-endorsements-survive-failed-access):
retain the latest verified decisions/evidence through denial, timeout, empty or incomplete retrieval.
Keep the failed observation, true last success, retries and escalation explicit. Do not interpret
missing input as withdrawal, install an access-only publication block or require an exception to
retain verified facts. A later complete publication can add reviewed decisions; actual contradictory
or withdrawal evidence still requires normal factual review. The task-handling qualification below
does not control whether already accepted evidence remains canonical.

The maintainer's October 27 UTC approval permits retaining accepted facts with an explicit
limitation after a future pure access failure following a complete accepted initial review.
`config/verification.yaml` schema 1.1 starts this default with Pacific slots on October 27;
weekly/daily frequency, normal automatic attempts, calendar/24-hour boundaries and genuine
three-slot escalation are unchanged. This does not complete #589's unapproved interval/other
criteria, adopt #497, close #616 or resolve an earlier dated obligation by policy migration.

Before qualifying a source, establish the COMPLETE accepted official-publication/mapping review
from actual existing facts and review evidence. Do not infer it from a normal manual acknowledgement
or baseline approval. Propose one attestation with exact source/election, explicit complete scope,
official URLs, original actual check time and named reviewer/review time, and one ordinary durable
facts/review reference. An immutable record path or commit-qualified reference avoids ambiguity
when an existing document can change. Existing review packets retain their ordinary formats.
Normal protected versioned review establishes acceptance of the explicit claim; the new writing actor/time are
recorded separately. Unsupported actual scope remains unresolved without a new publisher fetch
merely to satisfy record formatting. Run from the repository root:

```bash
uv run election-guide verification qualify-initial-review data/verification/wa-2026-general \
  --source-id <registered-source> --scope complete_official_publication_and_mappings \
  --official-url <official-publication-URL> --checked-at <actual-original-check-time> \
  --reviewer <actual-original-reviewer> --reviewed-at <actual-original-review-time> \
  --evidence <ordinary-durable-facts-review-reference> --recorded-by <actual-writing-actor>
```

Commit the proposed record through normal protected review. Pending archive-branch presence is
not sufficient: eligibility compares its exact bytes with the canonical archive blob in the
already available local `origin/main` snapshot. No network request is made for admission. The
normal workflow already fetches/merges main; if proof is unavailable or bytes differ, leave the
obligation unresolved. Structural validation still permits unmerged proposals. A later main
admission never changes a disposition already recorded on an older failed check.

For a genuinely observed manual failed request, preserve its actual observer/time and durable
bounded diagnostic reference. The following records an observation; it performs no source GET
and claims no successful acknowledgement or HTTP response body:

```bash
uv run election-guide verification record-access-failure config/verification.yaml \
  --election-id wa-2026-general --source-id <registered-manual-source> \
  --scheduled-for <Pacific-slot> --checked-at <actual-UTC-time> \
  --reviewer <actual-observer> --evidence <actual-failure-reference> \
  --category http_status --http-status 403
```

Only supported typed HTTP status/deadline/DNS/TLS access failures can carry the new limitation;
unknown, generic OS/network, parser, partial/conflicting publication and safety failures do not.
An older ambiguous failure remains unresolved without blocking a separate later typed pure-access
attempt. Positive intervening changed content, failed observed response/comparison or a typed
parse/incomplete/conflicting-publication reason still requires a later complete accepted review.
Never backfill such a reason or an HTTP diagnosis onto an old event; all older obligations remain.
Automatic sources continue their existing automatic path. A qualifier must already exist when
the new failed observation is recorded and predate its check; it cannot resolve an old check.
All historical failures, six automatic attempts, baseline approvals, ciphertext and IDs remain.
Legacy sources without demonstrable complete-review evidence remain unresolved; no qualification
is supplied by this implementation or its fixture tests.

Inspect `verification plan` for actual last success, latest failed attempt, freshness limitation
and next normal due date. `reconcile --dry-run` keeps failed statuses and escalation explicit.
A handled-only observation does not reopen an already closed dated task, but a new unresolved
observation does. Operators still close a finite task only after all other criteria pass;
reconciliation performs no automatic whole-task closure. Historical scoped SEIU closure authority
is separate; #616 remains the finite recovery follow-up.

## Legacy encrypted custody

Historical `verification seal` and `verification restore` utilities remain documented in
[EVIDENCE_CAPTURE.md](../EVIDENCE_CAPTURE.md#legacy-encrypted-custody-497). They operate only
on the retained legacy custody records with the original private key; they are not normal
verification, review, validation, reconciliation, migration or adoption prerequisites. Preserve
legacy ciphertext and keys; this implementation does not rotate, replace or delete them.

## Adoption evidence and postmortem notes

The dated notes below retain the original encrypted-custody facts, failures, instructions and
then-pending acceptance exactly as recorded. Their old vault/restoration steps are historical,
superseded for current/future operation by the October 23 factual contract above. Previously
accepted WFP factual review and native reuse remain accepted progress; they neither fabricate a
new source read nor establish the deployed secret-free six-source process. No historical full-page
reconstruction or forensic original-page audit is promised. Complete #497 only with the full
revised live evidence, including later independent normal scheduled reuse, honest manual queue,
genuine source recovery/approved coverage decision and applicable reviewed delivery verification.
See the [accepted design](../superpowers/specs/2026-10-23-secret-free-endorsement-verification-design.md)
and [implementation record](../superpowers/plans/2026-10-23-secret-free-endorsement-verification.md).

### October 24 SEIU 775 adoption-only coverage decision

At **2026-10-24T13:55:08Z**, maintainer **Scott** directly approved allowing #497 adoption
despite SEIU 775's persistent HTTP 403, provided the other five automatic sources have complete
current official factual baselines, real normal due-source scheduled execution, later independent
normal scheduled reuse of those reviewed baselines, and applicable reviewed delivery verification.
This changes only SEIU 775's adoption gate. It does not establish source recovery, a new baseline
approval, a successful check or completed adoption. #497 remains **open** and this runbook remains
**proposed** until the complete remaining acceptance packet exists.

All six sources stay in the automatic-attempt lane with ordinary daily retries, unchanged cadence
and existing access safeguards. The [October 24 observation](https://github.com/shaug/seattle-election-guide/issues/616#issuecomment-6382513458)
remains **failed**: HTTP 403, the eighth consecutive scheduled failure and an active escalation.
Keep the prior usable 29-fact SEIU 775 baseline, provenance, failure counters and immutable history.
The exception grants no source removal/reclassification, collector or adapter change, new source
review, data change, access-control bypass or release authority.

SEIU 775 access remains unresolved. Keep that follow-up explicit in the existing finite
[October 24 task #616](https://github.com/shaug/seattle-election-guide/issues/616) and subsequent
ordinary election/day failure tasks until supported recovery is verified. Adoption does not resolve
those failed observations or permit closing a daily task with unresolved source obligations.
Do not create a duplicate access task or permanent rolling maintenance queue. Earlier dated notes
below retain the requirements and observations in force when they were written.

### October 19 explicit delegation

For the current October 19 transaction, the maintainer directly delegated source checks and necessary endorsement changes to Codex without a separate approval prompt. The [transaction record](../GENERAL_VERIFICATION_2026-10-19.md) describes this scoped exception to the usual separate human spot-check and identifies the actual delegated reviewers. The existing manual commands retain their legacy `human` mode; evidence must explicitly name the Codex reviewer and delegation rather than asserting a new personal human source read. This does not authorize future unattended judgments, acknowledge inaccessible publications, approve fixtures, or convert an operator recovery into scheduled adoption evidence.

### Delegated completion of #497

The maintainer's same delivery instruction also covers the actual source reviews
needed to finish this finite #497 adoption transaction, including the new complete
WFP and UFCW baselines captured after these collector corrections deploy. Record
the actual Codex reviewer, review time, exact live snapshot and official-source
evidence; do not assert a personal maintainer read. This delegation ends with
this delivery transaction and grants no recurring unattended interpretation or
approval of later endorsement changes.

Keep the normal cadence and immutable history intact. A fixture, operator check,
or no-due run cannot stand in for the required independent scheduled execution.

A failed automatic fetch does not establish that an ordinary browser is denied access.
An authorized public browser view or supplied PDF/image can support normal factual review,
while respecting source-access restrictions. Record the official URL, actual observation or
known capture time, named reviewer and review time, covered races/choices, allocations and
limitations in the existing facts-only recheck packet. Keep full third-party artifacts private.
An unchanged comparison needs no ledger rewrite; additions or changes still require normal
factual admission and protected delivery. See the [SEIU supplied-snapshot recheck](../../data/review/rechecks/wa-2026-general-2026-10-27-seiu-supplied-snapshot.json).

That review creates no automatic success, native-snapshot approval, scheduled reuse or failure
reset. All six automatic lanes, ordinary attempts, cadence and access safeguards remain intact.
Incomplete or unreviewed scope remains explicit.

Future direct HTTP-fetch failures may append a bounded observation of the actual response
status or no response, followed-redirect count, and same-origin/cross-origin/refused class.
The fixed failure classification remains unchanged; challenge stays `UNKNOWN`, not a WAF
finding. The note contains no URLs, header values, environment data or response body and
does not change access or retry behavior.

### October 20 delegated daily reviews

The same finite delivery instruction covers the October 20 manual-source checks
and their actual-time acknowledgements. The [dated review record](../GENERAL_MANUAL_REVIEWS_2026-10-20.md)
names the actual delegated Codex reviewers and distinguishes completed publication
reviews, held omissions, prior approved interpretations and inaccessible sources.
This scoped exception to a separate human prompt asserts no personal maintainer
source read or future unattended interpretation authority. Keep failed requests,
private originals and the later native adoption requirement intact; the October 19
Times override supplies no October 20 success or general failure policy.

### October 21 delegated daily reviews and WFP reuse

The finite delivery instruction also covers the actual October 21 source checks
in [#593](https://github.com/shaug/seattle-election-guide/issues/593), including
necessary explicit endorsement additions through the ordinary evidence/manual
adapter and versioned release. Name each actual Codex researcher and verifier;
retain prior decisions, interpretations and failed access observations. This is
no personal maintainer source read or recurring unattended approval authority.
An inaccessible publication receives no successful acknowledgement.

WFP's [October 21 independent native scheduled reuse](../GENERAL_BASELINE_REUSE_2026-10-21_WFP.md)
now supplies that source's later-use evidence after its exact October 20 review.
It does not adopt the six-source system: changed unapproved originals, source
failures, complete manual coverage and other source-specific acceptance remain
open. TRU's separate ordinary October 21 diagnostic observed a registered-page
404 and an official-home maintenance notice. Preserve its native failure; do not
claim a parser defect, scheduled recovery or permission to alter cadence from
that separate observation.

### October 19 WFP complete-publication correction (#497)

WFP's initial page exposes only five of the ten approved in-inventory choices.
The public complete-list request is POST
`https://workingfamilies.org/wp-admin/admin-ajax.php`, URL-encoded form
`action=more_candidates&state=25&count=0`. GET with the same query returns an empty
body and cannot replace it. The reviewed public response contained 17 Washington
rows, including all ten approved choices and seven rows outside the frozen
inventory. The retained original is 2383 bytes with SHA-256
`193b7dbe1a1e2883513cc49a6c434ab19689a377623774295d7c4fc994890574`;
root's actual October 19 capture completed at `2026-10-19T15:24:08.372959Z` with
HTTP 200 and no redirects, independently matching the earlier public probe.
The original remains private; this observation is source proof, not a scheduled
run or baseline approval.

The WFP policy binds that exact endpoint, method and form. Its adapter recognizes
all ten existing mappings, checks two nonempty cells per row, and excludes only
the seven reviewed out-of-inventory facts. Unknown or malformed rows fail while
retaining the prior baseline. The original response is archived through the
existing encrypted pipeline, with actual request provenance in the manifest note.
The October 18 initial-page approval does not approve this different complete
snapshot. Review its full live capture and mappings, then obtain an independent
scheduled reuse through the deployed workflow. Keep #497 open until the full
adoption packet below exists; fixture exercises cannot satisfy these obligations.

The first live run on October 15 exposed publication-layout gaps (#542): SGN's
article headline is an `h2.mb-3.font-weight-bold`, and WFP's national index now
groups candidates under a Washington section. The adapters also recognize
SEIU 775's current `I-` initiative labels and `Pos.` council labels alongside
the previously reviewed wording. These are the same existing ballot mappings;
new or changed choices still require human review. Authored offline layout
fixtures cover these differences without committing complete source pages.
SEIU 775's initial fetch failure did not reproduce during local diagnosis;
its page was reachable, so the HTTP timeout and access safeguards stay intact.

Required before marking adopted: exact deployed workflow revision and run URL;
current due/coverage output; all six live source outcomes and approved initial
baselines; a second independent run proving reuse; immutable evidence/task links;
manual queue and missing/failure reconciliation; and a green `make check`.
The current implementation tests fixture runs, task retries, and index edits.
Keep #497 open until the complete adoption packet exists. Append dated execution
lessons here after each adoption exercise.

### October 18 verification follow-up

The maintainer’s existing private 1Password backup authenticated all 71 archived
captures; no key was printed, replaced or committed. The exact six baseline
reviews now have explicit human approvals. Separate current human reviews resolve
111 manual obligations across 37 sources without backdating missed dates. See
[the baseline review](../GENERAL_BASELINES_2026-10-18.md) and
[manual review](../GENERAL_MANUAL_REVIEWS_2026-10-18.md). A subsequent explicit
[WEA/Sierra approval](../GENERAL_WEA_SIERRA_2026-10-18.md) records five more
actual-time manual acknowledgements after normal browser access recovered both
official lists. The subsequent user-supplied [Stranger image review](../GENERAL_STRANGER_2026-10-18.md) and explicit human approval resolve its final two date obligations. All 120 manual-source obligations for October 16–18 now have actual-time acknowledgements.

TRU’s bounded redirect loop came from serializing `Host: transitriders.org:443`
through an HTTP connection object whose default port was 80. Using an HTTPS
connection with the same existing TLS context and validated socket produces the
standard Host header and recovers HTTP 200 with zero redirects. The same correction
recovers OneAmerica’s original page. Six offline request-serialization cases cover
default and nondefault HTTP/HTTPS ports. Public-peer checks, TLS validation,
deadline, size, downgrade and ten-redirect limits are unchanged.

These results do not mark the runbook adopted. An independent scheduled cycle
must still prove approved baseline reuse through the deployed workflow. Current
remaining source obligations and publication status are tracked in the
[October 18 closeout](../GENERAL_VERIFICATION_CLOSEOUT_2026-10-18.md).

## October 21 TRU publication coverage correction

The [finite TRU packet](../GENERAL_RECHECK_2026-10-21_TRU.md) adds four separately
admitted formal measure facts and corrects automatic discovery under #593/#497.
TRU checks fetch complete official WordPress archives until the reviewed September
30 article appears, at most 40 archive pages, 100 required articles, 140 combined
original captures and 64 MiB total. Pagination accepts the official root and clean
increasing `/page/N/` identities only. The two known general articles, successful
prior memberships and valid durable learned obligations are revisited every check.
New valid links are recorded with their actual archive capture before later
pagination or any required article can fail. Invalid pending evidence is rejected
by public archive validation before a runner changes state.

The designated October article must still link the exact reviewed
`TRU_November_2026_General_Endorsements-1024x581.jpg` on the source-owned CDN.
That exact image is fetched through the same bounded transport on every check,
retained as an image original and hashed in full. A removed or unrecognized
replacement asset, unsafe/canonical identity, maintenance layout, malformed HTML,
missing boundary or failed required input fails the check and retains the prior
snapshot and already learned article obligations. There is no OCR, automatic
image interpretation or expansion to other CDN assets.

Only the designated October article supplies the twelve supported formal facts;
older/home duplicates never enter extraction. The separate qualified candidate
recommendations remain full hashed context, with no endorsed-status conversion.
All archive/article/image hashes and sorted membership bind the derived comparison.
An image-only or unrecognized text edit therefore creates review work with an empty
semantic diff. Originals retain actual HTTP provenance and encrypted custody; the
comparison is a derived manual upload without an invented HTTP response.

This correction approves neither the exact October 20 original nor a new complete
automatic TRU baseline. An expanded live snapshot requires its own actual full
source review and exact snapshot attestation, then later independent native
scheduled reuse/recovery evidence. The October 21 failed native check remains
unchanged. This runbook stays proposed; neither parent issue closes here.
