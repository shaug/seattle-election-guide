# Secret-Free Endorsement Verification Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make #497 recurring verification operate from reviewed public endorsement facts with no evidence-encryption secret or historical-page dependency.

**Architecture:** Reuse existing manifests, extraction snapshots, semantic diffs, immutable checks and reviewer approvals. Add an explicit observed-only manifest and facts-only retention path, keep transient source responses private, and preserve legacy records unchanged. Ship implementation/policy together; complete real scheduled acceptance afterward.

**Tech Stack:** Existing Python/Pydantic collectors, pytest fixtures, Git-backed JSON and GitHub Actions. No new service or dependency.

**Spec:** `docs/superpowers/specs/2026-10-23-secret-free-endorsement-verification-design.md`.

## Global Constraints

- Durable evidence is endorsement facts, official URL, actual check timestamp and named actual reviewer. Full historical pages are not required.
- No normal verification/validation/reconciliation/approval/reuse operation reads `ENDORSEMENT_EVIDENCE_KEY` or restores old pages. No replacement evidence secret/service.
- Preserve all historical IDs/records/ciphertext/approvals/failures/releases. Existing approved facts remain precisely attributed; migration grants no new approval or fresh source read.
- Preserve six automatic sources,46 frozen-panel lanes, calendar cadence, source access/HTTP bounds, discovery/completeness guards, scoring and ledger/release authority. No new UI.
- Every first/changed/unapproved factual baseline requires official-source review. Automated checks reference approvals; they do not claim a human re-read.
- Run `make check` before proposing a diff and obtain fresh complete canonical review/protected checks. Release/deploy through the existing immutable automatic workflow where requested by changed paths. Keep #497 open until real adoption evidence exists.

## Review Focus

- Legacy snapshot references must work without old raw files or key access; malformed or cross-source public records still fail validation.
- HTTP errors, unknown/empty parser output and newly discovered/missing articles must not become unchanged success.
- An article-only change must remain visible even when extracted candidate IDs do not change.
- Check time, review time and reviewer identity must remain separate and truthful across independent automated runs.
- Failure recovery and fresh-runner migration must preserve last approved facts, historical failure counters and exact old record bytes.

### Task 1: Public observation records and facts-only refresh

**Files:** `src/election_guide/evidence/models.py`, `evidence/storage.py`, `evidence/manual.py`, `collection/refresh.py`; tests `test_evidence.py`, `test_collection.py`, `test_verification_runtime.py`.

**Interfaces:** Add `ObservedManifest(CaptureRequest)` with identified capture-style ID, `availability: Literal["observed"]`, `content_sha256`, `byte_length`, no storage reference, and the existing canonical record-hash/time/source identity constraints. Extend `CaptureManifest`/reader explicitly. Preserve the retained-artifact manual import boundary with an intentional observed-only rejection in `evidence/manual.py`/byte verification, never an accidental missing-field error. Add `record_observation(request: CaptureRequest, input_path: Path, manifest_dir: Path) -> Path`, which writes only canonical metadata and never retains the input file. Extend `refresh_source(..., retention: Literal["retain_original", "facts_only"] = "retain_original") -> RefreshEvent` without changing existing arguments/default behavior. Existing extraction/event models and `semantic_diff` remain the factual representation.

- [ ] Inspect current accepted main, live497 scope and source contracts; reuse an isolated clean implementation workspace and record ownership. The planning branch is not a delivery base; integrate actual then-main through the normal process. Add no new dependency.
- [ ] Write failing tests for an observed-only record with source URL/time/hash/size, missing/unsafe identity, tampered record hash, no `storage_reference`, and byte-verification refusing to claim a retained original. Test unchanged legacy manifest bytes/IDs and default retained capture behavior.
- [ ] Write failing facts-only refresh tests: first snapshot, same-content reuse, added/changed/removed facts, changed extractor fingerprint, missing old raw files and a legacy previous snapshot. Missing/corrupt/cross-source public metadata still fails; failures preserve the previous committed snapshot. Set the evidence key absent and make any attempted vault restore/read raise. Require a fresh observation on every successful fetch, including unchanged content with allowed canonical-URL/HTTP-metadata changes: event.capture_id points to the new observation, snapshot_id and approval remain the old ones, and source/hash joins validate. Retain the fetched observation on parse failure where available.
- [ ] Add only the observation model/writer and explicit refresh retention branch. Validate previous public references/hashes in facts-only mode; retain original-byte verification in the default path. Share existing extraction/event/locking/immutable-writing logic rather than duplicating a refresh pipeline. In facts-only mode create the observation before the unchanged shortcut or parse attempt and do not deduplicate away current fetch metadata via `_capture_for_content`.
- [ ] Run `uv run pytest tests/test_evidence.py tests/test_collection.py tests/test_verification_runtime.py -q`; require the targeted RED cases to become GREEN and existing retained-capture tests remain green. Commit the bounded change and obtain fresh Task review.

