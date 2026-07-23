# 2026 Primary Source Panel Expansion

Issue #61 evaluated six additional progressive endorsement publishers against the official-source
and independent-governance policy. Panel `wa-2026-primary-default-sources-v2` is the resulting
frozen panel for guide release `2026-primary.2`.

## Evaluation outcome

| Publisher | Outcome | Official evidence boundary |
| --- | --- | --- |
| Seattle Democratic Socialists of America | Included; 1 decision | The official chapter event page identifies Jaelynn Scott as newly endorsed. The chapter's published endorsement procedure establishes member control of endorsements. |
| Tech 4 Housing | Included; 4 decisions | Official Bluesky posts identify Rebecca Saldaña, Kelabe Tewolde, Jaelynn Scott, and Ron Davis. Event promotion without endorsement language was not transcribed. |
| Tech 4 Taxes | Included; 6 race decisions covering 7 candidates | Tech 4 Taxes and its official endorsement index remain the source provenance. While the origin is unavailable, an organization-specific Blue Voter Guide capture preserves eight displayed 2026 primary endorsements; seven candidates across six races match the authoritative Seattle inventory, while Noel Frame's LD 36 Senate race does not. |
| Washington for Peace and Justice | Included; 19 race decisions covering 21 candidates | The official site links the organization's `@wa4pj` Instagram account. Its eight-slide 2026 primary carousel marks vote-for recommendations in green; all green recommendations matching the authoritative Seattle ballot were transcribed, while gray and red entries did not contribute. |
| Washington Community Action Network | Included; 2 decisions | The official 2026 endorsement page names Rebecca Saldaña and Teresa Mosqueda and describes the Leadership Council's interview process. |
| Seattle Gay News Editorial Board | Included; 3 decisions | Official SGN Editorial Board articles 168513, 168554, and 168558 endorse Kelabe Tewolde, Kshama Sawant, and Nilu Jenks. |

All six are separately governed publishers. Tech 4 Housing and Tech 4 Taxes have collaborated on
events, but the audit found no shared publisher or endorsement authority. No overlap group was
added: the existing scoring output continues to disclose category coverage, and a speculative
weighting correction would misstate the evidence.

The Election Cheat Sheet and other aggregators were discovery leads only, except for the documented
temporary Tech 4 Taxes retrieval path above. That exception does not change the named publisher or
its official source URL. The Fuse/Progressive Voters Guide publisher relationship is unchanged, the
King County Republican Party remains out of scope, and the ballot universe is unchanged.

## Version and input identity

| Input | Before | After |
| --- | --- | --- |
| Panel ID | `wa-2026-primary-default-sources` | `wa-2026-primary-default-sources-v2` |
| Panel YAML SHA-256 | `5eb3494d17fff2ef1d87a751581f2dbfd034136c63adcd9c2c7689e0222c1e00` | `fdf04a9a2476ae70600c310411b1a2f9e243e2ff0ab952dd54054567cb50d5c4` |
| Canonical panel hash | — | `f07b6aaa1474419ed8e93d1435b9aed96801ba0bb0cca217c5a6c123e9b7a1c0` |
| Canonical dataset SHA-256 | `02eb2895ca0afa3f1226675d42e5a35bcef9191a60fcc0b2a90ccc9818b7cd27` | `4281d4f2a7d87c29f707b10efffe0f761795ca807dc5adb03b89792fd8f30548` |
| Scoring input hash | `dc0f1192ccf4cd424c714778ddf984ca0dbb3206b528e1b5851e07c70cda26c3` | `8266bd2dec8071d6bf31f240ba2e7be05ef2ea3498e7264e81fb634630b89cb6` |
| Data timestamp | `2026-07-21T15:40:21Z` | `2026-07-23T17:10:00Z` |
| Proposed sources | 42 | 48 |
| Consensus sources | 36 | 42 |
| Represented publications | 35 | 41 |
| Decisions | 486 | 521 |

The before state is commit `9faceeaaf7fe13c7f4d9c5c206db192ecd563321`. Git history, the
content hashes above, and the frozen timestamps make both input sets reconstructable. Release,
publication, and deployment metadata carry the canonical panel hash; the raw YAML hash is retained
here for byte-level audit.

