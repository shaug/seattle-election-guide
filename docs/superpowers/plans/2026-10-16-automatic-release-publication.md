# Automatic Verified Release Publication Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Deliver [#550](https://github.com/shaug/seattle-election-guide/issues/550): automatically publish, deploy, confirm, and retain evidence for a verified release after its reviewed PR merges.

**Architecture:** Extend the existing release builder and hosting verifier with a reviewed publication request and immutable candidate records. A serialized mainline workflow promotes one merged revision through publication, durable publication evidence, upload, and production confirmation; recovery retains the published canonical ZIP. Keep GitHub operations behind the existing CLI boundary and reuse the current bundle, rendering, and production contracts.

**Tech Stack:** Python 3.12, Pydantic 2, Typer, pytest, Git/GitHub CLI, GitHub Actions artifact v4 actions, pinned git-cliff 2.14.2 and Wrangler 4.149.0, existing Node toolchain.

**Spec:** [Approved design](../specs/2026-10-16-automatic-release-publication-design.md).

## Global Constraints

- Automatic publication and deployment follow merge; there is no final Publish action and no routine publication-switch toggle.
- `config/hosting/site.yaml` remains the authority for the selected current release version and archive composition. Workflows and supported current-release commands resolve it rather than carrying version literals.
- Reviewed ledger, canonical-dataset, and registry bindings are file-byte SHA-256 values. Panel and complete-registry semantic identities remain separate checks.
- The release tag, published current bundle, staged current bundle, upload commit, and expected production commit identify the same full merged revision.
- Use `queue: max` and `cancel-in-progress: false` for the complete mainline pipeline; PR CI remains parallel.
- Production confirmation has a 120-second deadline, at most one attempt per five seconds, request timeouts bounded by remaining time, and two consecutive successful complete strict probes.
- Never move a tag, delete/replace an asset, overwrite an archive, substitute newer main during recovery, or upload again during verification.
- Keep the existing two screenshot exclusions, required artifact sets, historical schemas, primary pins, `.7`/`.8` archives, and historical two-revision lineage verification unchanged.
- `CLOUDFLARE_PAGES_ENABLED` controls Pages uploads only. Distinguish `superseded`, `deployment_paused`, `published`, `verified`, and `failed` in operational results.
- Publication evidence must be durable before deployment. Deployment evidence includes both successful complete probes and failed observations. Evidence failure leaves finalization incomplete and retryable.
- PR jobs receive no new release-write or production credentials. Release writes belong only to the mainline publisher, issue writes only to evidence jobs, and Cloudflare secrets only to the upload step in the main-only production environment.
- Ordinary tests use fixtures, never live services. Run `make check` before proposing the implementation; run reproducibility and staged-site verification from its clean committed revision.
- This issue supplies no editorial or baseline approval and does not close #545, #497, or #491 automatically.

## Review Focus

1. A documentation merge arrives behind a queued release: the release stays queued and its original revision remains eligible (Tasks 5, 8).
2. A rebuilt ZIP has different screenshot bytes: recovery verifies deterministic equality but deploys from the original published archive and records its original digest (Task 4).
3. Evidence posting fails after upload or halfway through a multipart report: retry finishes evidence without another upload, duplicate parts, or edits to human comments (Tasks 7, 8).
4. A rerun finds expired artifacts or a same-named artifact from another attempt: use captured producer identities or rebuild the exact source revision, never select by latest name (Tasks 3, 5).
5. A slow complete probe makes several HTTP requests: every request shares the hard deadline; a failed attempt resets the two-pass streak and cannot extend the deadline (Task 6).

---

## File responsibilities and shared contracts

Paths below are repository-relative. Extend focused modules; do not restructure the large existing `cli.py` or introduce a general deployment framework.

| Files | Responsibility |
|---|---|
| `hosting/models.py`, `release/declaration.py` under `src/election_guide/` | Backward-readable request schema, current-release resolution, preparation, changed-path admission |
| `src/election_guide/release/history.py`, `cliff.toml`, `CHANGELOG.md` | Fixed-range software history in hashed release notes; deterministic legacy-history index |
| `src/election_guide/release/automation_models.py`, `candidate.py` | Shared operational record types; exact-source build and artifact verification |
| `src/election_guide/release/publication.py`, `github_cli.py` | GitHub publication state machine; shared subprocess boundary, binary downloads |
| `src/election_guide/hosting/promotion.py` | Canonical restaging, expired-artifact recovery, supersession guard |
| `src/election_guide/hosting/production_probe.py`, `production_wait.py` | One shared deadline across HTTP requests; bounded repeated strict verification |
| `src/election_guide/release/evidence.py` | Publication/upload/final receipts, bounded issue comments, idempotent finalization |
| `src/election_guide/release/automation_cli.py`, existing `cli.py` | Thin `release automation` commands registered on the existing Typer app |
| `Makefile`, CI/preview/verification workflows | Supported entry points, job dependencies, credentials, artifact IDs, serialization |
| `CONTRIBUTING.md`, `ARCHITECTURE.md`, `docs/RELEASE.md`, `docs/HOSTING.md` | Amended release policy and executable procedures, updated with their owning tasks |

