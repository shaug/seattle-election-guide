# Optional voting-address lookup (#657)

The Ballot dialog combines reviewed precinct matches and canonical address
suggestions in one field with labelled rows, without modes or an external finder.
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

## Failure and privacy boundaries

Explicit candidate selection, PointAddress scope, exact current site data and one
consistent supported city/precinct/district result are all required. Typed text,
a first suggestion, a score100 or a nearest point never suffices. Approximate,
partial, unit-unresolved, unsupported, boundary, contradictory, malformed or
truncated results leave direct entry available. A clearly selected canonical
street/building address is not verification of any originally typed unit.

Bounded before/after metadata checks reject detected City/precinct identity drift;
the exact tuple is checked for each site. This is not a transactional/atomic
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

Draft address text, suggestion identifiers, points and responses are ephemeral and
cleared on dialog close/history/re-edit. A committed canonical address label may
remain only in the current page memory for its applied precinct; Cancel preserves
it, while clear/history/reload/navigation discard it. Restored choices use the
precinct name, never a saved address. Address text, points and provider identifiers
never enter SEG URLs, storage, logs or analytics. Only Select commits the existing precinct draft through the
existing router/store. Cancel/Escape and stale responses cannot commit it.
