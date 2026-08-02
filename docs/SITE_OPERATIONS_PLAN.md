# Site operations plan (planned 2026-08-01, filed as #202–#227)

Operational and process work to mature the site's deploy, release, monitoring, and
election-planning practice. Scoped to deliberately avoid site rendering and features; the two
items that do touch rendering are called out and deferred.

Item IDs are `O<n>` for work items and `D<n>` for the questions this plan resolved. Every item is
filed; see *Filed issues* below for the mapping. Each epic is a GitHub parent and each `O` item is
one PR-sized child. This document remains the rationale of record — the issues carry the work, and
where they disagree the issues win.

## Findings that shape the plan

Four facts about the current implementation determine what several of these tickets can and
cannot assume.

**F1 — The staged site is origin-bound and commit-bound.** `hosting stage` bakes
`canonical_origin` into every canonical/OG tag, `deployment-manifest.json`, and the generated
`_worker.js`; `hosting verify` re-checks all of it against the manifest and
`--expected-git-commit`. A deployment to a non-production hostname is therefore not "the same
artifact elsewhere" — it either carries production canonical URLs or requires a second staged
build with an overridden origin.

**F2 — Non-canonical hosts are crawlable today.** `PAGES_HEADERS` in
`src/election_guide/hosting/pages.py` sets no `X-Robots-Tag`, and the generated worker only
301-redirects the two declared `LEGACY_HOSTS` to canonical. Every other hostname — `*.pages.dev`
and any future preview host — serves the full guide to crawlers. `docs/HOSTING.md` currently
documents Pages-hostname indexability as a deliberate choice.

**F3 — Cloudflare cannot build this project.** The Pages project is Direct Upload. Automatic
per-PR preview deployments are a Git-integration feature and are not available without letting
Cloudflare run the build, which it cannot do (Python, Chromium, the deterministic
double-build) and should not do (the verification gate lives in GitHub Actions). Per-PR previews
must be built in CI and uploaded with Wrangler.

**F4 — The second election breaks CI as written.** `hosting stage` requires one
`--bundle BUNDLE_ID=PATH` for every election declared in `config/hosting/site.yaml`, resolved to
a locally verified bundle directory. CI passes exactly one. Historical bundles cannot be rebuilt
from current code because `_verify_bundle` checks the pinned release-manifest hash and rendering
changes over time. They must be fetched from their published GitHub Releases.

**F5 — Published release history has already drifted.** `site.yaml` declares
`release_version: 2026-primary.2`. The only GitHub Release is `2026-primary.1`. The bundle that
is live in production has no published archive, so F4's fetch strategy has nothing to fetch for
the current election.

## Filed issues

Filed 2026-08-01. This document remains the rationale of record; the issues carry the work.

| Epic | Issue | Children |
| --- | --- | --- |
| A — Pre-merge preview deployments | #202 | O1 #209, O2 #210 |
| B — Publication control | #203 | O3 #211, O4 #212 |
| C — Release integrity and history | #204 | O5 #213, O6 #214, O7 #215, O8 #216 |
| D — Traffic monitoring | #205 | O9 #217, O10 #218 |
| E — Election operations calendar | #206 | O11 #219, O12 #220, O13 #221 |
| F — Production monitoring and continuity | #207 | O14 #222, O15 #223, O16 #224, O17 #225, O18 #226, O19 #227 |
| G — Post-election results (deferred) | #208 | none; needs a design conversation first |

Sub-issue and blocked-by relationships are populated on the issues themselves. Blockers recorded:
#210 by #209; #212 by #210; #214 and #215 by #213; #218 by #217; #220 by #219; #224 by #222 and
#219.

## Reference implementations in adjacent repositories

`shaug/eldritchdark` (private) already runs the deploy topology this plan proposes, split across
`deploy-pr-preview.yml`, `deploy-preview.yml`, and `deploy-production.yml`. Patterns adopted here
rather than reinvented:

- **Deploy workflows live in their own files**, not as extra jobs inside `ci.yml`.
- **PR previews are opt-in by label** (`deploy preview`), triggered on `labeled`, `synchronize`,
  `reopened`, and `closed`, with a per-PR concurrency group. See O2 for why this matters more here
  than it does there.
- **The fork guard is** `github.event.pull_request.head.repo.full_name == github.repository`.
- **Checkout uses** `github.event.pull_request.head.sha`, not the merge commit.
- **Each preview gets its own GitHub environment** (`pr-<number>`) whose URL is a step output, so
  the deployment surfaces in GitHub's UI.
