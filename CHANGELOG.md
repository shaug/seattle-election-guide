# Changelog

Site and code changes, generated from commit history by
[git-cliff](https://git-cliff.org). Do not edit by hand: CI regenerates this
file and fails when the result differs from what is committed.

This is not the record of what the guide *said*. Endorsement data, source
coverage, and the audit trail for one published election live in that release's
own `RELEASE_NOTES.md`, inside its bundle and attached to its GitHub Release.
This file covers the software that renders and ships those bundles.

## 2026-general.4 — 2026-10-04

### Documentation

- Add 2026-general.3 changelog (#489)

### Fixed

- Distinguish earliest ballot availability (#490)
- Refresh general endorsements and prepare 2026-general.4 (#493)
- Reject ingest certification dates that disagree with calendar (#492)

### Tooling

- Archive zone rollups through 2026-10-04 (#494)
- Bump the npm-dependencies group across 1 directory with 3 updates (#468)
- Bump the python-dependencies group across 1 directory with 2 updates (#443)
## 2026-general.3 — 2026-10-03

### Documentation

- Add 2026-general.2 changelog (#485)

### Fixed

- Make the endorsement meter rollback-proof (#488)

### Other

- Restore the final Meter v2 interaction (#487)
## 2026-general.2 — 2026-10-03

### Documentation

- Add 2026-general.1 changelog (#479)

### Fixed

- Replace endorsement pill with visible segments (#484)
## 2026-general.1 — 2026-10-03

### Added

- Add a supported way to compute the bundle_sha256 pin (#358)
- Add banner counting and certified post-election states (#339)
- Add certified result as an addable Comparisons column (#351)
- Add meter v2 color tokens and the exact-rational count formatter (#318)
- Add the results schema, validator, and rendering hook (#336)
- Allow one unpublished current hosting candidate (#460)
- Archive zone rollups before Cloudflare's window drops them
- Assert every declared release version is published (#257)
- Certified-results CSV ingestion adapter (#338)
- Declare the election calendar as repository data (#262)
- Declare the live 2026 primary's results-capture windows (#265)
- Deploy labeled pull requests to their own Pages preview (#263)
- Detect link rot in cited sources (O17) (#383)
- Draw a race's social card, and vendor the font that can spell it (#307)
- Escalate calendar milestones whose promised artifact never appeared (O12 follow-up) (#386)
- Generate the site changelog from commit history (#267)
- Give counting authorities their own capture lane (#281) (#337)
- Give every candidate a meter in their own section (#335)
- Grow a certified results strip on candidate race cards (#340)
- Grow the endorsements dialog's certified strip and vote-share rows (#345)
- Include Tech 4 Taxes in 2026 general endorsements (#466)
- Index only the canonical host (#255)
- Ingest wa-2026-primary certified results (#413)
- Lay out the segmented meter once, in two languages (#319)
- Migrate race detail to real race URLs with per-race social cards (#308)
- Open tracking issues from calendar milestones (#273)
- Publish a subscribable calendar feed of voter-facing election dates (#293)
- Render a per-election corrections page (#350)
- Render meter v2 on race social cards (#332)
- Resolve historical bundles from their published releases (#261)
- Reuse the candidate results component for measures (#352)
- Separate stable panel identity from registry audit hash (#438)
- State the complete certified result on a race page (#374)
- Swap the meter chrome to meter v2 across guide, race, compact, and print (#321)
- Verify post-tag release lineage (#462)
- Verify production is up and serving the expected commit (O14) (#377)

### Changed

- Dedupe the results-chip rule into guide-race.css (#355)
- Extract shared single-issue GitHub alert tracker (#404)
- Give the two fragment codecs one shared vocabulary (#294)
- Split renderer.py one concern per module (#277)

### Documentation

- Add the post-election retrospective checklist (#268)
- Confirm the client-side beacon works automatically (O10) (#375)
- Correct certified CSV filename in results ingest runbook (#414)
- Document credential and hosting ownership (O19) (#366)
- Document the production approval gate (#258)
- Establish the zone-analytics baseline (O9) (#360)
- Formalize the agentic runtime as runbooks (#272)
- Mock up a meter in every candidate's own section (#326)
- Name the field to trend, and why it is not requests (#412)
- Ratify meter v2, the segmented meter (#310)
- Ratify the measure results design pass (#349)
- Ratify the race-detail page's complete certified result (#371)
- Record the ratified post-election results design (#266)
- Say why this exists, and what licenses the voice (#317)
- Stop describing www attachment as still pending (#402)
- Stop hardcoding the LEGACY_HOSTS count (#394)
- Write and rehearse the production rollback procedure (#364)
- Write the endorsement discovery sweep (#363)

### Fixed

- Account for the results-capture and corrections links in expected_html_links (#356)
- Close two false negatives in the inline-script metric (#291)
- Confirm link rot by cause, not by repetition alone (#418)
- Correct primary certification offset and capture wa-2026-primary certified results (#407)
- Declare the sticky header's compositing promotion (#385)
- Fail preview teardown loudly when wrangler's projection goes stale (#389)
- Finish www routing to the apex (#393)
- Hold a race id to a slug, because it is about to be an address (#305)
- Let the sources page check the receipts it renders (#306)
- Make captured official-authority bytes outlive their session (#372)
- Make the release capture deterministic, and name the artifact that differs (#368)
- Notice a milestone on the day, without depending on a label (#320)
- Pin the persistent action strip's height to a whole pixel (#343)
- Pin the race page's lens strip like the guide's own (#369) (#376)
- Remove the per-race-card counting note (#346)
- Resolve released bundles in the PR preview staging step (#362)
- Resolve released bundles in the local staging target (#359)
- Seat the no-majority pill under the name it qualifies (#229)

### Other

- Alert on stale published data (#429)
- Automate analytics archive PR checks and merges (#439)
- Close out the front-end architecture epic: delete the grandfather lists, and make every rule say what holds it (#296)
- Complete initial 2026 general discovery sweep (#437)
- Declare every shared template/JS/CSS name once, and check it (#280)
- Extract the guide and sources inline glue into real modules (#260)
- Freeze the carried-forward 2026 general source panel (#430)
- Give each page its own CSS entry point (#276)
- Make release manifests reproducible without hashing rasterized screenshots (#435)
- Move every full HTML document onto one shared Jinja layout (#275)
- Name a race's leading choice once, and stop counting the list below it (#309)
- Parallelize CI checks and browser integration tests (#431)
- Recheck drifted endorsement sources; propose daily verification (#323)
- Record the 2026-08-04 election-night results capture (#322)
- Render the guide and sources lens regions with lit-html
- Say what happened when a comparison link fails, and give the page one address-bar owner (#278)
- Watch the collection opening artifact window (#434)
- Automate dependency updates (O18) (#378)
- Ingest Secretary of State totals for the eight cross-county races (#419)
- Make the general release runbook executable (#478)
- Refresh 2026 general endorsements (#475)

### Tests

- Fixture the surviving Python↔JS mirrors, and derive their inventory (#295)
- Stop asserting a dependency version the lockfile already pins (#388)
- Wait for the history re-render instead of sleeping (#390)

### Tooling

- Add general election release targets (#459)
- Archive zone rollups (#415)
- Archive zone rollups through 2026-08-16
- Archive zone rollups through 2026-08-17
- Archive zone rollups through 2026-08-19 (#405)
- Archive zone rollups through 2026-09-21 (#441)
- Archive zone rollups through 2026-09-22 (#444)
- Archive zone rollups through 2026-09-23 (#454)
- Archive zone rollups through 2026-09-24 (#455)
- Archive zone rollups through 2026-09-25 (#461)
- Archive zone rollups through 2026-09-26 (#463)
- Archive zone rollups through 2026-09-27 (#464)
- Archive zone rollups through 2026-09-28 (#467)
- Archive zone rollups through 2026-09-29 (#469)
- Archive zone rollups through 2026-09-30 (#470)
- Archive zone rollups through 2026-10-01 (#471)
- Archive zone rollups through 2026-10-02 (#473)
- Archive zone rollups through 2026-10-03 (#477)
- Bump the npm-dependencies group across 1 directory with 3 updates (#432)
- Bump the npm-dependencies group across 1 directory with 4 updates (#423)
- Bump the npm-dependencies group across 1 directory with 5 updates (#379)
- Bump the python-dependencies group across 1 directory with 5 updates (#424)
- Bump the python-dependencies group with 2 updates (#400)
- Bump the python-dependencies group with 3 updates (#380)
- Bump the python-dependencies group with 3 updates (#433)
- Cut staging to the 2026 general guide (#476)
- Format the PROJECT.md protocol snippet the way ruff 0.16 does (#391)
- Import the 2026 general ballot inventory (#427)
- Initialize 2026 general (#426)
- Move one 2027 date to verify subscribed events update in place (#333)
- Revert the temporary 2027 date used to verify subscribed updates (#334)
## 2026-primary.2 — 2026-08-02

### Added

- Activate Comparisons (#197)
- Add Washington Stonewall primary endorsements (#53)
- Add actionable sticky state strips (#158)
- Add comparison signal engine (#169)
- Add election-scoped guide routes
- Add server-rendered comparisons page (#170)
- Add shareable race endorsement detail panels (#73)
- Add stable source and category identities (#84)
- Add the deterministic personalized-lens engine (#87)
- Add the versioned personalized-lens URL codec (#86)
- Adopt the shell grammar and its two new primitives (#195)
- Automate Cloudflare Pages publishing (#57)
- Automate source adapter refreshes (#22)
- Bundle client modules with esbuild, one entry per page (#251)
- Complete the client payload contract and generate its types (#253)
- Compose sources page context (#161)
- Condense printable race cards into three-line rows (#36)
- Define election archive manifest (#69)
- Expose category and overlap analysis (#23)
- Generate canonical election titles (#160)
- Hide the Times comparison behind one Customize action (#88)
- Initialize future elections offline (#24)
- Keep guide sources strip visible (#188)
- Make over the Comparisons page (#194)
- Mark races without a majority (#168)
- Organize races by ballot sections and jurisdiction
- Present comparison differences (#172)
- Present personalized results and audited divergence (#91)
- Publish comparison display contract (#165)
- Publish the personalized-lens calculation contract (#85)
- Redesign printable guide for scanability (#34)
- Redirect legacy hosts to canonical domain (#60)
- Refine printable visual treatment (#38)
- Render the Comparisons table with lit-html, and prove the idiom (#254)
- Resolve cross-version personalized-lens migration (#89)
- Retire the Endorsements-page Times comparison in favor of Comparisons (#231)
- Retire the generated PDF edition; keep the guide printable (#247)
- Separate source coverage gaps (#55)
- Simplify Seattle Times comparison chips (#32)
- Simplify voter guide endorsement consensus (#30)
- Slim shared site footer (#189)
- Soft-launch comparison route (#178)
- Unify responsive recommendation rows (#47)

### Documentation

- Add front-end code guidelines and agent authority map (#198)
- Correct the operations plan's pre-filing status language (#230)
- Explain election archive operations (#72)
- Plan site operations work as epics and tickets (#228)

### Fixed

- Align sources sticky actions (#159)
- Anchor footer on short pages (#164)
- Clarify footer update dates (#180)
- Compact mobile race dialog header (#185)
- Contain phone dialog metrics (#162)
- Let page measure govern ledes (#191)
- Let the first comparison column be removed like any other (#201)
- Make the page head's contract visible at its call sites (#196)
- Prioritize source strip actions (#187)
- Rename methodology navigation (#186)
- Rewrite public-facing site prose (#190)
- Stack phone race card results (#163)
- Unify guide controls and action icons (#166)
- Untie the Comparisons unfurl text from the default preset (#200)

### Other

- Add Sierra Club and broader LD endorsement coverage (#28)
- Add UI polish round-5 candidates ledger (#147)
- Add a compact contested-race ballot mode (#74)
- Add a non-tallying comparison category kind to the personalization contract (#99)
- Add category and direct-source customization (#90)
- Add site UI/UX guidelines (docs/DESIGN.md) (#148)
- Archive the Compare-page planning prototype (#125)
- Build the /e/<election_id>/sources/ page (#111)
- Build the interactive comparison grid (#171)
- Compact the guide identity and responsive shell (#46)
- Complete 2026 primary source coverage (#26)
- Complete OG/Twitter tags and switch to summary_large_image (#137)
- Consolidate Methodology into About (#112)
- Cut the guide over to the dedicated sources page (#113)
- Eliminate residual print pill geometry inconsistencies (#49)
- Expand the 2026 endorsement source panel (#67)
- Fix mobile Safari rendering of race-detail candidate names
- Fix sources-tree UI issues found after #94 shipped (#105)
- Fold the Seattle Times visibility flag into the general selection model (#100)
- Implement the comparison fragment codec (#167)
- Lens correctness: one answer per quantity (H30-H32, I56, K51) (#139)
- Let the race-detail candidate heading wrap instead of crushing the name (#145)
- Make the public guide discoverable and add footer links (#58)
- Optically center print labels and refine PDF typography (#40)
- Publish an accessible About/FAQ and sharing layer (#93)
- Race-card anatomy and data-ink cleanup (#138)
- Rebuild the sources section as one merged, collapsible tree (#101)
- Reconcile race-detail dialog hash routing with the personalized lens (#144)
- Redesign PDF page 2 around a linked source directory (#48)
- Rename the guide's public name from Endorsement Guide to Elections Guide (#104)
- Roll the shell grammar out to every remaining page (#199)
- Round 4 dialog corrections: candidate order, reference-bar position, confidence-flag removal, stray meter (#143)
- Round 4 groundwork: token, color, and microcopy sweep (#129) (#133)
- Show source participation and streamline guide disclosures (#51)
- Spec the Round 4 UI polish pass (docs only) (#127)
- Stack the mobile metrics column: meter beside the name, count below (#146)
- UI polish pass: one cohesive site (brand, shell, tokens, meters, comparison bars) (#126)
- Unify the site shell: one frame, one masthead, one footer (#134)
- Validate and activate the personalized source lens (#92)
- Validate the page split and activate (#114)

### Tests

- Enforce the FRONTEND.md rules that are checkable today (#249)

### Tooling

- Type-check the client modules with tsc, and adopt Biome (#252)
## 2026-primary.1 — 2026-07-20

### Added

- Add canonical endorsement normalization (#17)
- Add canonical publication exports (#19)
- Add deterministic consensus scoring (#18)
- Import authoritative Seattle ballot inventory (#14)
- Publish reproducible primary release workflow (#21)

### Other

- Freeze the 2026 primary source panel (#15)
- Implement evidence capture and manual entry (#16)
- Render and validate the responsive election guide (#20)

### Tooling

- Bootstrap election guide project (#13)
- Initialize repository

