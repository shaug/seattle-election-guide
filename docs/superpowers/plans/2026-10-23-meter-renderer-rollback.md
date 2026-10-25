# Meter renderer rollback implementation plan

Scope: [#598](https://github.com/shaug/seattle-election-guide/issues/598).
Follow the [approved design](../specs/2026-10-23-meter-renderer-rollback-design.md)
and [delivery record](../../PRIMARY_METER_ROLLBACK_2026-10-23.md).
Scott's October 24, 2026 direct approval covers the exact pre-#605 two-CSS
restoration, including the rebuilt primary overview, with current data and
interactions preserved and no redesign.

## Stage A: prepare served primary history

### Prepared content and local request

- Prepend one truthful preparation entry to
  `data/corrections/wa-2026-primary.yaml`, dated `2026-10-24`, linking #598 and
  the LD32 House Position 1 primary race page. Describe planned restoration on
  primary race pages and the overview without claiming deployment.
- Preserve the full existing file after the `entries:` prefix byte-for-byte.
- Add this public successor plan, the successor design and the delivery record.
  Leave the frozen local preview and historical primary-refresh record intact.
- Keep primary `.6` pins, CSS, tests, renderer, scoring, ledgers, normalized
  data, results, evidence, JavaScript and registry unchanged. Only the normal
  current-general request changes in `config/hosting/site.yaml`.
- Local preservation proofs and content self-review are recorded. Normal
  preparation and resolution selected the local `2026-general.37` request for
  #598 against accepted M11
  `e85f694f9a3fedfd96a7707a12bd8279ed5d93d7` (`2026-general.36`, 929 general
  decisions). Preparation publishes or reserves no version. Fresh gates, the
  private commit, canonical review and protected delivery remain part of
  controller finalization.

### Finalize A — controller execution

1. Use accepted M11 `e85f694f9a3fedfd96a7707a12bd8279ed5d93d7` as the final
   Stage A comparison base. Confirm that exact accepted predecessor before
   request preparation without rewriting history.
2. Confirm no competing publication writer and refresh accepted production and
   exact current inputs. Keep all primary `.6` pins and old history unchanged.
3. Reconcile the entry's date with the actual Pacific publication sequence. If
   a later date requires correction, make it through a protected source update;
   do not backdate or rewrite immutable published history.
4. Run focused correction/history validation:
   `uv run pytest tests/test_updates_history.py tests/test_updates_gate.py -q`.
   Do not add a test merely to mirror an append-only entry.
5. Prepare and resolve the current-general publication request with the existing
   release automation (`prepare --issue 598`, then `resolve`). Use only the next
   version actually available at execution. Commit with a conventional subject
   and verify exact-base admission.
6. Run all required gates, including `make check`, applicable reproducibility,
   exact-source staging and live `make check-updates`. Obtain fresh canonical
   repository review and protected CI for the final candidate. Inspect its actual
   notes, seven data checks, six rendering checks and desktop/mobile images.
7. Create and attach a non-closing `Refs #598` PR; merge only after the protected
   sequence passes. Independently verify automatic release and production,
   including both elections and served Updates histories. Record the exact
   accepted A merged SHA and durable receipts.

Stage A itself does not change primary rendering or its served Updates. The
new source entry first becomes served when Stage B selects archive 1.

## Archive 1: publish the history bridge

After A is independently accepted, build a new immutable primary archive twice
from its exact clean merged SHA and commit timestamp, using actual prior-primary
software-history lineage. Compare both complete builds. Inspect notes, all seven
data checks, all six rendering checks and both screenshots; verify all 538
primary decisions, five CSV exports, certified results, source membership and
nonmetadata/non-Updates view-model fields against the previous archive.

Confirm every earlier Updates entry is retained and the new preparation entry
is present. Publish under a newly available identity, download the actual
published asset and verify its source, release manifest and bundle identities.
Record the release/tag/asset IDs and hashes from evidence. Do not activate pins
before this verification or overwrite any archive.

## Stage B: restore the approved renderer and select archive 1

1. Start from actual accepted main and recheck inputs, production and writer
   ownership. Transfer the two approved CSS files to their exact bytes at
   `bea5e4edc5c50c985932b8ae5e123a39a0b51449`:
   `src/election_guide/rendering/templates/guide-race.css` and
   `src/election_guide/rendering/templates/race.css`. Inspect all intervening
   changes; do not revert an entire commit.
2. Transfer only the focused browser-test hunks for the restored border mechanism
   and both transitions. Preserve #602 diagnostics tests and unrelated coverage;
   never restore whole test files.
3. Select only the actual downloaded archive 1's verified primary pins. Preserve
   all current 929 general and 538 primary decisions, counts, percentages,
   allocations, results, colors, dimensions, membership and interactions.
4. Prepare accurate general and primary source Updates for the behavior delivered
   by this stage and the remaining overview activation. Source dates must match
   actual Pacific publication dates when finalized. Verify the served primary
   preparation entry comes from archive 1; source YAML alone is insufficient.
   No copy may claim that the primary overview is already restored at B.
5. Prepare a fresh automatic current-general request against the actual accepted
   predecessor. Run fresh full required gates and canonical review; inspect the
   exact protected CI candidate notes, reports and desktop/mobile screenshots.
   Verify approved border geometry and current touch, hover and keyboard behavior.
6. Deliver a non-closing protected PR and independently accept its automatic
   release and production. Record the exact accepted B merged SHA and receipts.
   Race pages now use the restored CSS; the copied primary overview still comes
   from archive 1 and is pending replacement.

No new UI behavior may be folded into B.

## Archive 2: publish the restored primary overview

Build two complete new primary archives from the exact clean accepted B merged
SHA, with its commit timestamp and actual prior-primary history. Compare,
inspect and verify them with the same data, export, validation, history and
screenshot checks as archive 1. Archive 2 must contain the restored overview and
accurate accumulated Updates without losing any old entry. Preserve the two
historical source-access/discovery limitations in the archived notes.

Publish under another new immutable identity, download and independently verify
the actual asset, then record its real source, manifest, bundle, release and
asset identities. Reserve no identity before execution and alter no old archive.

## Stage C: activate the restored overview

Select only the verified downloaded archive 2 pins in a separate protected PR.
Reconcile the final source and served Updates dates and descriptions with actual
Pacific publication dates through protected updates if needed. Prepare a fresh
current-general request against actual accepted main, retaining all earlier
history and pins except the explicitly reviewed archive 2 activation.

Run fresh full required gates, canonical review and protected CI; inspect the
exact candidate notes, validation reports and screenshots. After merge,
independently verify the automatic release, durable producer/upload receipts,
strict production probes, both elections, served Updates histories and all
affected page identities. Visually accept desktop and mobile general/primary
race pages and the rebuilt primary overview against the approved restoration;
confirm data and interactions remain intact. Close #598 only after that final
production and visual acceptance.

## Evidence and completion

Record actual accepted SHAs, source/manifest/bundle hashes, release/tag/asset IDs,
CI artifacts, durable receipts, independent probes and visual acceptance in the
delivery record as each step completes. A candidate, screenshot, local version
or successful build does not establish production acceptance. At this local
preparation boundary, A acceptance, archive 1, B, archive 2 and C remain pending.
