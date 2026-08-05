# Runbook: election-night results capture

Capture the counting authority's first published tabulation as evidence, the evening of election
day. Unofficial returns are overwritten as later ballot drops land; this snapshot cannot be
reconstructed afterward. Nothing captured here is ever rendered (`docs/RESULTS.md`) — this is
archival evidence, and for a first cycle it doubles as the format survey the ingestion adapter
design needs.

## Trigger

The `results_capture_election_night` calendar milestone: election day, offset 0. King County
posts its first count around 8:15 p.m. Pacific; execute the same evening. Late is better than
never, but the first-count page may already reflect a later drop by the next afternoon.

## Autonomy

Human-launched. This is the strongest level-3 (dispatched) candidate among the runbooks — the
work is mechanical once the URLs are known — but it stays human-launched until at least one
execution has recorded the authority's real page and export structure below.

## Preconditions

- The election exists in `config/calendar/elections.yaml` with this milestone declared.
- `config/elections/<election-id>.yaml` exists; its `ballot_data_sources` entry names the
  authority's election page (for `wa-2026-primary`:
  <https://kingcounty.gov/en/dept/elections/election-information/2026/august-primary>).
- Known limitation, tracked as #281: `evidence capture` validates source ids against the
  endorsement source registry, and King County Elections is an authority, not an endorsement
  source — it does not belong in that registry. Until the authority capture lane lands,
  step 3 runs in its interim manual form; the bytes are stored content-addressed, so formal
  manifests are backfilled verifiably afterward.
- A working directory under the Git-ignored `tmp/` for downloaded artifacts.

## Procedure

1. **Locate the results publication.** From the election's official page, follow the results
   link King County activates on election night. Note the final URL — it is the canonical URL
   for the capture, and the postmortem notes below should pin it for the next cycle.
2. **Collect every representation offered.** The rendered results page itself, plus every
   machine-readable export the authority publishes (CSV, XML, JSON — whatever is offered).
   Bytes first, judgment later: capture formats even if they look redundant; the ingestion
   design will decide which one matters.
