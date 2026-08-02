# Agent Guide

Read this first; it says where authority lives. Rules are not restated here —
drift between copies is exactly the failure this file exists to prevent.

## Authority map

| Concern | Authority |
|---|---|
| UI/UX: look, voice, color, typography, page vs. modal | `docs/DESIGN.md` |
| Front-end code: modules, rendering, state, contracts, dependencies | `docs/FRONTEND.md` |
| Endorsement-data review | `REVIEW_GUIDE.md` |
| System boundary, pipeline, determinism | `ARCHITECTURE.md` |
| Launch policy and scoring decisions | `DECISIONS.md` |
| Workflow, PRs, local checks | `CONTRIBUTING.md` |

## Working rules

- **Run `make check` before proposing a diff.** It is the gate; green is the
  definition of mergeable.
- **When a check and your plan disagree, change the plan or change the rule —
  in the same pull request.** Never weaken, skip, or route around a check to
  make a diff pass. The docs above state the same contract for design and
  code rules: follow the document or amend it; never silently diverge.
- **Ratchet checks only move one way.** A ceiling or allowlist in the
  enforcement suite may shrink in your PR; it may not grow.
- **Unwired code is not presumed dead.** Check open issues before removing
  anything that merely lacks a caller; in-flight epics land in pieces.
- **Scope comes from an issue.** Link it, stay inside it, and state exactly
  what was verified and what remains incomplete (CONTRIBUTING.md).
