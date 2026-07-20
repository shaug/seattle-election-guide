# Data layout

The data pipeline will use these logical areas:

- `raw/`, `snapshots/`, and `imports/`: local or controlled evidence; ignored by Git.
- `extracted/`: evidence-linked claims suitable for review.
- `review/queue/`: immutable unresolved ambiguity records.
- `review/decisions/`: append-only approvals and rejections; one terminal decision per item.
- `overrides/`: append-only manual corrections with old and new JSON values.
- `normalized/`: canonical, diffable records.
- `manifests/`: snapshot, provenance, validation, and build hashes.
- `published/`: release inputs; bundled outputs are attached to GitHub Releases.

Directories are created by the relevant pipeline commands rather than committed empty. Public
records must not embed third-party material that the project lacks permission to redistribute.
`manifests/README.md` is retained to document the tracked-manifest boundary. Evidence capture
writes local bytes beneath `snapshots/sha256/` and metadata beneath `manifests/evidence/`.

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

`election-guide export build` writes the complete release bundle to `build/` by default. The
bundle contains canonical consensus and view-model JSON, race and source CSVs, the full
source-by-race matrix, unresolved review records, validation output, and provenance/build
manifests. Generated release artifacts are not hand-edited; see the
[publication export guide](../docs/PUBLICATION_EXPORTS.md) for their contract and hash boundaries.
