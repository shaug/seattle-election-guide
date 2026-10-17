# Primary election data history audit

Bounded revision range: `6bbebc0e23fdae9fc02ea6ca8501195ab2ed7b67` (first downloadable release baseline) through `5251de04a3ac09804eff2983fc67e8b6b0cc71b0`. Dates below use America/Los_Angeles. This covers endorsement/source/eligibility/allocation/inventory/results history; page audit covers presentation changes.

## Evidence and baseline

- First public downloadable release [2026-primary.1](https://github.com/shaug/seattle-election-guide/releases/tag/2026-primary.1) was published July 19, 2026 at 23:34:35 PDT (GitHub published_at 2026-07-20T06:34:35Z). It contains 174 normalized decisions from 17 represented publishers out of 37 active sources, and 32 publication races. Registered sources: 42 total, 36 consensus + 1 comparison + 5 excluded. Its release dataset is actual reviewed source data, not a sample fixture: the historical `release/builder.py` calls `verify_release_compilation(ledger_path, inventory_path, registry_path, dataset_path, snapshot_root, manifest_dir)`, then scores that returned dataset; the downloaded ZIP canonical dataset contains those 174 records. The source decisions ledger and primary inventory are the production inputs. The phrase sample guide in Progressive Voters Guide URL is an excluded-source discovery artifact, not the builder input.
- Inventory stayed unchanged across all eight canonical primary dataset mutations. Neither primary inventory file has any post-baseline commit. All 32 publication races and ballot choices are unchanged.
- All five semantic endorsement batches only ADD source/race decision records: 209 + 81 + 22 + 35 + 17 = 364. 174 + 364 = 538 final. There are zero endorsement removals or replacements in the canonical history. The source panel adds six sources on July 23; it removes none. Seven LD sources broaden eligibility in the initial-site batch.
- Recomputed support, counts and grades from exact allocations were checked against ALL 32 race rows in EACH downloaded .1, .2 and .3 public consensus report: zero mismatches. This matters because the prose on PR #323 incorrectly reports LD37 R1 7–7 to 9–7; actual published values are 13/2–13/2 to 17/2–13/2.

## Proposed chronology

### July 19 — First primary guide published (baseline)

First downloadable guide: 32 races, 174 recorded source decisions and 17 represented publications. Data timestamp is separate from publication time. Link release .1 above. This baseline can be one entry if the backfill begins with first publication.

### July 21 — Expanded primary coverage in the first live site

The first successful website publication at 13:24:27 PDT incorporated PRs [#26](https://github.com/shaug/seattle-election-guide/pull/26), [#28](https://github.com/shaug/seattle-election-guide/pull/28), [#53](https://github.com/shaug/seattle-election-guide/pull/53). Relative to the already downloadable .1 guide, recorded decisions rose 174 → 486 and represented publishers 17 → 35 of the same 37 active sources. This adds 312 source/race records (including 15 Seattle Times comparison-only decisions). All 32 races have changed default counts, support or comparison evidence even where their leader is unchanged.

A July 20 entry would mislabel merge dates as publication dates: these batches have no earlier public release asset and predate the first live site. The initial-site batch must account for all three commits.

| Commit / batch | New source/race records | Specific additions / eligibility |
| --- | ---: | --- |
| #26 0a9b2632 | 209 | 15 previously unrepresented publications (listed below), including Seattle Times comparison; missing regional PPAA and Times evidence resolved. Environmental & Climate Caucus status corrected from published to no candidate roster found. |
| #28 4cce1737 | 81 | Sierra Club +17; 37th LD +13; 11th +5, 32nd +9, 34th +9, 36th +8, 43rd +11, 46th +9. All seven LD organizations now count explicit Seattle-ballot federal/statewide/judicial/county/city choices while remaining restricted to their own LD for legislative contests. |
| #53 505ce616 | 22 | Official Washington Stonewall Facebook twelve-image gallery: 22 in-inventory decisions, including two dual endorsements; correct Washington organization (earlier California roster rejected). |

The #26 additions, by publisher: 11th LD Democrats 2; AFT Washington 20; Alliance for Gun Responsibility 22; NWPC Washington 20; OneAmerica Votes 9; Planned Parenthood Alliance Advocates 3; Sage Leaders 9; Seattle Times 15; SEIU 925 27; UFCW 3000 23; Washington Bikes 12; Washington Bus 4; Washington Education Association 12; Washington Housing Alliance 19; Washington State Building Trades 12.

Source evidence destinations also changed: AFT now links its exact primary legislative list; PPAA uses its organization-authored joint Supreme Court announcement republished in Islands’ Sounder; Times links the Aug. 4 primary editorial index; Sierra Club links its exact 2026 primary list; Stonewall links the official Facebook gallery. The source identity remains each named organization. Full before/after URLs/locators are in primary-data-changes.json.

### July 23 — Added six endorsement publishers

Published at 13:25:13 PDT from [#67](https://github.com/shaug/seattle-election-guide/pull/67). Adds Seattle DSA (1 decision), Tech 4 Housing (4), Tech 4 Taxes (6 race decisions / 7 candidates), Washington for Peace and Justice (19 / 21 candidates), Washington Community Action Network (2) and Seattle Gay News Editorial Board (3). Decisions 486 → 521; represented publications 35 → 41; active sources 37 → 43 (36 → 42 consensus, same one comparison). New decisions span 21 races, but eligibility/coverage counts change across all 32. Exact ties replace leads in LD37 Representative 1 and Supreme Court Position 3. Four other grade changes and all unchanged-leader count/share changes appear in table below.

Tech 4 Taxes stays attributed to official tech4taxes.org/endorsements; documented source-specific Blue Voter Guide capture temporarily supplied evidence while origin timed out. W4PJ uses the official Instagram carousel and only green vote-for choices. Gray/red/leave-blank entries do not contribute. All dual endorsements keep half-point allocations. No existing source was removed/replaced. Ballot inventory unchanged.

### August 5 — Added 17 previously missed endorsements

Published at 11:04:11 PDT from [#323](https://github.com/shaug/seattle-election-guide/pull/323), after election day. Six existing publishers were rechecked: Transit Riders Union +5, Washington Working Families Party +2, Sage Leaders +3, SEIU 775 +1, UFCW 3000 +1, Seattle Gay News +5. Decisions 521 → 538; source membership remains 41 represented / 43 active. Changed data touch 11 races. Kelabe Tewolde leads LD37 R1 at 17/30 (8.5 of 15 points), replacing a 6.5–6.5 tie; Jaime Michelle Hawk leads Supreme Court Position 3 at 21/40, replacing a 9.5–9.5 tie. Chipalo Street remains ahead in LD37 Senate, with grade A+ → A and share 29/32 → 29/36. This entry records when the guide caught up; it must not imply organizations announced endorsements on August 5. No prior recorded decision was replaced.

### August 19 — Published the first certified results

At 22:07:14 PDT, [#413](https://github.com/shaug/seattle-election-guide/pull/413) first published certified outcomes for 24 King County-contained races. Prior state: no result numbers; after: all ballot choices, vote totals/shares and advancement or approval flags for those 24, with authority/evidence. Certified_on is August 18 (certification date, not publication). The banner becomes “This election is complete.” Eight cross-county races explicitly remain without results pending statewide totals. [Acceptance evidence](https://github.com/shaug/seattle-election-guide/issues/409#issuecomment-5351627047), [CI/deployment](https://github.com/shaug/seattle-election-guide/actions/runs/32333732440). No endorsement data changes.

### September 13 — Completed certified results for all 32 races

At 20:50:10 PDT, [#419](https://github.com/shaug/seattle-election-guide/pull/419) first successfully published the remaining eight races: LD32 Senate and both Representative positions, US House 9, Supreme Court Positions 1, 3, 5, 7. Results coverage 24 → 32. Statewide Washington Secretary of State totals are displayed as votes counted; King County’s own 24 results retain ballots counted. All original 24 numerical outcomes remain byte-equivalent after removing only new provenance/schema fields. Per-race evidence links now cite the correct authority. The label “capture” becomes “evidence.” Source evidence was captured August 19; code merged August 22; original August 22 deployment failed. [Explicit public verification dated September 13](https://github.com/shaug/seattle-election-guide/issues/417#issuecomment-5658729647), [successful CI attempt 2](https://github.com/shaug/seattle-election-guide/actions/runs/32588483948/attempts/2). Do not date publication August 22.

### October 3 — Primary archive regressed during general cutover

First successful cutover at 07:27:19 PDT (b40cbaab) served the hash-pinned August 2 [2026-primary.2](https://github.com/shaug/seattle-election-guide/releases/tag/2026-primary.2) archive as configured by [#476](https://github.com/shaug/seattle-election-guide/pull/476). Dataset regressed 538 → 521, withdrawing the 17 August 5 additions and reversing their 11 race-level score/count changes; certified result coverage regressed 32 → 0. This is a publication restoration incident, not organization withdrawals. The precise affected 17 records and 11 score rows are the inverse of the August 5 audit table.

### October 11 — Restored the completed primary archive

At 22:49:41 PDT, [#526](https://github.com/shaug/seattle-election-guide/pull/526) switched the served archive to [2026-primary.3](https://github.com/shaug/seattle-election-guide/releases/tag/2026-primary.3): decisions 521 → 538 and certified results 0 → 32. The replacement ZIP itself had become downloadable earlier that day at 22:09:25 PDT. It preserves the final live primary endorsement ledger and results; these are restored historical records, not newly announced endorsements or recertification. The current renderer also restores the segmented meter. The authored log records the regression and restoration on their separate public dates.

## Every changed score/count row

Notation for each side: leader(s); leader support points; exact share; grade; explicit / covered / eligible counts. This records unchanged-leader changes too. Detailed decision-by-decision source/race additions live in JSON.

### July 21: net .1 → first website dataset (all 32 races)

| Race | Before | After |
| --- | --- | --- |
| king-county-assessor | rob-foxcurran; 4 points; 1; A+; 4/4/29 | rob-foxcurran; 15/2 points; 15/26; C; 13/13/36 |
| king-county-council-2 | rebecca-salda-a; 15/2 points; 15/16; A+; 8/8/29 | rebecca-salda-a; 35/2 points; 7/8; A; 20/20/36 |
| king-county-council-8 | teresa-mosqueda; 9 points; 1; A+; 9/9/29 | teresa-mosqueda; 21 points; 1; A+; 21/21/36 |
| ld-11-state-representative-1 | david-hackney; 5/2 points; 5/8; B; 4/5/30 | david-hackney; 7 points; 7/11; B; 11/12/30 |
| ld-11-state-representative-2 | steve-bergquist; 3 points; 1; A; 3/3/30 | steve-bergquist; 8 points; 1; A+; 8/8/30 |
| ld-32-state-representative-1 | danica-noble; 3 points; 3/4; A; 4/5/30 | danica-noble; 7 points; 7/11; B; 11/12/30 |
| ld-32-state-representative-2 | lauren-davis; 4 points; 2/3; B; 6/6/30 | lauren-davis; 21/2 points; 21/34; B; 17/17/30 |
| ld-32-state-senator | cindy-ryu; 4 points; 4/5; A; 5/5/30 | cindy-ryu; 21/2 points; 7/10; B; 15/15/30 |
| ld-34-state-representative-1 | brianna-k-thomas; 3 points; 1; A; 3/3/30 | brianna-k-thomas; 8 points; 1; A+; 8/8/30 |
| ld-34-state-representative-2 | joe-fitzgibbon; 7 points; 1; A+; 7/7/30 | joe-fitzgibbon; 17 points; 17/18; A+; 18/18/30 |
| ld-34-state-senator | emily-alvarado; 5 points; 1; A+; 5/5/30 | emily-alvarado; 15 points; 1; A+; 15/15/30 |
| ld-36-state-representative-1 | julia-grant-reed; 6 points; 1; A+; 6/6/30 | julia-grant-reed; 17 points; 1; A+; 17/17/30 |
| ld-36-state-representative-2 | liz-berry; 4 points; 1; A+; 4/4/30 | liz-berry; 13 points; 1; A+; 13/13/30 |
| ld-36-state-senator | noel-c-frame; 4 points; 1; A+; 4/4/30 | noel-c-frame; 10 points; 1; A+; 10/10/30 |
| ld-37-state-representative-1 | kelabe-tewolde; 2 points; 2/3; B; 3/3/30 | sharon-tomiko-santos; 6 points; 3/5; B; 10/10/30 |
| ld-37-state-representative-2 | jaelynn-scott; 6 points; 1; A+; 6/6/30 | jaelynn-scott; 16 points; 1; A+; 16/16/30 |
| ld-37-state-senator | chipalo-street; 5 points; 1; A+; 5/6/30 | chipalo-street; 27/2 points; 9/10; A+; 15/16/30 |
| ld-43-state-representative-1 | nicole-macri; 7 points; 1; A+; 7/7/30 | nicole-macri; 16 points; 1; A+; 16/16/30 |
| ld-43-state-representative-2 | shaun-scott; 4 points; 1; A+; 4/4/30 | shaun-scott; 8 points; 1; A+; 8/8/30 |
| ld-43-state-senator | hannah-sabio-howell, jamie-pedersen; 4 points; 1/2; TIED; 8/8/30 | jamie-pedersen; 13 points; 13/21; B; 21/21/30 |
| ld-46-state-representative-1 | gerry-pollet; 3 points; 1/2; C; 6/7/30 | gerry-pollet; 9 points; 9/14; B; 14/15/30 |
| ld-46-state-representative-2 | darya-farivar; 7 points; 1; A+; 7/7/30 | darya-farivar; 17 points; 1; A+; 17/17/30 |
| ld-46-state-senator | javier-valdez; 6 points; 1; A+; 6/6/30 | javier-valdez; 15 points; 1; A+; 15/15/30 |
| seattle-city-council-5 | nilu-jenks; 8 points; 1; A+; 8/8/29 | nilu-jenks; 37/2 points; 37/40; A+; 20/20/36 |
| seattle-municipal-court-judge-5 | gabe-rothstein; 2 points; 1; A; 2/2/29 | gabe-rothstein; 17/2 points; 17/18; A+; 9/9/36 |
| seattle-proposition-1-library-levy | yes; 4 points; 1; A+; 4/4/29 | yes; 9 points; 1; A+; 9/9/36 |
| supreme-court-justice-1 | colleen-melody; 6 points; 1; A+; 6/6/29 | colleen-melody; 19 points; 1; A+; 19/19/36 |
| supreme-court-justice-3 | mike-diaz; 7/2 points; 7/12; C; 6/6/29 | mike-diaz; 19/2 points; 19/36; C; 18/18/36 |
| supreme-court-justice-5 | theo-angelis; 7/2 points; 7/10; B; 5/5/29 | theo-angelis; 12 points; 12/19; B; 19/19/36 |
| supreme-court-justice-7 | debra-l-stephens; 3 points; 1; A; 3/4/29 | debra-l-stephens; 12 points; 1; A+; 12/13/36 |
| us-house-7 | pramila-jayapal; 5 points; 1; A+; 5/6/29 | pramila-jayapal; 18 points; 1; A+; 18/19/36 |
| us-house-9 | adam-smith; 3 points; 3/4; A; 4/5/29 | adam-smith; 8 points; 8/9; A; 9/12/36 |

### e6a1b635: Expand the 2026 endorsement source panel (#67)

| Race | Before | After |
| --- | --- | --- |
| king-county-assessor | rob-foxcurran; 15/2 points; 15/26; C; 13/13/36 | rob-foxcurran; 15/2 points; 15/26; C; 13/13/42 |
| king-county-council-2 | rebecca-salda-a; 35/2 points; 7/8; A; 20/20/36 | rebecca-salda-a; 21 points; 7/8; A; 24/24/42 |
| king-county-council-8 | teresa-mosqueda; 21 points; 1; A+; 21/21/36 | teresa-mosqueda; 23 points; 1; A+; 23/23/42 |
| ld-11-state-representative-1 | david-hackney; 7 points; 7/11; B; 11/12/30 | david-hackney; 7 points; 7/11; B; 11/12/36 |
| ld-11-state-representative-2 | steve-bergquist; 8 points; 1; A+; 8/8/30 | steve-bergquist; 8 points; 1; A+; 8/8/36 |
| ld-32-state-representative-1 | danica-noble; 7 points; 7/11; B; 11/12/30 | danica-noble; 8 points; 2/3; B; 12/13/36 |
| ld-32-state-representative-2 | lauren-davis; 21/2 points; 21/34; B; 17/17/30 | lauren-davis; 21/2 points; 7/12; C; 18/18/36 |
| ld-32-state-senator | cindy-ryu; 21/2 points; 7/10; B; 15/15/30 | cindy-ryu; 23/2 points; 23/32; B; 16/16/36 |
| ld-34-state-representative-1 | brianna-k-thomas; 8 points; 1; A+; 8/8/30 | brianna-k-thomas; 8 points; 1; A+; 8/8/36 |
| ld-34-state-representative-2 | joe-fitzgibbon; 17 points; 17/18; A+; 18/18/30 | joe-fitzgibbon; 18 points; 18/19; A+; 19/19/36 |
| ld-34-state-senator | emily-alvarado; 15 points; 1; A+; 15/15/30 | emily-alvarado; 16 points; 1; A+; 16/16/36 |
| ld-36-state-representative-1 | julia-grant-reed; 17 points; 1; A+; 17/17/30 | julia-grant-reed; 17 points; 1; A+; 17/17/36 |
| ld-36-state-representative-2 | liz-berry; 13 points; 1; A+; 13/13/30 | liz-berry; 14 points; 1; A+; 14/14/36 |
| ld-36-state-senator | noel-c-frame; 10 points; 1; A+; 10/10/30 | noel-c-frame; 10 points; 1; A+; 10/10/36 |
| ld-37-state-representative-1 | sharon-tomiko-santos; 6 points; 3/5; B; 10/10/30 | kelabe-tewolde, sharon-tomiko-santos; 13/2 points; 1/2; TIED; 13/13/36 |
| ld-37-state-representative-2 | jaelynn-scott; 16 points; 1; A+; 16/16/30 | jaelynn-scott; 20 points; 1; A+; 20/20/36 |
| ld-37-state-senator | chipalo-street; 27/2 points; 9/10; A+; 15/16/30 | chipalo-street; 29/2 points; 29/32; A+; 16/17/36 |
| ld-43-state-representative-1 | nicole-macri; 16 points; 1; A+; 16/16/30 | nicole-macri; 17 points; 1; A+; 17/17/36 |
| ld-43-state-representative-2 | shaun-scott; 8 points; 1; A+; 8/8/30 | shaun-scott; 9 points; 1; A+; 9/9/36 |
| ld-43-state-senator | jamie-pedersen; 13 points; 13/21; B; 21/21/30 | jamie-pedersen; 13 points; 13/23; C; 23/23/36 |
| ld-46-state-representative-1 | gerry-pollet; 9 points; 9/14; B; 14/15/30 | gerry-pollet; 9 points; 9/16; C; 16/17/36 |
| ld-46-state-representative-2 | darya-farivar; 17 points; 1; A+; 17/17/30 | darya-farivar; 18 points; 1; A+; 18/18/36 |
| ld-46-state-senator | javier-valdez; 15 points; 1; A+; 15/15/30 | javier-valdez; 15 points; 1; A+; 15/15/36 |
| seattle-city-council-5 | nilu-jenks; 37/2 points; 37/40; A+; 20/20/36 | nilu-jenks; 43/2 points; 43/46; A+; 23/23/42 |
| seattle-municipal-court-judge-5 | gabe-rothstein; 17/2 points; 17/18; A+; 9/9/36 | gabe-rothstein; 17/2 points; 17/18; A+; 9/9/42 |
| seattle-proposition-1-library-levy | yes; 9 points; 1; A+; 9/9/36 | yes; 9 points; 1; A+; 9/9/42 |
| supreme-court-justice-1 | colleen-melody; 19 points; 1; A+; 19/19/36 | colleen-melody; 19 points; 1; A+; 19/19/42 |
| supreme-court-justice-3 | mike-diaz; 19/2 points; 19/36; C; 18/18/36 | jaime-michelle-hawk, mike-diaz; 19/2 points; 1/2; TIED; 19/19/42 |
| supreme-court-justice-5 | theo-angelis; 12 points; 12/19; B; 19/19/36 | theo-angelis; 13 points; 13/20; B; 20/20/42 |
| supreme-court-justice-7 | debra-l-stephens; 12 points; 1; A+; 12/13/36 | debra-l-stephens; 12 points; 1; A+; 12/13/42 |
| us-house-7 | pramila-jayapal; 18 points; 1; A+; 18/19/36 | pramila-jayapal; 19 points; 1; A+; 19/20/42 |
| us-house-9 | adam-smith; 8 points; 8/9; A; 9/12/36 | adam-smith; 8 points; 8/11; B; 11/14/42 |

### 5d9360de: Recheck drifted endorsement sources; propose daily verification (#323)

| Race | Before | After |
| --- | --- | --- |
| king-county-council-2 | rebecca-salda-a; 21 points; 7/8; A; 24/24/42 | rebecca-salda-a; 23 points; 23/26; A; 26/26/42 |
| king-county-council-8 | teresa-mosqueda; 23 points; 1; A+; 23/23/42 | teresa-mosqueda; 25 points; 1; A+; 25/25/42 |
| ld-32-state-representative-2 | lauren-davis; 21/2 points; 7/12; C; 18/18/36 | lauren-davis; 21/2 points; 21/38; C; 19/19/36 |
| ld-37-state-representative-1 | kelabe-tewolde, sharon-tomiko-santos; 13/2 points; 1/2; TIED; 13/13/36 | kelabe-tewolde; 17/2 points; 17/30; C; 15/15/36 |
| ld-37-state-representative-2 | jaelynn-scott; 20 points; 1; A+; 20/20/36 | jaelynn-scott; 22 points; 1; A+; 22/22/36 |
| ld-37-state-senator | chipalo-street; 29/2 points; 29/32; A+; 16/17/36 | chipalo-street; 29/2 points; 29/36; A; 18/19/36 |
| ld-43-state-senator | jamie-pedersen; 13 points; 13/23; C; 23/23/36 | jamie-pedersen; 13 points; 13/25; C; 25/25/36 |
| ld-46-state-representative-1 | gerry-pollet; 9 points; 9/16; C; 16/17/36 | gerry-pollet; 9 points; 9/17; C; 17/18/36 |
| ld-46-state-representative-2 | darya-farivar; 18 points; 1; A+; 18/18/36 | darya-farivar; 19 points; 1; A+; 19/19/36 |
| supreme-court-justice-3 | jaime-michelle-hawk, mike-diaz; 19/2 points; 1/2; TIED; 19/19/42 | jaime-michelle-hawk; 21/2 points; 21/40; C; 20/20/42 |
| us-house-7 | pramila-jayapal; 19 points; 1; A+; 19/20/42 | pramila-jayapal; 20 points; 1; A+; 20/21/42 |

## Exact August 5 additions (and October archive restore set)

| Publisher | Race | Choice |
| --- | --- | --- |
| sage-leaders | king-county-council-2 | king-county-council-2--rebecca-salda-a |
| sage-leaders | king-county-council-8 | king-county-council-8--teresa-mosqueda |
| sage-leaders | ld-46-state-representative-2 | ld-46-state-representative-2--darya-farivar |
| seattle-gay-news | king-county-council-2 | king-county-council-2--rebecca-salda-a |
| seattle-gay-news | ld-37-state-representative-2 | ld-37-state-representative-2--jaelynn-scott |
| seattle-gay-news | ld-37-state-senator | ld-37-state-senator--tatiana-brown |
| seattle-gay-news | ld-43-state-senator | ld-43-state-senator--hannah-sabio-howell |
| seattle-gay-news | us-house-7 | us-house-7--pramila-jayapal |
| seiu-775 | king-county-council-8 | king-county-council-8--teresa-mosqueda |
| transit-riders-union | ld-32-state-representative-2 | ld-32-state-representative-2--imraan-siddiqi |
| transit-riders-union | ld-37-state-representative-1 | ld-37-state-representative-1--kelabe-tewolde |
| transit-riders-union | ld-37-state-senator | ld-37-state-senator--tatiana-brown |
| transit-riders-union | ld-43-state-senator | ld-43-state-senator--hannah-sabio-howell |
| transit-riders-union | ld-46-state-representative-1 | ld-46-state-representative-1--ron-davis |
| ufcw-3000 | supreme-court-justice-3 | supreme-court-justice-3--jaime-michelle-hawk |
| washington-working-families-party | ld-37-state-representative-1 | ld-37-state-representative-1--kelabe-tewolde |
| washington-working-families-party | ld-37-state-representative-2 | ld-37-state-representative-2--jaelynn-scott |

## Certified-results inventory

Original 24: king-county-assessor, king-county-council-2, king-county-council-8, ld-11-state-representative-1, ld-11-state-representative-2, ld-34-state-representative-1, ld-34-state-representative-2, ld-34-state-senator, ld-36-state-representative-1, ld-36-state-representative-2, ld-36-state-senator, ld-37-state-representative-1, ld-37-state-representative-2, ld-37-state-senator, ld-43-state-representative-1, ld-43-state-representative-2, ld-43-state-senator, ld-46-state-representative-1, ld-46-state-representative-2, ld-46-state-senator, seattle-city-council-5, seattle-municipal-court-judge-5, seattle-proposition-1-library-levy, us-house-7.

| Added race | Authority total (including write-ins) | Advancing choices |
| --- | ---: | --- |
| ld-32-state-representative-1 | 40234 votes | ld-32-state-representative-1--keith-scully, ld-32-state-representative-1--danica-noble |
| ld-32-state-representative-2 | 37293 votes | ld-32-state-representative-2--lauren-davis, ld-32-state-representative-2--imraan-siddiqi |
| ld-32-state-senator | 40458 votes | ld-32-state-senator--cindy-ryu, ld-32-state-senator--jesse-salomon |
| supreme-court-justice-1 | 1746523 votes | supreme-court-justice-1--colleen-melody, supreme-court-justice-1--scott-edwards |
| supreme-court-justice-3 | 1739993 votes | supreme-court-justice-3--jaime-michelle-hawk, supreme-court-justice-3--david-stevens |
| supreme-court-justice-5 | 1739405 votes | supreme-court-justice-5--theo-angelis, supreme-court-justice-5--dave-larson |
| supreme-court-justice-7 | 1726149 votes | supreme-court-justice-7--debra-l-stephens, supreme-court-justice-7--todd-a-bloom |
| us-house-9 | 142356 votes | us-house-9--doug-basler, us-house-9--adam-smith |

## Bounded commit inventory

59 commits touched config/ or data/ other than data/analytics/ in the bounded range, with scorer-only #23 added. Full paths are preserved in [the complete commit inventory](commit-inventory.json). All eight canonical mutations are listed above: five real data batches, three metadata/contract-only mutations. Primary inventory: zero post-baseline mutations. Primary results: two. Source registry: same five data batches plus the three non-data contract mutations. Hosting pins are checked for the October regression/restoration. Calendar and page-only changes are explicitly handed to the companion page audit. General-only files are handed to the general audit. No claim here extends outside this bounded range or file domain.

| Commit | Date committed | Subject | Disposition |
| --- | --- | --- | --- |
| [41802854](https://github.com/shaug/seattle-election-guide/commit/41802854b802d737a9ad2f1792b541bb1818a14d) | 2026-07-20 | feat: automate source adapter refreshes (#22) | Source-adapter configuration for refresh; no canonical primary input changes. |
| [2ee98b15](https://github.com/shaug/seattle-election-guide/commit/2ee98b15649136d6a0116c198496b03be5ffdbd3) | 2026-07-20 | feat: expose category and overlap analysis (#23) | Scoring report adds organizational-overlap analysis; no weights, leaders, allocations, default scores changed. |
| [0a9b2632](https://github.com/shaug/seattle-election-guide/commit/0a9b2632fcba920e866adf6a6b09d82a7395b7f3) | 2026-07-20 | Complete 2026 primary source coverage (#26) | Entry: July 21 initial-site batch; 209 decisions added. |
| [4cce1737](https://github.com/shaug/seattle-election-guide/commit/4cce17375c71b1bf853a7f755f966fc3ae016d91) | 2026-07-20 | Add Sierra Club and broader LD endorsement coverage (#28) | Entry: July 21 initial-site batch; 81 decisions added and seven LD eligibility scopes broadened. |
| [6653dde3](https://github.com/shaug/seattle-election-guide/commit/6653dde37df4ff36615994736e332a87c3bdee3d) | 2026-07-20 | Compact the guide identity and responsive shell (#46) | No primary data delta: rendering/hosting declaration; page audit owns UI changes; primary archive pin checked. |
| [505ce616](https://github.com/shaug/seattle-election-guide/commit/505ce61690b9a06e3f9b7c5116b2f813d1e23301) | 2026-07-21 | feat: add Washington Stonewall primary endorsements (#53) | Entry: July 21 initial-site batch; 22 Stonewall decisions added. |
| [e6a1b635](https://github.com/shaug/seattle-election-guide/commit/e6a1b635289a936ecbe807994139876a58714931) | 2026-07-23 | Expand the 2026 endorsement source panel (#67) | Entry: July 23 six-source expansion; 35 decisions added. |
| [8c9b562c](https://github.com/shaug/seattle-election-guide/commit/8c9b562cb0765ed69ff9a4a34c4d42d371c2d96f) | 2026-07-24 | feat: define election archive manifest (#69) | Archive manifest foundation; current primary remains live, no endorsement/outcome delta. |
| [e9e3ee20](https://github.com/shaug/seattle-election-guide/commit/e9e3ee2065c93de4a7c7c949fca31e8d590d40c1) | 2026-07-24 | feat: add election-scoped guide routes | Routes only; no input/score/outcome delta. |
| [d6535bfb](https://github.com/shaug/seattle-election-guide/commit/d6535bfb884289442e50b21b162f08670fc16dab) | 2026-07-26 | feat: add stable source and category identities (#84) | No content delta: panel v3 transport codes/category contract; same source, eligibility, decisions and default scoring. |
| [da72b41a](https://github.com/shaug/seattle-election-guide/commit/da72b41a3e54a4e5ae922ba80ef9588465a1da46) | 2026-07-26 | feat: publish the personalized-lens calculation contract (#85) | No primary canonical/registry/inventory/results mutation; operational/configuration change screened. |
| [c3af33b3](https://github.com/shaug/seattle-election-guide/commit/c3af33b30283fa469700d79b3adcd632552931b2) | 2026-07-28 | Add a non-tallying comparison category kind to the personalization contract (#99) | No data delta: panel v4 comparison-category selectability; same membership/eligibility/decisions/default scoring; page/UI audit owns surface. |
| [bc8a7242](https://github.com/shaug/seattle-election-guide/commit/bc8a7242b5fc4ee0ff34a79707dc1c085feef710) | 2026-07-28 | Rename the guide's public name from Endorsement Guide to Elections Guide (#104) | No primary data delta: rendering/hosting declaration; page audit owns UI changes; primary archive pin checked. |
| [083c2152](https://github.com/shaug/seattle-election-guide/commit/083c2152b02b15c6072e500e9e1b6d0e558ccc35) | 2026-07-29 | UI polish pass: one cohesive site (brand, shell, tokens, meters, comparison bars) (#126) | No primary data delta: rendering/hosting declaration; page audit owns UI changes; primary archive pin checked. |
| [9228891b](https://github.com/shaug/seattle-election-guide/commit/9228891b54cee51a434fc15eefed81424818a0a2) | 2026-07-30 | feat: generate canonical election titles (#160) | No primary data delta: rendering/hosting declaration; page audit owns UI changes; primary archive pin checked. |
| [b9547233](https://github.com/shaug/seattle-election-guide/commit/b9547233acdecd4ad804dcade15a50f3c603a7a2) | 2026-07-31 | feat: soft-launch comparison route (#178) | No primary data delta: rendering/hosting declaration; page audit owns UI changes; primary archive pin checked. |
| [9f310ce6](https://github.com/shaug/seattle-election-guide/commit/9f310ce6c6fbe3398d3e32f3db43166caf6627f3) | 2026-08-01 | feat: activate Comparisons (#197) | No primary data delta: rendering/hosting declaration; page audit owns UI changes; primary archive pin checked. |
| [37449dca](https://github.com/shaug/seattle-election-guide/commit/37449dca629cf0fbcf5c5f292b255848db1eb0e4) | 2026-08-02 | feat: retire the generated PDF edition; keep the guide printable (#247) | No primary data delta: rendering/hosting declaration; page audit owns UI changes; primary archive pin checked. |
| [1ebe464c](https://github.com/shaug/seattle-election-guide/commit/1ebe464c4e1623de13d392633fd3671998bc8b22) | 2026-08-02 | feat: declare the election calendar as repository data (#262) | Calendar repository declarations, not endorsement/ballot/outcome changes. |
| [9ab9b270](https://github.com/shaug/seattle-election-guide/commit/9ab9b270b9332906a670e337e1e2c536f56087bb) | 2026-08-02 | feat: declare the live 2026 primary's results-capture windows (#265) | Results capture windows, not outcome publication. |
| [95895a37](https://github.com/shaug/seattle-election-guide/commit/95895a37f353d5207704e22cd32d38a736eb181e) | 2026-08-03 | docs: add the post-election retrospective checklist (#268) | No primary endorsement/outcome delta: calendar/authority operation; page audit owns any displayed date. |
| [f7c75e46](https://github.com/shaug/seattle-election-guide/commit/f7c75e461e8224ca0170bd75d8c29cf3edaa6ca1) | 2026-08-03 | feat: publish a subscribable calendar feed of voter-facing election dates (#293) | No primary endorsement/outcome delta: calendar/authority operation; page audit owns any displayed date. |
| [bff49348](https://github.com/shaug/seattle-election-guide/commit/bff49348fd67776e5a98c188f87cd5b808d48ef9) | 2026-08-03 | docs: formalize the agentic runtime as runbooks (#272) | No primary endorsement/outcome delta: calendar/authority operation; page audit owns any displayed date. |
| [5d9360de](https://github.com/shaug/seattle-election-guide/commit/5d9360de079727689136ce5e752c7e0cc7e2d322) | 2026-08-05 | Recheck drifted endorsement sources; propose daily verification (#323) | Entry: August 5 missed endorsements; 17 decisions added. |
| [888dc04b](https://github.com/shaug/seattle-election-guide/commit/888dc04b996538b341fb8b76a6bb3faafa1ea52a) | 2026-08-05 | chore: move one 2027 date to verify subscribed events update in place (#333) | No primary endorsement/outcome delta: calendar/authority operation; page audit owns any displayed date. |
| [fd1264b4](https://github.com/shaug/seattle-election-guide/commit/fd1264b41611e61d2c7146c76791fb06a076201d) | 2026-08-07 | chore: revert the temporary 2027 date used to verify subscribed updates (#334) | No primary endorsement/outcome delta: calendar/authority operation; page audit owns any displayed date. |
| [a1711252](https://github.com/shaug/seattle-election-guide/commit/a1711252cb443edb214a1935991c943f98a08987) | 2026-08-07 | feat(evidence): give counting authorities their own capture lane (#281) (#337) | Authority adapter/capture-lane setup; no published outcome data. |
| [0e984b13](https://github.com/shaug/seattle-election-guide/commit/0e984b1322366e6fb440fcf8f7eb64b6416b7bd2) | 2026-08-12 | docs(runbooks): write the endorsement discovery sweep (#363) | No primary endorsement/outcome delta: calendar/authority operation; page audit owns any displayed date. |
| [0a5119dd](https://github.com/shaug/seattle-election-guide/commit/0a5119dd9c423d3e59ed19c20d36927733e85ca9) | 2026-08-13 | fix(evidence): make captured official-authority bytes outlive their session (#372) | Provenance storage migration: official authority bytes now retained; no inventory, endorsements or outcomes changed. |
| [3133f910](https://github.com/shaug/seattle-election-guide/commit/3133f910f9db0a92fbd9b0fa5b49e9d218ae7e70) | 2026-08-16 | feat(ops): escalate calendar milestones whose promised artifact never appeared (O12 follow-up) (#386) | No primary endorsement/outcome delta: calendar/authority operation; page audit owns any displayed date. |
| [6a21e7fa](https://github.com/shaug/seattle-election-guide/commit/6a21e7fad8c26034739540a08ffe33e911687ebb) | 2026-08-16 | feat(analytics): archive zone rollups before Cloudflare's window drops them | No primary canonical/registry/inventory/results mutation; operational/configuration change screened. |
| [e006c5ca](https://github.com/shaug/seattle-election-guide/commit/e006c5ca99fe8602d6843b40ffd1fae26e588658) | 2026-08-19 | fix(calendar): correct primary certification offset and capture wa-2026-primary certified results (#407) | Capture only: King County and SOS certified evidence plus calendar certification offset; no results file until #413. Calendar surface referred to page audit. |
| [5f09f2c5](https://github.com/shaug/seattle-election-guide/commit/5f09f2c533d276b3d666b1881ab5b50e521d261b) | 2026-08-19 | feat(results): ingest wa-2026-primary certified results (#413) | Entry: August 19 first 24 certified race results. |
| [3fa04daf](https://github.com/shaug/seattle-election-guide/commit/3fa04daf3d2b47ba9e4627ff7566965fab862c15) | 2026-08-22 | wa-2026-primary: ingest Secretary of State totals for the eight cross-county races (#419) | Entry: September 13 remaining eight certified results; August 22 merge/deployment failure is not public date. |
| [78c1ef5a](https://github.com/shaug/seattle-election-guide/commit/78c1ef5a6bfe209318ecd060fccf795b34ea4e8b) | 2026-09-13 | chore(elections): initialize 2026 general (#426) | No primary data delta: general-election or verification input; delegated to general audit. |
| [8eae5a36](https://github.com/shaug/seattle-election-guide/commit/8eae5a3658563c159ffa2ff39858baada85c27a2) | 2026-09-13 | chore(elections): import the 2026 general ballot inventory (#427) | No primary data delta: general-election or verification input; delegated to general audit. |
| [301f20be](https://github.com/shaug/seattle-election-guide/commit/301f20be41cefbaa53214dc95768801f0431253a) | 2026-09-14 | Freeze the carried-forward 2026 general source panel (#430) | No primary data delta: general-election or verification input; delegated to general audit. |
| [2c154d70](https://github.com/shaug/seattle-election-guide/commit/2c154d70097c64cd9b51b1fd9007c890324a0f33) | 2026-09-15 | Complete initial 2026 general discovery sweep (#437) | No primary data delta: general-election or verification input; delegated to general audit. |
| [de3ba700](https://github.com/shaug/seattle-election-guide/commit/de3ba7008a4ed8ed129bcda2cf23ba7100bba997) | 2026-09-17 | feat: separate stable panel identity from registry audit hash (#438) | No data delta: registry identity compatibility metadata, same input semantics and scoring. |
| [edd76e2a](https://github.com/shaug/seattle-election-guide/commit/edd76e2a896137bcd60d366066639f811987d33e) | 2026-10-02 | feat: include Tech 4 Taxes in 2026 general endorsements (#466) | No primary data delta: general-election or verification input; delegated to general audit. |
| [c6a87adb](https://github.com/shaug/seattle-election-guide/commit/c6a87adbbf296bd525fded5e8548216221719455) | 2026-10-02 | data: refresh 2026 general endorsements (#475) | No primary data delta: general-election or verification input; delegated to general audit. |
| [a6537323](https://github.com/shaug/seattle-election-guide/commit/a6537323ca3bdb60e4008e971aa6fa13845ee6b0) | 2026-10-02 | build: cut staging to the 2026 general guide (#476) | Entry: October 3 first successful general cutover served old .2 primary archive. |
| [eab5867a](https://github.com/shaug/seattle-election-guide/commit/eab5867a55bf881349310a3417c9742e3c8e9da6) | 2026-10-03 | fix: replace endorsement pill with visible segments (#484) | No primary data delta: rendering/hosting declaration; page audit owns UI changes; primary archive pin checked. |
| [f426b23e](https://github.com/shaug/seattle-election-guide/commit/f426b23e81a1ec953e3eab38eefa748b9c41037e) | 2026-10-03 | Restore the final Meter v2 interaction (#487) | No primary data delta: rendering/hosting declaration; page audit owns UI changes; primary archive pin checked. |
| [8c62179e](https://github.com/shaug/seattle-election-guide/commit/8c62179ebf52570b51894bf6ad0c8cb6fe9447f7) | 2026-10-03 | fix: distinguish earliest ballot availability (#490) | No primary endorsement/outcome delta: calendar/authority operation; page audit owns any displayed date. |
| [f5c55f92](https://github.com/shaug/seattle-election-guide/commit/f5c55f9292dd0a363f19581e7626d97c2a555aae) | 2026-10-04 | fix: refresh general endorsements and prepare 2026-general.4 (#493) | No primary data delta: general-election or verification input; delegated to general audit. |
| [717d4403](https://github.com/shaug/seattle-election-guide/commit/717d440325917c88a491828876eb6e1e4875b962) | 2026-10-04 | feat: declare and watch results ingest milestones (#498) | No primary endorsement/outcome delta: calendar/authority operation; page audit owns any displayed date. |
| [f9ee5918](https://github.com/shaug/seattle-election-guide/commit/f9ee59186da21133820c085c70b6e998db987eac) | 2026-10-10 | fix: reconcile general election endorsement coverage (#510) | No primary data delta: general-election or verification input; delegated to general audit. |
| [9a7aa440](https://github.com/shaug/seattle-election-guide/commit/9a7aa44011688d93d776b355c589f963b19fe75a) | 2026-10-11 | fix(ops): simplify production checks and retire daily analytics PRs (#513) | No primary canonical/registry/inventory/results mutation; operational/configuration change screened. |
| [0147fa03](https://github.com/shaug/seattle-election-guide/commit/0147fa03dc0ed928f412ecaff2761971245f928f) | 2026-10-11 | docs: assess additional general election endorsement evidence (#515) | No primary data delta: general-election or verification input; delegated to general audit. |
| [5b6aeb6d](https://github.com/shaug/seattle-election-guide/commit/5b6aeb6df914a0bc807f5a1190653bacc6ddc36b) | 2026-10-11 | feat: automate recurring endorsement verification (#502) | No primary data delta: general-election or verification input; delegated to general audit. |
| [9d193bbe](https://github.com/shaug/seattle-election-guide/commit/9d193bbe344a506f5545adb011e104534f9f137b) | 2026-10-11 | Restore the completed primary archive and reject retired meters (#526) | Entry: October 11 final primary archive restored. |
| [06e5ccb2](https://github.com/shaug/seattle-election-guide/commit/06e5ccb2c81d6d9c1ca5876eba5997da23afaec3) | 2026-10-12 | feat: add verified general-election sources and Tech 4 Taxes decision | No primary data delta: general-election or verification input; delegated to general audit. |
| [f5852664](https://github.com/shaug/seattle-election-guide/commit/f585266404ab5be84dd1258564fe03d1b673c4bb) | 2026-10-16 | fix: repair three live endorsement source checks (#544) | No primary data delta: general-election or verification input; delegated to general audit. |
| [e5eeb960](https://github.com/shaug/seattle-election-guide/commit/e5eeb9606c7018a7e8fcb1412933ffd3e7bc0638) | 2026-10-16 | chore(data): apply approved October 16 endorsements (#543) | No primary data delta: general-election or verification input; delegated to general audit. |
| [f696a936](https://github.com/shaug/seattle-election-guide/commit/f696a936fcda5dddb6347f6160a158491dbe0358) | 2026-10-16 | Verify Stranger and WEA; add two missed endorsements (#546) | No primary data delta: general-election or verification input; delegated to general audit. |
| [a1a83b5f](https://github.com/shaug/seattle-election-guide/commit/a1a83b5f1c09d7297a6100e3ac321b0e5034bf52) | 2026-10-16 | build: prepare 2026-general.8 publication (#548) | No primary data delta: rendering/hosting declaration; page audit owns UI changes; primary archive pin checked. |
| [46cd5d63](https://github.com/shaug/seattle-election-guide/commit/46cd5d631d719b41b7517322e1f892744a20e0d2) | 2026-10-16 | feat: broaden Updates and simplify How this works (#552) | No primary data delta: general-election or verification input; delegated to general audit. |
| [da307d6f](https://github.com/shaug/seattle-election-guide/commit/da307d6f4c695471ec5a025a4226824de5ffbbc5) | 2026-10-16 | build: prepare 2026-general.9 publication (#554) | No primary data delta: rendering/hosting declaration; page audit owns UI changes; primary archive pin checked. |

## Verification artifacts

- primary-data-changes.json: all eight canonical before/after comparisons; all 364 added records and source-registry/evidence-URL deltas; exact scoring differences for every affected race.
- primary-initial-site-scores.json: .1 → first public website score/count comparison for every race.
- primary-results-changes.json: all 32 results and eight additions; original-24 invariance check true.
- [the complete commit inventory](commit-inventory.json): complete bounded config/data commit inventory and dispositions.
- Published primary release ZIPs `.1`, `.2`, and `.3`: canonical and consensus JSON were downloaded and independently compared; the evidence above records the semantic differences.
- `commit-inventory.json` and `publications.json`: successful production deployment/status and release evidence used for dates.

Candidate validation is recorded in the parent history audit; the comparisons above are independent of renderer tests.