### Task 2: Use facts-only evidence throughout the scheduled collectors

**Files:** `collection/verification_runtime.py`, `verification_state.py`, `verification_cli.py`, `verification_review.py`, `verification_tasks.py`, `discovery.py`, `tru_discovery.py` and existing collector entrypoints that call `record_capture`; `.github/workflows/endorsement-verification.yml`. Tests: `test_verification_runtime.py`, `test_verification_sources.py`, `test_verification_discovery.py`, `test_verification_tru.py`, `test_verification_ufcw.py`, `test_verification_wfp.py`, `test_verification_workflows.py`, `test_verification_tasks.py`.

**Interfaces:** Recurring `run_verification(...)`/CLI keep their existing call/return contracts and select Task 1 `retention="facts_only"`. Existing discovery/collector entrypoints accept and propagate the same retention keyword, defaulting to original retention for unrelated callers. Archive validation accepts observed manifests as public evidence and legacy captured/vault envelopes as unchanged historical metadata. Validate each event's current observation against the reused snapshot's source/content hash without requiring their capture IDs to be identical. Add `SgnDiscoveryObligation` and `read_sgn_discovery_obligation(path: Path)` in existing `discovery.py`; record validated story membership before article work and explicitly dispatch that type in `verification_state.py`. `approve_baseline(...)` keeps its existing signature and writes the real reviewer/time against the exact factual snapshot; no key/original requirement is added. Normal manual acknowledgements retain their explicit due-slot/reviewer/evidence references.

- [ ] Add failing fixture regressions for all six automatic sources with no evidence key, including a second clean runner reusing the first runner's committed public records with no private capture directory. Add a legacy-mixed history case and assert all old file bodies are identical afterward.
- [ ] Add failing discovery regressions for new articles, article-only edits, rotated-away known links, incomplete required article fetches, image/body fingerprints, malformed parser output and existing public-peer bounds. Keep existing source matching and publication completeness assertions; do not lower thresholds. Pin the SGN two-run case explicitly: new URL discovered -> required article fetch/parser fails -> URL rotates off index -> fresh runner still attempts it and cannot report unchanged until all required work succeeds. Store only the existing obligation-pattern URL/metadata, with no new discovery framework.
- [ ] Add reviewer/coverage/task regressions: unchanged checks reuse an existing approval without changing its actor/date; unapproved snapshots remain unapproved; first/changed baselines require real review; failure and missed-slot routing preserve counters and same-day idempotency. No successful check may fabricate a fresh human review.
- [ ] Remove `read_key`, `restore_store` and `seal_store` from normal runtime. Keep actual new responses private/transient and publish only observations/facts/events/checks/discovery metadata. Propagate facts-only mode when each composite response is initially observed, so IDs/references are born truthful; do not rewrite published graphs afterward.
- [ ] Update archive validation and discovery manifest typing for both explicit record types. Validate all public identities/source/hash relationships; no restored raw file is required in the new path. Legacy encrypted files are not re-authenticated with a key during normal checks. Explicit legacy vault commands/tests may remain; do not delete the secret or historical files.
- [ ] Remove only `ENDORSEMENT_EVIDENCE_KEY` from the scheduled workflow environment. Keep ordinary repository/App authentication, concurrency group, cadence, source limits and protected publication behavior. Update stale task recovery advice that currently requires an evidence key.
- [ ] Run `uv run pytest tests/test_verification*.py -q` and the affected discovery/collection tests. Require new source operations to produce zero vault entries/full-page outputs and retain exact legacy bytes. Commit and obtain fresh Task review.

### Task 3: Align policy, runbook and operator instructions; deliver the implementation

**Files:** `SOURCE_POLICY.md`, `ARCHITECTURE.md`, `REVIEW_GUIDE.md`, `docs/COLLECTION.md`, `docs/EVIDENCE_CAPTURE.md`, `docs/RUNBOOKS.md`, `docs/runbooks/endorsement-source-daily-verification.md`, `.github/endorsement-verification-pr.md`; affected documentation-contract tests in `test_verification_workflows.py`, `test_verification_tasks.py`, `test_collection.py`. Include this spec/plan in the implementation record.

**Interfaces:** Consume Tasks1/2 and the revised live497 criteria. Produce one coherent, tested policy/runtime delivery; runbook remains proposed pending live acceptance. Historical descriptions remain dated historical facts rather than being rewritten as secret-free operation.

