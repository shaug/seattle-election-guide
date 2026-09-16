# Stable Panel Identity Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Separate stable personalized-panel identity from the complete mutable source-registry hash while preserving every published snapshot and link.

**Architecture:** Build one strict canonical panel-identity projection and hash it independently from the existing full-registry hash. Existing primary and general panels use validated compatibility bindings from their new projection hash to their already-published hash; publication, release, and hosting artifacts then carry both hashes with backward-readable schema transitions.

**Tech Stack:** Python 3.12, Pydantic 2, canonical JSON serialization, Typer, pytest, JavaScript URL-codec tests, YAML configuration.

**Spec:** `docs/superpowers/specs/2026-09-16-stable-panel-identity-design.md`

## Global Constraints

- Preserve the committed primary and general `panel-snapshots.json` files byte-for-byte.
- Keep `source_panel_hash` as the serialized stable panel-hash field; add `source_registry_hash` for the complete-input audit hash.
- The browser payload and personalized-link grammar continue to receive only the stable panel hash.
- Existing immutable publication, release, site, and deployment artifacts remain readable under their current schema versions.
- Write each behavioral test first, observe the expected failure at the base behavior, then add the minimum implementation.
- Run `make check` and `make check-release-reproducible` before publication.

---

### Task 1: Define and publish stable panel identity

**Files:**
- Modify: `src/election_guide/sources/models.py`
- Modify: `src/election_guide/sources/panel.py`
- Modify: `config/sources/default.yaml`
- Modify: `config/sources/wa-2026-general.yaml`
- Modify: `tests/test_sources.py`
- Modify: `tests/test_general_source_panel.py`

**Interfaces:**
- Consumes: `SourceRegistry`, `canonical_json_bytes`, and the existing `PanelSnapshot` projection.
- Produces: `PanelHashCompatibility`, `PanelIdentityContract`, `panel_identity_hash(registry: SourceRegistry) -> str`, and an updated `build_panel_snapshot(registry: SourceRegistry) -> PanelSnapshot`.

- [ ] **Step 1: Add failing behavior tests for mutable and structural changes**

Add tests that deep-copy a real registry payload, validate it, and compare both hashes. Use literal mutations rather than a helper that reimplements the projection:

```python
def test_discovery_refresh_changes_registry_hash_without_changing_panel_identity() -> None:
    before = read_source_registry(REGISTRY_PATH)
    payload = before.model_dump(mode="json")
    source = payload["sources"][0]
    source["discovery"]["checked_at"] = payload["research_cutoff"]
    source["discovery"]["notes"] = "Current official publication rechecked."
    source["organization_url"] = "https://example.org/current-source"
    after = SourceRegistry.model_validate(payload)

    assert source_registry_hash(after) != source_registry_hash(before)
    assert build_panel_snapshot(after).panel_hash == build_panel_snapshot(before).panel_hash
```

Parameterize separate structural mutations for source code, category membership,
panel role, source name, eligibility, overlap membership, and retired-code
migration reason. Assert each changes `panel_identity_hash` and the candidate
snapshot hash.

Update the general-panel regression to assert that `sources snapshot` is now a
deterministic no-op after the discovery sweep:

```python
assert current_projection == published
assert appended_panel_snapshot(committed_catalog, current_projection) == committed_catalog
```

- [ ] **Step 2: Run the new focused tests and record RED evidence**

Run:

```bash
uv run pytest \
  tests/test_sources.py::test_discovery_refresh_changes_registry_hash_without_changing_panel_identity \
  tests/test_general_source_panel.py::test_general_panel_snapshot_preserves_frozen_identity_contract \
  -q
```

Expected: the discovery test fails because `panel_hash` still equals
`source_registry_hash`; the general snapshot test fails because the current
projection still conflicts with the published snapshot.

- [ ] **Step 3: Add the strict identity and compatibility models**

In `sources/models.py`, keep schema 1.1 readable and add schema 1.2 plus the
optional compatibility record:

```python
class PanelHashCompatibility(SourceModel):
    panel_id: str = Field(min_length=1)
    contract_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    published_hash: str = Field(pattern=r"^[0-9a-f]{64}$")


class SourceRegistry(SourceModel):
    schema_version: Literal["1.1", "1.2"] = "1.2"
    panel_hash_compatibility: PanelHashCompatibility | None = None
```

Extend `SourceRegistry.validate_registry` so a compatibility record's
`panel_id` must equal `registry.id`; schema 1.1 rejects the new record and
schema 1.2 permits it.

In `sources/panel.py`, define strict projection models for eligibility,
categories, sources, overlap groups, and retired codes, then compose:

