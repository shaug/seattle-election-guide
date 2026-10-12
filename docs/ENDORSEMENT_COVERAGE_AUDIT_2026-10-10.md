# General-election endorsement coverage audit — October 10, 2026

Compared the live Lefty Cheat Sheet November 3, 2026 dataset with Seattle Elections Guide release 2026-general.4 and the repository canonical dataset. This report is an investigation; it changes no endorsement records.

Both guides have identical candidate/ballot-option sets in all 31 shared races, after punctuation and accent normalization. Our 21 additional races are uncontested. Lefty registers 33 sources. We register 48 organizations: 43 consensus/comparison panel sources and five excluded records.

For 27 directly comparable sources (separating PVG/Fuse and mixed national/local DSA), 283 source–race choices agree, one choice set differs, and 132 Lefty records are absent from our data. Four verified endorsements appear only in ours; three further ours-only records are explicit no-endorsement decisions. PVG adds 15 recommendations beyond the 14 choice sets shared with Fuse; DSA adds three unverified measure choices beyond the shared Scott endorsement. Four unregistered sources account for 30 additional Lefty records.

At organization-family level the raw comparison contains 298 matching choice sets, 150 Lefty-only records, one changed choice set, seven ours-only records (four endorsements and three explicit abstentions), and 30 records from unregistered organizations. Matching dual choices also preserve equal half-point allocations.

## Verified baseline

