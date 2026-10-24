# Complete meter rollback preview

Scope: [#598](https://github.com/shaug/seattle-election-guide/issues/598).

Scott requested a deployed preview for inspection on October 24. Production and
PR #618 merge are held pending that inspection. The approved appearance remains
the exact two CSS files at `bea5e4edc5c50c985932b8ae5e123a39a0b51449`;
general 929 decisions, primary 538 decisions and current interactions stay intact.
The preview must include a newly built primary overview, not just current race
CSS or an older published overview.

## Approach

The existing PR workflow builds general and downloads the published primary.
That cannot preview its rebuilt overview. Publishing a new archive from an
unmerged preview source conflicts with the merged-source archive rule. Reusing
primary.5 would show the old appearance but would not be a rebuilt-head preview.

Use existing release-build and hosting-stage/verify APIs for two local bundles.
An additional explicit opt-in, on an open same-repository **draft** PR with the
existing `deploy preview` label, builds primary from the exact PR head. Give it
`preview-pr-<PR>-primary-<fullHEAD>` as an unmistakably unpublished identity.
Generate only an ignored `dist/preview-site.yaml` with its actual source,
manifest and whole-bundle hashes. Supply both local bundles to normal staging
and independent verification. The tracked primary.6 declaration stays exact.

Normal preview behavior remains unchanged without the additional opt-in.
Keep the original declared-release check before composition, the existing
PR-only Pages branch, credentials, noindex behavior and teardown. No public
archive/tag, source/schema, production workflow, deployment switch or access
change is authorized. Do not add a new staging framework or dependency.

## Acceptance

- Explicit complete-preview opt-in is permitted only for an open same-repo
  draft PR. Current general-only previews keep their existing behavior.
- Both bundles authenticate to the exact clean candidate head. Primary's
  ephemeral identity and all hashes come from actual build output, never from
  published primary.6 or an assumed numeric release version.
- Temporary manifest generation leaves tracked declarations and every old
  primary archive untouched. Normal staging and verification reject wrong
  identities, data, pins and source hashes before preview upload.
- Transfer only the exact two approved CSS files and focused browser-test
  hunks. Preserve later diagnostics, all other tests, data, scoring and behavior.
- Run focused regressions, complete `make check`, required fresh review and
  exact-head dual-bundle verification before opting into deployment. Inspect
  actual served general and primary overview/race surfaces on desktop/mobile.
- Preserve every earlier Updates entry and add truthful preview/preparation
  entries for affected elections before building their local bundles. They must
  not assert that production restoration has occurred. Run the live Updates
  comparison on the complete staged preview; production still resolves primary.6.
- Return the working preview URL, exact source, both bundle identities and
  honest limits. The draft is never a production candidate; ordinary production
  publication gates and the protected A/archive/B/archive/C sequence stay in
  force. #598 remains open and production remains held.
