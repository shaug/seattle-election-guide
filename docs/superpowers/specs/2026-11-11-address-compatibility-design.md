# Address metadata compatibility (#746)

Scott authorized a resilient correction after two schema-clock rejections, rather
than repeated pin refreshes. This design is the coordinator's implementation
choice under that scope; it changes no UI, provider or address transmission.

## Evidence and approaches

The current public City Hall case is rejected before geocoding solely because
ADDRESS `schemaLastEditDate` differs. The same adapter with the current context
resolves SEA 34-3230; all three complete metadata responses are stable across that
operation. The current 45-field hash differs from November 4. Historical full
metadata is unavailable in the inspected retained incident scope: this is not
evidence that only clocks changed or that all fields remain equal.

Continuing clock pins repeats the reported outage. Removing the clock check
without validating semantics leaves important assumptions implicit. Validate only
the consumed metadata contract instead, for all three layers. This also handles
benign City/precinct schema churn while retaining their election-bound DATA pins.
Do not replace the clock with a complete-field-array hash.

## Runtime contract

- Keep the fixed County/Esri endpoints, admitted `serviceItemId`, and actual layer
  IDs: CITY 0, PRECINCT 655, ADDRESS 0.
- CITY and PRECINCT remain Polygon layers; ADDRESS remains Point. The reviewed
  native spatial reference is WKID 2926; a supplied latest WKID must agree.
  A coordinate-system change needs review because it changes geometry meaning.
- Require Query capability, JSON support and a safe integer `maxRecordCount` at
  least 20. City/precinct must support the requested Intersects relationship.
  Require standardized queries for the adapter's escaped literal SQL predicate.
- Require exactly one definition for each consumed field, with its expected
  type. CITY uses string CITYNAME/JURIS. PRECINCT uses string VOTDST, NAME,
  CONGDST, LEGDST, KCCDST and SCC. ADDRESS uses GUID SITEID and string ADDR_FULL,
  ZIP5, Building and Unit. Request only these five ADDRESS fields.
- Ignore field aliases, array order, indexes, extra unused fields and compatible
  schema clocks. Do not require all 45 definitions to remain identical.
- Keep recorded schema epochs in the existing payload as provenance. Provider
  schema-clock values or their absence do not define compatibility. Require
  well-formed observed DATA identities. CITY/precinct DATA must still equal the
  admitted election-specific bindings. ADDRESS DATA may change between lookups,
  but must remain equal before and after one resolution.
- Apply the same semantic checks before and after resolution. Retain complete
  bounded response checks, exact canonical address/unit/site validation, finite
  declared-4326 site geometry (both collection and any per-point declaration),
  actual Seattle intersection, and one consistent
  catalog precinct/name/all-district tuple. Reject malformed consumed site values.
- Preserve request count, deadlines, byte bounds, no retries, anonymous form POST,
  metadata GET, no-store/referrer/credential controls, cancellation and ephemeral
  state. Only the selected precinct may reach existing URL/storage owners.

## Tests and evidence

Use literal offline metadata fixtures to show clock, alias, index, order and extra
field churn resolve; require RED tests for missing/duplicate required fields,
wrong types/items/layers/geometry/SR, missing query support, insufficient response
limits, changed City/precinct DATA and ADDRESS data changing during resolution.
Exercise compatible and incompatible changes at the after-read boundary too.
Existing exact-site, unit, ambiguity, privacy and browser tests remain required.
Run the changed adapter against one public civic case using the originally served
binding, retaining actual before/after metadata and response identities.

## Limits and monitoring

Metadata does not establish that provider data is correct, detect a provider that
changes data without updating its identity, or prove an atomic multi-service
snapshot. Strict site and catalog tuple checks reduce those risks; one civic case
does not establish universal address coverage, voter eligibility or device/CORS
acceptance. Bounded responses can still reject very large benign metadata.

Existing hosted probes validate manifests, assets and routes, and offline address
tests substitute provider responses. Neither exercises this live external lookup.
The source-link schedule checks registry links, not this functional flow. A narrow
follow-up could run the same adapter with one public civic address against the
actual served binding and alert on failure, without updating pins or storing
private addresses. No new monitor, schedule or collector is added here.

## Delivery

`bec1ec1` and its successful full are retained pin-refresh prototype history.
Restore the original recorded ADDRESS epochs in ordinary additive work so the
final behavior demonstrates compatibility without another clock refresh. Amend
ADDRESS_LOOKUP, FRONTEND, ARCHITECTURE and the owning issue alongside the rule.
Require final-head focused/full/repro/readiness/canonical/CI/candidate inspection
and normal release/live verification. Issue746 preparation currently stops on
the different owner of main's unpublished PR741 request; never bypass that rule.