```python
class PanelIdentityContract(SourceModel):
    schema_version: Literal["1.0"] = "1.0"
    categories: list[PanelCategoryIdentity]
    sources: list[PanelSourceIdentity]
    overlap_groups: list[PanelOverlapIdentity]
    retired_codes: list[PanelRetiredCodeIdentity]


def panel_identity_hash(registry: SourceRegistry) -> str:
    contract = _panel_identity_contract(registry)
    return hashlib.sha256(canonical_json_bytes(contract.model_dump(mode="json"))).hexdigest()
```

Make `build_panel_snapshot` select the legacy public hash only for an exact
binding match:

```python
contract_hash = panel_identity_hash(registry)
compatibility = registry.panel_hash_compatibility
panel_hash = (
    compatibility.published_hash
    if compatibility is not None and compatibility.contract_hash == contract_hash
    else contract_hash
)
```

- [ ] **Step 4: Bind the two published panels to their immutable hashes**

Advance both current registry files to schema 1.2 and add these reviewed
bindings:

```yaml
panel_hash_compatibility:
  panel_id: wa-2026-primary-default-sources-v4
  contract_hash: 28cd877909a1b0328175ec217dc0dc3a65010579836fd7bf3743573076a601a6
  published_hash: 389a978b149da9afdb919fdb9dfd1d4d3fbecc290d3b1cd41da3e3fd363de0b5
```

```yaml
panel_hash_compatibility:
  panel_id: wa-2026-general-default-sources-v1
  contract_hash: 28cd877909a1b0328175ec217dc0dc3a65010579836fd7bf3743573076a601a6
  published_hash: b0fb2a603bd98da49d3282d2daa0cb55ff56e0bbdd46104c8b5a4a441b747a95
```

- [ ] **Step 5: Run the source and snapshot tests and record GREEN evidence**

Run:

```bash
uv run pytest tests/test_sources.py tests/test_general_source_panel.py tests/test_personalization.py -q
```

Expected: all pass; the committed snapshot JSON files remain unchanged.

- [ ] **Step 6: Commit the stable identity boundary**

```bash
git add \
  src/election_guide/sources/models.py \
  src/election_guide/sources/panel.py \
  config/sources/default.yaml \
  config/sources/wa-2026-general.yaml \
  tests/test_sources.py \
  tests/test_general_source_panel.py
git commit -m "feat: separate stable panel identity"
```

### Task 2: Carry both hashes through publication metadata

**Files:**
- Modify: `src/election_guide/publication/models.py`
- Modify: `src/election_guide/publication/builder.py`
- Modify: `src/election_guide/rendering/payload.py`
- Modify: `src/election_guide/rendering/templates/types/client-payload.d.ts`
- Modify: `tests/test_publication.py`
- Modify: `tests/test_personalization.py`
- Modify: `tests/test_rendering.py`

**Interfaces:**
- Consumes: `build_panel_snapshot` and `source_registry_hash`.
- Produces: publication schema 1.14 with `metadata.source_panel_hash` bound to stable identity and `metadata.source_registry_hash` bound to the complete registry.

- [ ] **Step 1: Add failing publication-boundary tests**

Add assertions against a built bundle:

```python
snapshot = build_panel_snapshot(registry)
metadata = bundle.view_model.metadata
assert metadata.source_panel_hash == snapshot.panel_hash
assert metadata.source_registry_hash == source_registry_hash(registry)
assert metadata.source_panel_hash != metadata.source_registry_hash
assert bundle.view_model.personalization.panel_hash == metadata.source_panel_hash
```

Add a model-validation test proving schema 1.14 rejects a missing
`source_registry_hash`, while a serialized schema 1.13 fixture without the
field still validates.

- [ ] **Step 2: Run the publication tests and record RED evidence**

Run:

```bash
uv run pytest \
  tests/test_publication.py \
  tests/test_personalization.py::test_version_bindings_match_the_published_panel \
  -q
```

Expected: failures show that publication metadata still assigns the complete
registry hash to `source_panel_hash` and has no `source_registry_hash`.

- [ ] **Step 3: Update publication models and builder wiring**

Allow `PublicationViewModel.schema_version` values `"1.13"` and `"1.14"`.
Add an optional `source_registry_hash` to `PublicationMetadata`, then validate
at the `PublicationViewModel` boundary that schema 1.14 requires it and schema
1.13 omits it.

Build one panel snapshot in `_build_view_model`, assign:

```python
source_panel_hash=snapshot.panel_hash,
source_registry_hash=source_registry_hash(dataset.source_registry),
```

