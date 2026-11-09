# Results update timestamps implementation plan

> **For agentic workers:** Use superpowers:executing-plans for this approved, single-owner correction.

**Goal:** Implement [#728](https://github.com/shaug/seattle-election-guide/issues/728): put the source check time in the body of preliminary-results updates, with US date, minute precision and a.m./p.m. in Pacific time.

**Architecture:** Keep exact authored slugs and aliases. Change only the generator's presentation and three retained entries; a new strict migration binds those presentation fields to the unchanged #718 audit.

**Tech stack:** Python, Pydantic, YAML, pytest, existing release and headless browser tools.

**Spec:** Issue #728; `docs/RESULTS.md` preliminary-update and permalink contracts.

## Global constraints

- Preserve result/evidence/status/count/export/retrieval clocks, totals, all unrelated card timestamps and metadata-only refresh suppression.
- Preserve `docs/audits/updates-718/` byte for byte; no ratchet or allowlist growth.
- Keep second-precision slug identity, including distinct updates in the same minute.
- Parent owns public writes and publication.

## Review focus

- UTC conversion crossing a Pacific date boundary, and daylight/standard time.
- Midnight/noon and dropping seconds without rounding.
- Distinct source check, publisher count and export clocks.
- Exact retained routes, aliases, evidence and original history.
- Migration must reject arbitrary headline/body and other field mutations.

### Task 1: Correct generated and retained update presentation

**Files:** `src/election_guide/results/publication.py`, `data/corrections/wa-2026-general.yaml`, `tests/test_preliminary_publication.py`, `tests/test_updates_history.py`, new `docs/audits/updates-728/`.

**Interface:** `build_preliminary_update(..., checked_at: datetime) -> CorrectionEntry | None` keeps its contract and precise slug; only headline/body presentation changes.

**Guard resolution:** Real same-minute RED exposed the legacy `(date, headline)` duplicate
guard in schema1.2. Use its already-required unique slug/alias identity; retain the legacy
guard for 1.0/1.1 and all routing-collision checks. Parent confirmed this required resolution.

- [ ] Write generator tests for localized check time, no headline timestamp, same-minute identity and clock distinction; run to observe RED.
- [ ] Add a strict #728 presentation-migration fixture and history tests, including negative mutations; confirm the unchanged retained entries fail the new binding.
- [ ] Implement the generator and three retained presentation edits; run focused tests to GREEN.
- [ ] Document the scoped presentation rule, run normal release prepare for #728, and run `make check`.
- [ ] Commit, then run normal request admission, release verification/reproducibility, staging/hosting/Updates checks and rendered index/detail desktop/mobile inspection on that committed candidate.
- [ ] Send parent exact head/tree, diff, checks and preserved evidence for independent review.
