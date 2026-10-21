# October 21 WFP scheduled baseline reuse

Issue [#497](https://github.com/shaug/seattle-election-guide/issues/497) requires
later independent native scheduled reuse after a complete baseline review.
WFP now has that source-specific evidence. The runbook remains proposed:
the other sources and complete coverage still have outstanding obligations.

The normal [scheduled run 39572435639](https://github.com/shaug/seattle-election-guide/actions/runs/39572435639),
attempt 1, ran the deployed source revision
`d3a063d8504e9aaaace8d6e320e4659146c0bad9`. Its actual due-source observation
was `2026-10-21T08:51:44Z`, after the Pacific date changed. The
[live receipt](../data/verification/runs/d8598a0d980ba1c7f3924078953e46152fb1fe97605eaf4195a71f782ff14524.json)
records a clean source tree, six automatic sources, forty manual obligations,
no missed checks, and policy fingerprint
`3da483c924a7eff327e07204acdf4fc04508b00c5a6285efa40babcc6069841d`.
The archive commit is `1a9ec2be251765e2830431b7660ac9e59e9a2db9`.

WFP's [refresh event](../data/verification/wa-2026-general/refreshes/refresh-washington-working-families-party-20261021T085144Z-ce991888e429.json)
records `unchanged`, `content_changed: false`, and an empty decision diff. Its
previous and current snapshot are both
`extraction-washington-working-families-party-20261020T085058Z-27e58e61bbe6`;
the receipt records `baseline_reviewed: true`. The original is 2,383 bytes with
SHA-256 `193b7dbe1a1e2883513cc49a6c434ab19689a377623774295d7c4fc994890574`.
The configured public POST still retrieves the complete Washington table.

The [actual October 20 baseline review](GENERAL_BASELINE_2026-10-20_WFP.md)
named OpenAI Codex `/root/review_497_wfp_oct20` and recorded its completed
context review at `2026-10-20T10:07:11.637698Z`, under the finite maintainer
delegation. It read all seventeen rows: ten existing in-inventory endorsements
and seven outside-inventory exclusions. That approval and its exact snapshot,
capture and encrypted original remain unchanged. Root inspected the later
native run, receipt, event and preserved approval; no new source approval,
operator check, fixture, dispatch or no-due execution supplies this result.

The same run retained three changed, unapproved baselines for SGN, Sage and
UFCW. TRU failed and retained its October 20 baseline; SEIU failed for its fifth
consecutive slot and remains escalated. The generic native errors do not identify
a transport or parser cause. A separate ordinary TRU diagnostic later observed
HTTP 404 on the registered page and a maintenance notice on the official home
page. That observation supplies context, not proof of the native failure's cause
or a successful recovery. Complete exact-original reviews, genuine failure
resolution and manual-source coverage remain explicit obligations. Neither #497
nor the October 21 daily issue closes through WFP's successful reuse alone.