3. **Capture each artifact.**

   **Interim form (until #281 lands — including the 2026-08-04 first execution).** King County
   Elections is an authority, not an endorsement source, and `evidence capture` currently
   accepts only registered endorsement sources, so capture manually and preserve exactly what
   a manifest would record. Per artifact:

   - compute the hash (`shasum -a 256 <artifact>`) and store the bytes at
     `data/snapshots/sha256/<first two hash characters>/<full sha256>` — the standard
     Git-ignored storage boundary;
   - record, in the capture PR and the postmortem notes: requested and final URLs (and the
     redirect chain when they differ), retrieval time in UTC, HTTP status, media type, byte
     length, the sha256, and the title per the target form's template ("<election>
     election-night results (<representation>)") — every field a backfilled manifest requires.

   Because storage is content-addressed, #281 backfills real manifests from these bytes and
   this metadata, and `evidence verify` proves the backfill honest.

   **Target form (after #281).** The capture method must match the artifact — the CLI's
   `CaptureRequest` validation rejects mismatches: `static_html` only for the rendered HTML
   results page; `pdf` only for PDF documents; `manual_upload` for the machine-readable
   exports (CSV, XML, JSON) — the CLI's honest category for bytes the caller fetched itself,
   whose manifest does not claim the command observed an HTTP exchange. Direct methods —
   `static_html`, `pdf`, and the escalation path's `browser` — additionally require
   `--http-status` with the observed 2xx; `manual_upload` takes no `--http-status`. When the
   final URL differs from the URL followed, record the chain with one or more `--redirect-url`
   options beginning with the requested URL and ending with the canonical URL; with no
   redirect, pass the same URL to both `--requested-url` and `--canonical-url`.

   ```bash
   uv run election-guide evidence capture tmp/<artifact> \
     --source-id <authority id per #281> \
     --requested-url <url followed> \
     --canonical-url <final url> \
     --retrieved-at <UTC timestamp of the fetch> \
     --media-type <text/html | text/csv | text/xml | application/json | application/pdf> \
     --capture-method <static_html | pdf | manual_upload> \
     --title "<election> election-night results (<representation>)" \
     --redistribution restricted \
     --redistribution-note "Official results retained locally; manifest public."
   ```

   In both forms, follow the repository default for raw official artifacts
   (`docs/COLLECTION.md`): restricted, local-only bytes with a public record of provenance,
   even though results are public records — relaxing that is a separate decision, not a
   capture-time judgment call.
4. **Repeat for the Secretary of State** (<https://results.vote.wa.gov>) for the same election,
   as corroborating evidence for state-level races. Secondary: skip rather than escalate if it
   is unavailable, and note the skip.
5. **Verify every capture.** Interim form: recompute each stored file's sha256 from its
   content-addressed path and confirm it matches the recorded hash and byte length. Target
   form:

   ```bash
   uv run election-guide evidence verify data/manifests/evidence/<capture-id>.json
   ```

6. **Open a pull request** with the capture record: in the interim form, the recorded
   provenance metadata (in the postmortem notes) with no manifests yet; in the target form,
   the new manifests. The PR body lists what was captured, the artifacts' formats, and any
   observations about structure — those observations are input to the ingestion adapter
   design (#208).

## Verification

- Every capture verifies (step 5): hashes and byte lengths recompute cleanly from the stored
  bytes — against the recorded metadata in the interim form, via `evidence verify` in the
  target form.
- The recorded retrieval times fall on election night, Pacific time.
- The PR contains only provenance records (and this runbook's postmortem notes); no bytes, no
  `data/results/` changes — ingestion happens at certification, not tonight.

## Escalation

Stop and flag a human when:

- No results publication is discoverable from the official election page by 9:00 p.m. Pacific.
  Retry hourly; do not guess at URLs beyond the authority's own navigation.
- The authority's page requires interaction (not static fetchable content) — in the interim
  form, note the fact and save what the browser delivered; in the target form, switch to the
  `browser` method with `--browser-required`, keeping `--http-status` (browser is also a
  direct method), and note the change here.

## Postmortem notes

*(Appended after each execution; this section is why the next cycle is easier than this one.)*

- 2026-08-03 (pre-execution review): `evidence capture` accepts only registered endorsement
  sources, and King County Elections is an authority, not an endorsement source — decided not
  to force it into the panel registry. The authority capture lane is #281; until it lands,
  step 3's interim manual form applies, and #281 backfills manifests from the retained
  content-addressed bytes.
- **2026-08-04 execution (`wa-2026-primary`, first count).** King County's page listed "Last
  updated: 8/4/2026 08:30 PM"; capture ran ~10:02 p.m. Pacific (2026-08-05T05:02Z–05:04Z UTC).
  Four artifacts captured in the interim manual form (no manifests yet — #281):

  | Artifact | Requested URL | Final URL | Retrieved (UTC) | Status | Media type | Bytes | sha256 |
  |---|---|---|---|---|---|---|---|
  | King County rendered results page | `https://kingcounty.gov/en/dept/elections/results/2026/august-primary-election` | same (no redirect) | 2026-08-05T05:02:45Z | 200 | `text/html; charset=utf-8` | 53270 | `5a8d5265e24349d43bc2befa8dbd39a89e63022bdd4b27c92f6e8131eb691f0f` |
  | King County results PDF | `https://election-results-pdf.kingcounty.gov/` | `https://election-results-01.kingcounty.gov/results.pdf` | 2026-08-05T05:02:25Z | 200 | `application/pdf` | 66021 | `de727e01e4d5c6d8b9ac244a7aa9be9daba1d7103b4f553400ad57748be9681a` |
  | King County results CSV | `https://election-results-csv.kingcounty.gov/` | `https://election-results-01.kingcounty.gov/webresults.csv` | 2026-08-05T05:02:25Z | 200 | `application/vnd.ms-excel` | 53262 | `3e240a3c0012635c21bf31ee6c1c89d73371cee5665c4198d09f71521c2de7ed` |
  | WA Secretary of State results JSON (statewide, corroborating) | `https://results.votewa.gov/results/public/api/elections/washington/20260804/data` | same (no redirect) | 2026-08-05T05:04:45Z | 200 | `application/json; charset=utf-8` | 430835 | `a110484467bd178f124d53746786292bae65ae10413c681bbde10893ca22fa40` |

  Titles follow the template: "2026 Washington August Primary election-night results
  (King County rendered results page)", "(King County PDF)", "(King County CSV)", and
  "(WA Secretary of State JSON, statewide)" respectively. All four stored at
  `data/snapshots/sha256/<first two chars>/<full sha256>`; every stored file's sha256 and byte
  length recomputed and matched (step 5).

  Discoveries for the next cycle:
  - King County's landing page links to the PDF and CSV via **client-side meta-refresh**
    (`<meta http-equiv="refresh">`), not an HTTP redirect — `curl -L` does not follow it. The
    canonical bytes live on a separate `election-results-01.kingcounty.gov` Azure-blob host;
    resolve the meta-refresh target and fetch that URL directly.
  - No XML export is offered; only the rendered page, one PDF, and one CSV.
  - King County serves the CSV with `Content-Type: application/vnd.ms-excel`, not `text/csv`,
    even though the content is plain CSV — recorded the observed media type as-is rather than
    normalizing it.
  - The King County landing page itself carries real evidence (turnout stats, validation
    requirements) distinct from the PDF/CSV, so it was captured as its own artifact rather than
    treated as mere navigation.
  - `results.votewa.gov` is a client-rendered SPA — the server-delivered HTML shell carries no
    results data. The actual data is a public, unauthenticated JSON export at
    `/results/public/api/elections/washington/<election-yyyymmdd>/data`, directly fetchable
    without a browser; captured that instead of the empty shell. This dataset is statewide, not
    Seattle/King-County-scoped.
  - All four fetches used a direct HTTP GET (`curl`) rather than the CLI, consistent with the
    interim form; no `browser_required` escalation was needed since every artifact was reachable
    without JS interaction once the canonical URLs were resolved.
