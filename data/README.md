# Data layout

The data pipeline will use these logical areas:

- `raw/`, `snapshots/`, and `imports/`: local or controlled evidence; ignored by Git.
- `evidence/official/`: content-addressed bytes of official-authority captures; tracked, because
  election results published by a counting authority are public records and their durability is
  the point (`docs/COLLECTION.md`).
- `extracted/`: evidence-linked claims suitable for review.
- `review/queue/`: immutable unresolved ambiguity records.
- `review/decisions/`: append-only approvals and rejections; one terminal decision per item.
- `overrides/`: append-only manual corrections with old and new JSON values.
- `normalized/`: canonical, diffable records.
- `manifests/`: snapshot, provenance, validation, and build hashes.
- `published/`: release inputs; bundled outputs are attached to GitHub Releases.
- `releases/`: reviewed source-decision ledgers and their reproducible permitted snapshots.
- `analytics/`: one file per UTC day of zone-traffic rollups; tracked, because Cloudflare keeps
  only about 30 days of totals and 8 days of path detail, and an ignored path is how the
  2026-08-04 capture bytes were lost (`docs/MONITORING.md`, issue #381).

Directories are created by the relevant pipeline commands rather than committed empty. Public
records must not embed third-party material that the project lacks permission to redistribute.
`manifests/README.md` is retained to document the tracked-manifest boundary. Evidence capture
writes metadata beneath `manifests/evidence/` and bytes beneath `snapshots/sha256/` for restricted
artifacts or `evidence/official/sha256/` for permitted official-authority ones; the manifest's
`storage_scope` records which.

The current canonical election inventory is
`normalized/wa-2026-primary-inventory.json`. Its source manifest records the official URLs and
content hashes, while raw King County CSV files remain local because they contain contact and
mailing fields that are not needed by the guide.

`extracted/official/` contains deterministic, privacy-stripped build inputs. Their manifests
retain the hashes of both the official raw artifacts and the safe extracts, allowing CI and a
fresh checkout to reproduce the canonical inventory without publishing unused personal fields.

Normalization records use content-derived IDs and canonical JSON. Record filenames use the
content ID except queue items and terminal decisions, whose filenames use the claim and review
item IDs respectively to enforce one atomic slot. Existing history is never replaced. See the
[normalization guide](../docs/NORMALIZATION.md) for the matching, review, and override commands.

The primary release ledger is `releases/wa-2026-primary/source-decisions.yaml`. Compilation turns
each source entry into a content-addressed JSON snapshot under that release's `snapshots/`
directory and a public capture manifest under `manifests/`, then writes
`normalized/canonical-dataset.json`. These snapshots contain reviewed structured transcriptions
and optional short source excerpts only; they do not claim to be copies of the source pages.
Each ledger `captured_at` value is the actual time the reviewer checked that official publication,
and manual-extract manifests intentionally omit an HTTP status because compilation does not make
an HTTP request. Ignored full-page captures are never copied into the tracked tree.
`election-guide release verify` recompiles all three generated areas in temporary storage and
requires exact path and byte equality.

`analytics/<YYYY-MM-DD>.json` holds aggregate zone traffic for one complete UTC day: total
requests, page views, and uniques, plus rollups by country and edge status code. `visits`,
`by_path`, and `by_device_type` come from a dataset Cloudflare keeps for only eight days, so they
are `null` on any day archived later than that — 18 of the first 25 committed days — and `sources`
records which datasets answered (`docs/MONITORING.md`, "The archive"). It carries
no per-visitor data — the `Source IP`, `Source user agent`, and `Source browser` dimensions are
never requested and the archive model rejects them, because this repository is public and a
committed identifier would be unretractable from every fork. `election-guide analytics export`
writes it; see the [monitoring guide](../docs/MONITORING.md) for the retention deadline that
makes it necessary.

`election-guide export build` writes the complete release bundle to `build/` by default. The
bundle contains canonical consensus and view-model JSON, race and source CSVs, the full
source-by-race matrix, unresolved review records, validation output, and provenance/build
manifests. Generated release artifacts are not hand-edited; see the
[publication export guide](../docs/PUBLICATION_EXPORTS.md) for their contract and hash boundaries.
The [release guide](../docs/RELEASE.md) documents final audit, packaging, and publication.