## Deterministic scoring impact

The machine-readable
[`source-panel-impact.json`](../data/releases/wa-2026-primary/source-panel-impact.json)
is generated from the validated before/after consensus reports. It contains every race's exact
winner, support share and points, grade/tie state, coverage counts, and complete warning records;
its SHA-256 is `36c726654f8b0d4aa8b5a90971c4eb9ebeac31db6a410732f9523685b8515979`.

The six-source expansion adds 35 decision records across 21 publication races. Tech 4 Taxes contributes
six race decisions covering seven candidates, and Washington for Peace and Justice contributes 19 race
decisions covering 21 green-marked candidates. Counts below are `explicit / covered / eligible / missing`;
the table lists every winner, grade, or tie-state change.

| Race | Before winner; share; grade; tie; coverage | After winner; share; grade; tie; coverage |
| --- | --- | --- |
| LD 32 Representative 2 | Lauren Davis; `21/34`; B; no; `17/17/30/13` | Lauren Davis; `7/12`; C; no; `18/18/36/18` |
| LD 37 Representative 1 | Sharon Tomiko Santos; `3/5`; B; no; `10/10/30/20` | Sharon Tomiko Santos and Kelabe Tewolde; `1/2`; TIED; yes; `13/13/36/23` |
| LD 43 Senator | Jamie Pedersen; `13/21`; B; no; `21/21/30/9` | Jamie Pedersen; `13/23`; C; no; `23/23/36/13` |
| LD 46 Representative 1 | Gerry Pollet; `9/14`; B; no; `14/15/30/15` | Gerry Pollet; `9/16`; C; no; `16/17/36/19` |
| Supreme Court Justice 3 | Mike Diaz; `19/36`; C; no; `18/18/36/18` | Jaime Michelle Hawk and Mike Diaz; `1/2`; TIED; yes; `19/19/42/23` |
| US House 9 | Adam Smith; `8/9`; A; no; `9/12/36/24` | Adam Smith; `8/11`; B; no; `11/14/42/28` |

The remaining 26 publication races retain the same winner, grade, and tie state. Their exact support
shares, points, coverage counts, and warnings remain available in the machine report. Missing coverage
never enters the denominator, so the one remaining access-restricted source affects coverage signals
but not support shares.

Washington for Peace and Justice creates one new tied result: its Jaime Hawk endorsement turns the
prior narrow Mike Diaz lead in Supreme Court Justice Position 3 into an exact tie. Its dual LD 37
Representative 1 endorsement allocates half a point to each candidate, preserving the tie created by
the other new publishers. Tech 4 Taxes does not change a leader, but its Ron Davis endorsement lowers
Gerry Pollet's LD 46 Representative Position 1 grade from B to C. No other leader changes.

Warning deltas are also deterministic:

- every race retains a `missing_coverage` warning, with its missing count increasing by six minus the
  number of new publishers with a resolved decision in that race;
- LD 37 Representative 1 improves from four to five covered categories, retains its
  `low_category_coverage` warning, and gains a review-backed `low_confidence` warning for the dual
  endorsement;
- LD 37 Representative 2 reaches all six categories and loses its prior
  `low_category_coverage` warning;
- US House 9 gains a review-backed `low_confidence` warning for the dual endorsement; and
- all other warning codes are unchanged. The machine report preserves the exact before/after source
  and review-item IDs as well as the messages summarized here.

To reproduce the after result:

```bash
uv run election-guide release compile data/releases/wa-2026-primary/source-decisions.yaml
uv run election-guide score \
  --computed-at 2026-07-23T17:10:00Z \
  --output-path /tmp/wa-2026-primary-v2-consensus.json
uv run election-guide compare-scores \
  /tmp/wa-2026-primary-v1-consensus.json \
  /tmp/wa-2026-primary-v2-consensus.json
```

The full release command in `docs/RELEASE.md` rebuilds and validates the canonical exports, HTML,
PDF, publication manifests, and release archive as `2026-primary.2`. Production deployment remains
the protected main-branch workflow; the deployed revision is the merge commit, not an artifact
created by this audit.
