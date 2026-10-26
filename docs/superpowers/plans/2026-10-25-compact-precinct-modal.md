# Compact Precinct Modal Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement Scott's specified compact Precinct slot and draft-choice modal on general Endorsements and Comparisons in existing draft PR #634.

**Architecture:** Keep admission, query/memory ownership and membership callbacks unchanged. Extend the existing filter composition with an optional Precinct slot and use a native dialog; add a declared optional CSS component only for pages with the precinct contract, preserving primary stylesheet bytes.

**Tech Stack:** Existing Jinja, lit-html, native HTML dialog, authored CSS, pytest/Chromium and Node tests; no new dependency.

**Spec:** Scott's exact October 26 02:35 UTC revision (Sentinel_11d14e5345c88191804fda181c0c5fbf), recorded in the private ROOT-UI-REVISION-AND-RECONCILIATION.json; docs/DESIGN.md voting precinct section updated to this explicit instruction.

## Global Constraints

- Same worktree/branch and draft PR #634; root remains reviewer/publisher.
- No membership, ordering, data, scoring, query precedence, memory semantics, primary activation or production changes.
- Preserve actual archived primary race bytes and existing navigation regressions.
- No separate search strip or explanatory line in the filter row.

## Review Focus

- Cancel/Escape after a changed draft preserve applied query, memory, membership and source choices.
- Opening focuses search; native modal traps focus; closing restores the current invoking control.
- Invalid/partial text cannot commit; exact name/code selection and keyboard submission work.
- Every picker-driven test must exercise explicit Select rather than retaining old immediate-commit assumptions.
- All four headers align on each wrapped row; modal/row remain within narrow and desktop viewports.

### Task 1: Compact shared control and focused regressions

**Files:** Modify `_filter_controls.html.j2`, `_precinct_control.html.j2`, guide/compare templates, `precinct-control.mjs`, `stylesheets.py`, `documents.py`, `docs/DESIGN.md`, `docs/FRONTEND.md`; add declared `precinct.css`. Update affected Node/browser tests and exact shared-name inventory.

- [x] Add failing runtime assertions for modal presence, draft Cancel/Escape, Select, clear, focus and header alignment.
- [x] Implement general-only slot, modal state and optional authored CSS component; preserve existing query/store functions and callbacks.
- [x] Adapt existing exact membership/navigation tests to open and explicitly commit the modal; preserve their assertions.
- [x] Run focused Node/type/style-contract and real Chromium desktop/mobile tests; inspect rendered screenshots.
- [x] Reconcile exact shared-name surfaces and document the explicit UI revision.
- [ ] Commit, run one genuine current-head `make check`, admission, reproducibility/staging, identity, Updates and raw primary32 equality; preserve terminal results.
- [ ] Hand off to root for fresh complete independent review, same-PR preview update and actual served/browser acceptance. Provide the exact updated preview URL after root verification; production remains held.
