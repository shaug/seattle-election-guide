# Seattle ballot inventory

## November 2026 general election

The canonical inventory for the November 3, 2026 general election is
`data/normalized/wa-2026-general-inventory.json`. It contains 52 races and 83 ballot choices:

- 48 federal, state, county, judicial, and City of Seattle candidate contests with 75 candidates;
- three statewide initiatives; and
- one City of Seattle ballot measure.

The retained canonical ballot CSV contains only ballot-facing names, order, party preference,
stable local IDs, and evidence locators. Its input manifest binds that file and the initialized
election configuration by SHA-256. The rows were transcribed from King County Elections' official
general-election candidate CSV and official ballot-measures list; contact and mailing fields from
the source CSV are not retained.

Reproduce and validate the import with:

```bash
uv run election-guide inventory import-initialized \
  config/elections/wa-2026-general.yaml \
  --manifest config/elections/wa-2026-general-ballot-input.yaml \
  --ballot-choices \
    data/extracted/official/king-county-2026-general-canonical-ballot.csv \
  --output data/normalized/wa-2026-general-inventory.json
uv run election-guide inventory validate \
  data/normalized/wa-2026-general-inventory.json
```

## August 2026 primary election

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

## Reviewed November2026 precinct projection (#608)

`config/elections/wa-2026-general-precinct-ballots.json` binds 1,020 reviewed
Seattle precincts to current major-district assignments and official city membership.
CD7/9, LD32/34/36/37/43/46, county council1/2/4/8 and Seattle council1–7 are
represented, including valid districts with no covered contest. Canonical LD11
records remain intact but match no reviewed Seattle precinct.

All Seattle precincts share statewide, countywide and citywide eligibility.
KCC1.12.050(B) makes District Court West citywide; RCW2.06.020(1)(a) makes
Appeals DivisionI District1 KingCounty. No judicial question is asked. Exact
sources, hashes, actual check dates and the accepted November-applicability
inference are in `data/review/geography/wa-2026-general-precinct-ballots.json`.
November3 is the target election date, not a claimed GIS effective date.

The31 fixture groups are source-composed expected sets over geographic combinations,
not official ballot styles or voter-specific samples. Each contains exact covered
IDs before and after candidate-only uncontested exclusion. The first set supplies
geographic membership before existing public eligibility; the second remains an
oracle for the default Contested view. An explicit All selection uses the full
geographic public set. Race mode does not change inventory or section order. The
countywide composite ballot is corroborating contest evidence, not a
precinct-specific ballot. On October27,2026, Scott approved shipping on the reviewed
1,020 official assignments, current declarations, all 52 mappings, 31 independent
exact-set checks, and that composite. He removed precinct-specific sample ballots
as a requirement, without creating a mandatory collection follow-up. This
supersedes the earlier sample-ballot release gate; its dated wording is retained
in DECISIONS.md. Actual end-to-end precinct/part/style comparisons remain
unperformed; this does not establish that such examples do not exist. Mapping,
admission, primary compatibility, and normal release checks remain required.
Primary is unsupported by this projection; future elections require new reviewed
evidence.

## November 2026 presentation order (#609)

`src/election_guide/publication/ballot_orders/wa-2026-general.v1.json` is the
reviewed, versioned presentation map for all 52 November inventory contests.
Its section/entry array order is authoritative for presentation; each entry
records the printed page, column (left=1, middle=2, right=3), and contest-box
ordinal in King County's 12-page official composite sample ballot. Box ordinals
include contests outside SEG and exclude instructions and heading blocks.

The supplied official PDF has SHA-256
`f1df968fe7093344a872eb22b9aaabc0a5dec3065f2b9448b7b72546381f572c`.
It was supplied by the user on October 26, 2026 (October 27 UTC), then all
12 rendered pages were inspected by the actual reviewer recorded in the map.
This custody is distinct from a successful county-host retrieval; the earlier
HTTP 403 is not erased or relabeled as a successful check. The map retains the
normal official URL, actual review timestamp and reviewer, and per-contest
visual locators without redistributing the PDF.

The publication builder rejects a missing map, duplicate section/contest IDs,
repeated or out-of-reading-order locators, a different election ID, and any
missing or unknown inventory contest. Validation covers the complete inventory
before publication eligibility or reader filters remove contests. A new contest
requires a reviewed map update; it is never silently appended or alphabetized.
No canonical race, choice, endorsement or scoring record is reordered or changed.

State measures lead; the State candidate section groups legislative districts
numerically, then senator and representative positions 1–2 within each district.
West Electoral District and Seattle Municipal Court are separate. The Seattle
transit measure follows municipal position 7. "State measures", "City of Seattle",
and "City of Seattle — measures" are SEG disambiguating headings: the ballot
prints "State" with initiative subtype headings and "City" with the jurisdiction
in contest titles. The Court of Appeals heading drops the ballot's "No." for
readability. Other headings retain the ballot wording with line breaks normalized.

Ordering is independent of #608 membership and of endorsement-source geography.
All existing source, eligibility, scoring and Races controls remain in force.
Other elections retain their existing section/sequence behavior until they have
an explicitly registered, reviewed election-specific map. The composite's other
county contests do not expand SEG's publication inventory or certify its coverage.