- **Production is `workflow_dispatch` with a `git_ref` input** defaulting to `main`, resolving the
  SHA explicitly, and **smoke-testing the deployed host after the deploy**.

`shaug/agent-scripts` (public) maintains a rich `CHANGELOG.md`, but inspection found no generator
configuration — no `cliff.toml`, `.releaserc`, or release-please manifest, and nothing
changelog-related in its CI. Its entries are date-grouped narrative prose that use conventional-
commit prefixes in bullets rather than being mechanically generated from them. It is a good model
for *what a changelog entry should say*; it is not a tool to adopt. See O8.

## Readiness

| Ready to file and start | Deferred by decision |
| --- | --- |
| O1, O2, O3, O5, O6, O7, O8, O9, O10, O11, O12, O13, O14, O15, O16, O17, O18, O19 | O4, D1, D2, Epic G |

Every open question was resolved on 2026-08-01; see *Resolved decisions* below. The middle column
of earlier drafts is now empty. O7 and O8 moved to ready on explicit decisions; O11, O12, and O16
on D5; O9 and O10 because they were misclassified — both need investigation rather than a choice,
and a spike belongs inside its ticket, not ahead of it.

Prerequisite for all of it: three new labels. `area: operations` and `type: ops`, because the
existing `area:` vocabulary covers publication, data, and research only; and `deploy preview`,
which O2 uses as its opt-in trigger rather than as a classification.

---

# Epic A — Pre-merge preview deployments

Every pull request gets its own deployed copy of the complete staged site, so changes are
reviewed as rendered pages rather than as diffs. The `check` job already builds, stages, and
verifies the full site on every PR; it only declines to upload. This epic closes that gap.

Deliberately excludes any change to `canonical_origin`. Preview pages keep production canonical
and OG URLs, which is the correct anti-duplicate-content signal and lets O2 ship without the
origin-override design work in D1. Internal links are relative and unaffected.

## O1 — Mark every non-canonical host `noindex`

**Outcome.** Any hostname other than the canonical origin serves the site with
`X-Robots-Tag: noindex`, so preview deployments and the production `pages.dev` hostname cannot
compete with `seattleelections.guide` in search results.

**Scope.** One condition in the generated worker in `hosting/pages.py`, alongside the existing
`LEGACY_HOSTS` branch: when `url.hostname !== CANONICAL_HOST`, attach the header to the response.
Covers asset responses and the 404 path. Update `docs/HOSTING.md`, which currently documents the
opposite policy; this ticket deliberately reverses that decision. Excludes `_headers` changes —
`_headers` is host-blind and cannot express this.

**Acceptance.**
- [ ] A request to the canonical origin carries no `X-Robots-Tag`.
- [ ] A request to a `pages.dev` or preview hostname carries `X-Robots-Tag: noindex`.
- [ ] Legacy-host redirects still 301 to canonical before any header is applied.
- [ ] `hosting verify` passes unchanged; worker generation has test coverage for both branches.
- [ ] `docs/HOSTING.md` states the new indexability rule and why it changed.

**Blocks.** O2 should not deploy previews until this lands.

## O2 — Deploy every pull request to its own Pages preview

**Outcome.** Opening or updating a PR produces a working deployment of the complete staged site
at a stable, predictable URL, linked from the PR.

**Scope.** Follows the `eldritchdark` topology (see *Reference implementations*).

- Add `.github/workflows/deploy-pr-preview.yml` as its own workflow rather than growing `ci.yml`,
  triggered on `labeled`, `synchronize`, `reopened`, and `closed`, with a per-PR concurrency group.
- **Gate on a `deploy preview` label rather than deploying every PR** — see the note below.
- Guard on `github.event.pull_request.head.repo.full_name == github.repository`. Fork PRs never
  receive secrets and never deploy; document that a contributor's branch is previewed by pushing it
  to origin.
- Check out `github.event.pull_request.head.sha`, and pass that commit wherever the build records
  one, so the preview's audit footer shows a hash that exists in the repository rather than the
  ephemeral merge commit.
- Parameterize `--branch` in the `pages:deploy` npm script and pass `--branch=pr-<number>`, so the
  alias is `pr-<number>.seattle-elections.pages.dev` — stable across pushes and immune to the
  slash-mangling that real branch names (`scott/ticket-192-…`) produce.
- Declare a per-PR GitHub environment `pr-<number>` with the preview URL as a step output, so the
  deployment appears in GitHub's UI, plus a sticky PR comment carrying the link.
