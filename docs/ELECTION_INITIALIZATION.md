# Election initialization

Future elections begin with one offline seed, not a copy of the 2026 primary inventory. The seed
declares election identity and scope, stable local jurisdiction and race IDs, and explicit versions
for the source panel and scoring policy. It contains no candidates or ballot choices and performs no
network collection.

The repository fixture models a municipal general election distinct from the 2026 primary:
`tests/fixtures/initialization/wa-2027-seattle-general.yaml`. Initialize it with:

```bash
uv run election-guide election init \
  tests/fixtures/initialization/wa-2027-seattle-general.yaml \
  --output build/initialization/wa-2027-seattle-general.json

uv run election-guide election validate \
  build/initialization/wa-2027-seattle-general.json
```

Initialization writes canonical JSON atomically. Repeating the command with the same seed reports
`unchanged` and preserves identical bytes. A different seed cannot overwrite an existing output.
This makes the initialization file safe to review before any official ballot source is downloaded.

## Identity and version rules

Jurisdiction and race IDs are user-declared stable slugs. The canonical output adds `election_id`
to every jurisdiction and race, so their durable identity is the pair `(election_id, id)`. Reordering
seed entries does not change canonical bytes or IDs. Parent jurisdictions and race jurisdictions
must resolve inside the same election; duplicates, inverted parent kinds, hierarchy cycles, and
duplicate logical race identities fail validation. `target_jurisdiction_ids` binds the declared
scope to actual topology: municipal targets are cities, county targets are counties, statewide
targets are states, and mixed elections must represent at least two target levels.

`source_panel` and `scoring_policy` each require an ID, numeric version, and canonical repository-
relative JSON or YAML path. These references state the intended policy inputs without reading them,
fetching endorsements, or implying that either policy has already been frozen. Candidate and choice
fields are rejected at the initialization boundary; official inventory import is a later workflow.

`state_jurisdiction_id` binds the election's two-letter state code to one explicit state node. Every
city, county, or state target must be on the hierarchy that contains the single citywide Seattle
jurisdiction. In mixed elections, a target is represented only by a race at the target's level or a
documented subordinate district level; a county office cannot stand in for a statewide race.

## Offline inventory handoff

The initialized JSON is consumed directly by the family-neutral `canonical-ballot-csv` adapter.
This adapter expects an explicit versioned input manifest and a hash-verified CSV with these exact
columns: `race_id`, `choice_id`, `choice_type`, `official_name`, `display_name`, `aliases`,
`ballot_order`, `party_preference`, and `evidence_locator`. `choice_id` is an explicit stable local
slug, scoped by `race_id`; it is never derived from a person's name or an option label. An election
authority's format-specific extractor is responsible for producing those canonical offline rows;
the import command never fetches them.

The distinct 2027 fixture demonstrates the complete handoff:

```bash
uv run election-guide inventory import-initialized \
  build/initialization/wa-2027-seattle-general.json \
  --manifest tests/fixtures/initialization/wa-2027-seattle-general-ballot-input.yaml \
  --ballot-choices tests/fixtures/initialization/wa-2027-seattle-general-ballot.csv \
  --output build/initialization/wa-2027-seattle-general-inventory.json

uv run election-guide inventory validate \
  build/initialization/wa-2027-seattle-general-inventory.json
```

The adapter preserves the initialized race and jurisdiction IDs, verifies the ballot artifact hash,
uses the manifest's separately hash-bound configuration source for election, jurisdiction, and race
claims, and uses the ballot source only for choice claims. It emits stable race-scoped choice IDs
and the ordinary validated `Inventory` model used by normalization and scoring. This avoids routing
future elections through the 2026 King County candidate/PCO/crosswalk importer. Initialized imports
emit Inventory schema `1.1`; the committed 2026 inventory remains valid `1.0`, while the new version
explicitly carries the expanded future jurisdiction-kind contract.

The election type is `primary`, `general`, or `special`. `election_scope` separately identifies a
`municipal`, `county`, `statewide`, or `mixed` ballot, allowing the same initializer to cover the
future election families named in the project plan without embedding 2026-specific assumptions.
