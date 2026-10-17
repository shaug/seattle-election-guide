# October 16 remaining verification review

Scope: [verification task #545](https://github.com/shaug/seattle-election-guide/issues/545), following the merged [878-decision application](GENERAL_VERIFICATION_APPLICATION_2026-10-16.md). The user requested marking the Stranger verified and reviewing the remaining unknowns, then approved the two concrete additions below. The candidate now contains **880 decisions across 45 source blocks**. All 878 prior choices, statuses and allocations remain unchanged.

## Verified and applied

| Publisher | Result | Approval |
| --- | --- | --- |
| The Stranger | All 31 Seattle decisions verified unchanged against the user-supplied two-page PDF. The complete cheat-sheet graphic and repeated text agree; 25 other publication decisions are outside the frozen Seattle inventory. | [31-decision verification](../data/review/approvals/wa-2026-general-2026-10-16-stranger-verification.json) |
| Washington Conservation Action | Added **No on IL26-638**, allocation 1. The current official page explicitly prints the correct measure number; the earlier IL26-368 observation remains historical. No label override was needed. The other 25 decisions retain their prior approval and evidence locators. | [One-decision approval](../data/review/approvals/wa-2026-general-2026-10-16-wca-corrected-measure.json) |
| Washington Education Association | Added **Ashley Fedan, LD11 House Position 1**, allocation 1. Verified the other 19 decisions unchanged from the user-supplied PDF, preserving the LD32 House Position 1 equal dual endorsement. | [20-decision PDF review](../data/review/approvals/wa-2026-general-2026-10-16-wea-pdf.json) |

The Stranger verification follows the user's instruction, “let's mark the Stranger as verified and go through the remaining unknowns”. WCA's addition follows “Approve the WCA addition”. WEA's review follows “Approve WEA addition and PDF verification”. OpenAI Codex transcribed the evidence; shaug is the human verifier. Both PDF reviews have finite October 16 manual-verification acknowledgements, with actual review times and durable approval references. WCA's one-decision approval does not attest to a new review of its entire source block.

The WEA user confirmed the PDF came from a live browser view after clicking past the modal. The agent reviewed that supplied snapshot and made no membership certification. The two existing congressional rows remain explicitly attributed to NEA-PAC in the transcription and retain their prior approved ledger treatment; this follow-up makes no new federal attribution decision. The agent's live browser access remained restricted. The earlier access observations remain accurate for those attempts.

The Stranger PDF explicitly identifies the November 3 general election and prints an October 9 publication date. Its existing approved Noel Frame and Jamie Michelle Hawk identity mappings remain intact. The publication's statement about omitted or uncontested races does not create new per-race no-endorsement claims. This verification concerns the supplied PDF, without claiming an agent live-page read.

Both original PDFs remain privately retained by content hash. Public records contain metadata, normalized facts and short transcriptions. The WCA browser capture is honestly labeled as a manually preserved visible excerpt, not original response HTML; no HTTP status or redirect claim is invented. The immutable proposals, pending manual entries and verified successors remain linked through their approval records.

## Remaining unknowns

| Publisher | Current evidence | Treatment |
| --- | --- | --- |
| Washington Stonewall Democrats | Revisited the [official public profile](https://www.facebook.com/stonewallwa/). Latest accessible post remains July 16; the known July 6 endorsement publication is primary-only. No official general-election list or explicit carry-forward statement was found. | General-election endorsement status remains unknown. No primary choices are carried forward and no no-endorsement decision is invented. |
| Washington for Peace and Justice | Rechecked the retained [official October 15 guide](https://www.instagram.com/wa4pj/p/Deh8Qd4gZen/) legend. Grey can mean likely supportive **or** running against someone opposed to the organization's interests. Colleen Melody (Supreme Court Position 1) and Ian Birk (Position 4) remain grey. | Both ratings remain unresolved and unscored. They are neither affirmative endorsements nor declined-to-endorse records. The previously approved 31 unambiguous decisions remain intact. |
| Washington Bikes | Revisited the [current general table](https://wabikes.org/index.php/advocacy/endorsements/) and its linked [news index](https://wabikes.org/index.php/blog-news/). The table supports 19 of the 22 prior decisions but still omits Imraan Siddiqi (LD32 House Position 2), Yes on Seattle Transit Proposition 1 and No on IL26-001. No explicit withdrawal or newer clarifying general publication was found; the latest visible endorsement news item is the July 16 primary post. | Preserve all 22 prior approved decisions. The three omissions remain flagged for clarification; absence does not establish withdrawal. |

These three groups exhaust the endorsement-data unknowns from the earlier browser retry after the approved ECC, Sierra Club, WA4PJ, office-correction, Stranger, WCA and WEA follow-ups. A primary-only list, an ambiguous rating and an omitted prior choice remain different evidence conditions. None supplies an implicit No or zero-point decision.

Six automatic-adapter baseline approvals and broader daily or whole-panel attestations remain separate workflow work under #497/#545. This follow-up creates none of those approvals and does not close the daily verification issue. Its two finite acknowledgements cover only the Stranger and WEA reviews explicitly approved here.

## Reviewed input bindings

The `2026-general.8` candidate binds the following approved inputs at 880 decisions. During preparation of this review, the latest published release was `2026-general.6` and no `.7` tag existed. The 878-decision `2026-general.7` archive was published concurrently from `20e80b74dc5b2e85807f88c2327bfe74aac7207d` before this follow-up merged. The maintainer then explicitly selected a new `.8` publication for these 880 decisions, preserving `.7`. This document does not itself publish or deploy a release. The source panel, source registry, inventory, eligibility and scoring rules are unchanged.

| Input | SHA-256 |
| --- | --- |
| `data/releases/wa-2026-general/source-decisions.yaml` | `1286c04ba2b8c38081f1f77d0d7789bdc95402bf52b955c7d4965625240f9b6e` |
| `data/normalized/wa-2026-general-canonical-dataset.json` | `da873f6755f0b83a82e1a5c5a00acbc3ed576dd52035aed65e76d5a6e241cd7c` |
| `config/sources/wa-2026-general.yaml` | `b768ab12d366d345a7886c8dc3a61438ff2cc33a52042b49cf5eb7c505e7dd0f` |

The semantic audit compares every prior source/race decision against commit `100ef8c9343f8705f7a873427f24323d8b36fc92`: exactly two additions, no removals, no replacements and no allocation changes. All preexisting append-only proposals, approvals, manual records, original evidence manifests and verification records remain byte-identical. Release compilation replaces the two affected current-generation extracts; their earlier generations remain in Git history and their original evidence manifests remain intact.
