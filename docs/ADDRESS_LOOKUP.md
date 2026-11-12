# Optional voting-address lookup (#657)

The Ballot dialog combines reviewed precinct matches and canonical address
suggestions in one field with labelled rows, without modes, plus a compact county precinct-search information link.
It can resolve a reader-selected canonical street/building address
to the reviewed November2026 precinct catalog. It does not verify voter registration,
unit occupancy, omitted apartments or the reader's complete official ballot. Direct
precinct entry remains available, including away/overseas and when lookup fails.

Scott approved this specific transmission on October28,2026 after independent
adversarial review: typed text goes to King County GIS; the selected canonical
address and site coordinates go to County-maintained Esri layers. SEG persists
only its existing election-specific precinct. No device location, World geocoder,
account/token, paid service, SDK or SEG backend proxy is used.

## Reviewed services and evidence

- [County Address Points locator](https://gismaps.kingcounty.gov/arcgis/rest/services/Address/Address_Points_locator/GeocodeServer): suggest and explicit selected-candidate resolution. The compiled locator build date was not exposed. Its point is not used for final intersections.
- [Current addressable sites](https://services.arcgis.com/Ej0PsM5Aw677QF1W/arcgis/rest/services/ADDRESS_POINT_642/FeatureServer/0): exact canonical ADDR_FULL and ZIP5, complete bounded site results and declared4326 point geometry. Address-site refreshes are distinct from polygon versions.
- [Incorporated city areas](https://services.arcgis.com/Ej0PsM5Aw677QF1W/arcgis/rest/services/CITY_AREA_448/FeatureServer/0): actual Seattle/SE intersection, not a postal city label.
- [Reviewed March2026 major-district union](https://services.arcgis.com/Ej0PsM5Aw677QF1W/arcgis/rest/services/FindMyDistricts_March2026/FeatureServer/655): exact precinct code/name and congressional, legislative, county-council and Seattle-council assignments must match the published catalog.

`config/elections/wa-2026-general-address-lookup.json` records separately reviewed
item/data/schema identities and the catalog hash. Independent review on October28
found all1,020 code/name/assignment tuples equal the shipped catalog. Edit times
are not legally certified November3 effective dates or voter ballot-part guarantees.
Current public civic fixture responses and their hashes are retained under
`tests/fixtures/address/public-civic.json`; they are not residential voter evidence.
Recorded schema edit epochs retain observation provenance. They are not the
runtime compatibility test: the adapter checks the layer contract it consumes.

### Reviewed ADDRESS context refresh (#691)

The November 4 UTC observation (November 3 Pacific) found a newer ADDRESS schema
identity on the same service item. The delegated reviewer compared all 45 complete
field definitions and the remaining metadata contract, then exercised the unchanged
adapter on the public civic case. The 11 successful requests resolved `SEA 34-3230`;
each layer's complete before/after metadata responses were equal. Only the ADDRESS
recorded data and schema epochs were refreshed. City/precinct identities and the
entire reviewed catalog remain unchanged.

The [structured review record](../data/review/geography/wa-2026-general-address-context-2026-11-04.json)
separates the actual retrieval, delegated review and later recording clocks, and
retains official URLs, response hashes and scope limits. Raw response bodies,
headers, forms and provider suggestion keys remain private. The earlier October 28
evidence is preserved. This bounded civic observation is not universal address
coverage, an atomic GIS snapshot or evidence of a deployed repair.

The original production-binding regression used retained responses offline and
rejected changed schema clocks. Issue #746 supersedes that clock comparison with
the semantic checks below. Item identity, exact-site, unit, Seattle and
precinct/district checks remain required.

### Schema-clock rejection and retained prototype (#746)

On November 12 UTC (November 11 Pacific), the published November 4 ADDRESS binding
rejected another schema change before geocoding. The same service item now reports
data/schema identity `1794228994534`. Review of the current field/query/geometry
contract and an unchanged-adapter City Hall resolution tested a prospective ADDRESS
context refresh. All 11 requests succeeded, resolving `SEA 34-3230`, with whole metadata
responses equal before and after. City/precinct identities and the catalog stay pinned.

The [current review record](../data/review/geography/wa-2026-general-address-context-2026-11-12.json)
and separate current civic fixture retain the actual observations. The complete
current field-array hash differs from the historical record; no whole old/new field
array equality is claimed. The current civic site differs only in an unused
`OBJECTID`; its exact site identity, geometry and district result remain equal.
That pin-refresh prototype and its original tests remain historical evidence.
Scott subsequently requested resilience to compatible metadata changes. The final
implementation retains the original recorded ADDRESS epochs and checks the consumed
contract instead. The prototype observation does not establish universal coverage
or a deployed fix.

### Semantic compatibility (#746)

All three layers must retain their reviewed service-item identity, expected layer
ID (`0`, `655`, `0`), geometry type and native spatial reference (`2926`, with any
`latestWkid` agreeing). They must support Query, JSON, standardized queries and at
least the requested 20 records. City and precinct metadata must declare Intersects
in an array of supported spatial relationships.

Each consumed field must occur exactly once with its expected type: city
`CITYNAME`/`JURIS`; precinct `VOTDST`/`NAME`/`CONGDST`/`LEGDST`/`KCCDST`/`SCC`; and
ADDRESS `SITEID` (GUID), `ADDR_FULL`, `ZIP5`, `Building` and `Unit` (strings).
ADDRESS queries request only those five fields. Field order, aliases, indexes,
unused fields and schema edit clocks do not determine compatibility; there is no
whole-field-array hash pin. Missing, duplicated or mistyped required fields fail
closed.

City and precinct data epochs stay bound to the reviewed catalog. ADDRESS data
may refresh between lookups, but every layer's data epoch must be well formed and
remain unchanged between the observations around one resolution. The full consumed
metadata contract is checked both times. Returned address collections and any
per-point spatial-reference declarations must consistently identify `4326`.

These checks tolerate compatible metadata churn without accepting a different
service, coordinate meaning, boundary dataset or consumed response shape. They
cannot establish an atomic snapshot, detect a provider misreporting unchanged data
epochs, or certify every address. Response limits, network failures and incompatible
contracts can still make lookup unavailable; direct precinct entry remains available.

The [separate compatibility observation](../data/review/geography/wa-2026-general-address-compatibility-2026-11-12.json)
used the changed adapter with the original published binding: all 11 anonymous
public civic requests succeeded and resolved `SEA 34-3230`. Each layer's complete
metadata response matched before and after. The actual executed module bytes were
preserved; this development observation does not claim deployed browser acceptance.

## Failure and privacy boundaries

Explicit candidate selection, PointAddress scope, exact current site data and one
consistent supported city/precinct/district result are all required. Typed text,
a first suggestion, a score100 or a nearest point never suffices. Approximate,
partial, unit-unresolved, unsupported, boundary, contradictory, malformed or
truncated results leave direct entry available. A clearly selected canonical
street/building address is not verification of any originally typed unit.

Bounded before/after metadata checks reject incompatible layer contracts, changed
service items, unreviewed City/precinct data epochs and data changing during a
resolution; the exact tuple is checked for each site. This is not a transactional/atomic
snapshot guarantee. No whole polygon downloads or automatic latest-year switch
occur. New general artifacts may retain their own pinned capability; primary,
legacy and nonmatching capabilities make no requests. Old artifacts are unchanged.

Address-bearing requests are debounced and bounded anonymous form POST; fixed,
address-free layer metadata uses GET. Both use omitted credentials,
no referrer and client no-store. There is no retry loop, bulk lookup or fallback
provider. Service errors, timeouts, CORS/offline and credential/cost demands fail
closed. No published quota or SLA was established. The observed address-feature
POST response advertised public,max-age=30,s-maxage=30; provider logs/retention are
undocumented. Client controls cannot promise zero provider caching or retention.
King County's [terms](https://kingcounty.gov/en/dept/kcit/data-information-services/gis-center/about/terms-conditions-copyrights)
permit nonsale use of county-owned information subject to third-party limits and
as-is/no-warranty conditions; they are not an unlimited traffic entitlement.

Address text is only a lookup aid. Draft text, suggestion identifiers, points and
responses are ephemeral and cleared on Select, dialog close, history or re-edit.
The applied summary and reopened editor always show the resolved precinct, exactly
as direct precinct selection does. Cancel preserves that applied precinct; clear
removes it, and history/reload/navigation restore only precinct identity. Address
text, points and provider identifiers never enter SEG URLs, storage, logs or
analytics. Only Select commits the existing precinct draft through the existing
router/store. Cancel/Escape and stale responses cannot commit it.

## Prefix suggestions and stable dialog (#657 revision, October 28)

SEG sends numeric-only and street-word prefixes through the same three-character
threshold and 300 ms debounce; a space is not an implementation prerequisite.
In the bounded public City Hall diagnostic, the approved provider returned zero
suggestions for `600` and three for `600 4th` (both HTTP 200). That observation
explains this example's context sensitivity; it does not establish that every
numeric prefix is unsupported or certify a private address. Provider responses
remain private diagnostic evidence, separate from product logs and factual review.
Canonical selection, collection rejection and exact geography validation are unchanged.

Suggestions overlay the content below the unified field inside a stable, viewport-bounded
dialog. Long lists scroll independently; visual-viewport resize/offset changes keep
it within the visible area. Loading, empty/error and option-selection announcements
remain, without result counts or instructions to narrow the query. Physical phone
keyboard behavior still requires actual device acceptance; emulated viewport geometry
and native browser keyboard/pointer tests do not claim that certification.

The modal's upper-right circled-i link reuses the historic county precinct-map
URL and opens a separate tab with `noopener noreferrer`. It has an accessible
purpose label and visible keyboard focus; its static destination never receives
typed text, selected-address details or SEG query state. This replaces the former
text finder link without adding a mode or changing address transmission/admission.

## Recurrence and monitoring limits (#746)

Hosted production checks cover routes, assets and published static payloads; they
do not execute a live address lookup. Browser tests use retained provider fixtures,
and the scheduled source-link check tests registry URLs rather than this functional
flow. Compatible-contract regressions prevent the known clock-rejection mechanism
from returning, but those checks cannot discover every live provider change.

A separate future monitoring change could exercise one public civic address with
the actual served binding and alert on failure. It would need its own scope and
traffic policy; it must not collect private addresses or mutate pins automatically.
Issue #746 adds no monitor, schedule or automatic acquisition.
