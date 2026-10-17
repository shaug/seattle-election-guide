# Updates history audit — October 16, 2026

Scope: [#556](https://github.com/shaug/seattle-election-guide/issues/556). The maintainer requested
the missing history for both elections, corrected publication dates, and verification from each
guide's first publication. This supersedes the `.9` publication record's initial claim of a
complete backfill.

## Coverage boundary

The audit starts with the first downloadable primary guide, `2026-primary.1`, published
**July 19, 2026 at 11:34:35 p.m. Pacific**, before the website opened July 21. The general guide
starts with `2026-general.1`, published **October 3, 2026**. The end is the published
`2026-general.9` production revision, `5251de04a3ac09804eff2983fc67e8b6b0cc71b0`.

Every one of the **283 first-parent commits** after the primary baseline through that end is
classified in the [combined commit inventory](audits/updates-2026-10-16/commit-inventory.json).
The inventory records the full revision, its public change or exclusion, the final dated
headline, and successful deployment evidence. Its ordered revision list was compared with
`git rev-list --first-parent --reverse 2026-primary.1..5251de04a3ac09804eff2983fc67e8b6b0cc71b0`:
no missing, extra, or repeated revisions.

There are **30 primary entries and nine general entries**, including each first publication.
Eighty-eight commits map to entries, including supporting code whose public effect arrived at
later activation. The other 195 have explicit exclusions. The inventory includes whole-history
review, not just a renderer-path search: that caught the certification-date correction in
calendar configuration.

The public log covers changes to recorded choices, source membership or eligibility, evidence,
counts and shares, race visibility, results, and meaningful reader behavior on the aggregate
and race pages. A changed leading choice is not required. Software-only work, cosmetic shell
polish, unchanged rechecks, preparation before first publication, and dormant features remain
explicit exclusions under [the Updates policy](RESULTS.md#the-updates-page). Reader selections
and time-dependent states already defined by published behavior are not separate editorial
releases. This audit makes a bounded claim through the named revision; later changes still
require their own entries.

## Publication dates

The [publication evidence](audits/updates-2026-10-16/publications.json) binds every dated entry
to a published release or successful website deployment. Dates use `America/Los_Angeles`.
Merge dates, review dates, source announcement dates, and certification dates are distinct.
Supporting code that could not render until data arrived maps to that activation, not to its
earlier merge.
The [failed-run assurance](audits/updates-2026-10-16/failed-run-assurance.json) also checks the
deployment steps, rather than treating every failed workflow as proof that nothing published.
The earlier statewide-results, co-endorsement, and `.6` attempts all skipped production upload;
their failures do not hide an earlier publication.

Important corrections and delayed publications:

| Change | Published date used | Why |
| --- | --- | --- |
| Primary's 312 initial additions | July 21 | The July 20–21 preparation first reached the public website together. |
| Primary certification date and first 24 results | August 19 | Certification was August 18; the guide corrected its date and published results the next day. |
| Remaining eight primary results | September 13 | The August 22 change first passed production publication on September 13. |
| Primary archive regression | October 3 | General cutover served the older August 2 snapshot. |
| Primary archive restoration | October 11 | The replacement release and restored website were published that evening. |
| King County Democrats co-endorsement | October 11 | Reviewed October 10; the `.5` release and working website followed October 11. |
| Sparse and unopposed general races | October 12 | Both changes reached the website that day, before the later October 16 release. |

The October 3 primary incident did **not** remove individual race URLs. The overview was copied
from the pinned old bundle, while Sources, Comparisons, race pages, and race previews were
regenerated from its older view model using the current renderer. The direct pages remained
available but lost later endorsements and certified results. Their share-preview bars also
changed and were restored that day. The log distinguishes those surfaces.

## Primary data changes

The [primary data audit](audits/updates-2026-10-16/primary-data.md),
[decision-level comparisons](audits/updates-2026-10-16/primary-data-changes.json), and
[first-website score comparison](audits/updates-2026-10-16/primary-initial-site-scores.json)
account for every source/race addition and changed score or coverage row, including unchanged
leaders. Five semantic batches add **364 decisions**, taking **174 → 538**, with no endorsement
removals or replacements:

| First publication | Decisions added | Resulting total |
| --- | ---: | ---: |
| July 21, first website | 312 | 486 |
| July 23, six additional organizations | 35 | 521 |
| August 5, six source rechecks | 17 | 538 |

The first row combines three preparation batches: 209, 81, and 22 additions. It also records the
broader eligibility of the seven legislative-district organizations and changed evidence links.
All primary ballot choices and race inventory remain unchanged after the first release.

The [results comparison](audits/updates-2026-10-16/primary-results-changes.json) accounts for the
24 initial King County results and eight later statewide results. The original 24 numerical
outcomes remain unchanged. The archive regression removed the later 17 endorsements and all
32 results from the served snapshot; restoration brought them back. Neither event is described
as an organization withdrawing or reissuing an endorsement.

Published `.1`, `.2`, and `.3` canonical and consensus artifacts were downloaded. Exact allocations,
support, counts, shares, and grades were recomputed for **all 32 races in each**. No discrepancies
were found. The actual LD37 House Position 1 support changed from **6½–6½ to 8½–6½**; the old
PR #323 prose saying 7–7 to 9–7 is not copied into this history.

## Primary page changes

The [page chronology](audits/updates-2026-10-16/primary-pages.md) and
[supporting changes](audits/updates-2026-10-16/primary-page-changes.json) account for changes to
agreement labels, source selection and counts, Times comparisons, race ordering and filters,
shared links, candidate ordering and arithmetic, direct race pages, segmented meters, counting
notices, certified-result presentation, and archive behavior. The combined inventory binds
these records to the final public headlines; overlapping result and archive events share entries
with the data history.

The audit explicitly avoids inventing visible incidents from unused code. Primary Corrections
never appeared because it had no entries. The earlier incomplete result-display implementation
was replaced before real results were published. Removed confidence-flag hooks had no visible
flags in the actual primary data. Those changes are documented as dormant or software-only.

## General data and page changes

The [general data audit](audits/updates-2026-10-16/general-data.md) and
[complete semantic comparison](audits/updates-2026-10-16/general-data-changes.json) account for
**266 additions, three replacements, and no removals** since the 614-decision first release:

| Release | Added | Replaced | Resulting total |
| --- | ---: | ---: | ---: |
| `.4` | 3 | 0 | 617 |
| `.5` | 64 | 1 | 681 |
| `.6` | 22 | 0 | 703 |
| `.7` | 175 | 2 | 878 |
| `.8` | 2 | 0 | 880 |

The comparison also records changed evidence links, availability notes, contributing-source
status, and every changed score/count/coverage row. The `.6` source additions change coverage
counts across all 52 races, including races with unchanged leaders. The source registry grows
from 43 to 46 active organizations; legislative eligibility rules and scoring do not change.

All **52 races in seven downloaded release consensus reports** (`.1`, `.4`, `.5`, `.6`, `.7`,
`.8`, `.9`) match independent recomputation, and their canonical JSON bytes match the exact tags.
Releases `.2`, `.3`, and `.9` introduce no source-decision changes. The October 3 bar-display
changes and October 12 sparse/unopposed overview changes are separately logged. Calendar-feed,
monitoring, preview, validation, version-bookkeeping, and methodology-formatting work have
explicit software-only exclusions in the combined inventory.

## Preservation and candidate verification

[Input bindings](audits/updates-2026-10-16/input-bindings.json) record exact file hashes and prove
the primary ledger, canonical dataset, registry, inventory, and certified results match
`2026-primary.3`; the general inputs match `2026-general.9`. The scoring configuration is also
unchanged. This backfill edits history prose and its publication evidence, not endorsements,
election results, scoring, or historical release assets.

The committed-history regression tests check the missing primary history, the corrected general
dates, the July 19/October 3 baselines, coverage references, and publication timezones. A separate
file-byte comparison verifies preserved inputs. Full repository checks and clean release builds
verify the actual publication pipeline.
The archived primary requires a new immutable release to expose its log; the old `.1`–`.3`
assets must not be overwritten. Publication and deployment receipts belong to #556.
