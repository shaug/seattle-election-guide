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
- **Run from the primary checkout, not a disposable worktree.** Captured bytes go to the tracked
  `data/evidence/official/` root and are committed with the manifests, so they survive; the
  command refuses a Git-ignored storage root inside a linked worktree, because that is exactly
  how the 2026-08-04 capture was lost (`docs/COLLECTION.md`, issue #357).

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
     --storage-root data/evidence/official \
     --redistribution permitted \
     --redistribution-note "Official public record; bytes retained in the repository."
   ```

   **Where the bytes must live:** the tracked `data/evidence/official/` root, not the ignored
   `data/snapshots/`. Official results are public records, so their bytes are committed and
   survive by the same mechanism as the rest of the repository (`docs/COLLECTION.md`). The
   manifest records `storage_scope: repository`; the command derives that from the root, so
   passing `--storage-root` is what makes it true.
4. **Repeat for the Secretary of State** (<https://results.vote.wa.gov>) for the same election,
   as corroborating evidence for state-level races, using `--source-id wa-secretary-of-state`.
   Secondary: skip rather than escalate if it is unavailable, and note the skip.
5. **Verify every capture, then confirm the bytes survived the session.**

   ```bash
   uv run election-guide evidence verify data/manifests/evidence/<capture-id>.json
   uv run election-guide evidence verify-all
   git status --short data/evidence/official
   ```

   `verify` proves each artifact matches its manifest. `verify-all` proves no manifest anywhere
   references bytes nobody holds. `git status` is the survival check the 2026-08-04 run did not
   have: every new artifact must appear as an untracked file ready to commit. If
   `data/evidence/official/` is empty or shows nothing, the bytes are not in the repository and
   will not survive — stop and re-capture with `--storage-root data/evidence/official` before
   going further.
6. **Open a pull request** with the new manifests **and their bytes**. The PR body lists what was
   captured, the artifacts' formats, and any observations about structure — those observations
   are input to the ingestion adapter design (#208).

## Verification

- Every capture verifies (step 5): `evidence verify` recomputes the SHA-256 and byte length from
  the stored bytes and confirms they match the manifest.
- `evidence verify-all` reports every official artifact `present`. Restricted endorsement
  artifacts report `expected-absent` when their ignored store is not on this machine; that is
  the documented passing state, not a failure (`docs/COLLECTION.md`).
- The recorded retrieval times fall on election night, Pacific time.
- The PR contains the new manifests, the new bytes under `data/evidence/official/`, and this
  runbook's postmortem notes; no `data/results/` changes — ingestion happens at certification,
  not tonight.
- After the PR merges, the bytes are on `main`. That, not a passing capture-time verification, is
  what makes the capture durable.

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
- **#357 changed where bytes live, so this cannot recur silently.** The loss above was never a
  redistribution judgment — it was a durability one that the restricted default made for us.
  Official-authority artifacts are now `redistribution: permitted`, stored in the tracked
  `data/evidence/official/` root, and committed alongside their manifests
  (`docs/COLLECTION.md`). Three things now enforce what this postmortem could only describe:
  `evidence capture` refuses a Git-ignored storage root inside a linked worktree — the exact
  mechanism that lost these bytes; `evidence verify-all` sweeps every manifest for byte presence
  and runs in `make check`; and step 5 now ends in a `git status` survival check rather than a
  capture-time verification that was already true at the moment the bytes died. The four
  artifacts above remain unrecoverable — those URLs serve a later drop — so this table stays
  their only record.

- **2026-11-03 execution (`wa-2026-general`, election-night initial capture; #535).**
  The existing accountable root operator used the authorized hourly backup in the proper window.
  The one-time wake had fired early at 14:24 Pacific and was rejected by the real-clock guard;
  it did not capture results. The exclusive capture guard began at 20:15:43 Pacific. Actual
  official navigation began at 20:16:15, and the retained representations were obtained between
  20:16:38 and 20:18:28 Pacific (2026-11-04 UTC). These are actual later retrieval times, not an
  exact 20:15 download or proof of the earliest publication ever served.

  Discovery followed the official Elections homepage → Results → 2026 → November General:
  <https://kingcounty.gov/en/dept/elections/results/2026/november-general>.
  This page offered its PDF and CSV links and “View Results” at
  <https://results.votewa.gov/results/public/king-county-wa/elections/20261103>.
  The PDF/CSV landing hosts returned HTTP 200 HTML with client-side meta-refresh targets,
  observed this evening, of `https://election-results-01.kingcounty.gov/results.pdf` and
  `https://election-results-01.kingcounty.gov/webresults.csv`. Each target was fetched directly;
  these were not HTTP redirects, and neither URL was guessed from the August capture.
  All retained direct responses were HTTP 200; no HTTP redirect was observed.

  The delegated results page required ordinary browser rendering. A single supported automated
  Chrome navigation, with passive Network observation enabled before navigation, retained its
  original HTTP shell, browser-produced full DOM HTML and full-page PNG, and the actual
  browser-loaded County count-data response. The DOM/PNG are browser artifacts, distinct from
  original HTTP entity bytes. Their manifests use `browser`, `browser_required: true`, and the
  observed underlying page HTTP 200; no separate image HTTP GET is claimed. The browser page
  displayed **UNOFFICIAL RESULTS**, “Last Updated Tuesday, November 3, 2026 at 8:12:12 PM”,
  535,712 ballots cast, and 1,460,414 registered voters. The PDF is 17 pages and separately
  prints `2026-11-03 20:08:11`; that producer clock is retained rather than substituted for the
  page update or retrieval time. The CSV has 286 choice rows across 115 contest IDs.

  The rendered page also actually offered “Media Export” at
  <https://results.votewa.gov/cdn/results/washington/export-20261103.json>.
  This statewide JSON was captured as Secretary of State corroboration. It reports
  `electionDate: 2026-11-03`, `electionName: 2026 General`, and its own
  `createdAt: 2026-11-04T04:16:52.5976406Z`; that is not the retrieval clock.
  It was served as `application/octet-stream`, which is preserved. The County CSV was served
  as `application/vnd.ms-excel`, also preserved. The browser-loaded County JSON was an actual
  application response, not an independently guessed or fetched export URL. The three offered
  export formats were PDF, CSV and statewide JSON; no XML export link was observed. Future
  daily-report and precinct-report labels on the County landing page did not offer downloadable
  links at this observation; no future or inferred URLs were requested.

  The supported evidence CLI ran from the primary checkout on an ordinary capture branch from
  actual main M51. The original `codex/hide-uncontested-races` branch/2433376 head and unrelated
  `.claude` work were preserved. The current configuration uses `official_url` rather than the
  runbook's older `ballot_data_sources` description; explicit supported authority-registry,
  manifest-directory and official-storage arguments resolved capture inputs without changing
  factual/product configuration. Machine-readable exports use `manual_upload` with no manifest
  HTTP status; the observed HTTP 200 and exact retrieval provenance are recorded in this table.

  | Representation / capture ID | Retrieved UTC | Observed HTTP / media type | Bytes | SHA-256 |
  |---|---|---|---:|---|
  | King County official results landing HTML<br>`capture-king-county-elections-20261104T041638Z-e677f9a12054` | 2026-11-04T04:16:38.859970Z | 200 / `text/html; charset=utf-8` | 54106 | `e90985f82c66f9cfbd520ec7bdfc9399424c8b18dc9d0e53617260a0d9a57756` |
  | King County PDF<br>`capture-king-county-elections-20261104T041704Z-d9f6ee0af95e` | 2026-11-04T04:17:04.631324Z | 200 / `application/pdf` | 49528 | `37ea544fff8c4763bb499e07a475747b106e70399b6afa1b48dc18a939c475d9` |
  | King County CSV<br>`capture-king-county-elections-20261104T041704Z-c65326f14ea0` | 2026-11-04T04:17:04.615486Z | 200 / `application/vnd.ms-excel` | 38447 | `0a6ebe9ab5289cc665d8b68a4a17a7343e7ae62ee38af43e37a5d87cdfcdde7c` |
  | King County delegated results HTTP shell; no count content<br>`capture-king-county-elections-20261104T041651Z-a505e0e0843a` | 2026-11-04T04:16:51.645421Z | 200 / `text/html` | 9684 | `d70a5009efd290a24fc9ba9a4db29533b367c0a8fee4e9710d3c2a51802bdc52` |
  | King County rendered results DOM HTML<br>`capture-king-county-elections-20261104T041756Z-d7aa8bfc51bf` | 2026-11-04T04:17:56.108586Z | 200 / `text/html` | 504302 | `c9b58eac9402e1543e78dc9f06d85a9784d109fcb22a5c83f4e8ccd680b7f116` |
  | King County rendered results full-page PNG<br>`capture-king-county-elections-20261104T041756Z-d20ed36bafde` | 2026-11-04T04:17:56.108586Z | 200 / `image/png` | 2617060 | `aee24ca1fe23e0f7369f7c8303ab298286c012665969bcfeced3a7f12fece69e` |
  | King County browser-loaded count data JSON; decoded HTTP entity<br>`capture-king-county-elections-20261104T041756Z-5ce16f5cb190` | 2026-11-04T04:17:56.823912Z | 200 / `application/json; charset=utf-8` | 771116 | `eba2d525d864dc57a546b6552c8dffa629746a65351b7002b18b0819c115f68f` |
  | WA Secretary of State offered Media Export JSON, statewide corroboration<br>`capture-wa-secretary-of-state-20261104T041828Z-dfc19a67eb1f` | 2026-11-04T04:18:28.818844Z | 200 / `application/octet-stream` | 848195 | `3de8a3aba113b76f933774e4b6f2de8319f370b329951ed0b8ca1242b62d4b8e` |

  All eight captures passed `evidence verify`; `evidence verify-all` passed with 588 manifests:
  507 present, 22 expected-absent restricted artifacts, and 59 no-artifact records. Every new
  artifact is under tracked `data/evidence/official/sha256/`, with its immutable manifest under
  `data/manifests/evidence/`. Original HTTP entity bytes and decoded browser response entities
  retain their respective provenance; no compressed-wire or global network proof is claimed.
  No results ingestion, `data/results/`, election facts, UI, or production publication changed.
  The evidence commit/PR is the durability handoff; bytes are not claimed to be on main until
  an authorized merge is actually observed. Certification and the November 24/25 follow-up
  remain separate future work.

  During evidence-PR preparation, Git treated the extensionless, content-addressed PDF as text:
  its ReportLab binary marker contains non-UTF-8 bytes, but the file has no NUL byte for Git's
  binary heuristic. The standard review runner therefore stopped while decoding the default
  Git diff, before creating a review invocation. That failure remains recorded. The PDF's exact
  immutable path is now classified as `binary` in `.gitattributes`, matching the existing
  `*.pdf binary` policy. This disables text conversion and text diff/merge handling for that
  one PDF; its original bytes, Git blob, capture manifest and SHA-256 remain unchanged. No
  review-runner, diff-producer, decoding or evidence-verification rule was changed.
