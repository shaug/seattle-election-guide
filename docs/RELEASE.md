# Primary release audit and publication

The release workflow turns the reviewed source-decision ledger into a reproducible public bundle.
It does not imply comprehensive source coverage. Gaps remain visible in the guide and in
`release-status.json`; missing coverage is never counted as opposition.

## Audited inputs

`data/releases/wa-2026-primary/source-decisions.yaml` contains reviewed structured transcriptions,
official URLs inherited from the frozen source registry, and short verification locators. Its
`captured_at` fields record when the reviewer actually checked each official publication. Optional
`evidence_excerpt` values are source text; the compiler never invents one from normalized values.
Because compilation imports a manual extract rather than issuing an HTTP request, its public
capture manifests do not claim an HTTP status. Full third-party HTML, PDF, browser, and restricted
captures remain outside Git.

Compile the ledger after an editorial change:

```bash
uv run election-guide release compile \
  data/releases/wa-2026-primary/source-decisions.yaml
```

The compiler validates source eligibility, races, candidates, publication state, timestamps,
candidate allocation, and review provenance. It writes:

- `data/normalized/canonical-dataset.json`;
- content-addressed permitted extracts under
  `data/releases/wa-2026-primary/snapshots/`; and
- immutable public capture records under `data/releases/wa-2026-primary/manifests/`.

Multi-candidate decisions create a high-severity review item and a linked approval from the named
ledger reviewer. The canonical dataset therefore preserves the ambiguity boundary without leaving
publication-blocking work unresolved.

Verify exact fresh-checkout reproducibility without changing tracked files:

```bash
uv sync --frozen
uv run election-guide release verify \
  data/releases/wa-2026-primary/source-decisions.yaml
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
than being rewritten. Likewise, publication schema 1.13 remains readable without the field, while
new schema 1.14 publication metadata requires it.

## Build and inspect

Use a stable version, the commit timestamp, and the full Git revision:

```bash
uv run election-guide release build \
  data/releases/wa-2026-primary/source-decisions.yaml \
    --release-version 2026-primary.2 \
    --generated-at "$(git show -s --format=%cI HEAD)" \
  --git-commit "$(git rev-parse HEAD)"
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
`RELEASE_NOTES.md`. Test the archive before publication:

```bash
unzip -t dist/primary-release/seattle-election-guide-2026-primary.2.zip
```

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

## GitHub Release

Create the GitHub Release only from the merged mainline revision whose hash appears in the bundle.
Use the bundled notes and attach the one versioned ZIP:

```bash
gh release create 2026-primary.2 \
  dist/primary-release/seattle-election-guide-2026-primary.2.zip \
  --title "Seattle 2026 primary endorsement guide — 2026-primary.2" \
  --notes-file dist/primary-release/bundle/RELEASE_NOTES.md \
  --target "$(git rev-parse HEAD)"
```

After upload, download the asset into a temporary directory, compare its SHA-256 with the local
archive, and confirm the release tag targets the recorded mainline commit.

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
