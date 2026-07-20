# Evidence capture and manual entry

Issue #4 establishes the evidence boundary between live or user-provided source material and
later extraction. It does not fetch websites automatically; automated adapters belong to issue
#10. Instead, it ingests an artifact that a reviewer obtained without bypassing access controls,
stores the bytes locally by SHA-256, and writes a public, immutable manifest.

## Storage boundary

The default artifact root is `data/snapshots/`, which is ignored by Git. Captured bytes are
stored at:

```text
data/snapshots/sha256/<first two hash characters>/<full sha256>
```

The corresponding JSON manifest is written to `data/manifests/evidence/`. It records the source,
requested and canonical URLs, redirects, retrieval time, HTTP status, media type, title,
publication/update dates when known, capture method, content hash, byte length, browser
requirement, storage scope, and redistribution decision. It contains neither raw content nor an
absolute local path.

Restricted and paywalled artifacts use `redistribution: restricted`. Their manifests remain
auditable in Git, while their bytes remain in the ignored local store or another controlled store.
The command rejects a restricted storage root that is inside the repository but not Git-ignored,
as well as an uncommitted restricted input left at an unignored repository path. Keep temporary
inputs under the ignored `tmp/` directory or outside the checkout.

## Capture an artifact

The caller supplies metadata from the retrieval because this command does not perform network
access:

```bash
uv run election-guide evidence capture tmp/local-page.html \
  --source-id the-stranger \
  --requested-url https://www.thestranger.com/endorsements/the-strangers-2026-primary-election-endorsements/ \
  --canonical-url https://www.thestranger.com/endorsements/the-strangers-2026-primary-election-endorsements/ \
  --retrieved-at 2026-07-19T12:00:00Z \
  --http-status 200 \
  --media-type text/html \
  --title "2026 Primary Endorsements" \
  --capture-method static_html \
  --redistribution restricted \
  --redistribution-note "Full third-party page retained locally for review only."
```

Capture methods are `static_html`, `pdf`, `image`, `browser`, and `manual_upload`. Direct capture
methods require a successful HTTP status. Browser captures must explicitly record
`--browser-required`. A changed canonical URL requires one or more `--redirect-url` options that
begin with the requested URL and end with the canonical URL.

Re-running an identical capture is idempotent. The capture ID binds the full public provenance
record and content identity; changing metadata or taking another capture creates a distinct
immutable history record, even when the content bytes are unchanged.

## Record an unavailable source

When evidence cannot be obtained without bypassing an access control, create a metadata-only
record:

```bash
uv run election-guide evidence unavailable \
  --source-id seattle-times-editorial-board \
  --requested-url https://www.seattletimes.com/opinion/editorials/ \
  --canonical-url https://www.seattletimes.com/opinion/editorials/ \
  --retrieved-at 2026-07-19T12:00:00Z \
  --http-status 403 \
  --media-type text/html \
  --unavailable-reason "The official page denied unattended access." \
  --redistribution-note "No page content was retained or redistributed."
```

An unavailable manifest has no content hash, byte length, or storage reference. Verification
validates the record without pretending an artifact exists.
`--canonical-url` is optional for this command because access-restricted discovery may not reach a
canonical publication URL.

## Verify integrity

```bash
uv run election-guide evidence verify data/manifests/evidence/<capture-id>.json
```

Verification resolves the content address within the configured local root and recomputes both
the SHA-256 and byte length. Missing or modified evidence fails loudly.

## Manual-entry adapter

Manual drafts are strict YAML. They cannot be silently mixed with parser output because every
record carries `entry_method: manual`, a reviewer, evidence type, evidence locator, transcription,
and explicit review status. Completed reviews also require a second reviewer field, timestamp,
and note. All public prose fields are bounded, and the tracked transcription is a short
verification excerpt limited to 4,000 characters; complete copyrighted or paywalled text remains
only in the restricted capture.

```yaml
schema_version: "1.0"
entry_method: manual
source_id: seattle-times-editorial-board
capture_id: capture-seattle-times-editorial-board-20260719T120000Z-0123456789ab
evidence_type: screenshot
evidence_locator: Screenshot 1, recommendation heading and first paragraph.
transcription: Candidate Example — King County Assessor
reviewer: reviewer-handle
entered_at: 2026-07-19T12:05:00Z
review_status: verified
reviewed_by: verifier-handle
reviewed_at: 2026-07-19T12:10:00Z
review_note: Compared the transcription character-for-character with the screenshot.
```

Validate or import the record with:

```bash
uv run election-guide evidence manual validate manual-entry.yaml
uv run election-guide evidence manual import manual-entry.yaml
```

Both commands verify that the source is preregistered, the referenced capture exists, the source
IDs agree, and the underlying artifact still matches its hash. Import writes canonical,
write-once JSON under `data/review/manual/`. A metadata-only unavailable record cannot support a
manual transcription; capture the reviewer-visible screenshot, image, PDF, or permitted extract
first.
