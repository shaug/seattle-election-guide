# Runbook: certified results capture and ingest

Capture the certified canvass as evidence the day after certification, then produce
`data/results/<election-id>.yaml` — the one results ingest the design allows
(`docs/RESULTS.md`: certified results only; the counting window ingests nothing).

**Status: preliminary.** Phase 1 (capture) is executable now. Phase 2 (ingest) is written to
the data-model contract in `docs/RESULTS.md`, but its tooling — the results adapter and
validator — does not exist yet; it is the ingestion design step of #208, informed by the
formats the election-night capture observes. Until that tooling lands, phase 2 stops at
escalation.

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
- The election-night capture runbook ran; its manifests exist (phase 2's format assumptions
  come from them).
- For phase 2: the results adapter and validator exist. If they do not, execute phase 1 and
  escalate.

## Procedure

### Phase 1 — capture the certified record

1. Collect the certified results in every representation offered — the results page, the
   machine-readable exports, and the canvass/certification documents King County publishes
   (abstract of votes, certification letter), which state the thing the site will assert:
   that these numbers are final.
2. Capture and verify each artifact exactly as in
   `results-capture-election-night.md` steps 3 and 5 (same authority identity, same
   restricted redistribution default), with titles naming the certified status.
3. Capture the Secretary of State's certified results for state-level races as corroboration.

### Phase 2 — ingest (blocked on #208's ingestion tooling)

4. Run the results adapter against the captured certified export to produce
   `data/results/<election-id>.yaml` per the `docs/RESULTS.md` data model — that document
   owns the contract; this runbook does not restate it.
5. Run its validator against the same contract. The one judgment rule this runbook owns:
   unmatched candidate or contest names escalate — they are never guessed.
6. Rebuild and confirm the results surfaces render: banner in its certified state, race-card
   results strips, endorsements-dialog vote rows, compare column offered, corrections page
   only if this election has corrections.

## Verification

- Phase 1: every capture ID verifies; the captured pages state certified status.
- Phase 2: validation passes; the rendered guide shows certified results with the certification
  date; the diff contains `data/results/<election-id>.yaml`, manifests, and rendering output
  only.
- One pull request per phase (or one combined, if phase 2 is same-day); production deploy
  approval remains with the human reviewer.

## Escalation

- Certification did not happen on the calendar date — check King County's canvass schedule;
  correct the calendar offset via a reviewed change if the statute-derived date was wrong.
- The certified export's contest or candidate names do not match the frozen inventory —
  never force a mapping; bring the discrepancy to a human with both spellings.
- Phase 2 tooling does not exist yet (the expected state for `wa-2026-primary`): finish
  phase 1, then hand the captured formats to the ingestion design conversation on #208.
- A recount is announced after ingest: the eventual amended flow (`docs/RESULTS.md`,
  open questions) is decided then — do not overwrite the certified file ad hoc.

## Postmortem notes

- Not yet executed. First execution: `wa-2026-primary`, phase 1 due 2026-08-20; phase 2
  expected to stop at escalation unless #208's ingestion tooling lands first.
