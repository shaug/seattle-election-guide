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

## Build and inspect

Use a stable version, build timestamp, and Git revision:

```bash
uv run election-guide release build \
  data/releases/wa-2026-primary/source-decisions.yaml \
  --release-version 2026-primary.1 \
  --generated-at 2026-07-20T02:00:00Z \
  --git-commit "$(git rev-parse HEAD)"
```

The command requires a clean Git checkout and a full revision equal to `HEAD`, then recomputes
consensus, canonical exports, responsive HTML, the two-page PDF, and the
detailed PDF fallback when necessary. It fails unless publication and rendered-artifact validation
both pass, all relevant high-severity reviews are resolved, every included evidence snapshot is
permitted, and every displayed decision has valid provenance.

The output directory contains the release ZIP and an unpacked `bundle/` for inspection. The ZIP
contains:

- concise and detailed PDF editions plus responsive HTML;
- canonical dataset, consensus, and publication-view-model JSON;
- race, decision, source, review, and source-matrix CSV files;
- publication, rendering, provenance, build, and release manifests;
- concise and detailed page images plus desktop and mobile screenshots referenced by the rendering
  validation report; and
- release notes that state source-access failures, incomplete coverage, review counts, data time,
  and code revision.

The ZIP uses stable entry ordering, timestamps, permissions, and compression settings. Repeating a
build with identical inputs produces identical archive bytes.

Inspect both concise PDF pages, every detailed PDF page, desktop and mobile screenshots, all
machine validation reports, and `RELEASE_NOTES.md`. Test the archive before publication:

```bash
unzip -t dist/primary-release/seattle-election-guide-2026-primary.1.zip
```

## GitHub Release

Create the GitHub Release only from the merged mainline revision whose hash appears in the bundle.
Use the bundled notes and attach the one versioned ZIP:

```bash
gh release create 2026-primary.1 \
  dist/primary-release/seattle-election-guide-2026-primary.1.zip \
  --title "Seattle 2026 primary endorsement guide — 2026-primary.1" \
  --notes-file dist/primary-release/bundle/RELEASE_NOTES.md \
  --target "$(git rev-parse HEAD)"
```

After upload, download the asset into a temporary directory, compare its SHA-256 with the local
archive, and confirm the release tag targets the recorded mainline commit.
