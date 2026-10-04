# General release audit and publication

The release workflow turns the reviewed source-decision ledger into a reproducible public bundle.
It does not imply comprehensive source coverage. Gaps remain visible in the guide and in
`release-status.json`; missing coverage is never counted as opposition.

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

## Build and inspect

Use a stable version, the commit timestamp, and the full Git revision:

```bash
uv run election-guide release build \
  data/releases/wa-2026-general/source-decisions.yaml \
  --release-version 2026-general.4 \
  --generated-at "$(git show -s --format=%cI HEAD)" \
  --git-commit "$(git rev-parse HEAD)" \
  --output-dir dist/general-release \
  --inventory-path data/normalized/wa-2026-general-inventory.json \
  --registry-path config/sources/wa-2026-general.yaml \
  --dataset-path data/normalized/wa-2026-general-canonical-dataset.json \
  --snapshot-root data/releases/wa-2026-general/snapshots \
  --manifest-dir data/releases/wa-2026-general/manifests
```

The command requires a clean Git checkout and a full revision equal to `HEAD`, then recomputes
consensus, canonical exports, and the responsive HTML guide. It fails unless publication and
rendered-artifact validation both pass, all relevant high-severity reviews are resolved, every
included evidence snapshot is permitted, and every displayed decision has valid provenance.

The output directory contains the release ZIP and an unpacked `bundle/` for inspection. The ZIP
contains:

- the responsive HTML guide;
- canonical dataset, consensus, and publication-view-model JSON;
- race, decision, source, review, and source-matrix CSV files;
- publication, rendering, provenance, build, and release manifests;
- desktop and mobile screenshots referenced by the rendering validation report; and
- release notes that state source-access failures, incomplete coverage, review counts, data time,
  and code revision.

The ZIP uses stable entry ordering, timestamps, permissions, and compression settings.

Inspect the desktop and mobile screenshots, all machine validation reports, and
`RELEASE_NOTES.md`. The supported release-candidate path builds the general twice before
inspection. Run it from a clean checkout of the full merged `release_candidate_sha`; these exact
commands are protected against documentation drift:

<!-- runbook-command:verify-general -->
```bash
make release-verify
make check-release-reproducible
unzip -t dist/reproducibility-a/seattle-election-guide-2026-general.4.zip
test -f dist/reproducibility-a/bundle/RELEASE_NOTES.md
test -f dist/reproducibility-a/bundle/validation/rendering/rendering_validation_report.json
test -f dist/reproducibility-a/bundle/validation/rendering/screenshots/desktop.png
test -f dist/reproducibility-a/bundle/validation/rendering/screenshots/mobile.png
```

Read the notes and rendering report and inspect both screenshots before publication. Record the
full `release_candidate_sha`, the ZIP SHA-256 and size, and the source-registry, canonical-dataset,
and source-decision-ledger SHA-256 values. Compare the last three with the final refresh evidence
recorded by #453; a mismatch stops publication rather than creating a new interpretation here.

## Reproducibility

Repeating a build with identical inputs produces the same deterministic release artifacts on the
Linux environment used for deployment. That is checked on every pull request and on demand locally
by building twice with one `--generated-at` and comparing the manifest-declared contract:

```bash
make check-release-reproducible
```

Schema 1.2 hashes every included artifact except the two rasterized QA images,
`validation/rendering/screenshots/desktop.png` and
`validation/rendering/screenshots/mobile.png`. Those paths are declared explicitly in
`unhashed_artifacts`; verification rejects any missing, overlapping, or additional unhashed path.
`release compare` verifies both bundles and requires every hashed artifact, including
`release-status.json`, to have identical bytes. It also requires the two release manifests to be
byte-identical. Schema 1.1 remains supported and continues to enforce its historical contract, in
which screenshots are hashed.

The screenshots remain inside the published GitHub Release ZIP as exact review evidence. Their
bytes, archive metadata, and compression can vary without failing the reproducibility gate. The
published whole-bundle SHA-256 still protects the exact bundle tree selected for release, including
both screenshots; excluding them from schema 1.2's cross-build comparison does not remove that
published-bundle integrity check.