Pass that same `PanelSnapshot` into `_personalization` so metadata and the
browser contract cannot be computed from different projections. Keep the
payload's `panel_hash` sourced from `metadata.source_panel_hash`; do not expose
`source_registry_hash` through client codec bindings.

- [ ] **Step 4: Regenerate client declarations and verify payload isolation**

Run:

```bash
make types
uv run pytest tests/test_publication.py tests/test_personalization.py tests/test_rendering.py -q
npm test -- --test-name-pattern='panel|fragment|lens'
```

Expected: Python tests pass, generated declarations match Pydantic models, and
the browser tests continue binding links only to the stable panel hash.

- [ ] **Step 5: Commit the publication contract**

```bash
git add \
  src/election_guide/publication/models.py \
  src/election_guide/publication/builder.py \
  src/election_guide/rendering/payload.py \
  src/election_guide/rendering/templates/types/client-payload.d.ts \
  tests/test_publication.py \
  tests/test_personalization.py \
  tests/test_rendering.py
git commit -m "feat: publish panel and registry hashes"
```

### Task 3: Preserve complete registry identity in release artifacts

**Files:**
- Modify: `src/election_guide/release/models.py`
- Modify: `src/election_guide/release/builder.py`
- Modify: `src/election_guide/release/comparison.py`
- Modify: `tests/test_release.py`
- Create: `tests/test_release_comparison.py`

**Interfaces:**
- Consumes: the two publication metadata hashes from Task 2.
- Produces: release manifest/status schema 1.3 records with stable `source_panel_hash` and complete `source_registry_hash`; schema 1.1/1.2 artifacts remain readable.

- [ ] **Step 1: Add failing release audit tests**

Extend release-build assertions by loading the emitted manifest and publication
view model from the real bundle:

```python
manifest = ReleaseManifest.model_validate(
    read_json(release.bundle_dir / "release-manifest.json")
)
view_model = PublicationViewModel.model_validate(
    read_json(release.bundle_dir / "data/publication_view_model.json")
)
assert release.status.source_panel_hash == view_model.metadata.source_panel_hash
assert release.status.source_registry_hash == view_model.metadata.source_registry_hash
assert manifest.source_panel_hash == release.status.source_panel_hash
assert manifest.source_registry_hash == release.status.source_registry_hash
```

Add validation cases proving schema 1.3 rejects a missing full-registry hash,
and checked-in schema 1.1/1.2-shaped dictionaries without the new field remain
valid. Add a comparison test in which panel hashes match but registry hashes
differ; the release verifier must report complete-input drift.

- [ ] **Step 2: Run release tests and record RED evidence**

Run:

```bash
uv run pytest tests/test_release.py tests/test_release_comparison.py -q
```

Expected: failures identify the absent `source_registry_hash` and the release
comparison's inability to distinguish discovery-input drift.

- [ ] **Step 3: Evolve release schemas without rewriting history**

Update both release models to accept their existing versions plus `"1.3"`.
Add:

```python
source_registry_hash: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
```

Model validators require it for schema 1.3 and reject it for older versions.
Make new builders emit schema 1.3 and populate both hashes from the publication
metadata. In `release/comparison.py`, require manifest and status registry
hashes to agree when either artifact is schema 1.3; preserve the old comparison
for legacy pairs.

- [ ] **Step 4: Run release tests and record GREEN evidence**

Run:

```bash
uv run pytest tests/test_release.py tests/test_release_comparison.py -q
```

Expected: all pass, including legacy artifact validation and full-input drift
detection.

- [ ] **Step 5: Commit the release audit split**

```bash
git add \
  src/election_guide/release/models.py \
  src/election_guide/release/builder.py \
  src/election_guide/release/comparison.py \
  tests/test_release.py \
  tests/test_release_comparison.py
git commit -m "feat: audit full source registry in releases"
```

### Task 4: Verify both identities during hosting and deployment

**Files:**
- Modify: `src/election_guide/hosting/models.py`
- Modify: `src/election_guide/hosting/pages.py`
- Modify: `tests/test_hosting_models.py`
- Modify: `tests/test_hosting.py`
- Modify: `tests/test_hosting_releases.py`

**Interfaces:**
- Consumes: release schema 1.3 status and manifest records.
- Produces: optional legacy-readable `source_registry_hash` declarations and exact comparisons for new site/deployment artifacts.

- [ ] **Step 1: Add failing hosting integrity tests**

