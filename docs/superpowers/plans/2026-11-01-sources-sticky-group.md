# Sources and filters sticky group Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. This execution is assigned to the sole source implementer; root owns fresh review and publication.

**Goal:** Join the Guide’s native controls and existing Sources navigation in one content-fitted sticky group, with Sources and the intact live count on row two when necessary.

**Architecture:** Extend the shared election-control macro with an optional Guide-only Sources slot. Keep the real controls, link and announcing roots in stable DOM order; CSS grid chooses rows without moving nodes. The existing compact-fit owner measures full control/source families, current count and actual container/font before admitting the single row. Guide source state remains owned by `guide-client.mjs` and derives from the existing tallying source selection.

**Tech Stack:** Jinja, authored CSS, existing ES modules/lit-html, Node tests, pytest and project headless Chrome.

**Spec:** Issue https://github.com/shaug/seattle-election-guide/issues/679 and the approved `/Users/scott/Documents/Codex/2026-10-30/task/sources-sticky-study/sources-sticky-prototype.html`, SHA256 d099fe8d17857790ec452b4d29c3fdc79d42b84acf072ee6a3971083fd77bee3. All five comparison PNGs were viewed. Trusted approval at 2026-11-01 16:17:33 UTC explicitly directs implementation/preview and accepts the mobile tradeoff. The design and execution method are settled; no new design approval loop applies.

## Global Constraints

- Guide/Endorsements only; Comparisons retains its existing layout, shared behavior and regression coverage.
- Order Precinct → View → Races → Ballot → Sources → intact reactive count. Narrow group has two sticky rows, never three or auto-hiding.
- Real container/content/font fit, no illustrative 1105px breakpoint, truncation, cloned live counter or prototype state logic.
- Preserve full precinct identity, native select nodes/options/focus, icon/cue modes, 44px targets, own Ballot/source state, URL/history/reload/address/precinct/anchor/dialog contracts.
- Preserve canonical data, scores, geography, results, subtitles, existing history and primary.9 pins; no #676 candidate edits.
- Ratchet ceilings/allowlists cannot grow. Update owning contracts and only normal behavior-change Updates/history/declaration.
- Source commits and local validation only. Root owns review, push/PR and preview; production/merge/issue close/formal approval are unauthorized.

## Review Focus

- Actual font/container changes must recover both fitting modes without oscillation; tested with measured fractional boundary and constrained wide viewport.
- Source selection may change summary length but not control tracks or own Ballot state; tested with real fragments and full source set restoration.
- A long precinct and Ballot scope must remain complete, named and usable at 320/360/390px; exercised with catalog values and existing native regressions.
- Sticky height changes must clear anchors and leave dialogs/content visible; geometry checks cover both rows and notices.
- Shared component edits must preserve Comparisons and legacy primary; existing browser/Node/parity coverage stays in the full gate.

### Task 1: Joined Guide layout and source projection

**Files:** Modify `_filter_controls.html.j2`, `guide.html.j2`, `precinct.css`, `compact-filters.mjs`, `guide-client.mjs`; tests in `tests/test_precinct_rendering.py`, `tests/js/guide-client.test.mjs`, `tests/js/compact-filters.test.mjs`; own `docs/DESIGN.md`, `docs/FRONTEND.md`, `tests/shared_names.json` declarations as derived.

**Interfaces:** Existing controller intent is unchanged. `projectCompactSources({selected:number,total:number,summary:string})` renders the existing link’s summary and accessible name, registers its complete value family, and requests existing compact fit. `wireCompactFilters()` adds optional source row fit and measured Guide sticky-height projection only for the source-bearing Guide bar.

- [ ] Write tests showing the absent two-row sticky Guide layout, source selection/count independence and measured single-row fit. Update the old Guide-only centered-group assertion to include its newly joined Sources member; retain Comparisons assertions.
- [ ] Run new Node/browser cases and observe meaningful feature-absent RED.
- [ ] Add optional macro composition, source projection, intrinsic measurements, stable grid rows and Guide-only sticky/anchor CSS. Keep legacy banner for primary and non-grouped pages.
- [ ] Run focused Node, browser and declaration checks; correct real failures without weakening requirements.
- [ ] Commit coherent source/tests/contracts once focused checks pass.

### Task 2: Candidate declaration and acceptance evidence

**Files:** Owning `config/hosting/site.yaml` current general request; append a faithful general Updates entry for changed persistent controls. Preserve every previous whole entry. All raw receipts and visual evidence stay outside source worktree in the #679 delivery folder.

**Interfaces:** Candidate keeps existing ledger/dataset/registry bytes and primary pins. Version is a local unreserved proposal only; root rechecks remote publication/version order. Prohibited tag/collection endpoints remain untouched.

- [ ] Prepare the issue’s exact input-bound local request and faithful Updates entry; commit final candidate before current-head checks.
- [ ] Run actual committed-head `make check`, reproducibility, resolve/request validation, stage/hosting verify and authenticated `make check-updates` as applicable. Preserve raw commands, times, head/tree, results and failures.
- [ ] Capture 320/360/390/intermediate/wide, measured transition both sides, constrained-container/font/long-values/source-change screenshots and geometry from the exact candidate. Record headless scope and pending native acceptance honestly.
- [ ] Recheck clean head/tree and criterion ledger. Return the committed candidate and evidence to root at the exact fresh-review restriction, without launching review or publishing.

## Self-review

The two tasks cover every issue implementation criterion; hosted preview/CI/fresh constrained review remain root-owned. No new module/state owner, provider request, dependency, generic redesign or new acceptance gate is introduced.


### Task 3: Complete actual-container fit

The Guide has no viewport-derived exemption for its narrower actual container.
The preserved a0 candidate’s full/readiness passes remain authentic; its six
long-source300/280px container failures require this scoped correction.

- [ ] Pin the exact44of45/31-contested-count failure in300/280px bars inside a1440px
  viewport across the production, system-ui and sans-serif fonts; separately
  preserve all six1-race scoped passes and wider recovery/focus/native identities.
- [ ] Reclaim the second row’s gap only as needed; if no inline gap can fit,
  stack the complete Sources prefix/value within its44px target and remeasure.
  Preserve text, font/icon sizes, count phrase, two rows and source/filter owners.
- [ ] Prove focused geometry, commit, then run the source-bound release/stage
  and full visual matrix before the expensive final full gate. Resolve any real
  geometry defect first, then run `make check` alone at the final committed head.
- [ ] Reuse genuinely current readiness/visual evidence and preserve previous
  heads’ exact reports; root still owns review and all publication.
