# Source panel sensitivity and recommendation robustness

Issue: [#65](https://github.com/shaug/seattle-election-guide/issues/65)

Status: Proposed methodology for review, October 18, 2026.

Show whether the audited result changes when a contributing source, a reporting
category, or a disclosed organizational group is excluded. Keep the standard
audited consensus as the publication baseline. Sensitivity describes dependence
on the sources counted; it does not estimate election probability, statistical
confidence, source independence, or candidate quality.

This specification fixes the proposed scenario rules and thresholds before
examining their outputs on real election data. All examples below are synthetic.
Review and merge the methodology before running that analysis. Any later change
to these rules requires a new policy version and a documented rationale; an
outcome-driven adjustment cannot be presented as the original preregistered test.

The authorities remain [DECISIONS.md](../../../DECISIONS.md),
[ARCHITECTURE.md](../../../ARCHITECTURE.md), [SCORING.md](../../SCORING.md),
[DESIGN.md](../../DESIGN.md), and [FRONTEND.md](../../FRONTEND.md). This proposal
adds an audit beside scoring; it does not amend the existing scoring rules.
Implementation, real-data analysis, and publication remain future work under #65.

## Questions the analysis answers

For each publication-eligible race or ballot measure:

1. Does excluding one contributing source change the leaders, recommendation
   state, majority status, or leading share materially?
2. Does excluding one contributing reporting category change those values?
3. Does excluding the eligible members of a disclosed group change those values?

A fixed exclusion suite answers these questions reproducibly. Reader-selected
source comparisons remain useful exploration, but do not establish that every
prescribed scenario was tested. Exhaustive subset enumeration and resampling
would answer different questions and are outside this methodology.

## Policy fixed before analysis

Use policy ID `source-panel-sensitivity-v1`. Its machine-readable policy must
contain the scenario and skip rules, material-change tests, exact rational
thresholds, and classification and reason priorities defined below. The report
embeds that complete policy and its canonical hash, alongside a separate wire
schema version starting at `1.0`.

| Decision | Version 1 rule |
|---|---|
| Baseline | The authoritative, unweighted audited consensus |
| Individual exclusions | Every eligible source making an affirmative endorsement in the race |
| Category definition | The source's one `reporting_category_id` |
| Category applicability | At least two reporting categories have affirmative endorsements |
| Group definition | Direct membership in a registered possible-overlap group |
| Group applicability | At least two eligible members and at least one affirmative member |
| Material share change | Absolute leading-share change of at least `1/10`, or 10 percentage points |
| Majority boundary | Leading share strictly greater than `1/2` |
| Narrow lead | Baseline leader's share minus runner-up share is at most `1/10` |
| Identity and state changes | Always material; no minimum share change required |
| Scenario combinations | None; each exclusion starts from the complete baseline |

The two `1/10` thresholds serve different purposes: one detects a substantial
change in displayed agreement; the other describes a close baseline lead. They
are editorial interpretation rules, not estimates of uncertainty. Use exact
values at both boundaries, without rounding first. Audit letter-grade changes
are recorded but do not independently trigger a voter-facing warning, because
the guide does not display those grades.

## Inputs and scoring semantics

Use the same validated canonical dataset, effective reviewed records, frozen
registry, scoring configuration, publication race list, and explicit computation
timestamp as canonical scoring. Revalidate the supplied baseline against those
inputs before calculating scenarios. A report cannot establish its own scope or
baseline by supplying matching hashes alone.

Analyze every publication-eligible race, including unopposed races omitted from
the Endorsements overview. Reader filters never change the analysis scope.

For a race, let `E` be exactly the consensus sources admitted by canonical
scoring's eligibility rules. Let `X` be the members of `E` whose effective record
has status `endorsed`, `dual_endorsement`, or `multiple_endorsement`. Let `C` be
the reporting categories represented by `X`. Sources outside `E`, including
Seattle Times and every other comparison-only or excluded source, never enter
an exclusion set or the scenario denominator.

`C` controls scenario applicability only. Canonical `category_coverage_count`
continues to count categories with resolved decisions, including explicit
non-endorsements; it must not be replaced with `len(C)`.

An exclusion removes membership from the scenario's counted sources, rather
than changing an endorsement into missing coverage. Retained sources preserve
all canonical semantics:

- Each affirmative source contributes one point, split exactly across its
  endorsed choices. Removing a co-endorser removes its entire one-point
  allocation, including every fractional part.
- `no_endorsement` and `declined_to_endorse` are resolved coverage with no
  candidate points. Missing, unavailable, ambiguous, and unverified records do
  not become endorsements or explicit non-endorsements.
- Legislative-district eligibility is identical to canonical scoring in every
  race. Excluding other sources cannot admit an otherwise ineligible source.
- Ties precede insufficient evidence, which precedes ordinary grades. A single
  source's split endorsement can therefore remain canonically tied. No support
  means no measured leaders, a null share, and insufficient evidence; it does
  not create a tie between zero-point choices.
- An insufficient result may retain a measured support leader but has no
  recommendation. Preserve the publication convention that tied results list
  all tied choices, while insufficient results have an empty recommendation
  choice list. A tie does not establish a singular recommendation.

Apply exclusions within the scoring boundary using the canonical allocation,
eligibility, and state-resolution logic. Do not mutate the canonical dataset or
registry, rewrite source roles, or reproduce scoring inside a renderer. The
unexcluded result must match the authoritative baseline exactly. Existing
before/after comparison helpers may support the audit, but cannot replace the
scenario enumeration or the complete deltas specified here.

Run the ordinary review gate before exclusions. An excluded source cannot hide
an unresolved high-severity review item. If the existing explicit exceptional
build mode is used, preserve its warnings and exceptional status in both reports;
sensitivity never clears or overrides them.

## Scenario enumeration

Build each race's complete scenario inventory from the baseline inputs once.
Never decide which scenarios to run from a previous scenario's result.

| Kind and scenario ID | Excluded members | When tested |
|---|---|---|
| `source:<source-id>` | That one source | For every member of `X` |
| `category:<category-id>` | All members of `E` with that reporting category | For every category in `C`, when `len(C) >= 2` |
| `overlap:<group-id>` | `E` intersected with the registered group's `member_ids` | When that intersection has at least two members and intersects `X` |

Category and group exclusions remove all their eligible members, including
members with explicit non-endorsements or missing coverage. This keeps scenario
coverage counts truthful. Non-contributing sources do not get individual
scenarios: excluding one cannot alter support, explicit-source count, or
recommendation state. The baseline still identifies those sources and their
coverage states.

Reporting categories are mutually exclusive in canonical scoring. The additive,
possibly overlapping `selection_category_ids` used by source customization do
not define category exclusions in version 1. Categories are not equally weighted
blocs or independent samples.

Groups use only the disclosed, directly registered members. Do not infer groups
from party labels or publishers, merge groups through a shared member, or follow
membership transitively. A group exclusion asks what happens without those
sources; it makes no claim that their endorsement decisions were duplicates.
An applicable group is tested even if it removes every contributing source.

Keep separately identified scenarios when two exclusions happen to remove the
same members. Record every eligible reporting category and every registered
group that was not tested, with its eligible member IDs and one fixed reason:
`fewer_than_two_contributing_categories`,
`fewer_than_two_eligible_members`, or `no_contributing_members`. For categories,
record `no_contributing_members` for an eligible category outside `C`; for a
category in `C`, apply the category-count rule. For groups, test the eligible
member-count rule before the contributing-member rule. Non-applicable scenarios
are not successful tests and cannot support a stability claim.

For a race with `N` affirmative sources, `K` contributing reporting categories,
and `G` applicable registered groups, the suite has
`N + (K if K >= 2 else 0) + G` scenarios. There are no pairwise exclusions,
iterative pruning, random samples, or configurable outcome-specific additions.

## Exact results and material changes

Every baseline and scenario snapshot contains:

- measured leader IDs in canonical ballot order, leading support points, and
  leading share;
- canonical grade, tie flag, recommendation choice IDs, and a derived state:
  `tied` when the grade is `TIED`, otherwise `insufficient` when the grade is
  `Insufficient`, otherwise `recommended`;
- eligible, resolved, affirmative, explicit non-endorsement, missing, represented
  category, and pending-review counts, plus their associated source/review IDs;
- every official choice's support and share, and the canonical structured
  warnings and overlap/category disclosures.

For delta reporting, zero-fill support for official choices absent from a
scored support map. Their shares are zero when the denominator is positive and
null when it is zero. This reporting projection must not alter canonical tie
resolution. A sole supported choice has a zero-point runner-up when calculating
the lead margin; a tied lead has margin zero; no support has a null margin.

Each race stores one baseline snapshot. Every scenario references that baseline
and stores its complete result snapshot, a sorted list of changed fields,
signed numeric deltas (`scenario - baseline`), choice-level support and share
deltas, added/removed IDs, and these independently derived material-change reasons:

| Reason | Exact test |
|---|---|
| `leaders_changed` | The ordered measured leader IDs differ |
| `recommendation_state_changed` | The derived state differs, including entering or leaving a tie or insufficient evidence |
| `recommendation_choices_changed` | The canonical recommendation choice IDs differ |
| `majority_boundary_crossed` | Both leading shares exist and `(share > 1/2)` differs |
| `leading_share_changed_materially` | Both leading shares exist and the absolute delta is at least `1/10` |

A scenario is material if any reason applies. Preserve every reason when more
than one applies. Null shares remain null, and a numeric delta involving null
is null; the snapshots and leader/state changes explain the transition. Never
substitute zero for an unavailable share. Ordinary grade-boundary crossings are
recorded separately, even when they are not material.

A smaller share change, the expected decrease in source count, or the removal
of an overlap/coverage warning alone does not trigger a sensitivity warning.
Canonical evidence and coverage warnings continue to appear under their own
rules. Do not interpret a less diverse scenario's cleaner warning list as
improved evidence.

## Classification and voter wording

Classify in this fixed precedence order. Also publish all material scenario IDs
and all affected scenario kinds; the primary label must not discard a secondary
category or group effect.

| Classification | Condition |
|---|---|
| `source_sensitive` | At least one material individual-source scenario |
| `category_sensitive` | Otherwise, at least one material category scenario |
| `overlap_sensitive` | Otherwise, at least one material group scenario |
| `tied` | Otherwise, baseline is tied |
| `insufficient` | Otherwise, baseline is insufficient |
| `narrow_but_stable` | Otherwise, baseline has a singular recommendation and lead margin at most `1/10` |
| `stable` | Otherwise, baseline has a singular recommendation |

An empty suite never earns `stable` or `narrow_but_stable`: with zero affirmative
sources the baseline is insufficient. Existing warnings retain their precedence.
Stability says only that none of the prescribed exclusions materially changed
the result. It says nothing about unregistered sources, missing endorsements,
unreviewed evidence, alternative thresholds, or representativeness.
Do not turn the fraction of unchanged scenarios into a confidence percentage;
the scenarios overlap and are not a probability sample.

Use quiet explanatory text on the race page for stable results: "Same leading
choice in all tested exclusions." For `narrow_but_stable`, use "Close lead;
same choice in all tested exclusions." Link both to the scenario details and
methodology. A tied or insufficient baseline never receives either statement.
With no material scenario, use "Tied across tested exclusions" or "Too few
endorsements," as appropriate.

Only material scenarios produce a prominent sensitivity warning. Name the
actual changed dimension rather than implying a different recommendation when
only the share changed. For example:

- "Leading choice changes without {source}."
- "Tied without {category} sources."
- "Too few endorsements without {group}."
- "No majority without {source}."
- "Agreement changes by {change} percentage points without {group}."

These are templates for the corresponding actual transitions; reverse changes
must describe their real before/after states. For multiple material scenarios,
show one concise warning and an accessible disclosure containing every result.
Choose its illustrative scenario by reason priority: recommendation-state
change, recommendation-choice change, measured-leader change, majority crossing,
then material share change; break ties by scenario order. The classification
still follows the table above. Every label must be justified by linked results.

Follow DESIGN.md: no candidate-quality grade, confidence badge, extra meter,
color-only meaning, or internal "panel" vocabulary outside audit metadata. Keep
the source count and share as the primary data. Material warnings use the
existing differ tone; stable explanations use plain muted text. Detailed
results belong on the existing race page; no new modal or standalone task page
is needed. On the Endorsements overview, show only material warnings. Compact layouts may link to
their full explanation without changing the warning's meaning across widths.

This suite describes **All sources**. While a personalized selection is active,
suppress the overview's sensitivity line rather than attaching the audited
claim to the selected result. Race-page audit details remain explicitly labeled
All sources. Recomputing sensitivity for arbitrary personalized selections is
outside version 1. Browser code consumes the published results and preformatted
wording; it does not run scenarios or classify results.

## Artifacts and reproducibility

Publish `sensitivity.json` and `sensitivity_scenarios.csv` beside the existing
audit exports. JSON contains the complete report: policy, input identities,
baseline snapshots, tested scenarios, skipped groups/categories, exact deltas,
classifications, material reasons, and preformatted summaries. CSV has one row
per tested race/scenario, with family and target, excluded member IDs,
before/after leaders and recommendation states/choices, leading support/share,
every count and its signed delta, audit grades, changed fields, and material
reasons. Choice-level vectors and structured before/after warnings may use
canonical JSON within CSV cells; CSV must preserve the complete result delta.

Extend `race_summary.csv` with policy ID, classification, tested/material counts,
and affected scenario kinds. The publication view model carries the same
validated per-race summary and details needed by HTML. Scenario outputs and
summaries are separate from `consensus.json`; baseline consensus bytes must be
identical with and without the analysis enabled. Add artifact hashes to the
existing build/release manifests and bind the report to:

- election ID, canonical dataset hash, complete source-registry hash, stable
  source-panel identity/hash, and publication-scope hash;
- canonical scoring configuration and authoritative consensus artifact hash;
- sensitivity policy ID, full policy contents/hash, schema version, and the
  explicit computation timestamp inherited from scoring.

Audit source/category IDs remain provenance. Browser-facing source/category
references use the existing transport codes and published display names, with
no new browser-side ID translation. A scenario ID is an opaque audit key, not a
second source-selection identity.

Use existing canonical JSON serialization, exact reduced rational strings,
UTF-8, and Unix newlines. CSV has an explicit fixed column order and header even
when there are no scenarios. Use canonical publication race order; within each
race, order scenarios by `source`, `category`, then `overlap`, and by target ID
lexicographically within a kind. Sort member IDs and reason/field-name sets;
preserve canonical ballot order for choice vectors and leader IDs. Serialize
skipped entries by kind then target ID using the same family order.
In scalar CSV cells, a missing share or delta is an empty cell, while exact zero
is `0`; collection and structured cells use canonical JSON with explicit nulls.

Do not read the clock, network, local preferences, or filesystem enumeration
order. The same canonical inputs, policy, timestamp, and publication revision
produce identical report and export bytes. No scenario mutates its inputs or
another scenario. Any schema carrying new required fields advances its version;
existing immutable release artifacts remain readable and are not rewritten.

## Validation and required fixtures

Recompute scenario membership, results, deltas, material reasons, and summaries
from the original canonical inputs during validation. Reject omitted or extra
scenarios, missing races, duplicate IDs, unauthorized members, stale hashes,
altered deltas, and a summary that disagrees with its scenarios. Validate skipped
entries too, so an applicable scenario cannot disappear behind a skip reason.
Require the embedded policy to match the approved policy input supplied to the
build; a self-declared matching policy hash cannot authorize different thresholds.
Reconcile JSON, CSV, view-model, rendered labels, and manifest hashes. A missing
or invalid required sensitivity artifact blocks the new publication format;
never silently publish it as "stable." Older releases without the feature make
no sensitivity claim.

The following worked examples use single-choice endorsements, sufficient
eligible sources, and no registered groups except where stated. Every source
has exactly one reporting category. They illustrate the rules without tuning
them to election results:

| Synthetic input | Expected interpretation |
|---|---|
| Four categories, each with 15 endorsements for A and 5 for B | A leads with `3/4`; every individual/category exclusion is nonmaterial: `stable` |
| Four categories, each with 11 endorsements for A and 9 for B | A leads with `11/20`, margin `1/10`; every individual/category exclusion is nonmaterial: `narrow_but_stable` |
| One category, two endorsements for A and one for B | Excluding an A source creates a tie: `source_sensitive`; the sole category is skipped |
| Two categories: one with 8 for A and 2 for B, the other with 4 for A and 6 for B | Individual exclusions are nonmaterial; excluding the first category gives B the lead, and excluding the second raises A's share by `1/5`: `category_sensitive` |
| Four categories, each with 3 for A and 2 for B; one disclosed group contains two A sources from each category | Individual/category exclusions are nonmaterial; excluding the eight group members leaves 4 for A and 8 for B: `overlap_sensitive` |

Fixtures must cover at least these synthetic cases, without using real results
to choose thresholds:

| Case | Required observation |
|---|---|
| Stable | Supported leader and state remain unchanged; no material share or majority change in any prescribed scenario |
| Narrow but stable | Unique lead margin is exactly `1/10`; every scenario is nonmaterial; a margin just above that boundary is `stable` |
| Single-source sensitive | Removing a specific source changes leader or creates a tie, even if leading share is unchanged |
| Category sensitive | No individual exclusion is material, but removing a reporting category changes the interpretation |
| Overlap sensitive | No individual/category exclusion is material, but removing a registered group is material |
| Multiple effects | All material families and reasons survive the primary-classification and illustrative-scenario priorities |
| Tied | Stable ties remain tied; a broken tie records the state/choice changes without inventing a baseline singular recommendation |
| Insufficient | Zero-source shares stay null; one-source measured leaders and shares remain visible without creating a recommendation |
| Tie before insufficiency | One split endorsement is tied before exclusion; removing it leaves insufficient evidence |
| Fractional and coverage states | Multi-endorsement points sum to one; non-endorsements and missing coverage never enter the denominator |
| Threshold boundaries | Share change exactly `1/10` is material, just below is not; exactly `1/2` has no majority, just above does |
| Grade only | A scenario crossing only an ordinary grade boundary below the share-change threshold is nonmaterial |
| Eligibility and groups | Wrong-district and comparison sources never contribute; overlapping groups do not expand transitively; duplicate member sets retain distinct scenario IDs |
| Category basis and skips | Multiple selection categories do not duplicate a source; a sole contributing reporting category is skipped; groups with too few eligible or no affirmative members are skipped |
| Complete exclusion | Removing a whole applicable group can leave zero sources; excluded sources are not counted as missing |
| Review and tampering | Exclusions cannot bypass the review gate; coherently rewritten hashes do not validate invented or incomplete scenarios |
| Determinism | Repeated builds are byte-identical, including empty-suite CSVs and deliberately varied set/map iteration order |

Use canonical scoring as the parity oracle for controlled synthetic source
subsets, and test baseline equality explicitly. Browser checks cover audited and
personalized modes, narrow widths, keyboard access to every material scenario,
and agreement between visible and accessible wording.

Implementation updates SCORING.md, PUBLICATION_EXPORTS.md, the public methodology,
and the affected schema documentation in the same change. Run `make types` when
client payload models change, `make check`, and the clean-tree
`make check-release-reproducible` gate when implementation changes rendering or
release artifacts. This specification alone requires `make check`; it does not
run or publish real-data sensitivity analysis.
