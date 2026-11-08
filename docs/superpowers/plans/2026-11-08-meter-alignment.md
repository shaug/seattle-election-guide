# Approved Result and Tie Meter Colors Implementation Plan

> **For agentic workers:** Use superpowers:executing-plans inline, followed by one fresh independent whole-branch review. Steps use checkbox syntax.

**Goal:** Deliver the two color treatments explicitly approved in [#711](https://github.com/shaug/seattle-election-guide/issues/711), without changing result facts or endorsement scoring.

**Architecture:** The existing Python result context derives presentation-only alignment from recorded advanced flags and aggregate recommendation IDs. Its shared Jinja result macro paints the same Guide/race block. Existing Python/JS meter-color mirrors and the social-image renderer share the actual-tie tokens; existing tie classes scope purple framing.

**Tech stack:** Python, Jinja, existing CSS tokens, lit-html, pytest, Node tests and normal protected release automation. No dependency changes.

**Spec:** [DESIGN.md: Result alignment and actual endorsement ties](../../DESIGN.md#result-alignment-and-actual-endorsement-ties-711), [METER_V2.md](../../METER_V2.md), and [RESULTS.md](../../RESULTS.md).

## Global Constraints

- Only recorded winning/advancing result meters change: green #087f73/#cee5e3 or terracotta #b4654c/#f0e0db. Preliminary counts do not create outcomes.
- Actual endorsement ties use lavender #bba6d7/deep violet #654a8b, preserving stepping/fading and existing wording. Sole sub-majority leaders and unrelated amber uses stay amber.
- Preserve badges, other result meters, result data/provenance, endorsement/scoring inputs, immutable archive bytes and unrelated work.
- No new labels or formal GitHub APPROVED review. Document alternatives in the owning design document.

## Review Focus

- Aggregate recommendation ties must include every tied choice; insufficient coverage must not manufacture a recommendation.
- Multiple certified advancers may have different alignment tones; vote ties, rounding and zero preliminary votes must not create outcomes.
- Source-lens changes update endorsement ties and pills consistently while result alignment remains the audited aggregate.
- Three-way palette stepping and per-candidate faded colors must remain distinguishable with readable existing text.
- Archived primary pages retain their original bytes; tests of newly rendered certified pages do not establish a changed archived UI.

### Task 1: Shared presentation, tests and design record

**Files:** rendering/context.py, rendering/og_image.py, shared result/meter templates and CSS, guide/race lens consumers; existing rendering, preliminary, image, parity and JS tests; DESIGN.md/METER_V2.md/RESULTS.md.

**Interfaces:** race_results_view retains its input interface and adds optional presentation-only meter_tone to RaceResultOutcomeView. meter_candidate_colors/meterCandidateColors retain their interfaces. The existing RaceContextView gains optional isTied; no payload schema change.

- [x] Verify both approved Library mockups and reconcile owners/current main before mutation.
- [x] Establish existing baseline and watch new context/markup/tie tests fail against unchanged code.
- [x] Add minimal tone/token/class changes; preserve amber for sole sub-majority leaders.
- [x] Exercise true two-/three-way ties through real scoring/publication fixtures and actual desktop/mobile Chrome; retain failures and corrected harness evidence separately.
- [ ] Verify preliminary zero/tied/unequal counts, certified choices, lens transitions, text contrast, faded states, image colors and server/client parity.
- [x] Record the approved alternatives in owning docs and regenerate only changed parity fixtures.

### Task 2: Exact-candidate review and delivery

- [ ] Reconcile live main and existing scheduled publisher before choosing the normal release declaration; no version reservation by branch/PR.
- [ ] Commit the scoped candidate, run full make check, normal admission, reproducibility, stage verification and authenticated Updates gate.
- [ ] Obtain fresh independent read-only whole-branch review; address material findings with tests.
- [ ] Open a draft PR, inspect exact native CI notes/reports and actual desktop/mobile images, and resolve all feedback.
- [ ] Complete the already approved protected delivery and verify the real release/deployment/production before issue closeout. State actual archive/device verification limits.
