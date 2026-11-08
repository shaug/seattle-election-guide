# Preliminary Meter Alignment Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Extend the approved result colors to current unofficial count leaders without calling outcomes (#715).

**Architecture:** Keep the shared result block and its existing `meter_tone`. Derive a presentation-only tone for a unique positive named vote leader; never change preliminary `advanced`, chips, counts, provenance or schema. Write-in ambiguity and tied/zero counts remain neutral. The same block serves Guide and race pages.

**Tech Stack:** Existing Python/Pydantic/Jinja renderer, CSS and Chrome/CDP test harness; no dependency or transport changes.

**Spec:** Scott's explicit follow-up approval, issue #715, and the amended result-alignment sections of DESIGN.md and RESULTS.md. Inline execution continues the existing approved workflow; no additional design approval is needed.

## Global Constraints

- Exact colors: aligned `#087f73` / `#cee5e3`; different `#b4654c` / `#f0e0db`.
- Use actual integer votes and published aggregate recommendation IDs, including endorsement ties.
- Color denotes a raw current lead, never certification, passage or advancement. Do not infer unknown thresholds or numbers of advancing seats.
- Preliminary flags remain false and chips absent. Preserve Unofficial, equal emphasis, available clocks and all other UI/data.
- No formal GitHub approval. Keep #712's separate source work and immutable archives intact.

## Review Focus

- Rounded display ties must not erase a unique raw-vote lead; real top ties and zero totals remain neutral.
- An aggregate write-in count at least as large as the top named count cannot prove a named leader.
- Empty aggregate recommendations do not manufacture endorsement; trailing endorsement ties do not tint losing rows.
- A measure's raw vote lead does not prove its threshold is met; a primary lead does not invent a second advancement slot.
- Missing races/choices retain existing admission/absence behavior; lens changes must not re-own the result block.

### Task 1: Shared leader presentation, regressions and policy record

**Files:** `src/election_guide/rendering/context.py`, `tests/test_preliminary_results.py`, `docs/DESIGN.md`, `docs/RESULTS.md`.

**Interfaces:** `race_results_view` continues to produce `RaceResultsView`; only preliminary row `meter_tone` changes. No payload schema or CSS changes.

- [x] Add literal table cases for unique aligned/different/no-recommendation leads, ties, zero, rounded ties, sub-majority, write-in ambiguity, measures, unknown advancement rules and missing data; run RED.
- [x] Derive the minimal leader tone in `_preliminary_race_view`; run GREEN with certified/alignment regressions.
- [x] Amend the former preliminary-neutral rule and document color versus outcome semantics in owning docs.
- [x] Verify Guide/race rendering at 390/1280 and exact existing colors with Unofficial/no chips; preserve browser originals.
- [ ] Commit, prepare the normal release request, obtain one independent whole-branch source review, then run the final full `make check` and readiness on the reviewed/fixed candidate.
- [ ] Open a draft PR, consume original CI/feedback, deliver through approved protected workflow, and independently verify production before closing #715.
