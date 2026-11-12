# Production Request Diagnostics Implementation Plan

> **For agentic workers:** Use superpowers:executing-plans inline; the final independent review uses the installed local_commit review-fix-loop under the current restricted reviewer contract.

**Goal:** Retain bounded evidence when production HTTP reads fail (#742).
**Architecture:** Add optional diagnostics to Observation and collect them at the existing request boundary. Preserve transport calls, failure outcomes and acceptance logic.
**Tech Stack:** Python, Pydantic, urllib, pytest.
**Spec:** docs/superpowers/specs/2026-11-11-production-read-diagnostics-design.md

## Global Constraints

No UI/data/dependency changes; no request or timeout/retry changes; no partial-body acceptance; no secrets or retained response content; legacy report compatibility. Run make check before proposing the diff. Old General113 retry remains spent.

## Review Focus

- Header-only route probes never read bodies.
- Truncation and reset retain failure while exposing available framing/partial metadata.
- Diagnostic field collection cannot mask original errors.
- Header/exception metadata stays bounded and excludes secrets.
- Optional records survive JSON serialization without changing strict acceptance.

### Task1: Request diagnostics

**Files:** Modify production_check.py, production_probe.py, tests/test_production_probe.py and docs/HOSTING.md.

- [ ] Write failing regressions for real truncated/successful responses, pre-response errors, body reset, safe headers and report round-trip; verify RED.
- [ ] Add minimal optional diagnostics and shared request collection, preserving existing behavior; verify focused GREEN.
- [ ] Commit the issue-scoped change, run full make check and normal release admission as applicable; fix only actual failures.
- [ ] Run fresh all-three-lens independent local_commit review. Publish only an authorized DRAFT PR with precise validation/limits.
- [ ] Reconcile exact deployed source before any separately documented bounded instrumented verification; never reset old retry or borrow a stale source acceptance.
