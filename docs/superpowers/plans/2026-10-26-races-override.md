# General Races Override Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make general Races controls truthful and responsive, with Contested as default and an explicit All override constrained by any selected precinct; improve the three requested alignment/emphasis details.

**Architecture:** Precinct membership describes all applicable SEG-covered public races. Race mode is a separate general query preference, shared across list and Sources navigation; the comparison router coordinates it with the existing comparison fragment without serializing a second race-mode copy there. Primary keeps its existing defaults and codec behavior. Existing modal and query/storage owners remain in place.

**Tech Stack:** Existing Python/Pydantic, Jinja, lit-html, CSS, Node and headless Chromium; no new dependency or service.

**Spec:** Scott's direct Sentinel_defa88862dac8191be7c0678d2d520a7 (October 26, 14:58 UTC), forwarded unchanged by root. Served diagnosis: private races-override-20261026/owner-diagnosis/SERVED-DIAGNOSIS.json.

## Global Constraints

- Same original owner, native worktree and draft PR #634. Root alone owns review, publishing, current-base/version/release-order reconciliation. Old47 is stale/unreserved.
- Contested includes applicable measures; All adds applicable uncontested races within existing covered/public eligibility. Geography and full-panel/source-independent eligibility remain separate.
- General defaults to Contested; explicit All survives selecting/changing/clearing precinct, navigation, reload and history. No change to primary default or archived raw bytes.
- Preserve modal draft Select/Cancel/Escape, invalid-query notice, source preferences, comparison columns and ballot ordering.
- Preserve prior ledgers/evidence; this is a new specifically authorized scope, not a reset or an automatic old-scope repair.

## Review Focus

- An explicit All URL must not be mistaken for an uninitialized default.
- Geographic membership must constrain both modes; all applicable measures remain in both.
- A mode change must update controls, counts, URL and navigation links together.
- Cancel/Escape must preserve applied mode, membership and memory; Clear removes geography without discarding an explicit race-mode override.
- Labels remain aligned while control bodies/count center correctly on desktop and wrap without overflow on mobile; primary styling stays untouched.

### Task 1: Separate all-applicable membership and race mode

**Files:** `publication/precinct_ballot.py`, `publication/models.py`, renderer payload/navigation paths and generated types; existing pure ballot query, guide filters, comparison codec/controller, Sources/guide composition and precinct-link projection; affected focused tests.

- [x] Establish served RED (done observationally: both buttons disabled;14 unchanged for2502 on both views at390/1280) and add local exact-set/mode/navigation regression tests before implementation.
- [x] Publish all geographic IDs, intersect with existing public eligibility, retaining frozen factual fixtures; use existing full-applicability and contested fixture sets as separate oracles.
- [x] General query mode defaults to Contested; explicit All is written and preserved. Primary behavior remains the existing default. The general comparison fragment no longer duplicates query-owned race mode; primary comparison encoding is unchanged.
- [x] Enable Races in selected precinct mode and apply it after geography; keep Ballot/differences restrictions separate. Preserve explicit mode through modal Select/Cancel/Clear and column presets.
- [x] Carry only owned precinct/races query context through complete renderer-owned list/Sources links; no arbitrary query copying or DOM-derived business state.
- [x] Run focused exact-set, default/override, modal, source/navigation/reload/real-history, types and contract tests.

### Task 2: Requested compact visual adjustments and delivery evidence

**Files:** General-only `precinct.css`, relevant rendering/navigation/browser tests and policy documentation.

- [x] Strengthen selected precinct weight using existing control typography; explicitly center Ballot bodies and the status text while preserving label alignment and mobile wrapping.
- [x] Verify actual geometry and inspect desktop/mobile images for both views; record exact All/Contested counts for SEA36-2502 and representative other precincts.
- [x] Prepare the scoped local candidate with focused verification (75 Python tests, 754 JavaScript tests, Python/client types, lint, desktop/mobile images).
- [ ] Reconcile the actual accepted integration predecessor and next available version with root before staging/publication, then revalidate the final current head. Independent UI development and testing do not wait for another source delivery. The precommit exploratory full run is not final-head acceptance.
- [ ] Root runs fresh complete independent review and updates the same supported preview; verify actual served counts/button state/layout at that head. Production and official-ballot evidence approvals remain held.

## Local handoff status

The candidate includes the source-independent all-applicable geography contract,
working general All/Contested controls, shared query context, general-only Sources
capability, and the requested alignment/emphasis changes. The actual release
screenshot audit now verifies the default, exercises All, and restores the default;
it continues to check the complete admitted public race count.

The first full check is exploratory: source/test edits continued after launch.
It ended with 2 failures and 2,245 passes: a missing FRONTEND check reference
and a stale compiled-source string assertion. Both original tracebacks are preserved.
The reference now names actual checks, and the string assertion is replaced by
primary Chromium checks of scoped Contested/All IDs, query semantics and history
isolation; the enforcement ratchet itself was not relaxed. Sources isolation now
restores the exact legacy payload and places the required true capability only
in a general typed variant. Shared compiled Sources HTML is not claimed identical.
No committed-head full-gate pass, updated served preview, official ballot-example
acceptance, production permission, release version or current-base admission is
claimed here. Root owns actual source/version integration, fresh independent
review, final formal gates and publication to the same draft PR634.

## Independent resumption (October26)

The central instruction cancels the imposed general50 prerequisite for UI
implementation and testing. Work resumed on preserved candidate76157da, whose
common base with accepted M25 (17cac4b) is4b40ca8; M25 is not an ancestor of this
local UI branch. These are explicit available-base implementation checks, not a
claim of integration with M25 or a final current-production predecessor.

- [x] Restore legacy SourcesPayload unchanged; introduce GeneralSourcesPayload
  with required Literal[True] capability, selected by the existing reviewed
  general precinct contract. Generate the union types and explicitly narrow it
  in the existing Sources entry/client. No primary false field, path sniffing,
  panel-name parsing, browser default, new archive or page-freezing mechanism.
- [x] Verify schema, general race modes/geography/modal/layout/navigation,
  legacy source semantics, generated client declarations and Python/client types.
- [x] Verify the complete literal primary Sources payload script against retained
  d273 staging (no normalization), and all32 current-factory primary race documents
  against the retained full raw bytes. The primary9 VM remains untouched.
- [ ] Coordinate only the actual shared integration/version/push/preview boundary
  through the sole publishing root. Revalidate after accepted-main integration;
  do not relabel the available-base checks as final accepted-head gates.

The initial Sources schema RED and constructor-dictionary typing failure are
preserved with their actual outputs; no check was skipped or weakened. Earlier
exploratory failures and old ledgers remain intact, with no numerical reset or
new repair/review allowance inferred from this resumption.