The following names and fields are the contract between tasks. Use strict Pydantic models with forbidden extras, lowercase 40-character Git SHAs, lowercase 64-character SHA-256 values, positive IDs, timezone-aware timestamps, and schema version `1.0` for new operational records. These records are outside the immutable release artifact schema.

- `InputHashes(ledger_sha256: str, dataset_sha256: str, registry_sha256: str)`.
- `PublicationRequest(issue_number: int, previous_release_sha: str, inputs: InputHashes)`; optional `PublishedElection.publication_request`, permitted only on the current election. Keep `SiteManifest.schema_version == "1.0"`; absence means legacy reading, not authorization to publish.
- Frozen dataclasses `ReleaseInputs(ledger: Path, inventory: Path, registry: Path, dataset: Path, snapshots: Path, manifests: Path)` and `ResolvedRelease(site: SiteManifest, current: PublishedElection, inputs: ReleaseInputs, archive_name: str)`.
- `Producer(repository: str, source_sha: str, workflow_sha: str, run_id: int, run_attempt: int)`; `FileDigest(sha256: str, size: int)`; `ArtifactRef(id: int, name: str, digest: FileDigest, producer: Producer)`. Normal main runs have equal source/workflow SHAs; an explicit recovery dispatch on main may check out an older reviewed source. Validate Actions metadata against `workflow_sha` and all build/deployment identities against `source_sha`.
- `CandidateRecord(declaration: PublishedElection, site_manifest_sha256: str, source_sha: str, generated_at: datetime, inputs: InputHashes, producer: Producer, archive: FileDigest, bundle_sha256: str, deployment_manifest_sha256: str, release_artifact: ArtifactRef, site_artifact: ArtifactRef, recovered_from: Producer | None = None)`.
- `PublishedArchive(candidate: CandidateRecord, candidate_artifact: ArtifactRef, release_id: int, asset_id: int, asset_name: str, archive: FileDigest, release_manifest_sha256: str, canonical_bundle_sha256: str, promotion_manifest_sha256: str)`; `PublicationResult(published: PublishedArchive, promotion_artifact: ArtifactRef)`.
- `UploadReceipt(publication: PublicationResult, producer: Producer, github_deployment_id: int, deployment_url: str, uploaded_at: datetime, source_sha: str)`; a deployment URL is the unique Pages upload URL, not the canonical production origin.
- `OperationReceipt(phase: Literal["publication", "deployment"], state: Literal["superseded", "deployment_paused", "published", "verified", "failed"], producer: Producer, publication: PublicationResult, upload: UploadReceipt | None, verification_sha256: str | None, error: str | None)`.

Artifact digests identify the Actions wrapper ZIP and come from upload outputs/API metadata; release archive digests identify the canonical release ZIP's own bytes. Never compare or interchange them. The candidate record contains the already-uploaded release/site artifact IDs; its own later-uploaded artifact ID lives in `PublicationResult`, avoiding a self-referential digest.

### Task 1: Resolve, prepare, and admit a reviewed publication request

**Files:** Modify `src/election_guide/hosting/models.py`, `src/election_guide/cli.py`, `docs/RELEASE.md`; create `src/election_guide/release/declaration.py`, `src/election_guide/release/automation_cli.py`, `tests/test_release_declaration.py`; extend `tests/test_hosting_models.py`.

**Interfaces:** Define `InputHashes`/`PublicationRequest` in `hosting/models.py`, and `ReleaseInputs`/`ResolvedRelease` in `declaration.py`. Produce:

```python
resolve_release(site_manifest_path: Path, *, repository: Path) -> ResolvedRelease
hash_release_inputs(inputs: ReleaseInputs) -> InputHashes
prepare_release(site_manifest_path: Path, *, repository: Path, issue_number: int,
                main_manifest: SiteManifest, occupied_versions: frozenset[str],
                previous_release_sha: str) -> ResolvedRelease
validate_release_request(current: ResolvedRelease, *, base: SiteManifest,
                         changed_paths: tuple[str, ...]) -> bool
```

`validate_release_request` returns whether this diff requests a new release; stale bindings or release-affecting changes without a fresh declaration raise `ValueError`. CLI: `release automation resolve [--site-manifest PATH]` writes JSON; `prepare --issue NUMBER` refreshes the declaration; `validate-request --base-sha FULL_SHA` checks Git objects from the declared comparison.

- [ ] **Write failing tests.** In `test_release_declaration.py`, pin `test_resolve_current_identity`, `test_prepare_refreshes_same_unpublished_proposal`, `test_prepare_skips_remote_tag_and_draft_collisions`, `test_concurrent_proposal_requires_refresh`, and parametrized `test_request_admission`:

  ```python
  assert second.current.release_version == first.current.release_version
  assert second.current.publication_request.inputs == hash_release_inputs(second.inputs)
  assert validate_release_request(docs_only, base=base, changed_paths=("docs/HOSTING.md",)) is False
  # Each stale ledger/dataset/registry binding, or runtime change without a
  # version increment, must raise ValueError before any publication command.
  ```

  Add legacy-manifest readability, current-only request placement, positive issue, full previous SHA, and ledger/dataset election-identity rejection tests. Assert archived declarations and their pins are unchanged by preparation.
