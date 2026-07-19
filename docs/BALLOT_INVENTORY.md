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
4. a PCO contest whose official precinct name begins with `SEA `.

The intersecting major districts are:

- Congressional Districts 7 and 9;
- Legislative Districts 11, 32, 34, 36, 37, 43, and 46; and
- Metropolitan King County Council Districts 2, 4, and 8.

County Council District 4 has no contest in the official August primary files, so it is modeled
as an intersecting jurisdiction without a race. The Northeast District Court contest is not
included because that electoral district does not intersect Seattle. The configuration and
canonical records cite the exact official files and maps supporting these decisions.

## Reproduce the import

Download the three official CSV inputs to a local directory. The repository does not publish
them because the source files contain candidate contact and mailing fields that the canonical
inventory does not need.

```bash
curl --fail --location --output candidates.csv \
  https://aqua.kingcounty.gov/elections/candidatefiling/2026/2026-primary-candidates.csv
curl --fail --location --output pco-democrats.csv \
  https://aqua.kingcounty.gov/elections/candidatefiling/2026/2026-primary-pco-dems.csv
curl --fail --location --output pco-republicans.csv \
  https://aqua.kingcounty.gov/elections/candidatefiling/2026/2026-primary-pco-reps.csv

uv run election-guide inventory import \
  --config config/elections/wa-2026-primary-inventory.yaml \
  --candidates candidates.csv \
  --pco-democrats pco-democrats.csv \
  --pco-republicans pco-republicans.csv
uv run election-guide inventory validate \
  data/normalized/wa-2026-primary-inventory.json
```

The importer rejects inputs whose SHA-256 hash differs from the captured source manifest. A
source refresh therefore requires a reviewed configuration and data diff, not an unnoticed
live-data change.

## Canonical guarantees

Validation rejects:

- duplicate source, jurisdiction, race, or ballot-choice IDs;
- references to missing sources, jurisdictions, parents, or elections;
- jurisdiction cycles;
- a candidate or ballot option attached to a different race;
- duplicate ballot order within one race; and
- source files whose contents differ from the recorded hash.

Every election, jurisdiction, race, candidate, and ballot option cites at least one official
source. Race records keep district, office, position, display name, and official display aliases
as separate fields so later endorsement matching does not depend on lossy string parsing.
