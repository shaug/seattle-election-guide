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

"The same release" does not mean the same bytes everywhere, and until issue #367 rewrote this gate
it assumed it did. Every artifact the pipeline *computes* — the canonical data, the guide HTML, the
manifests, the release status, the rendering validation report — is a pure function of its inputs
and is compared byte for byte, exactly as before. The two screenshots are not computed but
*rasterized*, and the one way they are observed to differ is now understood exactly.

The guide's vertical rhythm is rem-derived, so most boxes have fractional CSS-pixel heights and sit
at fractional offsets — `.site-band` measures 43.2188px tall, and everything beneath inherits that
fraction. Painting an edge that falls between two device pixels is not guaranteed to snap the same
way on every headless-Chrome renderer-process launch. That is the finding of issue #341, which #343
fixed for one element by pinning it to a whole pixel; pinning does not generalize, because the
fraction accumulates from the top of the page, so a child with a whole height still starts at a
fractional origin. Verified against the real runner: pinning `.segmented-control` and
`.filter-select` to whole pixels left the divergence bit-for-bit unchanged.

So a screenshot's contract is the shape of the difference, not a pixel budget: **two captures are
the same capture when every pixel that differs is explained by an edge snapping one device pixel
vertically.** On the real divergence, 3306 of 3326 differing pixels are explained that way; the 20
that are not are the corner antialiasing of two rounded rectangles that moved with it. A capture
that reflowed a line, moved a card, lost a tile, failed to decode, or drew a control in a different
state changes which pixels exist rather than which row an edge rounds to, so it fails here exactly
as a byte comparison would have. The comparison's own known gap — vertical movement of more than one
pixel through rows holding the same colours — is stated in `release/reproducibility.py`, along with
what else covers it. Both ceilings are ratchets: a pull request may tighten them, never loosen them
(AGENTS.md, Working rules). `release compare` names the artifact that moved and how, rather than
reporting an offset into the ZIP.

This check requires a clean checkout, because `release build` does; it is therefore not part of
`make check` (CONTRIBUTING.md, Local checks).

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