- Published release: [2026-general.4](https://github.com/shaug/seattle-election-guide/releases/tag/2026-general.4).
- Downloaded archive SHA-256: `948badc63eaa39efc024edc10cb52247fc6170177f3bd1a6147722bfcda000d5`, matching the GitHub asset digest.
- Canonical dataset SHA-256: `16b44e35c14a7d68203e0ed4335243221f697241f86354b8f3e153365bb129e0`, matching the live release manifest.
- Release canonical dataset equals repository canonical dataset, including all 617 records.
- Lefty deployed assets: [endorsements](https://electioncheatsheet.org/data/endorsements-20261103-75bf9ae8.json), [sources](https://electioncheatsheet.org/data/outlets-2026-general-2fb7126b.json), [races](https://electioncheatsheet.org/data/races-20261103-ab256202.json).

## Recommended work

1. Prepare a focused correction/refresh issue for existing sources: the October 9 Stranger slate, Tech 4 Housing, four Tech 4 Taxes candidate additions, King County Democrats, Washington Bus, Working Families Party and the captured-but-omitted OneAmerica/WashingtonCAN decisions. Include WFP’s Shaun Scott record from our uncontested inventory.
2. Record the King County Democrats and Washington Bus position errors explicitly. Require exact evidence for Tech 4 Taxes’ initiative claim and DSA’s initiative claims. Reverify Times choices through an authorized readable source.
3. Seek official general-election or carry-forward evidence for Urbanist, WA4PJ and Stonewall. A primary survivor does not itself establish a general endorsement under REVIEW_GUIDE.md.
4. Evaluate new organizations and additional comparison sources separately under panel policy. Preserve the distinction between Fuse organizational endorsements and PVG compiled recommendations.
5. Expand collection beyond one landing page, first-visible index entries, and image alt text. OneAmerica and WashingtonCAN demonstrate that unchanged captures can still contain unreviewed decisions.
6. Preserve existing verified PROTEC17/SEIU 925 endorsements and explicit no-endorsement records. After an issue-scoped data change, complete evidence/review records, rebuild scoring, run make check and follow the release process.

## Complete discrepancy ledger

Each row represents one organization–race decision. A dual endorsement is one record containing both candidates. An absent record is distinct from an explicit no-endorsement decision. All source URLs below were public discovery links; no organizations were contacted.

### Democratic Socialists of America

**Assessment:** Source identity and evidence locator unresolved. Lefty links both national DSA and a Seattle DSA candidate post. Its three initiative No choices were not established by the checked evidence. The shared Jaelynn Scott choice agrees.

Official links: [source 1](https://electoral.dsausa.org/our-campaigns/), [source 2](https://www.instagram.com/p/DWj0mLYAUve/).

| Race | Lefty record | Our record | Difference |
| --- | --- | --- | --- |
| Initiative IP26-645 — State and Local Taxes | No / Reject | Absent | Lefty only |
| Initiative IL26-001 — Parental Rights in Public Schools | No / Reject | Absent | Lefty only |
| Initiative IL26-638 — Participation in K-12 School Athletics | No / Reject | Absent | Lefty only |

### Tech 4 Housing

**Assessment:** Incomplete discovery endpoint. We used a Bluesky post containing three valid general-ballot candidates. The official website now has a dedicated general list and supports ten additional choices.

Official links: [source 1](https://www.tech4housing.org/endorsements).

| Race | Lefty record | Our record | Difference |
| --- | --- | --- | --- |
| Initiative IP26-645 — State and Local Taxes | No / Reject | Absent | Lefty only |
| Initiative IL26-001 — Parental Rights in Public Schools | No / Reject | Absent | Lefty only |
| Initiative IL26-638 — Participation in K-12 School Athletics | No / Reject | Absent | Lefty only |
| Legislative District 32 State Representative — Position 1 | Danica Noble | Absent | Lefty only |
| Legislative District 43 State Senator | Hannah Sabio-Howell | Absent | Lefty only |
| King County Assessor | Rob Foxcurran | Absent | Lefty only |
| Metropolitan King County Council — District 8 | Teresa Mosqueda | Absent | Lefty only |
| Seattle City Council — District 5 | Nilu Jenks | Absent | Lefty only |
| Seattle Municipal Court Judge — Position 5 | Gabe Rothstein | Absent | Lefty only |
| Seattle Proposition 1 — Seattle Transit Measure | Yes / Approve | Absent | Lefty only |

### Tech 4 Taxes

**Assessment:** Four new candidate-index entries; one unsupported measure lead. The current 2025–2026 index supports Pollet, Brown, Siddiqi and Tewolde, absent from the October 3 capture. No on IP26-645 was not verified from the linked candidate index or Instagram profile; a specific official measure publication is needed.

Official links: [source 1](https://tech4taxes.org/endorsements), [source 2](https://www.instagram.com/tech4taxes/).

| Race | Lefty record | Our record | Difference |
| --- | --- | --- | --- |
| Initiative IP26-645 — State and Local Taxes | No / Reject | Absent | Lefty only |
| Legislative District 32 State Representative — Position 2 | Imraan Siddiqi | Absent | Lefty only |
| Legislative District 37 State Senator | Tatiana Brown | Absent | Lefty only |
| Legislative District 37 State Representative — Position 1 | Kelabe Tewolde | Absent | Lefty only |
| Legislative District 46 State Representative — Position 1 | Gerry Pollet | Absent | Lefty only |

### King County Democrats

**Assessment:** New source content; one position typo. Current list adds No on IP26-645, Noble/Scully in LD32 House 1, and Siddiqi alongside Davis in LD32 House 2. None appeared in the October 3 capture. Pollet now appears, but is labeled House Position 2; the frozen ballot places him in Position 1. Review that correction explicitly.

Official links: [source 1](https://www.kcdems.org/our-party/e/2026-endorsements/).

| Race | Lefty record | Our record | Difference |
| --- | --- | --- | --- |
| Initiative IP26-645 — State and Local Taxes | No / Reject | Absent | Lefty only |
| Legislative District 32 State Representative — Position 1 | Danica Noble, Keith Scully | Absent | Lefty only |
| Legislative District 32 State Representative — Position 2 | Lauren Davis, Imraan Siddiqi | Lauren Davis | Different choices |
| Legislative District 46 State Representative — Position 1 | Gerry Pollet | Absent | Lefty only |

### The Stranger

**Assessment:** New general publication. The October 9 general cheat sheet supports all 31 choices. The prior October 3 source check predates it. Its Jaime Hawk spelling requires the same ballot alias check as other transcriptions.

Official links: [source 1](https://www.thestranger.com/news/the-stranger-election-control-board-2026-general-election-cheat-sheet/).

| Race | Lefty record | Our record | Difference |
| --- | --- | --- | --- |
| Initiative IP26-645 — State and Local Taxes | No / Reject | Absent | Lefty only |
| Initiative IL26-001 — Parental Rights in Public Schools | No / Reject | Absent | Lefty only |
| Initiative IL26-638 — Participation in K-12 School Athletics | No / Reject | Absent | Lefty only |
| U.S. Representative — Congressional District 7 | Pramila Jayapal | Absent | Lefty only |
| U.S. Representative — Congressional District 9 | Adam Smith | Absent | Lefty only |
| Legislative District 11 State Representative — Position 1 | Ashley Fedan | Absent | Lefty only |
| Legislative District 32 State Senator | Cindy Ryu | Absent | Lefty only |
| Legislative District 32 State Representative — Position 1 | Keith Scully | Absent | Lefty only |
| Legislative District 32 State Representative — Position 2 | Imraan Siddiqi | Absent | Lefty only |
| Legislative District 34 State Representative — Position 2 | Joe Fitzgibbon | Absent | Lefty only |
| Legislative District 36 State Senator | Noel C. Frame | Absent | Lefty only |
| Legislative District 37 State Senator | Chipalo Street | Absent | Lefty only |
| Legislative District 37 State Representative — Position 1 | Kelabe Tewolde | Absent | Lefty only |
| Legislative District 37 State Representative — Position 2 | Jaelynn Scott | Absent | Lefty only |
| Legislative District 43 State Senator | Jamie Pedersen | Absent | Lefty only |
| Legislative District 43 State Representative — Position 1 | Nicole Macri | Absent | Lefty only |
| Legislative District 46 State Senator | Javier Valdez | Absent | Lefty only |
| Legislative District 46 State Representative — Position 1 | Will Dreher | Absent | Lefty only |
| Legislative District 46 State Representative — Position 2 | Darya Farivar | Absent | Lefty only |
| King County Assessor | Rob Foxcurran | Absent | Lefty only |
| Metropolitan King County Council — District 2 | Rebecca Saldaña | Absent | Lefty only |
| Metropolitan King County Council — District 8 | Teresa Mosqueda | Absent | Lefty only |
| Washington Supreme Court Justice — Position 1 | Colleen Melody | Absent | Lefty only |
| Washington Supreme Court Justice — Position 3 | Jaime Michelle Hawk | Absent | Lefty only |
| Washington Supreme Court Justice — Position 4 | Ian Birk | Absent | Lefty only |
| Washington Supreme Court Justice — Position 5 | Theo Angelis | Absent | Lefty only |
| Washington Supreme Court Justice — Position 7 | Debra L. Stephens | Absent | Lefty only |
| King County District Court West Electoral District — Judge Position 1 | Bardi Martin | Absent | Lefty only |
| Seattle City Council — District 5 | Nilu Jenks | Absent | Lefty only |
| Seattle Municipal Court Judge — Position 5 | Gabe Rothstein | Absent | Lefty only |
| Seattle Proposition 1 — Seattle Transit Measure | Yes / Approve | Absent | Lefty only |

### King County Republican Party

**Assessment:** Outside progressive-source panel. Lefty displays this as a conservative comparison source. We do not register it in the current panel. Its 15 choices were not individually verified in this audit; whether to offer this comparison is a product/panel decision.

Official links: [source 1](https://kcgop.org/votersguide/).

| Race | Lefty record | Our record | Difference |
| --- | --- | --- | --- |
| Initiative IP26-645 — State and Local Taxes | Yes / Approve | Absent | Unregistered source |
| Initiative IL26-001 — Parental Rights in Public Schools | Yes / Approve | Absent | Unregistered source |
| Initiative IL26-638 — Participation in K-12 School Athletics | Yes / Approve | Absent | Unregistered source |
| U.S. Representative — Congressional District 7 | Nirav Sheth | Absent | Unregistered source |
| U.S. Representative — Congressional District 9 | Doug Basler | Absent | Unregistered source |
| Legislative District 36 State Senator | Jillian England | Absent | Unregistered source |
| Legislative District 46 State Senator | Sandra Stephens | Absent | Unregistered source |
| King County Assessor | Dominique M. Scarimbolo | Absent | Unregistered source |
| Washington Supreme Court Justice — Position 1 | Scott Edwards | Absent | Unregistered source |
| Washington Supreme Court Justice — Position 3 | David Stevens | Absent | Unregistered source |
| Washington Supreme Court Justice — Position 4 | Sean O'Donnell | Absent | Unregistered source |
| Washington Supreme Court Justice — Position 5 | Dave Larson | Absent | Unregistered source |
| Washington Supreme Court Justice — Position 7 | Todd A. Bloom | Absent | Unregistered source |
| Seattle City Council — District 5 | Julie Kang | Absent | Unregistered source |
| Seattle Proposition 1 — Seattle Transit Measure | No / Reject | Absent | Unregistered source |

### OneAmerica Votes

**Assessment:** Captured but omitted. Both No recommendations occur in the October 3 captured page as well as the current page. This is an extraction/review omission rather than solely a stale-data issue.

Official links: [source 1](https://oavotes.org/our-work/endorsements/2026-endorsements/).

| Race | Lefty record | Our record | Difference |
| --- | --- | --- | --- |
| Initiative IL26-001 — Parental Rights in Public Schools | No / Reject | Absent | Lefty only |
| Initiative IL26-638 — Participation in K-12 School Athletics | No / Reject | Absent | Lefty only |

### The Seattle Times

**Assessment:** Current evidence inaccessible. Lefty lists 17 more choices than our five verified comparison records. HTTP retrieval failed and browser security blocked opening the official index, so these remain unverified. Our prior review specifically distinguished criticism of Supreme Court Position 4 from an endorsement.

Official links: [source 1](https://www.seattletimes.com/opinion/editorials/feed/).

| Race | Lefty record | Our record | Difference |
| --- | --- | --- | --- |
| Initiative IL26-001 — Parental Rights in Public Schools | No / Reject | Absent | Lefty only |
| Initiative IL26-638 — Participation in K-12 School Athletics | No / Reject | Absent | Lefty only |
| Legislative District 11 State Representative — Position 1 | David Hackney | Absent | Lefty only |
| Legislative District 32 State Senator | Jesse Salomon | Absent | Lefty only |
| Legislative District 32 State Representative — Position 1 | Keith Scully | Absent | Lefty only |
| Legislative District 32 State Representative — Position 2 | Lauren Davis | Absent | Lefty only |
| Legislative District 37 State Representative — Position 1 | Kelabe Tewolde | Absent | Lefty only |
| Legislative District 43 State Senator | Jamie Pedersen | Absent | Lefty only |
| Legislative District 46 State Representative — Position 1 | Gerry Pollet | Absent | Lefty only |
| King County Assessor | Rob Foxcurran | Absent | Lefty only |
| Metropolitan King County Council — District 2 | Toshiko Grace Hasegawa | Absent | Lefty only |
| Metropolitan King County Council — District 8 | Nick Duda | Absent | Lefty only |
| Washington Supreme Court Justice — Position 1 | Colleen Melody | Absent | Lefty only |
| Washington Supreme Court Justice — Position 4 | Sean O'Donnell | Absent | Lefty only |
| Washington Supreme Court Justice — Position 7 | Debra L. Stephens | Absent | Lefty only |
| Seattle City Council — District 5 | Julie Kang | Absent | Lefty only |
| Seattle Municipal Court Judge — Position 5 | Garmon Newsom | Absent | Lefty only |

### Track AIPAC

**Assessment:** Outside registered panel; official support found. The official endorsement index supports Jayapal for WA-07 in the November 3 general election. Evaluate source eligibility separately.

Official links: [source 1](https://www.trackaipac.com/endorsements).

| Race | Lefty record | Our record | Difference |
| --- | --- | --- | --- |
| U.S. Representative — Congressional District 7 | Pramila Jayapal | Absent | Unregistered source |

### Washington for Peace and Justice

**Assessment:** Primary-only linked evidence. The linked July 14 Instagram caption describes the August 4 primary and advancing candidates to the general. It does not establish general-election carry-forward. Color-coded candidate assessments also need endorsement-semantics review.

Official links: [source 1](https://www.instagram.com/wa4pj/p/Dax5yPUlKYO/).

| Race | Lefty record | Our record | Difference |
| --- | --- | --- | --- |
| U.S. Representative — Congressional District 7 | Pramila Jayapal | Absent | Lefty only |
| Legislative District 32 State Senator | Cindy Ryu | Absent | Lefty only |
| Legislative District 32 State Representative — Position 2 | Imraan Siddiqi | Absent | Lefty only |
| Legislative District 34 State Representative — Position 2 | Joe Fitzgibbon | Absent | Lefty only |
| Legislative District 36 State Senator | Noel C. Frame | Absent | Lefty only |
| Legislative District 37 State Senator | Chipalo Street | Absent | Lefty only |
| Legislative District 37 State Representative — Position 1 | Kelabe Tewolde, Sharon Tomiko Santos | Absent | Lefty only |
| Legislative District 37 State Representative — Position 2 | Jaelynn Scott | Absent | Lefty only |
| Legislative District 43 State Senator | Hannah Sabio-Howell | Absent | Lefty only |
| Legislative District 43 State Representative — Position 1 | Nicole Macri | Absent | Lefty only |
| Legislative District 46 State Representative — Position 2 | Darya Farivar | Absent | Lefty only |
| Metropolitan King County Council — District 2 | Rebecca Saldaña | Absent | Lefty only |
| Metropolitan King County Council — District 8 | Teresa Mosqueda | Absent | Lefty only |
| Washington Supreme Court Justice — Position 3 | Jaime Michelle Hawk | Absent | Lefty only |
| Washington Supreme Court Justice — Position 5 | Theo Angelis | Absent | Lefty only |
| Seattle City Council — District 5 | Nilu Jenks | Absent | Lefty only |

### Washington State Stonewall Democrats

**Assessment:** Access restriction and primary phase. The linked Facebook post’s public description explicitly says 2026 Primary Election. Full general confirmation was not obtained; our prior access-restricted status explains the omission.

Official links: [source 1](https://www.facebook.com/stonewallwa/posts/endorsement-announcementthe-washington-state-stonewall-democrats-are-proud-to-an/1450344363801898/).

| Race | Lefty record | Our record | Difference |
| --- | --- | --- | --- |
| U.S. Representative — Congressional District 7 | Pramila Jayapal | Absent | Lefty only |
| U.S. Representative — Congressional District 9 | Adam Smith | Absent | Lefty only |
| Legislative District 11 State Representative — Position 1 | Ashley Fedan | Absent | Lefty only |
| Legislative District 32 State Senator | Cindy Ryu | Absent | Lefty only |
| Legislative District 32 State Representative — Position 2 | Imraan Siddiqi | Absent | Lefty only |
| Legislative District 34 State Representative — Position 2 | Joe Fitzgibbon | Absent | Lefty only |
| Legislative District 37 State Senator | Chipalo Street | Absent | Lefty only |
| Legislative District 37 State Representative — Position 1 | Kelabe Tewolde | Absent | Lefty only |
| Legislative District 37 State Representative — Position 2 | Jaelynn Scott | Absent | Lefty only |
| Legislative District 43 State Senator | Jamie Pedersen, Hannah Sabio-Howell | Absent | Lefty only |
| Legislative District 43 State Representative — Position 1 | Nicole Macri | Absent | Lefty only |
| Legislative District 46 State Senator | Javier Valdez | Absent | Lefty only |
| Legislative District 46 State Representative — Position 2 | Darya Farivar | Absent | Lefty only |
| Metropolitan King County Council — District 2 | Rebecca Saldaña | Absent | Lefty only |
| Washington Supreme Court Justice — Position 1 | Colleen Melody | Absent | Lefty only |
| Washington Supreme Court Justice — Position 3 | Jaime Michelle Hawk | Absent | Lefty only |
| Washington Supreme Court Justice — Position 5 | Theo Angelis | Absent | Lefty only |
| Seattle City Council — District 5 | Nilu Jenks | Absent | Lefty only |
| Seattle Municipal Court Judge — Position 5 | Gabe Rothstein | Absent | Lefty only |

### Young Democrats of Washington

**Assessment:** Outside registered panel; specific evidence missing. The linked Instagram profile is not a reconstructable source for all ten choices. Obtain specific official posts and election-phase evidence.

Official links: [source 1](https://www.instagram.com/youngdemswa).

| Race | Lefty record | Our record | Difference |
| --- | --- | --- | --- |
| U.S. Representative — Congressional District 7 | Pramila Jayapal | Absent | Unregistered source |
| U.S. Representative — Congressional District 9 | Adam Smith | Absent | Unregistered source |
| Legislative District 32 State Representative — Position 1 | Keith Scully | Absent | Unregistered source |
| Legislative District 43 State Senator | Hannah Sabio-Howell, Jamie Pedersen | Absent | Unregistered source |
| Legislative District 46 State Senator | Javier Valdez | Absent | Unregistered source |
| Metropolitan King County Council — District 2 | Toshiko Grace Hasegawa, Rebecca Saldaña | Absent | Unregistered source |
| Metropolitan King County Council — District 8 | Teresa Mosqueda | Absent | Unregistered source |
| Washington Supreme Court Justice — Position 3 | Jaime Michelle Hawk | Absent | Unregistered source |
| Washington Supreme Court Justice — Position 4 | Ian Birk | Absent | Unregistered source |
| Seattle City Council — District 5 | Nilu Jenks | Absent | Unregistered source |

### 11th District Democrats

**Assessment:** Different absence semantics. Our explicit US House 9 no-endorsement record appears as a blank in Lefty’s data. Retain the explicit decision.

Official links: [source 1](https://us17.campaign-archive.com/?u=c75f17fe2b6e715cad36922d4&id=c0097e484d).

| Race | Lefty record | Our record | Difference |
| --- | --- | --- | --- |
| U.S. Representative — Congressional District 9 | Absent | Explicit no endorsement | Our record only |

### 37th District Democrats

**Assessment:** Different absence semantics. Our explicit US House 9 no-endorsement record appears as a blank in Lefty’s data. Retain the explicit decision.

Official links: [source 1](https://37dems.org/).

| Race | Lefty record | Our record | Difference |
| --- | --- | --- | --- |
| U.S. Representative — Congressional District 9 | Absent | Explicit no endorsement | Our record only |

### 43rd District Democrats

**Assessment:** Different absence semantics. Our explicit US House 9 no-endorsement record appears as a blank in Lefty’s data. Retain the explicit decision.

Official links: [source 1](https://43rddemocrats.org/endorsements/2026).

| Race | Lefty record | Our record | Difference |
| --- | --- | --- | --- |
| U.S. Representative — Congressional District 9 | Absent | Explicit no endorsement | Our record only |

### Progressive Voters Guide

**Assessment:** Different publication and methodology. Lefty uses Progressive Voters Guide recommendations. We count Fuse’s own endorsements and retain PVG as an excluded discovery/ownership record. Fourteen choice sets agree and 15 appear only in PVG. Those 15 are not automatically missing Fuse endorsements.

Official links: [source 1](https://www.progressivevotersguide.com/washington/2026/general/city/seattle).

| Race | Lefty record | Our record | Difference |
| --- | --- | --- | --- |
| U.S. Representative — Congressional District 9 | Adam Smith | Absent | Lefty only |
| Legislative District 11 State Representative — Position 1 | Ashley Fedan, David Hackney | Absent | Lefty only |
| Legislative District 32 State Representative — Position 1 | Danica Noble | Absent | Lefty only |
| Legislative District 32 State Representative — Position 2 | Imraan Siddiqi, Lauren Davis | Absent | Lefty only |
| Legislative District 34 State Representative — Position 2 | Joe Fitzgibbon | Absent | Lefty only |
| Legislative District 36 State Senator | Noel C. Frame | Absent | Lefty only |
| Legislative District 37 State Senator | Chipalo Street | Absent | Lefty only |
| Legislative District 43 State Senator | Jamie Pedersen | Absent | Lefty only |
| Legislative District 43 State Representative — Position 1 | Nicole Macri | Absent | Lefty only |
| Legislative District 46 State Senator | Javier Valdez | Absent | Lefty only |
| Legislative District 46 State Representative — Position 1 | Gerry Pollet | Absent | Lefty only |
| Legislative District 46 State Representative — Position 2 | Darya Farivar | Absent | Lefty only |
| King County Assessor | Rob Foxcurran | Absent | Lefty only |
| Metropolitan King County Council — District 2 | Rebecca Saldaña | Absent | Lefty only |
| Seattle Municipal Court Judge — Position 5 | Gabe Rothstein | Absent | Lefty only |

### The Urbanist

**Assessment:** General-election applicability unverified. The linked tag archive and official elections committee page still point to a primary-only publication. Obtain an official general publication or explicit carry-forward evidence before importing these 16 choices.

Official links: [source 1](https://www.theurbanist.org/tag/2026-endorsements/).

| Race | Lefty record | Our record | Difference |
| --- | --- | --- | --- |
| Legislative District 32 State Senator | Jesse Salomon | Absent | Lefty only |
| Legislative District 32 State Representative — Position 1 | Danica Noble | Absent | Lefty only |
| Legislative District 32 State Representative — Position 2 | Imraan Siddiqi | Absent | Lefty only |
| Legislative District 34 State Representative — Position 2 | Joe Fitzgibbon | Absent | Lefty only |
| Legislative District 37 State Representative — Position 1 | Kelabe Tewolde | Absent | Lefty only |
| Legislative District 37 State Representative — Position 2 | Jaelynn Scott | Absent | Lefty only |
| Legislative District 43 State Senator | Hannah Sabio-Howell | Absent | Lefty only |
| Legislative District 43 State Representative — Position 1 | Nicole Macri | Absent | Lefty only |
| Legislative District 46 State Senator | Javier Valdez | Absent | Lefty only |
| Legislative District 46 State Representative — Position 2 | Darya Farivar | Absent | Lefty only |
| King County Assessor | Rob Foxcurran | Absent | Lefty only |
| Metropolitan King County Council — District 2 | Rebecca Saldaña | Absent | Lefty only |
| Metropolitan King County Council — District 8 | Teresa Mosqueda | Absent | Lefty only |
| Washington Supreme Court Justice — Position 1 | Colleen Melody | Absent | Lefty only |
| Washington Supreme Court Justice — Position 3 | Jaime Michelle Hawk | Absent | Lefty only |
| Seattle City Council — District 5 | Nilu Jenks | Absent | Lefty only |

### PROTEC17

**Assessment:** Our choices supported by current source. The current official list supports Cindy Ryu, Danica Noble and Nicole Macri, which Lefty omits. Retain our records.

Official links: [source 1](https://www.protec17.org/endorsements/).

| Race | Lefty record | Our record | Difference |
| --- | --- | --- | --- |
| Legislative District 32 State Senator | Absent | Cindy Ryu | Our record only |
| Legislative District 32 State Representative — Position 1 | Absent | Danica Noble | Our record only |
| Legislative District 43 State Representative — Position 1 | Absent | Nicole Macri | Our record only |

### Washington Bus

**Assessment:** General heading now present; image position errors. The October 3 capture said primary; the current page says general. Its graphics support the seven candidate names, but the Kelabe Tewolde and Jaelynn Scott graphics swap LD37 House positions. Preserve that error and the ballot-based resolution in review records.

Official links: [source 1](https://www.washingtonbus.org/endorsements).

| Race | Lefty record | Our record | Difference |
| --- | --- | --- | --- |
| Legislative District 32 State Representative — Position 1 | Danica Noble | Absent | Lefty only |
| Legislative District 37 State Senator | Tatiana Brown | Absent | Lefty only |
| Legislative District 37 State Representative — Position 1 | Kelabe Tewolde | Absent | Lefty only |
| Legislative District 37 State Representative — Position 2 | Jaelynn Scott | Absent | Lefty only |
| Legislative District 43 State Senator | Hannah Sabio-Howell | Absent | Lefty only |
| Metropolitan King County Council — District 2 | Rebecca Saldaña | Absent | Lefty only |
| Seattle City Council — District 5 | Nilu Jenks | Absent | Lefty only |

### SEIU 925

**Assessment:** Our choice supported by current source. The current official list supports Danica Noble in LD32 House Position 1, which Lefty omits. Retain our record.

Official links: [source 1](https://www.seiu925.org/2026endorsements/).

| Race | Lefty record | Our record | Difference |
| --- | --- | --- | --- |
| Legislative District 32 State Representative — Position 1 | Absent | Danica Noble | Our record only |

### Working Families Party

**Assessment:** Incomplete source endpoint and collapsed index. The national 2026 candidate index supports the four missing choices after expanding Washington’s list. Our source was the state landing page. The same index also supports Shaun Scott in uncontested LD43 House Position 2, outside Lefty’s 31-race comparison and absent from our data.

Official links: [source 1](https://workingfamilies.org/candidates/).

| Race | Lefty record | Our record | Difference |
| --- | --- | --- | --- |
| Legislative District 36 State Senator | Noel C. Frame | Absent | Lefty only |
| Legislative District 37 State Representative — Position 2 | Jaelynn Scott | Absent | Lefty only |
| Legislative District 43 State Senator | Hannah Sabio-Howell | Absent | Lefty only |
| Legislative District 46 State Representative — Position 2 | Darya Farivar | Absent | Lefty only |

### Nondriver Action

**Assessment:** Outside registered panel; official support found. The official November list supports all four Seattle choices. Evaluate this organization separately under the source registration and frozen-panel policy.

Official links: [source 1](https://ndaction.org/2026-endorsements/).

| Race | Lefty record | Our record | Difference |
| --- | --- | --- | --- |
| Metropolitan King County Council — District 2 | Rebecca Saldaña | Absent | Unregistered source |
| Metropolitan King County Council — District 8 | Teresa Mosqueda | Absent | Unregistered source |
| Seattle City Council — District 5 | Nilu Jenks | Absent | Unregistered source |
| Seattle Proposition 1 — Seattle Transit Measure | Yes / Approve | Absent | Unregistered source |

### Washington Community Action Network

**Assessment:** Captured images omitted. The two official general graphics clearly endorse Saldaña and Mosqueda. The image URLs were already present in our October 3 capture, with empty alt text. Our reviewed ledger omitted them.

Official links: [source 1](https://www.washingtoncan.org/endorsements).

| Race | Lefty record | Our record | Difference |
| --- | --- | --- | --- |
| Metropolitan King County Council — District 2 | Rebecca Saldaña | Absent | Lefty only |
| Metropolitan King County Council — District 8 | Teresa Mosqueda | Absent | Lefty only |

## Limits

This is a complete comparison of the downloaded datasets and an investigation of every discrepancy group, not independent reverification of all matching endorsements. Publication dates of several changed lists were not established. Lefty may have private confirmations unavailable in its public evidence links. Times’ new choices, several social-media claims and the 15 GOP choices remain unverified. No code, repository data, issues or deployments were changed.
