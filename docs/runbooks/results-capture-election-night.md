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
- A working directory under the Git-ignored `tmp/` for downloaded artifacts.

## Procedure

1. **Locate the results publication.** From the election's official page, follow the results
   link King County activates on election night. Note the final URL — it is the canonical URL
   for the capture, and the postmortem notes below should pin it for the next cycle.
2. **Collect every representation offered.** The rendered results page itself, plus every
   machine-readable export the authority publishes (CSV, XML, JSON — whatever is offered).
   Bytes first, judgment later: capture formats even if they look redundant; the ingestion
   design will decide which one matters.
3. **Capture each artifact:**

   ```bash
   uv run election-guide evidence capture tmp/<artifact> \
     --source-id king-county-elections \
     --requested-url <url followed> \
     --canonical-url <final url> \
     --retrieved-at <UTC timestamp of the fetch> \
     --http-status 200 \
     --media-type <text/html | text/csv | …> \
     --title "<election> election-night results (<representation>)" \
     --capture-method static_html \
     --redistribution restricted \
     --redistribution-note "Official results retained locally; manifest public."
   ```

   Follow the repository default for raw official artifacts (`docs/COLLECTION.md`): restricted,
   local-only bytes with a public manifest, even though results are public records — relaxing
   that is a separate decision, not a capture-time judgment call.
4. **Repeat for the Secretary of State** (<https://results.vote.wa.gov>) for the same election,
   as corroborating evidence for state-level races. Secondary: skip rather than escalate if it
   is unavailable, and note the skip.
5. **Verify every manifest:**

   ```bash
   uv run election-guide evidence verify data/manifests/evidence/<capture-id>.json
   ```

6. **Open a pull request** containing the new manifests. The PR body lists what was captured,
   the artifacts' formats, and any observations about structure — those observations are input
   to the ingestion adapter design (#208).

## Verification

- Every capture ID verifies (step 5) — hash and byte length recompute cleanly.
- The manifests' retrieval times fall on election night, Pacific time.
- The PR contains only manifests (and this runbook's postmortem notes); no bytes, no
  `data/results/` changes — ingestion happens at certification, not tonight.

## Escalation

Stop and flag a human when:

- No results publication is discoverable from the official election page by 9:00 p.m. Pacific.
  Retry hourly; do not guess at URLs beyond the authority's own navigation.
- `evidence capture` rejects the `king-county-elections` source id as unregistered. Registering
  an authority is a reviewed registry change, not something to improvise mid-capture.
- The authority's page requires interaction (not static fetchable content) that the
  `static_html` capture method cannot honestly describe — switch to the `browser` method with
  `--browser-required`, and note the change here.

## Postmortem notes

*(Appended after each execution; this section is why the next cycle is easier than this one.)*

- Not yet executed. First execution: `wa-2026-primary`, due 2026-08-04. Expected discoveries:
  the canonical results URL pattern, which export formats King County actually publishes,
  whether the `king-county-elections` source id needs registration first.
