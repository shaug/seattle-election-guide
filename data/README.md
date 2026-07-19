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
