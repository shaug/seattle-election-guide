# Primary meter rollback delivery record

Scope: [#598](https://github.com/shaug/seattle-election-guide/issues/598).
Scott directly approved the exact pre-#605 two-CSS restoration on October 24,
2026, including rebuilding the primary overview, with current data and
interactions preserved and no redesign. See the
[approved design](superpowers/specs/2026-10-23-meter-renderer-rollback-design.md)
and [remaining plan](superpowers/plans/2026-10-23-meter-renderer-rollback.md).

## Preserved inputs and history

The accepted Stage B comparison base is Stage A merged source
`2307f1d8b8e79e30799a27ab91b7501382e78430`, tree
`35cc809f1d1effc4e243e5e1fe08ddc497e5c08d`, published as `2026-general.37`.
Inputs remain 929 general and 538 primary decisions.

| Protected input | SHA-256 |
| --- | --- |
| General dataset | `7d209c8cee87155e386e8a35a17aee26e965ab27c1a726e1bb58f8018b7f517a` |
| General ledger | `cd2e9e777fb2218d463164af7e43ba8e2e940291f90a6ea0309d051d4eded39a` |
| Primary dataset | `327235fb6a5d95330970d87df2bed338e0b667ff984d7e9ada348e78fc6459d9` |
| Primary ledger | `b039e3d96cd61d6219ef7bb3ae493a955a2bf7aa54be60ff2ee45f5a7112a0b2` |

Every earlier Updates entry and immutable release remains historical. The
[earlier refresh record](PRIMARY_METER_REFRESH_2026-10-22.md) is unchanged.
No endorsement, result, source membership, allocation, color, dimension or
interaction change is part of this rollback.

## Accepted Stage A and archive 1

[PR #618](https://github.com/shaug/seattle-election-guide/pull/618)
merged Stage A. Its [automatic delivery run](https://github.com/shaug/seattle-election-guide/actions/runs/40120238698/attempts/2)
passed all 13 native jobs. Independent acceptance verified the published
archive, durable publication/upload receipts, both complete strict production
probe pairs, both elections and served Updates. Production deployment
`7303252059` serves the exact accepted Stage A source.

| Stage A identity | Verified value |
| --- | --- |
| General release / asset IDs | `422929187` / `673077725` |
| Published ZIP SHA-256 | `a4a2505815583b3cf77628fdb2ba8d6d04df42e97bf7e2d5a87478a823e9ef1b` |
| Release manifest SHA-256 | `9361e7c59ecbf3b093a6d01bba13adf6b29b74e3e26c843b12b0bcea0fbac936` |
| Bundle SHA-256 | `00239d03d9dc6f4aa17a53add70888811974b4855488d1dcf17a3dd75c0ea050` |
| Deployment manifest SHA-256 | `d8f5ade62431e85e51376b1f1639474deac9d8a9a4208663832442deb794e35c` |
| Acceptance record SHA-256 | `95eb0d46e42bc9a5061d842bf0c81d23af5e72237be195ef7f2628d1b5f7bf47` |

Archive 1, [2026-primary.7](https://github.com/shaug/seattle-election-guide/releases/tag/2026-primary.7),
was built twice from that exact clean accepted source, compared, inspected,
published, downloaded and independently accepted on October 24, 2026. The actual
draft and public asset downloads matched the reviewed build. All 538 primary
records and IDs, five CSV exports, results, source membership, all 33 old Updates
entries and the new preparation entry were verified. All 42 prior release, tag
and asset identities and the existing latest-release pointer were preserved.

| Archive 1 identity | Verified value |
| --- | --- |
| Source | `2307f1d8b8e79e30799a27ab91b7501382e78430` |
| Release / asset IDs | `422936879` / `673113976` |
| Published ZIP SHA-256 / bytes | `58c48583ef22ab25f4d34e5c70abababa713e00c587a015f5005c849bdccc3ff` / `536921` |
| Release manifest SHA-256 | `d2b91f622a4fe1bc9daaf372a0cae2ca9d0e74866b6a169daa7cf487d1ea56ee` |
| Bundle SHA-256 | `3da22b96f25cf8eeeee942b7e284821ed09b56b25edbf1fde05675975c41d203` |
| Acceptance record SHA-256 | `0d427593fcdba5dcaaad9b146068c766f44286d8326f5186df2abc71eed08832` |

Stage A's first CI attempt retained two Chrome startup failures before page
execution. The supported recovery passed at the unchanged source in attempt 2;
the original startup cause remains unknown.

## Accepted Stage B and archive 2; Stage C prepared

Stage B restored only the two approved CSS files to their exact bytes at
`bea5e4edc5c50c985932b8ae5e123a39a0b51449`, transferred the two focused browser-test
functions while preserving the other 140 and #602 diagnostics, and selected only
the actual downloaded archive 1 pins. The normal automation prepared the local
`2026-general.38` request for #598 against the accepted Stage A source.
Preparation publishes or reserves no version. Stage B refreshed the four existing hosting-test identity literals to archive 1;
Stage C refreshes those same four to the verified archive 2 values. Every
deployment assertion and gate remains in place.

The general and primary source Updates entries are dated October 24, 2026.
At Stage B delivery the general guide and general/primary race pages received
the restored CSS. The served primary Updates come from archive 1 and include
Stage A's preparation entry. The primary Stage B source entry was retained
for archive 2 and is **unserved at B**. At B the copied primary overview came
from archive 1 and **did not yet contain the restoration**.

| Step | Status and remaining evidence |
| --- | --- |
| A | Accepted at `2307f1d8b8e79e30799a27ab91b7501382e78430` / `2026-general.37` with independent release and production evidence above. |
| Archive 1 | Accepted published `2026-primary.7` from exact accepted A; actual downloaded pins above selected by Stage B. |
| B | Accepted [PR #621](https://github.com/shaug/seattle-election-guide/pull/621), merged source `095bf8a5acd71146d6286d24197d032fb0d68e90` / `2026-general.38`; all 13 jobs in [automatic delivery](https://github.com/shaug/seattle-election-guide/actions/runs/40135078226/attempts/1), durable receipts, both strict production probe pairs, both elections and served Updates independently accepted. |
| Archive 2 | Accepted published [2026-primary.8](https://github.com/shaug/seattle-election-guide/releases/tag/2026-primary.8) from exact accepted B on October 24, 2026; two matching builds, restored overview inspection, actual public download and identity verification complete. All 538 primary records and IDs, results, exports, source membership and 34 earlier Updates entries preserved. |
| C | Only the actual downloaded archive 2 pins are selected; normal automation prepared `2026-general.39` for #598 against exact accepted B. Preparation publishes or reserves no version. Fresh candidate gates, reviews, protected CI, merge and final independent production and visual acceptance remain pending. |

Final source entry dates must reflect actual Pacific publication dates. If dates
change, reconcile through protected source updates while preserving immutable
history. Each final candidate requires fresh full gates, canonical review,
protected CI and independent production evidence. #598 stays open until Stage C
production and visual acceptance. Final overview activation and overall visual
completion remain pending Stage C delivery.
Stage B was published October 24, 2026 (Pacific); archive 2 was published at
`2026-10-24T22:26:20Z`, also October 24 Pacific. Source Updates dates therefore
remain exact. Archive 2 serves all 35 primary entries, including the Stage B
entry and its separate-overview-step description and guide link; that entry was
**unserved at B**. This protected C activation selects the rebuilt overview
without rewriting historical Updates entries.

| Archive 2 identity | Verified value |
| --- | --- |
| Source | `095bf8a5acd71146d6286d24197d032fb0d68e90` |
| Release / asset IDs | `423015918` / `673466707` |
| Published ZIP SHA-256 / bytes | `fd161ab8e4fd877fba131b7447898e4f79f46de59399cd7d10a6d3dbc5de6f4d` / `536338` |
| Release manifest SHA-256 | `a661c19f43d9f9ae758b08d69ee79d88eb9c594c3ac1fa1ef9b4b098d201207b` |
| Bundle SHA-256 | `a5eeb309d85ef474c752638a3dc72beab5a813e2ac6da87efb69f6b13e9cec8d` |
| Acceptance record SHA-256 | `7cd4786b01d01482d656d217c4794ca80b340496fa6ffc57c1e744628c614abb` |
