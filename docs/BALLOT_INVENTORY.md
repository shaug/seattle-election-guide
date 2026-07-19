# Seattle ballot inventory

The canonical inventory for the August 4, 2026 primary is
`data/normalized/wa-2026-primary-inventory.json`. It contains 70 races and 163 ballot choices:

- 31 federal, state, county, and City of Seattle candidate contests;
- one City of Seattle ballot measure; and
- 38 contested Democratic precinct committee officer races in Seattle precincts.

The official Republican PCO file contains no Seattle-prefixed contests. That zero-result check
is preserved in the inventory rather than silently omitted. PCO races are part of the complete
ballot universe but have `publication_eligible: false`; the endorsement guide's core purpose is
not to recommend party officers.

## Geographic filter

The inventory starts with King County Elections' official candidate lists and composite sample
ballot. It does not start with endorsement publications.

A contest is included when it is:

1. statewide or King County-wide;
2. assigned to a congressional, legislative, or County Council district that the official
   current King County map shows intersecting Seattle;
3. a City of Seattle or Seattle City Council District 5 contest or measure; or
4. a PCO contest whose exact precinct is mapped to Seattle in King County's official current
   precinct crosswalk.

The intersecting major districts are:

- Congressional Districts 7 and 9;
- Legislative Districts 11, 32, 34, 36, 37, 43, and 46; and
- Metropolitan King County Council Districts 2, 4, and 8.

County Council District 4 has no contest in the official August primary files, so it is modeled
as an intersecting jurisdiction without a race. The Northeast District Court contest is not
included because that electoral district does not intersect Seattle. The configuration and
canonical records cite the exact official files and maps supporting these decisions.

## Reproduce the import

The repository retains privacy-stripped, hash-pinned extracts containing only the official
fields consumed by the importer. It also retains a Seattle-only extract of King County's
official precinct crosswalk. These files contain no candidate contact, mailing, or submission
fields, so a fresh checkout can reproduce the canonical inventory after upstream files change.
The crosswalk extract contains official `PrecinctName` rows with a nonblank
`SeattleCouncilDistrict`, joined to the workbook's `CityCodeKey` entry `SEA = Seattle`.

```bash
uv run election-guide inventory import \
  --config config/elections/wa-2026-primary-inventory.yaml \
  --candidates data/extracted/official/king-county-2026-primary-candidates.csv \
  --pco-democrats data/extracted/official/king-county-2026-primary-pco-democrats.csv \
  --pco-republicans data/extracted/official/king-county-2026-primary-pco-republicans.csv \
  --precinct-crosswalk \
    data/extracted/official/king-county-2026-seattle-precinct-crosswalk.csv
uv run election-guide inventory validate \
  data/normalized/wa-2026-primary-inventory.json
```

The source manifest records both each official raw artifact hash and each retained safe-input
hash. `inventory extract` verifies the raw King County candidate and PCO CSV hashes before
removing unused personal and contact columns. A source refresh requires a reviewed manifest,
safe-input, and canonical-data diff rather than an unnoticed live-data change.

## Canonical guarantees

Validation rejects:

- duplicate source, jurisdiction, race, or ballot-choice IDs;
- references to missing sources, jurisdictions, parents, or elections;
- jurisdiction cycles;
- a candidate or ballot option attached to a different race;
- duplicate source selectors that would import one official contest as two canonical races;
- a PCO precinct absent from the official Seattle crosswalk;
- a candidate race with ballot options, a measure with candidates, or an empty race;
- duplicate ballot order within one race; and
- source files whose contents differ from the recorded hash; and
- coverage counts that do not reconcile to records citing the checked source.

Every election, jurisdiction, race, candidate, and ballot option cites at least one official
source. Race records keep district, office, position, display name, and official display aliases
as separate fields so later endorsement matching does not depend on lossy string parsing. Race
and ballot-choice records also retain exact CSV selectors and sample-ballot page locators.
