# Updates backfill publication — October 16, 2026

Scope: [#556](https://github.com/shaug/seattle-election-guide/issues/556). The maintainer
authorized the missing history for both elections, corrected dates, and complete verification
from first publication. The [history audit](UPDATES_HISTORY_AUDIT_2026-10-16.md) and its linked
283-commit inventory define the bounded coverage.

Publish `2026-general.10` and `2026-primary.4` from the same full merged mainline
`release_candidate_sha`. The general release contains nine dated entries; the primary release
contains 30. Both retain “We get it right, eventually.” A new primary artifact is necessary:
the served `.3` view model has no Updates entries. Do not modify `.3` or overlay new log content
onto its hash-pinned artifact.

## Reviewed input bindings

The [exact file bindings](audits/updates-2026-10-16/input-bindings.json) compare all endorsement,
registry, inventory, scoring and primary-result inputs byte for byte with published
`2026-general.9` and `2026-primary.3`. The backfill changes no endorsement interpretation or
result. Existing human approvals remain applicable to the identical inputs.

General ledger: `1286c04ba2b8c38081f1f77d0d7789bdc95402bf52b955c7d4965625240f9b6e`.
General canonical dataset: `da873f6755f0b83a82e1a5c5a00acbc3ed576dd52035aed65e76d5a6e241cd7c`.
General registry: `b768ab12d366d345a7886c8dc3a61438ff2cc33a52042b49cf5eb7c505e7dd0f`.
The primary's complete input hashes, including certified results, are in the linked bindings.

The earlier general `.9` archive remains at
`da307d6f4c695471ec5a025a4226824de5ffbbc5`, with SHA-256
`9507d1cf10d9c43e38010e2011c934f05e181a934bceb681b28f04160fe041b0`.
The earlier primary `.3` remains at `6e93dafe45ac45f343c5ea3d123f53e24725d15e`,
with archive SHA-256 `decf71bffc914a231fc918dcb3fd188d61b24e37f59539935e7452eafa855516`
and bundle-tree SHA-256 `5418b15370a6ed0f8eb0f4e02d9c9a02faf9f6f5043f9c3e39f3abe120b5ad9d`.

## Primary artifact and production handoff

Follow [the release procedure](RELEASE.md) for the general build, immutable publication,
generated changelog, lineage, exact-candidate staging and production probes. Additionally,
build the primary twice from the same clean merged candidate:

```bash
for build in a b; do
  uv run election-guide release build \
    data/releases/wa-2026-primary/source-decisions.yaml \
    --release-version 2026-primary.4 \
    --generated-at "$(git show -s --format=%cI HEAD)" \
    --git-commit "$release_candidate_sha" \
    --output-dir "dist/primary-backfill-$build"
done
uv run election-guide release compare \
  dist/primary-backfill-a/bundle dist/primary-backfill-b/bundle
```

Inspect each guide's desktop/mobile screenshots, validation reports, Updates entries and
release notes. Preflight both remote tags, release records and asset lists before any mutation.
Publish the primary with the versioned ZIP and its bundled notes using the same non-clobbering
restart matrix as the general. Download both canonical assets again, compare exact bytes,
record their sizes/digests, and verify both tags resolve to `release_candidate_sha`.

After both tags exist, regenerate the changelog in its own focused non-closing PR. Then update
the historical declaration to the downloaded `.4` artifact's exact commit, release-manifest
hash and whole-bundle hash in a focused pin change. Retain the panel and registry identities.
Do not invent pin values before the artifact exists. CI continues using the existing `.3`
declaration until the reviewed replacement is published and pinned.

The final production candidate must descend from the release candidate. Verify general lineage
against the downloaded `.10` ZIP, stage and independently verify both elections, and use the
existing automatic deployment gate. Verify both live Updates pages, both sets of permanent
Corrections redirects, the exact deployed revision, and two strict production probes. Preserve
release identities, CI artifacts, deployment evidence, lineage and probes in #556. Preparation
of this record does not itself assert publication or production success.
