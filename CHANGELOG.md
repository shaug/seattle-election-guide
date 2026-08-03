# Changelog

Site and code changes, generated from commit history by
[git-cliff](https://git-cliff.org). Do not edit by hand: CI regenerates this
file and fails when the result differs from what is committed.

This is not the record of what the guide *said*. Endorsement data, source
coverage, and the audit trail for one published election live in that release's
own `RELEASE_NOTES.md`, inside its bundle and attached to its GitHub Release.
This file covers the software that renders and ships those bundles.

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

