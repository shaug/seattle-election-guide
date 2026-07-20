# Consensus scoring

The default score is an unweighted source-level consensus. It consumes one already validated
canonical dataset; it does not fetch evidence, infer endorsements, or repair unresolved records.
The frozen policy is `config/scoring/default.yaml`.

## Exact allocation and denominator

Every eligible source with an explicit endorsement contributes exactly one point. A singular
endorsement contributes `1`; a dual endorsement contributes `1/2` to each choice; larger
co-endorsements split the point equally. All allocations, thresholds, support totals, and shares
remain rational values. Canonical JSON serializes them as strings such as `"3/4"`. The scoring
boundary independently rejects an approved normalization record whose allocation is not the
configured exact equal split.

Only `endorsed`, `dual_endorsement`, and `multiple_endorsement` records enter the denominator.
An explicit `no_endorsement` or `declined_to_endorse` decision counts as resolved source coverage
and increments `no_endorsement_count`, but contributes no points. Missing, unavailable,
not-published, not-covered, unverified, and ambiguous states increment `missing_source_count` and
also contribute no points.

Source eligibility comes from the frozen registry. General consensus sources apply to all
publication-eligible Seattle-ballot races. A legislative-district organization applies only to
races in its registered district. Comparison and excluded sources never enter the default
denominator.

## Grades and ties

The winner share is its exact support divided by the total points from explicit endorsements.
Resolution follows the frozen order in `DECISIONS.md`: ties first, then insufficient coverage,
then `A+`, `A`, `B`, `C`, or `D`. `A+` additionally requires four explicit sources. Tied results
list every top choice, have no singular `winner_candidate_id`, and receive `TIED` rather than an
ordinary grade.

## Coverage and warnings

Each race reports eligible, resolved, explicit, no-endorsement, missing, category-coverage, and
pending-review counts. Structured warnings expose low source or category coverage, missing and
no-endorsement decisions, confidence concerns, disclosed source overlap, and unresolved review
work. Confidence warnings cover every displayed decision, including no-endorsement coverage
signals and comparison-only decisions. Overlap remains a disclosure; it never silently changes
source weights.

The Seattle Times is read from the same canonical records but reported separately. Its result is
`agrees`, `differs`, `no_endorsement`, or `not_covered` when a progressive winner exists. If it
endorses in a race with no progressive winner, the result is `no_consensus` so its choice remains
visible without inventing agreement.

## Publication gate and deterministic builds

An unresolved high-severity review item blocks scoring by default. `--allow-unresolved` permits
an exceptional output and adds both a report flag and visible race warning. Dataset and scoring
configuration validation failures also fail the command.

The build timestamp is an explicit input and cannot predate the frozen registry, evidence,
review, or override records it describes. Supply either `--computed-at` or `SOURCE_DATE_EPOCH`;
the command never reads the current clock implicitly.

```bash
uv run election-guide score \
  --dataset-path data/normalized/canonical-dataset.json \
  --config default \
  --computed-at 2026-07-20T01:00:00Z \
  --output-path data/normalized/consensus.json
```

The report embeds the validated scoring configuration and ordered publication race IDs so grade,
comparison-source, and completeness checks are self-contained. A component hash manifest binds
that publication scope and the canonical dataset hash into the result input hash. Per-race
confidence, overlap, and high-review signal IDs reconcile to required structured warnings. With
the same validated inputs and timestamp, canonical output bytes are identical.

Authoritative report revalidation requires the original canonical dataset as validation context.
The validator recomputes `dataset_hash` from that input and derives the publication race list from
its inventory, so a coherently truncated report cannot establish its own publication scope. It
then reruns scoring from the effective records and compares the complete canonical result. An
internally consistent false winner, altered comparison, missing warning, or backdated build cannot
validate merely by rewriting its public hashes.
