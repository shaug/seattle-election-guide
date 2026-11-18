# Preview label-removal cleanup (#767)

Goal: removing `deploy preview` removes only that PR's Pages previews, including
when labels, pushes and close events arrive during a build or upload. Re-adding
the label restores normal preview deployment. Production and election data do not change.

The issue is the approved scope. Keep the existing deploy and teardown jobs plus lightweight read-only admission,
serialize the entire PR lifecycle without automatic cancellation, and read current
PR identity/labels/head rather than trusting a queued event snapshot. Recheck the
built head immediately before upload. Always reconcile cleanup after the deploy
job, including a skipped/failed build. A subsequent event reconciles current state
again; pending Actions events may replace one another and need not run in order.

An event-only `unlabeled` condition is insufficient after relabeling. Separate
cancelling job locks can interrupt cleanup, so the PR-scoped lock moves to the
workflow with `cancel-in-progress: false`. GitHub documents both pending replacement
and YAML aliases; reuse one inline read-only policy script for all three reads.

- [x] Add regression tests for current label/close/head state, malformed or failed
  reads, re-addition, event races, PR isolation and unchanged cleanup failures.
- [x] Run the tests against the old workflow and retain genuine RED results.
- [x] Update `.github/workflows/deploy-pr-preview.yml`, the existing hosting
  workflow contract, and `docs/HOSTING.md`; preserve base-branch cleanup checkout,
  exact-head build/verification and production isolation.
- [ ] Run focused real Bash/jq fixture tests, lint/type checks and required full
  `make check` in the authorized normal-host execution context. Until it passes, no
  mergeability or deployed claim, no PR proposal, and no browser failure loop.
- [ ] Collect independent read-only review before ordinary authorized delivery;
  no formal GitHub approval or inferred merge authority.

References: https://github.com/shaug/seattle-election-guide/issues/767
https://docs.github.com/en/actions/how-tos/write-workflows/choose-when-workflows-run/control-workflow-concurrency
https://docs.github.com/en/actions/reference/workflows-and-actions/reusing-workflow-configurations
