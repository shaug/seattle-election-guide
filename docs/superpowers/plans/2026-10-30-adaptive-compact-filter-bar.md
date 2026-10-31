# Adaptive compact filter bar implementation plan

> Execution: sole implementer, inline with test-driven development; delivery owner arranges independent whole-branch review and preview. Implements [#673](https://github.com/shaug/seattle-election-guide/issues/673), approved C v5 (Library study libfile_f98338d764a48191bd7d6b813f20f4db; prototype libfile_35f5f6114ef481918a00fed511348346).

**Goal:** One 46px general-election bar: Precinct → View → Races → Ballot, with readable values, matching SVG icons and mutually exclusive adaptive menu cues.

**Architecture:** Retain the existing select/radio controls and their state owners, URL codecs, precinct resolver and source behavior. On admitted precinct pages only, place View/Races/Ballot controls in native dialog editors and project their existing state onto compact triggers through a shared module. Keep the existing precinct editor and privacy boundary. Use measured container/content fit after fonts settle (and resize), rather than a viewport breakpoint. Fall back to underlines before measurement; wide layout shows arrows and full precinct name when it fits. The wide Ballot trigger includes its full selected scope when measured content fits; only the constrained trigger stays “Ballot”. Its accessible label and editor always name the full selection, and only its own non-All scope lights the dot.

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

Gate correction: the first committed-head gate exposed four newly shared control labels and one stale standalone Precinct-header mirror. After 1,199 passes and that one failure, the owned test process was interrupted for correction. The mirror inventory now declares the real constant-label evidence and removes the vanished header claim; actual rendered radio/trigger label parity is tested. This inventory is a required coverage floor, not a ratchet ceiling or exemption list. The corrected committed head receives the complete gate; the first run is retained as failed/interrupted evidence.

Second gate completed with 2,441 passes and nine failures: two required shared-name inventories and seven address-browser cases still targeting the former inline Ballot select or concatenating full/compact name spans. The address tests now open the real Ballot editor by native keyboard, retain native select type-ahead and hit/focus checks, and target the full precinct-name field. The unified address editor still has exactly one input; the four retained filter radios are in their separate editors. All seven address cases and all thirteen shared-name checks pass. The shared-name declaration records actual newly shared hooks, with no scanner/exemption/ceiling change. Product, configuration and data bytes are unchanged by this correction; the new committed head still receives a complete gate and source-bound builds.

## Canonical attempt 1 — accepted #673 correctness corrections

Preserve the approved C v5 palette using three named tokens owned only by the
general compact-bar component; DESIGN explicitly records that bounded ownership
while shared base.css remains frozen. Correct the initial implementation's
unconditional Ballot-only presentation: measure the full scope in the wide bar,
then omit it only when that real content cannot fit. A two-view regression failed
before the correction and passed afterward.

Open editor geometry now follows the current visual viewport and anchor while
open, including movements that emit no resize event. Writes occur only when
geometry changes; closing ends tracking. No selected state, URL, focus reset or
forced close is used. Both-view View/Races/Ballot regressions open before resize,
then exercise portrait/landscape, short viewports, visual zoom and anchor movement.
They failed before correction and passed after it. An additional real zoom check
caught clipped radio text; existing radio labels now wrap when content needs it.
Full engine validation, commit/promotion, committed-head gates and fresh review
remain the engine/delivery owner's next steps; focused results are not substituted
for those gates.

### Attempt 2: platform font fit

The original Linux rendering gate exposed 320px overflow after the underline
fallback. Local browser coverage now includes the approved stack plus explicit
`system-ui` and `sans-serif` fallback metrics on both pages. The `system-ui`
Guide reproduced 321px of controls and separators inside a 320px bar. Recheck
that final mode and reclaim measured inline padding. If that still overflows,
remove gaps and position the scope dot above the text within its trigger. Reset
both adjustments before each fresh fit. The 300px container regression proves
that padding alone is insufficient, independently of a specific platform font.
Preserve full text, font size, icons, scope-dot visibility and target minima.

### Attempt 3: Scott’s preview corrections

Center the control group independently of the existing reactive status. Keep the
whole status phrase on one line beside that group when side space admits it, or
on its own centered line below. Restore the visible status without another
count/state owner. Empty Precinct and removal of duplicate Ballot editor text
preserve native Select/Cancel/naming. Actual native/browser regressions cover
320/360/390/1280 and filter/Clear/URL/history changes.

The requested full All ballot races value conflicts with the Guide’s narrow
row: at zero padding/gaps, no arrows and the dot out of text flow, complete
46-1279 + Compact + Contested + All ballot races needs 348.890625px in Avenir
and 351.765625px in system-ui. This was a concrete wording/fit tradeoff, preserved as historical diagnostic
evidence. Scott resolved it explicitly: constrained/mobile shows only Ballot
and its own-scope active dot, with no selected value. Wide shows only the current
value (default All ballot races), without a Ballot prefix or redundant Seattle.
The native select retains the current value without the duplicate paragraph.
No two-line Ballot, new abbreviation or font/target reduction is introduced.

Final source coverage includes no-precinct All and active County plus All races
at actual 320/360/390px viewports, under the approved stack, system-ui and
sans-serif fallback. Wide values, native selected options and Guide payload
labels agree; the renderer owns the general-only all-scope wording. The release
status audit compares the published all-scope label while retaining its original
three-part, whole-text and layout assertions. Legacy primary wording stays intact.

### Second authorized bounded follow-up: final 300px overflow

The retained Linux 204e measurements are genuine failures: zero-spacing inline
Guide controls need 318.84375px at300; Comparisons Differing needs319.296875px.
Local Mac fonts pass300 but reproduce the same intrinsic inline overcommit at
280. Complete pre-edit glyph/icon/box/padding/gap contributors and the original
Linux objects were recorded before source edits. No local result is a Linux run.

Recheck after the existing tight fallback. Only if it still overflows, arrange
icons above one-line values within the unchanged46px controls. Keep14px fonts
and icons,44px minimum targets, complete labels and own-scope dot. Wider layouts
remain inline; no platform flag or viewport breakpoint is introduced. Retain
300/320/360/390 and actual Full/Differing/active-scope coverage, adding280 as a
local real-geometry regression and actual300px viewport/count cases. Root owns
new Linux validation; the source correction does not claim that result.

The final stacked state retains a 2px inline inset between adjacent labels.
The label-separation assertion first failed in four real local cases before
this inset was applied; earlier zero-inset captures remain intermediate evidence.
