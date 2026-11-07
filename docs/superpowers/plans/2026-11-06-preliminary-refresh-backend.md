# Preliminary refresh backend implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans for native execution. Keep the existing sole writer and checkout.

**Goal:** Prepare complete official refresh candidates automatically without changing rendering or admitting unknown publisher metadata as facts.

**Architecture:** A reviewed stable ID/name/scope map is independent of each immutable capture. A pure report builder verifies complete inventory coverage and preserves nullable clocks/status. A serialized runner acquires the two fixed resources, records failures and access holds, and produces a report without writing `data/results`.

**Tech stack:** Existing Python/Pydantic evidence writer and bounded HTTP transport; GitHub Actions for an initially disabled hourly preparation job.

**Spec:** #696; `docs/RESULTS.md`; `docs/runbooks/results-preliminary-refresh.md`; current explicit instruction to continue independent non-UI work while timestamp wording awaits Scott.

## Global constraints

- Only Scott's subsequently approved State timestamp wording and missing-count-time note;
  no other layout, color, typography or control changes.
- No invented count timestamp, certification status, authority total or outcome.
- Whole inventory: State aggregate for 32 contests, County for 20 jurisdictions contained in King County.
- No alternate-client fallback; held access failures survive scheduled runs.
- The approved full local preliminary snapshot may be prepared. No protected publication,
  formal approval, issue closure or enabled schedule in this component.
- New PRs, when eligible, are draft.

## Review focus

- Mapping omissions, duplicate IDs or changed names must fail before network acquisition.
- County ancestry must prove containment; empty cross-county metadata is insufficient.
- Generic Write-in classification must preserve the contradictory publisher flag and explicit mapping reason.
- State generation time and computed vote sums must never become count time or authority totals.
- A cached denial or an overlapping invocation must stop before another request.

## Tasks

### 1. Stable mapping and pure refresh report

Files: `config/results/wa-2026-general-preliminary.yaml`, `src/election_guide/results/refresh.py`, `tests/test_preliminary_refresh.py`.

- [ ] Write failing tests for full scope, source-ID/name drift, duplicate choices, County containment, clock/status unknowns, and the explicitly mapped Write-in contradiction.
- [x] Implement strict mapping/source/containment validation in the existing producer.
- [x] Validate the retained real pair; preserve original flags, nullable clocks and total basis.

### 2. Serialized acquisition and scheduling preparation

Files: `src/election_guide/results/refresh.py`, `src/election_guide/cli.py`, `.github/workflows/preliminary-results.yml`, related tests/runbook.

- [ ] Write failing tests for preflight before requests, persisted holds, overlap exclusion, partial acquisition failure, and no results-file mutation.
- [x] Implement `prepare_preliminary_refresh(...)`: validate, lock, preflight both sources,
  acquire once each, atomically write the full candidate and preserve actual failures.
- [x] Add explicit `results prepare-refresh --live`; the read-only workflow uses a concurrency
  group, durable intent/artifacts, exact completion cache and an unset-by-default enable variable.
- [ ] Test the workflow contract and command offline. Do not enable or dispatch it.

### 3. Verification and review

- [ ] Run focused tests, lint/types and `make check` on the final non-UI changes.
- [ ] Request independent review within the repository's review contract; report component findings separately from whole-feature readiness.
- [ ] Preserve a local clean checkpoint, complete client matrix and remaining UI/admission boundary.

## Execution rulings

- Scott approved the precise timestamp wording during execution. The existing producer and
  component were extended directly; a separate report-only admission model would duplicate them.
- State missing certification metadata stays null. The guide labels its own reproduction
  preliminary and refuses any explicit true official flag; it does not assert a false State flag.
- Complete-choice vote sums are explicitly tagged; they are not ballots or publisher-stated totals.
- Automatic approval rejected the proposed write-capable App/branch workflow before mutation.
  The implemented alternative has only contents/Actions read permissions and cannot publish.
  Protected autonomous publication remains outside this completed preparation component.