- [ ] Document the sufficient factual evidence and the explicit absence of full-page reconstruction. State that observed-only manifests provide metadata/facts provenance and cannot prove retained original bytes. Explain actual reviewer/check-date separation and the migration rule.
- [ ] Replace mandatory vault/key setup/recovery/adoption steps in the active recurring runbook with public fact-baseline review and ordinary source-fetch recovery. Update the actual scheduled PR body template to describe public factual observations rather than promising encrypted restricted captures. Preserve the explicit legacy-command documentation separately. Do not weaken unrelated capture/official-results or source-access rules.
- [ ] Add documentation/workflow contract checks for key-free normal paths, unchanged cadence, no new source approval, honest coverage limitations and real later scheduled reuse. Keep ordinary tests fixture-based with a controlled clock and no live network.
- [ ] Record the controlled dry run with exact revision/due set/public baseline reuse/manual queue/failure/missing-slot outcomes and no evidence secret. Run `make check`, current release admission/verification/reproducibility/staging/Updates gates as applicable, and fresh complete canonical review. Inspect actual candidate artifacts before protected merge/publication. Use `Refs #497`, not an automatic closing keyword.
- [ ] Independently verify the merged implementation and any automatically requested release/production deployment. Record source, workflow and delivery evidence. This proves code delivery only; it does not itself adopt the runbook.

### Task 4: Complete factual reviews and independent scheduled adoption

**Files:** Add actual versioned `docs/GENERAL_VERIFICATION_SECRET_FREE_ADOPTION.md`; append only actual records under `data/verification`; update runbook/adoption index when complete. No invented fixture/live results or source decisions.

**Interfaces:** Consume the deployed implementation, existing reviewed WFP evidence and actual future normal scheduler output. Produce the finite complete acceptance packet and final497 disposition. Existing WFP review/reuse remains valid historical progress; new runtime key-free operation still needs actual evidence.

- [ ] Observe a normal real due-source schedule, retain exact deployed revision/run/actual results/public evidence references and confirm no evidence secret/original restore dependency. A dispatch, fixture or no-due success cannot stand in for that due cycle.
- [ ] Review current unapproved source facts against legitimately accessible official publications and record actual reviewer/check/review timestamps and URLs. Existing trusted factual approvals can be reused only for their exact facts; do not retroactively approve unreviewed historical baselines or attribute new reads to an old reviewer.
- [ ] Investigate actual SEIU 775 scheduled failures and deliver a scoped fix if needed. Require genuine recovery or an explicit approved coverage decision; preserve prior baselines/failures and do not silently remove a source from the six-source tranche.
- [ ] Let a later independent normal due schedule demonstrate reuse of approved durable factual baselines. Verify all 46 source lanes, finite due manual tasks, access limitations, escalation and routing. Record actual delegated reviewers by name and bind results to actual runs, not an assumed next cron time.
- [ ] Only after all revised497 criteria have evidence, prepare the adoption-record/runbook change, run required gates/fresh review/protected delivery and independently verify applicable release/production acceptance. Mark adopted and close #497 with exact evidence references. Keep #472/#505/#534/#535 and other finite drift tasks separate.

## Planning status and self-review

This is a plan, not implemented behavior. No secret read, source capture, migration, source approval, runtime change or adoption claim occurred during planning. All accepted evidence requirements map to Tasks1/2; policy alignment and controlled rehearsal to Task 3; real scheduled acceptance and closure to Task 4. The five Review Focus cases each have explicit regression/acceptance steps above. Shared signatures/defaults preserve unrelated collection callers; no new service, database, UI or credentials are proposed. Recheck the final task/package boundaries against actual then-main before implementation. Standing authorization selects subagents and permits delivery without repeated permission questions; this planning request does not itself claim any implementation gate has passed.

Builder check: `/root/builder_check_497_secret_free` identified current-observation retention, SGN failed-discovery persistence and two omitted consumer/template paths. The plan now resolves those implementation choices explicitly. No new product question or approval was requested; no runtime/test success is inferred.

## October 23 native-failure preflight

Seven retained SEIU 775 scheduled failures contain only a generic ValueError and do not establish a cause. Before the implementation delivery, add fixture-tested fixed stage/category information to the existing failure message, including only a validated numeric HTTP status when observed. Keep unknown causes explicit and retain no arbitrary exception, response, URL, address or credential text. This changes diagnosis only; the unchanged normal scheduler must still establish actual recovery or an explicitly approved coverage disposition during Task 4. No transport, access, source, cadence or retry change follows from the generic failures.
