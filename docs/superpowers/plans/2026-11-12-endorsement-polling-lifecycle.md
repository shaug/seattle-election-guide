# Endorsement Polling Lifecycle Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans. Same existing root implements; no new implementation owner.

**Goal:** Stop endorsement link requests and escalation after the election without rewriting failure history.

**Architecture:** The CLI resolves the current source registry and validates calendar identity before any fetch. It returns a distinct closed-period outcome and exposes an actual-state-write receipt for the workflow cache condition.

**Tech Stack:** Existing Python/Typer/Pydantic, pytest and GitHub Actions.

**Spec:** docs/superpowers/specs/2026-11-12-endorsement-polling-lifecycle-design.md

## Global Constraints

- America/Los_Angeles calendar dates own the boundary; election day remains eligible.
- No source requests, failure-state writes or alert reconciliation after that boundary.
- Preserve accepted facts, historical failures and missed collection slots.
- No force, backdating, check weakening, DNS repair, new acquisition or competing publication.

## Review Focus

- UTC midnight is not Pacific midnight: pin 07:59:59Z and 08:00:00Z on November 4.
- A missing or malformed calendar identity must fail before source requests.
- Site election changes must choose that election's registry without workflow edits.
- A skipped or dry run cannot clear cached failure state or close an alert as recovered.
- A real confirmed in-window failure still saves its state even when the command exits nonzero.

## Task 1: Enforce and integrate the lifecycle boundary

**Files:** Modify src/election_guide/cli.py, .github/workflows/check-links.yml, tests/test_sources_check_links_cli.py, tests/test_check_links_workflow.py, SOURCE_POLICY.md and docs/SITE_OPERATIONS_PLAN.md.

**Interfaces:** Keep the optional explicit registry argument; absent it, read --site-manifest config/hosting/site.yaml and select the release-input registry convention (default.yaml for the historical primary; otherwise <current_election_id>.yaml). Read --calendar config/calendar/elections.yaml. Optional --github-output appends state_written=true only after a real state write.

- [ ] Freeze existing positive CLI tests inside the declared voting period. Add regression cases for pre-election/day-of, the Pacific cutoff, repeated closed-period and dry runs with unchanged failure bytes, missing/malformed calendar and registry identity, site rollover and actual cache-output behavior.
- [ ] Run those tests against unmodified production code; retain the real failing assertions and exits.
- [ ] Add the calendar guard before run_link_check and state/alert reconciliation. Add current-election registry selection and the actual-state-write output; preserve normal in-window behavior.
- [ ] Remove the workflow's hardcoded registry and condition cache save on the command's state_written output. Keep serialized daily scheduling for future eligible elections.
- [ ] Amend O17 and source policy to state the closed-voting boundary. Verify CI/publication/freshness/production have no access-only source dependency; change only if an actual dependency exists.
- [ ] Run focused tests green, commit the issue-scoped candidate, then fresh normal owning preparation against the actually accepted predecessor, full make check, affected readiness and all three independent canonical lenses.
- [ ] Drive the reviewed candidate through current required CI, actual candidate inspection, ordinary expected-head merge and original-main publication/protected acceptance. Close #748 truthfully as retirement, retaining its original NXDOMAIN evidence and correcting the obsolete next-poll instruction.
