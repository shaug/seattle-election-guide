# Election Updates Implementation Plan

> **For agentic workers:** Execute inline with `superpowers:executing-plans`. The explicitly assigned source owner implements this plan; publication belongs to the release coordinator.

**Goal:** Implement issue #676's election-information Updates index and additive topic filters.

**Architecture:** Keep authored corrections YAML and `(corrected_on, headline)` identity. Add explicit validated topics/actions with legacy schema compatibility, and preserve complete originals in a durable classification audit before removing software-only public entries. A page-specific client owns only the topic query and projections; publication compares verified served election facts rather than software bytes.

**Tech Stack:** Existing Python/Pydantic/Jinja, ES modules/lit-html, CSS and existing test tools; no dependencies added.

**Spec:** [#676](https://github.com/shaug/seattle-election-guide/issues/676), approved Library `libfile_0e88a23139f0819180fd36f6b0dcda5b` version 2, exact 40,368-byte HTML SHA-256 `eca29635bec9fd4dc988bced59e4342a9f0e36a6cef2c4ac706925bd4d96a18d`. The local design-study scenes are reference only.

## Global Constraints

- No endorsement, collection, scoring, results-ingestion, #673 or #677 work.
- No production authority; release coordinator alone publishes. No historical pin activation or immutable primary/archive rewrite.
- Four visible centered highlight-only controls, minimum 44px, no icon/checkmark space, 320/360/390px reflow.
- Independent OR topics; none means all; All clears; selecting all three retains selection.
- Fixed-order deduplicated `topics=endorsements,sources,results`; unknown tokens ignored; preserve unrelated query parameters and history.
- Complete readable no-JavaScript content, native toggle keyboard behavior, persistent polite count announcement, no focus movement.
- `Changed` requires evidence of a publisher position change. `Correction` describes guide error. Preserve uncertain dates.
- Never bypass checks or grow ratchets. Full `make check`, reproducibility and fresh independent review precede preview readiness.

## Review Focus

- Legacy immutable view models must still validate without invented topics or action claims.
- Software-only classification must not erase mixed entries with actual lost/restored records, count/share errors or certification corrections.
- Old snapshot fingerprints cannot be treated as comparable to a new information policy: upgrade only from verified original deployed bytes, failing closed if unavailable.
- A changed result, endorsement count, source/evidence URL or coverage membership must still require a fresh served entry for that election.
- Filtering must preserve the active button and live-region elements through every subset/history transition.

### Task 1: Metadata and reviewed migration

**Files:** `corrections/models.py`, authored YAML; `docs/audits/updates-676/`; `tests/test_corrections.py`, `tests/test_updates_history.py`.

**Interface:** Extend `CorrectionEntry` with explicit `topics`/`actions`; `ElectionCorrections` accepts legacy 1.0 and validates complete metadata for 1.1. Runtime authoring remains one YAML store. Audit originals are historical records, never alternate editable public content.

- [x] Capture all 66 original entries, exact source file hashes, identity/body/provenance and per-row classification/rationale before mutation.
- [x] Establish clean-base focused validation: 79 passed.
- [x] Add and run failing metadata/migration preservation tests.
- [x] Implement validated metadata and migrate current public projections with conservative mixed-entry retention. Explicit primary route-only overlay uses current authored log/provenance; primary9 archive, overview, races and pins remain unchanged.
- [x] Verify original bodies/provenance/dates/identities, old audit joins and immutable artifacts remain intact. Actual retained primary9/M44 verification also preserves the overview and all 32 race HTML files literally, with all 18 original bundle file hashes unchanged.

### Task 2: Updates index filters

**Files:** `rendering/context.py`, `documents.py`, `payload.py`, `templates/corrections.html.j2`, `corrections.css`, new `updates-entry.mjs`, `updates-client.mjs`, `updates-route.mjs`; focused JS/Python/browser tests and existing enforcement registries.

**Interface:** A typed Updates payload carries topic labels, entry identity/topics and count wording; the client never derives content state from rendered prose. `wireUpdates` preserves server entries and controls while projecting selection/visibility. `updates-route` is the sole location/history owner.

- [x] Add failing all-eight-subsets/reset/final-deselection/canonicalization/history/focus/empty-result tests.
- [x] Implement page payload, topic query owner, stable toggle controls and count projection using existing shell and tokens.
- [x] Add no-JavaScript/rendering assertions and actual browser geometry/screenshots at desktop/320/360/390 after production Safari ownership releases browser phases.
- [x] Verify all required UI, keyboard, URL/history and deduplication behavior; no illustrative entries.

### Task 3: Election-information publication gate

**Files:** `hosting/updates.py`, `updates_baseline.py`, gate/baseline/publication tests; `docs/RESULTS.md`, `docs/RELEASE.md`, `CONTRIBUTING.md`, `docs/DESIGN.md`, `docs/FRONTEND.md`.

**Interface:** Version the served snapshot information policy; compare actual served election data text/evidence and semantic client facts, excluding software markup/styles/code and UI controls. Preserve complete deployment asset/hash verification. The first policy upgrade obtains the verified original production artifact; never compare incompatible fingerprints or fall back to main.

- [x] Add failing tests: software/CSS/code/no-change verification requires no entry; factual changes/counts/coverage/results/evidence still do; baseline incompatibility/tampering fails closed.
- [x] Implement the narrow information fingerprint and compatible baseline transition; retain existing entry-identity requirements for material changes.
- [x] Coordinate migration removals explicitly through durable original-identity evidence; removal never excuses changed election information.
- [x] Amend owning editorial/schema/frontend/publication docs in the same candidate.

### Task 4: Verification and source handoff

- [ ] Run focused/full checks; record actual failures and repairs. Run `make check` before proposing the source diff.
- [x] Release67 baseline sealed; ordinary authorized `prepare --issue 676` chose general68 against exact previous source79eb, with unchanged ledger/dataset/registry hashes. No other issue request was borrowed.
- [ ] Commit a clean conventional source candidate; run clean-tree reproducibility and applicable readiness gates.
- [ ] Resolve and perform fresh complete independent review under the actual supported boundary; no borrowed #673 exception or claimed tool-mask guarantee.
- [ ] Hand exact source/base/tree, check output, classification and remaining acceptance to the sole publisher. No push/PR/deployment by source owner.

Source freeze follows normal #676 preparation. Final complete gate, clean candidate commit, reproducibility/readiness and fresh independent review remain recorded in the delivery evidence outside this source tree; there is no production authority.