- Run `hosting verify` on the staged tree before upload, exactly as `deploy` does.
- On `closed`, delete the preview deployment so previews do not accumulate indefinitely.

Excludes any custom preview hostname (D1).

**Label-gating rather than every PR.** The stated goal is that every PR *can* have its own
deployment; label-gating delivers that without spending a deploy on every PR. This matters more
here than in `eldritchdark` because SEG's build is genuinely expensive — Chromium and the
deterministic double release build — and many PRs are data or documentation changes with no
visual surface. If the label proves to be friction in practice, inverting to deploy-by-default
with an opt-out label is a one-line change to the same workflow.

**Acceptance.**
- [ ] Applying `deploy preview` to a same-repo PR deploys it; the URL appears in a PR comment and
      in the PR's environment.
- [ ] The deployed preview's footer commit resolves to the PR head commit.
- [ ] A push to a labeled PR updates the same `pr-<number>` alias rather than creating a new one.
- [ ] An unlabeled PR runs `check` and does not deploy.
- [ ] A simulated fork PR runs `check` and skips the deploy without failing.
- [ ] Closing the PR removes its preview deployment.
- [ ] Production deploys from `main` are unchanged in behavior and target.
- [ ] `docs/HOSTING.md` documents the preview flow, the label, the fork rule, and the alias
      convention.

**Depends on.** O1.

**Note.** Do not use `pull_request_target` to give fork PRs previews. It runs untrusted code with
the Cloudflare API token.

**Open before merge.** Confirm whether Direct Upload preview deployments count against any plan
limit, and whether stale deployments need pruning. If pruning is needed, file it as a follow-up
rather than growing this ticket.

---

# Epic B — Publication control

Separates "merged" from "published." Today every green merge to `main` publishes to production
immediately. The valuable capability is not a preview hostname — Epic A covers pre-merge review —
it is the ability to keep merging work during the week before an election without changing what
voters see.

## O3 — Require approval on the production environment

**Outcome.** A production deploy waits for an explicit human approval, using GitHub's native
deployment-protection mechanism rather than anything repository-owned.

**Scope.** Repository settings only, no code. The `production` environment already exists — the
`deploy` job declares it — and currently carries an empty `protection_rules` list. Add:

- a **required reviewer**, so `deploy` queues rather than publishing on merge; and
- a **deployment branch policy** restricting the environment to `main`, so no workflow can ever
  target the production environment from a pull-request or preview job. This is defense in depth
  for Epic A.

Consider a short **wait timer** as a cheap accidental-merge cushion. Document the approval step
and how it composes with the existing `CLOUDFLARE_PAGES_ENABLED` kill switch in `docs/HOSTING.md`:
the variable is the durable off switch, approval is the per-deploy pause.

**Availability confirmed (2026-08-01).** Environment protection rules are free for public
repositories, and this repository is public. No plan change or paid tier is required.

**Acceptance.**
- [ ] A merge to `main` runs `check`, then queues `deploy` pending approval.
- [ ] Approving publishes; rejecting leaves production untouched.
- [ ] A job on a non-`main` ref cannot deploy to the `production` environment.
- [ ] `docs/HOSTING.md` documents approval, the branch policy, the kill switch, and when to use
      which.

**Note.** With a single maintainer this is self-approval, and `can_admins_bypass` is currently
`true`. That is fine — the value is the deliberate pause and the audit trail in the deployment
log, not enforcement against oneself. It may be the entire deploy-freeze capability the project
ever needs; exercise it for a cycle before building O4 (see D3).

## O4 — Promote an explicit commit to production on demand

**Outcome.** Production can be published from, or reverted to, any chosen commit through a
deliberate `workflow_dispatch` run rather than only as a side effect of merging.

**Scope.** `.github/workflows/deploy-production.yml`, following the `eldritchdark` shape: a
`workflow_dispatch` with a `git_ref` input defaulting to `main`, an explicit step resolving that
ref to a SHA, a deterministic rebuild at that SHA, `hosting verify --expected-git-commit`, deploy
with `--branch=main`, and **a smoke test against the deployed host afterward**. Rebuild-at-promote
rather than artifact-promote, because CI already proves byte-identical rebuilds and Actions
artifacts expire after seven days. Reuses the `--branch` parameterization from O2. Excludes
automatic promotion triggers.

**Acceptance.**
- [ ] Dispatching with a ref publishes exactly that commit's site.
- [ ] Verification failure aborts before any upload.
- [ ] The post-deploy smoke test fails the run if production does not serve the expected commit.
- [ ] Dispatching an older ref restores that earlier site, giving O15 a second rollback path.
- [ ] Concurrency with the merge-triggered deploy is serialized.

