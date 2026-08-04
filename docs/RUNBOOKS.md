# Runbooks: formalizing the agentic runtime

This project runs on three layers, two of which are already formal:

1. **The site runtime** — the build and the browser, rendering fixed JSON deterministically.
2. **The deterministic toolbelt** — the `election-guide` CLI: evidence capture with
   content-addressed storage, the manual-entry adapter with dual review, collection refreshes
   with immutable snapshots and semantic diffs, calendar validation. Each command is a checkpoint
   where fuzzy work becomes verified state.
3. **The agentic runtime** — discovery, judgment, transcription, timing: the work of noticing
   that a source published, deciding what a page asserts, and capturing it at the right moment.
   Historically this layer lived in ad-hoc sessions with whatever agent tool was current, and its
   procedures lived in nobody's repository.

Runbooks are how the third layer becomes repository-owned. A runbook is a versioned procedure
document under `docs/runbooks/` that any agent session — or any human with a browser and the
CLI — can execute end to end. The agent harness is expected to change; the runbooks are not
married to one.

## The contract

The repository formalizes the agentic runtime's **contract**, never its implementation:

- **Triggers** live in `config/calendar/elections.yaml`. A milestone names the `workflow` (a
  real CLI command) and a `reference` (the runbook or design doc that explains the work).
  Validation resolves both, so a renamed command or moved runbook fails the suite, not the cycle.
- **Procedure** lives in the runbook: trigger, preconditions, steps with CLI checkpoints,
  verification, escalation. Runbooks carry domain procedure — URLs, commands, judgment
  criteria — not agent disposition.
- **State** lives in the repository, never in chat history. Any session must be resumable from
  the repo alone: evidence manifests, refresh events, and normalized data record what has
  happened; a runbook's postmortem notes record what was learned.
- **Gates** are non-negotiable and already exist: agent work enters bedrock data only through a
  deterministic CLI checkpoint; every mutation lands as a reviewable pull request; the
  production deploy approval is never automated.

Because the gates do the enforcing, the agentic layer never has to be trusted — which is
precisely what makes it replaceable.

## Autonomy levels

Formalization is a dial, not a switch. Each level removes a piece of human attention while the
human's *judgment* — PR review and deploy approval — is never automated at any level:

| Level | Name       | What it removes                                                        |
| ----- | ---------- | ---------------------------------------------------------------------- |
| 0     | Declared   | Remembering dates: the calendar is repository data.                    |
| 1     | Scheduled  | Polling the calendar: due milestones open tracking issues (#220).      |
| 2     | Watched    | Noticing omissions: a milestone whose promised artifact never appeared escalates its issue (#279). |
| 3     | Dispatched | Launching the session: the tracking issue triggers an unattended agent run whose only output is a PR. |

Every runbook declares its own level. Mechanical, timing-critical work (results capture) is a
candidate for level 3; judgment-heavy work (endorsement decisions) should stay human-launched
even when everything around it is automated. The declaration is versioned repo state: raising a
runbook's autonomy is a reviewed change, not a habit.

Levels 1 and 2 are deterministic — a scheduled GitHub Actions job reading the calendar; no agent
involved. Level 1 is #220 (unchanged in scope); level 2 is its follow-up, #279. Level 3 is
per-runbook opt-in and needs no new infrastructure design until a runbook wants it.

## Runbook anatomy

Every runbook carries these sections, in order:

- **Trigger** — the calendar milestone (or condition) that makes it due.
- **Autonomy** — the declared level, and what specifically requires a human today.
- **Preconditions** — what must exist before starting; how to verify from the repo alone.
- **Procedure** — numbered steps. Every state mutation is a CLI command; anything the CLI would
  reject must not be worked around.
- **Verification** — how the executor proves the work landed (hashes verify, validators pass).
- **Escalation** — the conditions under which the executor stops and asks a human, stated
  concretely.
- **Postmortem notes** — dated observations appended after each execution. Runbooks are code:
  each run is a test, and what it teaches gets committed.

## Event horizons

The recurring workflows differ in profile but share the contract:

- **Results** (per election): a bounded window with one known authority and statutory timing.
  Timing-critical, judgment-light — the calendar drives it almost entirely. Runbooks:
  `results-capture-election-night.md`, `results-certified-ingest.md`.
- **Endorsements** (per election): an unbounded window across many sources with unknown
  publication times. Judgment-heavy, timing-tolerant — cadence belongs to the source registry,
  and the runbook's weight is in decision criteria. Runbook: planned; it should be written when
  the 2026 general's collection window opens, from the procedures the primary's collection
  actually followed.

## Index

Each runbook's autonomy level is declared in the runbook itself — its single owner.

| Runbook                                       | Trigger                              |
| --------------------------------------------- | ------------------------------------ |
| `runbooks/results-capture-election-night.md`  | `results_capture_election_night`     |
| `runbooks/results-certified-ingest.md`        | `results_capture_post_certification` |
| Endorsement discovery sweep — planned; write at the general's `collection_opens` | `collection_opens` → `refresh` |
