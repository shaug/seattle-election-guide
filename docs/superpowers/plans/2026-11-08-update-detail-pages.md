# Individual election Updates pages — #677

Scott approved the retained index-link and election-scoped detail-page treatment. This plan executes that approval; the separate preliminary result-meter release is accepted before this branch is published.

## Design and boundaries

Keep the per-election authored Updates log and shared entry view. Schema 1.2 adds a persisted, reviewed `slug` and optional `redirect_from` aliases; legacy 1.0/1.1 publication models retain their serialized shape. Require safe lowercase ASCII hyphenated segments, reject missing/duplicate/reserved slugs and alias collisions, and preserve the original date/headline audit identity. Assign existing slugs once in source data; renderers never derive identity from prose, date or position. A future deliberate rename retains its old route as a permanent redirect, never another entry.

The index keeps all current text, dates, topics, filters and evidence. Its headlines link to `/e/{election}/updates/{slug}/`. The detail page uses the same shell and narrow measure, one headline H1, original date and labels, complete unchanged body/evidence, same-election Back links and topic links to the filtered index. It has no filter toolbar, sidebar or comments. Direct/no-JavaScript reading, canonical/social metadata, real 404s and deterministic route/assets remain required. Native history is tested before adding any state machinery.

Accepted archives stay immutable. Existing current-source Updates projection supplies the archived election's admitted public entries. Details remain outside the existing fact-page snapshot projection; no snapshot schema upgrade is needed. Hourly result publication must persist a new slug at entry creation, with stable same-entry recovery. No results/scoring/provider collection changes belong here.

## Execution

1. **Identity contract (TDD):** reject unsafe/missing/duplicate/reserved slugs and alias collisions; allow the same slug in different elections; retain legacy serialization. Add schema1.2 and stable route helpers. Migrate both authored logs without changing any existing field or audit identity. Update the hourly entry producer with deterministic creation-time identity.
2. **Shared rendering (TDD):** extend the common entry view; make index H2 headlines links and render a complete detail document with title/canonical/social metadata, topic links and safe evidence. Keep legacy index behavior. Verify headline/date/reorder edits leave URLs unchanged.
3. **Staging and routing (TDD):** emit all admitted details and intentional alias redirects from the one Updates projection; register exact public paths/assets and verify them. Cover current and archived elections, safe deep links and genuine unknown/malformed 404 behavior. Preserve immutable bundles and Updates snapshot identities.
4. **Browser journeys:** actual desktop/mobile render, no-JS/direct/reload, keyboard/focus and readable width. Filter the index, follow a real detail link, then native Back and verify the prior query, visible entries and scroll. Keep existing route ownership if native restoration works.
5. **Owning documentation and release:** amend DESIGN/FRONTEND/RESULTS as needed. Run affected tests/static checks, independent whole-branch review, then a coherent committed candidate and `make check`. Use normal fresh release preparation/admission/reproducibility/stage/Updates proof, a draft PR and hosted preview. Complete authorized delivery only after normal gates, verifying production index/detail and preserving original comments/metadata on issue closeout.

## Verification and limits

Keep original RED failures and before/after receipts. Check migrated data semantically against the base commit with only routing fields removed; retain a private old identity→slug map. Automated browser coverage is credited only to its actual desktop/mobile viewport platform; do not imply physical phone or spoken screen-reader testing. Formal GitHub APPROVED reviews need separate action-time confirmation.
