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
- The counting authorities are registered in `config/authorities/default.yaml`
  (`king-county-elections`, `wa-secretary-of-state`) — a separate identity registry from the
  endorsement-source panel (`docs/EVIDENCE_CAPTURE.md`, "Counting authorities"), since neither
  authority carries a panel role, reporting category, or endorsement eligibility.
- A working directory under the Git-ignored `tmp/` for downloaded artifacts.

## Procedure

1. **Locate the results publication.** From the election's official page, follow the results
   link King County activates on election night. Note the final URL — it is the canonical URL
   for the capture, and the postmortem notes below should pin it for the next cycle.
2. **Collect every representation offered.** The rendered results page itself, plus every
   machine-readable export the authority publishes (CSV, XML, JSON — whatever is offered).
   Bytes first, judgment later: capture formats even if they look redundant; the ingestion
   design will decide which one matters.
3. **Capture each artifact.** The capture method must match the artifact — the CLI's
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
     --source-id king-county-elections \
     --requested-url <url followed> \
     --canonical-url <final url> \
     --retrieved-at <UTC timestamp of the fetch> \
     --media-type <text/html | text/csv | text/xml | application/json | application/pdf> \
     --capture-method <static_html | pdf | manual_upload> \
     --title "<election> election-night results (<representation>)" \
     --redistribution restricted \
     --redistribution-note "Official results retained locally; manifest public."
   ```

   Follow the repository default for raw official artifacts (`docs/COLLECTION.md`): restricted,
   local-only bytes with a public record of provenance, even though results are public records —
   relaxing that is a separate decision, not a capture-time judgment call.
4. **Repeat for the Secretary of State** (<https://results.vote.wa.gov>) for the same election,
   as corroborating evidence for state-level races, using `--source-id wa-secretary-of-state`.
   Secondary: skip rather than escalate if it is unavailable, and note the skip.
5. **Verify every capture.**

   ```bash
   uv run election-guide evidence verify data/manifests/evidence/<capture-id>.json
   ```

6. **Open a pull request** with the new manifests. The PR body lists what was captured, the
   artifacts' formats, and any observations about structure — those observations are input to
   the ingestion adapter design (#208).

## Verification

- Every capture verifies (step 5): `evidence verify` recomputes the SHA-256 and byte length from
  the stored bytes and confirms they match the manifest.
- The recorded retrieval times fall on election night, Pacific time.
- The PR contains only the new manifests (and this runbook's postmortem notes); no bytes, no
  `data/results/` changes — ingestion happens at certification, not tonight.

## Escalation

Stop and flag a human when:

- No results publication is discoverable from the official election page by 9:00 p.m. Pacific.
  Retry hourly; do not guess at URLs beyond the authority's own navigation.
- The authority's page requires interaction (not static fetchable content) — switch to the
  `browser` method with `--browser-required`, keeping `--http-status` (browser is also a direct
  method), and note the change here.

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
- **#281 landed** (authority evidence capture lane): `config/authorities/default.yaml` registers
  `king-county-elections` and `wa-secretary-of-state`; `evidence capture`/`evidence unavailable`
  accept either registry via `--authority-registry-path`. An election is identified by the title
  convention (`docs/EVIDENCE_CAPTURE.md`, "Counting authorities") rather than a new manifest
  field — a structured field was tried and reverted there because it changed the serialized shape
  of every already-committed evidence manifest. Step 3 above now shows only the target form; this
  and the 2026-08-03/2026-08-04 entries above are the retired interim form's permanent record.
  - **Backfill attempted, bytes unavailable.** Per this ticket's own scope ("if the bytes are
    unavailable or the capture never ran, land the lane without backfill and file the gap
    honestly — never fabricate manifests"): the implementing session located
    `data/snapshots/sha256/` on the operator's primary checkout (reachable, populated with 43
    files) but none of the four hashes recorded above
    (`5a8d5265…`, `de727e01…`, `3e240a3c…`, `a110484467…`) were present there, and every present
    file's modification time predates the 2026-08-04/05 capture by two weeks — they are
    unrelated endorsement-source evidence, not the retained election-night bytes. The retained
    bytes described in PR #322 and above are not reachable from any environment available to
    this implementation. No manifests were fabricated. **Next action**: whoever holds the actual
    retained bytes (or can re-derive them, e.g. from the King County/SoS pages' first-count
    history if still available) should run the step-3 command above against them to produce the
    four backfilled manifests; until then, this election's first-count capture has a documented
    provenance record (this table) but no formal manifest.
