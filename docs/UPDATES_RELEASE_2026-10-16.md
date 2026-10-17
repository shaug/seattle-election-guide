# Updates publication — October 16, 2026

Scope: [deployment #553](https://github.com/shaug/seattle-election-guide/issues/553), following
[the approved page changes in #552](https://github.com/shaug/seattle-election-guide/pull/552).
The maintainer explicitly requested merging #552 and deploying it.

`2026-general.9` publishes the broader Updates log, its permanent redirects from Corrections,
and the readable How this works page. The tagline remains “We get it right, eventually.”
The authored log includes new endorsements and every other change to a published aggregate or
position page, including changed counts or shares with an unchanged leading choice.
Its initial backfill accounts for the reviewed general-election endorsement-data changes.
The later [history audit](UPDATES_HISTORY_AUDIT_2026-10-16.md), requested in #556, found missing
presentation changes and two dates based on review or later publication rather than first
publication. That follow-up also supplies the previously absent primary history. The `.9`
publication alone must not be described as a complete history of both guides.

This is a publication change. All **880 source decisions across 45 source blocks** are preserved.
The source registry, source-decision ledger and canonical dataset are byte-identical to the
published `2026-general.8` inputs. No new endorsement interpretation, source eligibility,
scoring, inventory or primary-election change is authorized here.

## Reviewed input bindings

These inputs retain their earlier human approvals recorded in the
[October 16 verification follow-up](GENERAL_VERIFICATION_REMAINING_2026-10-16.md).
The publication preparation independently compares each file against the immutable
`2026-general.8` tag before recording these hashes.

| Input | SHA-256 |
| --- | --- |
| `data/releases/wa-2026-general/source-decisions.yaml` | `1286c04ba2b8c38081f1f77d0d7789bdc95402bf52b955c7d4965625240f9b6e` |
| `data/normalized/wa-2026-general-canonical-dataset.json` | `da873f6755f0b83a82e1a5c5a00acbc3ed576dd52035aed65e76d5a6e241cd7c` |
| `config/sources/wa-2026-general.yaml` | `b768ab12d366d345a7886c8dc3a61438ff2cc33a52042b49cf5eb7c505e7dd0f` |

The earlier `2026-general.8` release stays at
`a1a83b5f1c09d7297a6100e3ac321b0e5034bf52`, with one canonical ZIP whose SHA-256 is
`d1e7d9edc9b98f4ecfe1adaacaa963cced1a85f185b4c8705543c7d2444f1f56`.
Every historical release asset and the primary declaration remain intact.

## Publication evidence

Use the existing [release procedure](RELEASE.md) and [production probe](HOSTING.md#publication-day-production-probe).
The deployment issue retains the exact merged release candidate, release asset and digest,
production candidate, lineage report, CI run and artifact, deployment ID, and two successful
strict production probes. Preparation of this record does not itself claim publication or
production success.
