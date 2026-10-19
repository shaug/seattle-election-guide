# Publication exports

The publication build converts one validated canonical dataset and its authoritative consensus
report into a deterministic artifact bundle. It does not collect evidence, normalize claims, or
recompute presentation values in a renderer.

```bash
uv run election-guide export build \
  --dataset-path data/normalized/canonical-dataset.json \
  --consensus-path data/normalized/consensus.json \
  --snapshot-root data/snapshots \
  --output-dir build \
  --git-commit "$(git rev-parse HEAD)"
```

`--git-commit` may be omitted. The command then uses `GITHUB_SHA`, or the current Git revision
when that variable is absent. Every captured snapshot is verified against its manifest before the
consensus report is fully recomputed from the supplied dataset. Every artifact is then computed in
memory, staged in a sibling directory, and committed as one directory generation. The output
directory is dedicated to this canonical bundle; replacement is refused when unrelated entries
are present.

## Canonical bundle

- `consensus.json`: the revalidated exact scoring result.
- `sensitivity.json`: the complete exact exclusion audit under policy `source-panel-sensitivity-v1`.
- `sensitivity_scenarios.csv`: one row per tested race/scenario, including full snapshots and deltas.
- `publication_view_model.json`: the presentation-neutral input the renderer reads.
- `race_summary.csv`: one row per published race and its displayed scoring values.
- `endorsement_records.csv`: effective normalized decisions with allocations and evidence links.
- `source_metadata.csv`: the complete frozen registry, including excluded sources.
- `unresolved_review_items.csv`: unresolved review work and evidence locators.
- `source_matrix.csv`: every published race crossed with every active source.
- `validation_report.json`: machine-readable publication checks.
- `provenance_manifest.json`: hashes binding configuration, captures, normalized records, and
  consensus output.
- `build_manifest.json`: revision, counts, warnings, and hashes for every other bundle artifact.

JSON uses canonical sorted serialization and exact rational strings such as `"3/4"`. CSV uses
registry and inventory order, explicit field order, UTF-8, and Unix newlines. Identical inputs,
build timestamp, and Git revision therefore produce identical bytes.

`publication_view_model.json` uses schema `1.15`. It requires per-race sensitivity
summaries/details, the approved methodology policy, and a sensitivity report hash.
Schemas `1.9`, `1.13` and `1.14` remain readable without those fields and cannot
declare sensitivity claims. Evidence-linked source cells retain public capture,
publication, update, title and redistribution metadata; `is_contested` remains
derived from the authoritative inventory.
Those fields support audit exports and traceability; the voter-facing race panel intentionally centers
source, decision, agreement, and evidence link rather than displaying the full metadata record. The
model also retains per-source participation counts, candidate-centric affirmative endorsement groups,
category analysis, and overlap metadata for audit.

## Shared view model

Every consumer must read `publication_view_model.json` rather than calculating winners, grades,
percentages, coverage, comparisons, or warnings independently. The model
includes preformatted recommendation, percentage, support, alternatives, comparison badges,
candidate-centric affirmative endorsement groups, per-race category representation and candidate
support, methodology, the audit grade legend, limitations, build identity, and ordered source
cells. The voter-facing guide uses the consensus share and source count rather than displaying
the audit grade. Methodology also publishes source categories and possible-overlap groups. It
identifies `source_level` as the default aggregation view and `not_computed` as the deduplicated-view
status, so a consumer cannot silently substitute coalition grouping for raw source-level consensus.

Sensitivity report schema `1.0` carries one baseline per publication race and a full
canonical result for each independent exclusion, including all official choice
vectors, population IDs, signed counts/points/shares, changed fields, ID differences,
grade changes and material reasons. Null shares/deltas remain null. Scenario order
is source, category, overlap, then lexical target ID; choices retain ballot order.
Skipped category/group entries are validated as strictly as tested scenarios.