**Depends on.** O2 (branch parameterization). Shares the smoke-check logic with O14 — build it
once and call it from both.

**Deferred (resolved, D3).** Not built until O3's approval gate proves insufficient. If O3 covers
the need, this ticket may never be filed.

---

# Epic C — Release integrity and history

Three change streams exist and only one is recorded: data/editorial changes have per-bundle
`RELEASE_NOTES.md` and GitHub Releases; deployment state has `deployment-manifest.json`; site and
code changes have nothing but the commit log. This epic closes that gap and repairs F5.

## O5 — Publish the `2026-primary.2` GitHub Release

**Outcome.** The release version declared in `site.yaml` and running in production has a published,
verifiable archive.

**Scope.** Follow the existing procedure in `docs/RELEASE.md` for the merged mainline commit whose
hash appears in the live bundle: build, inspect, `gh release create` with the bundled notes and the
one versioned ZIP, then re-download and compare SHA-256. Purely a backfill; no code changes.

**Acceptance.**
- [ ] Tag `2026-primary.2` exists, targets the recorded mainline commit, and carries its ZIP.
- [ ] The uploaded asset's SHA-256 matches the locally built archive.
- [ ] The release's commit matches `deployment-manifest.json` in production.

**Blocks.** O7 has nothing to fetch without this.

## O6 — Assert declared release versions are published

**Outcome.** CI fails when `site.yaml` declares a release version with no corresponding GitHub
Release, so F5 cannot recur silently.

**Scope.** A check step iterating every election declared in `site.yaml` and asserting a published
release tag exists for its `release_version`. Extend to compare the release asset's hash against
the declaration once O7 establishes hash pinning. Read-only, no new secrets beyond the default
token.

**Acceptance.**
- [ ] CI fails on a `site.yaml` declaring an unpublished version.
- [ ] CI passes on current `main` once O5 lands.
- [ ] The failure message names the election and the missing tag.

**Depends on.** O5.

## O7 — Materialize historical bundles in CI

**Outcome.** CI can stage a `site.yaml` declaring more than one election, resolving each historical
bundle from its published GitHub Release rather than rebuilding it.

**Scope.** A step that, for every declared election other than the one built from source, downloads
the pinned release ZIP, verifies its hash against the `site.yaml` declaration, unpacks it, and
passes a `--bundle BUNDLE_ID=PATH` for it. Extend `site.yaml` declarations with whatever pinning
the verification requires. Cover with a fixture proving a two-election manifest stages and verifies.
Excludes actually adding a second election.

**Acceptance.**
- [ ] A two-election manifest stages and passes `hosting verify` in CI.
- [ ] A tampered or missing historical archive fails the build with a clear message.
- [ ] `docs/HOSTING.md` documents how a historical bundle is resolved.
- [ ] Current single-election `main` behavior is unchanged.

**Depends on.** O5.

**Resolved (2026-08-01): fetch from GitHub Releases.** The archives are already immutable, hashed,
and published, so the release is the natural bundle store. Rejected alternatives: committing
bundles to the repository (size, and it duplicates the release artifact) and rebuilding historical
elections from pinned code (rendering changes make bytes diverge and the manifest hash check would
fail). This makes a published Release a hard prerequisite for any election the site serves, which
is what O5 and O6 enforce.

## O8 — Generate and verify a site changelog

**Outcome.** `CHANGELOG.md` records site and code changes across releases, generated from the
commit history rather than hand-maintained.

**Scope.** Adopt an existing conventional-commit generator rather than writing one; the history
already follows the convention (`feat:`/`fix:` with PR numbers). Commit the generated file and add
a CI step asserting it is unchanged when regenerated, matching the determinism practice used
elsewhere. Distinguish in the document itself from per-bundle `RELEASE_NOTES.md`, which covers data
and coverage rather than code. No public surface; the site does not link to it.

**Acceptance.**
- [ ] `CHANGELOG.md` exists and covers history back to at least `2026-primary.1`.
- [ ] Regenerating on a clean checkout produces identical bytes; CI enforces this.
- [ ] The document states the split between it and per-release notes.
- [ ] The generator is pinned to an explicit version, like every other tool here.

**Tooling (resolved in principle: use an existing generator; specific choice open).**
`git-cliff` is the recommendation. It is config-driven (`cliff.toml`), renders deterministically
from git history — which is exactly what the regenerate-and-diff check needs — and, critically,
it **only renders history without owning versioning**.

