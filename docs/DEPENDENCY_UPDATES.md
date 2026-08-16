# Dependency updates

Configured for #226 (O18), part of epic #207. Python and Node dependencies drift silently
otherwise — this makes their updates a predictable, reviewable cadence instead of something that
only surfaces when a stale dependency breaks or blocks something else.

## What's configured

`.github/dependabot.yml` declares two ecosystems, each on the same weekly schedule:

- **`uv`** — Python dependencies pinned in `uv.lock`.
- **`npm`** — Node dependencies pinned in `package-lock.json`, including the exact-pinned
  `wrangler` version in `package.json`. Dependabot has no separate "this one dependency is
  special" carve-out, and it doesn't need one: an exact pin (a bare `x.y.z`, no `^`) still
  updates like any other `npm` dependency, so a new Wrangler release arrives as an ordinary
  reviewable PR rather than silently.

  No test asserts which version any dependency is at, and none should. Every install path is
  `npm ci`, which resolves strictly from `package-lock.json` — the lockfile is the pin, and a
  spec in `package.json` cannot put a different version on a deploy regardless of its style. A
  test asserting a version literal duplicates the lockfile's job, and because it fails on the
  bump itself it stops CI before the checks that would actually judge the new version ever run.

Both ecosystems run **weekly, Monday 09:00 America/Los_Angeles** — a fixed, low-noise cadence
that lands updates early in the week, ahead of most deploy activity, without being frequent
enough to bury reviewers.

## Grouping

Each ecosystem's updates land as one PR (`groups: { <name>: { patterns: ["*"] } }`) rather than
one PR per package. A dozen patch-level bumps reviewed as one diff is a five-minute check; the
same twelve bumps as twelve separate PRs is twelve CI runs and twelve review contexts for the
same amount of actual risk. Grouping trades a rare "one unrelated bump makes the whole group fail
CI and has to be pulled out" cost for the common case being cheap to review.

## The gate

Existing CI (`make check`, run by `.github/workflows/ci.yml` on every pull request) is the only
gate. There is no auto-merge — every update PR is reviewed and merged the same way a human's PR
is. Dependabot's job is to make sure the PR exists on a schedule; it never gets to decide whether
an update is safe.

## The election-window exclusion

Dependabot's schedule is a fixed weekly cadence — it can't read `config/calendar/elections.yaml`
or skip specific calendar dates on its own. The exclusion is a documented manual step, not new
automation: **before a declared election's window opens, pause both Dependabot updates** via
**Settings → Code security → Dependabot → Dependabot updates → Pause**, and **resume them once the
window closes**.

The window reuses the calendar's own statutory anchors (`docs/ELECTION_CALENDAR.md`, "How offsets
are chosen") rather than inventing a separate one: it runs from **ballots mailing (`-18` days)**
through the **post-certification capture, the day after certification** (`+22` after a general,
`+16` after a primary or special) — the same span the results-capture epic already treats as the
period where an unplanned surprise is costliest. Outside that span, a broken dependency bump is
an inconvenience caught by CI; inside it, an engineer's attention is better spent watching the
election than triaging an unrelated Dependabot PR.

This is a manual step because CI already prevents an update from merging unreviewed — the risk
the exclusion manages is reviewer *attention* during the window, not an unsafe auto-merge. A
maintainer checking `config/calendar/elections.yaml` for the next election's dates ahead of time
is the same lightweight, no-new-infrastructure posture the rest of epic #207 takes.
