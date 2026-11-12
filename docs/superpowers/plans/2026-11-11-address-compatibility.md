# Address Compatibility Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans inline with the same existing coordinator. Preserve the delivery ledger and evidence.

**Goal:** Resolve compatible GIS metadata refreshes while rejecting changes that
invalidate the exact precinct lookup contract.

**Architecture:** Validate the consumed metadata projection before and after the
existing adapter operation. Keep election-bound City/precinct DATA, stable ADDRESS
DATA within a resolution, and exact returned geography checks. Keep existing
payload shape and providers; do not pin a complete metadata hash.

**Tech Stack:** Existing JavaScript ESM, Node tests, Python/browser contract tests;
no new dependencies.

**Spec:** `docs/superpowers/specs/2026-11-11-address-compatibility-design.md`

## Global constraints

- Same owner and worktree; no edits beneath the retained prototype full.
- Fixed providers, layer IDs 0/655/0 and reviewed native WKID 2926.
- Response limit 20, existing byte/time bounds, no retry or new transmission.
- Original recorded epochs remain provenance; exact City/precinct DATA remains.
- Amend owning rules with implementation; no UI change or new monitoring feature.
- Final canonical review uses installed local_commit and all three lenses.

## Review focus

- Harmless schema churn at either metadata observation must remain compatible.
- Duplicate required names must not silently win through a Map conversion.
- A lowered server limit must not make incomplete arrays look complete.
- Unused metadata must not become another whole-schema equality proxy.
- Malformed site values must not exploit JavaScript truthiness for units/identity.

## Task 1: Metadata semantics and regressions

**Files:** `voting-address-lookup.mjs`, its Node tests, shared browser metadata
fixtures and the existing address fixture helper.

**Interfaces:** Keep `createVotingAddressLookup(binding, precincts, options)`.
Add one internal semantic metadata predicate; `context(signal)` still supplies
the observed ADDRESS data identity for the unchanged before/after comparison.

- [ ] Write benign-drift and incompatible-metadata tests around the actual adapter.
- [ ] Observe benign cases fail against the clock guard and incompatible cases
  fail when the unvalidated metadata is otherwise accepted.
- [ ] Add the small three-layer semantic contract, remove schema-clock equality,
  and narrow ADDRESS outFields to the five consumed fields.
- [ ] Preserve all existing rejection, privacy, cancellation and completeness
  tests; add malformed consumed-site cases and after-read mutations.
- [ ] Run the complete affected Node and Python/browser suites, inspect outputs.
- [ ] Exercise one current public civic resolution with the originally served
  binding and preserve all actual evidence; do not claim deployed acceptance.
- [ ] Amend owning docs and restore original recorded ADDRESS epochs, then commit
  ordinary additive work with the prototype history intact.

## Task 2: Final validation and delivery

**Files:** Owning issue746, normal hosting declaration when preparation is allowed,
and private existing delivery receipts.

**Interfaces:** Normal owning `prepare --issue 746`, exact-head/full and installed
local_commit evidence, original-source publication and strict production checks.

- [ ] Reconcile actual741 publication state and actual main/published predecessor;
  retain the supported recovery diagnosis and any controlling execution stop.
- [ ] Run normal preparation, admission and final-head `make check` once valid;
  never impersonate issue696 or weaken the unpublished-owner rule.
- [ ] Complete reproducibility/readiness, actual candidate inspection, all three
  canonical lenses, required CI, draft PR and expected-head ordinary delivery.
- [ ] Complete actual live civic Select and privacy checks, strict production
  acceptance and resource/public closeout, or report a concrete external blocker.

Ruling: Scott explicitly authorized this resilience implementation and normal
judgment without another design-permission hold. The coordinator executes inline;
no second writer or per-task agent is introduced. The user's installed canonical
review/fix contract governs final review and any fixes, including fresh review
after a changed head. Preserve the private ledger/evidence rather than deleting it.