The gate is defined once, in the `Makefile`, and CI invokes that target rather than restating it, so
the command a contributor runs locally cannot drift from the one CI runs.

The guarantee is intentionally Linux-only. The project does not spend CI compute establishing
macOS equivalence for a release pipeline that is deployed only from Linux.

## Post-tag release lineage

Publishing `2026-general.4` and then committing the generated changelog creates two intentional
commit identities. The published archive remains bound to `release_candidate_sha`; the general
bundle staged for production is rebuilt from the later `production_candidate_sha`. Verify that
narrow boundary before handing the production bundle to `hosting stage`:

<!-- runbook-command:verify-lineage -->
```bash
uv run election-guide release verify-lineage \
  dist/downloaded/seattle-election-guide-2026-general.4.zip \
  dist/reproducibility-a/bundle \
  "$release_candidate_sha" \
  "$production_candidate_sha" \
  > dist/release-lineage-report.json
```

Both identities must be full Git commit IDs in the current repository, and the release candidate
must be an ancestor of the distinct production candidate. The command independently verifies each
bundle, including its exact declared file set and every manifest hash, before comparing anything.
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

## GitHub Release

Create the GitHub Release only from the merged mainline revision whose hash appears in the bundle.
Before changing GitHub, inspect the tag, release record, and full asset list separately:

<!-- runbook-command:release-preflight -->
```bash
git ls-remote --tags origin refs/tags/2026-general.4 refs/tags/2026-general.4^{}
gh release view 2026-general.4 \
  --json url,tagName,targetCommitish,isDraft,isPrerelease,name,body,assets
```

Interpret that preflight with this restart matrix. Do not delete, replace, move, or overwrite
remote state to force a match.

| Observed state | Permitted action |
| --- | --- |
| No tag and no release | Create the release and its tag with the command below. |
| Exact tag exists and no release exists | Create the release on that exact tag. |
| Exact published metadata exists with no assets | Upload the one canonical ZIP. |
| Exact tag, metadata, and one canonical ZIP already exist | Download and verify; make no mutation. |
| Wrong tag target, draft/prerelease, metadata mismatch, partial/duplicate/wrong assets, or noncanonical bytes | Stop and request explicit recovery direction. |

For a permitted create, use the bundled notes and attach the one versioned ZIP:

<!-- runbook-command:release-create -->
```bash
gh release create 2026-general.4 \
  dist/reproducibility-a/seattle-election-guide-2026-general.4.zip \
  --title "Seattle 2026 general election endorsement guide — 2026-general.4" \
  --notes-file dist/reproducibility-a/bundle/RELEASE_NOTES.md \
  --target "$release_candidate_sha"
```

When the preflight instead proves that the exact published metadata already exists and the asset
list is empty, upload the canonical ZIP without `--clobber`:

<!-- runbook-command:release-upload -->
```bash
gh release upload 2026-general.4 \
  dist/reproducibility-a/seattle-election-guide-2026-general.4.zip
```

The omitted `--clobber` is deliberate. If another operator creates an asset after the preflight,
the command must fail rather than replace it; return to the restart matrix and inspect the new
state.

After upload, use `gh release view` again to prove the release is published, non-draft,
non-prerelease, and has exactly one asset named
`seattle-election-guide-2026-general.4.zip`. Record the release URL and the asset ID, name, and size.
Download that exact asset through the Release API, rather than accepting a similarly named local
file, then verify the bytes and tag with the protected command below:

