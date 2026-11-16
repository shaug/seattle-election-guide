# Compressed Release Evidence Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox syntax for tracking. Execution method: native.

**Goal:** Replace ordinary fifteen-comment release evidence with three durable compressed checkpoints without losing original bytes, identity or historical recovery.

**Architecture:** A bounded v2 codec feeds the existing evidence validation boundary. Ship dual readers and an explicit current-workflow historical compatibility preparation while writers remain v1; prove those deployed boundaries, then activate v2 writers in a separately gated change.

**Tech Stack:** Existing Python/Pydantic, standard-library gzip/zlib/base64/hashlib/JSON, authenticated gh API and existing Actions workflows. No dependency or permission-map addition.

**Spec:** docs/superpowers/specs/2026-11-15-compressed-release-evidence-design.md; original task records are separate.

## Global Constraints

- Scope #762; same serial /root owner, native implementation, spare capacity; SB/Currents priority and heavy work/publication serialized.
- Do not change UI/rendering/election data, credentials, permission maps, actors or producer identities; do not edit/delete existing evidence.
- Preserve publication, uploaded-before-probes and verified checkpoints, all current strict gates, Primary and Updates.
- Active writers remain v1 through Stage A. Historical proof and independent deployed acceptance precede Stage B writer activation.
- Body <60,000 characters; 16 reports; 8 MiB/report; 16 MiB decoded envelope; 4 MiB gzip; 32,768-byte chunks; 128 parts maximum; reject rather than truncate.
- Continue incomplete v1 groups as v1. Reread complete evidence after uncertain POST before retry; fail closed on conflicts.
- Source/reader/exporter/workflow/producer identities remain separate. Fixture transport is explicitly labeled, never native GitHub execution evidence.
- Normal fresh publication request and unreserved version come from current actual main/catalog/open-draft reconciliation; do not touch #761's branch/source or create competing publication.

## Review Focus

1. A valid early receipt fragment followed by a conflicting v2 upload must still block canonical admission — Task2 cross-format conflict test.
2. A lost POST reply with a successfully stored envelope must not create a duplicate comment — Task5 ambiguous-success test.
3. A gzip member that expands past the budget or has a second member/trailing bytes must be rejected before model validation — Task1 bounded-decompression tests.
4. Old source checks every managed intent, so exporting only its requested release is insufficient — Task3 multi-release historical-global-admission test.
5. An incomplete v1 operation must keep its representation and immutable IDs after writer activation — Task5 continuation test.

## Files and interfaces

- Create src/election_guide/release/evidence_v2.py: typed v2 framing, bounded compression/decoding and multipart assembly; no API or production decisions.
- Modify src/election_guide/release/evidence.py: combine authenticated v1/v2 comments and shared validation; explicit lossless v1 retention helper; active v1 default in Stage A.
- Create src/election_guide/release/evidence_compat.py: current-workflow compatibility preparation; no upload/provider capability. Create tests/test_release_evidence_historical.py: subprocess execution proof using unmodified historical Git objects and an offline fixture API.
- Modify src/election_guide/release/automation_cli.py: explicit preparation/proof command and failure artifact propagation.
- Modify .github/workflows/verify-release.yml: explicit preparation mode using existing permissions/concurrency; default verification behavior retained.
- Modify docs/RELEASE.md and ARCHITECTURE.md: format/limits and required recovery ordering.
- Create tests/test_release_evidence_v2_codec.py (unit), tests/test_release_evidence_v2.py (integration-artifacts), tests/test_release_evidence_compat.py (integration-artifacts), with tests/suites.json entries.
- Extend tests/test_release_evidence.py, tests/test_release_workflow.py, tests/test_preupload_disposition.py, tests/test_updates_baseline.py and tests/test_release_automation_workflow.py only where their consumer/CLI/workflow contract is exercised.
- Retain exact General128 operation/report fixtures under tests/fixtures/release/evidence-general128/ when needed for a repeatable byte proof; exclude unrelated comments and signed handles; bind original hashes and provenance.

