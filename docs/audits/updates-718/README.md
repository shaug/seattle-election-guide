# Results-only Updates correction (#718)

The generator compared source clocks, reporting metadata and complete original-byte identities,
then called every affected contest a results change. A source recheck could therefore create a
full public Update without changing a single tally. Scott requested a results-only rule.

The audit in `classification.json` binds the five published automatic records to their original
creation commits and parents, complete before/after tally projections, results-file SHA256s and
original prose. `original-wa-2026-general.yaml` retains the entire General94 authored log, including
every original field and published slug. These are historical observations, not fresh source reads.

| Original publication (Pacific) | Actually changed contests | Disposition |
| --- | ---: | --- |
| November 6, 23:21:55 | 52 | Retain; describe actual counts |
| November 7, 05:22:26 | 0 | Remove no-change card; redirect to preceding count update |
| November 7, 16:43:49 | 52 | Retain; describe actual counts |
| November 7, 18:25:32 | 8 | Retain; correct original claim of 52 affected contests |
| November 7, 20:23:13 | 0 | Remove no-change card; redirect to preceding count update |

The two removed entries had no changes to named-choice votes, write-ins or contest totals.
Their old public URLs remain permanent aliases via the existing `redirect_from` mechanism;
they identify the preceding substantive result record, rather than inventing a new event.
The other three canonical URLs and all earlier election information remain intact. Accepted
release archives, original results captures and immutable source manifests are unchanged.

Prospectively, metadata-only refreshes still retain and validate evidence and refresh status.
They do not generate an Updates entry. Real increases, decreases, redistributed votes,
write-ins and distinct contest ballots/vote totals do. Choice ordering is immaterial.

The release gate adopts snapshot policy6.0 for this distinction. Its older policies remain
readable and verifiable under their original rules; upgrading a live baseline requires the
exact authenticated deployed artifact. Full assets remain hash-verified. Only recognized
unofficial-result clocks, recency and properly scoped original-evidence identities cease to
force a filler entry. Certification, counts, authority and unrelated election facts still do.