<!-- runbook-command:verify-published-asset -->
```bash
mkdir -p dist/downloaded
test ! -e dist/downloaded/seattle-election-guide-2026-general.4.zip
gh release download 2026-general.4 \
  --pattern seattle-election-guide-2026-general.4.zip \
  --dir dist/downloaded
local_release_digest="$(shasum -a 256 \
  dist/reproducibility-a/seattle-election-guide-2026-general.4.zip | awk '{print $1}')"
downloaded_release_digest="$(shasum -a 256 \
  dist/downloaded/seattle-election-guide-2026-general.4.zip | awk '{print $1}')"
test "$local_release_digest" = "$downloaded_release_digest"
unzip -t dist/downloaded/seattle-election-guide-2026-general.4.zip
git fetch origin tag 2026-general.4
test "$(git rev-parse '2026-general.4^{commit}')" = "$release_candidate_sha"
```

The digest comparison proves the downloaded archive is byte-for-byte the inspected local archive;
the release asset size recorded above must also equal the local file size. Retain the downloaded ZIP
for the lineage command above. The recorded SHA-256 is the release asset digest handed to #450 and
#440.

## Changelog

`CHANGELOG.md` records tagged releases, so it changes once per release rather than once per pull
request. The new tag has to exist first — that is what moves its commits out of untagged history and
into a section. Once the release above is published, regenerate and commit the result:

```bash
npm run changelog
```

`make check` regenerates the file and compares bytes, so a stale copy fails the build. Never edit it
by hand. It covers the software that renders and ships bundles; what the guide *said* for one
election is in that bundle's own `RELEASE_NOTES.md`.

The changelog belongs in one focused, non-closing PR created after the tag exists. After that PR is
merged, fetch `main` and record its full head as `production_candidate_sha`; do not move or amend
the published tag. Require `release_candidate_sha` to be an ancestor of the production candidate,
then rebuild at the latter SHA and run the lineage check. If `main` advances before the production
handoff is complete, select and verify the new exact candidate again.

## Website publication

The validated HTML is also resolved through the repository-owned site manifest and staged
under the election-scoped `/e/<election-id>/` path for deployment from `main`. See
[HOSTING.md](HOSTING.md) for the archive manifest, route contract, Wrangler configuration, safety
gates, one-time credentials, local preview, and automatic deployment workflow.

For a schema 1.3 release, declare its `source_registry_hash` beside `source_panel_hash` in
`config/hosting/site.yaml`. `hosting stage` requires both declarations to match the release status,
requires the release status and manifest to agree, and copies the complete registry hash into the
deployment manifest. `hosting verify` then compares the site declaration, deployment manifest, and
staged release status before recomputing asset hashes. Historical declarations and deployments
without `source_registry_hash` remain valid only for the legacy release schemas that omitted it;
do not add a reconstructed value to their immutable artifacts.

After lineage passes at `production_candidate_sha`, stage and independently verify the complete
two-election site:

<!-- runbook-command:stage-candidate -->
```bash
make hosting-stage
uv run election-guide hosting verify \
  config/hosting/site.yaml \
  dist/cloudflare-site \
  --expected-git-commit "$production_candidate_sha"
```

The first command builds the general from the current checkout and resolves the hash-pinned primary
from its published release. The second check is intentionally separate: release lineage proves the
general's allowed post-tag provenance differences, while hosting verification proves the whole
current-plus-historical site and deployment manifest.

## Operational evidence handoff

The three publication tickets use one evidence vocabulary. Record all of these exact identities;
do not replace a full SHA with a branch name or a dashboard's abbreviated display:

- `release_candidate_sha`, the merged commit bound to the published archive;
- `production_candidate_sha`, the later merged commit bound to the staged site;
- the release URL, peeled tag SHA, asset identity/size, and release asset digest;
- the lineage report and the verified two-election deployment manifest;
- the exact CI run and artifact for `production_candidate_sha`;
- the waiting production deployment ID and its full SHA; and
- the read-only `production-probe.json` output after an authorized deployment.

A production artifact expires after seven days. If it expires or is missing, rerun CI for that exact
`production_candidate_sha`, repeat lineage and staged-site verification against the new run, and
record the replacement run/artifact. Never substitute the newer `main` head. Production
approval remains a separate exact-candidate action described in [HOSTING.md](HOSTING.md); none of
the release, changelog, lineage, or staging commands approves it.
