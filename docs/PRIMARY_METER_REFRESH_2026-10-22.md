# Primary meter refresh publication sequence

Scope: [#600](https://github.com/shaug/seattle-election-guide/issues/600) prepares the
archive needed by [#598](https://github.com/shaug/seattle-election-guide/issues/598).
This record tracks the delivery order and completed acceptance. General release
`2026-general.28` from `bea5e4edc5c50c985932b8ae5e123a39a0b51449` passed automatic
publication and production acceptance. The first replacement primary archive,
`2026-primary.5`, was built twice from that same clean source, compared, inspected,
published, downloaded and verified. Its release and asset IDs are `421416319` and
`667827096`; the ZIP SHA-256 is
`ebcfa1b8fb58f3b4e0cc566ecd4b304f1ac9276a8cec1a104ee3ca27eccc1cb4`,
the bundle SHA-256 is
`ef881727c52374610e383fbad42271bdaf2bef4abdab84b592c03744a4d5e6c3`,
and the release-manifest SHA-256 is
`cd7e5e8ed414d902f5892b4cf199991290ab5b096a0c0c1bee0daad26c7410c9`.
The published archive was verified; production still serves primary `.4` until
the reviewed pin and border change below is merged and deployed.

The primary overview is copied from its immutable release archive. Its individual
race pages are rendered from that archive's verified data using current code.
Updates entries come from the archive's publication view model. Consequently, a
shared meter correction requires new published primary archives and reviewed pins;
editing repository YAML alone cannot change the served primary Updates page.

1. Completed: merge the primary Updates preparation with a fresh current-general publication
   request. Verify the automatic general release and production deployment. The
   primary remains pinned to its existing archive at this stage.
2. Completed: from that exact clean merged source, build the next unused primary version
   twice with the existing `release.builder.build_release` API, the primary ledger,
   and the source's commit timestamp. Supply its `software_history` input from
   `release.history.generate_software_history`, bounded by the previous published
   primary source and this exact source. Compare the bundles with `release compare`. Inspect notes,
   validation reports, both screenshots, frozen inputs and retained Updates
   identities. Preflight complete remote tag/release/asset state, publish without
   replacing any existing asset, download the published archive, and verify its
   exact bytes, tag source, release manifest and bundle hash.
3. Pending: deliver the closing-border CSS correction with pins from the published
   primary archive, a general Updates entry and fresh general publication request.
   The first new primary entry then covers its race-page correction and the
   overview's already-approved touch behavior from #562. Its copied overview still
   predates the closing-border CSS correction. Include a second primary Updates
   entry in this source for the later overview activation, and keep #598 open.
4. Pending: after that merged source's automatic release and production deployment pass,
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

The source file for primary Updates carries a second October 22 entry for the
later overview activation. Primary `.5` freezes only the first new entry, so the
second entry is not served with this pin. Confirm or correct its Pacific date
against the actual later archive publication before that archive is published.
The general and primary race-page border change and primary `.5` activation
remain pending here; the later overview archive and pin record still follow them.
Keep #598 open until both stages and the final production checks pass.

The replacement primary overview activates the existing #562 touch discovery
behavior because its previous archive predates that merged change. Record and
verify that activation; it adds no new interaction design. Preserve all endorsement,
inventory, registry, scoring and certified-result inputs. Old archives, release
assets and private evidence remain unchanged. No frozen view-model overlay,
feature-branch publication, direct local production upload or Updates exception is
part of this sequence. Current-general publication continues through the automatic
merged-source workflow.