- [ ] **Run red:** `uv run pytest tests/test_release_declaration.py tests/test_hosting_models.py -q`; expect missing request/resolver behavior.
- [ ] **Implement the schema and resolver.** Resolve standard paths once from election ID: `data/releases/{id}/source-decisions.yaml`, `data/normalized/{id}-inventory.json`, `config/sources/{id}.yaml`, `data/normalized/{id}-canonical-dataset.json`, and ledger-adjacent `snapshots/`/`manifests/`. Preserve the existing primary's legacy `config/sources/default.yaml` and `data/normalized/canonical-dataset.json` mapping. Verify files and their election identities; derive bundle ID as `{election_id}-{release_version}` and archive name with existing `release_archive_name`.
- [ ] **Implement preparation and admission.** Read main plus paginated remote tag/release names through `run_gh`; fail incomplete queries. The next numeric election-scoped suffix exceeds both main and occupied identities. Retain this PR's higher unpublished version only when its issue/boundary match and it is unoccupied. Bind the full SHA of main's selected published release, require its ancestry, and atomically update only the current declaration. Admission covers `src/`, `data/`, `config/`, `scripts/`, `.github/workflows/`, `Makefile`, `cliff.toml`, `pyproject.toml`, `uv.lock`, `package.json`, `package-lock.json`, `wrangler.jsonc`, and `wrangler.toml`; document this conservative policy. A documentation/test-only diff with unchanged declaration is not a release.
- [ ] **Run green:** the red command plus CLI tests for JSON output and nonzero stale-binding errors. Document preparation without changing today's manual upload path yet.
- [ ] **Commit:** `feat: prepare and validate reviewed publication requests` (Refs #550), staging only this task's files.

### Task 2: Generate tag-independent software history inside release notes

**Files:** Create `src/election_guide/release/history.py`, `tests/test_release_history.py`; modify `src/election_guide/release/builder.py`, `release/automation_cli.py`, `.github/workflows/ci.yml`, `cliff.toml`, `package.json`, `Makefile`, `CHANGELOG.md`, `CONTRIBUTING.md`, `docs/RELEASE.md`, `tests/test_changelog.py`, `tests/test_release.py`.

**Interfaces:** Consume Task 1's resolver/request. Produce `generate_software_history(repository: Path, *, previous_release_sha: str, source_sha: str, release_version: str, generated_at: datetime) -> str` and `generate_changelog_index(repository: Path) -> str`. Extend `build_release(..., software_history: str | None = None) -> ReleaseResult`; legacy callers omit it and retain existing bundle structure. New current-candidate builds supply it before notes hashing/ZIP creation.

- [ ] **Write failing tests.** `test_history_identical_before_and_after_candidate_tag` creates a temporary Git repository, renders notes, tags the same source, renders again, and asserts exact bytes. `test_history_uses_fixed_range_and_commit_time` asserts the earlier boundary commit and later commits are absent, conventional and unconventional in-range commits appear, and the heading uses the declared election version/date. `test_legacy_index_ignores_future_tags` asserts unchanged historical entry bytes after adding a descendant release tag. Assert the notes digest changes when the software section changes and the required artifact set does not grow.

  ```python
  assert before_tag == after_tag
  assert f"## {release_version}" in before_tag
  assert legacy_index_before == legacy_index_after
  ```

- [ ] **Run red:** `uv run pytest tests/test_release_history.py tests/test_changelog.py -q`; expect new generation/policy assertions to fail.
- [ ] **Implement fixed-input generation.** Invoke pinned local git-cliff offline with explicit `previous_release_sha..source_sha`, ignoring discovered tags, to obtain context. Set its sole rendered release's version and timestamp from the arguments before rendering through the existing conventional-commit parsers; do not use `--unreleased`, the latest tag, or wall-clock time. Verify both endpoints exist and the boundary is an ancestor. Append `## Software changes` to the existing `RELEASE_NOTES.md` before hashing. The before/after-tag test is the executable contract if git-cliff context handling needs adjustment.
- [ ] **Amend changelog policy and checks together.** Record `legacy_history_end_sha = "a1a83b5f1c09d7297a6100e3ac321b0e5034bf52"` in a `[release_history]` section of `cliff.toml`. Generate the root index with a link to published releases and the retained historical sections through that fixed endpoint. Preserve their bytes; never append later tag-generated sections to the committed index. Expose `release automation changelog-index --output PATH`; make `npm run changelog` and `make check-changelog` generate/compare this index, retain the exact git-cliff pin, and add deterministic software-history tests to the existing gate. Add locked Python setup to the existing client CI lane because its changelog entry point now needs Python; preserve lane independence. Replace the former mandatory post-tag commit policy in CONTRIBUTING and RELEASE with the approved policy.
- [ ] **Run green:** the red command, `uv run pytest tests/test_release.py -q`, and `make check-changelog`. Confirm the archived schemas and `release/lineage.py` require no changes.
- [ ] **Commit:** `feat: include deterministic software history in release bundles` (Refs #550).

### Task 3: Capture and validate one candidate and its producing artifacts

**Files:** Create `src/election_guide/release/automation_models.py`, `src/election_guide/release/candidate.py`, `tests/test_release_candidate.py`; modify `release/automation_cli.py`, `Makefile`, `tests/test_ci.py` under their existing locations.

**Interfaces:** Define the shared operational records from `Producer` through `OperationReceipt` in `automation_models.py`, with field validation tests; their behavior is added by the owning tasks below. Consume Tasks 1–2 and existing `build_release`, `compare_release_bundles`, `stage_pages_site`, `verify_staged_pages_site`. Produce:

```python
build_current_candidate(resolved: ResolvedRelease, *, repository: Path,
                        output_dir: Path, source_sha: str) -> Path
record_candidate(resolved: ResolvedRelease, *, repository: Path, output_dir: Path,
                 producer: Producer, release_artifact: ArtifactRef,
                 site_artifact: ArtifactRef,
                 recovered_from: Producer | None = None) -> CandidateRecord
verify_candidate(record: CandidateRecord, *, repository: Path,
                 archive_path: Path, site_dir: Path) -> None
verify_artifact_ref(expected: ArtifactRef, observed: ArtifactRef) -> None
```

`build_current_candidate` returns the first build's archive path; fixed output layout is `reproducibility-a/`, `reproducibility-b/`, `cloudflare-site/`, then `candidate.json`. CLI commands: `build --source-sha SHA --output-dir PATH`, `record --producer-file PATH --release-artifact-file PATH --site-artifact-file PATH --output PATH`, and `verify-candidate --record PATH --archive PATH --site-dir PATH`. Also expose `stage --bundle-dir PATH --output-dir PATH --source-sha SHA` as a thin resolver-backed call to the existing staging/verification functions for `make hosting-stage`.

- [ ] **Write failing tests.** `test_candidate_binds_full_source_and_all_bytes` rejects changed ZIP bytes, site assets, manifest, site declaration, or any reviewed hash. `test_artifact_attempt_cannot_be_substituted` changes only attempt/ID/source in an otherwise identical fixture and expects rejection. `test_record_does_not_reference_its_own_artifact` asserts only release/site artifact refs are embedded. Check wrapper digest and inner ZIP digest remain separate. Use small verified bundle fixtures for unit tests and one real existing build fixture for wiring.

  ```python
  assert record.source_sha == record.producer.source_sha
  assert record.archive.sha256 == hashlib.sha256(archive_path.read_bytes()).hexdigest()
  with pytest.raises(ValueError):
      verify_artifact_ref(expected, wrong_attempt)
  ```

- [ ] **Run red:** `uv run pytest tests/test_release_candidate.py -q`.
- [ ] **Implement exact-source preparation.** Require a clean checkout equal to `source_sha`; read `%cI` once. Build twice with the same resolved inputs and Task 2 history, compare using existing exclusions, select build A's exact ZIP, and stage/independently verify the complete site with the pinned published primary. Verify full ZIP member set against the declared included artifacts, not merely existence of selected paths. Compute byte digests and the existing whole-bundle hash.
- [ ] **Implement artifact binding.** Upload steps will run between `build` and `record`; consume their captured IDs/digests/sizes and validate repository, source, run, attempt, and names. Use `release-{run_id}-{run_attempt}`, `site-{run_id}-{run_attempt}`, and `candidate-{run_id}-{run_attempt}`; never resolve an artifact by newest name. Candidate JSON uses canonical serialization. Preserve all required identity checks after every download.
- [ ] **Replace current-version Make literals.** Point `check-release-reproducible` and current `hosting-stage` at shared commands/resolution while preserving the aliases and historical explicit verification commands. Amend `test_ci.py` to assert resolver use and actual resolved arguments rather than a copied version string; keep deterministic comparison, complete staging, and expected-SHA assertions.
- [ ] **Run green:** the red command and `uv run pytest tests/test_ci.py -q`. Run the real reproducibility gate after committing, because the builder rejects a dirty tree.
- [ ] **Commit:** `feat: bind release candidates to exact source and artifact identities` (Refs #550).

### Task 4: Publish or recover the canonical GitHub archive without overwrite

**Files:** Create `src/election_guide/release/publication.py`, `tests/test_release_publication.py`; modify `src/election_guide/github_cli.py`, `hosting/releases.py`, `release/automation_cli.py`; extend `tests/test_hosting_releases.py`.

**Interfaces:** Consume Task 3's shared models. Produce `publish_candidate(candidate: CandidateRecord, *, candidate_artifact: ArtifactRef, repository: Path, archive_path: Path, work_dir: Path, existing_receipt: PublicationResult | None) -> PublishedArchive`, `bind_publication(published: PublishedArchive, promotion_artifact: ArtifactRef) -> PublicationResult`, and `download_gh(command: list[str], destination: Path, failure: str) -> None` in the shared GitHub boundary. Expose existing safe ZIP extraction as `extract_release_bundle(archive_path: Path, bundle_dir: Path, declaration: PublishedElection) -> None` without weakening existing callers. CLI `publish --record PATH --candidate-artifact-file PATH --archive PATH --output-dir PATH` writes `published-archive.json`, the canonical bundle, and the verified promotion site; after the Actions upload step, `bind-publication --published PATH --promotion-artifact-file PATH --output PATH` captures its artifact identity.

- [ ] **Write failing state-matrix tests.** Parametrize `test_publication_preflight_states`: absent tag/release; matching owned empty draft; matching owned draft with verified ZIP; unrelated draft; wrong tag target; wrong notes; extra/missing/duplicate assets; published matching/conflicting archive; absent/conflicting receipt. Assert failure states make no writes. `test_published_screenshot_difference_preserves_original_zip` asserts original asset ID/digest/screenshot bytes survive while deterministic files compare equal; changing a deterministic artifact fails. `test_uploaded_archive_is_downloaded_before_publish` asserts draft → upload → download verification → publish order and no deployment eligibility for a draft.

  ```python
  assert recovered.asset_id == original_asset_id
  assert recovered.archive == original_archive_digest
  assert canonical_desktop.read_bytes() == published_desktop_bytes
  assert mutation_calls == []  # Existing matching published release.
  ```

- [ ] **Run red:** `uv run pytest tests/test_release_publication.py tests/test_hosting_releases.py -q`.
- [ ] **Implement preflight and ownership.** Use paginated tag/release/asset reads through `run_gh`; peel annotated tags to full commits. Published/finalized state requires exactly one canonical ZIP and no unrecognized assets; a matching owned empty draft may receive its missing ZIP. A newly created draft records a final ownership marker binding repository, version, source, request digest, and notes digest. Resume only matching ownership/content; a pre-existing orphan tag without a matching owned draft/verified published release fails for operator inspection. Create a missing tag only through publication targeted at the exact candidate SHA. Never call tag update/delete, release delete, asset delete, or clobber APIs.
- [ ] **Implement canonical recovery.** Stream binary downloads to files through `download_gh`, verify size/SHA and archive member safety (including duplicate/path-alias members and symlinks), then reuse existing manifest and deterministic comparison. For published assets, compare against the same-source fresh candidate and preserve original ZIP bytes even if screenshots differ. A matching existing receipt must agree; reconstruct a missing one only after complete verification of the exact reviewed source. Restage a promotion site from that canonical bundle at the captured source using existing hosting functions and verify it. Return its manifest digest in `PublishedArchive`; Task 8 uploads `promotion-{run_id}-{run_attempt}` using the Actions upload action, then `bind_publication` validates that captured ref and produces `PublicationResult`. Python does not invent an Actions artifact-upload API. Do not alter the build's original candidate record.
- [ ] **Run green:** the red command plus `uv run pytest tests/test_release_comparison.py tests/test_release_lineage.py -q`. Verify no new screenshot exclusion or historical schema is introduced. Use the official [release API](https://docs.github.com/en/rest/releases/releases) and [artifact API](https://docs.github.com/en/rest/actions/artifacts) for response fixtures.
- [ ] **Commit:** `feat: publish verified archives with conflict-safe recovery` (Refs #550).

### Task 5: Recover exact-source artifacts and prevent stale promotion

**Files:** Create `src/election_guide/hosting/promotion.py`, `tests/test_release_promotion.py`; modify `release/automation_cli.py`.

**Interfaces:** Consume the shared models in `automation_models.py`, existing hosting verification, and Task 3's build entry point. Produce `recover_candidate(candidate: CandidateRecord, *, repository: Path, work_dir: Path) -> Path` returning the rebuilt archive path, `promotion_allowed(publication: PublicationResult, *, selected: SiteManifest, latest_verified: OperationReceipt | None) -> bool`, and `verify_merged_release_source(repository: Path, *, source_sha: str) -> int` returning the merged PR number. CLI `admit --source-sha SHA --base-sha SHA` and `promotion-check --publication PATH --output PATH` produce explicit eligibility/state JSON; `recover --record PATH --output-dir PATH` rebuilds files for subsequent captured artifact uploads and Task 3's `record` command.

- [ ] **Write failing tests.** `test_expired_artifact_rebuilds_original_sha` asserts every Git/build/manifest operation uses the captured full SHA even when main advances; a wrong existing artifact errors instead of causing silent fallback. `test_docs_advance_does_not_supersede_release` preserves eligibility when only main's documentation changed. `test_out_of_order_release_cannot_replace_newer_production` rejects an older or incomparable candidate. `test_source_requires_merged_main_pr` rejects PR refs, non-main refs, missing/ambiguous merged PR association, and failed exact-source CI evidence. Cover a newer declaration before upload and an allowed merge arriving after the final check.

  ```python
  assert promotion_allowed(publication, selected=docs_advanced, latest_verified=prior) is True
  assert promotion_allowed(publication, selected=newer_selection, latest_verified=prior) is False
  assert rebuilt_source_shas == [candidate.source_sha, candidate.source_sha]
  ```

- [ ] **Run red:** `uv run pytest tests/test_release_promotion.py -q`.
- [ ] **Implement recovery.** Validate Actions artifact metadata by captured ID and producer before use. Only absent/expired artifacts trigger recovery, in a clean detached checkout at `candidate.source_sha`; install locked dependencies and rerun all required checks plus the two-build/site gates for that exact source. Task 8 uploads replacement artifacts and calls `record_candidate` with their captured refs and `recovered_from=candidate.producer`; preserve the original candidate in durable evidence. For a published version, Task 4's original archive remains canonical. A recovery cannot label a current checkout or old failed CI run as successful evidence.
- [ ] **Implement admission and guard.** Validate the candidate's exact merged PR/source relation via GitHub, requiring base `main`, merged status, and matching merge commit. The normal same-workflow path consumes all five successful required CI lane results; a recovery must provide fresh results at the original source. Compare current main's selected declaration (including input/request identity) and the latest verified durable production receipt. A different newer declaration supersedes; equal declaration with later docs commits remains eligible; older/incomparable production lineage fails closed. Check immediately before the sole upload while holding the workflow lock. Return `superseded` for a legitimate newer selection; reserve `failed` for conflicting/unverifiable state.
- [ ] **Run green:** the red command and candidate/publication tests. No upload occurs in any of these tests.
- [ ] **Commit:** `feat: guard canonical promotion against stale and expired candidates` (Refs #550).

### Task 6: Confirm production twice within one hard deadline

**Files:** Create `src/election_guide/hosting/production_wait.py`, `tests/test_production_wait.py`; modify `hosting/production_probe.py`, `cli.py`, `tests/test_production_probe.py`, `tests/test_hosting_check_production_cli.py`, `docs/HOSTING.md` under existing roots.

**Interfaces:** Extend `run_production_check(..., deadline: float | None = None) -> ProductionCheckReport` with an absolute monotonic deadline. Add frozen `ProductionWaitReport(attempts: tuple[ProductionCheckReport, ...], successful_indices: tuple[int, ...], timed_out: bool)` with `.ok` and deterministic JSON serialization. Produce `wait_for_production(base_url: str, *, site_manifest: SiteManifest, expected_git_commit: str, active_window: bool, timeout: float = 15.0) -> ProductionWaitReport` and its terminable worker boundary `run_deadline_probe(base_url: str, *, site_manifest: SiteManifest, expected_git_commit: str, active_window: bool, timeout: float, deadline: float) -> ProductionCheckReport`; inject time/worker results through monkeypatched module functions in tests. Add `hosting check-production --wait` using this behavior; retain existing single-check and availability-only modes.

- [ ] **Write failing tests.** Controlled-clock `test_previous_release_then_two_complete_passes` asserts a wrong initial SHA is retained and two subsequent full reports are required. `test_failure_resets_success_streak` uses pass/fail/pass/pass and asserts the final pair. `test_shared_deadline_bounds_every_http_request` simulates slow multiple-request probes and asserts each timeout is `<= min(15, remaining)` with no request at/after 120 seconds. Parametrize persistent bad SHA, manifest, route, redirect, and transport failures; all time out and preserve observations. Assert successive attempt starts are at least five seconds apart and no upload command exists.

  ```python
  assert report.successful_indices == (2, 3)  # pass/fail/pass/pass fixture.
  assert all(b - a >= 5 for a, b in zip(starts, starts[1:]))
  assert timed_out_at - started_at <= 120
  ```

- [ ] **Run red:** `uv run pytest tests/test_production_wait.py tests/test_production_probe.py tests/test_hosting_check_production_cli.py -q`.
- [ ] **Implement deadline propagation and waiting.** Recompute remaining time immediately before every HTTP request and cap its timeout. Run each complete probe in a terminable child process with a structured result channel and a parent wait bounded by the same absolute deadline; urllib's per-operation timeout alone does not bound a slowly streamed body or DNS. On deadline, terminate/join the worker and append a timeout observation, preserving prior complete reports. Keep redirects disabled. The outer loop uses monotonic time, starts no more often than once per five seconds, and succeeds only after two consecutive `.ok` strict reports from the same origin, trusted declaration, full SHA, and release identity. Preserve the existing calendar-based active freshness policy rather than changing it during retry. Always write the complete attempt report before a timeout exits nonzero. Add a local fixture worker that blocks on a body to verify real termination without a live service.
- [ ] **Run green:** the red command and `uv run pytest tests/test_production_check.py -q`. Document exact wait limits and that retrying verification performs no upload.
- [ ] **Commit:** `feat: wait for bounded consecutive production confirmations` (Refs #550).

### Task 7: Retain durable, resumable publication and deployment evidence

**Files:** Create/complete `src/election_guide/release/evidence.py`, create `tests/test_release_evidence.py`; modify `release/automation_cli.py`.

**Interfaces:** Consume `UploadReceipt`/`OperationReceipt` from `automation_models.py`. Produce `retain_evidence(receipt: OperationReceipt, *, issue_number: int, reports: dict[str, bytes]) -> tuple[int, ...]` returning comment IDs; `load_verified_receipts(*, repository: str, issue_number: int, release_version: str, source_sha: str) -> tuple[OperationReceipt, ...]`; `latest_production_receipt(repository: str) -> OperationReceipt | None`; and `finalize_deployment(upload: UploadReceipt, *, site_manifest: SiteManifest, producer: Producer, output_dir: Path) -> OperationReceipt`. CLI commands: `retain-publication --publication PATH`, `record-upload --publication PATH --github-deployment-id ID --deployment-url URL --uploaded-at ISO --output PATH`, and `finalize --upload PATH --output-dir PATH`. Evidence commands read the owning issue from the reviewed request, not arbitrary release-body text.

- [ ] **Write failing tests.** `test_publication_evidence_required_before_upload` asserts a missing/conflicting durable publication receipt blocks upload. `test_receipts_retain_all_identities_and_both_probes` asserts every shared-record field and report digest is retained. `test_partial_comment_retry_posts_only_missing_parts` injects failure after part one, resumes, and asserts one copy per part and no human-comment edits. `test_finalize_retry_never_uploads` starts from an existing upload receipt after probe/evidence failure and asserts no build/upload call. Test missing publication receipt reconstruction, conflicting bot receipts, malformed/truncated parts, and deployment status distinctions.

  ```python
  assert posted_bodies.count(first_part_body) == 1
  assert all(len(body) < 60_000 for body in posted_bodies)
  assert upload_calls == []  # Evidence-only retry after the existing upload.
  ```

- [ ] **Run red:** `uv run pytest tests/test_release_evidence.py -q`.
- [ ] **Implement bounded comments and receipt validation.** Use canonical UTF-8 JSON. Split at UTF-8 boundaries into payloads of at most 24,000 bytes, keeping complete comment bodies below 60,000 characters with numbering, SHA-256, and bounded framing. Each comment ends with an automation marker binding repository, release, full source, producer run/attempt, phase, report name, part number/count, and digest. Read all comment pages; accept markers only from the workflow's bot identity with matching payload hashes. Reuse exact existing parts, fail conflicting parts, never update human comments. A final receipt lists all required part IDs/hashes; report partial writes as incomplete rather than verified.
- [ ] **Implement read-only finalization.** Verify the existing publication/upload receipts and the trusted site declaration's captured byte hash; retain the upload record before calling Task 6, then retain the operation receipt and full report (including both passes). Discover the latest verified release across owning issues through automation-owned production GitHub deployments: their payloads identify issue/release/source, and success requires matching durable final evidence. Read all pages; missing/conflicting evidence on a managed successful deployment is an error. No managed predecessor on first activation returns `None`; Task 8 separately verifies the existing legacy production evidence without fabricating a legacy request. Issue-write failure keeps a retryable nonzero outcome even if production is healthy. Resume from the recorded upload without build, release mutation, or deployment. Post truthful `failed`, `superseded`, or `deployment_paused` receipts where applicable; none close the owning issue or assert editorial approval. Publish local failure evidence and job summaries even if GitHub comments are unavailable.
- [ ] **Run green:** the red command and Tasks 4–6's fixture suites. Verify comment size limits using Unicode-heavy reports and a partial-write retry.
- [ ] **Commit:** `feat: retain durable resumable release evidence` (Refs #550).

### Task 8: Wire, review, and activate the complete automatic path

**Files:** Modify `.github/workflows/ci.yml`, `.github/workflows/deploy-pr-preview.yml`, `Makefile`, `config/hosting/site.yaml`, `CONTRIBUTING.md`, `ARCHITECTURE.md`, `docs/RELEASE.md`, `docs/HOSTING.md`, `tests/test_ci.py`, `tests/test_release_runbook.py`, `tests/test_production_verification_workflow.py`, `tests/test_preview_teardown.py`; create `.github/workflows/verify-release.yml`, `tests/test_release_automation_workflow.py`. Complete `release/automation_cli.py` command wiring without moving unrelated CLI commands.

**Interfaces:** Consume Tasks 1–7. Mainline job graph: existing five independent lanes → stable `check` → `publish` → `publication-evidence` → `deploy` → `finalize`. `publish` additionally needs the publication lane's exact artifact outputs; `deploy` also needs `check` and verified durable publication evidence. Outputs are captured artifact IDs/digests and validated JSON record paths, never arbitrary shell fragments or latest-name selection.

- [ ] **Write failing workflow/command tests.** `test_mainline_serialization_preserves_queued_release` asserts workflow-level common mainline group, `queue: max`, `cancel-in-progress: false`, PR-specific parallel groups, and no conflicting deploy lock. `test_publish_requires_every_lane_and_exact_merged_source` executes representative gate commands with success/failure/cancelled fixtures. `test_privileges_and_switch_scope` asserts main-only writes, no PR publication, no Cloudflare secrets outside upload, and paused upload still permits publication evidence. `test_attempt_scoped_artifact_ids_flow_through_jobs` asserts upload outputs feed ID-based downloads and failures retain artifacts. `test_verification_rerun_cannot_build_or_upload` asserts the separate workflow lacks release/CF credentials and build/deploy commands. Add shell-executed fixture paths for a complete successful run, supersession, paused deployment, expired recovery, and a failed-probe/evidence retry.

  ```python
  assert workflow["concurrency"]["queue"] == "max"
  assert workflow["concurrency"]["cancel-in-progress"] == "false"  # BaseLoader.
  assert "publication-evidence" in jobs["deploy"]["needs"]
  assert jobs["publish"]["permissions"]["contents"] == "write"
  ```

- [ ] **Run red:** `uv run pytest tests/test_release_automation_workflow.py tests/test_ci.py tests/test_production_verification_workflow.py tests/test_release_runbook.py tests/test_preview_teardown.py -q`.
- [ ] **Wire read-only candidate CI.** Preserve the five lane names and independent scheduling and the stable aggregate `check`. Fetch full history where fixed-range notes/admission need it. Validate requests against the PR base; expose candidate notes/reports and desktop/mobile images for pre-merge human review. Mainline candidate records require merged-source admission. Add a `workflow_dispatch` recovery input `source_sha`; default it to the event SHA for ordinary runs, and use the validated captured SHA in every lane's checkout/build. An explicit recovery source must be a reviewed main ancestor with its original request and fresh complete checks; record the dispatch workflow SHA separately. Docs/test-only main commits still run normal CI but produce no publication/deployment request. Replace current-version literals in both workflows with the shared resolver; preserve preview opt-in, same-repository guards, PR-head identity, and teardown behavior.
- [ ] **Wire serialization.** Use `verified-release-mainline` for all non-PR mainline runs; use `ci-pr-{number}-{run_id}` for parallel PR runs, with the approved queue policy ([GitHub concurrency contract](https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-syntax#concurrency)). Surface queue exhaustion as delivery failure.
- [ ] **Wire publication and its evidence gate.** `publish` has contents write plus actions/issues/pull requests read and verifies all exact-source gates. Bind canonical promotion upload outputs through Task 4's two-step interface. `publication-evidence` has issues write and must finish before deployment. Evidence jobs also have the contents/actions read access needed to check out trusted code and fetch exact artifacts.
- [ ] **Wire the guarded upload.** `deploy` has contents/actions/issues read and deployments write in the main-only production environment; it runs the final stale check and switch check before upload. When paused/superseded, emit that state without exposing Cloudflare secrets. For an admitted upload, create an automation-owned GitHub production deployment for the exact SHA with owning-issue/release identity, invoke pinned Wrangler once, capture stdout/stderr plus its unique Pages URL and upload time into `UploadReceipt`, and immediately record the URL on its deployment status for recovery. Capture failures even if upload outcome is uncertain; require operator verification before any new upload.
- [ ] **Wire finalization and failure retention.** `finalize` has issues/deployments write and no Cloudflare secret; it retains all probe/evidence results and marks the owned GitHub deployment successful only after durable finalization. Add `if: always()` artifact preservation with attempt-scoped names and existing seven-day retention. A receipt-write failure must fail delivery even when `check` is green.
- [ ] **Wire verification-only recovery.** `verify-release.yml` accepts owning issue, release version, full source SHA, and producing run/attempt, loads the matching durable receipts and trusted declaration from that Git object, and runs only verification/evidence finalization using trusted workflow code from main. If upload evidence is incomplete, reconstruct it only from the matching owned GitHub deployment/status and retained upload report; ambiguity fails without another upload. It never resolves latest main as the candidate. Release recovery resumes the original mainline run or dispatches on main with `source_sha` fixed to the captured source through all checks.
- [ ] **Amend executable runbooks.** Retire `make hosting-deploy` as an upload route (fail with the supported recovery instructions), remove direct-upload instructions from current runbooks, and preserve historical two-SHA verification documentation. Rewrite protected command blocks and drift tests around preparation, CI artifacts, same-SHA identities, wait mode, and evidence retry. Update ARCHITECTURE with the new boundary and CONTRIBUTING with pre-merge visual review. Do not add mandatory screenshot attestations after merge.
- [ ] **Run focused green checks:** the red command and all new fixture suites must pass.
- [ ] **Prepare activation.** Run `uv run election-guide release automation prepare --issue 550`, refreshing against current main/remote versions; keep the approved 880-decision ledger/dataset/registry bytes unchanged unless a separately reviewed data change is explicitly included. Re-run affected request tests.
- [ ] **Run the full gate and commit.** Run `make check`, then commit `feat: automate verified publication and production promotion` (Refs #550), staging only task-owned files.
- [ ] **Verify the clean candidate.** Run `make check-release-reproducible`, `make hosting-stage`, and independent `hosting verify` with the full committed SHA; inspect both candidate screenshots and notes before proposing the implementation PR.
- [ ] **Publish and review the implementation.** Publish a focused PR linked to #550, attach it to this chat, and report exact test/repro/site evidence and any incompleteness. Complete the repository-owned review and required GitHub checks before merge.
- [ ] **Check rollout readiness.** Verify the existing `.8` production identity against durable manual evidence on #545 and retain a link as activation context, without inventing a legacy publication request. Enumerate old pending mainline/deployment runs and retire superseded legacy uploads; confirm the main-only environment does not require an extra Publish approval and the existing upload switch is enabled.
- [ ] **Activate by merge.** Merge under the user's applicable merge authorization; this is the rollout action.
- [ ] **Verify live acceptance.** Follow the exact merged revision through the archive, durable publication receipt, canonical promotion artifact, one upload, two complete production passes, and durable final receipt. Compare the published asset digest/ID with the receipt and confirm the pinned primary remains unchanged. If any step fails, leave #550 open with the observed state and use the corresponding recovery entry point; do not toggle the switch, overwrite an archive, or report completion from an upload alone. Close #550 only when its acceptance and live rollout evidence are met.

## Plan review and handoff

Self-review coverage: request/version authority → Task 1; changelog policy → Task 2; reproducibility and artifact identity → Task 3; canonical publication/restart → Task 4; expiry and concurrency ordering → Tasks 5/8; propagation → Task 6; durable evidence → Task 7; privilege boundaries, compatibility, executable docs, and live activation → Task 8. Every Review Focus item has a named test above.

Implementation has not started. Review this plan and select an execution method before starting Task 1. The tasks share candidate/receipt interfaces, so native execution is a reasonable lower-cost choice; a production publication mistake is costly enough that subagent-driven execution is recommended for fresh review at each task boundary, followed by whole-branch review. Either method must preserve the repository's checks and the final live verification gate.
