# Pre-upload Intent Disposition Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Resolve a proved pre-upload managed intent through authenticated durable evidence while retaining all upload safety gates.

**Architecture:** Carry a distinct pre-upload disposition through existing sealed negative evidence. The global guard consumes that proof while same-source guards remain unchanged; the correction's normal serialized main CI records the disposition and deploys its own freshly admitted release.

**Tech Stack:** Existing Python/Pydantic/Typer, GitHub evidence and Actions, pinned Wrangler, offline pytest fixture services.

**Spec:** `docs/superpowers/specs/2026-11-14-preupload-intent-disposition-design.md`

## Global Constraints

- Scope #757; General124 archive/tag/asset and original negative evidence remain immutable.
- No election facts, rendering, credential, source acquisition or unrelated changes.
- Original failed report remains failed/uncertain; disposition is separate evidence.
- Unknown or actual resource writes retain verification-only recovery requirements.
- Full make check, exact-head CI, normal applicable gates and independent installed canonical review precede merge.
- No formal GitHub APPROVED; new PR starts draft; issue remains open through independent post-merge acceptance.
- Same serial owner retains PR755 guard custody; PR756 publication follows the actually accepted correction release. General124 may remain unshipped/superseded with its archive identity preserved.

## Review Focus

- A valid wrapper can contain hostile/duplicate ZIP members: disposition must reject unsafe extraction.
- An authentic report can identify a different producer/source/intent: reject exact identity mismatch.
- Later contradictory evidence can appear after disposition: admission must recheck it.
- A software-only declaration cannot remain unchanged: use normal fresh-release prepare/admission, with no exemption for the correction.
- Concurrent or repeated recovery can duplicate an upload: serialize operations and keep new intent/upload identity distinct.

### Task 1: Authenticate and retain a pre-upload disposition

**Files:** Create `src/election_guide/release/preupload.py`; extend `tests/test_release_workflow.py` and fixture services as needed. Reuse existing strict operational models and evidence/Actions helpers; add only the minimal public helper needed for safe local wrapper validation.

**Interfaces:** Produce `resolve_preupload_failure(...)` and `load_preupload_dispositions(...)` with strict typed records. Inputs bind exact original publication, original intent and reviewed retained-wrapper request; results bind all proof digests and disposition producer. Sealed proof survives temporary artifact expiry; fresh contradictions remain live.

- [ ] Run original workflow/evidence focused tests on clean base; retain actual result.
- [ ] Write the regression and identity/unsafe-wrapper/output/contradiction negative controls before production code. Confirm red because the supported disposition is absent.
- [ ] Implement the classifier and authenticated durable disposition, with no upload/status/deletion behavior.
- [ ] Run focused tests and static checks; retain red/green evidence; commit coherent code and tests.

### Task 2: Honor proved dispositions through all upload guards

**Files:** `src/election_guide/release/workflow.py`, `tests/test_release_workflow.py`.

**Interfaces:** Consume validated dispositions only in `require_no_unverified_uploads`, without removing rows from `deployment_rows` or changing same-source `admit_upload`/`create_deployment` rejection.

- [ ] Write tests for legitimate different-source correction admission, preserved same-source rejection, original-intent contradictions, later correction uploads and a second unresolved intent; demonstrate failure at the current base behavior.
- [ ] Implement the narrow distinction while retaining original failure/intent objects and duplicate protections.
- [ ] Run focused release/evidence/promotion tests and static checks; commit.

### Task 3: Deliver the trusted-main bootstrap/recovery path

**Files:** `src/election_guide/release/automation_cli.py`, `.github/workflows/ci.yml`, reviewed retained-wrapper request in `config/hosting/`, normal hosting release declaration, workflow/runbook tests, `docs/RELEASE.md`, `ARCHITECTURE.md`.

**Interfaces:** The `record-preupload-disposition --request <JSON> --output <JSON>` CLI consumes the exact retained wrapper from a reviewed operational request. Normal merged-source CI records historical proof in the existing publication-evidence job without provider credentials or deployment access. The deployment job performs fresh live-intent contradiction checks, then uses its own existing canonical promotion, guarded uploader and finalization APIs. No permission map grows. The correction requires its own normal fresh publication request; it preserves the prior General124 archive.

- [ ] Write CLI/workflow tests for fresh declaration/bootstrap, original wrapper authentication, selected publication/canonical archive preservation, pre-upload gating, credential scope and no duplicate upload. Pin that unchanged-declaration source/workflow corrections still fail release admission.
- [ ] Implement the smallest supported workflow and commands; document executable recovery and its narrow evidence limits.
- [ ] Run full make check and all additional applicable repository gates. Commit the final coherent candidate; run complete installed review-fix-loop local_commit review and remediate material findings through that engine.
- [ ] Publish one draft PR with Refs #757; complete normal CI/candidate/Ready/expected-head merge gates through the existing owner, then independently verify correction on main.

### Task 4: Accept the correction release and deliver retained PR756

**Files:** Operational evidence only after correction is merged.

**Interfaces:** Consume the accepted correction and exact old negative wrapper. Produce actual guarded disposition/production receipts and independent correction-release acceptance, retain General124 unshipped/superseded, then produce current PR756 review/delivery receipts.

- [ ] Reconcile actual current source/main/owner/flocks/catalog/feedback/CI/artifacts and uncertain outcomes before the correction's ordinary expected-head merge. No old-source dispatch/rerun or manual upload is part of this sequence.
- [ ] Observe the normal merged-source CI execute only the reviewed supported path after proof checks. Read actual mutation outcomes; stop the exact action on denial or uncertainty.
- [ ] Independently verify the correction's public archive bytes, production source/manifest/content and strict probe pair; preserve every prior catalog object including124 and reconcile its superseded/unshipped status, lifecycle and custody truthfully.
- [ ] Reconcile retained PR756 against actual accepted predecessor; complete its own prepare/full/readiness/canonical review/CI/candidate/merge/production gates without duplicate source acquisition or assumed version.
- [ ] Close only accepted scopes and release only proven-quiescent resources; retain existing hourly follow-up and truthful incomplete state otherwise.
