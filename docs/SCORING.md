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
publication-eligible Seattle-ballot races. Each legislative-district organization counts as an
independent source in federal, statewide, judicial, countywide, citywide, and other non-legislative
races where it publishes an explicit decision. It applies to legislative contests only in its own
registered district. The shared Democratic Party network is disclosed rather than deduplicated.
Comparison and excluded sources never enter the default denominator.

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
signals and comparison-only decisions. The category breakdown keeps representation counts
(`eligible_source_count`, `source_coverage_count`, and `explicit_endorsement_count`) separate from
candidate support points. A category with more sources therefore remains visibly more represented;
the output does not present categories as independent samples or equally weighted blocs.

Possible overlap groups report the registered relationship and the eligible, covered, and explicit
members for each race. These are disclosures, not statistical estimates of dependence. The default
view remains the raw, unweighted source-level consensus, and overlap never silently changes source
weights. No deduplicated view is computed because a possible relationship alone does not establish
a shared endorsement decision. Any future deduplicated view must be optional and explicitly labeled.

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

Consensus report schema `1.1` adds per-race possible-overlap group details. It is intentionally a
new wire version because a `1.0` consumer cannot validate those required fields.

## Source sensitivity analysis

Issue [#65](https://github.com/shaug/seattle-election-guide/issues/65) has a
[preregistered methodology](superpowers/specs/2026-10-18-source-panel-sensitivity-methodology-design.md)
for deterministic source, reporting-category, and disclosed-group exclusions.
It defines the scenario set, material-change thresholds, classifications, and
audit outputs before examining real-data scenario results. Policy
`source-panel-sensitivity-v1` implements that contract through the same prepared
canonical scorer. `consensus.json` is unchanged; every publication race has a
separate `sensitivity.json` result, including unopposed races omitted from the overview.

Individual scenarios remove every affirmative eligible source in turn. Category
scenarios remove all eligible members of a reporting category when at least two
categories contribute. Disclosed groups use their directly registered eligible
members, with at least two members and one contributor; membership never expands
transitively. Non-endorsers and missing members leave with their category/group.
Every exclusion starts from the baseline, and skipped categories/groups record
fixed reasons. Comparison-only and ineligible sources never enter an exclusion.

Exact leader, recommendation-state, or recommendation-choice changes are material.
So are crossing strictly above one half and a leading-share change of at least
`1/10`. Ordinary grade changes alone remain audit data. Classification precedence
is source-sensitive, category-sensitive, overlap-sensitive, tied, insufficient,
narrow-but-stable (lead margin at most `1/10`), then stable. All material scenario
IDs and affected kinds survive that primary classification. No-support shares
and their numeric deltas remain null; reporting zero-fills official choices
without creating artificial ties. The canonical review gate runs before exclusions.

`validate_sensitivity_report` recomputes the entire report from the original
dataset, consensus and approved policy, including skips, deltas, wording and
provenance. Rewritten self-hashes do not authorize a changed result or policy.