### Task 1: Bounded v2 codec (Stage A)

**Interfaces:** EnvelopeMarker validates schema2.0, producer/release/phase/state/group/encoding and both size/hash pairs. encode_envelope(files: dict[str, bytes]) -> bytes returns deterministic gzip; decode_envelope(payload: bytes, marker: EnvelopeMarker) -> dict[str, bytes] returns original bytes. render_envelope(marker, payload) -> str enforces the body bound. decode_comment(body: str) returns typed marker and payload; envelope_parts(marker: EnvelopeMarker, payload: bytes) -> tuple[tuple[EnvelopeMarker, bytes], ...] chooses atomic or bounded part framing. assemble_envelope(marker: EnvelopeMarker, seal_payload: bytes, comments: dict[int, tuple[EnvelopeMarker, bytes]]) -> dict[str, bytes] verifies actual part IDs/order/hashes and sealed completeness.

- [ ] Write codec tests: deterministic gzip mtime=0, exact Unicode/JSON bytes and per-file hashes; unknown fields/names/keys rejected; marker/source identity binding; invalid base64, gzip corruption/truncation/trailing/concatenated members; each size/count boundary; 128-part bounded fallback and malformed/duplicate/missing refs.
- [ ] Run `uv run --offline --frozen pytest -q tests/test_release_evidence_v2_codec.py`; observe RED at missing codec, with no unrelated failure.
- [ ] Implement the codec with bounded zlib output and strict JSON duplicate-key handling. Keep API access out of this file.
- [ ] Run the same tests to GREEN plus lint/type checks; commit `feat: add bounded compressed evidence codec` with suite membership and design/plan.

### Task 2: Dual readers, unchanged active v1 writes (Stage A)

**Interfaces:** _comments retains actual IDs with a PartMarker | EnvelopeMarker union; _completed returns the same list[tuple[OperationReceipt, dict[str, bytes]]] contract. retain_evidence retains its current public signature and active v1 behavior; retain_v1_evidence provides the explicit compatibility representation without changing receipt/report content.

- [ ] Add RED tests using actual General128 receipt/report fixtures: three atomic v2 comments reconstruct original bytes; v1-only and mixed groups; matching cross-format dedup; conflicting reports/upload/source/bot/producer; unsealed groups block admission; valid partial receipt cannot be contradicted.
- [ ] Add consumer tests for require_publication_evidence, latest_production_receipt, pre-upload disposition, Updates baseline, read_evidence_reports and recover_upload with expired artifact transport.
- [ ] Run `uv run --offline --frozen pytest -q tests/test_release_evidence_v2.py tests/test_release_workflow.py tests/test_preupload_disposition.py tests/test_updates_baseline.py` and observe the new failures.
- [ ] Implement dual reading through the existing validation boundary, filtering format-specific assembly without synthetic production comment IDs. Preserve all current v1 framing and validation bytes.
- [ ] Run those tests plus tests/test_release_evidence.py to GREEN. Assert ordinary retain_evidence still emits v1 and prior groups/bodies remain unchanged. Commit `feat: read compressed and legacy release evidence`.

### Task 3: Supported historical compatibility preparation (Stage A)

**Interfaces:** prepare_historical_evidence(repository: str, issue_number: int, output_dir: Path) -> compatibility report materializes only missing matching v1 records from authenticated complete v2 groups, with actual current exporter identity separate. The mandatory historical integration test executes the original verification workflow recover-upload command and latest-production/global-admission consumers in separate processes, recording imported Git-blob identities and exact receipt/report hashes. CLI `release automation prepare-historical-evidence` exposes preparation under trusted current-main execution only; the same workflow mode runs and retains the historical proof without a second production Git orchestration API.

