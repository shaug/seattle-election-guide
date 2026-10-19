# October 16–18 verification closeout status

Refs [#545](https://github.com/shaug/seattle-election-guide/issues/545), [#560](https://github.com/shaug/seattle-election-guide/issues/560), and [#567](https://github.com/shaug/seattle-election-guide/issues/567).

The 34 approved additions are applied: **914 decisions across 46 publishers**, with all 880 prior decision dictionaries preserved. The [application record](GENERAL_VERIFICATION_APPLICATION_2026-10-18.md) and immutable approval bind every change to its evidence. The 37 current manual-source reviews and six exact automatic baselines have separate explicit human approvals, recorded at actual time `2026-10-19T04:14:31.209146Z`. The resulting [attestation record](../data/review/approvals/wa-2026-general-2026-10-18-verification.json) links six baseline approvals, 111 manual acknowledgements and 15 verified transcription successors. A subsequent [WEA/Sierra approval](../data/review/approvals/wa-2026-general-2026-10-18-wea-sierra.json), recorded at `2026-10-19T04:30:32.442975Z`, adds five acknowledgements and two verified successors for 44 unchanged decisions. The subsequent [Stranger image approval](../data/review/approvals/wa-2026-general-2026-10-18-stranger.json), recorded at `2026-10-19T04:36:18.741704Z`, adds the final two acknowledgements and one verified successor. Together with the two earlier October 16 acknowledgements, **all 120 manual-source date obligations are acknowledged**. All six required baseline snapshots are also human-approved.

All 144 original issue observations and the two prior October 16 Stranger/WEA human acknowledgements remain intact. Current reviews resolve past-due work at their actual time; they do not establish missed historical webpage contents. All three tickets remain open pending applicable merged publication evidence.

## Source access recovery

| Publisher | Current evidence | Current disposition |
| --- | --- | --- |
| OneAmerica Votes | Complete official web representation reviewed unchanged at 17 decisions; subsequently the corrected collector retained the original HTML with HTTP 200 and zero redirects. | Current human review is included in the 37 approved sources. The original-byte access limitation is resolved. |
| Transit Riders Union | Corrected collector retained original HTML with HTTP 200 and zero redirects. All eight article list items match the authenticated original; full page bytes differ. | Exact earlier baseline is human-approved. Earlier failed automatic observations remain immutable; the transport correction is separate evidence and not a backdated scheduled success. |
| WEA | At the user’s explicit instruction, Proceed was clicked normally. The current public list was fully read and matches all 20 approved decisions, including the existing equal dual and NEA-PAC attribution. Derived visible-text evidence and a supplemental screenshot are retained. | Human review for October 17/18 is approved in the [WEA/Sierra packet](GENERAL_WEA_SIERRA_2026-10-18.md). The October 16 PDF acknowledgement remains intact. |
| Sierra Club Washington | The current official main page loads normally without a CAPTCHA; all 24 approved decisions match. Its invalid initiative link resolves to a nonpublisher single-label hostname and was not followed. The main page explicitly states No on IP26-645 and Yes on Seattle Transit. | Human review for October 16/17/18 is approved in the same packet. No new decision is inferred from an inaccessible or malformed link. |
| The Stranger | The user supplied the complete two-column general-election cheat-sheet PNG. All 56 recommendations are accounted for: 31 unchanged decisions in the frozen inventory and 25 outside. The original image is retained unmodified; live-page access remains blocked and is not asserted. | The [supplied-image review](GENERAL_STRANGER_2026-10-18.md) and October 17/18 actual-time acknowledgements are human-approved. The earlier October 16 acknowledgement remains intact. No endorsement or name mapping changed. |

Washington Bikes’ three omitted prior choices remain without withdrawal inference: Imraan Siddiqi, Yes on Seattle Transit Proposition 1 and No on IL26-001. WA4PJ’s grey Melody and Birk ratings remain unresolved and unscored. The human 37-source approval expressly preserves those treatments.

## Authenticated exact baselines

The maintainer’s original private 1Password key authenticated and restored all 71 archived captures, including SGN’s underlying indices and articles. The [receipt](../data/review/evidence-authentication/wa-2026-general-2026-10-18.json) records AES-GCM, original SHA-256 and length validation without a key or source text. No key was printed, persisted, replaced or committed. The [six-baseline packet](GENERAL_BASELINES_2026-10-18.md) accounts for 87 mapped decisions and all 99 broader approved source decisions, including the 12 fixed-adapter omissions.

The archive imported from `a0aa1050659d1459662d6bd260dd20a60c94ce55` preserves the pending [evidence PR#566](https://github.com/shaug/seattle-election-guide/pull/566). Its verification data matches the original reviewed `7e9c59c0602dbd1f0caf8d00c999a966e1b5c72a` archive. No existing raw capture, envelope or historical observation was rewritten. The six new approvals use the existing approval command and exact snapshot identities.

These attestations do not mark [#497](https://github.com/shaug/seattle-election-guide/issues/497) adopted. Independent scheduled baseline reuse through the deployed workflow remains separate adoption work. No fixture, no-due workflow success or local probe is presented as that evidence.

## Collector correction and publication

The collector created an HTTP connection object around a manually validated TLS socket, causing the request serializer to append `:443` to the Host header. WordPress redirected every such TRU request to the same HTTPS URL until the existing ten-redirect cap failed. Offline request serialization reproduced the defect; a guarded single-variable validation confirmed the cause. The correction uses `HTTPSConnection` with the existing SSL context and validated socket for TLS, retaining `HTTPConnection` for HTTP.

Six offline regression cases cover default and nondefault HTTP/HTTPS ports. The existing public DNS and connected-peer validation, TLS validation, handshake deadline, total timeout, size ceiling, HTTPS downgrade rejection, request identity and ten-redirect cap are unchanged. The actual implemented collector subsequently fetched both TRU and OneAmerica with HTTP 200 and zero redirects; their original bytes remain private.

The prepared `2026-general.13` request is owned by #567 and supports #545/#560. It includes an Updates entry covering every approved addition and the resulting LD11 House 1 tie. A merged PR, release asset, production deployment and finite-ticket closure must be recorded from their actual results; none is asserted by this preparation document. Closing references are withheld while required post-merge evidence is incomplete.

## Validation before publication

The full `make check` passed with 1,787 Python tests, 735 JavaScript tests, no lint/type failures, and the generated changelog check. Subsequent validation passed for all 515 archive records and 542 evidence manifests after the final additive attestations. Private original hashes and approval bindings are checked separately from the public gate, which correctly allows restricted source bytes to remain private. The release declaration requests `2026-general.13`; a clean candidate build and its actual review evidence remain required before merge.
