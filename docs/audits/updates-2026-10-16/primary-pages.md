# Primary public page backfill audit

The audit applies AGENTS.md and the repository design, front-end, results and contribution contracts.

Coverage: all **283 first-parent commits** after `2026-primary.1` through `5251de0`, each classified in `commit-inventory.json`. The primary presentation boundary ends at restoration `9d193bb`; general-election changes are classified in the combined inventory. Initial rendering/publication/scoring/hosting path scan selected154 commits; whole-history review additionally found public certification-date correction `e006c5c` (#407). Date evidence is retained in the combined inventory and `publications.json`.

Dates are actual successful production status timestamps, not merge dates. Primary.1 was a public GitHub HTML/PDF release **July19 23:34:35 PDT**; the first successful website deployment was **July21 13:24:27 PDT**. Pre-website changes are grouped at first website publication. No preliminary election-night totals were published.

Critical archive composition: the overview is copied from the immutable release, while Sources, Comparisons, all32 race pages and race social images are regenerated from its pinned view model with the current renderer. The Oct3 cutover restored the Aug2 overview and521-decision dataset with no results; **direct race URLs survived**. PR484 briefly changed primary race social previews to permanent seams/no percentage; PR487 restored their resting percentage display later Oct3. Primary overview stayed old throughout. Restoration Oct11 reinstated538 decisions/all32 results and modern overview navigation/meter.

Dormant/non-events explicitly excluded: #350 never published a primary Corrections page because no nonempty primary corrections data existed; #345 certified per-candidate rows were replaced by #374 before any actual results ingest, so no live omitted-winner incident is established; #143 removed confidence-flag hooks but all published primary extraction/normalization confidences were1, so no actual flag disappearance is established. Pure CSS/token/shell refinements, byte-equivalent refactors, deployment controls and monitoring remain software changelog matters.

Verified exceptional dates: #350 not public; #374 result functionality first visible with #413 Aug19; #376 sticky source strip first successful descendant Aug16 06:53:59; #419 mergedAug22 but first productionSep13 20:50:10; #407 date correctionAug19 19:42:31; #413 actual resultsAug19 22:07:14; #476 cutoverOct3 07:27:19; #484 race preview changeOct3 11:20:36; #487 restorationOct3 17:21:57; #526 archive restorationOct11 22:49:41. The deployment IDs/run links are carried per commit, and compact success records are `publications.json`.

The entries below account for the primary presentation and access changes. The authored log combines overlapping result and archive events with the data audit; the combined inventory binds each supporting commit to its final dated headline. General data changes are documented separately.

## 2026-07-21: Simplified endorsement agreement and source disclosures.

`primary-initial-consensus`

The website replaced letter grades with the leading choice’s share among explicitly endorsing sources, a source count, and a warning when there were too few endorsements. Candidate lists linked each endorsement to its evidence and identified split endorsements. The source directory added participation counts and separated contributing organizations from two research gaps.

Support: [Reviewed change #30](https://github.com/shaug/seattle-election-guide/pull/30), [Reviewed change #32](https://github.com/shaug/seattle-election-guide/pull/32), [Reviewed change #48](https://github.com/shaug/seattle-election-guide/pull/48), [Reviewed change #51](https://github.com/shaug/seattle-election-guide/pull/51), [Reviewed change #55](https://github.com/shaug/seattle-election-guide/pull/55).

## 2026-07-22: Put races in ballot order.

`primary-race-order`

Races were organized by ballot section and jurisdiction, with judicial offices under the jurisdiction they serve.

Support: [Reviewed change #59](https://github.com/shaug/seattle-election-guide/pull/59).

## 2026-07-24: Added election links and shareable race details.

`primary-election-race-links`

The primary received a stable election address and an archive entry. Each recommendation opened candidate-centered endorsement details with evidence links, split-endorsement labels and separate nonendorsement and missing-coverage explanations; race links could be shared and restored.

Support: [Reviewed change #70](https://github.com/shaug/seattle-election-guide/pull/70), [Reviewed change #73](https://github.com/shaug/seattle-election-guide/pull/73).

## 2026-07-25: Added a compact ballot and contested-race filter.

`primary-compact-filter`

Readers could switch between full and compact endorsement views and limit either view to contested races. Contested status came from the official ballot choices, and shared links retained the selected view and race filter.

Support: [Reviewed change #74](https://github.com/shaug/seattle-election-guide/pull/74).

## 2026-07-27: Made the Seattle Times comparison optional.

`primary-optional-times`

Seattle Times comparison bars, comparison evidence rows and comparison-only choices became hidden by default on the responsive guide. A Customize control could reveal them; showing the Times did not add it to the endorsement tally.

Support: [Reviewed change #88](https://github.com/shaug/seattle-election-guide/pull/88).

## 2026-07-28: Added custom source selections.

`primary-source-lens`

Readers could choose source categories or individual organizations and see the resulting choices, shares and counts, with an All sources reference when their selection differed. Source documentation and checkboxes were combined into one tree, including a separate non-tallying Times comparison. The shared-link format changed; earlier links using its previous schema returned to the default with an explanation.

Support: [Reviewed change #84](https://github.com/shaug/seattle-election-guide/pull/84), [Reviewed change #85](https://github.com/shaug/seattle-election-guide/pull/85), [Reviewed change #86](https://github.com/shaug/seattle-election-guide/pull/86), [Reviewed change #87](https://github.com/shaug/seattle-election-guide/pull/87), [Reviewed change #89](https://github.com/shaug/seattle-election-guide/pull/89), [Reviewed change #90](https://github.com/shaug/seattle-election-guide/pull/90), [Reviewed change #91](https://github.com/shaug/seattle-election-guide/pull/91), [Reviewed change #92](https://github.com/shaug/seattle-election-guide/pull/92), [Reviewed change #99](https://github.com/shaug/seattle-election-guide/pull/99), [Reviewed change #100](https://github.com/shaug/seattle-election-guide/pull/100), [Reviewed change #101](https://github.com/shaug/seattle-election-guide/pull/101).

## 2026-07-29: Moved source selection to its own page and corrected its total.

`primary-sources-page`

Source selection moved to a Sources page with Save, Cancel and Reset actions, and the guide carried the current selection to that page. The guide’s selectable-source total was corrected from 42 to 40 by excluding the two research gaps. Methodology moved from the guide into About.

Support: [Reviewed change #111](https://github.com/shaug/seattle-election-guide/pull/111), [Reviewed change #112](https://github.com/shaug/seattle-election-guide/pull/112), [Reviewed change #113](https://github.com/shaug/seattle-election-guide/pull/113), [Reviewed change #114](https://github.com/shaug/seattle-election-guide/pull/114).

## 2026-07-29: Clarified the all-sources comparison.

`primary-reference-display`

The audited reference was labeled “All sources” with its choice and share, and its agreement or difference from the selected sources was stated in text as well as color. Endorsement meters were made consistent across views.

Support: [Reviewed change #126](https://github.com/shaug/seattle-election-guide/pull/126).

## 2026-07-30: Corrected personalized race details and shared links.

`primary-lens-corrections`

Race-detail counts, shares, meters, candidate order and accessible summaries were corrected to follow the current source selection. Unselected endorsement evidence remained visible as “Not counted,” ties used ballot order, and split-endorsement arithmetic received an explanation. Opening, closing or sharing race details preserved the selected sources; empty candidate meters were removed.

Support: [Reviewed change #138](https://github.com/shaug/seattle-election-guide/pull/138), [Reviewed change #139](https://github.com/shaug/seattle-election-guide/pull/139), [Reviewed change #143](https://github.com/shaug/seattle-election-guide/pull/143), [Reviewed change #144](https://github.com/shaug/seattle-election-guide/pull/144), [Reviewed change #158](https://github.com/shaug/seattle-election-guide/pull/158).

## 2026-07-31: Marked races without a majority.

`primary-no-majority`

A leading share at or below 50% received an amber meter and an explicit “No majority” label. The label followed the current source selection, including when that selection created or dissolved a tie.

Support: [Reviewed change #168](https://github.com/shaug/seattle-election-guide/pull/168).

## 2026-07-31: Added side-by-side endorsement comparisons.

`primary-comparisons-preview`

A direct comparison page let readers compare all sources, organizations or categories, with the first column as the reference. Shared links retained the columns and race, section and differences-only filters. Agreement and disagreement were stated in words, while missing endorsements and out-of-scope sources stayed distinct.

Support: [Reviewed change #165](https://github.com/shaug/seattle-election-guide/pull/165), [Reviewed change #167](https://github.com/shaug/seattle-election-guide/pull/167), [Reviewed change #169](https://github.com/shaug/seattle-election-guide/pull/169), [Reviewed change #170](https://github.com/shaug/seattle-election-guide/pull/170), [Reviewed change #171](https://github.com/shaug/seattle-election-guide/pull/171), [Reviewed change #172](https://github.com/shaug/seattle-election-guide/pull/172), [Reviewed change #178](https://github.com/shaug/seattle-election-guide/pull/178).

## 2026-07-31: Kept the counted-source total visible.

`primary-source-status`

The guide’s source strip began showing the sources being counted even with the default selection, with actions to customize sources or restore all sources.

Support: [Reviewed change #187](https://github.com/shaug/seattle-election-guide/pull/187), [Reviewed change #188](https://github.com/shaug/seattle-election-guide/pull/188).

## 2026-08-01: Moved Times comparisons to the Comparisons page.

`primary-comparison-launch`

Comparisons joined the public navigation and became the place to compare the Times with the aggregate. Times bars and comparison-only choice sections were removed from the guide and race details; older selection links retained their tallying sources while ignoring the retired comparison toggle. The first comparison column could be removed when three columns were present, and the next column became the reference.

Support: [Reviewed change #197](https://github.com/shaug/seattle-election-guide/pull/197), [Reviewed change #199](https://github.com/shaug/seattle-election-guide/pull/199), [Reviewed change #201](https://github.com/shaug/seattle-election-guide/pull/201), [Reviewed change #231](https://github.com/shaug/seattle-election-guide/pull/231).

## 2026-08-02: Replaced the PDF download with printing from the guide.

`primary-printable-guide`

The generated PDF edition was retired. Existing PDF links redirected to the primary guide, and browser printing used the guide view the reader was looking at.

Support: [Reviewed change #247](https://github.com/shaug/seattle-election-guide/pull/247).

## 2026-08-02: Corrected comparison rounding and selection-link failures.

`primary-share-and-rounding-fixes`

Comparison percentages stopped changing after interaction because of different rounding rules: a 9-of-16 share now stayed 56.2%. Failed source-selection links also received visible explanations instead of silently losing the selection.

Support: [Reviewed change #254](https://github.com/shaug/seattle-election-guide/pull/254), [Reviewed change #260](https://github.com/shaug/seattle-election-guide/pull/260).

## 2026-08-03: Explained invalid comparison links.

`primary-invalid-comparison-links`

Unreadable or rejected comparison links began returning to the default comparison with an explanation. A column change that could not be shared was visibly reverted instead of silently doing nothing.

Support: [Reviewed change #278](https://github.com/shaug/seattle-election-guide/pull/278).

## 2026-08-04: Gave every race its own page.

`primary-race-pages`

Race pages replaced the guide’s dialogs, with individual addresses, page titles and share previews. Existing race-fragment links forwarded to the new pages with the selected sources intact. Sole leaders were named once; ties used separate candidate headings and meters instead of a sole-leader headline.

Support: [Reviewed change #305](https://github.com/shaug/seattle-election-guide/pull/305), [Reviewed change #306](https://github.com/shaug/seattle-election-guide/pull/306), [Reviewed change #307](https://github.com/shaug/seattle-election-guide/pull/307), [Reviewed change #308](https://github.com/shaug/seattle-election-guide/pull/308), [Reviewed change #309](https://github.com/shaug/seattle-election-guide/pull/309).

## 2026-08-05: Showed the endorsement breakdown in the meter.

`primary-meter-v2`

Endorsement meters gained candidate runs and source blocks, including split endorsements and source tooltips. Captions stated exact endorsement points, including fractions, and race share previews adopted the same breakdown.

Support: [Reviewed change #318](https://github.com/shaug/seattle-election-guide/pull/318), [Reviewed change #319](https://github.com/shaug/seattle-election-guide/pull/319), [Reviewed change #321](https://github.com/shaug/seattle-election-guide/pull/321), [Reviewed change #332](https://github.com/shaug/seattle-election-guide/pull/332).

## 2026-08-07: Added a meter for each endorsed candidate.

`primary-candidate-meters`

Each candidate’s race-page section gained its own static endorsement meter, showing that candidate’s share and split endorsements in context. This replaced the single shared race-page meter.

Support: [Reviewed change #335](https://github.com/shaug/seattle-election-guide/pull/335).

## 2026-08-08: Added counting status and official results links.

`primary-counting-status`

After election day, the guide linked readers to the official ongoing count and stated the scheduled certification date without publishing preliminary totals. Candidate cards briefly repeated that counting note. The stated August 19 certification date was later corrected to August 18.

Support: [Reviewed change #339](https://github.com/shaug/seattle-election-guide/pull/339), [Reviewed change #340](https://github.com/shaug/seattle-election-guide/pull/340).

## 2026-08-09: Consolidated the counting notice.

`primary-counting-notes`

The repeated counting notes were removed from individual race cards. The election banner retained the official-results link and counting status.

Support: [Reviewed change #346](https://github.com/shaug/seattle-election-guide/pull/346).

## 2026-08-16: Kept source-selection context visible on race pages.

`primary-sticky-source-strip`

The race page’s counted-source strip and Edit sources link stayed visible while readers scrolled through endorsement evidence.

Support: [Reviewed change #376](https://github.com/shaug/seattle-election-guide/pull/376).

## 2026-08-19: Corrected certification timing and added certified results.

`primary-results-and-certification`

The certification date was corrected from August 19 to August 18. Certified results were then published for the 24 races fully covered by King County, including all ballot choices in finish order, their shares and outcomes, and official evidence links. Results were separate from endorsement agreement and could be added as a comparison column without affecting its agreement labels.

Support: [Reviewed change #407](https://github.com/shaug/seattle-election-guide/pull/407), [Reviewed change #336](https://github.com/shaug/seattle-election-guide/pull/336), [Reviewed change #338](https://github.com/shaug/seattle-election-guide/pull/338), [Reviewed change #339](https://github.com/shaug/seattle-election-guide/pull/339), [Reviewed change #340](https://github.com/shaug/seattle-election-guide/pull/340), [Reviewed change #345](https://github.com/shaug/seattle-election-guide/pull/345), [Reviewed change #351](https://github.com/shaug/seattle-election-guide/pull/351), [Reviewed change #352](https://github.com/shaug/seattle-election-guide/pull/352), [Reviewed change #371](https://github.com/shaug/seattle-election-guide/pull/371), [Reviewed change #374](https://github.com/shaug/seattle-election-guide/pull/374), [Reviewed change #413](https://github.com/shaug/seattle-election-guide/pull/413).

## 2026-09-13: Completed certified results for all 32 races.

`primary-crosscounty-results`

Secretary of State totals added the eight races spanning county lines: LD32’s three legislative races, Congressional District 9 and four Supreme Court positions. Every race’s result named its own authority and evidence. The change merged August 22 and first reached the website September 13.

Support: [Reviewed change #419](https://github.com/shaug/seattle-election-guide/pull/419).

## 2026-10-03: The primary archive reverted to an older release.

`primary-archive-regression`

The general-election cutover archived the August 2 primary release rather than its final live version. The archive lost the later 17 source decisions and all certified results, and its overview returned to the retired meter and dialog navigation. Individual race URLs remained available, but used the older endorsement data. Their share-preview meter also briefly showed permanent segmentation before the earlier display was restored that day. The older primary data remained until October 11.

Support: [Reviewed change #476](https://github.com/shaug/seattle-election-guide/pull/476), [Reviewed change #484](https://github.com/shaug/seattle-election-guide/pull/484), [Reviewed change #487](https://github.com/shaug/seattle-election-guide/pull/487).

## 2026-10-11: Restored the completed primary archive.

`primary-archive-restored`

The archive was replaced with the completed primary: 538 source decisions and certified results for all 32 races. The overview regained its segmented endorsement meter and links to individual race pages, and those pages regained the completed data. The endorsement dataset and results matched the final live primary.

Support: [Reviewed change #526](https://github.com/shaug/seattle-election-guide/pull/526).
