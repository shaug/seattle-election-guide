# General-election data history audit

Bounded range: first public release `2026-general.1` through frozen main `5251de04a3ac09804eff2983fc67e8b6b0cc71b0`. All Git mutation inventories use first-parent history. The authored Updates entries are checked against the immutable source and release records.

## Result

Exactly five canonical general-data input mutations occur after first publication. They add 266 source/race records and replace three existing records, with no removals: 614 +3 +64 +22 +175 +2 =880. General inventory and scoring rules remain unchanged. All current authored data entries map to these five batches; no unrepresented public choice, eligibility or ballot delta was found. Source/evidence changes below belong to the same batches and their linked source-by-source review records. Recommended short prose additions are listed separately; they do not imply another data batch.

Seven independently downloaded public ZIPs (.1, .4, .5, .6, .7, .8, .9) exactly match each tag’s committed canonical dataset bytes. Recalculated support, grade, counts, comparisons and category breakdown match all52 race rows of each published consensus report: zero discrepancies. The scorer is unchanged in the entire bounded range. Tags .2/.3 and .9 have unchanged canonical bytes/registry/inventory relative to their predecessors.

## Publication-date anchors

| Release | Public downloadable publication, America/Los_Angeles | Data / current entry |
| --- | --- | --- |
| 2026-general.1 | October3 01:27:20 PDT; website October3 07:27:19 PDT | First general guide:614 decisions from34 represented source blocks /43 active sources,52 races |
| 2026-general.4 | October4 08:24:56 PDT | Added WashingtonCAN’s three initiative endorsements |
| 2026-general.5 | October11 17:29:23 PDT | Added64 endorsements from eight organizations; separate King County Democrats coendorsement entry |
| 2026-general.6 | October12 10:47:06 PDT | Added three sources and22 decisions |
| 2026-general.7 | October16 11:41:31 PDT | Added175 source decisions and revised two endorsements |
| 2026-general.8 | October16 12:21:34 PDT | Added two previously unrecorded endorsements |
| 2026-general.9 | October16 14:54:22 PDT | Updates/rendering release, no choice/source-data delta |

These are release publication dates, not organization announcement dates or commit dates. The October10 reconciliation commit did not publish .5 until October11. Date grounding: GitHub Release API (`published_at`) and the deployment evidence retained in `commit-inventory.json` and `publications.json` for the first website.

## Batch inventory and current-entry coverage

### general.4: f5c55f92

