# General release audit and publication

The release workflow turns the reviewed source-decision ledger into a reproducible public bundle.
It does not imply comprehensive source coverage. Gaps remain visible in the guide and in
`release-status.json`; missing coverage is never counted as opposition.

## Public update log

Compare the candidate with the currently published guide before publication. Every change to
the published aggregate or a position page requires an entry in
`data/corrections/<election-id>.yaml`, which renders as **Updates** at the election's
`/updates/` address. Include the entry in the same change as the publication inputs or rendering
behavior it describes. The stored `corrections` names remain compatible with existing releases.

Newly published or previously missed endorsements count, even if the leading choice stays
the same. Record changed counts, shares, source coverage, evidence, displayed races, and results
as well as corrected or withdrawn endorsements. Explain what changed and why; link the evidence
and affected pages. A batch entry must link a complete account of its changes. A refresh that
leaves published content unchanged needs no entry. The editorial rule is in
[RESULTS.md, The updates page](RESULTS.md#the-updates-page).

The update log ships with the release that publishes the changes. Keep historical entries and
immutable release bundles intact. An update's date does not assert when a source announced its
endorsement.

`make check-updates` enforces this policy after staging. It compares both elections' aggregate
and position pages with the last successful production deployment, including the archived
election's pages rendered by current code. It runs in the required Publication build lane and
again before the serialized production upload. Its JSON report lists changed pages and the new
entries actually present in each affected election's served `/updates/` page. Editing repository
YAML that is absent from an immutable archived bundle does not satisfy the gate: publish a new
archive containing the entry and update its reviewed pins.

Each staged site carries `updates-snapshot.json`, protected by the deployment manifest's asset
hash. It records content fingerprints and dated/headlined entry identities, so the next check
does not depend on short-lived Actions artifacts. The served source and manifest hash must match
the last verified automatic-release upload. Before the first snapshot is deployed, the
gate downloads and verifies the legacy `cloudflare-site` artifact for the successful production
revision, or the exact promotion artifact bound to a verified automatic-release receipt. A
successful job that skipped uploading cannot replace that baseline. Missing or expired bootstrap
evidence, unavailable production, a hash mismatch, or a
different served revision blocks publication; none falls back to a release tag or newer main.

The comparison includes rendered markup, CSS, client payloads, bundled code and referenced local
script/stylesheets. Only HTML comments/formatting whitespace, the footer's site-build stamp,
the data-cutoff date and input-hash labels, and the client's top-level `data_version` are
normalized. Actual source/panel identities, counts, shares, evidence, results, and behavior remain
compared, including visible word separators, non-breaking spaces, and preformatted text.
CSS and code comparisons are conservative: a change to their shipped bytes may need
an entry even when the initial visible text stays the same. An unchanged refresh needs none.
The Updates page itself is excluded, so correcting history does not require a recursive entry.

A changed election requires an additional dated/headlined entry while retaining existing entry
identities. Editing a body, replacing an old entry, or adding an entry to another election cannot
satisfy it. Correct historical dates/headlines separately from a content change so those repairs
cannot masquerade as its new entry. Review still verifies that the prose and linked batch record
explain every change; the mechanical gate enforces presence and election scope.

For an offline diagnostic against a retained production artifact:

```bash
uv run election-guide hosting check-updates dist/cloudflare-site \
  --baseline-site-dir dist/retained-production-site \
  --output-path dist/updates-check.json
```

CI and production always resolve the baseline from production; they do not use the diagnostic
override. `make check` remains offline and exercises the gate with fixtures.

## Audited inputs

`data/releases/wa-2026-general/source-decisions.yaml` contains reviewed structured transcriptions,
official URLs inherited from the frozen source registry, and short verification locators. Its
`captured_at` fields record when the reviewer actually checked each official publication. Optional
`evidence_excerpt` values are source text; the compiler never invents one from normalized values.
Because compilation imports a manual extract rather than issuing an HTTP request, its public
capture manifests do not claim an HTTP status. Full third-party HTML, PDF, browser, and restricted
captures remain outside Git.

A decision may supply a reviewed `evidence_url` when its supporting publication differs from
the registry's discovery page. The compiler groups that source's decisions by publication and
review provenance and creates a separate permitted factual extract for each group, so receipts
and exports open the supporting publication. Decisions without this field retain the registry URL
and its publication metadata. An explicit URL does not inherit the discovery page's publication or
update dates, and the compiler never infers URLs from free-text locators.

A decision may also supply all four provenance overrides: `captured_at`, `reviewed_at`, `reviewer`,
and `review_note`. They must be either all supplied or all absent/null. A complete tuple requires
an explicit valid `evidence_url` and nonblank `evidence_locator`; it cannot borrow these from the
source block. Reviewer and note text must be nonblank and respect the source-level length limits.
The decision tuple takes precedence over the source block. Without it, the existing source times
and source reviewer/note apply, with the ledger reviewer/note filling absent source values.
Omitted/null overrides serialize no new fields, preserving existing factual extracts and records.

Check and review times remain separate: `captured_at` records the actual official-publication
check, while `reviewed_at` records the named review, never an inferred publication date or extract
assembly time. Both timestamps must include a timezone; review cannot predate check, and neither
may exceed `data_as_of`. Every effective check must be at or after the registered discovery check.
The source block's own timestamp validations still apply, including when all its decisions supply
overrides. One source block per source and one decision per race within that block remain required.

Within a source, the factual-extract grouping key is the explicit URL (or its absence), effective
check time, and snapshot reviewer/note. Legacy snapshot reviewer/note retain their optional source
values before ledger fallback; complete overrides supply their explicit values. Group and decision
order follow their first appearance in the ledger. The snapshot header carries the group's check
and review attribution; projected decisions retain their URL, locator and excerpt but omit the four
override fields. Review time is excluded from the snapshot and retained on endorsements and, for
multi-candidate decisions, approvals. Changing only review time therefore preserves capture and
claim identity. Adding or changing a row within an existing identical group can change that
extract and its peers' identities; distinct provenance groups remain independent. This capability
does not add a counting source or change source-counting policy.

Compile the ledger after an editorial change:

```bash
uv run election-guide release compile \
  data/releases/wa-2026-general/source-decisions.yaml \
  --inventory-path data/normalized/wa-2026-general-inventory.json \
  --registry-path config/sources/wa-2026-general.yaml \
  --output-path data/normalized/wa-2026-general-canonical-dataset.json \
  --snapshot-root data/releases/wa-2026-general/snapshots \
  --manifest-dir data/releases/wa-2026-general/manifests
```

The compiler validates source eligibility, races, candidates, publication state, timestamps,
candidate allocation, and review provenance. It writes:

- `data/normalized/wa-2026-general-canonical-dataset.json`;
- content-addressed permitted extracts under
  `data/releases/wa-2026-general/snapshots/`; and
- immutable public capture records under `data/releases/wa-2026-general/manifests/`.

Multi-candidate decisions create a high-severity review item and a linked approval from the named
effective reviewer (decision override, source block, then ledger fallback). Their review items use
the effective check time; approvals and endorsements use the effective review time and note.
The canonical dataset therefore preserves the ambiguity boundary without leaving
publication-blocking work unresolved.

Verify exact fresh-checkout reproducibility without changing tracked files:

```bash
uv sync --frozen
uv run election-guide release verify \
  data/releases/wa-2026-general/source-decisions.yaml \
  --inventory-path data/normalized/wa-2026-general-inventory.json \
  --registry-path config/sources/wa-2026-general.yaml \
  --dataset-path data/normalized/wa-2026-general-canonical-dataset.json \
  --snapshot-root data/releases/wa-2026-general/snapshots \
  --manifest-dir data/releases/wa-2026-general/manifests
```

Verification recompiles into temporary storage and byte-compares the dataset, every permitted
snapshot, and every capture manifest. Publication of those three areas is transactional: a failed
swap restores the complete previous generation. CI runs verification and a repeated full release
build.

## Panel and registry identity

New publication view models carry two explicit identities. `source_panel_hash` is the stable
transport-facing panel hash used by personalized links and panel-version compatibility;
`source_registry_hash` is the SHA-256 of the complete validated registry, including mutable
discovery evidence. The browser payload receives only the stable panel hash because the complete
registry has no role in decoding a link or selecting sources.

New `release-status.json` and `release-manifest.json` files use schema 1.3 and require both hashes.
Release verification binds the status and manifest to the same `source_panel_id`,
`source_panel_hash`, and complete `source_registry_hash`; this detects a discovery-input change
even when the panel contract is unchanged. A discovery refresh therefore produces a new complete
release-input identity without requiring a new panel version.

Immutable release-manifest schemas 1.1 and 1.2 and release-status schema 1.2 remain readable. They
predate `source_registry_hash`, must not declare it, and retain their historical meaning rather
than being rewritten. Likewise, the archived primary's publication schema 1.9 and later schema
1.13 remain readable without the field, while new schema 1.14 publication metadata requires it.

## Prepare and review a release

Publication is automatic after merge. `config/hosting/site.yaml` selects the current release
and records the owning issue, previous published source, and SHA-256 bindings for reviewed
ledger, dataset, and registry bytes. Preparation supplies no editorial or baseline approval.

<!-- runbook-command:prepare -->
```bash
uv run election-guide release automation prepare --issue "$issue_number"
uv run election-guide release automation resolve
```

Preparation captures remote main's full SHA once, reads the declaration at that revision, and
reads all remote tag and release names, including draft release reservations. It selects the next
numeric election-scoped version above main and every occupied version. Repeating preparation
retains a higher unpublished proposal only for the same issue and previous published revision. It refreshes the derived panel and complete-registry
identities and binds the exact ledger, canonical-dataset, and registry file bytes with SHA-256.
Formatting-only changes to those files therefore require preparation again. It changes only the
current election declaration; archived declarations and their release pins remain intact.
The previous published tag is resolved from remote state to a full commit and must be an
ancestor of the checkout. Preparation fetches that exact object if it is missing locally.
It also fetches the selected named tag if absent, without fetching unrelated tags or
overwriting an existing tag, and verifies its peeled commit against the authenticated
published source. A conflicting local or fetched tag blocks preparation.
Preparation does not imply editorial or baseline approval.

If the selected declaration on captured main never published, preparation and admission may
recover its recorded `publication_request.previous_release_sha`. This requires complete,
successful remote tag and release enumeration proving that the failed version has neither
a tag nor any release reservation, including drafts. A missing local tag, failed API request,
or malformed or partial enumeration does not establish absence. The recorded source's exact
Git declaration must select the same election at a lower numeric version. That version must
have an actual published, non-prerelease GitHub Release, verified by the exact release-by-tag
resource with a matching tag name and positive release ID. Complete tag and release lists still
establish occupied names, draft reservations, and absence. Its peeled remote tag must equal the
recorded full source SHA and any declaration source pin. The recorded source must be an
ancestor of the exact captured main or comparison-base revision; ancestry only to a later
corrective checkout is insufficient.

Recovery retains the owning issue and verified published predecessor, selects a higher unused
version, and refreshes exact input-byte bindings. Admission may retain an equal
`PublicationRequest` payload only after this shared unpublished-base proof succeeds. Ordinary
published-base admission still requires a fresh request. Recovery never relaxes version
increments, clean-checkout or exact-source checks, reviewed input bindings, or archive pins.

Commit the reviewed declaration and its inputs together. Admission checks exact Git objects:

```bash
uv run election-guide release automation validate-request --base-sha "$base_sha"
```

Use a clean tracked checkout and the full comparison-base SHA. Admission rejects stale input
bindings and requires a fresh request with a version increment for changes under `src/`, `data/`,
`config/`, `scripts/`, or `.github/workflows/`, or to `Makefile`, `cliff.toml`, `pyproject.toml`,
`uv.lock`, `package.json`, `package-lock.json`, `wrangler.jsonc`, or `wrangler.toml`. This is a
conservative release policy: even a change in one of those paths that appears unrelated to the
rendered guide needs a declaration. A documentation/test-only change with an unchanged declaration
does not request a release. An absent request supports historical reading and never authorizes
automatic publication.

## Build and inspect before merge

Run `make check`, then commit the reviewed changes. From that clean candidate, run:

<!-- runbook-command:verify-general -->
```bash
make release-verify
make check-release-reproducible
uv run election-guide release automation resolve > dist/resolved.json
unzip -t "dist/reproducibility-a/$(jq -r .archive_name dist/resolved.json)"
test -f dist/reproducibility-a/bundle/RELEASE_NOTES.md
test -f dist/reproducibility-a/bundle/validation/rendering/rendering_validation_report.json
test -f dist/reproducibility-a/bundle/validation/rendering/screenshots/desktop.png
test -f dist/reproducibility-a/bundle/validation/rendering/screenshots/mobile.png
```

Inspect both screenshots, release notes, and validation reports before merging. PR CI retains
these as `candidate-review-<run>-<attempt>` for seven days. There is no mandatory screenshot
attestation after merge. The reproducibility gate compares two complete builds using the
commit-derived timestamp. Only the existing desktop/mobile rasterized screenshots are excluded
from deterministic comparison; both remain inside the whole-bundle digest and canonical ZIP.
The guarantee applies to the Linux deployment environment.

<!-- runbook-command:stage-candidate -->
```bash
source_sha="$(git rev-parse HEAD)"
make hosting-stage
uv run election-guide hosting verify \
  config/hosting/site.yaml \
  dist/cloudflare-site \
  --expected-git-commit "$source_sha"
```

## Latest manual publication boundary

The retained manual history ends at `2026-general.10`, published from
`c5a5252202d0f78bcec5e54f9f6d0dfe0841d481` with ZIP SHA-256
`466efd641d2f190f5030e6d7e8b29d58bd4dff0d96e521af51dd0c3b950b161e`.
Its reviewed input hashes and Updates backfill evidence remain in
[the backfill publication record](UPDATES_BACKFILL_RELEASE_2026-10-16.md).
The archived primary uses the canonical `2026-primary.4` source, manifest, and whole-bundle
pins from that publication. Preserve these archives and all earlier manual releases unchanged;
preparation chooses the next unused general version from current remote metadata.

An archived-election refresh needs a new immutable archive built from a clean merged
source, followed by a protected PR recording pins from its downloaded published asset.
The [primary meter refresh sequence](PRIMARY_METER_REFRESH_2026-10-22.md) records the
staged Updates preparation and activation required when current code renders an
archive's race pages while its overview and Updates remain frozen in that archive.
It does not change the automatic current-general publication path.

## Automatic delivery and evidence

The five independent CI lanes feed the stable `check` status. A reviewed release request on
main then runs `publish`, `publication-evidence`, `deploy`, and `finalize`. The tag, archive,
staged current bundle, uploaded commit, and expected production commit all identify the same
full merged `source_sha`. Documentation/test-only main commits run CI without another release.
The merged-source and lane admission reads enumerate every GitHub API page before their respective
validation. If `gh` exits with `unexpected end of JSON input` during one of these read-only paginated
GETs, admission retries the entire listing up to three attempts. A failed attempt's partial
response is discarded; exhausted reads and malformed pages stop admission. Ambiguous PR matches
and invalid lineage prevent source and producer records from being captured.

All non-PR CI runs and verification-only recovery dispatches share `verified-release-mainline`,
`queue: max`, and `cancel-in-progress: false`, serializing their durable evidence writes.
PR runs stay parallel. The queue supports 100 pending runs;
queue exhaustion is a delivery failure to investigate, never a silently discarded request.
Artifact names include producing run and attempt; consumers use captured IDs and independently
verify wrapper digests, workflow/repository identity, and attempt time boundaries. A wrapper
ZIP digest is distinct from the release asset digest. Wrapper downloads use unique managed
temporary storage outside the checkout and remove it on success and failure; extracted
artifacts remain in the requested output directory.

The publisher creates or resumes only an owned matching draft, verifies its canonical ZIP,
then publishes it. Existing archives and their screenshot bytes remain immutable. Durable
publication evidence on the owning issue must complete before upload. The final selection check
rejects stale candidates and a disabled upload switch yields `deployment_paused`; a newer
selected declaration yields `superseded`. Neither state is a successful deployment.

The owning number may identify an issue or a pull request. Durable receipts use GitHub's
[issue-comment API](https://docs.github.com/en/rest/issues/comments#create-an-issue-comment)
for either owner. Trusted publication-evidence, finalization, and verification-recovery jobs
therefore declare both `issues: write` and `pull-requests: write`; deployment declares read
access to both so it can verify the receipts. Job permission maps replace the workflow defaults,
so each declares its own required access. These grants retain the main-only delivery boundaries
and verification recovery's prohibition on rebuilding or uploading. A published archive whose
durable evidence failed is still incomplete delivery; it supplies no production acceptance (#644).

The production environment permits only main, with no extra Publish approval. Cloudflare
credentials exist only on the one pinned upload step. It saves the validated upload receipt,
stdout/stderr and upload time before recording the unique Pages URL on its owned GitHub deployment.
A failed status write leaves that exact upload recoverable from the retained artifact. Uncertain upload
outcomes require operator verification before another upload. Finalization waits at most
120 seconds for two consecutive complete strict probes at least five seconds apart and retains
all failed observations. GitHub deployment success follows durable verified evidence only.

Publication receipts include the release asset digest/ID/size, source/input hashes, canonical
bundle and manifest hashes, CI run and artifact IDs/digests. Upload/final receipts add deployment
ID, unique URL, upload time, and complete production-wait.json evidence. Local receipt writes,
probe failures, or durable issue-write failures fail delivery even when `check` is green.
Failure artifacts are retained with `always()` for seven days; issue evidence is durable.

## Recovery

Never move a tag, overwrite an archive, replace an asset, or substitute newer main. If candidate
artifacts expire before upload, rerun the original CI run or dispatch trusted main CI with its
captured source fixed through every fresh lane and build:

<!-- runbook-command:recover-candidate -->
```bash
gh workflow run ci.yml --ref main -f source_sha="$source_sha"
```

This requires the original reviewed request at an exact merged main ancestor. It rebuilds and
verifies that source and compares an existing archive against its canonical deterministic content.
Fresh attempt artifacts get fresh receipts; their stable archive identity must agree with earlier
evidence. The current checkout or latest main is never substituted for the candidate.

After any upload, retry only verification and evidence, using the original producing run/attempt:

<!-- runbook-command:retry-evidence -->
```bash
gh workflow run verify-release.yml --ref main \
  -f issue="$issue_number" \
  -f release_version="$release_version" \
  -f source_sha="$source_sha" \
  -f run_id="$run_id" \
  -f run_attempt="$run_attempt"
```

Verification-only uses trusted workflow code from main and the declaration from the original
Git object. It loads immutable upload evidence or reconstructs it only from one matching owned
deployment and an authenticated retained successful upload report. The retained receipt, when
present, must match the report exactly. An absent initial status can be recovered; existing
in-progress or success status URLs must agree with the upload. Missing, conflicting or ambiguous
evidence fails closed.
It never builds, republishes, uploads, or relabels the original upload producer.
Already successful verification is idempotent and cannot reorder an older production deployment.
`make hosting-deploy` deliberately fails with these recovery instructions.

## Software history

The pinned local git-cliff generates the bundled software history from the request's explicit
previous-release SHA through the exact candidate SHA using its declared version and timestamp.
Tags cannot change that section. `CHANGELOG.md` is a generated release index retaining manual
history through `2026-general.9`; publication needs no second changelog commit.

## Historical post-tag release lineage

The historical publication sequence through `2026-general.9` created two intentional commit
identities: the published archive is bound to `release_candidate_sha`, and a production handoff
rebuilds from a later `production_candidate_sha` after a changelog commit. The following verifier preserves
that existing two-revision contract and remains available when inspecting those archives. New
request-driven publication uses one merged source revision for the tag, archive, staged bundle,
and deployment; it requires no post-tag changelog commit. For a historical two-revision handoff,
verify the narrow boundary before handing the production bundle to `hosting stage`:

<!-- runbook-command:verify-lineage -->
```bash
uv run election-guide release verify-lineage \
  dist/downloaded/seattle-election-guide-2026-general.10.zip \
  dist/reproducibility-a/bundle \
  "$release_candidate_sha" \
  "$production_candidate_sha" \
  > dist/release-lineage-report.json
```

Both identities must be full Git commit IDs in the current repository, and the release candidate
must be an ancestor of the distinct production candidate. The command independently verifies each
bundle, including its exact declared file set and every manifest hash, before comparing anything.
Within each bundle, timestamp identities must agree as timezone-aware instants. The builder emits
both `Z` and `+00:00` for UTC; these spellings are equivalent. Different instants, missing timezones,
and malformed timestamps are rejected, including in consensus rows and the release notes.
It then requires the same election, release, source panel and registry, canonical dataset,
source-decision snapshots, scoring input, and deterministic release content.

Only these schema-owned commit-bound values are normalized: the release-status commit and build
time; consensus computation times; publication, validation, provenance, and build-manifest commit
or time fields; the consensus and artifact hashes directly derived from those fields; the two
corresponding release-note lines; the rendered guide's commit link, commit label, and site-updated
date; and the release-manifest time and directly derived artifact hashes. The report lists every
normalized path. A new field is not normalized implicitly, so adding commit-bound provenance
requires an explicit allowlist change and review. The two declared screenshots are verified as
present but remain outside cross-build byte comparison under the existing schema 1.2/1.3 contract.

The canonical JSON report exits with status 1 and records `result: fail` for invalid identity,
ancestry, bundle integrity, or content drift. Preserve it for #450 and the #440 closeout evidence.
This command verifies the general release bundle only; complete two-election route and deployment-
manifest composition remains the separate `hosting verify` gate.
