# Primary meter rollback delivery record

Scope: [#598](https://github.com/shaug/seattle-election-guide/issues/598).
Scott directly approved the exact pre-#605 two-CSS restoration on October 24,
2026, including rebuilding the primary overview, with current data and
interactions preserved and no redesign. See the
[approved design](superpowers/specs/2026-10-23-meter-renderer-rollback-design.md)
and [remaining plan](superpowers/plans/2026-10-23-meter-renderer-rollback.md).

## Accepted preparation baseline

The controller has accepted general `2026-general.36` production from
`e85f694f9a3fedfd96a7707a12bd8279ed5d93d7`, tree
`fcfb9c9af2c2c719893d5a3f3adc3293dd1a741a`. Current inputs contain 929 general
and 538 primary decisions.

| Protected input | SHA-256 |
| --- | --- |
| General dataset | `7d209c8cee87155e386e8a35a17aee26e965ab27c1a726e1bb58f8018b7f517a` |
| General ledger | `cd2e9e777fb2218d463164af7e43ba8e2e940291f90a6ea0309d051d4eded39a` |
| Primary dataset | `327235fb6a5d95330970d87df2bed338e0b667ff984d7e9ada348e78fc6459d9` |
| Primary ledger | `b039e3d96cd61d6219ef7bb3ae493a955a2bf7aa54be60ff2ee45f5a7112a0b2` |

The selected immutable primary remains `2026-primary.6`:

- Source: `c27e432d9bc477289d54ee9136746845a92696d0`
- Release manifest: `701c956310cad5e5374a291beb2cd54389a5f15087fc40a40c3a6707345c594d`
- Bundle: `daa492dc72d526de6178281292ef660a8b3885a7194cbcd8e7d51fb9b450ea07`

These primary pins remain unchanged. Stage A finalization prepares only the
current-general request in `config/hosting/site.yaml`. The [earlier refresh record](PRIMARY_METER_REFRESH_2026-10-22.md)
remains historical. Every old Updates entry and immutable release is preserved.

## Prepared content and local request; protected delivery pending

Stage A content and the local current-general request are prepared: the public
spec and plan, this record, one primary Updates preparation entry dated
`2026-10-24`, and the normally prepared `2026-general.37` request for #598. It describes planned
restoration on race pages and the overview without claiming deployment. That
source entry is **unserved** until the first new archive is selected in Stage B;
the current primary overview and Updates still come from `.6`.

| Step | Status and required evidence |
| --- | --- |
| A | Content and local current-general request prepared on accepted M11; fresh gates, canonical review, protected CI, merge and independent automatic-release/production acceptance are required before acceptance. |
| Archive 1 | Pending exact accepted A merged SHA; two matching builds, inspection, immutable publication, download and identity verification. |
| B | Pending protected restoration and verified archive 1 activation, followed by independent production acceptance. |
| Archive 2 | Pending exact accepted B merged SHA; two matching builds containing the restored overview, inspection, immutable publication, download and identity verification. |
| C | Pending protected archive 2 activation and final independent production and visual acceptance. |

The final Stage A comparison base is accepted M11
`e85f694f9a3fedfd96a7707a12bd8279ed5d93d7` / `2026-general.36` / 929 general
decisions. No new versions have been reserved. Actual final source identities,
artifacts, receipts, probes and visual acceptance will be added only after
verification.

Final source entry dates must reflect actual Pacific publication dates. If dates
change, reconcile through protected source updates while preserving immutable
history. Each final candidate requires fresh full gates, canonical review,
protected CI and independent production evidence. #598 stays open until Stage C
production and visual acceptance; no visual fix or deployment is claimed here.
