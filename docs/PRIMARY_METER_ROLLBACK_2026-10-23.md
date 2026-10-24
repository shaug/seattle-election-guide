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

## Stage B candidate; protected delivery pending

Stage B restores only the two approved CSS files to their exact bytes at
`bea5e4edc5c50c985932b8ae5e123a39a0b51449`, transfers the two focused browser-test
functions while preserving the other 140 and #602 diagnostics, and selects only
the actual downloaded archive 1 pins. The normal automation prepared the local
`2026-general.38` request for #598 against the accepted Stage A source.
Preparation publishes or reserves no version.

New general and primary source Updates entries are dated October 24, 2026.
At Stage B delivery the general guide and general/primary race pages receive
the restored CSS. The served primary Updates come from archive 1 and include
Stage A's preparation entry. The new primary Stage B source entry is retained
for archive 2 and is **unserved at B**. The copied primary overview still comes
from archive 1 and **does not yet contain the restoration**.

| Step | Status and remaining evidence |
| --- | --- |
| A | Accepted at `2307f1d8b8e79e30799a27ab91b7501382e78430` / `2026-general.37` with independent release and production evidence above. |
| Archive 1 | Accepted published `2026-primary.7` from exact accepted A; actual downloaded pins above selected by the B candidate. |
| B | Local restoration, Updates and normal current-general request prepared; exact candidate gates, canonical review, protected CI, merge and independent production acceptance precede delivery. |
| Archive 2 | Pending exact accepted B merged SHA; two matching builds containing the restored overview, inspection, immutable publication, download and identity verification. |
| C | Pending protected archive 2 activation and final independent production and visual acceptance. |

Final source entry dates must reflect actual Pacific publication dates. If dates
change, reconcile through protected source updates while preserving immutable
history. Each final candidate requires fresh full gates, canonical review,
protected CI and independent production evidence. #598 stays open until Stage C
production and visual acceptance. Stage B delivery, archive 2, final overview
activation and overall visual completion are not claimed here.
