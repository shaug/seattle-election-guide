# Automatic publication of verified releases

Status: proposed for written review; no workflow or production policy has changed.

Scope: [#550](https://github.com/shaug/seattle-election-guide/issues/550).
Baseline: merged main `165b21bffa5bbdce0e1f05226b2dee20ba554a8e`.

## Intended outcome

The maintainer selected **automatic publication and deployment after merge**.
Reviewing source decisions and the rendered candidate remains human work. Once a
reviewed release PR merges, automation completes validation, archive publication,
deployment, production confirmation, and evidence collection. There is no final
Publish action and no routine publication-switch toggle.

Success means the next reviewed release can go live without the manual steps
needed for `.7` and `.8`: publishing an archive by hand, preparing a post-tag
changelog PR, selecting another main revision, rebuilding that revision, and
assembling deployment evidence. A real conflicting release or failed contract
continues to stop publication.

## Existing causes and selected approach

CI already validates inputs, builds twice, stages the complete two-election site,
and verifies its assets. Deployment requires a published release, but no job
publishes one. The runbook additionally requires a post-tag changelog commit and
a different production revision. Version literals occur in multiple commands,
workflows, examples, and tests. The production checker makes one immediate pass;
on October 16 it saw `.6` just after the successful `.8` upload, then passed once
the new deployment propagated.

A single Publish action wrapping the existing runbook would reduce commands but
retain the second commit and its coordination. Automating a changelog PR would
retain that dependency and introduce another bot-managed merge. The selected
approach promotes artifacts from one merged revision through one workflow and
generates release notes without another repository commit.

## Release declaration and preparation

`config/hosting/site.yaml` remains the authority for the selected current release
version and archive composition. Commands and workflows obtain the current
version, bundle identity, and archive name through a shared validated resolver;
they do not carry election-specific version literals. Existing explicit
historical identities and pins remain unchanged.

The current election declaration gains a publication request containing the
owning issue number and SHA-256 bindings for the source-decision ledger,
canonical dataset, and source registry, plus the full previous-release revision
used as the software-history boundary. These are file-byte hashes; the existing
validated panel and complete-registry identities remain separate checks. It is
a claim about the files included in the reviewed PR, not a new endorsement or
baseline approval. The schema
accepts existing manifests without this request for reading and historical
verification; a new automatic release requires it. Historical declarations do
not gain reconstructed approval metadata.

A supported preparation command updates the current release version, derived
bundle identity, issue reference, history boundary, and input bindings together. It selects the
next unused election-scoped version relative to the current main declaration
and existing tags/releases. Repeating preparation for the same unpublished
proposal refreshes its bindings without creating another version. A version
claimed by a different published release is never reused. Concurrent PRs that
claim the same next version must refresh against main before merge.

PR validation rejects changed release inputs with unchanged or stale bindings.
It also requires a new release declaration for changes to runtime source,
rendering/templates/assets, dependency locks, or publication/site configuration
that could change the public artifact. Start with conservative, documented
coverage of these paths rather than guessing whether a code change is harmless.
Documentation and test-only commits run normal CI and do not request another
release or redeploy an existing version from a different revision.

Source interpretation, approved allocations, unresolved-review checks, panel
identity, and all current validation rules remain authoritative. The publication
request never marks the six outstanding automatic baselines reviewed or closes
the separate editorial verification issues.

## One candidate through the complete workflow

On a release PR, read-only CI validates the request and provides the generated
candidate, validation reports, and desktop/mobile images for review. Publication
and production credentials remain unavailable to pull-request jobs.

On its merge to main:

1. Capture the full merged revision and verify that the release request came
   through a merged PR. Recheck the reviewed input bindings against that exact
   checkout. All required CI lanes must pass on the merged revision.
2. Run the existing two-build reproducibility gate with the commit-derived
   timestamp. Select one exact canonical ZIP and stage the complete site from
   its verified bundle plus the published, hash-pinned primary. Independently
   verify the staged site against the same full revision.
3. Preserve a candidate record binding the revision, release declaration, input
   hashes, selected ZIP digest/size, complete deployment-manifest digest, and
   producing CI run and artifact IDs. Artifact names include their producing
   run attempt; consumers use the captured IDs rather than a latest-by-name
   search. This also prevents name collisions on workflow reruns.
4. A publication job depending on the full check gate publishes and verifies
   that candidate's archive. A deployment job depends on successful publication
   and the complete site verification, and uploads that verified site artifact.
5. Wait for the expected production identity, run strict confirmation twice,
   and preserve the operational receipt and full evidence.

The release tag, published current bundle, staged current bundle, upload commit,
and expected production commit identify the same merged revision. There is no
requirement for a later production commit. Existing lineage verification remains
available for historical two-revision releases; its ancestry and normalization
rules are not weakened to accommodate this flow. The new path proves identical
candidate identity and artifact integrity directly.

Visual review moves before merge. After merge the reproducibility, semantic
rendering, and integrity gates still run; automation does not invent a human
inspection of the final merged screenshots. This is an explicit runbook policy
change, not a claim that the current manual inspection step already disappeared.

## Software change history

Generate the new software-change section from the previous release boundary in
the reviewed request to the selected candidate, using the declared version and
commit timestamp. Include it in the existing, hashed `RELEASE_NOTES.md`; no new
required artifact is imposed on legacy bundle schemas. The same inputs must
generate the same section before and after the tag
exists; a tag created during the workflow cannot change its input range.

`CHANGELOG.md` retains its existing historical entries and becomes an index to
the immutable release notes for subsequent releases. It no longer requires a
commit after every new tag. Amend `CONTRIBUTING.md`, the runbooks, the generator
contract, and the affected checks together. Replace the tag-sensitive comparison
with deterministic release-note generation and artifact-integrity checks; retain
coverage of conventional history, election-scoped versions, and legacy history.

## Publication state and restart behavior

The publisher inspects the tag, release metadata, and complete asset list before
mutation. It never moves a tag, deletes/replaces an asset, or uses overwrite.

For a new release, create an automation-owned draft, upload the single canonical
ZIP, download and verify its bytes and metadata, then publish it. The draft is
not eligible for deployment. An incomplete draft may be resumed only when its
ownership, version, target, notes, and existing assets match this request; an
unrecognized draft or conflicting state fails with an actionable receipt.

For an existing published release, download its original canonical ZIP, validate
its full tag/source identity, input bindings, manifest and file set, and compare
its deterministic artifacts with the same-revision verified build. Retain the
original asset ID, size, digest, and screenshot bytes. A rebuilt ZIP can differ
because the two declared screenshots are excluded from cross-build comparison;
that is not permission to replace the published ZIP or adopt a new digest.

An existing publication receipt must agree with the release asset identity and
digest. A missing receipt may be reconstructed only by verifying the existing
archive against the exact reviewed request and reproducible build. Conflicting
receipts or deterministic content fail. Recovery then stages from the downloaded
canonical bundle at its original revision, preserving the original archive.

Expired CI artifacts are rebuilt only at the captured source revision, with fresh
reproducibility and site verification. Published archives remain the canonical
selection. Recovery never substitutes the current head of main for that revision.

## Concurrent releases and promotion

Use workflow-level serialization for the complete mainline pipeline, so the
publication and deployment jobs share one critical section. PR CI remains
parallel. This deliberately also serializes mainline checks rather than adding
a separate cross-job lock coordinator. Use `queue: max` and
`cancel-in-progress: false`: a later documentation-only run must not cancel the
queued run that introduced an unpublished release. GitHub currently supports
100 pending runs with this setting; queue exhaustion is an explicit delivery
failure, not a reason to lose a request silently. See the
[concurrency contract](https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-syntax#concurrency).

GitHub concurrency is a lock, not proof that candidates finish in release order.
Before upload, while holding that lock, compare the candidate with main's
selected release and the latest successful production receipt.

A candidate superseded by a newer release declaration may retain its published
audit archive but skips deployment. It cannot replace a newer deployed release.
Later documentation commits do not invalidate the source revision of an
otherwise current release declaration. New reviewed data must carry a new
version, so it cannot silently enter an existing release during this check. A
new merge can arrive after the final stale-candidate check: it becomes the next
queued release, while the already admitted deployment may finish. The guarantee
is that an older deployment never replaces a newer deployed release, not that
main cannot advance while an admitted upload is in flight.

A failure after the upload does not automatically roll back, change the
publication switch, or select another candidate. It preserves what was observed.
Distinguish `superseded`, `deployment_paused`, `published`, `verified`, and
`failed` in receipts and job summaries so intentional skips are not mistaken
for a release requiring operator repair.

## Production confirmation and evidence

Add a bounded wait mode around the existing read-only checker: a 120-second
deadline, at most one attempt per five seconds, per-request timeouts bounded by
the remaining deadline, and two consecutive successful complete strict probes.
Every attempt uses the same canonical origin, trusted manifest, full expected
revision, and release identity. Preserve failed observations as well as the two
successful reports. Persistent wrong identities, incomplete manifests, incorrect
routes/redirects, and transport errors still fail at the deadline.

Waiting never uploads again. The read-only verification/evidence entry point
can be rerun separately against the existing deployment without invoking a new
build or upload; it does not claim to replace the full CI gate for a new candidate.

Write a durable publication receipt to the request's owning GitHub issue after
archive verification and before deployment. After confirmation, append a durable
deployment receipt and both full probe reports. Identify comments by release,
revision, producing run/attempt and phase; resume matching evidence without
rewriting human comments. Number/hash bounded report parts if a report exceeds
the comment-size limit. Short-lived Actions artifacts remain convenient copies,
not the sole retained evidence.

Receipts include release/tag/source identities, all reviewed input hashes, asset
ID/name/size/digest, candidate/site artifact IDs and digests, production deployment
and upload identity, deployment time, and probe observations. A failure to retain
required evidence leaves finalization incomplete and retryable. Posting receipts
does not close the issue or attest to editorial work outside this release.

## Permissions, switch, and compatibility

Keep publication and deployment as explicitly dependent jobs in the same mainline
workflow. Do not depend on a new workflow being triggered by a release created
with `GITHUB_TOKEN`. Grant release writes only to the mainline publisher; grant
issue writes only to evidence writers. Keep Cloudflare credentials in the
production upload job and retain the main-only environment policy.

`CLOUDFLARE_PAGES_ENABLED` continues to control Pages uploads. A disabled switch
may leave an archive published and deployment intentionally paused; it does not
delete releases or supply an alternate deployment path. Re-enabling it resumes
the currently selected candidate through the same checks.

Existing `.7`, `.8`, primary bundles, published schemas, evidence, approvals, and
pins remain readable and unchanged. No screenshot exclusion, manifest allowlist,
source-panel rule, or existing enforcement ratchet grows.

## Acceptance and rollout

Use fixture-based GitHub/Pages responses and a controlled clock to verify:

- declaration resolution, preparation idempotency, collisions, stale bindings,
  and release-affecting changes without a new declaration;
- creation, matching partial-draft recovery, already-published recovery,
  changed screenshot bytes with unchanged deterministic artifacts, missing
  receipts, and conflicting tags/assets/receipts;
- exact run/attempt/artifact binding, absent/expired artifacts, failed CI lanes,
  and the prohibition on publication from PRs or non-main refs;
- concurrent declarations, out-of-order completion, newer production, and
  documentation-only main advances;
- propagation from the previous release, two successful strict confirmations,
  a hard deadline and bounded request timeouts, persistent wrong routes or SHA,
  and finalization without another upload;
- retained receipt/report contents, bounded comment parts, and evidence retry.

Run `make check` and the existing reproducibility and staged-site verification
gates. Update the runbook drift tests to the new supported entry points, keeping
their enforcement rather than editing around them. Normal tests make no live
network calls.

The activation PR prepares the next fresh release version with the same
approved 880-decision inputs unless a separately reviewed data change is included.
Its merge is the rollout action. Retire the legacy manual upload sequence and
enumerate superseded pending runs before enabling the new path. Verify the
complete automatic path and both live probes, then record any unmet acceptance.
Design review alone neither publishes that release nor changes the current
production site.

Implementation planning starts after review of this written design. No source
collection, endorsement interpretation, baseline approval, automatic rollback,
recurring production monitor, or unrelated UI change is part of #550.
