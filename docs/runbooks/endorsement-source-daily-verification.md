# Runbook: endorsement source daily verification

**Status: proposed, implementation awaiting adoption evidence (#497).** Keep this
status until the first live scheduled cycle, six human baseline spot-checks, and
independent baseline reuse have durable evidence. Fixture execution proves the
mechanism, not live publisher access or human approval.

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

Every eligible source appears in the coverage record. Adding another election
requires its own frozen registry, inventory, and reviewed adapters in the policy;
never copy primary or previous-cycle candidate mappings into a new ballot.
Policy validation rejects duplicate elections/sources, wrong-election inputs,
unknown or ineligible sources, invalid adapters, and contradictory anchors.

## Autonomy and coverage

Level 2 (Watched): capture, compare, preserve, and report. Human review retains
interpretation, transcription approval, baseline approval, ledger edits, PR
review, releases, and production approval. The detector does not modify the
published source decisions, source panel, scoring, or historical releases.

The first general-election tranche is:

| Source | Automatic publication check | Limitation |
|---|---|---|
| Transit Riders Union | Current general endorsement page | A bounded live probe currently exceeds the redirect limit. Keep failed checks visible; diagnose access without bypassing the limit. |
| Sage Leaders | Current 2026 section, excluding past-year sections | Fixed, reviewed factual mappings; changed bytes require review. |
| SEIU 775 | Washington section | Fixed, reviewed factual mappings; changed bytes require review. |
| UFCW 3000 | Official endorsements page | Fixed, reviewed factual mappings, including dual endorsements and publisher spelling variants. |
| Washington Working Families Party | Our Candidates section | Fixed, reviewed factual mappings; changed bytes require review. |
| Seattle Gay News | Current Seattle index plus known/new articles | Daily from collection opening. Traverse pagination to the reviewed oldest current-cycle article, then revisit every known article. |

These checks use `config/adapters/wa-2026-general/`; the older primary TRU adapter
remains separate. The factual fixtures preserve the current general mappings
reviewed in #474. They contain names and offices, not full third-party pages or
editorial prose. They do not approve the first automatic live baseline.

The six stay in the automatic-attempt lane, including an inaccessible source;
failures do not silently reduce coverage. TRU's access limitation prevents a
claim that all six have successful live coverage or that this runbook is adopted.
Resolve that limitation and verify the resulting live baseline before adoption.

All other eligible panel sources use manual review, including not-found,
restricted, social, dynamic, PDF, and image publications without an installed
adapter. Every scheduled manual obligation receives its due date in that day's
finite task. It does not count as successful verification until a human records
the review time and durable evidence reference. Comprehensive sweeps (#491,
#472, and later calendar checkpoints) retain their separate scope.

`verification plan` returns each lane, cadence, last successful human-verified
check, next due date, and limitation. Unapproved captures and fixture runs do not
populate the successful verification date.

## Git-backed evidence

The workflow continues `codex/endorsement-verification-state`, merges current
`main` into it, and opens/updates an ordinary evidence PR. It does not auto-merge.
Independent runs reuse that branch while the PR awaits review, so pending data
cannot disappear or be replaced with an older mainline baseline.

`data/verification/<election>/` contains immutable JSON records:

- `activation.json`: actual activation date and producing revision.
- `checks/`: scheduled slot, actual check time, mode, result, event reference.
- `refreshes/`, `extractions/`, `manifests/`: existing collection records.
- `vault/sha256/<prefix>/<digest>.json`: AES-256-GCM encrypted original bytes.
- `discovery/`: index/article capture links, known/listed articles, derived hash.
- `approvals/`: explicit human attestations bound to a live snapshot.

`data/verification/runs/` records the exact producing revision, due coverage,
actual results, policy fingerprint, and fixture/live mode. `source_tree_dirty`
identifies a local exercise with uncommitted source; it cannot prove a deployed
revision. Git commits preserve the whole record set;
tasks link to the full committed SHA, not a moving branch or expiring artifact.
Public validation checks record identities, references, and encrypted envelopes.
The keyed runner also authenticates and hashes every restored original capture.

The base64-encoded random 32-byte `ENDORSEMENT_EVIDENCE_KEY` is an Actions secret.
Keep a private recoverable copy under the maintainer's credential procedures.
Neither the key nor decrypted pages belong in Git, logs, or uploaded artifacts.
The workflow reuses the repository's archive GitHub App credentials for branch
and PR writes; its ordinary job token owns issue writes. No external evidence
service is used. Full restricted content is committed only as authenticated
ciphertext; public manifests, hashes, short factual excerpts, and review records
remain readable alongside the rest of the data.

Captures are decrypted only into a private temporary directory and removed at
transaction end. Changed bytes are sealed before their observation is published;
unchanged originals retain the existing ciphertext. Existing manifest IDs and
`storage_scope` semantics remain unchanged: the original raw capture is
`local_only`, while the verification vault is its separately validated encrypted
custody record. Restore reconstructs the same relative SHA-256 addresses.

SGN's comparison artifact contains article headings and original-body hashes.
It is explicitly marked as derived/manual-upload, with no invented HTTP status.
Every actual HTTP index and article response has its own encrypted original and
observed HTTP manifest. Article URLs use stable story IDs; a title edit cannot
turn one article into two identities. Missing boundary, ambiguous/looping
pagination, inaccessible article, or exceeded bounds fails the check. Discovery
allows at most 40 index pages, 100 articles, and 64 MiB total response bytes;
each HTTP fetch retains the existing public-peer, redirect, time, and size limits.

## Results and finite review tasks

The Calendar watcher reads committed archive state independently of the source
job. Both workflows share `election-maintenance` concurrency, which serializes
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
| First baseline or unapproved zero diff | Human spot-check of the entire publication and mappings. |
| Identical bytes with approved live snapshot | Retain a successful check; no source review section. |
| Added/changed/removed decisions | Include canonical IDs and immutable event/capture references. |
| Changed bytes with zero recognized decision diff | Review wording, new/unrecognized decisions, article body, and parser coverage. Never silently trust it. |
| Fetch or parser failure | Retain the prior comparison snapshot; append the failure. |
| Missing scheduled event | Independent watcher reports the missing slot, even when the source job produced nothing. |
| Manual obligation | Review due on the explicit date; record human evidence when complete. |

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
issue markers; a missing key cannot suppress the startup alert indefinitely.

Resolve each observation through a reviewed adapter correction or endorsement
change, linking the merged PR and applicable release/publication evidence. Close
the finite task after every source obligation is resolved; never use #497 or a
permanent rolling issue as the future maintenance queue.

## Operator procedure and recovery

Before enabling the schedule, configure the evidence key and confirm the archive
App has contents, PR, and workflow permissions. A missing or mismatched key
fails loudly. Do not replace the key to make a failure pass: historical ciphertext
requires the original key. Key rotation requires a separately reviewed migration;
never overwrite immutable captures. Losing every key copy loses recoverability.

Inspect coverage without fetching:

```bash
uv run election-guide verification plan config/verification.yaml --as-of 2026-10-05
uv run election-guide verification validate config/verification.yaml
```

Run a controlled offline exercise with the factual fixtures, a temporary test
key, and a separate state root. Never seed production state with fixture checks.
Run the same state again on the next scheduled date and inspect baseline reuse,
then use `reconcile --dry-run` to inspect task sections without issue mutation.
The CLI requires `--live` or `--fixtures` explicitly; ordinary tests never fetch.

For a real run, use the scheduled workflow or dispatch it. A failed source is
retried at the next scheduled slot. Inspect the archive PR and day's task. If a
job stops before committing, the next run starts from the last committed state;
the independent watcher reports the missed slot. If issue writes fail after the
archive push, repeat reconciliation against that SHA: markers prevent duplicates.
If the archive branch is accidentally removed, restore its latest verified commit
from the evidence PR/mainline before resuming. Preserve pending captures and
attestations; do not restart from an older baseline.

For human baseline review, check out the current archive branch, restore its vault
to an external private directory with `verification restore`, authenticate the
capture, and compare the entire official publication against its extraction.
Record the review, then commit the attestation through normal PR review:

```bash
uv run election-guide verification approve-baseline data/verification/wa-2026-general \
  --snapshot-id <extraction-id> --reviewer <reviewer> --reviewed-at <actual-UTC-time> \
  --evidence <durable-spot-check-reference>
```

Fixture snapshots cannot receive live approval. For manual obligations use
`verification acknowledge-manual` with election root, `--source-id`,
`--scheduled-for`, `--reviewer`, `--reviewed-at`, and `--evidence`, then review and
commit that attestation. Neither command approves an endorsement ledger edit.

`verification reconcile` requires `--repository`, exact `--revision`, and
`--as-of`. Mutation verifies that local archive bytes exactly match that commit
before publishing links. `--watch` adds missing checks; `--dry-run` prints the
proposed sections without GitHub writes and permits an uncommitted local exercise.

## Adoption evidence and postmortem notes

Required before marking adopted: exact deployed workflow revision and run URL;
current due/coverage output; all six live source outcomes and approved initial
baselines; a second independent run proving reuse; immutable evidence/task links;
manual queue and missing/failure reconciliation; and a green `make check`.
The current implementation tests fixture runs, task retries, and index edits.
Live deployment, the real encryption secret, baseline approval, and the first
scheduled cycle remain operator/adoption work. Keep #497 open until this packet
exists. Append dated execution lessons here after each adoption exercise.
