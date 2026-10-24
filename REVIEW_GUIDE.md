# Review Guide

This guide governs endorsement-data review. Front-end code standards live in
`docs/FRONTEND.md`; UI/UX rules live in `docs/DESIGN.md`.

No endorsement becomes publishable solely because an extractor produced it.

For each claim, a reviewer must verify:

1. The evidence belongs to the registered organization and target election.
2. The wording is an endorsement, not discussion, praise, polling, or reporting.
3. The race matches by jurisdiction, office, district, and position where applicable.
4. Every choice matches a candidate or ballot option in that race.
5. Multi-candidate, ranked, acceptable-choice, no-endorsement, and skip semantics are preserved.
6. The evidence locator and source link allow the decision to be reconstructed.

An official, organization-maintained candidate endorsement index covering a date range that
includes the target election may support a general-election claim when it is still live after
the primary and is not labeled primary-only. Review each listed candidate separately against
the general ballot and check for a newer withdrawal, replacement, or election-specific list.
Exclude candidates absent from that ballot without discarding valid listed candidates. Describe
the evidence as a current-cycle endorsement, not as a separate general-election slate. A
primary-only publication still needs an explicit official carry-forward statement before its
choices can be used for the general election; ballot advancement alone is not that statement.

Ambiguous matches remain unresolved. Overrides are data records containing the prior value, new
value, reason, evidence, author, and timestamp; they are never hidden source-code branches.

High-severity unresolved items include uncertain endorsement semantics, a race or candidate
match with multiple plausible results, missing evidence for a displayed claim, or disagreement
between canonical output and the rendered guide. These block the standard publication build.

Manual transcriptions must use the evidence adapter rather than ad hoc notes. A completed manual
record identifies the original capture, evidence type and locator, transcriber, verifier, review
timestamp, status, and review note. Pending records may be retained for work tracking but cannot
be treated as verified endorsement claims.

## Recurring factual baseline review (#497)

Endorsement facts, official URL, actual check timestamp, actual reviewer and actual review timestamp
are sufficient durable evidence for recurring verification. Review every first, changed or
unapproved factual baseline against the official current publication and the complete supported
mappings, including changed wording that produced an empty semantic diff. Preserve explicit
source-access, article discovery, completeness and interpretation limitations. Removal remains a
review lead; detection grants no ledger or release approval.

Observed-only manifests (`availability: observed`) retain successful fetch metadata, SHA-256 and
byte length without a storage reference. They document metadata/facts provenance, not retained
original bytes. Hashes cannot prove publisher authorship; full-page reconstruction is not required.
Normal baseline approval, validation, reconciliation and reuse need no evidence key or restored
historical page. The separate manual-entry adapter above still requires its retained, verified
artifact and dual-review fields; an observed-only manifest cannot be used as that artifact.

Check time and review time are separate. An unchanged automated check references the exact prior
factual approval, its actual reviewer and review timestamp. It does not claim that reviewer
personally re-read the source on the new check date. Name a human or an explicitly delegated
reviewer truthfully under existing maintainer authority; never substitute the maintainer's name
for delegated work. The commands' legacy `human` mode does not change the actual actor.

Preserve historical IDs, ciphertext, approvals, failures and releases unchanged. Valid existing
approvals apply only to the precise facts/snapshot reviewed. Migration supplies no new approval,
fresh source read, backdated check, failure reset or authority for unattended interpretation.
Fixtures cannot receive live baseline approval. Keep #497 and its runbook proposed until actual
scheduled execution and later independent normal scheduled reuse have the required evidence.

## Recorded maintainer-approved measure interpretation

The October 12, 2026 general update records one explicit exception: Tech 4 Taxes’
official legislative agenda supports the millionaire income tax, and the maintainer
approved mapping that position to No on Initiative IP26-645 after reviewing the
distinction between policy support and explicit ballot wording. The official
voters’ guide supplies the repeal mapping. Preserve the PRO source wording and
identify No as a human-approved interpretation, with prior value, new value,
reason, author, timestamp, and both evidence links in the approval record.
This recorded case does not establish automatic policy-to-ballot inference.
See [the reviewed treatment](docs/GENERAL_ADDITIONS_2026-10-12.md).
