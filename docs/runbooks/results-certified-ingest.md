# Runbook: certified results capture and ingest

Capture the certified canvass as evidence the day after certification, then produce
`data/results/<election-id>.yaml` — the one results ingest the design allows
(`docs/RESULTS.md`: certified results only; the counting window ingests nothing).

**Status: executable.** Both phases are executable now. Phase 2's adapter and validator landed
with #284, informed by the formats the election-night capture observed
(`docs/RESULTS.md`, "Ingestion mechanics"). Phase 2 currently ingests King County's certified CSV
export only; the races whose true totals require the Secretary of State's results (Legislative
District 32, Congressional District 9, and the four Supreme Court Justice positions — see
`docs/RESULTS.md`, "Ingestion mechanics," County scope) are named explicitly in step 4's
`--race-id` list and omitted from a King-County-sourced ingest rather than silently published
from a partial count. Ingesting those races' true totals is a follow-up, not yet built.
`results ingest` requires `--race-id` — there is no every-publication-eligible-race default — so
omitting a cross-county race here is the only way to run it, never an accident.

## Trigger

The `results_capture_post_certification` calendar milestone: the day after certification
(primary/special: election day +16; general: +22). For `wa-2026-primary`: certification
2026-08-19, this runbook 2026-08-20.

## Autonomy

Human-launched. Phase 2 ends in a data change that flips every results surface on the site;
it should stay human-launched at least through the first full cycle.

## Preconditions

- The certification milestone has passed and King County has published certified results —
  confirm the results page states certified/final status, not an interim count.
- The election-night capture runbook ran and its manifests exist, **if** it ran for this
  election. For `wa-2026-primary` it did not: the 2026-08-04 capture's bytes are not present in
  this checkout (established investigating #281 — never re-fetched to avoid asserting a stale
  count as if it were fresh) and no manifest exists to cite. `--election-night-capture` in step 4
  is optional for exactly this reason; omit it for `wa-2026-primary`'s run rather than inventing a
  manifest path.

## Procedure

### Phase 1 — capture the certified record

1. Collect the certified results in every representation offered — the results page, the
   machine-readable exports, and the canvass/certification documents King County publishes
   (abstract of votes, certification letter), which state the thing the site will assert:
   that these numbers are final. King County's certified export is the CSV at
   `https://cdn.kingcounty.gov/-/media/king-county/depts/elections/results/<year>/<month>/webresults-<date>.csv`
   (`docs/RESULTS.md`, "Ingestion mechanics") — the adapter's parse target.
2. Capture and verify each artifact exactly as in
   `results-capture-election-night.md` steps 3 and 5 (same authority identity, same
   restricted redistribution default), with titles naming the certified status.
3. Capture the Secretary of State's certified results for state-level races as corroboration.

### Phase 2 — ingest

4. Run the adapter against the captured certified CSV export to produce
   `data/results/<election-id>.yaml` per the `docs/RESULTS.md` data model — that document
   owns the contract; this runbook does not restate it. Pass every publication-eligible race
   King County's canvass alone can state the true total for
   (`docs/RESULTS.md`, "Ingestion mechanics," County scope); for `wa-2026-primary` that is
   every publication-eligible race except Legislative District 32, Congressional District 9,
   and the four Supreme Court Justice positions. Omit `--election-night-capture` — there is no
   `wa-2026-primary` election-night manifest to cite (Preconditions, above); pass it only for a
   future election whose election-night runbook actually ran and produced one:

   ```bash
   uv run election-guide results ingest \
     --election-id wa-2026-primary \
     --authority-id king-county-elections \
     --certified-on 2026-08-19 \
     --certified-capture data/manifests/evidence/<certified-capture-id>.json \
     --race-id king-county-assessor --race-id king-county-council-2 \
     --race-id king-county-council-8 --race-id ld-11-state-representative-1 \
     --race-id ld-11-state-representative-2 --race-id ld-34-state-representative-1 \
     --race-id ld-34-state-representative-2 --race-id ld-34-state-senator \
     --race-id ld-36-state-representative-1 --race-id ld-36-state-representative-2 \
     --race-id ld-36-state-senator --race-id ld-37-state-representative-1 \
     --race-id ld-37-state-representative-2 --race-id ld-37-state-senator \
     --race-id ld-43-state-representative-1 --race-id ld-43-state-representative-2 \
     --race-id ld-43-state-senator --race-id ld-46-state-representative-1 \
     --race-id ld-46-state-representative-2 --race-id ld-46-state-senator \
     --race-id seattle-city-council-5 --race-id seattle-municipal-court-judge-5 \
     --race-id seattle-proposition-1-library-levy --race-id us-house-7
   ```

   The command aborts if any listed race is missing from the export, if a contest or candidate
   name resolves ambiguously or not at all, or if the export is missing an expected column —
   the one judgment rule this runbook owns: unmatched candidate or contest names escalate, they
   are never guessed.
