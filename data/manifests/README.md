# Evidence manifests

This tracked directory receives metadata-only evidence manifests. Raw or restricted artifacts
belong in the ignored `data/snapshots/` content store or another controlled local store.
Permitted official-authority bytes are the exception and are tracked, but in their own content
store at `data/evidence/official/` — never here (`docs/COLLECTION.md`).

Do not place third-party page contents, screenshots, PDFs, credentials, browser profiles, or
personal data here. See [`docs/EVIDENCE_CAPTURE.md`](../../docs/EVIDENCE_CAPTURE.md).
