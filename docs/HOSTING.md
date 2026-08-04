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

The workflow uses the GitHub `production` environment, which carries a required-reviewer rule and a
`main`-only deployment branch policy. Both are configured under **Settings / Environments /
production**: add the maintainer as a required reviewer, and add a deployment branch rule naming
`main`. Rebuilding the environment without them restores automatic publication.
[Deployment gate](#deployment-gate) describes what each one does and when to reach for the kill
switch instead.

Leave publishing disabled until the project and both secrets exist. Then create the repository
Actions variable `CLOUDFLARE_PAGES_ENABLED` with the exact value `true`. Run the **CI** workflow
manually on `main` for the first upload. That run, and every push to `main` after it, builds,
validates, and stages automatically, then queues a production deployment for approval. A pull
request deploys only when it is opted in, and only from a branch in this repository — see
[Pull request previews](#pull-request-previews).

## Custom domains

The canonical public hostname is `seattleelections.guide`. Add it to the Pages project under
**Custom domains** and manage its apex DNS through Cloudflare. The staged Pages worker permanently
redirects these legacy hostnames to the canonical hostname while preserving the request path and
query string:

- `seattle-elections.dobravoda.dev`;
- `seattle-elections.guide`.

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

## Archive manifest and routes

`config/hosting/site.yaml` is the versioned source of truth for the site. Its ordered election list
declares the current election first and binds every public election ID to a logical bundle ID,
release version, and source-panel identity/hash. Optional Git commit, release-manifest hash, and
complete bundle hash fields can pin older immutable inputs more tightly. The staging command
resolves each logical bundle ID to a local verified release bundle; it never infers the current
election from dates, filenames, directory order, or an earlier deployment.

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

The command reads every declared election and fails when a `release_version` has no published
Release, naming each election and the tag it expects. Draft releases do not count; a draft carries a
tag name but publishes no archive. It reads release state through the GitHub CLI, so `gh` must be
installed and authenticated — CI supplies the default `GITHUB_TOKEN`, and the check is read-only.

Publishing a release is described in [RELEASE.md](RELEASE.md). Publish first: this check runs on
pull requests, so a new `release_version` must already have a published Release before the pull
request that declares it in `site.yaml` can pass CI.

## Historical bundles

Only the current election is built from source. An older election cannot be rebuilt — its pinned
artifact hashes were produced by the rendering code of its own time, and rendering changes since
then would make the bytes diverge — so its bundle is downloaded from the Release that published it.

Pass `--released-bundle-dir` to resolve every declared bundle that was not supplied with
`--bundle`:

```bash
uv run election-guide hosting stage config/hosting/site.yaml \
  --bundle wa-2026-primary-2026-primary.2=dist/primary-release/bundle \
  --released-bundle-dir dist/released-bundles \
  --output-dir dist/cloudflare-site
```

Each unresolved election's versioned ZIP is downloaded through the GitHub CLI, unpacked under that
directory, and staged like any other bundle. Supplying every bundle locally downloads nothing, so
the current single-election build is unaffected.

An election resolved this way **must** declare `bundle_sha256`, and staging rejects it otherwise. A
downloaded archive is remote input, and the release manifest travelling inside it cannot vouch for
it: whatever could replace the artifacts could replace their recorded hashes too. The pin lives in
`site.yaml`, which is under review, so it is the one hash an attacker who controls the archive does
not control. Archive entries outside the bundle root, or with parent-directory segments, are
rejected before anything is written.

## Local staging and preview

Build the audited release as described in [RELEASE.md](RELEASE.md), then stage it:

```bash
make hosting-stage
```

The Make target resolves the current manifest bundle as
`wa-2026-primary-2026-primary.2=dist/primary-release/bundle`. When another election is added, prepare
each declared bundle and pass one `--bundle BUNDLE_ID=PATH` option for each. Staging verifies all
declared identities, each release status, every release-manifest artifact hash, and the current
bundle's exact Git revision before it changes the existing output. It then atomically replaces
`dist/cloudflare-site/` with:

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
Wrangler. Normal publication should go through GitHub Actions so the deployed artifact is the one
that passed the full mainline release checks.

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

## Deployment gate

The `deploy` job depends on the complete CI `check` job. CI builds the deterministic current release
twice, compares the archives, validates the archive and rendered output, resolves all
manifest-declared bundles, stages the complete site, and uploads the staged directory as a
short-lived GitHub Actions artifact. Only then can the production job download and upload it with
Wrangler. Concurrent production uploads are serialized.

Passing CI makes a commit publishable; it does not publish it. Two independent controls stand
between a green merge and the live site.

### Approval

The `production` environment carries a required-reviewer protection rule. A merge to `main` runs
`check` and then queues `deploy` in a waiting state until a reviewer approves it from the workflow
run page. The repository's Deployments page lists the waiting deployment and links to that run, but
carries no approval control of its own. Approving starts the upload; rejecting ends the run and
leaves the live site on its previous deployment. Work can keep landing on `main` while a deployment
waits, which is the point: merging and publishing are separate decisions, and during the week before
an election the second one deserves its own moment.

What waits is one commit, not a backlog. The `deploy` job serializes on a single concurrency group,
so production deployments never accumulate: a run queued behind the waiting one is itself canceled
when a newer run queues behind it. Approving therefore publishes the commit the waiting deployment
carries — the deployments log records which — and that is not necessarily the head of `main`. To
publish a newer commit instead, reject the waiting deployment and approve the newer one. Re-running
CI on the exact commit you want is the dependable way to produce a deployment for it.

A hold is also bounded. The job publishes by downloading the `cloudflare-site` artifact that `check`
uploaded, and Actions keeps that artifact for seven days; approving afterward fails at the download
step rather than publishing. GitHub fails an unapproved deployment after thirty days, but the
artifact expires long before that, so seven days is the real limit. Past it, re-run CI on the commit
to stage a fresh artifact.

The only reviewer is the maintainer, so this is self-approval, and admins can bypass it. That is
deliberate. What it buys is the pause and the audit trail in the deployment log, not enforcement
against oneself.

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

Approval is the per-deploy pause, and the normal path: hold a specific commit, or sit on a change
overnight before putting it in front of voters. See [Approval](#approval) for which commit a waiting
deployment carries.

The variable is the durable off switch. Use it when publication should be off rather than merely
waiting: while Cloudflare credentials are rotated, while the Pages project is rebuilt, or for any
freeze approaching the seven-day artifact window. While it is unset the `deploy` job never runs, so
there is no deployment to expire or approve by mistake, and restoring publication takes a deliberate
settings change rather than a click.
