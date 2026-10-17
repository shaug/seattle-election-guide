# Updates backfill publication — October 16, 2026

Scope: [#556](https://github.com/shaug/seattle-election-guide/issues/556). The maintainer
authorized the missing history for both elections, corrected dates, and complete verification
from first publication. The [history audit](UPDATES_HISTORY_AUDIT_2026-10-16.md) and its linked
283-commit inventory define the bounded coverage.

Publish `2026-general.10` and `2026-primary.4` from the same full merged mainline
`release_candidate_sha`. The general release contains nine dated entries; the primary release
contains 31: 30 historical entries and the newly activated sparse-race label change in customized
overview views. Both retain “We get it right, eventually.” A new primary artifact is necessary:
the served `.3` view model has no Updates entries. Do not modify `.3` or overlay new log content
onto its hash-pinned artifact.

The default primary overview's visible text is unchanged apart from Updates navigation and build
provenance. Its old embedded client module predates #533, however: rebuilding activates the
measured-leader label for sparse personalized selections. Record that activation on the new
release's actual Pacific publication date, independently of the frozen 39-entry historical audit.
The new primary entry is dated October 16; verify this still matches publication before upload.

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

After both tags exist, use one focused, non-closing publication PR for the generated changelog
and the historical declaration of the downloaded `.4` artifact's exact commit, release-manifest
hash and whole-bundle hash. This is the post-tag release-record change described in RELEASE.md;
keep it limited to these publication records and their corresponding tests. Retain the panel
and registry identities.
Do not invent pin values before the artifact exists. CI continues using the existing `.3`
declaration until the reviewed replacement is published and pinned.

The final production candidate must descend from the release candidate. Verify general lineage
against the downloaded `.10` ZIP, stage and independently verify both elections, and use the
existing automatic deployment gate. Verify both live Updates pages, both sets of permanent
Corrections redirects, the exact deployed revision, and two strict production probes. Preserve
release identities, CI artifacts, deployment evidence, lineage and probes in #556. Preparation
of this record does not itself assert publication or production success.

## Published archive identities

Both immutable releases were published from `c5a5252202d0f78bcec5e54f9f6d0dfe0841d481`.

| Release | ZIP SHA-256 | Bytes |
| --- | --- | ---: |
| `2026-general.10` | `466efd641d2f190f5030e6d7e8b29d58bd4dff0d96e521af51dd0c3b950b161e` | 684423 |
| `2026-primary.4` | `06e65dce9343688e89f57d1320cdbeaf6852206c42ab2c41c8c69b1ed6b533e2` | 535156 |

The primary `.4` pin is computed from its downloaded canonical archive, with release-manifest
SHA-256 `723c6b16bd74e212850f95a4454b28253abc630b71ffd42ed0ac6a1345a02cbc` and bundle-tree SHA-256 `7ec162d04f795900bbd94172d0d555fd2e8a292267156bc0576882dc11ae14c6`.
Its publication date in America/Los_Angeles is October 16, matching the new display-activation
entry. These release identities do not themselves assert the later website deployment succeeded.