That last point is the deciding constraint. SEG's release versions are election-scoped
(`2026-primary.2`), not semver. Generators that own version bumping and release creation —
release-please, semantic-release — assume semver and would fight the release model documented in
`docs/RELEASE.md`. They are the wrong shape here despite being the more common choice.

**What the referenced repositories actually do.** `shaug/agent-scripts` has no generator; its
changelog is narrative prose grouped by date, using conventional-commit prefixes in bullets. It is
a strong model for entry *voice* — specific, naming issues and consequences — and worth mirroring
in the `cliff.toml` template. `shaug/eldritchdark` has no changelog at all.

---

# Epic D — Traffic monitoring

Understand what voters actually use, especially through the traffic spike in the two weeks before
an election. Explicitly rejects Google Analytics: cookie-based tracking obligates a consent
banner, a consent banner on a nonpartisan voter guide is a credibility and usability cost, and it
would hand voter-interest data to an advertising company. Cloudflare's options are cookieless and
better aligned.

## O9 — Establish the zone-analytics baseline

**Outcome.** Request volume, top paths, status codes, referrers, and country breakdown are
available for the site with no client-side code and no consent obligation, including PDF
downloads that a client beacon cannot see.

**Scope.** Confirm the custom domain's zone reports usable data, document where to find it and how
to read it, and record free-plan retention limits. If retention is too short to span an election
cycle, document the GraphQL Analytics API pull as the follow-up rather than building it here.
No repository code changes expected.

**Acceptance.**
- [ ] A new `docs/MONITORING.md` documents where traffic data lives and what it can answer.
- [ ] PDF download counts are demonstrably obtainable.
- [ ] Retention limits are recorded, with a stated decision on whether history needs exporting.

**No decision required.** An earlier draft of this plan listed O9 as blocked on a decision. That
was a misclassification: what it needs is *investigation* — reading the dashboard and recording
what is actually there — not a choice from anyone. It is ready to start.

## O10 — Add per-page analytics if it can be done without touching rendering

**Outcome.** Per-page views, referrers, and device mix are available, or the ticket closes with a
documented reason not to pursue it.

**Scope.** Spike first: determine whether Cloudflare Pages' automatic Web Analytics beacon
injection works for a project shipping an advanced-mode `_worker.js`. If it does, enable it —
no repository change. If it does not, evaluate injecting the beacon in the worker and weigh that
against the project's rendering-neutrality goal before committing. Cookieless and consent-free
either way.

**Acceptance.**
- [ ] The spike's answer is recorded in `docs/MONITORING.md`.
- [ ] Either the beacon is live and reporting, or the ticket documents why it was declined.
- [ ] No change to rendered guide output in either outcome.

**Depends on.** O9 for the document.

**No decision required to start; one may arrive mid-ticket.** Like O9, this was misclassified as
blocked. The unknown is a fact to establish, not a preference to state: run the spike first. A
decision only becomes necessary if auto-injection turns out not to work, at which point the
fallback — injecting the beacon from the worker — needs an explicit yes or no before proceeding.
Do not adopt worker-side injection without that.

**Weigh this before saying yes to worker injection.** `hosting verify` recomputes the hash of every
staged asset, and the whole publication chain is built on the deployed artifact being exactly the
verified one. A worker that rewrites HTML in flight leaves stored bytes verifiable while making the
bytes *served to readers* differ from anything the manifest attests to. For a project whose
central claim is auditability, that gap may be a good enough reason to decline per-page analytics
entirely and live with O9's server-side numbers.

**Consumer waiting on this.** #193 proposes retiring the generated PDF edition. Download counts
would settle that on evidence rather than intuition.

---

# Epic E — Election operations calendar

Washington's election cadence is statutory and predictable: February and April specials, the
August primary, the November general, plus fixed filing week, ballot-mailing, registration, and
certification dates. The recurring failure mode for this project is not a bad build — it is
missing a data-gathering window that cannot be reopened. This epic makes the cycle a tracked
artifact rather than something remembered.

**This is the highest-priority epic in the plan.** Per D5, the calendar is a first-order process
artifact and the primary driver of development effort going forward: it sets deadlines, orders
feature work, and determines what has to be ready by when. Every other epic here is
infrastructure that serves a release cadence the calendar defines. It is also the only epic whose
value strictly decreases with delay, because its worth is proportional to lead time.

Still not a site feature. See D5 for the deliberate seam left for later rendering use.

