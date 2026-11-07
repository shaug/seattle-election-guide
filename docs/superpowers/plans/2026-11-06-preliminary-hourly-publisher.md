# Hourly preliminary-results publisher (#696)

Extend the shipped preparation component and preserve the verified General79 snapshot.
Scott has approved lifting the pause and enabling an hourly publisher with repository
contents and pull-request write access. Rendering and formal PR approval remain outside
this change. Use the existing exclusive checkout and normal release gates.

## Design

Reuse the existing archive App, requesting only contents and pull-request write. The
job token remains read-only. A fixed owned branch and one draft PR carry a candidate.
A pending PR suppresses new acquisition; an orphaned pushed candidate is recovered
without another provider request. Never force-push, self-approve, self-merge, bypass
required CI/review or upload a private production build.

Keep the existing hourly cron, explicit enable variable, source intent, exact prior-state
cache and denial holds. Only known complete source outcomes may produce a candidate.
The retained last snapshot survives failures. Capture a maximum of one request per
registered source per eligible tick. New evidence is immutable and content-addressed.

Prepare truthful results Updates for changed counts, publisher clocks/reporting state,
or new unavailable observations. An unchanged verification needs no information Update.
Use the existing normal release prepare, make check and normal PR CI. Reject code,
Primary, symlinked, deleted or over-100-MiB files before stage/push. Ordinary branch push
and PR creation are durable boundaries; preserve failures/uncertain outcomes for recovery.

## Tasks

1. RED/GREEN pure publication planning, truthful Update generation and narrow file staging.
2. RED/GREEN workflow: least-privilege App token, pending-candidate recovery, full checks,
   ordinary push and draft PR, with durable source/candidate failure state.
3. Final current-head make check, normal readiness and fresh complete independent review.
   Publish a draft implementation PR, consume original CI and normal deployment. Then
   enable the approved variable and verify one real publisher run and its candidate.

## Remaining completion distinction

A draft PR alone does not complete #696. Candidate review, merging through the normal
gates and production verification remain required. The first verified cycle and actual
scheduled evidence must be distinguished from merely configured cron. No source-clock,
coverage, certification, device or autonomous-delivery claim may be inferred from fixtures.
