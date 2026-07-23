# 2026 Primary Source Panel Expansion

Issue #61 evaluated six additional progressive endorsement publishers against the official-source
and independent-governance policy. Panel `wa-2026-primary-default-sources-v2` is the resulting
frozen panel for guide release `2026-primary.2`.

## Evaluation outcome

| Publisher | Outcome | Official evidence boundary |
| --- | --- | --- |
| Seattle Democratic Socialists of America | Included; 1 decision | The official chapter event page identifies Jaelynn Scott as newly endorsed. The chapter's published endorsement procedure establishes member control of endorsements. |
| Tech 4 Housing | Included; 4 decisions | Official Bluesky posts identify Rebecca Saldaña, Kelabe Tewolde, Jaelynn Scott, and Ron Davis. Event promotion without endorsement language was not transcribed. |
| Tech 4 Taxes | Included as an access-restricted coverage gap; 0 decisions | The organization owns a 2025-2026 endorsement index, but repeated direct origin, browser, and IPv4 requests timed out. Search-result text was used only for discovery, and the official Bluesky feed did not reproduce the list. |
| Washington for Peace and Justice | Included as an access-restricted coverage gap; 0 decisions | The official site links the organization's Instagram account. Search results indicated a 2026 guide, but the account could not be retrieved without an authenticated session; that indication and third-party text remained discovery leads only. |
| Washington Community Action Network | Included; 2 decisions | The official 2026 endorsement page names Rebecca Saldaña and Teresa Mosqueda and describes the Leadership Council's interview process. |
| Seattle Gay News Editorial Board | Included; 3 decisions | Official SGN Editorial Board articles 168513, 168554, and 168558 endorse Kelabe Tewolde, Kshama Sawant, and Nilu Jenks. |

All six are separately governed publishers. Tech 4 Housing and Tech 4 Taxes have collaborated on
events, but the audit found no shared publisher or endorsement authority. No overlap group was
added: the existing scoring output continues to disclose category coverage, and a speculative
weighting correction would misstate the evidence.

The Election Cheat Sheet and other aggregators were discovery leads only. The Fuse/Progressive
Voters Guide publisher relationship is unchanged, the King County Republican Party remains out of
scope, and the ballot universe is unchanged.

## Version and input identity

| Input | Before | After |
| --- | --- | --- |
| Panel ID | `wa-2026-primary-default-sources` | `wa-2026-primary-default-sources-v2` |
| Panel YAML SHA-256 | `5eb3494d17fff2ef1d87a751581f2dbfd034136c63adcd9c2c7689e0222c1e00` | `53a77eabb99e4e461daedfa2aa65345ff4bdff8b31aaf9469715a77fa3b87fd0` |
| Canonical panel hash | — | `0e700942a28f0a04e5f8e19fc8a9335b8e7065d7af3323b3676cf59d9d8d5953` |
| Canonical dataset SHA-256 | `02eb2895ca0afa3f1226675d42e5a35bcef9191a60fcc0b2a90ccc9818b7cd27` | `b9bfaf4a00bebbeef661dde2e6144342aa78762d3abb74ca99a0029d059ca363` |
| Scoring input hash | `dc0f1192ccf4cd424c714778ddf984ca0dbb3206b528e1b5851e07c70cda26c3` | `8a1c582f8ea16b90f73b252e7687f27ea7604468286b2728728186486011c2c1` |
| Data timestamp | `2026-07-21T15:40:21Z` | `2026-07-23T13:01:14Z` |
| Proposed sources | 42 | 48 |
| Consensus sources | 36 | 42 |
| Represented publications | 35 | 39 |
| Decisions | 486 | 496 |

The before state is commit `9faceeaaf7fe13c7f4d9c5c206db192ecd563321`. Git history, the
content hashes above, and the frozen timestamps make both input sets reconstructable. Release,
publication, and deployment metadata carry the canonical panel hash; the raw YAML hash is retained
here for byte-level audit.

## Deterministic scoring impact

The machine-readable
[`source-panel-impact.json`](../data/releases/wa-2026-primary/source-panel-impact.json)
is generated from the validated before/after consensus reports. It contains every race's exact
winner, support share and points, grade/tie state, coverage counts, and complete warning records;
its SHA-256 is `b6d0d9aa91fcd0512905f43182724ab0461d22a77c8c5e0d4f58f01d78bf7371`.

The following are the races that received a new explicit decision. Counts are
`explicit / covered / eligible / missing`.

| Race | Before winner; share; grade; tie; coverage | After winner; share; grade; tie; coverage |
| --- | --- | --- |
| King County Council 2 | Rebecca Saldaña; `7/8`; A; no; `20/20/36/16` | Rebecca Saldaña; `39/44`; A; no; `22/22/42/20` |
| King County Council 8 | Teresa Mosqueda; `1`; A+; no; `21/21/36/15` | Teresa Mosqueda; `1`; A+; no; `22/22/42/20` |
| LD 37 Representative 1 | Sharon Tomiko Santos; `3/5`; B; no; `10/10/30/20` | Sharon Tomiko Santos and Kelabe Tewolde; `1/2`; TIED; yes; `12/12/36/24` |
| LD 37 Representative 2 | Jaelynn Scott; `1`; A+; no; `16/16/30/14` | Jaelynn Scott; `1`; A+; no; `18/18/36/18` |
| LD 46 Representative 1 | Gerry Pollet; `9/14`; B; no; `14/15/30/15` | Gerry Pollet; `3/5`; B; no; `15/16/36/20` |
| Seattle City Council 5 | Nilu Jenks; `37/40`; A+; no; `20/20/36/16` | Nilu Jenks; `13/14`; A+; no; `21/21/42/21` |
| US House 9 | Adam Smith; `8/9`; A; no; `9/12/36/24` | Adam Smith; `4/5`; A; no; `10/13/42/29` |

The remaining 25 publication races retain the same winner, support points/share, grade, tie state,
explicit count, and covered count. Their eligible and missing counts each increase by six because
all six new publishers are panel-eligible while none published a decision in those races.

The only winner/grade-state change is LD 37 Representative 1: two new Kelabe Tewolde endorsements
change the prior Sharon Tomiko Santos lead into an exact tie. Missing coverage never enters the
denominator, so the two access-restricted sources affect coverage signals but not support shares.

Warning deltas are also deterministic:

- every race retains a `missing_coverage` warning, with its missing count increasing by six minus
  the number of new decisions in that race;
- LD 37 Representative 1 improves from four to five covered categories, while retaining its
  `low_category_coverage` warning;
- LD 37 Representative 2 reaches all six categories and loses its prior
  `low_category_coverage` warning; and
- all other warning codes and messages are unchanged. The machine report preserves the exact
  before/after source and review-item IDs as well as the messages summarized here.

To reproduce the after result:

```bash
uv run election-guide release compile data/releases/wa-2026-primary/source-decisions.yaml
uv run election-guide score \
  --computed-at 2026-07-23T13:01:14Z \
  --output-path /tmp/wa-2026-primary-v2-consensus.json
uv run election-guide compare-scores \
  /tmp/wa-2026-primary-v1-consensus.json \
  /tmp/wa-2026-primary-v2-consensus.json
```

The full release command in `docs/RELEASE.md` rebuilds and validates the canonical exports, HTML,
PDF, publication manifests, and release archive as `2026-primary.2`. Production deployment remains
the protected main-branch workflow; the deployed revision is the merge commit, not an artifact
created by this audit.
