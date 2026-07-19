# Data layout

The data pipeline will use these logical areas:

- `raw/`, `snapshots/`, and `imports/`: local or controlled evidence; ignored by Git.
- `extracted/`: evidence-linked claims suitable for review.
- `review/`: approvals, rejections, and unresolved items.
- `overrides/`: append-only manual corrections.
- `normalized/`: canonical, diffable records.
- `manifests/`: snapshot, provenance, validation, and build hashes.
- `published/`: release inputs; bundled outputs are attached to GitHub Releases.

Directories are created by the relevant pipeline commands rather than committed empty. Public
records must not embed third-party material that the project lacks permission to redistribute.

The current canonical election inventory is
`normalized/wa-2026-primary-inventory.json`. Its source manifest records the official URLs and
content hashes, while raw King County CSV files remain local because they contain contact and
mailing fields that are not needed by the guide.

`extracted/official/` contains deterministic, privacy-stripped build inputs. Their manifests
retain the hashes of both the official raw artifacts and the safe extracts, allowing CI and a
fresh checkout to reproduce the canonical inventory without publishing unused personal fields.
