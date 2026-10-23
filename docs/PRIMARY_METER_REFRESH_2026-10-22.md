# Primary meter refresh publication sequence

Scope: [#600](https://github.com/shaug/seattle-election-guide/issues/600) prepares the
archive needed by [#598](https://github.com/shaug/seattle-election-guide/issues/598).
This record defines the delivery order; it does not assert publication or deployment.

The primary overview is copied from its immutable release archive. Its individual
race pages are rendered from that archive's verified data using current code.
Updates entries come from the archive's publication view model. Consequently, a
shared meter correction requires new published primary archives and reviewed pins;
editing repository YAML alone cannot change the served primary Updates page.

1. Merge the primary Updates preparation with a fresh current-general publication
   request. Verify the automatic general release and production deployment. The
   primary remains pinned to its existing archive at this stage.
2. From that exact clean merged source, build the next unused primary version
   twice with the existing `release.builder.build_release` API, the primary ledger,
   and the source's commit timestamp. Supply its `software_history` input from
   `release.history.generate_software_history`, bounded by the previous published
   primary source and this exact source. Compare the bundles with `release compare`. Inspect notes,
   validation reports, both screenshots, frozen inputs and retained Updates
   identities. Preflight complete remote tag/release/asset state, publish without
   replacing any existing asset, download the published archive, and verify its
   exact bytes, tag source, release manifest and bundle hash.
3. Deliver the closing-border CSS correction with pins computed from that published
   primary archive, a general Updates entry and fresh general publication request.
   The first new primary entry then covers its race-page correction and the
   overview's already-approved touch behavior from #562. Its copied overview still
   predates the closing-border CSS correction. Include a second primary Updates
   entry in this source for the later overview activation, and keep #598 open.
4. After that merged source's automatic release and production deployment pass,
   build, compare, inspect, publish and download another new immutable primary
   archive from that clean source. It contains the closing-border CSS and the
   second entry. Deliver its actual pins through a separate protected publication
   record PR and fresh general request. Verify both elections, both served Updates
   pages, the actual meter geometry and the automatic release and deployment before
   closing #598.

Each candidate runs `make check`, release reproducibility, exact-source staging,
the live `make check-updates` comparison, fresh repository review and protected
checks. Each changed election must retain its old served Updates identities and
add the entry appropriate to the stage that actually changes its pages. Confirm
the entries' Pacific dates against actual publication before publishing an archive.
Do not reserve later versions or invent pins in advance.

The replacement primary overview activates the existing #562 touch discovery
behavior because its previous archive predates that merged change. Record and
verify that activation; it adds no new interaction design. Preserve all endorsement,
inventory, registry, scoring and certified-result inputs. Old archives, release
assets and private evidence remain unchanged. No frozen view-model overlay,
feature-branch publication, direct local production upload or Updates exception is
part of this sequence. Current-general publication continues through the automatic
merged-source workflow.