## O11 — Declare the election calendar as repository data

**Outcome.** A versioned, validated calendar declaring upcoming election dates and the working-
backward milestones each one implies.

**Scope.** A schema under `config/calendar/` declaring each election's identity and date, plus
milestones derived by offset from it — initialize the election, filing closes and official
inventory imports, source panel freezes, endorsement collection opens, ballots mail and the guide
publishes, refresh points, election day, results capture, certification, retrospective. Populate
for the 2026 general and the 2027 cycle. Add a `election-guide calendar validate` command and wire
it into `make check`, matching how inventory and source configuration are already validated.
Excludes automation and any site consumption.

Include the results-capture milestones pulled forward out of Epic G: election-night capture and
post-certification capture. Those windows are unrecoverable, and they do not depend on any
presentation design.

**Acceptance.**
- [ ] The calendar validates in `make check` and in CI.
- [ ] Invalid offsets, unknown election IDs, and duplicate milestones fail validation.
- [ ] `docs/` gains a document explaining the cadence and how offsets are chosen.
- [ ] Milestones for the 2026 general reference the existing `election init` workflow by name.
- [ ] Election-night and post-certification results-capture milestones are declared.
- [ ] Election identity and dates are modeled cleanly enough to be read by a renderer later,
      while the schema declares no presentation semantics (D5).

**Schema scope (resolved, D5).** Model election identity, dates, and milestone offsets as
first-class validated data suitable for driving planning. Leave the seam for later rendering use
open by declaring no display strings, no banner semantics, and no copy.

## O12 — Open tracking issues from calendar milestones

**Outcome.** A milestone coming due creates a GitHub issue with enough context to act, without
anyone watching a calendar.

**Scope.** A scheduled workflow that reads the calendar, finds milestones due within a lead
window, and opens one issue per milestone using the existing `task.yml` structure, labeled and
attached to a per-election milestone. Idempotent — re-running never duplicates. Excludes closing
issues and any status tracking beyond creation.

**Acceptance.**
- [ ] A due milestone produces exactly one issue, with the election, date, and required action.
- [ ] Repeated runs create no duplicates.
- [ ] A dry-run mode prints what would be created.
- [ ] Manually verified end to end against the next real 2026-general milestone.

**Depends on.** O11.

## O13 — Add a post-election retrospective milestone

**Outcome.** Every election cycle ends with a recorded retrospective, so source-panel and process
lessons carry to the next one instead of being re-learned.

**Scope.** A checklist document covering what to review after certification: source panel
accuracy and gaps, coverage failures, sources that moved or disappeared, publication timing,
corrections issued, and process changes for the next cycle. Referenced by a calendar milestone
at roughly T+30. Documentation only.

**Acceptance.**
- [ ] The checklist exists and is referenced from the calendar milestone definition.
- [ ] It names concrete artifacts to review, not general prompts.

**Depends on.** O11 for the milestone reference; the document itself can be written first.

---

# Epic F — Production monitoring and continuity

The worst outcome for this project is the guide being down, stale, or wrong during the week voters
use it. This epic makes those states detectable and recoverable.

## O14 — Verify production is up and serving the expected commit

**Outcome.** A scheduled check confirms the live site responds correctly and is serving the commit
currently on `main`, and raises a visible alert when it is not.

**Scope.** A scheduled workflow requesting `/`, the current election's guide, its PDF, and
`/deployment-manifest.json`, asserting expected status codes and redirect behavior against the
documented route contract, and comparing the manifest's recorded commit against `main`. Alerts by
opening or updating an issue. Raise the cadence inside an election window. No new infrastructure —
`deployment-manifest.json` already publishes everything required.

**Acceptance.**
- [ ] A healthy site produces a passing run and no issue.
- [ ] A simulated commit mismatch and a simulated 404 each raise an alert.
- [ ] The alert issue is updated rather than duplicated on repeated failures, and closes on
      recovery.
- [ ] Cadence increases within the pre-election window.

**Note.** The commit comparison also catches a silently failed deploy, which a plain uptime check
would miss entirely.

## O15 — Write and rehearse the rollback procedure

**Outcome.** A tested, documented way to return production to a known-good state quickly.

**Scope.** Document both paths: Cloudflare Pages deployment history rollback, and O4's
dispatch-at-SHA rebuild. State when to use which, who can execute them, and expected time to
recover. Rehearse once against production outside an election window and record the actual
observed timings. The rehearsal is part of the ticket, not a follow-up.

