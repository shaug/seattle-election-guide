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
- Every general- and primary-election public view includes an uncontested race only when its actual
  eligible progressive endorsements meet the configured minimum explicit-source threshold
  (issue [#607](https://github.com/shaug/seattle-election-guide/issues/607),
  superseding #528). The official ballot determines whether a race is contested.
  This applies to Endorsements, Comparisons, individual race pages, generated race
  links, and their client payloads. Eligibility uses the full verified panel; reader source
  preferences change displayed scores only. Contested races remain visible without endorsements.
  Empty sections and filter options are omitted. The inventory, scoring, and audit
  exports retain the complete publication scope. Existing immutable archives remain unchanged;
  the primary overview requires a newly published and verified replacement archive and protected
  pin activation to adopt this visibility policy.

## Voter ballot membership (#608)

Ballot membership operates on the shared public-view projection owned by #607/#610.
It does not override the all-view visibility policy or calculate another confidence
threshold. Canonical inventory, scoring and audit records remain complete. The full
reviewed district catalog stays selectable even when a district has no visible contest.

A voter may manually specify independent districts and jurisdiction memberships.
Only reviewed citywide or city-containing jurisdictions are automatically shared.
Unanswered questions retain potentially applicable contests with a visible label.
“Setup complete” means every membership decision in SEG's inventory is resolved;
it never certifies the inventory as the voter's complete official ballot.

Ballot membership does not control section placement or ordering. Location lookup
is deferred and will supply the same profile for confirmation and manual correction.

## Collection and evidence

- The manual-entry adapter is a first-class collection path for the initial release.
- Easy, stable sources may receive automated adapters, but comprehensive automation is not a
  launch requirement.
- Source organizations are preregistered before scoring begins.
- Plaintext full captures from paywalled, copyrighted, or access-controlled pages remain outside the
  public repository unless redistribution is clearly permitted.
- Recurring endorsement verification (#497) retains endorsement facts, official URLs, actual
  check timestamps, and the actual reviewer and review timestamp in Git (SOURCE_POLICY.md).
  Responses are fetched and parsed in private temporary storage, then discarded; new records
  contain factual snapshots and observed-only metadata, hashes, checks and review attestations,
  with no full-page plaintext or ciphertext. Full-page reconstruction is not required, and
  normal operation requires no evidence key or external evidence service. Existing ciphertext,
  historical records, approvals and failures remain unchanged; migration grants no approval or
  fresh check. The separate rules for manual transcriptions, retained original captures and
  official-authority election results remain in SOURCE_POLICY.md. None of these paths permits
  access-control bypass or unauthorized redistribution.

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
- The published guide is generated from one publication view model.
- Reproducibility tests use an explicit build timestamp or `SOURCE_DATE_EPOCH`.
- GitHub Releases, rather than normal commits, carry versioned publication bundles.