- [ ] Add RED tests: multiple managed releases and latest selection survive preparation; partial v1 continuation; already complete v1 no POST; corrupt/incomplete v2 fails before export; conflicts fail closed; original producer/source never rewritten; no artifacts/provider/upload/deployment-status call; bounded export batches report incomplete visibly.
- [ ] Add a subprocess integration test that executes actual original K source/workflow command against explicitly labeled retained/fixture transport; pure v2 is not silently treated as old-reader success, while lossless compatibility preparation yields exact old consumer receipts/reports. Assert imported project origins come from the original source, not the current checkout.
- [ ] Implement the preparation command and testable historical proof using full immutable Git objects and authenticated retained General128 custody. Discover all owning issues from managed deployment payloads and preflight them before any export; bound new comments per invocation to 256, with explicit nonzero partial/resumable output. Do not patch old code. Record current reader/exporter SHA separately from original operation.
- [ ] Add explicit preparation/proof mode to verify-release.yml, preserving existing permission values, concurrency and default recovery. Invalid mode/input/retention exits nonzero with retained local report/summary; default verification remains unchanged.
- [ ] Run `uv run --offline --frozen pytest -q tests/test_release_evidence_compat.py tests/test_release_evidence_historical.py tests/test_release_automation_workflow.py tests/test_release_runbook.py` to GREEN; commit `feat: preserve historical readers through evidence preparation` with runbook ordering.

### Task 4: Deploy and prove reader rollout (Stage A gate)

- [ ] Self-review spec coverage and run complete `make check` on the committed candidate. Run required reproducibility/staging/Updates readiness under repository rules; record exact source and no factual Updates filler.
- [ ] Complete canonical installed review-fix-loop local_commit: all three independent read-only reviews and aggregate, no reviewer messaging/delegation/network/project tests/builds; resolve material findings through canonical Decide before fixes. Validate its terminal result/checkpoint.
- [ ] Reconcile live main/open drafts/catalogs/ownership, prepare the reviewed request with issue762 and an actually unreserved version, commit any required request change, revalidate affected gates and review. Open one draft reader PR with `Refs #762`.
- [ ] Own its ordinary lifecycle through exact-head CI and native candidate inspection, Ready and expected-head nonforce merge, original owning-main pipeline, independent archive/material/images/strict production and preservation acceptance. Active comments must remain v1. No other results source is mutated.
- [ ] Execute the deployed supported historical preparation/proof workflow for original K and retain actual native run/all-jobs/command/origin and full proof output. Prove current verification-only recovery from durable evidence with Actions artifact retrieval unavailable. No old upload or new General128 acceptance clock is claimed.
- [ ] Require all reader, historical, old-v1 preservation and production gates to pass before Task5. Keep the issue and Stage B pending if any real gate is denied; report exact action/state without alternate route.

### Task 5: V2 writer activation (separate Stage B candidate)

**Interfaces:** retain_evidence keeps its public signature; a private format selector chooses v1 for any matching pending v1 group, reuses a matching complete group, otherwise selects v2. Posting returns actual immutable comment IDs. Multipart writes missing parts then final seal. Existing finalize_deployment retains upload before probes.

- [ ] Add RED tests: three ordinary checkpoints produce exactly three total comments and reconstruct all original bytes; matching rerun posts zero; interrupted/ambiguous atomic and multipart POSTs reread and reuse; confirmed missing reply remains nonzero; conflicting results/duplicate parts fail; incomplete v1 continues v1; checkpoint precedes probes and failed retention stays nonzero/status failed.
- [ ] Run `uv run --offline --frozen pytest -q tests/test_release_evidence_v2.py tests/test_release_evidence.py tests/test_release_workflow.py tests/test_preupload_disposition.py tests/test_updates_baseline.py` and observe the activation-specific failures.
- [ ] Implement only the writer switch and safe POST reconciliation. Do not alter codec/identity/verification gates to satisfy the count. Run the same focused set to GREEN and commit `feat: write atomic compressed release checkpoints`.
- [ ] Repeat fresh full/canonical review/readiness, current admission/version reconciliation, draft PR, exact-head CI/candidate/Ready/ordinary merge and independent owning-main/production/preservation acceptance for Stage B. Verify actual bot-authored common-case checkpoint count and whole original reports; retain multipart/expiry test evidence. Do not reuse Stage A review/CI for a changed head.

