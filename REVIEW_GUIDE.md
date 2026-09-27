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