Add a new-release fixture with distinct panel and registry hashes. Assert
staging copies both into `DeployedElection`, and verification rejects either a
declared-vs-deployed mismatch or a deployed-vs-release-status mismatch in the
registry hash. Retain one legacy fixture with no registry hash and assert it
still validates.

- [ ] **Step 2: Run hosting tests and record RED evidence**

Run:

```bash
uv run pytest tests/test_hosting_models.py tests/test_hosting.py tests/test_hosting_releases.py -q
```

Expected: new fixtures fail because hosting models and comparison maps carry
only `source_panel_hash`.

- [ ] **Step 3: Thread the registry hash through hosting models and checks**

Add this field to `PublishedElection` and `DeployedElection`:

```python
source_registry_hash: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
```

When staging a schema 1.3 release, copy the non-null value into the deployment
manifest. Extend `_verify_bundle` and `verify_staged_pages_site` comparison maps
with `source registry hash`; require equality when the release provides it,
while accepting absent values for legacy releases.

- [ ] **Step 4: Run hosting tests and record GREEN evidence**

Run:

```bash
uv run pytest tests/test_hosting_models.py tests/test_hosting.py tests/test_hosting_releases.py -q
```

Expected: all pass; new artifacts compare both identities and old declarations
remain readable.

- [ ] **Step 5: Commit hosting verification**

```bash
git add \
  src/election_guide/hosting/models.py \
  src/election_guide/hosting/pages.py \
  tests/test_hosting_models.py \
  tests/test_hosting.py \
  tests/test_hosting_releases.py
git commit -m "feat: verify source registry identity in hosting"
```

### Task 5: Document the panel lifecycle and complete verification

**Files:**
- Modify: `docs/POST_ELECTION_RETROSPECTIVE.md`
- Modify: `docs/COLLECTION.md`
- Modify: `docs/runbooks/endorsement-discovery-sweep.md`
- Modify: `docs/RELEASE.md`
- Modify: files changed by `make format` or `make types` only when those tools produce ticket-scoped updates.

**Interfaces:**
- Consumes: the final names and schema behavior from Tasks 1-4.
- Produces: operator-facing rules that distinguish a discovery refresh, a panel-version change, and a complete release-input change.

- [ ] **Step 1: Update the human contracts**

Document the exact projection field list from the design. State explicitly:

```text
A discovery refresh changes source_registry_hash and therefore release audit
identity. It does not change panel_hash and does not require a panel version
bump. A membership, transport-code, selectable-category, role, eligibility,
overlap, attribution, or retired-code migration change changes panel_hash and
must be published under a new panel version.
```

Explain that existing compatibility bindings preserve already-published hashes
only while their canonical projection matches, and that published snapshot
catalog entries are never rewritten.

- [ ] **Step 2: Run formatting and focused validation**

Run:

```bash
make format
uv run pytest \
  tests/test_sources.py \
  tests/test_general_source_panel.py \
  tests/test_personalization.py \
  tests/test_publication.py \
  tests/test_release.py \
  tests/test_release_comparison.py \
  tests/test_hosting_models.py \
  tests/test_hosting.py \
  tests/test_hosting_releases.py \
  -q
npm test -- --test-name-pattern='panel|fragment|lens'
```

Expected: every focused Python and JavaScript test passes with no warnings or
unexpected output.

- [ ] **Step 3: Prove the published snapshots were not rewritten**

Run:

```bash
git diff --exit-code origin/main -- \
  data/releases/wa-2026-primary/panel-snapshots.json \
  data/releases/wa-2026-general/panel-snapshots.json
uv run election-guide sources snapshot \
  config/sources/wa-2026-general.yaml \
  --catalog-path data/releases/wa-2026-general/panel-snapshots.json
git diff --exit-code -- data/releases/wa-2026-general/panel-snapshots.json
```

Expected: both diff checks exit zero; snapshot generation reports the existing
general panel without modifying its catalog.

- [ ] **Step 4: Run the complete repository gates**

Run:

```bash
make check
make check-release-reproducible
```

Expected: both commands exit zero.

- [ ] **Step 5: Commit documentation and mechanical formatting**

```bash
git add \
  docs/POST_ELECTION_RETROSPECTIVE.md \
  docs/COLLECTION.md \
  docs/runbooks/endorsement-discovery-sweep.md \
  docs/RELEASE.md
git add -u
git commit -m "docs: define panel identity lifecycle"
```

- [ ] **Step 6: Verify the final candidate is clean and complete**

Run:

```bash
git status --short
git diff --check origin/main...HEAD
git log --oneline origin/main..HEAD
```

Expected: the worktree is clean, diff checking emits no errors, and history
contains only issue #436's design and implementation commits.