The CSV's fixed header is present for empty suites. Scalar missing shares/deltas
are blank and exact zero is `0`; canonical JSON cells `baseline`, `after` and
`delta` retain the complete structured data, including explicit nulls and warnings.
`race_summary.csv` adds `sensitivity_policy_id`, `sensitivity_classification`,
`sensitivity_tested_count`, `sensitivity_material_count` and `sensitivity_affected_kinds`.
The view model contains compact preformatted display rows rather than raw snapshots;
the guide's browser payload contains only a nullable warning and its full detail link.

The report binds dataset, complete registry, stable panel, publication scope,
canonical scoring configuration, consensus bytes, approved full policy/hash,
explicit computation timestamp and publication revision. Both sidecars enter the
build/release manifest hashes; the policy hash enters configuration provenance.
The new-format release verifier requires both sidecars even if artifact inventories
are rewritten, and recomputes the report from bundled canonical inputs before
reconciling CSV and view-model projections. Historical release bytes are unchanged.
Newly staged sites publish the two verified downloads under each election's `data/`
directory; race-page details link to them and to the public methodology.
Each published race also carries `is_contested`, derived solely from whether the authoritative ballot
inventory contains more than one official choice. Endorsement coverage never influences that flag.

`PublicationViewModel.guide_sections` projects the general-election Endorsements overview from
the complete `sections` record: an unopposed race appears only when an active consensus or
comparison source cell has a verified `endorsement` or `multi_endorsement`. Empty sections are
omitted. The guide's cards, filter options, screenshot counts, and semantic validation use this
one projection. The serialized model, individual race pages, Comparisons, and embedded race
identities retain the complete race set, so audit data and legacy `#race-…` links remain available.
Source selection does not change this projection, and primary-election rendering uses the full
sections unchanged (issue [#528](https://github.com/shaug/seattle-election-guide/issues/528)).

Every active source includes `endorsement_count` and `split_endorsement_count`. The first counts
published races where its effective cell is `endorsement` or `multi_endorsement`; the second is the
subset in `multi_endorsement`. Counts include only races published in the guide. The Seattle Times
comparison uses the same affirmative-decision derivation but is labeled as picks, because it never
enters the progressive consensus. Source-category membership and category order are also validated
against the publication source registry.

Every active source also has a presentation status. `contributing` sources appear in the guide's
source directory. A `coverage_gap` remains in the audit registry and source matrix but appears in
a separate voter-facing section with its official URL, discovery status, and research note. This
distinguishes missing or inaccessible published results from an explicit decision not to endorse;
it does not change eligibility or scoring.

An `Insufficient` race retains its measured support leader for audit, but has no recommendation
candidate and its audit recommendation label remains `Too few endorsements`. The guide card
displays the measured support leader's name when endorsements exist, with the insufficiency
warning below it; zero endorsements retain the unavailable heading. The display does not turn
one source's choice into a consensus recommendation (issue
[#532](https://github.com/shaug/seattle-election-guide/issues/532)).

Each endorsement group contains one candidate or choice and only the consensus-panel sources that
affirmatively endorsed it. Multi-candidate endorsements appear under every endorsed choice with a
co-endorsement marker. The evidence URL and locator remain attached to each endorser; comparison,
non-endorsement, missing, unavailable, and not-applicable states remain in the ordered source cells.

Each source cell has one explicit state:

- `endorsement`: one candidate is endorsed.
- `multi_endorsement`: two or more candidates share the source's endorsement.
- `no_endorsement`: the source explicitly declined to choose.
- `not_covered`: no usable decision was published for an eligible race.
- `unavailable`: access failed and only an unavailable-evidence manifest exists.
- `unverified`: the normalized decision still requires review.
- `not_applicable`: the race is outside the source's registered geography.

Candidate IDs, exact allocations, evidence URLs, evidence locators, public capture titles, capture and
publication dates, redistribution status, and confidence warnings stay attached to the cell. Storage
references and restricted artifacts do not enter the public model. This makes displayed values and
states traceable without inspecting a renderer.

## Hash boundaries

The provenance manifest records separate hashes for election inventory, source registry, scoring
policy, every captured content snapshot or unavailable manifest, effective normalized data, the consensus
bytes, and the canonical dataset. The build manifest adds hashes for all other generated
artifacts. It intentionally does not hash itself, which avoids a circular self-reference.