5. Run the validator against the produced file:

   ```bash
   uv run election-guide results validate data/results/wa-2026-primary.yaml
   ```
6. Rebuild and confirm the results surfaces render: banner in its certified state, race-card
   results strips, endorsements-dialog vote rows, compare column offered, corrections page
   only if this election has corrections.

## Verification

- Phase 1: every capture ID verifies; the captured pages state certified status.
- Phase 2: `results ingest` and `results validate` both succeed; the rendered guide shows
  certified results with the certification date; the diff contains
  `data/results/<election-id>.yaml`, manifests, and rendering output only.
- One pull request per phase (or one combined, if phase 2 is same-day); production deploy
  approval remains with the human reviewer.

## Escalation

- Certification did not happen on the calendar date — check King County's canvass schedule;
  correct the calendar offset via a reviewed change if the statute-derived date was wrong.
- `results ingest` aborts on an unmatched, ambiguous, or missing race or candidate name —
  never force a mapping; bring the discrepancy to a human with both spellings. Recheck the
  export's column names too: the adapter's parse target assumes King County keeps its current
  `Contest`/`Choice`/`Votes`/`BallotsWith Contest` CSV columns (`docs/RESULTS.md`, "Ingestion
  mechanics"); a real schema change there is a design conversation, not a silent adapter patch.
- A race outside the `--race-id` list above (Legislative District 32, Congressional District 9,
  a Supreme Court Justice position) needs to ship: its true total requires the Secretary of
  State's export, which this adapter does not yet parse (`docs/RESULTS.md`, open questions) —
  file or pick up that follow-up rather than ingesting King County's partial count for it.
- A race's write-in tally is large — including the unopposed races above, where a write-in is a
  voter's only alternative to the single declared candidate. This is expected and needs no
  action: `share` is computed against the declared (non-write-in) total, so declared shares sum
  to ~1 regardless, while `ballots_counted` is always King County's own `BallotsWith Contest`
  figure for the race, untouched by any of this (`docs/RESULTS.md`, "Ingestion mechanics,"
  Write-in votes). No race is ever dropped from the run for this.
- `results ingest` aborts with `zero votes for every declared ballot choice in race ...`: the
  export gave that race's named candidates no votes at all while write-ins carried some. Treat it
  as a capture or export problem — re-check the captured file for the race before anything else,
  and bring it to a human. Do not hand-edit the results file.
- `results ingest` aborts with `zero ballots-with-contest for race ...` or `two different
  ballots-with-contest counts for ...`: the export's own `BallotsWith Contest` column was zero or
  inconsistent across a contest's rows for that race. This points at a malformed or truncated
  capture, not a data judgment call — re-check the captured file and bring it to a human.
- `results ingest` aborts the whole run with `shares sum to ..., not ~1` for one race: after the
  declared-total share fix this should be unreachable from a normal ingest (the shares the
  adapter writes sum to one within a few ten-thousandths, far inside
  `src/election_guide/results/models.py`'s `SHARE_SUM_TOLERANCE`), so seeing it means the adapter
  itself is wrong, not the data. Stop, keep the capture, and escalate to a human — do not drop
  races or edit numbers to get a run through. The same error from `results validate` on a
  hand-edited or amended file is instead a defect in that file.
- A recount is announced after ingest: the eventual amended flow (`docs/RESULTS.md`,
  open questions) is decided then — do not overwrite the certified file ad hoc.

## Postmortem notes

- Not yet executed against live data. Phase 2's adapter and validator (`results ingest`,
  `results validate`) landed with #284 and are exercised by that PR's fixture test
  (`tests/test_results.py`, a trimmed real King County CSV excerpt) — no network, offline only.
  First live execution: `wa-2026-primary`, phase 1 due 2026-08-20, phase 2 the same day per
  the procedure above.