**Acceptance.**
- [ ] `docs/` contains the runbook with both paths and a stated preference.
- [ ] The rehearsal is performed and its real timings recorded.
- [ ] Production is verifiably back to the correct commit after the rehearsal.

**Depends on.** O4 for the second path; the dashboard path can be documented and rehearsed first.

## O16 — Alert on stale published data

**Outcome.** Published data going stale during an active election window is detected rather than
noticed.

**Scope.** Extend O14's scheduled check to read the published data timestamp already exposed in the
release manifest and audit footer, and alert when it exceeds a threshold during an active window.
Outside a window, no alert.

**Acceptance.**
- [ ] A simulated stale timestamp inside a window alerts.
- [ ] The same timestamp outside a window does not.
- [ ] The threshold and its rationale are documented.

**Depends on.** O14 and O11. Per D5 the active window is read from the calendar rather than a
separately configured date range, so that election timing has exactly one source of truth.

## O17 — Detect link rot in cited sources

**Outcome.** A cited official source URL that starts returning an error is detected, because a dead
citation is an auditability failure in a project whose central claim is provenance.

**Scope.** A scheduled workflow requesting each URL in the source registry, tolerating redirects,
and opening an issue listing URLs that fail across consecutive runs. Rate-limited and polite.
Reports only; never mutates source data, never rewrites a stored URL, and never re-captures
evidence. Consecutive-failure confirmation avoids alerting on transient errors.

**Acceptance.**
- [ ] A run against current sources completes and reports accurately.
- [ ] A deliberately broken fixture URL is reported only after repeated failures.
- [ ] No source data, evidence, or manifest is modified by the check.
- [ ] Findings are aggregated into one issue per run, not one per URL.

## O18 — Automate dependency updates

**Outcome.** Python and Node dependencies receive proposed updates on a predictable cadence rather
than drifting until something forces the issue.

**Scope.** Configure automated update PRs for `uv.lock` and npm, including the pinned Wrangler
version. Group updates and schedule them to avoid election windows. Existing CI is the gate; no
auto-merge.

**Acceptance.**
- [ ] Update PRs open on the configured schedule and run full CI.
- [ ] Grouping and scheduling are documented, including the election-window exclusion.
- [ ] Wrangler updates arrive as reviewable PRs rather than silently.

## O19 — Document credential and hosting ownership

**Outcome.** Every credential, account, and DNS dependency the live site relies on has recorded
ownership, rotation expectations, and a recovery path.

**Scope.** Document the Cloudflare account and API token including scope and expiry, the GitHub
Actions secrets and variables, apex DNS on Cloudflare nameservers, and Namecheap's role for the
legacy hostname. Add a calendar milestone for token rotation ahead of expiry. Records ownership
and process only — no secret material in the repository.

**Acceptance.**
- [ ] Every credential and DNS dependency in the deploy path is listed with an owner.
- [ ] Rotation procedure is documented for the Cloudflare API token.
- [ ] A rotation milestone is scheduled ahead of any known expiry.
- [ ] No secret values appear in the repository.

**Note.** Election day is the worst possible time to discover an expired API token.

---

# Epic G — Post-election results (placeholder, not ready)

Ingesting certified results and rendering how each race actually completed. Deferred to its own
ticket and its own design conversation; see D4. Recorded here so the calendar work does not
silently assume it.

**Framing (resolved, D4).** This is about tracking *trends*, not measuring performance. The site
does not predict outcomes and is not scored against them. Its purpose is surfacing the candidate
or policy that best matches the value system it represents; how results trend against those
values over successive elections is informative context, not a grade. Language implying accuracy,
prediction, or a track record is out of scope for the epic and for anything it renders.

One operational piece is available immediately and does not depend on the design: **capture
election-night and certified results as evidence at the correct time**, driven by an O11 calendar
milestone. Missing that capture window is unrecoverable in a way that deferring the presentation
design is not. This is folded into O11's milestone set rather than waiting for the epic.

---

# Resolved decisions (2026-08-01)

## D1 — A stable preview hostname and origin override — DEFERRED

Whether to run `preview.seattleelections.guide` as a persistent staging site with its own
`canonical_origin`, distinct from Epic A's per-PR previews. It would require parameterizing
`canonical_origin` through `hosting stage`, `hosting verify`, and `deployment-manifest.json`
(F1) — real work.