[Committed batch](https://github.com/shaug/seattle-election-guide/commit/f5c55f9292dd0a363f19581e7626d97c2a555aae); 614 → 617 decisions; {'added': 3}. 3 of52 exact scoring/count/comparison rows change. Inventory unchanged: True.

Current entry: Added WashingtonCAN’s three initiative endorsements.. Linked review: [GENERAL_REFRESH_2026-10-03.md](https://github.com/shaug/seattle-election-guide/blob/2026-general.4/docs/GENERAL_REFRESH_2026-10-03.md).

Additions by source: washington-community-action-network +3.

Changed active source projections:
- 11th-district-democrats: `{"evidence_url": ["http://eepurl.com/QAju_Mt-ye", "https://us17.campaign-archive.com/?u=c75f17fe2b6e715cad36922d4&id=c0097e484d"]}`.
- planned-parenthood-alliance-advocates: `{"coverage_gap_note": ["The official URL replaces the primary registry's third-party discovery lead, but the direct access gap is explicit and no choices affected panel classification.", "HTTP 403; access-restricted disposition preserved."]}`.
- seattle-subway: `{"evidence_url": ["https://www.seattlesubway.org/election-endorsements/", "https://seattlesubway.org/election-endorsements/"], "coverage_gap_note": ["No official 2026 general-election publication was located; the primary recommendations were not reused as general-election evidence.", "Official publication still explicitly describes the August 2026 primary; not reused."]}`.
- sierra-club-washington: `{"coverage_gap_note": ["The primary-specific publication was not assumed to be general-election evidence; the access gap is explicit.", "HTTP 200 contains an Incapsula access challenge; access-restricted disposition preserved."]}`.
- the-stranger: `{"coverage_gap_note": ["No official 2026 general-election guide was located. The primary publication was not reused as general-election evidence.", "Archive still leads with the 2026 primary guide; no general guide found."]}`.
- the-urbanist: `{"coverage_gap_note": ["No separate or updated official 2026 general-election publication was located.", "Primary-only guide; supplemental official elections-committee page also links only the 2026 primary."]}`.
- washington-bus: `{"coverage_gap_note": ["No official 2026 general-election endorsement section was located.", "Official page still labels its 2026 endorsements PRIMARY; older 2025 general list not reused."]}`.
- washington-for-peace-and-justice: `{"coverage_gap_note": ["No official 2026 general-election endorsement publication was located.", "Official site has no current endorsement publication located."]}`.
- washington-state-democrats: `{"coverage_gap_note": ["The access gap is explicit; county and legislative-district publications are tracked as separate sources.", "HTTP 403; access-restricted disposition preserved."]}`.
- washington-stonewall-democrats: `{"coverage_gap_note": ["No clean, directly verifiable official-site general-election publication was available at the research cutoff.", "Official Facebook response exposed no reconstructable post content; access-restricted disposition preserved."]}`.

Existing decision evidence fields changed for 614 records; counts by source/field:

- 11th-district-democrats: {'evidence_url': 15, 'evidence_locator': 15}.
- 32nd-district-democrats: {'evidence_locator': 21}.
- 34th-district-democrats: {'evidence_locator': 23}.
- 36th-district-democrats: {'evidence_locator': 24}.
- 37th-district-democrats: {'evidence_locator': 25}.
- 43rd-district-democrats: {'evidence_locator': 25}.
- 46th-district-democrats: {'evidence_locator': 23}.
- aft-washington: {'evidence_locator': 25}.
- alliance-for-gun-responsibility: {'evidence_locator': 23}.
- environmental-climate-caucus-wa-democrats: {'evidence_locator': 10}.
- fuse-washington: {'evidence_locator': 14}.
- king-county-democrats: {'evidence_locator': 34}.
- mlk-labor: {'evidence_locator': 6}.
- nwpc-washington: {'evidence_locator': 26}.
- oneamerica-votes: {'evidence_locator': 15}.
- protec17: {'evidence_locator': 25}.
- sage-leaders: {'evidence_locator': 13}.
- seattle-democratic-socialists: {'evidence_locator': 1}.
- seattle-gay-news: {'evidence_locator': 7}.
- seattle-times-editorial-board: {'evidence_locator': 5}.
- seiu-775: {'evidence_locator': 29}.
- seiu-925: {'evidence_locator': 33}.
- tech-4-housing: {'evidence_locator': 3}.
- tech-4-taxes: {'evidence_locator': 6}.
- transit-riders-union: {'evidence_locator': 8}.
- ufcw-3000: {'evidence_locator': 25}.
- washington-bikes: {'evidence_locator': 20}.
- washington-community-action-network: {'evidence_locator': 2}.
- washington-conservation-action: {'evidence_locator': 25}.
- washington-education-association: {'evidence_locator': 19}.
- washington-housing-alliance: {'evidence_locator': 30}.
- washington-state-building-trades: {'evidence_locator': 19}.
- washington-state-labor-council: {'evidence_locator': 30}.
- washington-working-families-party: {'evidence_locator': 5}.

Exact score/count changes (leader; points; share; grade; explicit/covered/eligible):

| Race | Before | After |
| --- | --- | --- |
| initiative-26-001 | no; 17 points; share 1; A+; 17/17/42 | no; 18 points; share 1; A+; 18/18/42 |
| initiative-26-638 | no; 15 points; share 1; A+; 15/15/42 | no; 16 points; share 1; A+; 16/16/42 |
| initiative-26-645 | no; 15 points; share 1; A+; 15/15/42 | no; 16 points; share 1; A+; 16/16/42 |

### general.5: f9ee5918

[Committed batch](https://github.com/shaug/seattle-election-guide/commit/f9ee59186da21133820c085c70b6e998db987eac); 617 → 681 decisions; {'added': 64, 'replaced': 1}. 32 of52 exact scoring/count/comparison rows change. Inventory unchanged: True.

Current entry: Added 64 endorsements from eight organizations.. Linked review: [GENERAL_RECONCILIATION_2026-10-10.md](https://github.com/shaug/seattle-election-guide/blob/2026-general.5/docs/GENERAL_RECONCILIATION_2026-10-10.md).

Additions by source: king-county-democrats +3, oneamerica-votes +2, tech-4-housing +10, tech-4-taxes +4, the-stranger +31, washington-bus +7, washington-community-action-network +2, washington-working-families-party +5.

Replacement: king-county-democrats / ld-32-state-representative-2: `{"status": "endorsed", "candidate_ids": ["ld-32-state-representative-2--lauren-davis"], "allocation": {"ld-32-state-representative-2--lauren-davis": "1"}}` → `{"status": "dual_endorsement", "candidate_ids": ["ld-32-state-representative-2--lauren-davis", "ld-32-state-representative-2--imraan-siddiqi"], "allocation": {"ld-32-state-representative-2--imraan-siddiqi": "1/2", "ld-32-state-representative-2--lauren-davis": "1/2"}}`.

Changed active source projections:
- tech-4-housing: `{"evidence_url": ["https://bsky.app/profile/tech4housing.org/post/3mpkb7wcjok2z", "https://www.tech4housing.org/endorsements"]}`.
- the-stranger: `{"evidence_url": ["https://www.thestranger.com/category/election-endorsements/", "https://www.thestranger.com/news/the-stranger-election-control-board-2026-general-election-cheat-sheet/"], "contribution_status": ["coverage_gap", "contributing"], "coverage_gap_status": ["not_found", null], "coverage_gap_note": ["Archive still leads with the 2026 primary guide; no general guide found.", null]}`.
- washington-bus: `{"contribution_status": ["coverage_gap", "contributing"], "coverage_gap_status": ["not_found", null], "coverage_gap_note": ["Official page still labels its 2026 endorsements PRIMARY; older 2025 general list not reused.", null]}`.
- washington-working-families-party: `{"evidence_url": ["https://workingfamilies.org/state/washington/", "https://workingfamilies.org/candidates/"]}`.

Existing decision evidence fields changed for 68 records; counts by source/field:

- king-county-democrats: {'evidence_locator': 34, 'requires_review': 1}.
- oneamerica-votes: {'evidence_locator': 15}.
- tech-4-housing: {'evidence_url': 3, 'evidence_locator': 3}.
- tech-4-taxes: {'evidence_locator': 6}.
- washington-community-action-network: {'evidence_locator': 5}.
- washington-working-families-party: {'evidence_url': 5, 'evidence_locator': 5}.

Exact score/count changes (leader; points; share; grade; explicit/covered/eligible):

| Race | Before | After |
| --- | --- | --- |
| initiative-26-001 | no; 18 points; share 1; A+; 18/18/42 | no; 21 points; share 1; A+; 21/21/42 |
| initiative-26-638 | no; 16 points; share 1; A+; 16/16/42 | no; 19 points; share 1; A+; 19/19/42 |
| initiative-26-645 | no; 16 points; share 1; A+; 16/16/42 | no; 19 points; share 1; A+; 19/19/42 |
| king-county-assessor | rob-foxcurran; 10 points; share 1; A+; 10/10/42 | rob-foxcurran; 12 points; share 1; A+; 12/12/42 |
| king-county-council-2 | rebecca-saldana; 18 points; share 6/7; A; 21/21/42 | rebecca-saldana; 21 points; share 7/8; A; 24/24/42 |
| king-county-council-8 | teresa-mosqueda; 20 points; share 1; A+; 20/20/42 | teresa-mosqueda; 23 points; share 1; A+; 23/23/42 |
| king-county-district-court-west-judge-1 | nyjat-rose-akins; 5 points; share 5/8; B; 8/8/42 | nyjat-rose-akins; 5 points; share 5/9; C; 9/9/42 |
| ld-11-state-representative-1 | david-hackney; 8 points; share 4/5; A; 10/10/36 | david-hackney; 8 points; share 8/11; B; 11/11/36 |
| ld-32-state-representative-1 | danica-noble; 21/2 points; share 21/32; B; 16/16/36 | danica-noble; 13 points; share 13/20; B; 20/20/36 |
| ld-32-state-representative-2 | lauren-davis; 21/2 points; share 21/34; B; 17/17/36 | lauren-davis; 10 points; share 10/19; C; 19/19/36 |
| ld-32-state-senator | cindy-ryu; 11 points; share 11/17; B; 17/17/36 | cindy-ryu; 12 points; share 2/3; B; 18/18/36 |
| ld-34-state-representative-2 | joe-fitzgibbon; 14 points; share 14/15; A+; 15/15/36 | joe-fitzgibbon; 15 points; share 15/16; A+; 16/16/36 |
| ld-36-state-senator | noel-c-frame; 11 points; share 1; A+; 11/11/36 | noel-c-frame; 13 points; share 1; A+; 13/13/36 |
| ld-37-state-representative-1 | kelabe-tewolde; 21/2 points; share 21/34; B; 17/17/36 | kelabe-tewolde; 27/2 points; share 27/40; B; 20/20/36 |
| ld-37-state-representative-2 | jaelynn-scott; 23 points; share 1; A+; 23/23/36 | jaelynn-scott; 26 points; share 1; A+; 26/26/36 |
| ld-37-state-senator | chipalo-street; 33/2 points; share 33/40; A; 20/20/36 | chipalo-street; 35/2 points; share 35/46; A; 23/23/36 |
| ld-43-state-representative-1 | nicole-macri; 14 points; share 1; A+; 14/14/36 | nicole-macri; 15 points; share 1; A+; 15/15/36 |
| ld-43-state-representative-2 | shaun-scott; 6 points; share 1; A+; 6/6/36 | shaun-scott; 7 points; share 1; A+; 7/7/36 |
| ld-43-state-senator | jamie-pedersen; 13 points; share 13/20; B; 20/20/36 | jamie-pedersen; 14 points; share 7/12; C; 24/24/36 |
| ld-46-state-representative-1 | gerry-pollet; 25/2 points; share 25/26; A+; 13/13/36 | gerry-pollet; 29/2 points; share 29/32; A+; 16/16/36 |
| ld-46-state-representative-2 | darya-farivar; 14 points; share 1; A+; 14/14/36 | darya-farivar; 16 points; share 1; A+; 16/16/36 |
| ld-46-state-senator | javier-valdez; 15 points; share 1; A+; 15/15/36 | javier-valdez; 16 points; share 1; A+; 16/16/36 |
| seattle-city-council-5 | nilu-jenks; 20 points; share 20/21; A+; 21/21/42 | nilu-jenks; 23 points; share 23/24; A+; 24/24/42 |
| seattle-municipal-court-judge-5 | gabe-rothstein; 19/2 points; share 19/20; A+; 10/10/42 | gabe-rothstein; 23/2 points; share 23/24; A+; 12/12/42 |
| seattle-proposition-1-transit | yes; 8 points; share 1; A+; 8/8/42 | yes; 10 points; share 1; A+; 10/10/42 |
| supreme-court-justice-1 | colleen-melody; 20 points; share 1; A+; 20/20/42 | colleen-melody; 21 points; share 1; A+; 21/21/42 |
| supreme-court-justice-3 | jaime-michelle-hawk; 20 points; share 1; A+; 20/20/42 | jaime-michelle-hawk; 21 points; share 1; A+; 21/21/42 |
| supreme-court-justice-4 | ian-birk; 17 points; share 1; A+; 17/17/42 | ian-birk; 18 points; share 1; A+; 18/18/42 |
| supreme-court-justice-5 | theo-angelis; 18 points; share 1; A+; 18/18/42 | theo-angelis; 19 points; share 1; A+; 19/19/42 |
| supreme-court-justice-7 | debra-l-stephens; 16 points; share 1; A+; 16/16/42 | debra-l-stephens; 17 points; share 1; A+; 17/17/42 |
| us-house-7 | pramila-jayapal; 18 points; share 1; A+; 18/18/42 | pramila-jayapal; 19 points; share 1; A+; 19/19/42 |
| us-house-9 | adam-smith; 6 points; share 1; A+; 6/9/42 | adam-smith; 7 points; share 1; A+; 7/10/42 |

### general.6: 06e5ccb2

[Committed batch](https://github.com/shaug/seattle-election-guide/commit/06e5ccb2c81d6d9c1ca5876eba5997da23afaec3); 681 → 703 decisions; {'added': 22}. 52 of52 exact scoring/count/comparison rows change. Inventory unchanged: True.

Current entry: Added three sources and 22 decisions.. Linked review: [GENERAL_ADDITIONS_2026-10-12.md](https://github.com/shaug/seattle-election-guide/blob/2026-general.6/docs/GENERAL_ADDITIONS_2026-10-12.md).

Additions by source: citizens-against-aipac-corruption +1, nondriver-action +4, tech-4-taxes +1, young-democrats-of-washington +16.

Changed active source projections:
- citizens-against-aipac-corruption: `{"name": [null, "Citizens Against AIPAC Corruption (Track AIPAC)"], "reporting_category_id": [null, "rights_representation"], "selection_category_ids": [null, ["rights_representation"]], "code": [null, "caac"], "panel_role": [null, "consensus"], "organization_url": [null, "https://citizensagainstaipac.com/"], "eligibility": [null, {"jurisdiction_ids": [], "kind": "all_seattle_ballot_races", "rationale": "A national organization with general geographic scope. Its current program is federal: admit only directly published, reviewed Seattle-intersecting congressional decisions; do not infer state/local choices or import recommendations from separate publishers."}], "overlap_group_ids": [null, []], "publisher_id": [null, null], "evidence_url": [null, "https://www.trackaipac.com/endorsements"], "contribution_status": [null, "contributing"], "coverage_gap_status": [null, null], "coverage_gap_note": [null, null]}`.
- nondriver-action: `{"name": [null, "Nondriver Action"], "reporting_category_id": [null, "transportation_urbanism"], "selection_category_ids": [null, ["rights_representation", "transportation_urbanism"]], "code": [null, "nact"], "panel_role": [null, "consensus"], "organization_url": [null, "https://ndaction.org/"], "eligibility": [null, {"jurisdiction_ids": [], "kind": "all_seattle_ballot_races", "rationale": "Use only explicit, reviewed organizational decisions for races on the Seattle ballot."}], "overlap_group_ids": [null, ["nondriver-affiliation"]], "publisher_id": [null, null], "evidence_url": [null, "https://ndaction.org/2026-endorsements/"], "contribution_status": [null, "contributing"], "coverage_gap_status": [null, null], "coverage_gap_note": [null, null]}`.
- young-democrats-of-washington: `{"name": [null, "Young Democrats of Washington"], "reporting_category_id": [null, "democratic_party"], "selection_category_ids": [null, ["democratic_party"]], "code": [null, "ydwa"], "panel_role": [null, "consensus"], "organization_url": [null, "https://www.instagram.com/youngdemswa/"], "eligibility": [null, {"jurisdiction_ids": [], "kind": "all_seattle_ballot_races", "rationale": "Use only explicit, reviewed organizational decisions for races on the Seattle ballot."}], "overlap_group_ids": [null, []], "publisher_id": [null, null], "evidence_url": [null, "https://www.instagram.com/p/DeQTz0cgTzM/"], "contribution_status": [null, "contributing"], "coverage_gap_status": [null, null], "coverage_gap_note": [null, null]}`.

Existing decision evidence fields changed for 0 records; counts by source/field:

- None.

Exact score/count changes (leader; points; share; grade; explicit/covered/eligible):

| Race | Before | After |
| --- | --- | --- |
| court-of-appeals-division-1-district-1-judge-5 | none; None points; share None; Insufficient; 0/0/42 | none; None points; share None; Insufficient; 0/0/45 |
| court-of-appeals-division-1-district-1-judge-6 | none; None points; share None; Insufficient; 0/0/42 | none; None points; share None; Insufficient; 0/0/45 |
| initiative-26-001 | no; 21 points; share 1; A+; 21/21/42 | no; 22 points; share 1; A+; 22/22/45 |
| initiative-26-638 | no; 19 points; share 1; A+; 19/19/42 | no; 20 points; share 1; A+; 20/20/45 |
| initiative-26-645 | no; 19 points; share 1; A+; 19/19/42 | no; 20 points; share 1; A+; 20/20/45 |
| king-county-assessor | rob-foxcurran; 12 points; share 1; A+; 12/12/42 | rob-foxcurran; 12 points; share 1; A+; 12/12/45 |
| king-county-council-2 | rebecca-saldana; 21 points; share 7/8; A; 24/24/42 | rebecca-saldana; 45/2 points; share 45/52; A; 26/26/45 |
| king-county-council-4 | jorge-l-baron; 14 points; share 1; A+; 14/14/42 | jorge-l-baron; 14 points; share 1; A+; 14/14/45 |
| king-county-council-8 | teresa-mosqueda; 23 points; share 1; A+; 23/23/42 | teresa-mosqueda; 25 points; share 1; A+; 25/25/45 |
| king-county-director-of-elections | julie-wise; 5 points; share 1; A+; 5/5/42 | julie-wise; 5 points; share 1; A+; 5/5/45 |
| king-county-district-court-west-judge-1 | nyjat-rose-akins; 5 points; share 5/9; C; 9/9/42 | nyjat-rose-akins; 5 points; share 5/9; C; 9/9/45 |
| king-county-district-court-west-judge-2 | none; None points; share None; Insufficient; 0/0/42 | none; None points; share None; Insufficient; 0/0/45 |
| king-county-district-court-west-judge-3 | none; None points; share None; Insufficient; 0/0/42 | none; None points; share None; Insufficient; 0/0/45 |
| king-county-district-court-west-judge-4 | none; None points; share None; Insufficient; 0/0/42 | none; None points; share None; Insufficient; 0/0/45 |
| king-county-district-court-west-judge-5 | none; None points; share None; Insufficient; 0/0/42 | none; None points; share None; Insufficient; 0/0/45 |
| king-county-prosecuting-attorney | leesa-manion; 11 points; share 1; A+; 11/11/42 | leesa-manion; 11 points; share 1; A+; 11/11/45 |
| ld-11-state-representative-1 | david-hackney; 8 points; share 8/11; B; 11/11/36 | david-hackney; 8 points; share 8/11; B; 11/11/39 |
| ld-11-state-representative-2 | steve-bergquist; 7 points; share 1; A+; 7/7/36 | steve-bergquist; 7 points; share 1; A+; 7/7/39 |
| ld-32-state-representative-1 | danica-noble; 13 points; share 13/20; B; 20/20/36 | danica-noble; 27/2 points; share 9/14; B; 21/21/39 |
| ld-32-state-representative-2 | lauren-davis; 10 points; share 10/19; C; 19/19/36 | lauren-davis, imraan-siddiqi; 10 points; share 1/2; TIED; 20/20/39 |
| ld-32-state-senator | cindy-ryu; 12 points; share 2/3; B; 18/18/36 | cindy-ryu; 13 points; share 13/19; B; 19/19/39 |
| ld-34-state-representative-1 | brianna-k-thomas; 8 points; share 1; A+; 8/8/36 | brianna-k-thomas; 8 points; share 1; A+; 8/8/39 |
| ld-34-state-representative-2 | joe-fitzgibbon; 15 points; share 15/16; A+; 16/16/36 | joe-fitzgibbon; 15 points; share 15/16; A+; 16/16/39 |
| ld-34-state-senator | emily-alvarado; 15 points; share 1; A+; 15/15/36 | emily-alvarado; 15 points; share 1; A+; 15/15/39 |
| ld-36-state-representative-1 | julia-grant-reed; 16 points; share 1; A+; 16/16/36 | julia-grant-reed; 16 points; share 1; A+; 16/16/39 |
| ld-36-state-representative-2 | liz-berry; 13 points; share 1; A+; 13/13/36 | liz-berry; 13 points; share 1; A+; 13/13/39 |
| ld-36-state-senator | noel-c-frame; 13 points; share 1; A+; 13/13/36 | noel-c-frame; 13 points; share 1; A+; 13/13/39 |
| ld-37-state-representative-1 | kelabe-tewolde; 27/2 points; share 27/40; B; 20/20/36 | kelabe-tewolde; 27/2 points; share 9/14; B; 21/21/39 |
| ld-37-state-representative-2 | jaelynn-scott; 26 points; share 1; A+; 26/26/36 | jaelynn-scott; 27 points; share 1; A+; 27/27/39 |
| ld-37-state-senator | chipalo-street; 35/2 points; share 35/46; A; 23/23/36 | chipalo-street; 35/2 points; share 35/46; A; 23/23/39 |
| ld-43-state-representative-1 | nicole-macri; 15 points; share 1; A+; 15/15/36 | nicole-macri; 15 points; share 1; A+; 15/15/39 |
| ld-43-state-representative-2 | shaun-scott; 7 points; share 1; A+; 7/7/36 | shaun-scott; 7 points; share 1; A+; 7/7/39 |
| ld-43-state-senator | jamie-pedersen; 14 points; share 7/12; C; 24/24/36 | jamie-pedersen; 29/2 points; share 29/50; C; 25/25/39 |
| ld-46-state-representative-1 | gerry-pollet; 29/2 points; share 29/32; A+; 16/16/36 | gerry-pollet; 31/2 points; share 31/34; A+; 17/17/39 |
| ld-46-state-representative-2 | darya-farivar; 16 points; share 1; A+; 16/16/36 | darya-farivar; 16 points; share 1; A+; 16/16/39 |
| ld-46-state-senator | javier-valdez; 16 points; share 1; A+; 16/16/36 | javier-valdez; 17 points; share 1; A+; 17/17/39 |
| seattle-city-council-5 | nilu-jenks; 23 points; share 23/24; A+; 24/24/42 | nilu-jenks; 25 points; share 25/26; A+; 26/26/45 |
| seattle-municipal-court-judge-1 | cat-mcdowall; 4 points; share 1; A+; 4/4/42 | cat-mcdowall; 4 points; share 1; A+; 4/4/45 |
| seattle-municipal-court-judge-2 | katharine-edwards; 8 points; share 1; A+; 8/8/42 | katharine-edwards; 8 points; share 1; A+; 8/8/45 |
| seattle-municipal-court-judge-3 | pooja-vaddadi; 6 points; share 1; A+; 6/6/42 | pooja-vaddadi; 6 points; share 1; A+; 6/6/45 |
| seattle-municipal-court-judge-4 | anita-crawford-willis; 2 points; share 1; A; 2/2/42 | anita-crawford-willis; 2 points; share 1; A; 2/2/45 |
| seattle-municipal-court-judge-5 | gabe-rothstein; 23/2 points; share 23/24; A+; 12/12/42 | gabe-rothstein; 23/2 points; share 23/24; A+; 12/12/45 |
| seattle-municipal-court-judge-6 | shantrice-anderson; 8 points; share 1; A+; 8/8/42 | shantrice-anderson; 8 points; share 1; A+; 8/8/45 |
| seattle-municipal-court-judge-7 | damon-shadid; 1 points; share 1; Insufficient; 1/1/42 | damon-shadid; 1 points; share 1; Insufficient; 1/1/45 |
| seattle-proposition-1-transit | yes; 10 points; share 1; A+; 10/10/42 | yes; 11 points; share 1; A+; 11/11/45 |
| supreme-court-justice-1 | colleen-melody; 21 points; share 1; A+; 21/21/42 | colleen-melody; 21 points; share 1; A+; 21/21/45 |
| supreme-court-justice-3 | jaime-michelle-hawk; 21 points; share 1; A+; 21/21/42 | jaime-michelle-hawk; 22 points; share 1; A+; 22/22/45 |
| supreme-court-justice-4 | ian-birk; 18 points; share 1; A+; 18/18/42 | ian-birk; 18 points; share 1; A+; 18/18/45 |
| supreme-court-justice-5 | theo-angelis; 19 points; share 1; A+; 19/19/42 | theo-angelis; 19 points; share 1; A+; 19/19/45 |
| supreme-court-justice-7 | debra-l-stephens; 17 points; share 1; A+; 17/17/42 | debra-l-stephens; 17 points; share 1; A+; 17/17/45 |
| us-house-7 | pramila-jayapal; 19 points; share 1; A+; 19/19/42 | pramila-jayapal; 21 points; share 1; A+; 21/21/45 |
| us-house-9 | adam-smith; 7 points; share 1; A+; 7/10/42 | adam-smith; 8 points; share 1; A+; 8/11/45 |

### general.7: e5eeb960

[Committed batch](https://github.com/shaug/seattle-election-guide/commit/e5eeb9606c7018a7e8fcb1412933ffd3e7bc0638); 703 → 878 decisions; {'added': 175, 'replaced': 2}. 37 of52 exact scoring/count/comparison rows change. Inventory unchanged: True.

Current entry: Added 175 source decisions and revised two endorsements.. Linked review: [GENERAL_VERIFICATION_APPLICATION_2026-10-16.md](https://github.com/shaug/seattle-election-guide/blob/2026-general.7/docs/GENERAL_VERIFICATION_APPLICATION_2026-10-16.md).

Additions by source: aft-washington +3, alliance-for-gun-responsibility +1, environmental-climate-caucus-wa-democrats +4, planned-parenthood-alliance-advocates +26, seattle-democratic-socialists +2, seattle-subway +20, seattle-times-editorial-board +21, seiu-775 +3, sierra-club-washington +24, the-urbanist +30, ufcw-3000 +4, washington-bikes +2, washington-for-peace-and-justice +31, washington-state-building-trades +1, washington-state-democrats +3.

Replacement: aft-washington / ld-32-state-senator: `{"status": "endorsed", "candidate_ids": ["ld-32-state-senator--jesse-salomon"], "allocation": {"ld-32-state-senator--jesse-salomon": "1"}}` → `{"status": "endorsed", "candidate_ids": ["ld-32-state-senator--cindy-ryu"], "allocation": {"ld-32-state-senator--cindy-ryu": "1"}}`.

Replacement: environmental-climate-caucus-wa-democrats / ld-43-state-senator: `{"status": "endorsed", "candidate_ids": ["ld-43-state-senator--jamie-pedersen"], "allocation": {"ld-43-state-senator--jamie-pedersen": "1"}}` → `{"status": "dual_endorsement", "candidate_ids": ["ld-43-state-senator--jamie-pedersen", "ld-43-state-senator--hannah-sabio-howell"], "allocation": {"ld-43-state-senator--hannah-sabio-howell": "1/2", "ld-43-state-senator--jamie-pedersen": "1/2"}}`.

Changed active source projections:
- planned-parenthood-alliance-advocates: `{"evidence_url": ["https://www.plannedparenthoodaction.org/planned-parenthood-alliance-advocates", "https://www.plannedparenthoodaction.org/planned-parenthood-alliance-advocates/elections/washington-candidate-endorsements"], "contribution_status": ["coverage_gap", "contributing"], "coverage_gap_status": ["access_restricted", null], "coverage_gap_note": ["HTTP 403; access-restricted disposition preserved.", null]}`.
- seattle-subway: `{"contribution_status": ["coverage_gap", "contributing"], "coverage_gap_status": ["not_found", null], "coverage_gap_note": ["Official publication still explicitly describes the August 2026 primary; not reused.", null]}`.
- sierra-club-washington: `{"evidence_url": ["https://www.sierraclub.org/washington", "https://www.sierraclub.org/washington/2026-endorsements"], "contribution_status": ["coverage_gap", "contributing"], "coverage_gap_status": ["access_restricted", null], "coverage_gap_note": ["HTTP 200 contains an Incapsula access challenge; access-restricted disposition preserved.", null]}`.
- the-urbanist: `{"evidence_url": ["https://www.theurbanist.org/2026-primary-election-endorsements/", "https://www.theurbanist.org/2026-general-election-endorsements/"], "contribution_status": ["coverage_gap", "contributing"], "coverage_gap_status": ["not_found", null], "coverage_gap_note": ["Primary-only guide; supplemental official elections-committee page also links only the 2026 primary.", null]}`.
- washington-for-peace-and-justice: `{"evidence_url": ["https://www.wa4pj.com/", "https://www.instagram.com/wa4pj/p/Deh8Qd4gZen/"], "contribution_status": ["coverage_gap", "contributing"], "coverage_gap_status": ["not_found", null], "coverage_gap_note": ["Official site has no current endorsement publication located.", null]}`.
- washington-state-democrats: `{"evidence_url": ["https://wadems.org/", "https://wadems.org/2026-campaign-resources/"], "contribution_status": ["coverage_gap", "contributing"], "coverage_gap_status": ["access_restricted", null], "coverage_gap_note": ["HTTP 403; access-restricted disposition preserved.", null]}`.

Existing decision evidence fields changed for 157 records; counts by source/field:

- aft-washington: {'evidence_locator': 25}.
- alliance-for-gun-responsibility: {'evidence_locator': 23}.
- environmental-climate-caucus-wa-democrats: {'evidence_locator': 10, 'requires_review': 1}.
- seattle-democratic-socialists: {'evidence_locator': 1}.
- seattle-times-editorial-board: {'evidence_locator': 5}.
- seiu-775: {'evidence_locator': 29}.
- ufcw-3000: {'evidence_locator': 25}.
- washington-bikes: {'evidence_locator': 20}.
- washington-state-building-trades: {'evidence_locator': 19}.

Exact score/count changes (leader; points; share; grade; explicit/covered/eligible):

| Race | Before | After |
| --- | --- | --- |
| initiative-26-001 | no; 22 points; share 1; A+; 22/22/45 | no; 29 points; share 1; A+; 29/29/45 |
| initiative-26-638 | no; 20 points; share 1; A+; 20/20/45 | no; 27 points; share 1; A+; 27/27/45 |
| initiative-26-645 | no; 20 points; share 1; A+; 20/20/45 | no; 27 points; share 1; A+; 27/27/45 |
| king-county-assessor | rob-foxcurran; 12 points; share 1; A+; 12/12/45 | rob-foxcurran; 14 points; share 1; A+; 14/14/45 |
| king-county-council-2 | rebecca-saldana; 45/2 points; share 45/52; A; 26/26/45 | rebecca-saldana; 51/2 points; share 51/58; A; 29/29/45 |
| king-county-council-4 | jorge-l-baron; 14 points; share 1; A+; 14/14/45 | jorge-l-baron; 19 points; share 1; A+; 19/19/45 |
| king-county-council-8 | teresa-mosqueda; 25 points; share 1; A+; 25/25/45 | teresa-mosqueda; 29 points; share 1; A+; 29/29/45 |
| ld-11-state-representative-1 | david-hackney; 8 points; share 8/11; B; 11/11/39 | david-hackney; 8 points; share 4/7; C; 14/14/39 |
| ld-11-state-representative-2 | steve-bergquist; 7 points; share 1; A+; 7/7/39 | steve-bergquist; 11 points; share 1; A+; 11/11/39 |
| ld-32-state-representative-1 | danica-noble; 27/2 points; share 9/14; B; 21/21/39 | danica-noble; 35/2 points; share 35/54; B; 27/27/39 |
| ld-32-state-representative-2 | lauren-davis, imraan-siddiqi; 10 points; share 1/2; TIED; 20/20/39 | imraan-siddiqi; 13 points; share 13/24; C; 24/24/39 |
| ld-32-state-senator | cindy-ryu; 13 points; share 13/19; B; 19/19/39 | cindy-ryu; 15 points; share 5/7; B; 21/22/39 |
| ld-34-state-representative-1 | brianna-k-thomas; 8 points; share 1; A+; 8/8/39 | brianna-k-thomas; 9 points; share 1; A+; 9/9/39 |
| ld-34-state-representative-2 | joe-fitzgibbon; 15 points; share 15/16; A+; 16/16/39 | joe-fitzgibbon; 20 points; share 10/11; A+; 22/22/39 |
| ld-34-state-senator | emily-alvarado; 15 points; share 1; A+; 15/15/39 | emily-alvarado; 18 points; share 1; A+; 18/18/39 |
| ld-36-state-representative-1 | julia-grant-reed; 16 points; share 1; A+; 16/16/39 | julia-grant-reed; 22 points; share 1; A+; 22/22/39 |
| ld-36-state-representative-2 | liz-berry; 13 points; share 1; A+; 13/13/39 | liz-berry; 17 points; share 1; A+; 17/17/39 |
| ld-36-state-senator | noel-c-frame; 13 points; share 1; A+; 13/13/39 | noel-c-frame; 17 points; share 1; A+; 17/17/39 |
| ld-37-state-representative-1 | kelabe-tewolde; 27/2 points; share 9/14; B; 21/21/39 | kelabe-tewolde; 17 points; share 17/25; B; 25/25/39 |
| ld-37-state-representative-2 | jaelynn-scott; 27 points; share 1; A+; 27/27/39 | jaelynn-scott; 31 points; share 1; A+; 31/31/39 |
| ld-37-state-senator | chipalo-street; 35/2 points; share 35/46; A; 23/23/39 | chipalo-street; 21 points; share 7/9; A; 27/27/39 |
| ld-43-state-representative-1 | nicole-macri; 15 points; share 1; A+; 15/15/39 | nicole-macri; 21 points; share 1; A+; 21/21/39 |
| ld-43-state-representative-2 | shaun-scott; 7 points; share 1; A+; 7/7/39 | shaun-scott; 10 points; share 1; A+; 10/10/39 |
| ld-43-state-senator | jamie-pedersen; 29/2 points; share 29/50; C; 25/25/39 | jamie-pedersen; 17 points; share 17/30; C; 30/30/39 |
| ld-46-state-representative-1 | gerry-pollet; 31/2 points; share 31/34; A+; 17/17/39 | gerry-pollet; 35/2 points; share 7/8; A; 20/21/39 |
| ld-46-state-representative-2 | darya-farivar; 16 points; share 1; A+; 16/16/39 | darya-farivar; 21 points; share 1; A+; 21/21/39 |
| ld-46-state-senator | javier-valdez; 17 points; share 1; A+; 17/17/39 | javier-valdez; 21 points; share 1; A+; 21/21/39 |
| seattle-city-council-5 | nilu-jenks; 25 points; share 25/26; A+; 26/26/45 | nilu-jenks; 28 points; share 28/29; A+; 29/29/45 |
| seattle-municipal-court-judge-5 | gabe-rothstein; 23/2 points; share 23/24; A+; 12/12/45 | gabe-rothstein; 23/2 points; share 23/24; A+; 12/12/45 |
| seattle-proposition-1-transit | yes; 11 points; share 1; A+; 11/11/45 | yes; 14 points; share 1; A+; 14/14/45 |
| supreme-court-justice-1 | colleen-melody; 21 points; share 1; A+; 21/21/45 | colleen-melody; 24 points; share 1; A+; 24/24/45 |
| supreme-court-justice-3 | jaime-michelle-hawk; 22 points; share 1; A+; 22/22/45 | jaime-michelle-hawk; 26 points; share 1; A+; 26/26/45 |
| supreme-court-justice-4 | ian-birk; 18 points; share 1; A+; 18/18/45 | ian-birk; 21 points; share 1; A+; 21/21/45 |
| supreme-court-justice-5 | theo-angelis; 19 points; share 1; A+; 19/19/45 | theo-angelis; 23 points; share 1; A+; 23/23/45 |
| supreme-court-justice-7 | debra-l-stephens; 17 points; share 1; A+; 17/17/45 | debra-l-stephens; 19 points; share 1; A+; 19/21/45 |
| us-house-7 | pramila-jayapal; 21 points; share 1; A+; 21/21/45 | pramila-jayapal; 26 points; share 1; A+; 26/27/45 |
| us-house-9 | adam-smith; 8 points; share 1; A+; 8/11/45 | adam-smith; 11 points; share 1; A+; 11/17/45 |

### general.8: f696a936

[Committed batch](https://github.com/shaug/seattle-election-guide/commit/f696a936fcda5dddb6347f6160a158491dbe0358); 878 → 880 decisions; {'added': 2}. 2 of52 exact scoring/count/comparison rows change. Inventory unchanged: True.

Current entry: Added two previously unrecorded endorsements.. Linked review: [GENERAL_VERIFICATION_REMAINING_2026-10-16.md](https://github.com/shaug/seattle-election-guide/blob/2026-general.8/docs/GENERAL_VERIFICATION_REMAINING_2026-10-16.md).

Additions by source: washington-conservation-action +1, washington-education-association +1.

Changed active source projections:
- None.

Existing decision evidence fields changed for 44 records; counts by source/field:

- washington-conservation-action: {'evidence_locator': 25}.
- washington-education-association: {'evidence_locator': 19}.

Exact score/count changes (leader; points; share; grade; explicit/covered/eligible):

| Race | Before | After |
| --- | --- | --- |
| initiative-26-638 | no; 27 points; share 1; A+; 27/27/45 | no; 28 points; share 1; A+; 28/28/45 |
| ld-11-state-representative-1 | david-hackney; 8 points; share 4/7; C; 14/14/39 | david-hackney; 8 points; share 8/15; C; 15/15/39 |

## Source/evidence interpretation

- .4: all614 retained records receive fresh capture IDs in their evidence locators; that part is provenance refresh. Material evidence destinations also change:15 11th-LD decisions and the source link resolve the eepurl short URL to its canonical campaign archive; Seattle Subway’s source link normalizes www. Nine existing coverage-gap notes are refreshed, with no discovery-status transitions. The linked full43-source refresh documents the source dispositions. The current short entry can make this easier to see by adding one sentence on the same evidence/access refresh.
- .5: two source status transitions (Stranger and Bus, unavailable→contributing); Tech4Housing links change from Bluesky to the official endorsement page for its three retained records and source link; WFP changes the official index path for five retained records/source link. Other changed locators explicitly preserve original reviews. The linked reconciliation records all eight discovery updates and each added/replaced decision.
- .6: three sources join membership (active43→46; consensus42→45, comparison remains one). Nondriver is selectable in both rights and transportation categories; affiliate/DMI overlap metadata is disclosed; DMI itself stays excluded. All52 eligible/missing source counts change, even where no new endorsement exists and no leader changes. LD32 House2 becomes tied at one half each. The linked additions review covers exact membership/category/overlap policy and22 decisions.
- .7: six existing sources move unavailable→contributing; no membership/eligibility/scoring change. PPAA, Subway, Sierra Club, Urbanist, WA4PJ, State Democrats become newly represented; these are the six publishers named in the current entry and linked review. AFT’s single-choice replacement and ECC’s single→dual allocation replacement are separately identified. AFT/AGR/DSA/Times/SEIU775/UFCW/Bikes/Trades prior records get new approval locators while retaining their choices; ECC’s changed record carries its reviewed warning.
- .8: two additions only.44 retained WCA/WEA records gain explicit evidence-locator wording preserving prior review; no source registry projection, status or destination changes. The linked remaining-verification record explains these finite PDF/one-decision approvals and unchanged prior choices.

## Not separately represented as new Updates entries

- No additional public choice/source/ballot/scoring batch is missing from the authored general log.
- October4 source-link/access-note changes are visible content changes in that same refresh. The existing linked43-source review covers them; one clarifying sentence in the short entry would make that coverage clear.
- October12 source admission changes every race’s eligible/missing count; one clarifying sentence in the existing22-decision entry would make unchanged-leader coverage explicit.
- Routine capture IDs/review timestamps and record IDs alone are provenance, not new organization endorsements. They are fully enumerated in JSON so they are not silently ignored.

## Bounded first-parent input-mutation inventory

17 commits touch config/ or data/ other than traffic analytics in the bounded range. Every one is listed; file paths are in JSON. There are zero first-parent mutations to the general inventory files, election/ballot-input files, scorer or normalization/inventory implementation directories. Exactly five canonical/source-registry mutations are the five batches above. No general results file exists or is introduced.

| Commit | Subject | Disposition |
| --- | --- | --- |
| [eab5867a](https://github.com/shaug/seattle-election-guide/commit/eab5867a55bf881349310a3417c9742e3c8e9da6) | fix: replace endorsement pill with visible segments (#484) | Meter/UI rendering configuration; no input/scoring delta; existing October 3 UI entry. |
| [f426b23e](https://github.com/shaug/seattle-election-guide/commit/f426b23e81a1ec953e3eab38eefa748b9c41037e) | Restore the final Meter v2 interaction (#487) | Meter/UI rendering configuration; no input/scoring delta; existing October 3 UI entry. |
| [8c62179e](https://github.com/shaug/seattle-election-guide/commit/8c62179ebf52570b51894bf6ad0c8cb6fe9447f7) | fix: distinguish earliest ballot availability (#490) | Calendar/date configuration; no endorsement/source/inventory/scoring delta; page audit owns displayed dates. |
| [f5c55f92](https://github.com/shaug/seattle-election-guide/commit/f5c55f9292dd0a363f19581e7626d97c2a555aae) | fix: refresh general endorsements and prepare 2026-general.4 (#493) | Data batch: general.4; represented by the corresponding current Updates entry. |
| [717d4403](https://github.com/shaug/seattle-election-guide/commit/717d440325917c88a491828876eb6e1e4875b962) | feat: declare and watch results ingest milestones (#498) | Calendar/date configuration; no endorsement/source/inventory/scoring delta; page audit owns displayed dates. |
| [f9ee5918](https://github.com/shaug/seattle-election-guide/commit/f9ee59186da21133820c085c70b6e998db987eac) | fix: reconcile general election endorsement coverage (#510) | Data batch: general.5; represented by the corresponding current Updates entry. |
| [9a7aa440](https://github.com/shaug/seattle-election-guide/commit/9a7aa44011688d93d776b355c589f963b19fe75a) | fix(ops): simplify production checks and retire daily analytics PRs (#513) | Operational adapter configuration only; no general canonical publication delta. |
| [0147fa03](https://github.com/shaug/seattle-election-guide/commit/0147fa03dc0ed928f412ecaff2761971245f928f) | docs: assess additional general election endorsement evidence (#515) | Unpublished proposals/manual research and captures only; not admitted to general canonical data. |
| [5b6aeb6d](https://github.com/shaug/seattle-election-guide/commit/5b6aeb6df914a0bc807f5a1190653bacc6ddc36b) | feat: automate recurring endorsement verification (#502) | Verification automation and baseline machinery; no canonical or rendered-source mutation. |
| [9d193bbe](https://github.com/shaug/seattle-election-guide/commit/9d193bbe344a506f5545adb011e104534f9f137b) | Restore the completed primary archive and reject retired meters (#526) | Primary archive pin restoration; no general input delta. |
| [06e5ccb2](https://github.com/shaug/seattle-election-guide/commit/06e5ccb2c81d6d9c1ca5876eba5997da23afaec3) | feat: add verified general-election sources and Tech 4 Taxes decision | Data batch: general.6; represented by the corresponding current Updates entry. |
| [f5852664](https://github.com/shaug/seattle-election-guide/commit/f585266404ab5be84dd1258564fe03d1b673c4bb) | fix: repair three live endorsement source checks (#544) | Verification adapters only; no canonical decisions, source registry, source evidence shown by publication, inventory or score mutation. |
| [e5eeb960](https://github.com/shaug/seattle-election-guide/commit/e5eeb9606c7018a7e8fcb1412933ffd3e7bc0638) | chore(data): apply approved October 16 endorsements (#543) | Data batch: general.7; represented by the corresponding current Updates entry. |
| [f696a936](https://github.com/shaug/seattle-election-guide/commit/f696a936fcda5dddb6347f6160a158491dbe0358) | Verify Stranger and WEA; add two missed endorsements (#546) | Data batch: general.8; represented by the corresponding current Updates entry. |
| [a1a83b5f](https://github.com/shaug/seattle-election-guide/commit/a1a83b5f1c09d7297a6100e3ac321b0e5034bf52) | build: prepare 2026-general.8 publication (#548) | Release/hosting version declaration only; canonical inputs unchanged. |
| [46cd5d63](https://github.com/shaug/seattle-election-guide/commit/46cd5d631d719b41b7517322e1f892744a20e0d2) | feat: broaden Updates and simplify How this works (#552) | Updates prose/rendering; no general endorsement/source/ballot/scoring delta. |
| [da307d6f](https://github.com/shaug/seattle-election-guide/commit/da307d6f4c695471ec5a025a4226824de5ffbbc5) | build: prepare 2026-general.9 publication (#554) | Release/hosting version declaration only; canonical inputs unchanged. |

## Verification files

- general-data-changes.json contains every266 addition and three replacement, source/evidence field differences for all retained records, allchanged score rows, public ZIP verification, tag equality, input-path invariance and current-entry mapping.
- Published general release ZIPs `.1`, `.4`, `.5`, `.6`, `.7`, `.8`, and `.9` were downloaded; the canonical and consensus comparisons are retained in the linked JSON.

No make check run: this audit creates no repository diff.
