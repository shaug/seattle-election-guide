# Results badge archive activation

Scope: the approved status-only badge and second-line timestamp follow-up to
[#696](https://github.com/shaug/seattle-election-guide/issues/696).
[PR #703](https://github.com/shaug/seattle-election-guide/pull/703) delivered the shared
rendering and conservative Updates comparison changes in merged source
`ccce7f3f0285e39bb541d7e2984e36b8e92e1595`. General `2026-general.84` passed
all thirteen original main jobs and two independent strict production probes.

## Verified immutable Primary archive

The Primary overview is copied from its immutable archive; current code renders
its race pages. Completing the Certified overview badges therefore requires a
new archive and protected pin activation, rather than rewriting Primary9.
Primary `2026-primary.11` was built twice from that clean merged source using
its commit timestamp and software history from the actual Primary9 source.
The deterministic comparison, data/rendering reports, artifact hashes and ZIP CRC
passed. Both desktop and mobile images were inspected.

All 538 decisions, five CSV exports, certified results, source membership and
nonmetadata/non-Updates view-model fields match Primary9. The newly explicit
`precinct_ballot` field is null. The Updates value is exactly the existing current
authored schema-1.1 log; Primary9 and its original schema-1.0 log remain immutable.
Each of the 32 overview result blocks says only Certified, with
Certified on Aug 18, 2026 on the second provenance line. No outcome-chip or
endorsement treatment changes are included.

The [published Primary11 archive](https://github.com/shaug/seattle-election-guide/releases/tag/2026-primary.11)
was downloaded and verified byte-for-byte against the accepted candidate.

- Release ID: `437820660`; asset ID: `721836246`.
- Source: `ccce7f3f0285e39bb541d7e2984e36b8e92e1595`.
- ZIP SHA-256: `d684a16ac1212fa65433a27a8547f208ac76fad2c97e1863287d71f215a24877`.
- Bundle SHA-256: `e61152cad9f195a68c420cf98c35f55d7479c4fd15ba3aee4ac48da7d775c81a`.
- Release-manifest SHA-256: `d7590c753deed52ea9e8439c7cacf8c02318bcf31e28bf0c005227a0ee3d4894`.

## Protected activation

This change selects only the verified downloaded Primary11 pins and prepares a
fresh current-General release request against actual main and published releases.
Before merge, run the complete local gate, reproducibility, exact-source staging,
authenticated Updates comparison, independent review and protected CI. After the
automatic main deployment, verify the exact deployed source with two complete
strict production probes and confirm the archived overview identity. Earlier
archives remain unchanged. No new source access or current results count is
claimed by this presentation-only release.
