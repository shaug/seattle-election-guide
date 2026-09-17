# Stable Panel Identity and Mutable Registry Audit Hashes

## Context

The source registry currently has one hash with two incompatible jobs.
`source_registry_hash` records every validated registry field, which is correct
for release audit and reproducibility. `build_panel_snapshot` also publishes
that hash as `panel_hash`, which makes mutable discovery work look like a
change to the personalized-link contract. A routine recheck can therefore
make an unchanged frozen panel conflict with its append-only published
snapshot.

Issue #436 separates those jobs without rewriting any snapshot that has
already shipped.

## Design

### Two hashes with different meanings

`panel_hash` identifies the transport-facing source-selection contract. It is
stable while that contract is stable and changes when any field that can
change source selection, migration, eligibility, or visible attribution
changes.

`source_registry_hash` remains the SHA-256 of the complete validated registry.
It changes when any registry input changes, including discovery evidence,
URLs, notes, or timestamps, and remains the release audit and reproducibility
hash.

The release and publication models carry both values under those explicit
names. User-facing personalized links and panel-version checks use
`panel_hash`. Release manifests, release status, deployment comparison, and
audit records use `source_registry_hash` when they need to prove the complete
input. Existing `source_panel_hash` fields keep their serialized name for
compatibility but carry only the stable panel hash; new
`source_registry_hash` fields carry the complete-input hash.

### Exact panel-identity projection

A dedicated strict model defines the canonical panel-identity projection. The
hash covers these fields, in their validated transport order:

- panel identity schema version;
- categories: `id`, `code`, `label`, `selectable`, `panel_role`, and current
  selectable member source codes;
- sources: `id`, `code`, `name`, `panel_role`, derived `selectable`,
  `reporting_category_id`, and `selection_category_ids`;
- source eligibility: `kind` and `jurisdiction_ids`;
- source overlap membership and the overlap groups' `id`, `label`, and
  `member_ids`; and
- retired transport codes: `code`, `kind`, `former_id`,
  `retired_in_panel`, and the user-visible migration `reason`.

Overlap collections have no semantic order: sort source `overlap_group_ids`,
sort overlap groups by `id`, and sort each group's `member_ids` before hashing.
Order-only edits remain visible to the complete registry audit hash.

The projection deliberately excludes registry and election identifiers,
freeze and research timestamps, registry notes, category descriptions,
organization and discovery URLs, geographic labels already represented by
eligibility, publisher provenance, panel rationale, and every discovery field.
Those values remain covered by `source_registry_hash`.

Excluding `panel_id` and `panel_version` prevents an empty version bump from
manufacturing a new contract hash. A real structural change produces a new
hash; the append-only catalog then requires a new panel identifier before it
will accept that contract.

### Legacy hash compatibility

The primary and general panels already have public `panel_hash` values created
from the old full-registry algorithm. Those exact values remain valid and the
committed snapshot catalogs remain byte-for-byte unchanged.

`SourceRegistry` schema 1.2 adds a required `panel_hash_compatibility` lineage
anchor. Schema 1.1 remains readable for immutable historical inputs. Each
existing published panel's current registry advances to schema 1.2 and receives
one anchor containing:

- its `panel_id`;
- the new canonical projection hash of the contract that was published; and
- its existing public legacy `panel_hash`.

The anchor remains on every later registry in the same version lineage; its
`panel_id` identifies the initially published panel rather than necessarily the
current registry. When the current projection matches the binding,
`build_panel_snapshot` continues to emit the legacy public hash. A
discovery-only refresh still matches and therefore remains the same panel
identity. If a structural field changes, the projection no longer matches; the
compatibility binding is not used and the new projection hash becomes the
candidate identity. Attempting to publish that changed contract under the old
`panel_id` is rejected by the existing append-only catalog rule, requiring an
intentional version bump.

The compatibility object itself remains part of the full registry audit hash,
but never enters the canonical panel projection. Compatibility bindings are
validated data, not conditional branches scattered through builders. Schema
1.2 rejects a missing anchor, and an anchor's `panel_id` must belong to the same
version lineage as the registry. A new lineage anchors its initial canonical
hash to itself. Later versions retain the anchor: a structural change uses its
canonical projection hash directly because it no longer matches, while an empty
version bump still emits the anchored published hash and is rejected by the
catalog as a duplicate.

### Schema evolution

Newly generated publication metadata, release status, and release manifests
carry both the stable panel hash and the full registry hash. Their schema
versions advance where required. Readers continue accepting the existing
published schema versions; an older artifact without `source_registry_hash`
retains its historical meaning, while every newly generated artifact requires
both hashes.

Deployment and release comparisons distinguish the two questions:

- panel compatibility compares `panel_id` and the stable panel hash; and
- exact release-input equality compares the full registry hash.

The browser payload does not receive the full registry hash because discovery
metadata has no role in link decoding or personalized selection.

## Failure behavior

- A malformed compatibility binding fails registry validation.
- A stale binding whose projection no longer matches is never allowed to mask
  the structural change; the computed canonical hash wins.
- A changed contract under an already published `panel_id` is rejected by the
  snapshot catalog rather than rewriting history.
- A new release artifact missing the full registry hash fails validation.
- Older immutable artifacts remain readable under their original schema and
  are never rewritten in place.

## Testing

Behavioral tests are written first and observed failing on the base revision.
They prove that:

1. changing each discovery field, organization URL, notes, and check/freeze
   timestamps changes `source_registry_hash` but not `panel_hash`;
2. changing membership, codes, selectable categories, roles, labels,
   eligibility, overlap policy, or retired-code migration semantics changes the
   canonical panel identity;
3. the published primary and general panels retain their exact existing hashes
   and still round-trip through the snapshot catalog and personalized-link
   codec;
4. a discovery-only refresh is an idempotent snapshot operation with no panel
   version bump;
5. a structural change under an existing panel identifier is rejected;
6. new release artifacts carry both hashes and release/deployment comparison
   uses the correct one for each purpose; and
7. legacy release artifacts remain readable.

Focused source, personalization, publication, release, hosting, and JavaScript
link tests run before the complete repository gate. Because release builders
and rendered payloads change, `make check-release-reproducible` is also
required before publication.

## Documentation

The source-panel snapshot documentation will list the exact identity fields,
name the full registry hash separately, and state the lifecycle boundary:
routine discovery refreshes update release audit identity but do not require a
panel version bump; transport, eligibility, overlap, or migration-contract
changes do.

## Non-goals

This change does not alter source membership, eligibility, scoring policy,
endorsement interpretation, any existing panel snapshot, or the personalized
link grammar. It does not migrate or republish historical release bundles.
