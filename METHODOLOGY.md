# Methodology

This document describes the publication methodology. The binding launch choices
live in [DECISIONS.md](DECISIONS.md).

## Principles

- Publish only official organizational endorsements supported by preserved evidence.
- Treat silence, missing publication, explicit no endorsement, and ambiguity as distinct
  states.
- Match candidates only within an already-matched race.
- Give each eligible, explicitly endorsing source one total point per race.
- Split a multi-candidate endorsement equally.
- Exclude missing and no-endorsement states from candidate share while displaying their counts.
- Report source coverage alongside agreement so small samples do not look authoritative.
- Show Seattle Times separately from the progressive consensus.

## Editorial disclosure

The output aggregates a selected set of progressive and left-of-center organizations. It is not
official election information, independent candidate vetting, or a prediction of candidate
quality or electoral success. Exact ballot contents vary by voter address.

The published guide preserves the frozen source list, eligibility rules, audit grade
thresholds, overlap warnings, review status, limitations, and build version.

The launch panel is now preregistered in
[`config/sources/default.yaml`](config/sources/default.yaml), and its human-readable discovery
report is [`docs/SOURCE_DISCOVERY.md`](docs/SOURCE_DISCOVERY.md). Later collection and scoring
work must consume that freeze without adding or removing sources based on observed consensus.

## Source checks

The [preregistered methodology](docs/superpowers/specs/2026-10-18-source-panel-sensitivity-methodology-design.md)
defines deterministic exclusions of each contributing source, each contributing reporting
category when two or more contribute, and each directly registered group with at least two
eligible members and one contributor. Each check reruns the canonical unweighted scorer
from the same reviewed inputs. It does not change the published consensus or deduplicate sources.

A change is material when measured leaders, recommended choices, or recommendation state
change; the leading share crosses the strictly-greater-than-half majority boundary; or
the leading share moves by at least 10 percentage points. A lead margin of at most
10 percentage points is narrow. Ordinary audit-grade changes alone are recorded without
a sensitivity warning. Exact thresholds and scenario membership are fixed before real-data
results are examined.

Only material changes produce overview warnings. Race pages disclose every All sources
check, skipped category/group, and quiet stable, narrow, tied or insufficient explanation.
Customization suppresses the overview's audited claim; race-page checks remain explicitly
All sources. These overlapping checks are not a probability sample, a confidence percentage,
candidate vetting or a prediction. Missing sources, unregistered relationships and alternative
policies remain outside the claim. Historical guides without checks make no stability claim.

Separate JSON/CSV audit exports preserve exact snapshots, deltas, approved policy and input
identities. Publication and release validation recompute them from the original canonical
inputs. See [export contracts](docs/PUBLICATION_EXPORTS.md) and [scoring rules](docs/SCORING.md).