### Task 6: Final feature closeout

- [ ] Bind an acceptance ledger to both deployed sources and native runs, with every approved criterion and original-byte/hash provenance. Preserve General128/old v1 and all prior release/Primary/Updates records; no repeated old artifacts/public downloads for status.
- [ ] Update only the feature PR/issue records with independently read-back actual outcomes. Close #762 only after both staged deployments and post-merge acceptance pass; do not transition #696 or a future tracker. No formal GitHub APPROVED review.
- [ ] Record non-gating lifecycle/shape observations, release the exact owned guard once after live identity and resource checks, preserve this worktree/evidence and all unrelated worktrees, and update the existing hourly automation to completed feature state. Broader future program remains incomplete.

## Plan self-review

Coverage: codec/framing/limits -> Task1; original bytes/ownership/current consumer contracts -> Task2; historical source execution/order/expiry -> Task3 and deployed Task4 proof; reader-before-writer deployment -> Task4 gate; multipart/idempotency/uncertain writes/incomplete-v1/upload-before-probes/failures -> Task5; full/review/CI/candidate/ordinary shipping/preservation/resource closeout -> Tasks4-6. Every Review Focus row has an owning regression test. Interfaces use original operation identity throughout. The compatibility preparation is required recovery ordering, not a new permission or optional approval gate. Execution remains native and the staged acceptance gates remain mandatory.


## Named executable regressions

Task1: `test_codec_round_trips_original_unicode_bytes`; `test_deterministic_gzip_header`; `test_codec_rejects_trailing_or_concatenated_gzip`; `test_decode_rejects_expansion_over_budget`; `test_envelope_rejects_duplicate_json_keys`; `test_report_limits_fail_before_encoding`; `test_decode_rejects_report_hash_or_operation_digest_conflict`; `test_comment_framing_roundtrip_and_bound`; `test_multipart_requires_exact_immutable_ids_and_hashes`. Assertions include decode(encode(files)) == original literal UTF-8 bytes, gzip mtime bytes equal four zero bytes, appended gzip member/trailer and max+1 expansion raise ValueError, and omitted/duplicate/conflicting sealed part IDs cannot complete.

Task2: `test_general128_three_v2_comments_restore_exact_original_reports`; `test_mixed_representations_deduplicate_only_identical_bytes`; `test_incomplete_v2_blocks_preupload_disposition`; `test_partial_v1_receipt_cannot_be_contradicted_by_v2_upload`; `test_v2_supports_current_admission_latest_updates_and_expired_artifact_recovery`; `test_reader_rollout_keeps_active_writer_v1`.

Task3: `test_compatibility_preparation_covers_global_managed_intents`; `test_compatibility_export_resumes_original_v1_ids`; `test_compatibility_export_keeps_original_producer_and_records_exporter`; `test_original_workflow_and_consumers_after_lossless_preparation`; `test_historical_proof_rejects_current_import_origins`; `test_historical_preparation_keeps_permissions_lock_and_default_recovery`; `test_preparation_cli_preserves_nonzero_and_never_runs_verification`.

Task5: `test_ordinary_release_retains_exactly_three_comments`; `test_ambiguous_successful_post_is_reused_after_reread`; `test_missing_ambiguous_post_stays_nonzero`; `test_multipart_retry_posts_only_missing_records`; `test_existing_partial_v1_remains_v1_after_cutover`; `test_upload_checkpoint_is_retained_before_probes`; `test_failed_retention_is_nonzero_and_does_not_mark_deployment_success`.
