# Voter ballot membership implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Show the contests applicable to a Seattle voter from manually supplied districts, retaining uncertain contests until setup is complete.

**Architecture:** Publish reviewed jurisdiction applicability alongside stable contest identifiers. A pure client matcher determines membership; shared setup controls collect a voter profile; Endorsements and Comparisons consume membership without changing their supplied section or contest order. A later location lookup supplies the same profile.

**Tech stack:** Existing Python/Pydantic publication builder, Jinja, ES modules, lit-html, Node tests, and Chromium integration checks. No added dependencies.

**Spec:** [Issue #608](https://github.com/shaug/seattle-election-guide/issues/608), including its manual-first scope and independent ballot-ordering boundary, approved in the conversation preceding this plan.

## Global constraints

- Membership never calculates section placement or sorts contests. Preserve incoming relative order.
- Use stable race and jurisdiction identifiers from reviewed inventory; no parsing of display labels or filter tokens.
- Include applicable contests without endorsements; explicitly amend the existing general-overview omission policy.
- Never label a partial profile as a complete ballot. Matching the publication inventory does not prove official inventory completeness.
- Leave the other chat's checkout and changes alone. This work uses branch `codex/608-voter-ballot` in an isolated managed checkout based on main at `5dde3f0c1e4d7b564d7c5d3644e7ba247dd51da5`.
- Location lookup, geocoding, section ordering, scoring changes, and inventory expansion are outside this implementation.
- Amend conflicting documented rules in this PR. Do not increase existing ratchet ceilings or allowlists or weaken checks.
- Run `make check` before proposing the implementation diff and `make check-release-reproducible` on the committed clean candidate before pushing.
- Default publication is a ready PR with a non-closing `Refs #608`; merging and closing the issue require separate authorization.

## Review focus

1. A district type can have no contest for the voter's district this election. An explicit “My district is not listed” selection must differ from “I don't know.”
2. Judicial districts with the same kind need not be mutually exclusive. Never group all judicial jurisdictions into a single choice.
3. A saved profile can become stale or corrupt, or browser storage can fail. Retain uncertain contests and explain when remembering fails.
4. Personalization, comparison rerenders, legacy filter URLs, and direct race links must not silently conceal applicable decisions or override membership.
5. Archived view models lack membership data. They must remain readable without guessing jurisdiction applicability from their labels.

## Task 1: Publish jurisdiction applicability independently of ordering

**Files:**

- Create `src/election_guide/publication/ballot.py` and `tests/test_ballot_membership.py`.
- Modify `src/election_guide/publication/models.py`, `builder.py`, `src/election_guide/rendering/payload.py`, and generated `templates/types/client-payload.d.ts`.
- Update relevant publication/schema and historical-artifact tests in `tests/test_publication.py`, `tests/test_client_payload_types.py`, and `tests/test_hosting.py`.

**Interfaces:**

- `build_ballot_membership(inventory: Inventory) -> BallotMembershipContract` publishes an election identifier, selectable jurisdiction groups, and one applicability rule for every publication-eligible race.
- `BallotMembershipContract` publishes reviewed IDs and labels, shared applicability, and the requirement a race needs resolved; it carries no section IDs or order keys.
- `PublicationViewModel.ballot_membership` is absent/null for historical models and populated in new builds. Guide and comparison payloads carry it. Unknown historical applicability disables setup with a visible explanation rather than assuming a match.

- [ ] Write tests asserting every eligible race has exactly one rule, shared jurisdictions use reviewed `contains_city`/`citywide` applicability, and rule generation never changes publication sections.
- [ ] Cover the two independent judicial jurisdictions in the current inventory, an unsupported jurisdiction kind, missing references, and archived publication models.
- [ ] Run the focused tests and observe failure before implementation.
- [ ] Implement the strict Pydantic contract and builder. Congressional, legislative, county council, and city council choices are independent groups. Present independent yes/no/unknown membership questions for intersecting jurisdictions that lack a reviewed mutually exclusive group; do not infer shared coverage merely from their names.
- [ ] Validate all race/jurisdiction references. Unsupported or insufficient mappings remain explicitly unresolved and prevent a “setup complete” claim.
- [ ] Publish available districts from the election's reviewed inventory. Support explicit membership outside a group's listed jurisdictions without inventing an official jurisdiction ID.
- [ ] Regenerate types with `make types`, rerun focused tests, and commit the contract change.

## Task 2: Resolve and remember a voter profile

**Files:**

- Create `templates/ballot-membership.mjs`, `ballot-profile-store.mjs`, and `ballot-setup.mjs` under `src/election_guide/rendering/`.
- Create corresponding `tests/js/*.test.mjs` files and a shared test profile fixture.
- Update `tests/js/support/module-guards.mjs`, its tests, and `docs/FRONTEND.md` together with the feature.

**Interfaces:**

- `resolveBallot(contract, profile)` returns membership (`applicable`, `inapplicable`, `unresolved`) keyed by race ID, missing requirements, and profile completeness. It never sorts, selects sections, or consults endorsement data.
- A versioned profile records each group choice as unknown, a reviewed jurisdiction ID, or explicitly outside the listed districts; independent membership questions record yes/no/unknown.
- `readBallotProfile(electionId)` and `writeBallotProfile(electionId, profile)` are asynchronous and report storage failure. Save profiles per election so changing boundaries or jurisdiction catalogs cannot silently reuse a prior election's assumptions.
- `wireBallotSetup(contract, onChange)` owns the setup region and calls `onChange` whenever the resolved profile or browse mode changes.

- [ ] Write pure matcher tests for full and partial profiles, distinct district kinds, shared races, independent judicial memberships, unknown/invalid selections, stale profiles, and explicit unlisted districts.
- [ ] Assert matching does not inspect or mutate supplied race/section ordering and produces the same membership under reordered input.
- [ ] Observe failing tests, then implement the pure matcher and profile admission.
- [ ] Implement one IndexedDB adapter for this versioned ballot profile. Keep the existing prohibition on localStorage, sessionStorage, and cookies intact. Explicitly amend the broader URL-only rule to permit this ballot-profile store; add checks confining IndexedDB ownership and persisted shape, including negative tests, without expanding an existing exception list.
- [ ] Test absent, corrupt, old-version, and invalid saved data; denied/unavailable storage; asynchronous load races against a newer user choice; and clearing/reloading a saved profile.
- [ ] Implement lit-html setup controls using native labeled selects and independent membership questions. Preserve focus and the server-owned live-region root.
- [ ] Provide “Your ballot” and “Browse all Seattle contests” modes plus review/change/clear actions. Starting setup selects Your ballot; unknown answers retain uncertain races. Browsing all does not silently discard saved districts.
- [ ] Link to the verified official resource: https://kingcounty.gov/en/dept/elections/maps/find-my-district . It offers precinct, county council, city council, legislative, and congressional district lookup; use its official voter-information resource for any additional membership question.
- [ ] Explain that setup matches contests in SEG's Seattle inventory and that the official ballot remains the completeness reference. Do not collect an address or request geolocation in this phase.
- [ ] Run matcher, storage, and setup tests and commit.

## Task 3: Apply membership consistently to election lists

**Files:**

- Modify `templates/guide.html.j2`, `guide-entry.mjs`, `guide-client.mjs`, and `guide-filters.mjs`.
- Modify `templates/compare.html.j2`, `compare-client.mjs`, and `compare-table.mjs`.
- Add shared setup markup/styles through existing Jinja/CSS composition; update `rendering/stylesheets.py` if a shared CSS part is introduced.
- Modify rendering/browser validation, publication overview policy, relevant Python/Node tests, and audited parity fixtures.
- Update `docs/DESIGN.md`, `docs/FRONTEND.md`, `docs/RENDERING.md`, `docs/PUBLICATION_EXPORTS.md`, and `DECISIONS.md` where their contracts change.

**Interfaces:**

- Endorsements and Comparisons receive the same resolved profile and membership statuses.
- List rendering excludes only `inapplicable` races, visibly identifies `unresolved` races, and preserves each page's supplied relative order.
- Direct race pages stay reachable and do not redirect merely because a device profile excludes their race. They remain reference pages, not ballot lists.
- Source editing and source-lens scoring retain their existing identity, URL, and scoring contracts.

- [ ] Write integration tests for retained shared races, excluded nonmatching districts, unresolved labels, cross-page persistence, and independent source selections.
- [ ] Cover stale legacy `filter` query parameters and comparison section fragments: ballot mode must show all applicable contests rather than inheriting an invisible section restriction. If a reader chooses a deliberate presentation restriction, state it visibly and never call that restricted list the complete ballot.
- [ ] Verify ballot membership consumes the shared #607/#610 public-view selector; uncontested races use the full verified panel and existing configured confidence threshold. Retain all district options and canonical audit records without a personalized visibility exception.
- [ ] Observe failing tests, then integrate setup and membership. Keep membership logic out of ordering and source-lens modules.
- [ ] Remove/replace the guide's scope-filter UI where it conflicts with ballot setup, without removing unrelated code merely because it lacks a caller. Preserve existing Full/Compact behavior; ensure any Contested/Differing view restriction is clearly described.
- [ ] Integrate comparison membership into its view-model rendering so column changes and fragment updates cannot restore excluded rows. Preserve the existing lazy takeover behavior when no profile is active.
- [ ] Test no-JS and unsupported-payload baselines, storage denial, direct race navigation, and a profile identifying no district-specific contests.
- [ ] Regenerate parity fixtures through their existing generators; verify Jinja/lit parity and generated types.
- [ ] Inspect desktop and mobile setup views for overflow, keyboard focus, labels, status announcements, and printable inclusion of the active ballot context.
- [ ] Run focused tests, `make check`, commit all intended changes, and run `make check-release-reproducible` on the clean tree.
- [ ] Run the repository review-fix-loop on the exact committed candidate, reconcile every #608 acceptance criterion with current evidence, and publish one reviewable PR if the publication size gate permits it. Do not merge or close #608.

## Execution notes

- Baseline: `make sync` succeeded. `uv run pytest tests/test_client_payload_types.py tests/test_publication.py -q` passed (31 tests) before implementation.
- Predicted publication shape: one coherent PR for manual ballot membership. Location lookup and ballot ordering remain separate initiatives. If the completed candidate is too broad for one reviewable PR, stop at the publication size gate with concrete split evidence rather than silently publishing a monolith.
- Repository inspection found another initiative's uncommitted changes in the primary checkout. No files there were modified by this run.

## October 24 policy amendment

Scott superseded the original uncontested-race exception: every view uses the
full verified panel and the existing configured confidence threshold. Selected
sources control displayed scores only. #607/#610 owns the single public visibility
selector; #608 consumes its public race IDs and preserves the complete district
catalog before applying geographic membership. #609 still owns ordering.

The previous 266af72 implementation and previews remain historical evidence,
not approval for revised behavior. Revised candidates require fresh validation,
review and direct visual sign-off through oversight. The separately approved
#598 exact meter rollback remains first; the sole delivery owner controls actual
accepted predecessors and every main/publication advance.
