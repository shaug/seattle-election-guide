# Cloudflare Pages hosting

The public archive is a Direct Upload Cloudflare Pages project named `seattle-elections`. GitHub
Actions builds and validates the current release, resolves every release declared in
`config/hosting/site.yaml`, composes the complete archive, and then uses the repository-pinned
Wrangler version to upload that exact artifact. Cloudflare does not run the Python build itself.

## One-time setup

Install the Node dependency and authenticate Wrangler locally:

```bash
npm ci
npx wrangler login
npm run pages:create
```

The create command configures `main` as the production branch. It creates an empty Direct Upload
project at `seattle-elections.pages.dev`; subsequent dashboard drag-and-drop uploads and Wrangler
uploads target the same kind of Pages project. If that project name is unavailable, update both
`wrangler.jsonc` and the documented hostname before continuing.

Create a Cloudflare custom API token with **Account / Cloudflare Pages / Edit** permission and note
the Cloudflare account ID. Store both values under the GitHub repository's Actions secrets:

- `CLOUDFLARE_API_TOKEN`
- `CLOUDFLARE_ACCOUNT_ID`

The workflow uses the GitHub `production` environment with a `main`-only deployment branch policy.
Under **Settings / Environments / production**, add a deployment branch rule naming `main` and
leave required reviewers and the wait timer disabled. Production deploys automatically after CI
passes. [Deployment gate](#deployment-gate) describes the checks and publication switch.

Leave publishing disabled until the project and both secrets exist. Then create the repository
Actions variable `CLOUDFLARE_PAGES_ENABLED` with the exact value `true`. Run the **CI** workflow
manually on `main` for the first upload. That run, and every push to `main` after it, builds,
validates, stages, and deploys automatically when all checks pass. A pull
request deploys only when it is opted in, and only from a branch in this repository — see
[Pull request previews](#pull-request-previews).

## Custom domains

The canonical public hostname is `seattleelections.guide`. Add it to the Pages project under
**Custom domains** and manage its apex DNS through Cloudflare. The staged Pages worker permanently
redirects these legacy hostnames to the canonical hostname while preserving the request path and
query string:

- `seattle-elections.dobravoda.dev`;
- `seattle-elections.guide`;
- `www.seattleelections.guide`.

Every legacy hostname must be associated with the Pages project so Cloudflare can terminate HTTPS
before the worker redirects the request. The redirect retains the complete election-scoped path and
query string. For `seattle-elections.dobravoda.dev`, Namecheap remains the authoritative DNS
provider and publishes this record after Pages accepts the hostname:

| Type | Host | Value |
| --- | --- | --- |
| CNAME | `seattle-elections` | `seattle-elections.pages.dev` |

The apex `seattle-elections.guide` domain must use Cloudflare nameservers before it can be attached
to Pages. A registrar URL-forwarding record is not sufficient because it does not provide the TLS
endpoint required before an HTTPS redirect can run. Certificate issuance and DNS propagation may
take time after either hostname is attached or repointed.

`www.seattleelections.guide` is on the same zone as the canonical apex, so it shares the apex's
Cloudflare nameservers and needs no separate DNS record — only attachment to the Pages project, the
same way as the other legacy hostnames: **Custom domains** on the Pages project. That attachment is
done; `www` now 301-redirects to the apex like the other legacy hosts. Cloudflare's proxied DNS
accepts a connection to any hostname on a zone it manages, including one that is not attached to an
origin, so an unattached `www` record used to fail at the edge with a `522` rather than never
resolving — the failure mode issue #382 fixed.

## Archive manifest and routes

`config/hosting/site.yaml` is the versioned source of truth for the site. Its ordered election list
declares the current election first and binds every public election ID to a logical bundle ID,
release version, and source-panel identity/hash. Git commit, release-manifest hash, and complete
bundle hash fields pin older immutable inputs more tightly. All three are optional for a bundle
supplied from a local build, but `bundle_sha256` is required for one resolved from a published
release, and staging refuses to resolve it without one — see
[Historical bundles](#historical-bundles). The staging command resolves each logical bundle ID to a
verified release bundle, supplied locally or downloaded from the release that published it; it never
infers the current election from dates, filenames, directory order, or an earlier deployment.

The public route contract is:

- `/` returns a temporary `307` redirect to the manifest-declared current election;
- `/e/` is an index of every declared guide, with the current election listed first;
- `/e/<election-id>/` serves that election's HTML, release status, and release manifest;
- `/e/<election-id>/<anything>.pdf` returns a permanent `301` redirect to that election's guide
  page, so links to the retired generated PDF edition (issue 193) still resolve;
- `/e/<election-id>/races/<race-id>/` serves one race's own page and, beside it,
  `og-image.png` — that race's build-time social card, so a shared race unfurls as the race rather
  than as the site (issue 136). Every race in every published election's inventory has one,
  archived elections included, and `/e/<election-id>/races/` is not itself a page;
- a directory addressed without its trailing slash redirects to the trailing-slash form with a
  permanent `308`, which covers `/e/<election-id>` and every race page from one rule;
- the current election may set `comparison_route_preview: true` to serve
  `/e/<election-id>/comparisons/` and canonicalize its slashless form without adding a link from the
  guide, Sources, archive, About/FAQ, or 404 page; this preview override is rejected for historical
  elections and the release's comparison policy remains the source of truth for public promotion;
- `/about/` is a site-wide, hand-authored About/FAQ page explaining the methodology, source-panel
  versioning, and how to report a correction, with reciprocal navigation to the current guide;
  every rendered guide links back to it from its footer;
- `/about` redirects to the trailing-slash form;
- `/calendar.ics` is a site-wide RFC 5545 calendar of voter-facing election dates, served as
  `text/calendar; charset=utf-8`; and
- unknown elections, assets, and other paths return a real `404` with `noindex`.

The calendar feed is generated from `config/calendar/elections.yaml` at staging time and carries
only milestones marked `public: true`; its `DTSTAMP` is the current release's build timestamp
rather than the clock, so restaging the same inputs produces identical bytes. It joins the staged
asset set like any other file, so `hosting verify` checks its hash against the deployment manifest.
`docs/ELECTION_CALENDAR.md` explains how a milestone is marked public and when to bump its
`revision`.

The generated Pages worker uses an exact staged-asset allowlist before consulting the Pages asset
binding. This prevents Cloudflare's document fallback from turning a historical-looking unknown URL
into the current guide. The archive and known election pages remain indexable on the canonical
host. Rendered guides set their canonical and Open Graph URL to
`https://seattleelections.guide/e/<election-id>/`, and each race page sets its own to
`https://seattleelections.guide/e/<election-id>/races/<race-id>/`.

### Only the canonical host is indexable

The worker attaches `X-Robots-Tag: noindex` to every asset response whose hostname is not
`seattleelections.guide`. Legacy hosts are redirected to canonical before the rule applies, so that
hop stays a bare `301`, and the `404` page is `noindex` on every host including canonical.

This reverses an earlier decision (issue 209). Indexing the Cloudflare Pages hostnames alongside the
custom domain was reasonable while `seattle-elections.pages.dev` was the only other name for the
site. It stops being reasonable once every pull request can mint a hostname serving a complete copy
of a voter guide, because a preview's endorsement data may already be wrong and nothing outside the
canonical host is a claim this project wants to publish. The rule lives in the worker rather than
`_headers` because `_headers` is host-blind and cannot express it.

## Published releases

Every election the site serves is expected to have a published GitHub Release whose tag is the
`release_version` declared for it in `config/hosting/site.yaml`. That archive is the durable copy of
the bundle: it is what a historical election is resolved from once it is no longer built from
source, and what an audit compares a deployed guide against.

Nothing enforced that pairing before, so the two drifted — `2026-primary.2` was declared, built, and
deployed while only `2026-primary.1` had ever been published (issue 213). CI now rejects that:

```bash
uv run election-guide hosting verify-releases config/hosting/site.yaml
```

By default, the command reads every declared election and fails when a `release_version` has no
published Release, naming each election and the tag it expects. Draft releases do not count; a draft
carries a tag name but publishes no archive. It reads release state through the GitHub CLI, so `gh`
must be installed and authenticated — CI supplies the default `GITHUB_TOKEN`, and the check is
read-only.

Publishing a release is described in [RELEASE.md](RELEASE.md). Publish first: this check runs on
pull requests, so a new `release_version` must already have a published Release before the pull
request that declares it in `site.yaml` can pass CI.

The one exception is prepublication staging of the manifest-declared current election. Automation
may name that exact bundle once with `--candidate-bundle-id`; every historical election must still
have a published, non-draft Release. A historical, undeclared, mismatched, or repeated candidate is
rejected. Use one value for both the exception and the local bundle supplied to staging:

```bash
CANDIDATE_BUNDLE_ID=wa-2026-general-2026-general.6
uv run election-guide hosting verify-releases config/hosting/site.yaml \
  --candidate-bundle-id "$CANDIDATE_BUNDLE_ID"
uv run election-guide hosting stage config/hosting/site.yaml \
  --bundle "$CANDIDATE_BUNDLE_ID=dist/general-release/bundle" \
  --released-bundle-dir dist/released-bundles \
  --expected-git-commit "$(git rev-parse HEAD)"
```

That mode changes only the remote-publication check; staging still verifies bundle identity,
release metadata, canonical assets, hashes, and the current bundle's commit. It is legal only while
preparing or previewing the current candidate. Before upload, deployment must run
`hosting verify-releases` again with no candidate option, so an
unpublished candidate can never cross the production boundary.

## Historical bundles

Only the current election is built during staging. An older election is downloaded from its
declared Release, because rebuilding an existing release identity with newer rendering code
would violate its artifact hashes. To correct an archived guide, build and publish a new immutable
release from merged mainline code and the completed election inputs, then update its version and
reviewed pins. Existing release artifacts remain unchanged and available for audit.

Every served HTML page must exclude the retired percentage-only meter's `--meter-fill` chrome.
Both bundle staging and independent staged-site verification reject it, even when all recorded
hashes agree. An authentic older release is an audit record, not permission to restore retired UI.

Pass `--released-bundle-dir` to resolve every declared bundle that was not supplied with
`--bundle`:

```bash
uv run election-guide hosting stage config/hosting/site.yaml \
  --bundle wa-2026-general-2026-general.6=dist/general-release/bundle \
  --released-bundle-dir dist/released-bundles \
  --output-dir dist/cloudflare-site
```

Each unresolved election's versioned ZIP is downloaded through the GitHub CLI, unpacked under that
directory, and staged like any other bundle. Supplying every bundle locally downloads nothing; the
supported two-election composition instead supplies the general locally and resolves the primary.

An election resolved this way **must** declare `bundle_sha256`, and staging rejects it otherwise. A
downloaded archive is remote input, and the release manifest travelling inside it cannot vouch for
it: whatever could replace the artifacts could replace their recorded hashes too. The pin lives in
`site.yaml`, which is under review, so it is the one hash an attacker who controls the archive does
not control. Archive entries outside the bundle root, or with parent-directory segments, are
rejected before anything is written.

### Computing the pin

`hosting bundle-hash` prints that value for one bundle directory, and prints nothing else, so it can
be pasted into `site.yaml` or captured directly. Compute it from the published archive rather than
from a local build directory: the archive is what staging downloads, and a local directory can pick
up files the archive never carried.

```bash
gh release download 2026-primary.3 \
  --pattern 'seattle-election-guide-*.zip' --dir dist/pin
unzip -q dist/pin/seattle-election-guide-2026-primary.3.zip -d dist/pin
uv run election-guide hosting bundle-hash dist/pin/seattle-election-guide
```

The digest covers every file in the tree, each path and body length-prefixed so two different trees
cannot concatenate to the same bytes. The command reads the tree and writes nothing; it refuses a
directory with no `release-status.json`, because a pin computed from the wrong tree is wrong
silently. When a declared pin and the downloaded archive disagree, staging names both digests —
`expected <declared>, found <computed>` — so the difference can be reviewed rather than guessed at.

## Local staging and preview

Build the audited release as described in [RELEASE.md](RELEASE.md), then stage it:

```bash
make hosting-stage
```

The Make target supplies the current election's bundle as
`wa-2026-general-2026-general.6=dist/reproducibility-a/bundle` and passes
`--released-bundle-dir dist/released-bundles`, which is the pair CI stages with. The current election
is the only one built from source, so when another election is declared it resolves from the release
that published it rather than from anything prepared locally — see
[Historical bundles](#historical-bundles). The archived primary therefore comes from its published,
hash-pinned `2026-primary.3` release, containing the completed primary's certified results and
Meter v2. That download reads GitHub, so `gh` must be installed and
authenticated.
Staging verifies all declared identities, each release status, every release-manifest artifact hash,
and the current bundle's exact Git revision before it changes the existing output. It then
atomically replaces `dist/cloudflare-site/` with:

- `e/index.html`, generated from the manifest;
- each guide at `e/<election-id>/index.html`, copied byte-for-byte from its validated release;
- each election's `release-status.json` and `release-manifest.json`;
- `about/index.html`, the site-wide About/FAQ page, generated from the manifest;
- a site-wide deployment manifest recording every verified release and staged asset hash; and
- `_headers` with browser-security and revalidation policy. Indexability is not set here: it
  depends on the request's hostname, which `_headers` cannot see, so the worker applies it.

`hosting stage` verifies the completed tree before the atomic swap. The same integrity gate can be
run independently, and CI runs it once before artifact upload and again after the deploy job
downloads the artifact:

```bash
uv run election-guide hosting verify \
  config/hosting/site.yaml \
  dist/cloudflare-site \
  --expected-git-commit "$(git rev-parse HEAD)"
```

Verification validates the deployment-manifest schema and election identities, binds each staged
release status/manifest to its declaration, requires the exact declared asset set, and recomputes
every asset hash. `deployment-manifest.json` is the documented sole exclusion from its own asset
hash map.

Preview the staged directory with Wrangler:

```bash
make hosting-serve
```

For an exceptional local production upload, run `make hosting-deploy` after authenticating
Wrangler. The target stages with the narrow current-candidate exception, then requires every
declared release to be published with no exception before it invokes the upload. Normal publication
should go through GitHub Actions so the deployed artifact is the one that passed the full mainline
release checks.

## Pull request previews

A pull request can be reviewed as rendered pages rather than as a diff. Apply the **`deploy
preview`** label and `.github/workflows/deploy-pr-preview.yml` builds the release at the pull
request's head commit, stages the complete site, verifies it, and uploads it as its own Pages
deployment. A single comment on the pull request carries the link and is rewritten in place on each
push.

The preview lives at:

```text
https://pr-<number>.seattle-elections.pages.dev
```

The alias comes from the pull request number, not the branch name. It is therefore stable across
pushes and immune to the mangling that slashes in a real branch name would cause. Pushing to a
labeled pull request replaces the deployment behind the same alias instead of minting a new address.

Four rules govern when a preview exists:

- **Opt in with the label.** Previews are not automatic. This build is expensive — Chromium
  rendering plus a full release build — and most pull requests here change data or prose with no
  visual surface. Removing the label stops future deployments. If the label ever becomes friction,
  inverting to deploy-by-default with an opt-out label is a one-line change to the same workflow.
- **Only branches in this repository.** The deploy job requires
  `github.event.pull_request.head.repo.full_name == github.repository`. A pull request from a fork
  skips the job — it is not failed, and it never receives the Cloudflare secrets. Preview a
  contributor's work by pushing their branch to origin and opening a pull request from it. The
  workflow deliberately does not use `pull_request_target`, which would run a fork's code with the
  Cloudflare API token in scope.
- **Closing tears the preview down.** Closing or merging the pull request deletes its deployments.
  Teardown is not label-gated, so a preview whose label was removed before the pull request closed
  is still cleaned up.
- **`CLOUDFLARE_PAGES_ENABLED` still applies.** Previews respect the same publication switch as
  production.

Previews carry `X-Robots-Tag: noindex` like every other non-canonical host, so a preview cannot
compete with the real site in search results. Its pages still declare the production canonical URL,
because a preview is a copy of the site rather than a separate site.

Production is unaffected. The `pages:deploy` script defaults to `--branch=main`; only the preview
workflow overrides it, by setting `PAGES_BRANCH`.

## Publication-day production probe

After a deployment completes, use the read-only production checker. Supply the full deployed
`production_candidate_sha`; the checker refuses a base URL
other than the site manifest's canonical origin and uses that manifest as the trusted expectation
for election order, current marker, release and bundle identities, panel/registry identities, and
the historical declaration.

<!-- runbook-command:production-probe -->
```bash
uv run election-guide hosting check-production \
  https://seattleelections.guide \
  --site-manifest config/hosting/site.yaml \
  --expected-git-commit "$production_candidate_sha" \
  --output dist/production-probe.json
```

Production checking is always read-only: it never opens, updates, or closes GitHub issues and does
not require GitHub credentials. The former `--dry-run` and `--repository` options are retired (#523).

The JSON output preserves the checked URL and time, the raw HTTP status and `Location` header for
every redirect, the complete expected and observed deployment manifests, all route results, and the
resolved representative race. That race is the lexicographically first current-election race route
in the fetched schema-valid deployment manifest's asset inventory. The checker also requires:

- a temporary `307` from `/` to the manifest-declared general guide;
- `/e/` with the complete ordered election list and only the general marked current;
- successful general and historical-primary guides;
- successful representative race and comparisons pages;
- a genuine `404` from a deterministic unknown-election path; and
- `2026-general.6` and the exact `production_candidate_sha` in the public manifest.

Attach `dist/production-probe.json` to the deployment issue with the CI run and artifact,
deployment ID, full deployed SHA, and deployment time. Run the same command a second time after
deployment completion and preserve that output separately (for example,
`dist/production-probe-confirmation.json`); both probes must pass. A failure preserves evidence and
routes the operator to [the production rollback runbook](runbooks/production-rollback.md). It never
authorizes a rollback, kill-switch change, or deployment of another SHA.

## Production verification policy

Hourly production monitoring and its alert issues are retired (#523), superseding the availability
schedule introduced by #512. This site serves immutable assets through a stateless Cloudflare Pages
worker. A failure after a verified deployment usually offers little action beyond investigating
Cloudflare or domain configuration. A failed deployment probe instead identifies a release that
can be corrected or rolled back.

The protected `deploy` job runs strict, read-only verification immediately after its production upload,
using the job's full `GITHUB_SHA`, and preserves `production-probe.json` as an Actions artifact.
A failed probe fails the deployment job; it does not roll back or authorize another deployment.
Strict verification requires `--expected-git-commit`; combining it with `--availability-only` is
rejected rather than silently discarding the release expectation.

For a manual availability diagnosis without release expectations:

```bash
uv run election-guide hosting check-production https://seattleelections.guide --availability-only
```

This fetches and parses the served deployment manifest, checks the home redirect, requests the
current guide declared by that manifest, and checks its legacy PDF redirect. Both redirects must
point to the canonical production origin. It does not compare the site with `main`, enforce
unpublished release declarations, or check data age. The result is printed with a nonzero exit
status on failure; `--output` can preserve the JSON report. It creates no alert issues.

## Production freshness check

Strict release verification reads the current election's public `release-manifest.json` and treats
its `generated_at` value as stale when it is more than seven days old during the seven-day
pre-election window. The manual availability probe does not run this check. Outside that window,
age alone never fails strict verification. The window comes from the `election_day`
milestone in `config/calendar/elections.yaml`; no second election date is configured in the probe.

Seven days matches the guide's planned weekly refresh rhythm: the calendar schedules refreshes
at eleven and four days before election day. The comparison is strict: exactly seven days old
still passes. Recurring endorsement verification remains separate from availability monitoring.

## Deployment gate

The `deploy` job depends on the complete CI `check` job. CI builds the deterministic current release
twice, compares the manifest-declared deterministic artifacts, separately validates an archive's
structure, contents, and rendered output, resolves all manifest-declared bundles, stages the
complete site, and uploads the staged directory as a short-lived GitHub Actions artifact. Only then
can the production job download and upload it with Wrangler. Concurrent production uploads are
serialized.

When publication is enabled, a merge to `main` runs `check` and then deploys automatically. The
`production` environment has no required reviewers or wait timer. Manual approval was removed in
#521 because its prompt was detached from a preview of the changes and added no useful review.

The job downloads the `cloudflare-site` artifact from that same CI run, verifies it against the
run's full `GITHUB_SHA`, and requires every declared release to be published before uploading.
After upload, the strict production probe checks the deployed SHA and preserves its report as
the `production-probe` artifact. A mismatch fails the job; it does not trigger an automatic rollback.

The deployment log records the commit each job publishes. Concurrent uploads are serialized, and
a newer queued job can replace an older queued job. Always use the job's explicit SHA when checking
production, even if `main` has advanced. Re-running CI on the exact commit you want is the
dependable way to produce a deployment for it. Actions artifacts expire after seven days; if the
`cloudflare-site` artifact is missing or expired, rebuild it by rerunning CI for that exact commit.

### Branch policy

The same environment restricts deployments to one branch, `main`. A workflow running on any other
ref cannot target `production` at all, so a pull-request or preview job cannot reach the production
Pages project even if it names the environment. The `deploy` job already tests
`github.ref == 'refs/heads/main'`; the branch policy enforces that same rule from repository
settings, where editing the workflow cannot reach it.

### Kill switch

To stop automatic publication without changing code, set `CLOUDFLARE_PAGES_ENABLED` to any value
other than `true` or delete the variable. The `deploy` job is skipped outright and no deployment is
created.

### Which one to use

Review changes before merging, using [Pull request previews](#pull-request-previews) when useful.
Merging starts the automatic CI-and-deployment path.

The variable is the durable off switch. Use it while Cloudflare credentials are rotated, while the
Pages project is rebuilt, or during a publication freeze. While it is unset, new CI runs skip
`deploy`. Cancel any already queued or running production jobs separately. To resume publication,
restore the variable to `true` and run CI on the intended `main` commit; restoring it does not rerun
skipped jobs.

## Credential and hosting ownership

[One-time setup](#one-time-setup) covers standing the deploy path up once. This section covers its
ongoing custody: everything the live site depends on, who owns it, and how to recover it. There is
one maintainer today, so every row below has the same owner — the point of writing it down is
recovery speed under pressure, not division of labor. Election day is the worst possible time to
discover an expired token or a DNS record nobody remembers configuring.

No secret values live here or anywhere else in this repository. Tokens and account identifiers are
named by purpose only; their values live in the Cloudflare dashboard and GitHub's encrypted secret
store, never in git history.

| Dependency | Where it lives | Purpose | Recovery path |
| --- | --- | --- | --- |
| Cloudflare account | Cloudflare dashboard | Owns the `seattle-elections` Pages project, the `seattleelections.guide` zone, and the API token below. | Account recovery through Cloudflare support using the maintainer's registered email. |
| Cloudflare API token | GitHub Actions secret `CLOUDFLARE_API_TOKEN` | Scoped to **Account / Cloudflare Pages / Edit**; authorizes the `wrangler pages deploy` upload in `deploy` (production) and `deploy-pr-preview.yml` (previews). | See [Rotating the Cloudflare API token](#rotating-the-cloudflare-api-token). Until a new token is in place, set `CLOUDFLARE_PAGES_ENABLED` to anything but `true` — see [Kill switch](#kill-switch) — so a broken or revoked token fails closed instead of failing every deploy job loudly. |
| Cloudflare account ID | GitHub Actions secret `CLOUDFLARE_ACCOUNT_ID` | Identifies which Cloudflare account the token above acts on; required by every `wrangler pages` invocation. | Stable for the account's lifetime. Re-read from the Cloudflare dashboard sidebar and update the secret if the account is ever recreated. |
| Cloudflare analytics token | GitHub Actions secret `CLOUDFLARE_ANALYTICS_TOKEN`; local environment for manual exports | Scoped to **Zone / Analytics / Read** on `seattleelections.guide`; optional manual zone-analytics export only. The daily archive workflow was retired in #512. Separate from the deployment token. | Rotate any retained token with the same **Zone / Analytics / Read** scope; validate a manual export to a separate directory before revoking the old token. There is no unattended archive to restore or retention deadline to maintain. |
| Cloudflare zone ID | GitHub Actions secret `CLOUDFLARE_ZONE_ID` | Identifies which zone the analytics token reads; required by every GraphQL analytics query. Not secret in Cloudflare's own terms — it appears in dashboard URLs — but stored as a secret because this repository names account identifiers by purpose only and commits none of their values. | Stable for the zone's lifetime. Re-read from the Cloudflare dashboard's zone overview (right sidebar, **API → Zone ID**) and update the secret if the zone is ever recreated. |
| Analytics archive GitHub App (retired) | Maintainer-owned GitHub App; client ID in `ANALYTICS_ARCHIVE_APP_CLIENT_ID`, private key in `ANALYTICS_ARCHIVE_APP_PRIVATE_KEY` | Previously installed only on this repository with **Contents / Read and write**, **Pull requests / Read and write**, and **Workflows / Read and write**. No workflow uses it after #512. | The maintainer may revoke the App and remove its Actions credentials. Until revoked, rotate any retained active private key annually and after suspected exposure. Do not recreate the retired archive automation. |
| Publication switch | GitHub Actions variable `CLOUDFLARE_PAGES_ENABLED` | The durable kill switch described in [Which one to use](#which-one-to-use). | Not a credential; reset to `true` once the dependency it was protecting is healthy again. |
| Apex DNS (`seattleelections.guide`) | Cloudflare nameservers | Canonical hostname's DNS and TLS termination; required before Pages can attach a custom domain to it. | Domain registrar account controls which nameservers are authoritative. If Cloudflare nameserver delegation is ever lost, the canonical hostname stops resolving until it is restored — this is the single highest-impact entry in this table. |
| Apex DNS (`seattle-elections.guide`, legacy) | Cloudflare nameservers | DNS and TLS termination for the hyphenated legacy hostname redirected to canonical — see [Custom domains](#custom-domains). Requires Cloudflare nameservers for the same reason the canonical apex does. | Domain registrar account controls which nameservers are authoritative. Losing this delegation breaks only this hostname's redirect; the canonical hostname is unaffected. |
| Legacy DNS (`seattle-elections.dobravoda.dev`) | Namecheap | Publishes the CNAME to `seattle-elections.pages.dev` documented in [Custom domains](#custom-domains), keeping the retired hostname's redirect alive. | Namecheap account recovery through the maintainer's registered email. Losing this record breaks the legacy redirect only; the canonical hostname is unaffected. |
| GitHub `production` environment | Repository Settings → Environments | Carries the `main`-only branch policy described in [Deployment gate](#deployment-gate), with required reviewers and the wait timer disabled. | Repository admin access recreates it from [One-time setup](#one-time-setup) if it is ever deleted. |

The archive App setup is retired (#512). Its inventory above records any credentials that still
exist. Production probes are read-only and require no GitHub credentials (#523).
The daily archive does not need to be recreated to operate the site.

### Rotating the Cloudflare API token

1. In the Cloudflare dashboard, create a replacement custom token with the same **Account /
   Cloudflare Pages / Edit** permission the original carries — see [One-time
   setup](#one-time-setup).
2. Update the `CLOUDFLARE_API_TOKEN` GitHub Actions secret with the new value. This takes effect
   on the next workflow run; nothing else in the repository names the token.
3. Confirm the rotation before revoking anything: run the **CI** workflow manually on `main`, or
   wait for the next scheduled preview build, and check that the `deploy` (or preview) job
   authenticates successfully.
4. Revoke the old token from the Cloudflare dashboard once step 3 has confirmed the new one works.
   Revoking first would leave no working token if step 2 had a typo.

If a token is compromised rather than routinely rotated, reverse steps 4 and 1: revoke the
compromised token immediately, then create and install its replacement. A dead token fails deploys
loudly; a live compromised one fails silently.

### Rotation milestone

Cloudflare custom API tokens carry no forced expiry unless one is set explicitly at creation, and
nothing in this repository or GitHub's secret store records whether this project's token has one —
that detail lives only in the Cloudflare dashboard. Confirm it there before the first scheduled
review; if an expiry is set, move the milestone below to precede it. Absent a known expiry, or
until it is confirmed, rotation should not wait for a compromise: a recurring annual review is tracked
as a GitHub milestone due one year from the token's creation date (2026-07-21), with a tracking
issue attached so the review is not silently missed: [Cloudflare API token rotation review
2027](https://github.com/shaug/seattle-election-guide/milestone/6), tracked by issue
[#365](https://github.com/shaug/seattle-election-guide/issues/365). Closing that issue and rolling
the milestone forward one year is part of completing the rotation.
