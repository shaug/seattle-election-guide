# Runbook: production rollback

Return production to a known-good build when the live site is wrong, broken, or stale. Two paths
exist. They are not interchangeable, and the difference matters most when you are under time
pressure and least inclined to reason about it.

One thing to know before anything else: **rolling back does not fix `main`.** Both paths change
what production serves; neither changes what the repository says should be served. Until the bad
commit is reverted on `main`, the next approved deployment republishes it. The revert step is not
cleanup — it is the half of the procedure that keeps the rollback from silently expiring.

## Trigger

Not a calendar milestone. This runbook is due on a condition: **production is serving a build that
is wrong, broken, or stale, and correcting forward would take longer than reverting.**

The condition is normally noticed one of three ways: the scheduled production check (#222) reports
a deployed commit that is not the expected one; a rendered guide is visibly wrong; or a merge that
should not have shipped was approved.

Reach for this runbook only when the wrong build is *already live*. If it is merely merged and
waiting, the cheaper control is rejecting the queued deployment — see `docs/HOSTING.md`,
"Approval". Rejecting costs one click and leaves the live site untouched.

## Autonomy

Level 0 — declared. Human-launched and human-executed, permanently.

Every step here mutates production, and the deploy approval gate is never automated at any autonomy
level (`docs/RUNBOOKS.md`, "Autonomy levels"). An agent session may prepare a rollback — identify
the target deployment, verify what it carries, draft the revert pull request — but a human performs
the promotion itself. This runbook is not a level-3 candidate and is not expected to become one.

**Ownership.** The maintainer is the only Cloudflare account holder and the only `production`
environment reviewer, so both paths are single-person operations today. That concentration is the
continuity risk #227 exists to record; it is not resolved here.

## Preconditions

- **The commit production is currently serving.** Record it before touching anything:

  ```bash
  curl -s https://seattleelections.guide/deployment-manifest.json \
    | jq -r '.current_election_id as $c | .elections[] | select(.election_id == $c) | .git_commit'
  ```

  Write it down. It is what you compare against afterward, and it is what you restore to if the
  rollback turns out to have been the wrong call.

- **A target commit you believe is good**, and a reason to believe it. "The deployment before this
  one" is a reason; "it is older" is not.

- **Cloudflare dashboard access** to the `seattle-elections` Pages project, for path A.

- **`gh` authenticated, and the ability to approve the `production` environment**, for path B only.

- **Nothing else in flight.** A production deployment waiting for approval will publish whatever it
  carries the moment someone approves it, which may undo the rollback you are about to perform.
  Check the repository's Actions page and reject anything queued before you start.

## Procedure

### Step 1 — Choose the path

**Prefer path A.** It re-points production at bytes Cloudflare already holds: it uploads nothing,
builds nothing, and cannot fail on an expired artifact. It is the fast path, and speed is the whole
point of a rollback.

Use **path B** only when path A cannot reach the state you need:

- the known-good state is a commit that was never deployed to production — a fresh revert, for
  example;
- the target deployment has aged out of the retained deployment history; or
- `CLOUDFLARE_PAGES_ENABLED` is unset and you want publication to resume through the normal gate
  rather than as an alias re-point.

Note the asymmetry in the last case: path A works while the kill switch is off, because it happens
entirely inside Cloudflare and never involves GitHub Actions. Path B does not.

**Expected time to recover.**

| Path | Promotion itself | Realistic end to end                                       |
| ---- | ---------------- | ---------------------------------------------------------- |
| A    | seconds          | a couple of minutes, nearly all of it human decision time   |
| B    | a full CI run    | that run, plus however long approval takes to arrive        |

Path A's promotion was measured as effectively instantaneous — see
[Postmortem notes](#postmortem-notes). Treat propagation as free and spend your attention on
picking the right target instead. Path B's timing has not been measured under pressure; assume it
is bounded by CI, and do not choose it when minutes matter and path A can reach the state you need.

### Path A — Roll back the Pages deployment

1. Open the project's deployments list:

   ```text
   https://dash.cloudflare.com/?to=/:account/pages/view/seattle-elections
   ```

   The `:account` placeholder resolves on its own, so there is no account ID to look up.

2. Under **All deployments**, find the target row. Its **Deployment** column carries a permanent
   alias of the form `https://<deployment-id>.seattle-elections.pages.dev`.

3. **Verify the target before promoting it.** The alias serves that deployment's own bytes, so you
   can read exactly what you are about to publish:

   ```bash
   curl -s https://<deployment-id>.seattle-elections.pages.dev/deployment-manifest.json \
     | jq -r '.current_election_id as $c | .elections[] | select(.election_id == $c) | .git_commit'
   ```

   This step is what makes path A safe. The row shows a truncated commit subject, which is not
   identity; the manifest is. If the commit is not the one you intend to publish, stop here — you
   have changed nothing.

4. On the target row, open the `…` overflow menu and choose **Rollback to this deployment**. The
   confirmation dialog lists all four hostnames it will affect — `seattle-elections.pages.dev`,
   both legacy names, and `seattleelections.guide` — and repeats the caveat above in Cloudflare's
   own words: "With automatic deployments enabled, your next commit will update your Production
   environment." Confirm with **Roll back**.

   The **Production** panel at the top of the page updates to name the target deployment. The
   rollback re-points the production alias in place: no history row is added, and none is removed.
   The deployment you rolled *away* from keeps its row and its alias, so rolling forward again is
   the same three clicks on that row.

5. Verify, using [Verification](#verification) below.

6. Revert on `main` — [Step 2](#step-2--revert-on-main). Do not skip it.

### Path B — Rebuild at a ref and publish through the gate

This path publishes a chosen commit through the normal CI-and-approval route, which is the
mechanism `docs/HOSTING.md` already names: "Re-running CI on the exact commit you want is the
dependable way to produce a deployment for it."

1. Find the CI run for the target commit:

   ```bash
   gh run list --workflow=ci.yml --branch main --limit 20 \
     --json databaseId,headSha,conclusion,displayTitle
   ```

2. Re-run it. This rebuilds deterministically at that commit and stages a fresh artifact, which
   matters because Actions artifacts expire after seven days:

   ```bash
   gh run rerun <run-id>
   ```

3. When `check` completes, the `deploy` job queues in a waiting state. Approve it from the workflow
   run page. Approving is deliberately a human moment; do it from the run page rather than
   scripting it.

4. Verify, using [Verification](#verification) below.

5. Revert on `main` — [Step 2](#step-2--revert-on-main), unless the commit you just published *is*
   the head of `main`.

**When O4 lands**, this path collapses into a single `workflow_dispatch` with a `git_ref` input
(#212, deferred by decision D3 in `docs/SITE_OPERATIONS_PLAN.md`). The re-run form above is what
exists today and needs no new infrastructure; replace this section when #212 ships rather than
keeping both.

### Step 2 — Revert on `main`

Production and `main` now disagree. Open a pull request reverting the bad commit, and land it
through the normal gate.

Until that lands, treat `main` as loaded: the next approved deployment publishes it, and if the bad
commit is still there, the outage returns without anyone deciding to bring it back. If the revert
cannot land immediately — the fix is genuinely hard, or it is the middle of the night — set
`CLOUDFLARE_PAGES_ENABLED` to something other than `true` so no deployment can publish while the
divergence stands (`docs/HOSTING.md`, "Kill switch"). Restore it when the revert lands.

## Verification

The rollback is not done until all three of these hold:

1. **The deployed commit is the intended one.** This is the authoritative check:

   ```bash
   curl -s https://seattleelections.guide/deployment-manifest.json \
     | jq -r '.current_election_id as $c | .elections[] | select(.election_id == $c) | .git_commit'
   ```

2. **The guide actually serves.** A manifest is not a page:

   ```bash
   curl -sS -o /dev/null -w '%{http_code}\n' https://seattleelections.guide/e/
   ```

3. **The dashboard agrees.** The **Production** panel names the deployment you promoted. A
   disagreement between the panel and check 1 means the custom domain is not following the
   production alias, which is an escalation, not a retry.

Check 1 is the same comparison #222 automates on a schedule; once that lands, it is what will tell
you a rollback drifted back.

## Escalation

Stop and get help rather than deploying repeatedly when:

- **The manifest still reports the wrong commit** after two checks a few minutes apart. The
  deployment is not the problem — suspect the custom domain binding or an edge cache. Repeated
  rollbacks will not fix either, and each one adds noise to the deployment log.
- **The target deployment's manifest does not carry the commit you expected.** Do not promote it.
  Find the deployment that does, or use path B.
- **No deployment in the retained history carries a good commit.** Path A has nothing to reach for;
  go to path B.
- **The site is down rather than wrong** — the custom domain fails to resolve, or every path
  returns an error. That is a hosting-layer failure, not a bad build, and rolling back will not
  address it.
- **You are inside an election window and the revert cannot land promptly.** Use the kill switch to
  freeze publication and say so out loud; a frozen site serving the last good build is a much
  better state than an unattended divergence between `main` and production.

## Postmortem notes

Runbooks are code: each execution is a test, and what it teaches gets committed. Append a dated
entry after every execution, rehearsal or real.

### 2026-08-12 — first rehearsal (agent-executed, path A)

Rehearsed against live production outside an election window, per #223, with the maintainer
authorizing each mutation. Production was serving `0e984b1` (deployment `55c849e1`); the rehearsal
rolled back to `7a4dd0a` (deployment `95ec602c`), verified, then rolled forward to `0e984b1` and
verified again.

**Timings.**

| Leg                                   | Observed                                                     |
| ------------------------------------- | ------------------------------------------------------------ |
| Confirm → live on `7a4dd0a`           | complete before the first poll — under the measurement floor |
| Confirm → live on `0e984b1`           | complete before the first poll — under the measurement floor |
| Total time production was rolled back | ~40 s (17:45:50Z → 17:46:30Z), including verification        |

Both legs propagated faster than the verification poll could observe. The floor is the polling
round-trip, roughly five seconds, not the platform — so what this rehearsal establishes is an upper
bound rather than a duration: **propagation is not the cost.** Time to recover is dominated by a
human noticing, deciding, opening the dashboard, and identifying the right row. Budget a couple of
minutes end to end and treat the promotion itself as instantaneous.

The 40-second figure is the deliberate gap between the two legs, which included running all four
verification checks. It is not a recovery time; it is evidence that the checks themselves are fast
enough to run before declaring the rollback done.

**Observations.**

- The pre-flight alias check works as written. `https://<id>.seattle-elections.pages.dev/`
  `deployment-manifest.json` served each target deployment's own manifest, so the commit about to
  be published was confirmed before any promotion. This is the step that turns path A from a guess
  into a verified operation; do not skip it to save ten seconds.
- Rollback re-points the production alias in place. The deployment list gained no row and lost
  none, and the deployment rolled away from kept its alias — which is why rolling forward was
  symmetric with rolling back.
- Cloudflare's own confirmation dialog states the revert-on-`main` caveat. Reassuring, but it
  appears *after* you have decided; it is not a substitute for knowing it going in.
- Blast radius was checked before mutating: the two deployments differed only in build-identity
  metadata. A served race page was byte-identical at 206,449 bytes apart from the audit footer's
  commit link. Choosing a rehearsal window where the two candidate builds carry the same voter-
  facing content is worth the five minutes it takes to confirm.

**Not exercised.** Path B was not rehearsed. It publishes through the same CI-and-approval route
that every merge already exercises weekly, so a rehearsal would have re-proven the deploy gate
rather than the rollback. What remains genuinely unproven about path B is its *timing* — how long
a full rebuild takes when you are in a hurry. Record that the first time it is used in anger.
