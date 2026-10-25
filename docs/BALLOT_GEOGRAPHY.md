# Personal ballot geography (#608)

Membership determines which contests apply to a Seattle voter. It does not order
contests or sections; #609 owns that work. Source selection, source eligibility,
allocations, and consensus scoring do not depend on the voter's district.

Manual selection asks separately for congressional, legislative, county council,
and city council districts. A legislative district alone cannot establish the
other boundaries. Judicial jurisdictions remain independent membership questions.
Unanswered and unlisted districts retain uncertain contests with a confirmation
notice. A named district with no current contest is a valid, complete answer.

## Reviewed 2026 universe

`config/elections/wa-2026-ballot-geography.json` pins the normalized official
assignment extract, retained official city crosswalk, and dated reconciliation
record by SHA-256. Builds read these files offline. District choices come from
explicit assignment fields across all 1,020 Seattle precincts, independently of
which districts have races in the canonical inventory. Validation rejects changed
hashes, duplicate precincts, incomplete joins, and contradictory city assignments.

The official March 2026 combined district service, restricted to explicit Seattle
council assignments and joined exactly to the official Seattle precinct extract,
contains congressional districts 7/9, legislative districts 32/34/36/37/43/46,
county council districts 1/2/4/8, and city council districts 1–7. The dated record
is `data/review/geography/wa-2026-seattle-20261023.json`; it records URLs, native
capture manifests, joins, and access limitations.

This corrects two assumptions in the earlier inventory documentation: County
Council District 1 has Seattle assignments; LD 11 has none in this reviewed
extract. The canonical LD 11 records remain available for reference and audit.
An explicit outside-target membership rule omits them from Your ballot and a
notice in the expandable setup guidance explains the discrepancy. The inventory, endorsement matching,
and scoring inputs are preserved. Unknown major districts fail publication until
reviewed rather than becoming silently inferred options.

The fresh official workbook returned HTTP 403. No workbook access bypass was
used. Current official map text corroborates the reconciliation, but no visual
boundary inspection or exact voter ballot-style certification is claimed. Raw
JSON captures remain local-only under the evidence policy; the committed extract
contains normalized public geographic facts and no voter records.

## Later location lookup

An optional address/location resolver should populate the same independent
jurisdiction profile, show the resolved districts for confirmation, and retain
manual correction. Coordinates and addresses should not become source-selection
inputs. Provider choice, consent, retention, failure behavior, and boundary
versioning belong to that later scope; no live lookup occurs in this change.

The shared #607/#610 public-view selector owns uncontested-race visibility using
its full verified panel and existing configured confidence threshold. Source
preferences change displayed scores only. The membership contract projects race
rules to those public contest IDs while preserving every reviewed district option.
Membership matching and #609 ordering do not recalculate that visibility decision.
Revised rendering still requires direct human visual approval before publication.

## Primary archive activation

The accepted primary8 archive remains an immutable release with its accepted pins.
Hosting copies its overview HTML from that bundle; changing current publication
models or generating new detail pages does not add ballot setup to the copied
primary overview. A fresh primary render used for #608 review is a source preview,
not evidence of the currently served archive or permission to replace it.

Before activating revised primary UI, the sole delivery owner must prepare a new
immutable primary artifact, verify its overview, embedded client payload and
related public routes agree, and update the release identity and hashes through
the normal pin workflow. Preserve the existing archive and audit records. The
shared #607/#610 selector applies before geographic matching in the replacement;
no primary-specific confidence rule or source-selection override belongs here.
The revised images require direct visual sign-off before activation.
