# Source panel sensitivity implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task by task. Steps use checkbox syntax for tracking.

**Goal:** Implement issue [#65](https://github.com/shaug/seattle-election-guide/issues/65) with deterministic exclusion reports and clear voter-facing interpretation, using the methodology merged in PR #569.

**Architecture:** Share prepared canonical scoring inputs and the existing race scorer between the audited consensus and exclusion scenarios. Publish the sensitivity report separately, project compact display values into the publication model, and render those values without browser-side analysis. Preserve historical publication readers with an explicit new publication schema.

**Tech Stack:** Existing Python, Pydantic, exact `Fraction` arithmetic, canonical JSON/CSV, Jinja, lit-html, and repository test/build tools; no new dependencies.

**Spec:** [Source panel sensitivity methodology](../specs/2026-10-18-source-panel-sensitivity-methodology-design.md).

## Global constraints

- Policy ID is `source-panel-sensitivity-v1`; report schema starts at `1.0`.
- Material leading-share change is at least `1/10`; narrow lead margin is at most `1/10`; majority requires a share strictly greater than `1/2`.
- Source exclusions cover every affirmative eligible source; category exclusions use `reporting_category_id` and require at least two contributing categories; groups use direct registered membership with at least two eligible members and one contributor.
- Every scenario starts from the same baseline; comparison and ineligible sources never enter the counted panel; retain duplicate exclusion sets under distinct scenario IDs.
- Preserve canonical tie-first resolution, exact splits, non-endorsement/missing semantics, the review gate, and baseline consensus bytes.
- JSON and CSV must describe every scenario and exact delta, including source membership and skipped category/group reasons.
- Prominent warnings require a material scenario; stable/tied/insufficient labels never imply probability, statistical confidence, or candidate quality.
- Analyze all publication races; customized source selection suppresses the overview's audited sensitivity warning, while race-page audit details remain labeled All sources.
- Existing archives remain readable. No deployment, tracker transition, source-panel change, or methodology threshold adjustment is part of implementation.

## Review focus

- A coherently altered report must fail recomputation against canonical inputs and approved policy, even after its hashes are rewritten; Task 2 owns this test.
- A category containing non-endorsers must remove their membership rather than turn them into missing coverage; Task 2 owns this test.
- A historical publication without sensitivity must remain readable, while a new publication missing its required analysis must fail; Task 3 owns these tests.
- Customized-source rerenders and reset must hide and restore the same server-authored warning without deriving state from the DOM; Task 4 owns this browser/markup-parity test.
- A declared new-format release must fail if either sensitivity artifact is absent, even when artifact inventories are rewritten; Task 3 owns this release verification test.

### Task 1: Share prepared canonical scoring inputs

**Files:** Modify `src/election_guide/scoring/engine.py`; verify `tests/test_scoring.py` and existing publication/personalization tests.

**Interfaces:**

- Consumes the existing validated `CanonicalDataset`, `ScoringConfiguration`, explicit timestamp, and `allow_unresolved` flag.
- Produces `prepare_scoring(dataset, configuration, *, computed_at, allow_unresolved=False) -> ScoringContext` and `score_race(context, race, *, excluded_source_ids=frozenset()) -> RaceConsensus`.
- `ScoringContext` carries the canonical dataset/configuration, prepared effective records/review context, per-race endorsements and eligible sources, component hashes, and timestamp. Existing `score_dataset(...) -> ConsensusReport` keeps its signature and bytes.

- [ ] Record the base's existing scoring/publication/personalization test result and a canonical consensus-byte digest.
- [ ] Extract preparation and reuse the same race allocation/state logic; compute eligibility once per source, then reuse it across scenarios. Reject exclusion IDs outside a race's eligible consensus set.
- [ ] Verify the same existing tests and baseline digest. This task is a behavior-preserving extraction; it uses the preservation evidence exemption.
- [ ] Commit the extraction with its focused validation evidence.

### Task 2: Compute and validate the complete sensitivity suite

**Files:** Create `src/election_guide/scoring/sensitivity_models.py`, `src/election_guide/scoring/sensitivity.py`, `tests/test_sensitivity.py`, and fixture support under `tests/` as needed.

**Interfaces:**

- Consumes Task 1's prepared scorer and a revalidated canonical `ConsensusReport`.
- Produces strict `SensitivityPolicy`, `SensitivitySnapshot`, `SensitivityScenario`, `RaceSensitivity`, and `SensitivityReport` models.
- Produces `build_sensitivity_report(dataset, consensus, *, git_commit, policy=None) -> SensitivityReport` and `validate_sensitivity_report(report, dataset, consensus, *, policy=None) -> SensitivityReport`; validation recomputes the full report rather than trusting embedded hashes.
- The policy is a frozen, machine-readable value embedded in the report, with all scenario/skip rules, materiality thresholds, and classification/reason priorities. There is one reviewed version, with no outcome-specific tuning interface.

- [ ] Write public-surface tests for the spec's five worked synthetic examples and observe their failure before implementing the new API. Example assertions:

  ```python
  assert result.classification == "narrow_but_stable"
  assert result.baseline.leading_margin == "1/10"
  assert result.material_scenario_ids == []
  ```

- [ ] Implement deterministic scenario/skip enumeration in canonical race and family/target order, scoring each exclusion from the original prepared inputs.
- [ ] Publish complete snapshots, population IDs, official-choice vectors, exact signed deltas, changed fields and IDs, material reasons, grade-boundary changes, primary classification, and all material scenario IDs/kinds.
- [ ] Add and run the spec's tied, insufficient, one-source split, no-endorsement/missing, threshold-boundary, grade-only, district/comparison eligibility, group non-transitivity, duplicate-set, sole-category, whole-exclusion, and exceptional-review cases.
- [ ] Add and observe failing tampering tests, then enforce full canonical-input/policy validation, complete scope/enumeration, and repeatable bytes. Include null-versus-zero deltas and an all-empty scenario suite.
- [ ] Verify the new tests plus the canonical scoring tests and baseline-byte preservation; commit.

### Task 3: Publish auditable artifacts and versioned display data

**Files:** Create `src/election_guide/publication/sensitivity.py`; modify `publication/builder.py`, `publication/models.py`, `release/comparison.py`, and affected publication/release/hosting tests.

**Interfaces:**

- Consumes Task 2's validated report.
- Produces presentation models `SensitivityDisplay` and `SensitivityScenarioDisplay`, `sensitivity_display(dataset, report) -> dict[str, SensitivityDisplay]`, and `sensitivity_scenarios_csv(report) -> bytes`.
- Adds `PublicationRace.sensitivity` and the publication methodology's sensitivity policy, optional only for historical schemas. New schema `1.15` requires them; accepted earlier schema versions remain readable.
- Adds `sensitivity.json` and `sensitivity_scenarios.csv` to new publication bundles, manifest hashes, and new-format release verification. The report's identity includes dataset, registry, panel, scope, scoring, baseline bytes, approved policy, timestamp, and publication revision.

- [ ] Write failing publication tests for deterministic sidecars, complete JSON/CSV deltas and empty CSV headers, summary columns, canonical baseline equality, and consistent view-model projection.
- [ ] Build the report once per publication and project compact, preformatted display rows/summary; preserve full audit data in sidecars rather than copying every audit snapshot into browser payloads.
- [ ] Extend `race_summary.csv` with policy ID, classification, tested/material counts, and affected scenario kinds; add corresponding validation checks and provenance bindings.
- [ ] Add failing new-schema completeness, old-schema readability, report/summary tampering, and missing-sidecar release tests; implement the versioned requirements without altering immutable historical artifacts.
- [ ] Verify publication, scoring, release-artifact and hosting compatibility tests; commit.

### Task 4: Present source checks on existing voter pages

**Files:** Modify `rendering/context.py`, `rendering/payload.py`, `rendering/templates/guide-card.mjs`, `guide.html.j2`, `race.html.j2`, the relevant existing page stylesheet, generated payload declarations, and affected Python/Node/browser parity tests and enforcement inventories.

**Interfaces:**

- Consumes Task 3's preformatted summary, material flag, scenario rows and target display names. Audit IDs remain provenance; browser-addressed sources/categories use existing transport codes.
- Adds a nullable, server-authored warning to the guide's race display payload and foot view. Customized mode yields no warning; audited mode/reset uses the original published value.
- Renders an All sources audit section on the existing race page, including a compact summary, one material warning when applicable, and accessible disclosure of every tested scenario and skip reason. Details link to methodology and machine-readable exports.

- [ ] Write failing tests for material-only overview warnings, quiet stable/narrow labels on race pages, complete/tied/insufficient disclosures, and no sensitivity claim for legacy publications.
- [ ] Implement the shared server/client foot markup with preformatted copy, and static race-page audit details that stay explicitly All sources while the live selection changes.
- [ ] Add and observe a failing customized/reset test and markup-parity coverage, then implement warning hide/restore from payload state. Use the existing differ/neutral design families and the current shared templates.
- [ ] Regenerate payload declarations, update any client schema version required by new required payload fields, and register genuine new mirrors/shared names without raising any ratchet.
- [ ] Verify focused Python rendering, Node parity/lens behavior, and narrow-width/keyboard browser checks; commit.

### Task 5: Document and verify the complete feature

**Files:** Update `docs/SCORING.md`, `docs/PUBLICATION_EXPORTS.md`, `METHODOLOGY.md`, `rendering/templates/about.html.j2`, and relevant schema/design documentation. Preserve the merged methodology spec as the preregistered policy record.

**Interfaces:** Consumes the finished scoring/export/display contracts from Tasks 1–4; produces current methodology, acceptance evidence, and a reviewed implementation PR.

- [ ] Document actual scenario rules, exact thresholds, canonical semantics, exclusions/skips, classes and limitations, export identities, and compatibility behavior. Avoid “panel” in voter-facing prose outside audit metadata.
- [ ] Run focused tests and static checks, then `make check`, retaining the complete log and exact candidate identity. Reconcile every authored #65 acceptance criterion against source-conforming evidence.
- [ ] Commit, then run `make check-release-reproducible` on the clean candidate. Inspect responsive rendered output and actual warning/disclosure behavior; record screenshots or geometry/behavior evidence required by the spec.
- [ ] Delegate the complete committed candidate to repository-owned `review-fix-loop` with `publication.policy: local_commit`, using fresh read-only three-lens review and the exact spec/issue/evidence. Resolve only material in-scope findings and rerun affected gates after changes.
- [ ] Apply the repository publication-size gate, open the focused PR with `Refs #65`, attach it, and hand its lifecycle to `babysit-pr` under `ready_to_merge`. Wait for required CI and review gates; merge and tracker transition remain separate user actions.
