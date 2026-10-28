# Finite recurring-verification adoption — October 28, 2026

Scott approved the revised acceptance criterion for
[#497](https://github.com/shaug/seattle-election-guide/issues/497) on **October 28 at
03:12 UTC, known to minute precision**. The decision accepts genuine normal
scheduled WFP approved-baseline reuse plus meaningful existing source-specific
automated coverage. Four additional successful live TRU, Sage, UFCW and SGN reuse
demonstrations are not adoption gates.

This is adoption of the implemented verification process, not approval of an
unobserved source result. First, changed and unapproved factual baselines still
require exact official-source review under [REVIEW_GUIDE.md](../REVIEW_GUIDE.md).
Equal mapped facts do not justify inheriting another snapshot's approval or
discarding unknown wording, article membership, required images or full input
changes. The prior criterion is preserved below as superseded history.

## Actual scheduled WFP evidence

The normal [October 27 run 40476661213](https://github.com/shaug/seattle-election-guide/actions/runs/40476661213),
attempt 1, made its WFP observation at **2026-10-27T08:53:43Z**. Its
[live receipt](../data/verification/runs/3ede6ffaee4a93a02abcca6c246dae9a369b559c5fdc7b270df1935467e43599.json)
records a clean source tree and declares revision
`a521bc38669bcb820732167543ee475c3b28bd51`. This is retained declared-run provenance,
not an independent attestation of the executing Python or module origins.

The exact joins are:

- [Current check](../data/verification/wa-2026-general/checks/5b85f14e859065ae6b38826bd96f07f563ae630c6f9426caa461f32ff697bfd8.json):
  `mode: live`, scheduled for October 27, `status: unchanged`.
- [Refresh event](../data/verification/wa-2026-general/refreshes/refresh-washington-working-families-party-20261027T085343Z-7183f103bb9c.json):
  `content_changed: false`, empty decision diff, and the same previous/current snapshot.
  The run receipt records `baseline_reviewed: true`.
- [Current observed manifest](../data/verification/wa-2026-general/manifests/capture-washington-working-families-party-20261027T085343Z-d09d18f72c2b.json)
  remains distinct from the reused
  [October 20 factual snapshot](../data/verification/wa-2026-general/extractions/extraction-washington-working-families-party-20261020T085058Z-27e58e61bbe6.json).
- [Exact snapshot approval](../data/verification/wa-2026-general/approvals/extraction-washington-working-families-party-20261020T085058Z-27e58e61bbe6.json):
  **OpenAI Codex /root/review_497_wfp_oct20**, recorded by root under finite
  maintainer delegation, reviewed **2026-10-20T10:07:11.637698Z**.

The [complete baseline review](GENERAL_BASELINE_2026-10-20_WFP.md) and
[factual review record](../data/review/rechecks/wa-2026-general-2026-10-20-wfp.json)
identify the official public POST publication at
`https://workingfamilies.org/wp-admin/admin-ajax.php`, its actual October 20
08:50:58Z check, and all 17 rows: ten existing ballot decisions and seven
outside-inventory exclusions. Its actual source, provenance and context review
times remain distinct. The October 27 unchanged observation reuses that exact
approval; it claims no new personal source read by the original reviewer.
The separately recorded [October 21 scheduled reuse](GENERAL_BASELINE_REUSE_2026-10-21_WFP.md)
remains earlier genuine progress, not a newly performed observation.

The October 27 archive `99fd136888a1ad9aa43ae133c010edbafabe20e3` added 89 immutable
records through normal archive/task reconciliation. Their later delivery does not
rewrite their statuses or grant approval at execution to the other four updated
snapshots. No fixture, artificial dispatch or no-due workflow supplies the WFP result.

## Existing source-specific automated coverage

All sources use the shared durable snapshot/review mechanism. The existing tests
also exercise the distinct producers and failure boundaries:

| Coverage | Existing meaningful cases |
|---|---|
| All six sources and shared review joins | [Source cases](../tests/test_verification_sources.py): complete reviewed mappings and fresh-state committed-record reuse. [Runtime cases](../tests/test_verification_runtime.py): exact approval reuse without restored pages, same-day idempotence and current observation/event integrity. |
| Sage | The all-six source and runtime cases exercise its direct HTML mapping, independent state and changed-input approval loss. |
| TRU | [TRU cases](../tests/test_verification_tru.py): twelve formal facts and exclusions, complete HTML/held-wording/image changes, failed discovery, learned membership and independent recovery. |
| UFCW | [UFCW cases](../tests/test_verification_ufcw.py): article-body change, persisted reuse, rotated and remembered articles, required-article failures and the complete 33-fact mapping. |
| SGN | [Discovery cases](../tests/test_verification_discovery.py): new and known articles, body-only changes, pagination/missing-boundary failures and durable membership across a fresh runner. The [11-fact regression](../tests/test_verification_sources.py) covers the three explicit No measures. |
| WFP | [WFP cases](../tests/test_verification_wfp.py): complete public-response mapping and reuse; unknown or empty expanded output preserves the usable baseline and fails visibly. |

These cases passed in the implementation's full local gate at
`a27a7c3ce9a4844b328b578c9f63458159800cc8`: 2,426 Python tests, 757 JavaScript tests
and eight history checks. Its tree `595fa2dbbdf13565524cfd4ef48753150e75ecbe` is
identical to accepted main `5ee95406ece5d5dfce3ef6c6c3a578becb808938`.
[PR #654](https://github.com/shaug/seattle-election-guide/pull/654) was independently
accepted in general.60 with primary.9 unchanged; the
[original main run 40610522117](https://github.com/shaug/seattle-election-guide/actions/runs/40610522117)
passed all 13 jobs. These are actual implementation-validation and delivery
results, not new adoption-documentation gate results or publisher checks.
Normal current-head validation and protected review still apply to this change.

## Explicit remaining observations and limits

This record consumes retained evidence; it performs no new source check or
factual review and assigns no result to a later archive revision or future slot.
The retained October 27 observations remain:

| Source | Actual retained state and ordinary follow-up |
|---|---|
| TRU | Native 12-fact snapshot, later exactly approved by OpenAI Codex /root/review_608_code_c340 on October 27 at 11:02:37.944401Z. Later independent normal reuse is not established here. Formal-versus-held recommendation qualifications remain. |
| Sage | Native 13-fact snapshot with that same actual later reviewer/time. Later independent normal reuse is not established here; current-list qualifications remain. |
| UFCW | Native 33-fact snapshot with that same actual later reviewer/time. Later independent normal reuse is not established here. Equal duals and held Hackney evidence remain explicit. |
| SGN | The native October 27 eight-fact extraction remains incomplete and unapproved. The complete 11-fact mapping 1.0.2 and reviewed ledger facts are already delivered. A future actual native 11-fact extraction needs its own exact factual approval; neither it nor later reuse is supplied or approved by this adoption record. |
| SEIU 775 | The native October 27 HTTP 403 and eleventh consecutive failure remain failed and escalated, retaining the prior usable 29-fact baseline. The separately reviewed supplied PDF supports 32 canonical decisions / 33 choices but supplies no automated recovery, native approval or scheduled reuse. The collector's access-failure cause remains unknown. |

The exact later TRU, Sage and UFCW approvals are retained in the
[October 27 automatic factual record](../data/review/rechecks/wa-2026-general-2026-10-27-automatic.json).
No unchanged mapped output can turn changed or unreviewed raw inputs into an
approved snapshot. No harmless-page-change normalization or new approval transfer
is introduced.

All six automatic-attempt lanes, all 46 honest panel lanes, current frequencies,
access restrictions, HTTP bounds, failure counters and escalation remain intact.
The [October 24 SEIU adoption-only exception](runbooks/endorsement-source-daily-verification.md#october-24-seiu-775-adoption-only-coverage-decision)
still changes no successful-check status or ordinary retry obligation.
Latest-VERIFIED canonical facts survive failed access under [SOURCE_POLICY.md](../SOURCE_POLICY.md).

The [October 27 dated task #647](https://github.com/shaug/seattle-election-guide/issues/647#issuecomment-6458004214)
closed with 35 bounded manual acknowledgements, four genuine failed-access
dispositions and one WEA administrative member-boundary disposition, not 40 fresh
successful reads. The [October 24 task #616](https://github.com/shaug/seattle-election-guide/issues/616#issuecomment-6454430592)
retains its late/limited closeout. Neither becomes a permanent recovery queue.
The separate October 30 #505 and November 3 #534/#535 obligations are not completed
by adoption. No new evidence store, source lane, automatic factual judgment,
permission, service, UI or cadence is introduced.

## Superseded acceptance history

Scott's October 28 decision supersedes the following original #497 adoption
criteria 3, 5 and 10. They are quoted exactly as historical criteria, not current
requirements to obtain four more successful live demonstrations:

> - [ ] All six named sources have current-election fixture-tested checks. Complete current-election reviewed factual baselines remain required for the other five sources; SEIU 775 follows the October 24 adoption-only coverage decision below. New articles, article-only changes, rotated-away remembered links, missing required articles and parser breaks cannot silently become unchanged success. Existing live-fetch opt-in, public-peer checks, bounds and access restrictions remain enforced.
> - [ ] An independent subsequent run uses a prior durable factual baseline and its real approval without old raw bytes. First/unapproved baselines remain review work; failure preserves the prior usable baseline, provenance and historical failure counters. The October 24 adoption-only coverage decision below satisfies the SEIU 775 coverage-decision alternative; its genuine scheduled failures and unresolved access follow-up remain explicit, without dropping the source silently.
> - [ ] Real due-source native scheduled execution and later independent normal scheduled reuse of the other five sources' complete reviewed factual baselines provide durable revision/run/source/check/task evidence; all six source outcomes, including SEIU 775's failed attempts under the October 24 coverage decision below, remain recorded. Fixtures, dispatches and no-due successful workflows do not substitute. Mark the runbook/`docs/RUNBOOKS.md` adopted and close #497 only after the complete revised evidence and applicable reviewed delivery verification exist.

The runbook's dated October 24 decision retains its original paragraph unchanged.
Its five-source adoption condition and open/proposed status are superseded; its
SEIU exception, actual failures and operating safeguards remain. Historical
reviews, IDs, ciphertext, approvals and releases are not rewritten by this decision.
