# General release audit and publication

The release workflow turns the reviewed source-decision ledger into a reproducible public bundle.
It does not imply comprehensive source coverage. Gaps remain visible in the guide and in
`release-status.json`; missing coverage is never counted as opposition.

## Public update log

Compare the candidate with the currently published guide before publication. Every change to
the published aggregate or a position page requires an entry in
`data/corrections/<election-id>.yaml`, which renders as **Updates** at the election's
`/updates/` address. Include the entry in the same change as the publication inputs or rendering
behavior it describes. The stored `corrections` names remain compatible with existing releases.

Newly published or previously missed endorsements count, even if the leading choice stays
the same. Record changed counts, shares, source coverage, evidence, displayed races, and results
as well as corrected or withdrawn endorsements. Explain what changed and why; link the evidence
and affected pages. A batch entry must link a complete account of its changes. A refresh that
leaves published content unchanged needs no entry. The editorial rule is in
[RESULTS.md, The updates page](RESULTS.md#the-updates-page).

The update log ships with the release that publishes the changes. Keep historical entries and
immutable release bundles intact. An update's date does not assert when a source announced its
endorsement.

## Audited inputs

`data/releases/wa-2026-general/source-decisions.yaml` contains reviewed structured transcriptions,
official URLs inherited from the frozen source registry, and short verification locators. Its
`captured_at` fields record when the reviewer actually checked each official publication. Optional
`evidence_excerpt` values are source text; the compiler never invents one from normalized values.
Because compilation imports a manual extract rather than issuing an HTTP request, its public
capture manifests do not claim an HTTP status. Full third-party HTML, PDF, browser, and restricted
captures remain outside Git.

Compile the ledger after an editorial change:

```bash
uv run election-guide release compile \
  data/releases/wa-2026-general/source-decisions.yaml \
  --inventory-path data/normalized/wa-2026-general-inventory.json \
  --registry-path config/sources/wa-2026-general.yaml \
  --output-path data/normalized/wa-2026-general-canonical-dataset.json \
  --snapshot-root data/releases/wa-2026-general/snapshots \
  --manifest-dir data/releases/wa-2026-general/manifests
```

The compiler validates source eligibility, races, candidates, publication state, timestamps,
candidate allocation, and review provenance. It writes:

- `data/normalized/wa-2026-general-canonical-dataset.json`;
- content-addressed permitted extracts under
  `data/releases/wa-2026-general/snapshots/`; and
- immutable public capture records under `data/releases/wa-2026-general/manifests/`.

Multi-candidate decisions create a high-severity review item and a linked approval from the named
ledger reviewer (or the source block's reviewer when supplied). The canonical dataset therefore
preserves the ambiguity boundary without leaving publication-blocking work unresolved.

Verify exact fresh-checkout reproducibility without changing tracked files:

```bash
uv sync --frozen
uv run election-guide release verify \
  data/releases/wa-2026-general/source-decisions.yaml \
  --inventory-path data/normalized/wa-2026-general-inventory.json \
  --registry-path config/sources/wa-2026-general.yaml \
  --dataset-path data/normalized/wa-2026-general-canonical-dataset.json \
  --snapshot-root data/releases/wa-2026-general/snapshots \
  --manifest-dir data/releases/wa-2026-general/manifests
```

Verification recompiles into temporary storage and byte-compares the dataset, every permitted
snapshot, and every capture manifest. Publication of those three areas is transactional: a failed
swap restores the complete previous generation. CI runs verification and a repeated full release
build.

## Panel and registry identity

New publication view models carry two explicit identities. `source_panel_hash` is the stable
transport-facing panel hash used by personalized links and panel-version compatibility;
`source_registry_hash` is the SHA-256 of the complete validated registry, including mutable
discovery evidence. The browser payload receives only the stable panel hash because the complete
registry has no role in decoding a link or selecting sources.

New `release-status.json` and `release-manifest.json` files use schema 1.3 and require both hashes.
Release verification binds the status and manifest to the same `source_panel_id`,
`source_panel_hash`, and complete `source_registry_hash`; this detects a discovery-input change
even when the panel contract is unchanged. A discovery refresh therefore produces a new complete
release-input identity without requiring a new panel version.

Immutable release-manifest schemas 1.1 and 1.2 and release-status schema 1.2 remain readable. They
predate `source_registry_hash`, must not declare it, and retain their historical meaning rather
than being rewritten. Likewise, the archived primary's publication schema 1.9 and later schema
1.13 remain readable without the field, while new schema 1.14 publication metadata requires it.

## Prepare and review a release

Publication is automatic after merge. `config/hosting/site.yaml` selects the current release
and records the owning issue, previous published source, and SHA-256 bindings for reviewed
ledger, dataset, and registry bytes. Preparation supplies no editorial or baseline approval.

<!-- runbook-command:prepare -->
```bash
uv run election-guide release automation prepare --issue "$issue_number"
uv run election-guide release automation resolve
```

Preparation captures remote main's full SHA once, reads the declaration at that revision, and
reads all remote tag and release names, including draft release reservations. It selects the next
numeric election-scoped version above main and every occupied version. Repeating preparation
retains a higher unpublished proposal only for the same issue and previous published revision. It refreshes the derived panel and complete-registry
identities and binds the exact ledger, canonical-dataset, and registry file bytes with SHA-256.
Formatting-only changes to those files therefore require preparation again. It changes only the
current election declaration; archived declarations and their release pins remain intact.
The previous published tag is resolved from remote state to a full commit and must be an
ancestor of the checkout. Preparation fetches that exact object if it is missing locally.
Preparation does not imply editorial or baseline approval.

Commit the reviewed declaration and its inputs together. Admission checks exact Git objects:

```bash
uv run election-guide release automation validate-request --base-sha "$base_sha"
```

Use a clean tracked checkout and the full comparison-base SHA. Admission rejects stale input
bindings and requires a fresh request with a version increment for changes under `src/`, `data/`,
`config/`, `scripts/`, or `.github/workflows/`, or to `Makefile`, `cliff.toml`, `pyproject.toml`,
`uv.lock`, `package.json`, `package-lock.json`, `wrangler.jsonc`, or `wrangler.toml`. This is a
conservative release policy: even a change in one of those paths that appears unrelated to the
rendered guide needs a declaration. A documentation/test-only change with an unchanged declaration
does not request a release. An absent request supports historical reading and never authorizes
automatic publication.

## Build and inspect before merge

Run `make check`, then commit the reviewed changes. From that clean candidate, run:

<!-- runbook-command:verify-general -->
```bash
make release-verify
make check-release-reproducible
uv run election-guide release automation resolve > dist/resolved.json
unzip -t "dist/reproducibility-a/$(jq -r .archive_name dist/resolved.json)"
test -f dist/reproducibility-a/bundle/RELEASE_NOTES.md
test -f dist/reproducibility-a/bundle/validation/rendering/rendering_validation_report.json
test -f dist/reproducibility-a/bundle/validation/rendering/screenshots/desktop.png
test -f dist/reproducibility-a/bundle/validation/rendering/screenshots/mobile.png
```

Inspect both screenshots, release notes, and validation reports before merging. PR CI retains
these as `candidate-review-<run>-<attempt>` for seven days. There is no mandatory screenshot
attestation after merge. The reproducibility gate compares two complete builds using the
commit-derived timestamp. Only the existing desktop/mobile rasterized screenshots are excluded
from deterministic comparison; both remain inside the whole-bundle digest and canonical ZIP.
The guarantee applies to the Linux deployment environment.

<!-- runbook-command:stage-candidate -->
```bash
source_sha="$(git rev-parse HEAD)"
make hosting-stage
uv run election-guide hosting verify \
  config/hosting/site.yaml \
  dist/cloudflare-site \
  --expected-git-commit "$source_sha"
```

## Automatic delivery and evidence

The five independent CI lanes feed the stable `check` status. A reviewed release request on
main then runs `publish`, `publication-evidence`, `deploy`, and `finalize`. The tag, archive,
staged current bundle, uploaded commit, and expected production commit all identify the same
full merged `source_sha`. Documentation/test-only main commits run CI without another release.

All non-PR mainline runs use `verified-release-mainline`, `queue: max`, and
`cancel-in-progress: false`. PR runs stay parallel. The queue supports 100 pending runs;
queue exhaustion is a delivery failure to investigate, never a silently discarded request.
Artifact names include producing run and attempt; consumers use captured IDs and independently
verify wrapper digests, workflow/repository identity, and attempt time boundaries. A wrapper
ZIP digest is distinct from the release asset digest.

The publisher creates or resumes only an owned matching draft, verifies its canonical ZIP,
then publishes it. Existing archives and their screenshot bytes remain immutable. Durable
publication evidence on the owning issue must complete before upload. The final selection check
rejects stale candidates and a disabled upload switch yields `deployment_paused`; a newer
selected declaration yields `superseded`. Neither state is a successful deployment.

The production environment permits only main, with no extra Publish approval. Cloudflare
credentials exist only on the one pinned upload step. Its owned GitHub deployment retains the
unique Pages upload URL immediately, plus stdout/stderr and upload time. Uncertain upload
outcomes require operator verification before another upload. Finalization waits at most
120 seconds for two consecutive complete strict probes at least five seconds apart and retains
all failed observations. GitHub deployment success follows durable verified evidence only.

Publication receipts include the release asset digest/ID/size, source/input hashes, canonical
bundle and manifest hashes, CI run and artifact IDs/digests. Upload/final receipts add deployment
ID, unique URL, upload time, and complete production-wait.json evidence. Local receipt writes,
probe failures, or durable issue-write failures fail delivery even when `check` is green.
Failure artifacts are retained with `always()` for seven days; issue evidence is durable.

## Recovery

Never move a tag, overwrite an archive, replace an asset, or substitute newer main. If candidate
artifacts expire before upload, rerun the original CI run or dispatch trusted main CI with its
captured source fixed through every fresh lane and build:

<!-- runbook-command:recover-candidate -->
```bash
gh workflow run ci.yml --ref main -f source_sha="$source_sha"
```

This requires the original reviewed request at an exact merged main ancestor. It rebuilds and
verifies that source and compares an existing archive against its canonical deterministic content.
Fresh attempt artifacts get fresh receipts; their stable archive identity must agree with earlier
evidence. The current checkout or latest main is never substituted for the candidate.

After any upload, retry only verification and evidence, using the original producing run/attempt:

<!-- runbook-command:retry-evidence -->
```bash
gh workflow run verify-release.yml --ref main \
  -f issue="$issue_number" \
  -f release_version="$release_version" \
  -f source_sha="$source_sha" \
  -f run_id="$run_id" \
  -f run_attempt="$run_attempt"
```

Verification-only uses trusted workflow code from main and the declaration from the original
Git object. It loads immutable upload evidence or reconstructs it only from one matching owned
deployment/status and an authenticated retained upload report. Missing or ambiguous evidence
fails closed. It never builds, republishes, uploads, or relabels the original upload producer.
Already successful verification is idempotent and cannot reorder an older production deployment.
`make hosting-deploy` deliberately fails with these recovery instructions.

## Software history

The pinned local git-cliff generates the bundled software history from the request's explicit
previous-release SHA through the exact candidate SHA using its declared version and timestamp.
Tags cannot change that section. `CHANGELOG.md` is a generated release index retaining manual
history through `2026-general.9`; publication needs no second changelog commit.

## Historical post-tag release lineage

The historical publication sequence through `2026-general.9` created two intentional commit
identities: the published archive is bound to `release_candidate_sha`, and a production handoff
rebuilds from a later `production_candidate_sha` after a changelog commit. The following verifier preserves
that existing two-revision contract and remains available when inspecting those archives. New
request-driven publication uses one merged source revision for the tag, archive, staged bundle,
and deployment; it requires no post-tag changelog commit. For a historical two-revision handoff,
verify the narrow boundary before handing the production bundle to `hosting stage`:

<!-- runbook-command:verify-lineage -->
```bash
uv run election-guide release verify-lineage \
  dist/downloaded/seattle-election-guide-2026-general.9.zip \
  dist/reproducibility-a/bundle \
  "$release_candidate_sha" \
  "$production_candidate_sha" \
  > dist/release-lineage-report.json
```

Both identities must be full Git commit IDs in the current repository, and the release candidate
must be an ancestor of the distinct production candidate. The command independently verifies each
bundle, including its exact declared file set and every manifest hash, before comparing anything.
Within each bundle, timestamp identities must agree as timezone-aware instants. The builder emits
both `Z` and `+00:00` for UTC; these spellings are equivalent. Different instants, missing timezones,
and malformed timestamps are rejected, including in consensus rows and the release notes.
It then requires the same election, release, source panel and registry, canonical dataset,
source-decision snapshots, scoring input, and deterministic release content.

Only these schema-owned commit-bound values are normalized: the release-status commit and build
time; consensus computation times; publication, validation, provenance, and build-manifest commit
or time fields; the consensus and artifact hashes directly derived from those fields; the two
corresponding release-note lines; the rendered guide's commit link, commit label, and site-updated
date; and the release-manifest time and directly derived artifact hashes. The report lists every
normalized path. A new field is not normalized implicitly, so adding commit-bound provenance
requires an explicit allowlist change and review. The two declared screenshots are verified as
present but remain outside cross-build byte comparison under the existing schema 1.2/1.3 contract.

The canonical JSON report exits with status 1 and records `result: fail` for invalid identity,
ancestry, bundle integrity, or content drift. Preserve it for #450 and the #440 closeout evidence.
This command verifies the general release bundle only; complete two-election route and deployment-
manifest composition remains the separate `hosting verify` gate.
