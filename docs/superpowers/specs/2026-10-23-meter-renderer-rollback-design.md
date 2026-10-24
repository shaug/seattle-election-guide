# Meter renderer rollback

Scope: [#598](https://github.com/shaug/seattle-election-guide/issues/598).
Scott directly approved the exact pre-#605 two-CSS restoration on October 24,
2026, including rebuilding the primary overview. This public successor records
that approval and supersedes the frozen local preview spec's publication hold
for this exact scope. No redesign is authorized.

## Approved change

Restore these two files to their exact bytes at
`bea5e4edc5c50c985932b8ae5e123a39a0b51449`:

- `src/election_guide/rendering/templates/guide-race.css`
- `src/election_guide/rendering/templates/race.css`

Preserve current Meter v2, opening transitions, counts, percentages, source
membership, allocation arithmetic, dimensions, colors and interactions,
including touch inspection. Keep the current 929 general and 538 primary
decisions, all certified results, exports and historical evidence. Do not
restore retired percentage-only meters. The rollback is limited to the approved
border rendering; a whole-commit revert would undo unrelated work.

Later implementation transfers only the focused browser-test hunks that verify
the restored mechanism and both transitions. Preserve the #602 diagnostics
tests; do not restore whole test files or remove coverage to obtain a pass.

## Why the sequence has three stages

The primary overview and Updates are copied from an immutable archive. Primary
race pages are rendered from that archive's verified data using current code.
An entry in source YAML alone therefore cannot satisfy the served Updates gate
when race-page rendering changes. Two new immutable primary archives bridge the
history before the renderer changes and then deliver the rebuilt overview.

| Stage | Protected delivery | Primary behavior after acceptance |
| --- | --- | --- |
| A | Prepare the primary history entry and publish through the current-general workflow. | Primary `.6` pins, overview, Updates and race rendering remain unchanged. |
| Between A and B | Build, inspect, publish, download and verify archive 1 from the exact accepted A merged source. | No pin activation yet; existing primary remains served. |
| B | Restore the two CSS files and activate archive 1 in a protected PR. | Current code restores primary race-page borders; archive 1 supplies the preparation entry. Its copied overview still precedes the rollback. |
| Between B and C | Build, inspect, publish, download and verify archive 2 from the exact accepted B merged source. | Archive 2 contains the restored overview and accurate accumulated Updates. |
| C | Activate archive 2 in a protected PR. | The rebuilt primary overview joins the restored race pages. |

Preserve `2026-primary.6`, every earlier release/tag/asset identity and every old
Updates entry. Each new archive has its own new identity; neither existing nor
new archives may be overwritten. No future versions are reserved here.

## Current preparation boundary

The controller has accepted `2026-general.36` production from
`e85f694f9a3fedfd96a7707a12bd8279ed5d93d7` (tree
`fcfb9c9af2c2c719893d5a3f3adc3293dd1a741a`). This accepted M11 source is the
Stage A preparation and final comparison base. The normal local current-general
request is prepared and resolved as `2026-general.37` for #598. Fresh gates,
review, the private commit and protected delivery remain part of finalization.

The public spec, plan, delivery record and one primary Updates preparation entry
are prepared, together with that local request in the hosting configuration.
Primary `.6` pins stay unchanged; preparation publishes or reserves no version. The first source entry is dated October 24, 2026; it remains unserved
until archive 1 is selected in Stage B. Reconcile dates against actual Pacific
publication dates at finalization through protected source updates if needed.
The preparation text makes no claim that restoration is already deployed.

## Acceptance

Each final stage candidate requires fresh full required gates, canonical
repository review, protected CI and inspection of the exact candidate's notes,
data and rendering validation reports, and desktop/mobile screenshots. Each
merged stage requires independent automatic-release and production evidence.
Each new primary archive must be built twice from its exact clean accepted
source, compared, inspected, published, downloaded and verified before pins are
selected. Preserve all 929/538 decision records and unchanged export/data
semantics throughout.

Scott's approved scope does not substitute for those checks. Final production
must show the approved borders on general and primary race pages and the primary
overview at desktop and mobile sizes, with current interactions intact.
[#598](https://github.com/shaug/seattle-election-guide/issues/598) stays open
until Stage C production and visual acceptance. No gate, archive, merge,
deployment or visual completion is asserted by this preparation.
