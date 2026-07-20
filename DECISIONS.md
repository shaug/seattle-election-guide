# Launch Decisions

These decisions define the first publishable release. Changes require a documented pull
request before viewing consensus results, so methodology cannot be tuned to an outcome.

## Product scope

- The first release covers races and measures that can appear on at least one ballot for a
  voter registered within the City of Seattle.
- The complete King County sample ballot is an input, not the publication scope. Each race
  must have evidence that its jurisdiction intersects Seattle.
- The target publication date for the first release is July 25, 2026.
- Incomplete coverage is acceptable when gaps are explicit. Untraceable claims are not.

## Collection and evidence

- The manual-entry adapter is a first-class collection path for the initial release.
- Easy, stable sources may receive automated adapters, but comprehensive automation is not a
  launch requirement.
- Source organizations are preregistered before scoring begins.
- Full captures from paywalled, copyrighted, or access-controlled pages remain outside the
  public repository unless redistribution is clearly permitted.

## Consensus eligibility

- An eligible source is active, preregistered for the default panel, relevant to the election,
  and geographically applicable to the race.
- Legislative-district organizations participate in the default consensus wherever they publish
  an explicit decision for a race on a Seattle ballot, including federal, statewide, judicial,
  countywide, and citywide races. They may contribute to legislative contests only in their own
  district; party-network overlap remains disclosed rather than suppressing valid support.
- Each eligible, explicitly endorsing source contributes exactly one total point per race.
- Seattle Times editorial-board endorsements are comparison-only by default.
- Coalition overlap is recorded and disclosed. It is not converted into a speculative
  statistical correction.

## Grade rules

Scoring uses exact rational allocations and unrounded shares. Resolution order is:

1. `TIED` when multiple choices share the greatest support.
2. `Insufficient` when fewer than two eligible progressive sources explicitly endorse.
3. `A+` for a share at least 90 percent with at least four explicit sources.
4. `A` for a share at least 75 percent.
5. `B` for a share at least 60 percent.
6. `C` for a share at least 45 percent.
7. `D` otherwise.

Missing coverage and explicit no-endorsement decisions do not enter the candidate-share
denominator, but both remain visible as separate coverage signals.

## Publication gate

- An unresolved high-severity review item affecting a displayed race blocks the standard
  publication build.
- HTML and PDF are generated from one publication view model.
- Reproducibility tests use an explicit build timestamp or `SOURCE_DATE_EPOCH`.
- GitHub Releases, rather than normal commits, carry versioned publication bundles.
