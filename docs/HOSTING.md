# Cloudflare Pages hosting

The public guide is a Direct Upload Cloudflare Pages project named `seattle-elections`. GitHub
Actions builds and validates the complete release, stages only the public guide assets, and then
uses the repository-pinned Wrangler version to upload that exact artifact. Cloudflare does not run
the Python/PDF build itself.

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

The workflow uses the GitHub `production` environment. GitHub creates that environment on the
first enabled deployment; environment protection rules may be added later if publication should
require approval.

Leave publishing disabled until the project and both secrets exist. Then create the repository
Actions variable `CLOUDFLARE_PAGES_ENABLED` with the exact value `true`. Run the **CI** workflow
manually on `main` for the first upload. After that, every push to `main` builds, validates, stages,
and publishes automatically. Pull requests never receive the Cloudflare secrets and never deploy.

## Custom domain

In the Pages project, add `seattle-elections.dobravoda.dev` under **Custom domains** before changing
DNS. Because Namecheap remains the authoritative DNS provider, add this record there after Pages
accepts the hostname:

| Type | Host | Value |
| --- | --- | --- |
| CNAME | `seattle-elections` | `seattle-elections.pages.dev` |

Do not create only the CNAME: Cloudflare requires the hostname to be associated with the Pages
project first. Certificate issuance and DNS propagation may take time.

## Local staging and preview

Build the audited release as described in [RELEASE.md](RELEASE.md), then stage it:

```bash
make hosting-stage
```

Staging verifies the release status, every release-manifest hash, and the exact Git revision. It
atomically replaces `dist/cloudflare-site/` with:

- `index.html`, copied byte-for-byte from the validated responsive guide;
- the concise PDF and, when present, the detailed PDF;
- `release-status.json` and a deployment manifest for machine-readable verification; and
- `_headers` with browser-security, revalidation, and preview-indexing policy.

Preview the staged directory with Wrangler:

```bash
make hosting-serve
```

For an exceptional local production upload, run `make hosting-deploy` after authenticating
Wrangler. Normal publication should go through GitHub Actions so the deployed artifact is the one
that passed the full mainline release checks.

## Deployment gate

The `deploy` job depends on the complete CI `check` job. CI builds the deterministic release twice,
compares the archives, validates the archive and rendered output, stages the first validated build,
and uploads the staged directory as a short-lived GitHub Actions artifact. Only then can the
production job download and upload it with Wrangler. Concurrent production uploads are serialized.

To stop automatic publication without changing code, set `CLOUDFLARE_PAGES_ENABLED` to any value
other than `true` or delete the variable.