**Decided: not now, likely overkill.** Per-PR previews cover pre-merge review. Current feature
churn is expected to stabilize, and the long-term shape of this project is predominantly
data-driven releases rather than continuous feature work — which is exactly the case a persistent
staging site serves least. Revisit only if a concrete need appears that Epic A does not meet. If
it is ever revisited, first confirm Cloudflare permits a custom domain on a preview branch alias.

## D2 — A public corrections log — DEFERRED, decided with Epic G

A user-facing record of editorial corrections: what was wrong, when it was fixed, what changed.
`/about/` already promises a correction path without publishing a record of its use. This is a
trust artifact rather than a developer changelog, it touches rendering, and it raises editorial
questions — what counts as a correction versus a routine data refresh, and how long entries
persist across the archive.

**Decided: scope alongside the post-election results work (D4).** Both concern what the archive
says about itself after publication, and deciding them together keeps that voice consistent.

## D3 — What a deploy freeze actually is — RESOLVED into O3

Whether the project wants a declared window in which only data corrections and priority fixes
publish, and whether that is machine-enforced or observed by convention.

**Decided: use GitHub's native environment protection, and defer O4 until O3 is no longer
sufficient.** O3 adds a required reviewer and a `main`-only deployment branch policy to the
existing `production` environment. Confirmed available at no cost for public repositories, which
this is. A single approver may make mechanized enforcement unnecessary, and a gate that blocks a
genuine correction during ballot week is worse than no gate. O4 is not filed on a schedule; it is
filed if and when the approval gate demonstrably fails to cover a real need. `eldritchdark`'s
`deploy-production.yml` is the template when that day comes.

## D4 — Post-election results design — DEFERRED to its own ticket and conversation

Two separable concerns. The data concern is a collection adapter for King County and Secretary of
State results carrying the same evidence-capture, hashing, and provenance discipline as
endorsements, including the distinction between election-night and certified counts. The
rendering concern is how a completed race presents: winners, advancement out of a primary, vote
shares, certification status.

**Decided: own ticket, own design conversation, and framed as trends rather than performance.**
The site does not predict results and is not scored against them. It surfaces the candidate or
policy that best matches the value system it represents. How results trend against those values
across successive elections is informative context — not a track record, not accuracy, not a
grade. See Epic G for the framing constraint this places on the eventual work.

Meanwhile the results-capture milestones move into O11, so the evidence exists whenever the
design lands.

## D5 — Whether the calendar becomes the site's source of election dates — RESOLVED

Ticket #192 makes election day a self-retiring banner, so the site already needs date awareness.

**Decided: the calendar is a first-order process artifact and the primary driver of development
effort going forward.** Beyond generating reminders, it sets deadlines, orders feature work, and
determines what must be ready by when. Even if it never surfaces on the site directly, it becomes
the organizing input for planning.

Two consequences already applied to this plan: Epic E is promoted to the first sequencing group,
and O16's active-window definition reads the calendar rather than a separately configured date
range. O11 keeps the rendering seam open — clean election identity and dates, no presentation
semantics — so #192 can consume it later without that being a commitment now.

# Still open

Nothing blocks filing. Two questions resolve inside their own tickets rather than ahead of them:
O8's specific generator (`git-cliff` recommended, and the constraint that rules out its
competitors is recorded) and O10's beacon spike, including the contingent worker-injection call
if auto-injection proves unavailable. O4 stays deferred until O3 proves insufficient.

---

# Sequencing

**First — the calendar, plus what is cheap and unblocking.** O11 and O12 lead, per D5: the
calendar drives everything downstream and is the only item whose value strictly decreases with
delay. Alongside it, create the three labels, then O5 (release backfill), O1 then O2 (PR previews —
the highest daily-value item here), and O3 (approval gate, settings only).

**Second, before the next election is added.** O6 and O7 — F4 and F5 make these urgent the moment
a second election is declared — and O14 (production verification), which O16 then extends.

**Third, steady-state hardening.** O15, O17, O18, O19, O16, O9 then O10, O8, O13.

**Deferred by decision.** O4 until O3 is demonstrably no longer sufficient — not on a schedule;
D1; D2 and Epic G together in their own conversation.

---

# Watch items, not tickets

**CI duration.** The `check` job builds the release twice on every pull request under Chromium. That is the correct gate today. It grows as elections accumulate and each
declared bundle must be staged. Worth a stated time budget so the erosion is noticed rather than
absorbed — but not worth weakening the determinism check to fix preemptively.

**Archive growth.** Every past election stays staged and re-uploaded on every deploy. Direct Upload
deduplicates by hash, so this is not currently a concern. Revisit if the archive reaches a size
where upload time becomes material.
