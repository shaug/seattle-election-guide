# Adaptive compact filter bar implementation plan

> Execution: sole implementer, inline with test-driven development; delivery owner arranges independent whole-branch review and preview. Implements [#673](https://github.com/shaug/seattle-election-guide/issues/673), approved C v5 (Library study libfile_f98338d764a48191bd7d6b813f20f4db; prototype libfile_35f5f6114ef481918a00fed511348346).

**Goal:** One 46px general-election bar: Precinct → View → Races → Ballot, with readable values, matching SVG icons and mutually exclusive adaptive menu cues.

**Architecture:** Retain the existing select/radio controls and their state owners, URL codecs, precinct resolver and source behavior. On admitted precinct pages only, place View/Races/Ballot controls in native dialog editors and project their existing state onto compact triggers through a shared module. Keep the existing precinct editor and privacy boundary. Use measured container/content fit after fonts settle (and resize), rather than a viewport breakpoint. Fall back to underlines before measurement; wide layout shows arrows and full precinct name when it fits. Ballot closed text stays “Ballot”; its accessible label and editor name the full selection, and only its own non-All scope lights the dot.

**Tech stack:** existing Jinja, lit-html ES modules, optional general-only precinct.css; no dependency, payload or data changes.

## Constraints and review focus

- Preserve primary.9 archive/pins and derived current-code Comparisons; leave shared base.css unchanged.
- Preserve complete unique precinct identity: abbreviate only exact reviewed SEA district-code grammar with a unique compact name in the catalog. Other names and differentiating suffixes remain intact; no address display in applied state.
- Native dialogs must preserve keyboard entry, focus containment, Escape/Cancel and return. Precinct remains draft/Select; other filters apply on choice and dismiss.
- Preserve applicable scope availability/fallback/Clear, All/Contested measures, independent View/Races/source scoring, URL/history/reload, and Safari checked-state CSS.
- Real-font fit at 320/360/390, measured boundary either side, constrained bar in a wide viewport, longest catalog names and disabled comparison View. Insufficient space must remain honest/readable, never silently truncate identity.

## Tasks

- [x] Reconcile topology/main and create managed worktree from M43 5df7891. Baseline: 58 focused JS tests; 44 precinct/browser/stylesheet tests pass.
- [x] RED: extend actual general-page browser tests for 46px order, readable complete identity, four icons, independent popup edits, own-scope dot, exclusive cues and geometry. Add focused JS tests for safe catalog abbreviations and popup state/focus. Observe expected failures before implementation.
- [x] GREEN: shared compact trigger/dialog template and wiring; project state from guide-filters/compare-client, retaining native controls and existing resolver. Update precinct summary with safe full/compact presentation and move Clear into precinct editor. General-only CSS handles fit, focus and anchored dialogs. No competing state engine.
- [x] Verify focused tests and real font/container geometry; amend obsolete header-alignment assertions to approved 46px trigger behavior without losing membership/modal/history coverage. Update DESIGN/FRONTEND authority.
- [ ] Prepare normal issue673 release request and truthful substantive general Updates entry; commit candidate. Run one final committed-head make check and normal admission/readiness/reproducibility/stage/Updates/primary checks. Record exact results and browser limitations; delivery owner handles review/publication/preview.

## Self-review and execution ledger

All ten issue criteria are assigned above. Approved design supersedes the old wrapping/header layout only on admitted general pages. Native editors preserve existing policy and minimize new interaction machinery. Actual mockup QA is reference evidence, not product coverage. No new design approval needed under explicit execution request.

Ruling: Clear lives inside the Precinct editor, as shown in approved C v5; the closed bar contains only four triggers. Existing tests now assert full accessible identity instead of concatenated hidden/visible span text. Screenshot policy continues counting the same five underlying inputs, excluding launchers and Cancel controls; no count ceiling grew.

Observed RED: old bar absent; missing full accessible/compact precinct identity. Fit RED caught 320px overflow and missing separator widths. Spacing corrected without truncation; real Avenir font/code needs arrows at 360px for Compact/Contested and underlines below it. Actual keyboard regression caught asynchronous close focus stealing; dismissal now restores synchronously and late close events only project expanded state.

Native Safari limitation: lost REPL binding first failed before native access. Explicitly authorized documented same-route Safari initialization then returned a genuine Mac lock/automatic-unlock failure. No dependent native actions/retries/alternate route. Independent Chrome project tests continue; no Safari or physical iPhone acceptance is inferred.
