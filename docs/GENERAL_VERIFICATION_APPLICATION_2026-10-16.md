# October 16 approved endorsement application

> Subsequent follow-up: the [remaining verification review](GENERAL_VERIFICATION_REMAINING_2026-10-16.md) records the Stranger and WEA PDF verifications and two further approved additions, bringing the `2026-general.8` candidate to 880 decisions. The 878-decision application and input bindings below belong to the immutable published `2026-general.7` archive.

Scope: [verification task #545](https://github.com/shaug/seattle-election-guide/issues/545). This follows the [original prepared research packet](GENERAL_VERIFICATION_2026-10-16.md), which remains a historical preparation snapshot.

shaug approved the original concrete packet with “approved. let's apply the 114 additions and the replacement to the guide”, then approved five enumerated ECC changes with “Include the ECC changes”. The [immutable approval record](../data/review/approvals/wa-2026-general-2026-10-16.json) records the actual approval transcription time, `2026-10-16T15:48:50.280092Z`, the exact proposal and browser-facts hashes, original captures, every prior/new value and 15 verified manual successors. The original proposals and pending entries remain immutable. OpenAI Codex is the transcriber; shaug is the verifier.

The release candidate now contains **878 decisions across 45 source blocks**: 703 prior decisions plus 175 additions and two replacements. Six published sources are newly represented: Planned Parenthood Alliance Advocates, Seattle Subway, The Urbanist, Washington State Democrats, Sierra Club and Washington for Peace and Justice. The two replacements are AFT Washington’s LD32 Senate choice (Jesse Salomon → Cindy Ryu) and ECC’s LD43 Senate choice (Jamie Pedersen → Jamie Pedersen / Hannah Sabio-Howell, allocated 1/2 each).

Every other prior choice, status and allocation remains intact. This includes Washington Bikes’ three held absences—Imraan Siddiqi, Seattle Transit Yes and IL26-001 No—and all previously approved co-endorsement splits. Seattle Times remains comparison-only. PPAA’s Mosqueda office correction was specifically approved in the later batch; national Action Fund congressional endorsements remain excluded from this regional source. No panel membership, category, code, eligibility, overlap, scoring or primary-election input changed. Only the six discovery dispositions needed to admit approved publications were updated across the two approval batches.

## ECC browser recovery and approved supplement

The [official ECC list](https://eccwa.org/wp/endorsements/2026-endorsed-candidates/) was readable in the in-app browser after the bounded collector failures. Its general-election framing states that the vote ran September 8–15 and that primary endorsements carry forward. The user explicitly approved four additions—Pramila Jayapal (US House 7), Adam Smith (US House 9), Mary Anito (LD34 House 2), and Julia Grant Reed (LD36 House 1)—and replacing the LD43 Senate single choice with Jamie Pedersen / Hannah Sabio-Howell, allocated 1/2 each. ECC now has 14 decisions; its other nine choices remain unchanged.

The [immutable supplement](../data/review/proposals/wa-2026-general-2026-10-16-ecc-supplement.json) binds the exact browser-facts hash, manually preserved visible excerpt, capture and pending transcription. The capture is honestly recorded as `manual_upload`, `text/html`, `browser_required: true`, with no HTTP status or redirect claim. The generated HTML only wraps manually preserved visible words; it is not original response HTML. Private bytes live in the durable primary-checkout store. The approval record links the verified successor and preserves the prior single choice.

## Subsequent browser approval

The [browser retry](GENERAL_BROWSER_RETRY_2026-10-16.md) covers all ten unresolved publishers and four additional flagged publications. shaug then directed: “Apply all 54 decisions and all three explicit corrections”. The [separate immutable approval](../data/review/approvals/wa-2026-general-2026-10-16-browser-retry.json), recorded at `2026-10-16T16:05:10.192531Z`, adds 57 previously absent source/race decisions: Sierra Club 24, WA4PJ 31, AGR one and PPAA one. It binds the exact pending proposal, capture hashes, nine verified manual successors, four Sierra name mappings, three court terminology mappings, and three explicit office overrides. The original 120-change approval and both pending proposals remain immutable.

| Publisher | Preserved printed label | Approved ballot match |
| --- | --- | --- |
| WA4PJ | LD-11 Rep 12: Steve Bergquist | LD11 House Position 2 |
| Alliance for Gun Responsibility | State House of Representatives / District 21 / Position 2: steve bergquist | LD11 House Position 2 |
| Planned Parenthood Alliance Advocates | King County Council Teresa Mosqueda, District 6 | King County Council District 8 |

The retained AGR and PPAA original captures were checked again to confirm these exact printed conflicts before using their hashes. The WA4PJ image likewise preserves the Rep 12 label. Under WA4PJ’s explicit Supreme Court heading, “District” 3, 5 and 7 maps to statewide Positions 3, 5 and 7. Sierra’s “Chiaplo Street,” “Julia Reed,” “Jaime Hawk” and “Noel Frame” map to the unique candidates in their stated offices, with source spelling preserved.

WA4PJ’s US House 9 and Supreme Court Position 7 red blank/off-ballot-write-in recommendations are recorded as `declined_to_endorse`, with no candidate IDs and zero points. Its grey Colleen Melody and Ian Birk ratings remain unresolved and excluded. Washington Conservation Action’s IL26-368 label and Washington Bikes’ three absences remain held.

## Remaining work

The `2026-general.7` release declarations, hosting contract, CI, runbooks and version-pinned tests are prepared for this material data update. Publication, release lineage, production approval and public-route verification remain separate gates. No release has been published or deployed by this application. Six verification-adapter baseline approvals and daily or whole-panel human attestations remain separate; none was created. Remaining inaccessible, primary-only and ambiguous evidence and the held absences remain outside the 177 approved source/race changes. No historical verification was backdated.

## Initial 120-change input bindings (historical)

These hashes preserve the first approved application at 821 decisions. They are historical inputs; the final release uses the later bindings below. Release and production commit identities follow the existing separate lineage and deployment gates. The panel remains `wa-2026-general-default-sources-v2` with stable panel hash `5b9645bcfd45f9749ca6602e70b748e3b45566f9feee1fc67c729cf60a893569`; only the four discovery dispositions needed to admit the approved publications changed.

| Input | SHA-256 |
| --- | --- |
| `data/releases/wa-2026-general/source-decisions.yaml` | `e4382f12df31a3e9bbf50c96f9ba4d5f49774722c3364204b8d4b64265a3324b` |
| `data/normalized/wa-2026-general-canonical-dataset.json` | `082bac49e4b26f0e327a01a24d3deb9a7c408f3c40f5f78d85ffd87a98d3e9ea` |
| `config/sources/wa-2026-general.yaml` | `b876a55161f59b94112164b59888abb0572f14d7139efad60fd8158b279f791c` |

## Reviewed input bindings

The final `2026-general.7` candidate must match these inputs after both approvals, with 878 decisions and 45 source blocks. The stable panel remains `wa-2026-general-default-sources-v2` with hash `5b9645bcfd45f9749ca6602e70b748e3b45566f9feee1fc67c729cf60a893569`.

| Input | SHA-256 |
| --- | --- |
| `data/releases/wa-2026-general/source-decisions.yaml` | `c9d1b5a36910bbca155bb2abc6d257873e4cfcc57888fdfe3b48e9cf8d069781` |
| `data/normalized/wa-2026-general-canonical-dataset.json` | `e72a55ed235da0b93c7f3b2cbad3d8ffa773b7095b0cd00cc4d396273c86c9d7` |
| `config/sources/wa-2026-general.yaml` | `b768ab12d366d345a7886c8dc3a61438ff2cc33a52042b49cf5eb7c505e7dd0f` |
