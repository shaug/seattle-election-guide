# Election-bounded operational evidence retention

Scope: [#768](https://github.com/shaug/seattle-election-guide/issues/768).

## Intent and boundary

Preserve the guide's factual integrity and useful change history, not a complete
backup of every review execution. The 2026 storage audit found 13.9 GB of custom
operational captures under `.git/delivery-sweep-20261019`, compared with about
295 MB in the working tree's entire `data/` directory. Operational archives are
not Git history and `git gc` does not remove them.

Root checkouts are source/reference locations, not implementation workspaces.
New run payloads belong in the owning isolated worktree. Cross-run receipts and
explicit shared caches belong in a separate, bounded operational store. Do not
copy full evidence stores, full diffs or build archives into each review attempt.

## Retention classes

| Class | Lifetime |
| --- | --- |
| Authoritative source bytes and manifests | Preserve while referenced by the guide or verifier, including other elections. |
| Published historical guide and structured decisions/corrections | Product history; not disposable operational output. |
| Compact receipts | Keep source/release/PR/CI identifiers, hashes, capture URLs/times, decision and exception records. No embedded full payload backups. |
| Active candidate/checkpoint | Keep until its owner completes or transfers the work. |
| Completed run's raw logs, repeated diffs, report copies and build archives | Candidate for retirement after completion, ownership, unique-work and reference verification. |
| Election-wide operational archive | Candidate at verified election closeout, not merely election day or arrival of the next cycle. |
| Deliberate rollback target/cache | Explicit purpose, owner, size limit and expiration; not an excuse to retain every prior state. |
| Unknown/unregistered legacy material | Hold until classified. Never infer ownership or obsolescence from a directory date alone. |

At election closeout, verify certified-results ingest and accepted publication,
extract the short retrospective, and retire election-specific operational history.
Shared artifacts remain held until *all* references permit retirement. By the next
election, old local validation archives need an explicit exception rather than
indefinite retention. Published archives are outside this local cleanup policy.

A digest can detect changed bytes when those bytes are available; it cannot replace
source bytes required by `evidence verify-all`. This policy does not weaken that
contract, remove source manifests, rewrite Git history or authorize deletion.
A future source-retirement change must update manifests, verifiers and consumers
together, with an explicit product decision about what historical verification
remains possible.

## First executable increment: declaration-based triage

```
election-guide evidence retention-plan /path/to/inventory.json
```

This command reads one inventory and prints a deterministic JSON report to stdout.
It performs no path traversal, writes, network calls, hashing or deletion. It is
**not** a live ownership check, cleanup executor, complete disk inventory, or proof
that a receipt's claims are true. Every report includes `deletion_authorized: false`.
Candidate byte totals are supplied inventory estimates, not measured APFS reclaim.

Example input (kept small; do not embed full source or review captures):

```json
{
  "schema_version": "1",
  "elections": {
    "wa-2026-general": {"phase": "active", "closeout_receipts": []}
  },
  "artifacts": [{
    "id": "review-42-command-log",
    "path": "runs/review-42/commands.jsonl",
    "kind": "operational",
    "elections": ["wa-2026-general"],
    "run_state": "completed",
    "owner": "review-42",
    "completion_receipt": "receipts/review-42.json",
    "active_consumers": [],
    "hold": null,
    "bytes": 12000
  }]
}
```

The `path` is an inventory key relative to a separate operational store, limited
to `runs/<owner>/<payload>`. It is not an instruction to follow a filesystem path.
This deliberately excludes raw repository `data/` and `.git` paths. Legacy sweep
material must first be mapped to owned runs; do not rename a directory just to
pass this constraint. The separate resource manager must validate real paths,
symlinks, overlaps, inode identity, current users and references before acting.

Allowed kinds: `operational`, `election-operational`, `source`, `published`,
`receipt`, `checkpoint`, `unknown`. Only the first two can become candidates.
Missing owner/completion declarations, active consumers, an explicit hold,
unknown election references and incomplete election closeout retain the payload.
For `election-operational`, every referenced election must declare `phase: closed`
and the closeout receipt categories `certified-ingest`, `accepted-release`, and
`retrospective`. Those labels are triage inputs only. The executor must verify the
actual immutable receipts; this planner does not establish election completion.

## Remaining enforcement work

The triage command is intentionally read-only. It does not yet stop capture writers
or clean old archives. Completion requires integration with the personal-project
resource manager: register every created payload and its references, enforce
bounded logs and caches, attach compact completion receipts, and reconcile missed
cleanup after crashes. Missing or contradictory proof must yield a visible hold,
not force deletion. Test normal and squash merges, interrupted closeout, active
owners, ignored/unique files, shared evidence and path substitution before enabling
removal. No current election is closed solely by this document or its examples.
