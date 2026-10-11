# October 10, 2026 general endorsement reconciliation — pending human verification

Scope: [#508](https://github.com/shaug/seattle-election-guide/issues/508). Prepared by OpenAI Codex from the electioncheatsheet.org audit, then checked against the official publications captured below. This is a targeted correction packet; the comprehensive October 15 sweep in [#491](https://github.com/shaug/seattle-election-guide/issues/491) remains open.

**Review status: pending.** The 64 additions and one changed decision below have not been applied to the release ledger or canonical dataset. Human verification must cover the new transcriptions and explicit label mappings before application. If all are verified, the decision count becomes 681 (617 + 64); updating the existing Davis decision does not add another record. Two new published source blocks bring coverage from 34 to 36.

The proposal is [structured data](../data/review/proposals/wa-2026-general-2026-10-10.json), bound to the baseline input hashes below. It contains 15 pending manual-entry records and 19 new capture records: eight static official pages, a supplemental Stranger record with the observed October 9 publication date and identical artifact bytes, nine official images, and one manually saved browser DOM table excerpt. The WFP excerpt normalizes intertag whitespace, covers the displayed Washington table, and asserts no browser HTTP status. Restricted artifact bytes live in the primary checkout’s durable ignored data/snapshots store, outside the linked implementation worktree. All proposal evidence is hash-verified there.

The structured proposal also includes eight discovery updates with prior and proposed values, including the newer official Tech 4 Housing page and expanded WFP index. These updates validate against the registry model and preserve the stable panel hash `b0fb2a603bd98da49d3282d2daa0cb55ff56e0bbdd46104c8b5a4a441b747a95`; apply them together with the verified ledger changes.

Source membership, eligibility, roles, weighting, official ballot inventory, and grade rules retain their existing contracts. Keep verified PROTEC17’s Ryu, Noble and Macri endorsements, SEIU 925’s Noble endorsement, and the 11th / 37th / 43rd District Democrats’ explicit US House 9 no-endorsement decisions. Their absence from the comparator is not evidence for deleting them.

## Review summary

| Official source | Additions | Changed decisions |
| --- | ---: | ---: |
| [The Stranger Election Control Board](https://www.thestranger.com/news/the-stranger-election-control-board-2026-general-election-cheat-sheet/) | 31 | 0 |
| [Tech 4 Housing](https://www.tech4housing.org/endorsements) | 10 | 0 |
| [Tech 4 Taxes](https://tech4taxes.org/endorsements) | 4 | 0 |
| [King County Democrats](https://www.kcdems.org/our-party/e/2026-endorsements/) | 3 | 1 |
| [The Washington Bus](https://www.washingtonbus.org/endorsements) | 7 | 0 |
| [Washington Working Families Party](https://workingfamilies.org/candidates/) | 5 | 0 |
| [OneAmerica Votes](https://oavotes.org/our-work/endorsements/2026-endorsements/) | 2 | 0 |
| [Washington Community Action Network](https://www.washingtoncan.org/endorsements) | 2 | 0 |

## Explicit source-label mappings for confirmation

These proposed mappings use unique identities in the frozen official ballot. They remain pending; no corrected race has been silently published.

| Source | Original label | Proposed ballot match | Reason |
| --- | --- | --- | --- |
| The Stranger Election Control Board | Jamie Michelle Hawk | Jaime Michelle Hawk | Supreme Court Position 3 and unique ballot identity resolve the source spelling. Human must confirm this explicit alias treatment. |
| King County Democrats | Ballot Measure IL26-645 - OPPOSE | Initiative IP26-645 - No | The heading mistypes IL, but the Vote NO on IP26-645 link and Millionaires Tax description identify the measure. Human must confirm this mapping. |
| King County Democrats | Gerry Pollet, LD 46 Representative Pos. 2 | Gerry Pollet, LD46 Representative Position 1 | The source separately lists Farivar for Position 2. Pollet appears only in Position 1 in the frozen ballot. Human must confirm the source position typo before publication. |
| The Washington Bus | Kelabe Tewolde, Legislative District No. 37, State Representative, Pos. 2 | Kelabe Tewolde, LD37 Representative Position 1 | The two LD37 House image labels are swapped. Frozen ballot uniquely places Tewolde in Position 1. Human must confirm the corrected race match. |
| The Washington Bus | Jaelynn Scott, Legislative District No. 37, State Representative, Pos. 1 | Jaelynn Scott, LD37 Representative Position 2 | The two LD37 House image labels are swapped. Frozen ballot uniquely places Scott in Position 2. Human must confirm the corrected race match. |

## Every proposed decision

In each section, the capture and pending manual-entry IDs are the immutable audit references. A dual choice is one decision; the allocation column is the point assigned to each named choice.

### The Stranger Election Control Board

New October 9 general publication, after the October 3 check. All 31 contested Seattle-inventory choices have been transcribed. Jaime Hawk spelling is surfaced below.

| Race | Proposed choice(s) | Change | Allocation each | Evidence |
| --- | --- | --- | --- | --- |
| Initiative IP26-645 — State and Local Taxes | No | Add | 1 | [Official evidence](https://www.thestranger.com/news/the-stranger-election-control-board-2026-general-election-cheat-sheet/) |
| Initiative IL26-001 — Parental Rights in Public Schools | No | Add | 1 | [Official evidence](https://www.thestranger.com/news/the-stranger-election-control-board-2026-general-election-cheat-sheet/) |
| Initiative IL26-638 — Participation in K-12 School Athletics | No | Add | 1 | [Official evidence](https://www.thestranger.com/news/the-stranger-election-control-board-2026-general-election-cheat-sheet/) |
| U.S. Representative — Congressional District 7 | Pramila Jayapal | Add | 1 | [Official evidence](https://www.thestranger.com/news/the-stranger-election-control-board-2026-general-election-cheat-sheet/) |
| U.S. Representative — Congressional District 9 | Adam Smith | Add | 1 | [Official evidence](https://www.thestranger.com/news/the-stranger-election-control-board-2026-general-election-cheat-sheet/) |
| Legislative District 11 State Representative — Position 1 | Ashley Fedan | Add | 1 | [Official evidence](https://www.thestranger.com/news/the-stranger-election-control-board-2026-general-election-cheat-sheet/) |
| Legislative District 32 State Senator | Cindy Ryu | Add | 1 | [Official evidence](https://www.thestranger.com/news/the-stranger-election-control-board-2026-general-election-cheat-sheet/) |
| Legislative District 32 State Representative — Position 1 | Keith Scully | Add | 1 | [Official evidence](https://www.thestranger.com/news/the-stranger-election-control-board-2026-general-election-cheat-sheet/) |
| Legislative District 32 State Representative — Position 2 | Imraan Siddiqi | Add | 1 | [Official evidence](https://www.thestranger.com/news/the-stranger-election-control-board-2026-general-election-cheat-sheet/) |
| Legislative District 34 State Representative — Position 2 | Joe Fitzgibbon | Add | 1 | [Official evidence](https://www.thestranger.com/news/the-stranger-election-control-board-2026-general-election-cheat-sheet/) |
| Legislative District 36 State Senator | Noel C. Frame | Add | 1 | [Official evidence](https://www.thestranger.com/news/the-stranger-election-control-board-2026-general-election-cheat-sheet/) |
| Legislative District 37 State Senator | Chipalo Street | Add | 1 | [Official evidence](https://www.thestranger.com/news/the-stranger-election-control-board-2026-general-election-cheat-sheet/) |
| Legislative District 37 State Representative — Position 1 | Kelabe Tewolde | Add | 1 | [Official evidence](https://www.thestranger.com/news/the-stranger-election-control-board-2026-general-election-cheat-sheet/) |
| Legislative District 37 State Representative — Position 2 | Jaelynn Scott | Add | 1 | [Official evidence](https://www.thestranger.com/news/the-stranger-election-control-board-2026-general-election-cheat-sheet/) |
| Legislative District 43 State Senator | Jamie Pedersen | Add | 1 | [Official evidence](https://www.thestranger.com/news/the-stranger-election-control-board-2026-general-election-cheat-sheet/) |
| Legislative District 43 State Representative — Position 1 | Nicole Macri | Add | 1 | [Official evidence](https://www.thestranger.com/news/the-stranger-election-control-board-2026-general-election-cheat-sheet/) |
| Legislative District 46 State Senator | Javier Valdez | Add | 1 | [Official evidence](https://www.thestranger.com/news/the-stranger-election-control-board-2026-general-election-cheat-sheet/) |
| Legislative District 46 State Representative — Position 1 | Will Dreher | Add | 1 | [Official evidence](https://www.thestranger.com/news/the-stranger-election-control-board-2026-general-election-cheat-sheet/) |
| Legislative District 46 State Representative — Position 2 | Darya Farivar | Add | 1 | [Official evidence](https://www.thestranger.com/news/the-stranger-election-control-board-2026-general-election-cheat-sheet/) |
| King County Assessor | Rob Foxcurran | Add | 1 | [Official evidence](https://www.thestranger.com/news/the-stranger-election-control-board-2026-general-election-cheat-sheet/) |
| Metropolitan King County Council — District 2 | Rebecca Saldaña | Add | 1 | [Official evidence](https://www.thestranger.com/news/the-stranger-election-control-board-2026-general-election-cheat-sheet/) |
| Metropolitan King County Council — District 8 | Teresa Mosqueda | Add | 1 | [Official evidence](https://www.thestranger.com/news/the-stranger-election-control-board-2026-general-election-cheat-sheet/) |
| Washington Supreme Court Justice — Position 1 | Colleen Melody | Add | 1 | [Official evidence](https://www.thestranger.com/news/the-stranger-election-control-board-2026-general-election-cheat-sheet/) |
| Washington Supreme Court Justice — Position 3 | Jaime Michelle Hawk | Add | 1 | [Official evidence](https://www.thestranger.com/news/the-stranger-election-control-board-2026-general-election-cheat-sheet/) |
| Washington Supreme Court Justice — Position 4 | Ian Birk | Add | 1 | [Official evidence](https://www.thestranger.com/news/the-stranger-election-control-board-2026-general-election-cheat-sheet/) |
| Washington Supreme Court Justice — Position 5 | Theo Angelis | Add | 1 | [Official evidence](https://www.thestranger.com/news/the-stranger-election-control-board-2026-general-election-cheat-sheet/) |
| Washington Supreme Court Justice — Position 7 | Debra L. Stephens | Add | 1 | [Official evidence](https://www.thestranger.com/news/the-stranger-election-control-board-2026-general-election-cheat-sheet/) |
| King County District Court West Electoral District — Judge Position 1 | Bardi Martin | Add | 1 | [Official evidence](https://www.thestranger.com/news/the-stranger-election-control-board-2026-general-election-cheat-sheet/) |
| Seattle City Council — District 5 | Nilu Jenks | Add | 1 | [Official evidence](https://www.thestranger.com/news/the-stranger-election-control-board-2026-general-election-cheat-sheet/) |
| Seattle Municipal Court Judge — Position 5 | Gabe Rothstein | Add | 1 | [Official evidence](https://www.thestranger.com/news/the-stranger-election-control-board-2026-general-election-cheat-sheet/) |
| Seattle Proposition 1 — Seattle Transit Measure | Yes | Add | 1 | [Official evidence](https://www.thestranger.com/news/the-stranger-election-control-board-2026-general-election-cheat-sheet/) |

- Capture: `capture-the-stranger-20261011T010722Z-a5226d3f00e5`.
- Supplemental publication-date capture, identical artifact bytes: `capture-the-stranger-20261011T010722Z-df2465eb47ac`.
- Pending transcription: `manual-the-stranger-20261011T011018Z-9d2c99bf93fd`.

### Tech 4 Housing

Official 2026 General section adds ten decisions beyond the three recorded from a Bluesky publication. Jessica Forsythe (LD48) and Tacoma SAFE Homes are outside the frozen Seattle inventory. The separate primary section is excluded.

| Race | Proposed choice(s) | Change | Allocation each | Evidence |
| --- | --- | --- | --- | --- |
| Initiative IP26-645 — State and Local Taxes | No | Add | 1 | [Official evidence](https://www.tech4housing.org/endorsements) |
| Initiative IL26-001 — Parental Rights in Public Schools | No | Add | 1 | [Official evidence](https://www.tech4housing.org/endorsements) |
| Initiative IL26-638 — Participation in K-12 School Athletics | No | Add | 1 | [Official evidence](https://www.tech4housing.org/endorsements) |
| Legislative District 32 State Representative — Position 1 | Danica Noble | Add | 1 | [Official evidence](https://www.tech4housing.org/endorsements) |
| Legislative District 43 State Senator | Hannah Sabio-Howell | Add | 1 | [Official evidence](https://www.tech4housing.org/endorsements) |
| King County Assessor | Rob Foxcurran | Add | 1 | [Official evidence](https://www.tech4housing.org/endorsements) |
| Metropolitan King County Council — District 8 | Teresa Mosqueda | Add | 1 | [Official evidence](https://www.tech4housing.org/endorsements) |
| Seattle City Council — District 5 | Nilu Jenks | Add | 1 | [Official evidence](https://www.tech4housing.org/endorsements) |
| Seattle Municipal Court Judge — Position 5 | Gabe Rothstein | Add | 1 | [Official evidence](https://www.tech4housing.org/endorsements) |
| Seattle Proposition 1 — Seattle Transit Measure | Yes | Add | 1 | [Official evidence](https://www.tech4housing.org/endorsements) |

- Capture: `capture-tech-4-housing-20261011T010723Z-5922ff5e6774`.
- Pending transcription: `manual-tech-4-housing-20261011T011018Z-55ce2661486d`.

### Tech 4 Taxes

Four additions on the official 2025–2026 candidate index. Current-cycle endorsements need the ballot / withdrawal check in REVIEW_GUIDE.md. No IP26-645 lead is still unresolved and excluded. LD26 / LD48 candidates are outside this inventory.

| Race | Proposed choice(s) | Change | Allocation each | Evidence |
| --- | --- | --- | --- | --- |
| Legislative District 46 State Representative — Position 1 | Gerry Pollet | Add | 1 | [Official evidence](https://tech4taxes.org/endorsements) |
| Legislative District 37 State Senator | Tatiana Brown | Add | 1 | [Official evidence](https://tech4taxes.org/endorsements) |
| Legislative District 32 State Representative — Position 2 | Imraan Siddiqi | Add | 1 | [Official evidence](https://tech4taxes.org/endorsements) |
| Legislative District 37 State Representative — Position 1 | Kelabe Tewolde | Add | 1 | [Official evidence](https://tech4taxes.org/endorsements) |

- Capture: `capture-tech-4-taxes-20261011T010722Z-1b4bd05aca1f`.
- Pending transcription: `manual-tech-4-taxes-20261011T011018Z-86be8d2ed9f4`.

### King County Democrats

Three added decisions and one changed choice set. LD32 House Position 1 endorses Noble and Scully together; Position 2 now endorses Davis and Siddiqi together. Each is one point split equally. Pollet position and IP26-645 heading errors need explicit confirmation.

| Race | Proposed choice(s) | Change | Allocation each | Evidence |
| --- | --- | --- | --- | --- |
| Initiative IP26-645 — State and Local Taxes | No | Add | 1 | [Official evidence](https://www.kcdems.org/our-party/e/2026-endorsements/) |
| Legislative District 32 State Representative — Position 1 | Danica Noble, Keith Scully | Add | 1/2 | [Official evidence](https://www.kcdems.org/our-party/e/2026-endorsements/) |
| Legislative District 32 State Representative — Position 2 | Lauren Davis, Imraan Siddiqi | Update from lauren davis | 1/2 | [Official evidence](https://www.kcdems.org/our-party/e/2026-endorsements/) |
| Legislative District 46 State Representative — Position 1 | Gerry Pollet | Add | 1 | [Official evidence](https://www.kcdems.org/our-party/e/2026-endorsements/) |

- Capture: `capture-king-county-democrats-20261011T010722Z-8db51a3344bb`.
- Pending transcription: `manual-king-county-democrats-20261011T011018Z-c4b9f878ea3b`.

### The Washington Bus

The page now labels the image gallery 2026 GENERAL ELECTION ENDORSEMENTS. Seven Seattle-inventory candidates; seven other gallery candidates are outside the inventory. Tewolde / Scott images swap the two LD37 House position labels, surfaced below.

| Race | Proposed choice(s) | Change | Allocation each | Evidence |
| --- | --- | --- | --- | --- |
| Legislative District 43 State Senator | Hannah Sabio-Howell | Add | 1 | [Official evidence](https://images.squarespace-cdn.com/content/v1/6802c86d1563454e4aa66f2f/75296ef1-b742-4513-89d3-53d616ab85a6/hannahfix.png) |
| Seattle City Council — District 5 | Nilu Jenks | Add | 1 | [Official evidence](https://images.squarespace-cdn.com/content/v1/6802c86d1563454e4aa66f2f/bdc0d946-db26-4f0d-89e8-cf37e338d51a/5.png) |
| Legislative District 37 State Senator | Tatiana Brown | Add | 1 | [Official evidence](https://images.squarespace-cdn.com/content/v1/6802c86d1563454e4aa66f2f/4bbbb2c9-7efe-43aa-9c64-dc49bbc929a0/3.png) |
| Metropolitan King County Council — District 2 | Rebecca Saldaña | Add | 1 | [Official evidence](https://images.squarespace-cdn.com/content/v1/6802c86d1563454e4aa66f2f/aeb1c339-40ba-4121-b042-52a101e7b5c8/6.png) |
| Legislative District 32 State Representative — Position 1 | Danica Noble | Add | 1 | [Official evidence](https://images.squarespace-cdn.com/content/v1/6802c86d1563454e4aa66f2f/940fffd0-5926-4a03-88c4-ed0462c701d0/4.png) |
| Legislative District 37 State Representative — Position 1 | Kelabe Tewolde | Add | 1 | [Official evidence](https://images.squarespace-cdn.com/content/v1/6802c86d1563454e4aa66f2f/a724c019-e27a-4506-94f5-1322380e3138/6.png) |
| Legislative District 37 State Representative — Position 2 | Jaelynn Scott | Add | 1 | [Official evidence](https://images.squarespace-cdn.com/content/v1/6802c86d1563454e4aa66f2f/01954ef8-74b1-403b-9a83-9368740e1695/5.png) |

- Capture: `capture-washington-bus-20261011T010723Z-f28d04da4bcb`.

- Capture: `capture-washington-bus-20261011T010723Z-35b46c8a38b3`.

- Capture: `capture-washington-bus-20261011T010723Z-ab1a1678a561`.

- Capture: `capture-washington-bus-20261011T010723Z-6c1740663489`.

- Capture: `capture-washington-bus-20261011T010723Z-969c0dda7736`.

- Capture: `capture-washington-bus-20261011T010723Z-d46c9e5bbbfd`.

- Capture: `capture-washington-bus-20261011T010723Z-f55404f17b9c`.
- Pending transcription: `manual-washington-bus-20261011T011018Z-7ae6a30544c8`.
- Pending transcription: `manual-washington-bus-20261011T011018Z-60a6392b6888`.
- Pending transcription: `manual-washington-bus-20261011T011018Z-a0ff47636758`.
- Pending transcription: `manual-washington-bus-20261011T011018Z-bfe962a5832b`.
- Pending transcription: `manual-washington-bus-20261011T011018Z-b980f7dfa365`.
- Pending transcription: `manual-washington-bus-20261011T011018Z-0d7bb40aa6fa`.
- Pending transcription: `manual-washington-bus-20261011T011018Z-d4e8bffc6a68`.

### Washington Working Families Party

Official Our 2026 Candidates index, Washington filter, View More expanded: 17 rows, ten Seattle-inventory candidates (five already recorded plus five additions). Seven non-Seattle candidates excluded. The static response alone omits the dynamically rendered rows, so the captured browser table excerpt supplies these additions. These are current-cycle endorsements, not an election-specific general slate.

| Race | Proposed choice(s) | Change | Allocation each | Evidence |
| --- | --- | --- | --- | --- |
| Legislative District 37 State Representative — Position 2 | Jaelynn Scott | Add | 1 | [Official evidence](https://workingfamilies.org/candidates/) |
| Legislative District 43 State Representative — Position 2 | Shaun Scott | Add | 1 | [Official evidence](https://workingfamilies.org/candidates/) |
| Legislative District 46 State Representative — Position 2 | Darya Farivar | Add | 1 | [Official evidence](https://workingfamilies.org/candidates/) |
| Legislative District 36 State Senator | Noel C. Frame | Add | 1 | [Official evidence](https://workingfamilies.org/candidates/) |
| Legislative District 43 State Senator | Hannah Sabio-Howell | Add | 1 | [Official evidence](https://workingfamilies.org/candidates/) |

- Capture: `capture-washington-working-families-party-20261011T010831Z-07fcfbad8277`.
- Pending transcription: `manual-washington-working-families-party-20261011T011018Z-0b55339acf93`.

### OneAmerica Votes

Two November No initiative choices appear under Initiatives. The same wording is already present in capture-oneamerica-votes-20261004T045656Z-5a5ae1a02f34; this corrects an earlier omission in review.

| Race | Proposed choice(s) | Change | Allocation each | Evidence |
| --- | --- | --- | --- | --- |
| Initiative IL26-001 — Parental Rights in Public Schools | No | Add | 1 | [Official evidence](https://oavotes.org/our-work/endorsements/2026-endorsements/) |
| Initiative IL26-638 — Participation in K-12 School Athletics | No | Add | 1 | [Official evidence](https://oavotes.org/our-work/endorsements/2026-endorsements/) |

- Capture: `capture-oneamerica-votes-20261011T010723Z-6badda3e27c2`.
- Pending transcription: `manual-oneamerica-votes-20261011T011018Z-15769b0c3539`.

### Washington Community Action Network

The two county council endorsement graphics were already linked in capture-washington-community-action-network-20261004T045652Z-fdad3f223455. Empty alt text hid them from the earlier transcription. Both visible graphics were checked; prior initiative and candidate choices are retained.

| Race | Proposed choice(s) | Change | Allocation each | Evidence |
| --- | --- | --- | --- | --- |
| Metropolitan King County Council — District 2 | Rebecca Saldaña | Add | 1 | [Official evidence](https://images.squarespace-cdn.com/content/v1/58fcdc8637c5811d5b7a50a7/5fe1ff20-4d88-4a9f-9c32-8a83d8996014/2026+General+Endorsements++-+2.PNG) |
| Metropolitan King County Council — District 8 | Teresa Mosqueda | Add | 1 | [Official evidence](https://images.squarespace-cdn.com/content/v1/58fcdc8637c5811d5b7a50a7/96031cac-155f-4c00-b312-347cf37d7c8c/2026+General+Endorsements++-+1.PNG) |

- Capture: `capture-washington-community-action-network-20261011T010723Z-daf7801a3785`.

- Capture: `capture-washington-community-action-network-20261011T010723Z-07bb27e7e6f2`.
- Pending transcription: `manual-washington-community-action-network-20261011T011018Z-8989491758cb`.
- Pending transcription: `manual-washington-community-action-network-20261011T011018Z-a6084af9a856`.

## Unresolved leads — excluded from this proposal

If every proposed row is human-verified, the audit's organization-family comparison would have 362 matching choice sets and no conflicting choice sets. This reconciles 64 shared decisions (63 additions and the changed dual); WFP's Shaun Scott addition is outside the comparator's contested-only inventory. The remaining 87 comparator-only records comprise the 72 unresolved leads below and 15 additional PVG recommendations. Thirty records from unregistered sources remain separate eligibility work. This is a conditional comparison, not a claim that the pending rows are already published.

| Source | Outstanding evidence | Next action |
| --- | --- | --- |
| Urbanist | Sixteen competitor records; checked official tag archive and elections committee page still establish primary endorsements only. | Obtain an official general publication or explicit carry-forward; do not infer it from advancement. |
| Washington for Peace and Justice | Sixteen competitor records; referenced Instagram carousel metadata identifies July / primary timing; endorsement vs candidate rating semantics also need confirmation. | Obtain exact official general decisions and confirm endorsement meaning. |
| Stonewall Democrats | Nineteen competitor records; referenced Facebook post says primary, full content limited by access. | Use legitimately accessible official general evidence or record continuing restricted status. |
| Seattle DSA | Three No initiative leads; checked Seattle candidate post establishes candidates rather than those measure choices. | Obtain a specific official initiative publication and resolve national / local source identity. |
| Tech 4 Taxes | No on IP26-645 lead is not established by the candidate index or social profile. | Obtain a specific official measure post. |
| Seattle Times | Seventeen new competitor choices; current official page access is restricted. Prior five reviewed choices retained. | An authorized reviewer can supply legitimately accessible official evidence. Review Position 4 endorsement semantics explicitly; prior commentary was not an endorsement. |

The unresolved leads retain their exact discovery URLs and complete race-level comparison in the [October 10 audit](../docs/ENDORSEMENT_COVERAGE_AUDIT_2026-10-10.md). No organizations were contacted. This packet does not present primary-only or inaccessible material as general evidence.

## Separate panel eligibility work

[#509](https://github.com/shaug/seattle-election-guide/issues/509) and the [separate eligibility assessment](SOURCE_ELIGIBILITY_REVIEW_2026-10-10.md) record Nondriver Action, Citizens Against AIPAC Corruption / Track AIPAC, Young Democrats of Washington, and King County GOP. Track AIPAC's own attribution identifies the endorsing organization as Citizens Against AIPAC Corruption, so its project and organization must not become two sources. Nondriver Action’s four choices and that organization's Jayapal choice have official publication leads; YDWA needs exact official posts. GOP would be a separate comparison-policy decision. The existing frozen panel is unchanged. Progressive Voters Guide’s extra recommendations remain distinct from Fuse’s organizational endorsements and excluded under the current duplicate-publisher policy.

## Baseline bindings

| Input | File-byte SHA-256 |
| --- | --- |
| `source-decisions.yaml` | `9996691a56d809ba418c901eb9907d21ab020b5e5bf13034af0539ec47302d90` |
| `wa-2026-general-canonical-dataset.json` | `16b44e35c14a7d68203e0ed4335243221f697241f86354b8f3e153365bb129e0` |
| `wa-2026-general-inventory.json` | `46072aa86d3a63dc66c88ae8c347b813dfc3dea2b0334d87b835eb9d80640ed6` |
| `wa-2026-general.yaml` | `00a38879d59b9a45cd3cee3b799f784eade9fd629439d2e8f57e7ccd3c50e1e6` |

## Application and release gate

1. Human verifies the transcriptions above and confirms or rejects each explicit label mapping. Record the actual verifier, time, and review note through new immutable manual-entry records; retain the pending originals.
2. Apply verified decisions only; preserve all unaffected source decisions and their earlier review provenance. Record the King County Democrats Davis-to-dual update with prior value, new value, reason, capture, author, and timestamp. Refresh discovery URLs / timestamps for the eight checked sources and preserve the stable panel hash.
3. Compile and verify the general ledger; refresh affected scoring / rendering fixtures; run make check and prepare the next immutable release version through docs/RELEASE.md. A later approval cannot be backdated to packet preparation.
4. Complete repository review / PR gates. Release publication and production approval follow docs/RELEASE.md / docs/HOSTING.md and remain separate from source verification.

Validation before human verification: baseline release verify passed at d6f186c78c286381c3c6ce45ec4223be8d6c47d5 (34 sources / 617 decisions). Every proposed candidate resolves to the stated frozen race, each allocation sums to one, and every proposal capture / pending manual record validates. Eight proposed discovery updates validate without changing the stable panel hash. The change-demonstrating-test form is `evidence_docs_config_exemption`: only documentary review data, evidence metadata, and the collection checklist have changed; no executable behavior has changed.

`make check` passed after preparation: 1,301 Python tests and 684 JavaScript tests, format / lint / type checks, both election contracts and release verification, calendar, evidence, results, and changelog gates. The primary release remains 538 decisions / 41 sources and the general release remains 617 decisions / 34 sources. The separate durable-store check `evidence verify-all --require-local --storage-root <primary-checkout>/data/snapshots` also passed: all 162 capture manifests resolve to 156 present records or six intentional metadata-only records. No artifact was missing or corrupt. `git diff --check` passed.
