# Preliminary official results refresh (#696)

Preliminary means unofficial count-so-far. Complete jurisdiction coverage does not mean
counting or reporting has finished. Never publish King County's share as a statewide or
multi-county total. This runbook does not reopen #535 or perform future #692/#693 early.

## Admission

1. Start from the registered official authority and actually offered publication links.
   Verify election, jurisdiction and unofficial/certified status. Preserve actual response
   bodies, URLs, redirects, status and check clocks; stop actual access denials without a
   different actor, user-agent, login, host or guessed endpoint workaround.
2. Preserve new official bytes through the normal `election-guide evidence capture` writer,
   in the tracked official evidence store. Keep every original capture unchanged. A new
   retrieval is not a new publisher count time, and export generation is not count-as-of.
3. Prove every frozen race's full official contest scope and choice mapping. Statewide and
   cross-county races need their complete authoritative count-so-far. Prefer the official
   aggregate; never sum selected counties or infer scope from empty `crossCounties`.
4. Bind each tally to its actual publisher count timestamp and original capture. Verify
   reported update schedules and certification status/timing separately for each authority.
   County November24 and existing calendar tickets do not prove State certification timing.
5. Preserve all named choices and separate write-ins. Percentages use named-choice votes.
   The countline uses only the authority's stated contest-ballots or explicitly stated vote
   total, with the correct noun; never derive a ballot count by adding candidate votes.
6. Validate the strict preliminary document, frozen inventory and all retained evidence
   with `uv run --offline --frozen election-guide results validate <results-file>`.
   Unsupported/missing geography, clock or choices blocks admission. A partial County-only
   candidate cannot be marked complete. Current data files remain absent until these proofs
   exist; historical schema fixtures are not production data or current-data approval.

## Refresh and failures

The local producer consumes an explicitly reviewed mapping and already captured bytes:

```sh
uv run --offline --frozen election-guide results ingest-preliminary <mapping.yaml> \
  --inventory-path data/normalized/wa-2026-general-inventory.json
uv run --offline --frozen election-guide results validate data/results/wa-2026-general.yaml
```

`PreliminaryAdmissionPlan` binds each source format, registered authority and immutable
capture; every inventory race then binds its exact source contest ID/name, jurisdiction,
whole-scope proof and every named source choice ID/name to the frozen ballot choice.
There is no name-only discovery or partial-inventory production mode. The parser preserves
unknown fields: the historical statewide Media Export's `createdAt` is generation time,
not count-as-of, and that payload does not independently establish unofficial status or
an explicit authority contest total. It cannot pass this producer without those proofs.
An existing certified file cannot be overwritten with preliminary results.

Use an operator-triggered capture/admission/diff/review/publication sequence after official
announced releases. Check at least daily during active counting, grounding the actual schedule
in publisher evidence. No live client polling, scheduled automatic commit or direct deploy.
Compare every named count/share, reporting state, coverage and source clock. A lower corrected
count is a reviewable revision, not a value to silently clamp or discard. A timestamp regression
or changed election/schema/scope must stop new admission and preserve the previous snapshot.

Retain the last admitted whole-jurisdiction counts on a later access/refresh failure, with
their original count-as-of and explicit stale/unavailable status. Do not replace them with
zero, advance their publisher clock, erase endorsement facts or manufacture a successful
check. A successful unchanged official recheck can update verification time separately; it
cannot advance count-as-of. All changed count/share information passes normal exact-head
checks, substantive Election Updates, independent review and protected release gates.

Record a genuine failed retrieval with the normal evidence-unavailable writer, then attach
that retained unavailable manifest with:

```sh
uv run --offline --frozen election-guide results record-refresh-failure \
  data/results/wa-2026-general.yaml <unavailable-manifest.json>
```

The source identity and actual check clock must match the manifest. This is not a way to
label a mapping/validation error as an HTTP failure. Counts and their publisher timestamps
remain unchanged. A later successful capture can clear the visible warning while keeping
failure history. The displayed verification time ages to **Stale** after 24 hours; a later
failed retrieval displays **Refresh unavailable**. Reader-side aging makes no requests,
writes no storage and cannot certify data. The count-as-of remains visible throughout.
None of these result checks refreshes endorsement publisher-access clocks or `data_as_of`.

## Certification

A calendar date is never evidence of certification. Capture the authority's actual formal
certification publication at the proper future window, verify complete coverage and reconcile
authority-specific dates/status. Use the certified/amended ingestion contract; do not relabel
preliminary tallies or rewrite historical captures. Preliminary data cannot satisfy the
calendar's certified-results ingestion milestone. Keep #692/#693 scope accurate when actual
authority evidence establishes any needed follow-up correction.
