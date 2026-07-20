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
- `publication_view_model.json`: the presentation-neutral input shared by HTML and PDF.
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

## Shared view model

HTML and PDF consumers must read `publication_view_model.json`; neither consumer may calculate
winners, grades, percentages, coverage, comparisons, or warnings independently. The model
includes preformatted recommendation, percentage, support, alternatives, comparison badges,
methodology, grade legend, limitations, build identity, and ordered source cells.

An `Insufficient` race retains its measured support leader for audit, but has no recommendation
candidate and displays `Insufficient coverage`. This prevents a renderer from turning one source's
choice into a consensus recommendation.

Each source cell has one explicit state:

- `endorsement`: one candidate is endorsed.
- `multi_endorsement`: two or more candidates share the source's endorsement.
- `no_endorsement`: the source explicitly declined to choose.
- `not_covered`: no usable decision was published for an eligible race.
- `unavailable`: access failed and only an unavailable-evidence manifest exists.
- `unverified`: the normalized decision still requires review.
- `not_applicable`: the race is outside the source's registered geography.

Candidate IDs, exact allocations, evidence URLs, evidence locators, and confidence warnings stay
attached to the cell. This makes displayed values and states traceable without inspecting a
renderer.

## Hash boundaries

The provenance manifest records separate hashes for election inventory, source registry, scoring
policy, every captured content snapshot or unavailable manifest, effective normalized data, the consensus
bytes, and the canonical dataset. The build manifest adds hashes for all other generated
artifacts. It intentionally does not hash itself, which avoids a circular self-reference.
