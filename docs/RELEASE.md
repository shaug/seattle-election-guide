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

## Reproducibility

Repeating a build with identical inputs produces the same release. That is checked, on every pull
request and on demand locally, by building twice with one `--generated-at` and comparing the two
archives:

```bash
make check-release-reproducible
```

Every artifact in the bundle is held to its exact bytes, the two rendered screenshots included.
What issue #367 changed is not that contract but what a failure can say. `cmp` on the two archives
printed a single offset into compressed data, which named nothing: the first byte to differ belongs
to whichever entry's header the deflate stream reached first, so a moved screenshot surfaced as an
offset inside `release-manifest.json`. `release compare` walks the archives entry by entry and names
the artifact.

That gate used to fail roughly one run in seven on same-input builds. The cause was in the capture,
not the comparison: `rendering/browser.py` waited a fixed interval and then photographed whichever
frame existed. It now waits on a readiness signal — fonts loaded, every animation finished, two
frames produced — asserts the page settled rather than assuming it, and runs Chrome with the
compositor and rasterization controls that keep a half-drawn or partially rastered frame from being
captured. Measured on the CI runner, 30 same-input builds diverged 4 times before the change, 2
times with the readiness signal but without those flags, and 0 times with both: each half is
necessary and neither alone is sufficient. No tolerance is applied to a screenshot, because none is
needed, and one would have hidden the defect instead of fixing it.

Inspect the desktop and mobile screenshots, all machine validation reports, and
`RELEASE_NOTES.md`. Test the archive before publication:

```bash
unzip -t dist/primary-release/seattle-election-guide-2026-primary.2.zip
```

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
