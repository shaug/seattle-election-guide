# October 3, 2026 rolling endorsement refresh

Scope: [issue #474](https://github.com/shaug/seattle-election-guide/issues/474), `wa-2026-general`. This is one comprehensive pass in the active rolling window. Later checks through the election, the final October 15 pass, immutable Release publication, and production acceptance remain pending.

All 43 frozen consensus/comparison sources were checked in oldest `discovery.checked_at` order on October 3 Pacific (October 4 UTC). The pass resolves to 34 published blocks, five `not_found` dispositions, and four `access_restricted` dispositions. Source membership, classifications, eligibility, scoring, and ballot inventory are unchanged. The stable panel hash remains `b0fb2a603bd98da49d3282d2daa0cb55ff56e0bbdd46104c8b5a4a441b747a95`.

OpenAI Codex prepared the captured source-by-source comparison packet. **shaug confirmed the whole packet with “verified” in the implementing session**, covering all source dispositions, the 614 retained decisions, and the three new image transcriptions. The confirmation was recorded at `2026-10-04T05:30:06Z`; retrieval times below are actual fetch observations. Prior ambiguity and ballot-match treatments remain in the source-specific ledger notes.

## Material delta against the live guide

The downloaded `2026-general.3` archive matches the prior repository canonical dataset exactly. Its SHA-256 is `8ffdc611be41eae702ac631a36d9b8944e378f0f5827371d455ddd24cb973d4e`, matching the GitHub asset digest; the published candidate is `8726c614bb8ac2a6e9ea3eb406bb53442d44effd`. The refreshed ledger retains all 614 decisions and adds three WashingtonCAN No recommendations, yielding 617. No in-inventory withdrawal, replacement, or other changed choice was found.

| Frozen race | Added choice | Official image text | Verified manual record |
| --- | --- | --- | --- |
| `initiative-26-001` | `initiative-26-001--no` | Vote No on I-001 & I-638 | `manual-washington-community-action-network-20261004T050422Z-7e4a0dc1a674` |
| `initiative-26-638` | `initiative-26-638--no` | Vote No on I-001 & I-638 | `manual-washington-community-action-network-20261004T050422Z-7e4a0dc1a674` |
| `initiative-26-645` | `initiative-26-645--no` | NO 645 | `manual-washington-community-action-network-20261004T050422Z-6d9f6991d34d` |

The 645 graphic’s filename says 648; its visible badge says **NO 645**. The reviewed image text supplies the match to the frozen inventory. The source publication dates of these graphics were not independently established. Both image captures and the official gallery HTML are referenced in the ledger and registry. The two existing WashingtonCAN candidate endorsements remain present.

## Source-by-source evidence

All capture IDs resolve under `data/manifests/evidence/`. Supplemental captures are listed below the table. Full third-party bytes remain restricted in the durable content-addressed store on the capturing machine, outside Git. The 48 new manifests comprise 44 present artifacts and four intentional metadata-only unavailability records. Each was verified individually and the complete store was audited with `evidence verify-all --require-local`.

| Official source | Actual check (UTC) | Disposition | Observation | Capture ID |
| --- | --- | --- | --- | --- |
| [The Stranger Election Control Board](https://www.thestranger.com/category/election-endorsements/) | 2026-10-04T04:56:52Z | not_found | Archive still leads with the 2026 primary guide; no general guide found. | `capture-the-stranger-20261004T045652Z-05ddb946821f` |
| [The Urbanist Elections Committee](https://www.theurbanist.org/2026-primary-election-endorsements/) | 2026-10-04T04:56:52Z | not_found | Primary-only guide; supplemental official elections-committee page also links only the 2026 primary. | `capture-the-urbanist-20261004T045652Z-992c9743995c` |
| [Fuse Washington](https://www.fusewashington.org/news/blog/fuses-2026-general-election-endorsements) | 2026-10-04T04:56:52Z | published | Current official capture retains the prior publication decision text. | `capture-fuse-washington-20261004T045652Z-565aa39a551b` |
| [Seattle Democratic Socialists of America](https://seattledsa.org/event/jaelynn-scott-37ld-campaign-kick-off-canvass/) | 2026-10-04T04:56:52Z | published | Related-event widget changed; Jaelynn Scott endorsement text unchanged. | `capture-seattle-democratic-socialists-20261004T045652Z-fd260ad850f9` |
| [Tech 4 Housing](https://bsky.app/profile/tech4housing.org/post/3mpkb7wcjok2z) | 2026-10-04T04:56:52Z | published | Current official capture retains the prior publication decision text. | `capture-tech-4-housing-20261004T045652Z-6a77e1f6d5b0` |
| [Tech 4 Taxes](https://tech4taxes.org/endorsements) | 2026-10-04T04:56:52Z | published | Current official capture retains the prior publication decision text. | `capture-tech-4-taxes-20261004T045652Z-1b922edfa9fa` |
| [Washington for Peace and Justice](https://www.wa4pj.com/) | 2026-10-04T04:56:52Z | not_found | Official site has no current endorsement publication located. | `capture-washington-for-peace-and-justice-20261004T045652Z-5b8b4ae92d99` |
| [Washington Community Action Network](https://www.washingtoncan.org/endorsements) | 2026-10-04T04:56:52Z | published | Verified material delta: No on IL26-001, IL26-638, IP26-645. Two existing candidate decisions preserved. Image text, rather than the erroneous 648 filename, supplies the 645 mapping. | `capture-washington-community-action-network-20261004T045652Z-fdad3f223455` |
| [Washington Working Families Party](https://workingfamilies.org/state/washington/) | 2026-10-04T04:56:53Z | published | Current official capture retains the prior publication decision text. | `capture-washington-working-families-party-20261004T045653Z-3bd0d468ecd5` |
| [The Washington Bus](https://www.washingtonbus.org/endorsements) | 2026-10-04T04:56:53Z | not_found | Official page still labels its 2026 endorsements PRIMARY; older 2025 general list not reused. | `capture-washington-bus-20261004T045653Z-30f108b8466d` |
| [Sage Leaders](https://www.sageleaders.org/2026-endorsements) | 2026-10-04T04:56:53Z | published | Current official capture retains the prior publication decision text. | `capture-sage-leaders-20261004T045653Z-4e2d45cd6f5e` |
| [Washington State Democratic Party](https://wadems.org/) | 2026-10-04T04:56:53Z | access_restricted | HTTP 403; access-restricted disposition preserved. | `capture-washington-state-democrats-20261004T045653Z-5b254f723baf` |
| [King County Democrats](https://www.kcdems.org/our-party/e/2026-endorsements/) | 2026-10-04T04:56:53Z | published | Removed Jenne Alderks in LD1 Pos2; that race is outside the frozen Seattle inventory, so no published decision changes. | `capture-king-county-democrats-20261004T045653Z-7099181e37eb` |
| [11th Legislative District Democrats](http://eepurl.com/QAju_Mt-ye) | 2026-10-04T04:56:53Z | published | Current official capture retains the prior publication decision text. | `capture-11th-district-democrats-20261004T045653Z-1c69ce0cdea5` |
| [32nd Legislative District Democrats](https://32democrats.org/2026-endorsements/) | 2026-10-04T04:56:53Z | published | Formatting, full names, and initiative descriptions changed; candidate sets, dual endorsements, and three No decisions remain the same. | `capture-32nd-district-democrats-20261004T045653Z-d66cbf40a164` |
| [34th Legislative District Democrats](https://34dems.org/2026-endorsements/) | 2026-10-04T04:56:53Z | published | Current official capture retains the prior publication decision text. | `capture-34th-district-democrats-20261004T045653Z-82887823c97e` |
| [36th Legislative District Democrats](https://36th.org/endorsements-2026/) | 2026-10-04T04:56:54Z | published | Current official capture retains the prior publication decision text. | `capture-36th-district-democrats-20261004T045654Z-745b079c64ec` |
| [43rd Legislative District Democrats](https://43rddemocrats.org/endorsements/2026) | 2026-10-04T04:56:54Z | published | Current official capture retains the prior publication decision text. | `capture-43rd-district-democrats-20261004T045654Z-3e84f0d75d25` |
| [46th Legislative District Democrats](https://www.46dems.org/2026_46th_district_dems_endorsed_candidates_campaigns) | 2026-10-04T04:56:54Z | published | Current official capture retains the prior publication decision text. | `capture-46th-district-democrats-20261004T045654Z-9105db21d8ac` |
| [Washington State Stonewall Democrats](https://www.facebook.com/stonewallwa/posts/1450344363801898/) | 2026-10-04T04:56:54Z | access_restricted | Official Facebook response exposed no reconstructable post content; access-restricted disposition preserved. | `capture-washington-stonewall-democrats-20261004T045654Z-72ae3a59634c` |
| [Transit Riders Union](https://transitriders.org/transit-riders-union-2026-general-election-endorsements/) | 2026-10-04T04:56:54Z | published | Current official capture retains the prior publication decision text. | `capture-transit-riders-union-20261004T045654Z-a94f0424cdd3` |
| [Washington Bikes](https://wabikes.org/index.php/advocacy/endorsements/) | 2026-10-04T04:56:54Z | published | Current official capture retains the prior publication decision text. | `capture-washington-bikes-20261004T045654Z-592872819910` |
| [Seattle Subway](https://www.seattlesubway.org/election-endorsements/) | 2026-10-04T04:56:54Z | not_found | Official publication still explicitly describes the August 2026 primary; not reused. | `capture-seattle-subway-20261004T045654Z-b4b43955e3de` |
| [Washington Conservation Action](https://waconservationaction.org/our-work/areas-of-work/endorsements/) | 2026-10-04T04:56:54Z | published | Current official capture retains the prior publication decision text. | `capture-washington-conservation-action-20261004T045654Z-9794a0a1c5b7` |
| [Sierra Club Washington State Chapter](https://www.sierraclub.org/washington) | 2026-10-04T04:56:54Z | access_restricted | HTTP 200 contains an Incapsula access challenge; access-restricted disposition preserved. | `capture-sierra-club-washington-20261004T045654Z-bb852d680797` |
| [Environment and Climate Caucus of the Washington State Democratic Party](https://eccwa.org/wp/endorsements/2026-endorsed-candidates/) | 2026-10-04T04:56:54Z | published | Current official capture retains the prior publication decision text. | `capture-environmental-climate-caucus-wa-democrats-20261004T045654Z-f148d9a7bf47` |
| [MLK Labor](https://www.mlklabor.org/endorsements/) | 2026-10-04T04:56:54Z | published | Current official capture retains the prior publication decision text. | `capture-mlk-labor-20261004T045654Z-00ed20bad11c` |
| [Washington State Labor Council, AFL-CIO](https://wslc.org/wp-content/uploads/2026/05/2026-WSLC-election-endorsements.pdf) | 2026-10-04T04:56:55Z | published | Current official capture retains the prior publication decision text. | `capture-washington-state-labor-council-20261004T045655Z-824028c6e752` |
| [SEIU 775](https://seiu775.org/2026endorsements/) | 2026-10-04T04:56:55Z | published | Current official capture retains the prior publication decision text. | `capture-seiu-775-20261004T045655Z-024b6837ef59` |
| [SEIU 925](https://www.seiu925.org/2026endorsements/) | 2026-10-04T04:56:55Z | published | Current official capture retains the prior publication decision text. | `capture-seiu-925-20261004T045655Z-6e9fed87c8e6` |
| [UFCW 3000](https://ufcw3000.org/endorsements) | 2026-10-04T04:56:55Z | published | Member-story widget changed; endorsement list unchanged. | `capture-ufcw-3000-20261004T045655Z-ac563a1c44fe` |
| [AFT Washington](https://www.aftwa.org/endorsements-and-elections) | 2026-10-04T04:56:55Z | published | Captured both linked official general-legislative and Supreme Court publications; both retain identical visible text to October 3 captures. | `capture-aft-washington-20261004T045655Z-b4b37848fba3` |
| [Washington Education Association](https://www.washingtonea.org/advocacy/wea-pac/2026-endorsements/) | 2026-10-04T04:56:55Z | published | Current official capture retains the prior publication decision text. | `capture-washington-education-association-20261004T045655Z-9df06a76043e` |
| [Washington State Building and Construction Trades Council](https://www.wabuildingtrades.org/candidates.html) | 2026-10-04T04:56:55Z | published | Current official capture retains the prior publication decision text. | `capture-washington-state-building-trades-20261004T045655Z-baaaa6209933` |
| [PROTEC17](https://www.protec17.org/endorsements/) | 2026-10-04T04:56:55Z | published | Added Portland endorsements, updated page timestamp and contact widget; no frozen Seattle-inventory decision changes. | `capture-protec17-20261004T045655Z-f23fa6e17be3` |
| [Planned Parenthood Alliance Advocates](https://www.plannedparenthoodaction.org/planned-parenthood-alliance-advocates) | 2026-10-04T04:56:56Z | access_restricted | HTTP 403; access-restricted disposition preserved. | `capture-planned-parenthood-alliance-advocates-20261004T045656Z-1b36e7fabf51` |
| [OneAmerica Votes](https://oavotes.org/our-work/endorsements/2026-endorsements/) | 2026-10-04T04:56:56Z | published | Current official capture retains the prior publication decision text. | `capture-oneamerica-votes-20261004T045656Z-5a5ae1a02f34` |
| [Alliance for Gun Responsibility Victory Fund](https://gunresponsibility.org/2026-endorsements/) | 2026-10-04T04:56:56Z | published | Current official capture retains the prior publication decision text. | `capture-alliance-for-gun-responsibility-20261004T045656Z-fc3912865542` |
| [Washington Housing Alliance](https://www.wahousingalliance.org/endorsements) | 2026-10-04T04:56:56Z | published | Current official capture retains the prior publication decision text. | `capture-washington-housing-alliance-20261004T045656Z-a736d43c4cd9` |
| [National Women's Political Caucus of Washington](https://www.nwpcwa.org/endorsements_2026) | 2026-10-04T04:56:56Z | published | Current official capture retains the prior publication decision text. | `capture-nwpc-washington-20261004T045656Z-8b1b6ed1f79d` |
| [The Seattle Times Editorial Board](https://www.seattletimes.com/opinion/editorials/) | 2026-10-04T04:56:56Z | published | Current official capture retains the prior publication decision text. | `capture-seattle-times-editorial-board-20261004T045656Z-dd417300dcc7` |
| [37th Legislative District Democrats](https://37dems.org/) | 2026-10-04T04:56:56Z | published | Same visible text as the October 3 official capture; comparison uses the latest capture, not the obsolete July primary page. | `capture-37th-district-democrats-20261004T045656Z-7893bd8f74c4` |
| [Seattle Gay News Editorial Board](https://www.sgn.org/ch/News/Seattle?start=20) | 2026-10-04T04:56:56Z | published | Current official capture retains the prior publication decision text. | `capture-seattle-gay-news-20261004T045656Z-63416c1da15c` |

Supplemental official captures:

- [washington-community-action-network](https://images.squarespace-cdn.com/content/v1/58fcdc8637c5811d5b7a50a7/1789506320122-9AW0DKTSI0ZPP4BYRWI3/No+hate+in+wa+state+for+website.png), 2026-10-04T04:59:22Z: `capture-washington-community-action-network-20261004T045922Z-080aa37b091f`.
- [washington-community-action-network](https://images.squarespace-cdn.com/content/v1/58fcdc8637c5811d5b7a50a7/1789505191999-20HFECETIFPIKHRHT3V7/No+on+648+for+website.png), 2026-10-04T04:59:23Z: `capture-washington-community-action-network-20261004T045923Z-baee3c92a842`.
- [aft-washington](https://www.aftwa.org/endorsements-and-elections/our-2026-general-legislative-endorsements), 2026-10-04T04:59:23Z: `capture-aft-washington-20261004T045923Z-9f869878e7bb`.
- [aft-washington](https://www.aftwa.org/endorsements-and-elections/washington-state-supreme-court-endorsements), 2026-10-04T04:59:25Z: `capture-aft-washington-20261004T045925Z-a2faf78f9c19`.
- [the-urbanist](https://www.theurbanist.org/elections-committee/), 2026-10-04T04:59:26Z: `capture-the-urbanist-20261004T045926Z-5f0b91c9cccc`.

## Publication handoff

The human-reviewed `2026-general.4` inputs have these file-byte SHA-256 values. The release
operator must compare all three before publication; these raw file hashes are distinct from the
validated registry audit identity below.

| Input file | SHA-256 |
| --- | --- |
| `config/sources/wa-2026-general.yaml` | `00a38879d59b9a45cd3cee3b799f784eade9fd629439d2e8f57e7ccd3c50e1e6` |
| `data/normalized/wa-2026-general-canonical-dataset.json` | `16b44e35c14a7d68203e0ed4335243221f697241f86354b8f3e153365bb129e0` |
| `data/releases/wa-2026-general/source-decisions.yaml` | `9996691a56d809ba418c901eb9907d21ab020b5e5bf13034af0539ec47302d90` |

This material delta requires a new immutable election-scoped release; the existing `2026-general.3` tag and assets must remain intact. This PR prepares reviewed inputs, evidence, and the `2026-general.4` candidate declarations across the build, CI, preview, and hosting contracts. The complete registry audit hash is `2da80c88fc1a913e32aeb7ddfd5d66ffb18f9820e41579da575120e6de4c5d16`. Release publication and the lineage, manual production approval, and public-route checks must use the supported sequence in `docs/RELEASE.md` and `docs/HOSTING.md` after landing. No release was published and no production deployment was requested in this pass. Issue #474 stays open until those acceptance items and the continuing refresh work are satisfied.
