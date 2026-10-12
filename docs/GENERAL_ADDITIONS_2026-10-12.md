# General-election additions — October 12, 2026

Scope: [issue #509](https://github.com/shaug/seattle-election-guide/issues/509), with the Tech 4 Taxes follow-up from [issue #508](https://github.com/shaug/seattle-election-guide/issues/508). The maintainer directed: “let’s add that tech4taxes gap, and update the guide with the new decisions.” This begins production admission after the [merged evidence assessment](https://github.com/shaug/seattle-election-guide/pull/515); it is not a continuation of the earlier frozen-panel refresh.

The update adds **22 decisions**: Young Democrats of Washington 16, Nondriver Action four, Citizens Against AIPAC Corruption one, and Tech 4 Taxes No on Initiative 645. The first 21 retain the immutable human-verified records and exact published choice sets in the [assessment](../data/review/source-assessments/wa-2026-general-20261011/assessment.md). Three Young Democrats co-endorsements each contribute one total point split equally between the two candidates. The current request authorizes their production admission and the specific Tech 4 Taxes mapping.

## Admission decisions, made before changed-panel consensus was inspected

| Publisher | Reporting / selection categories | Eligibility and attribution |
|---|---|---|
| Young Democrats of Washington (`ydwa`) | Democratic Party | One statewide party youth organization; only reviewed explicit Seattle-ballot decisions. Shared Democratic Party affiliation is disclosed, without assuming duplicate endorsement governance. |
| Nondriver Action (`nact`) | Transportation/urbanism; also selectable under rights/representation | One publisher of its November slate. Reciprocal Nondrivers Alliance affiliation, 501(c)(4) identity, and historical DMI roots are disclosed in an overlap record. DMI remains excluded. This is not a finding of independent legal or voting governance. |
| Citizens Against AIPAC Corruption (`caac`) | Rights/representation | Classification follows its explicit Palestinian-rights criteria. Track AIPAC is its project, not a second source. Its geographic eligibility is general; current publication coverage is federal. Admit only directly published, reviewed Seattle-intersecting congressional decisions; only Jayapal is verified here. Do not infer state/local decisions. |

The general panel becomes `wa-2026-general-default-sources-v2`. Its original freeze timestamps and initial compatibility anchor remain historical facts. The original v1 snapshot is preserved, and a successor is appended so historical membership remains reconstructable. Existing explicit source selections retain their source identities. Category tokens continue to follow current category membership under the existing migration contract, with the visible earlier-version notice; this update does not freeze historical category membership in a live lens. Primary-panel membership and all primary publication inputs remain unchanged. Existing category meanings, scoring weights, grade thresholds, and equal-split policy remain unchanged. King County GOP and PVG are not admitted by this update.

## Tech 4 Taxes: specific human-reviewed ballot mapping

The [official legislative agenda](https://tech4taxes.org/legagenda) labels “Millionaire’s Income Tax (SB6346)” **PRO**. It does not publish the words “Vote No on 645.” The [official voters’ guide](https://voter.votewa.gov/genericvoterguide.aspx?c=99&e=899&language=en#/measure/7325), Information and Explanatory Statement tabs, identifies the income-tax repeal and explains that approval repeals the annual tax on individual income over $1,000,000.

After this distinction was presented, the maintainer explicitly directed adding the gap. The approved mapping is **prior value: absent; new value: No on Initiative IP26-645**. The source’s actual PRO wording is preserved; No is a human-approved interpretation, not an invented source quotation. The approval record identifies the author, timestamp, original captures, official measure mapping, and manual record. This case does not authorize automated policy-to-ballot inference or importing other unresolved comparator claims.

## Publication scope

Only the 22 approved decisions are added. All 681 existing source/race choice sets, abstentions, and allocations are retained. The general inventory and the archived primary remain unchanged. Urbanist, WA4PJ, Stonewall, DSA initiative positions, and inaccessible additional Times decisions remain unresolved.

The immutable publication is `2026-general.6`. The reviewed input hashes below bind the publication inputs. Final release and deployment identities are retained in the operator receipt and independently checked before completion. No changed-panel consensus outcome is used to select sources, categories, eligibility, or interpretation.

## Reviewed input bindings

| Input | SHA-256 |
|---|---|
| `data/releases/wa-2026-general/source-decisions.yaml` | `60909b45fee3b5dc06e1f98ecedbef84c8cd076f36f14ccedb566ca284964be0` |
| `data/normalized/wa-2026-general-canonical-dataset.json` | `c626a4b629a9ea9443395bcb126955f03c367f8c7225e2a0b154a1dec6d91b13` |
| `config/sources/wa-2026-general.yaml` | `216e0b2643f6f563c10f3e0a8b5ca0524f6233e6ca290f31833bd84707d08a86` |

The release and production commit identities differ only under the existing post-tag lineage gate. Publication receipts are retained by the operator; final metadata and live deployment must be independently verified.
