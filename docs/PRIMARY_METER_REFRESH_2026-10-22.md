# Primary meter refresh publication sequence

Scope: [#600](https://github.com/shaug/seattle-election-guide/issues/600) prepared the
immutable archives required by [#598](https://github.com/shaug/seattle-election-guide/issues/598).
This record tracks completed publication and the remaining production acceptance.

## Accepted first delivery stage

General `2026-general.28` from `bea5e4edc5c50c985932b8ae5e123a39a0b51449`
passed automatic publication and production acceptance. Primary `2026-primary.5`
was built twice from that clean source, compared, inspected, published, downloaded
and verified. Its release and asset IDs are `421416319` and `667827096`.

[PR #605](https://github.com/shaug/seattle-election-guide/pull/605) then delivered
the closing-border correction and activated primary `.5`. Its merged source is
`c27e432d9bc477289d54ee9136746845a92696d0`. Automatic general
[`2026-general.29`](https://github.com/shaug/seattle-election-guide/releases/tag/2026-general.29)
and production passed acceptance: all thirteen jobs succeeded on attempt one,
both automatic and independent strict probes passed twice, and all 88 affected
HTML/Updates responses reconciled to the uploaded artifact. The 923 general
decisions and five CSV exports are unchanged. The actual delegated page reviewer
was `/root/audit_605_production_pages`.

The primary overview is copied from its immutable archive. Individual race pages
are rendered from that archive's verified data using current code, and Updates
entries come from its frozen publication view model. Consequently, primary `.5`
activated the corrected race pages and existing #562 touch behavior, while its
copied overview still predated the closing-border correction.

## Published primary overview replacement

After general `.29` passed acceptance, primary `2026-primary.6` was built twice
from that exact clean merged source, using its commit timestamp and software
history from the actual primary `.5` source through that merged source. The two
complete ZIPs are byte-identical. Notes, seven data checks, six rendering checks
and both screenshots were inspected. All 538 primary decisions, five CSV exports,
certified results, source membership and every nonmetadata/non-Updates view-model
field remain identical to primary `.5`. Its 32 earlier Updates entries are retained;
the added October 23 entry covers this archived-overview correction.

The [published primary `.6` archive](https://github.com/shaug/seattle-election-guide/releases/tag/2026-primary.6)
was downloaded and verified. Release ID: `421849109`; asset ID: `669144772`;
source: `c27e432d9bc477289d54ee9136746845a92696d0`.

- ZIP SHA-256: `6d825f5a88ac06bbb5a15f4ed771e1cc5ed24e7d7e52a85ee216cf5d5e1ceeb8`
- Bundle SHA-256: `daa492dc72d526de6178281292ef660a8b3885a7194cbcd8e7d51fb9b450ea07`
- Release-manifest SHA-256: `701c956310cad5e5374a291beb2cd54389a5f15087fc40a40c3a6707345c594d`

All 33 prior release, tag and asset identities were preserved. The October 23
source entry matches its actual Pacific publication date. The two historic primary
source-access/discovery limitations remain explicit in the archived notes.

## Remaining protected activation

This separate publication record selects the actual downloaded primary `.6` pins
and prepares the fresh automatic general `2026-general.30` request against accepted
source `c27e432d9bc477289d54ee9136746845a92696d0`. Production continues to serve
primary `.5` until this record merges and its automatic deployment passes.

Before merging, run `make check`, release reproducibility, exact-source staging,
the live `make check-updates` comparison, fresh repository review and protected
checks. Inspect the exact CI candidate notes, reports and desktop/mobile images.
The new primary archive supplies its own overview Updates entry; every older
served identity must remain present.

After merge, independently verify the automatic current-general release, its
producer and durable receipts, both elections and served Updates histories, the
actual meter geometry and strict production probes. Keep #598 open until those
checks pass. Preserve every earlier immutable archive and private evidence;
current-general publication continues through the automatic merged-source workflow.
