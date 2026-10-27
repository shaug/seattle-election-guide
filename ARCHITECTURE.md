# Architecture

## System boundary

The project converts official election inventories and captured endorsement evidence into
reviewed, normalized decisions and publication artifacts. Live collection is separate from a
normal build so identical captured inputs can be rebuilt deterministically.

```text
election and source configuration
              |
              v
evidence captures or observed-only provenance
              |
              v
extracted claims -> review decisions and overrides
              |
              v
canonical normalized JSONL
              |
              v
deterministic scoring
              |
              v
single publication view model
              |
              +-> JSON and CSV
              +-> responsive, printable HTML
```

## Authoritative data

Diffable YAML, canonical JSON records, and assembled JSONL files are the authoritative project
records. SQLite may be generated as a query index, but it is not the only copy of canonical data.
Raw captures are addressed by content hash and governed by `SOURCE_POLICY.md`.

## Components

- **Configuration:** elections, jurisdictions, sources, scoring, and rendering policy.
- **Collection:** HTTPX for static content and Playwright only when browser rendering is
  necessary. Collection never runs as an implicit part of publication.
- **Evidence storage:** Retained restricted plaintext artifacts are stored by SHA-256 outside Git.
  Recurring verification explicitly selects `facts_only`: private temporary responses produce
  observed-only manifests, factual snapshots, checks and approvals in Git, without new full-page
  plaintext or ciphertext. Endorsement facts, official URL, actual check timestamp and actual
  reviewer/review timestamp are sufficient durable evidence. Observed metadata and hashes cannot
  prove retained original bytes or publisher authorship; full-page reconstruction is not promised.
  Unrelated refresh callers default to `retain_original`; permitted official-authority bytes remain
  tracked directly. Legacy records and ciphertext retain their IDs and bytes. Normal validation
  checks public source/hash/time/reference integrity and legacy envelope metadata without
  decryption or an evidence key. Failed or inaccessible sources remain explicit.
- **Extraction:** source-specific adapters produce evidence-linked claims without deciding
  ambiguous matches silently.
- **Review:** manual transcriptions, approvals, and overrides are append-only data with author,
  reason, evidence locator, capture identity, and review status. First/changed/unapproved factual
  baselines require official-source review. Unchanged automated observations reuse the exact
  prior approval without claiming a new personal source read; check and review times stay distinct.
  Migration preserves existing approvals and failures and grants no new review. Retained-original
  manual transcription still requires byte verification; observed-only approval uses factual records.
- **Normalization:** race and candidate matching is constrained to the authoritative election
  inventory. Exact and normalized aliases precede race-scoped fuzzy matching; ambiguity produces
  an immutable review item rather than a guessed selection. Endorsement allocations use exact
  rational values.
- **Scoring:** exact allocations, configured eligibility, coverage signals, ties, grades, and a
  separate Seattle Times comparison. A standard score build rejects unresolved high-severity
  review work; an explicitly allowed exceptional build carries machine-readable warnings.
- **Publication exports:** one validated builder derives canonical JSON and CSV exports,
  provenance and build manifests, and a presentation-neutral view model from canonical data and
  the authoritative consensus report.
- **Rendering:** one autoescaped Jinja document and stylesheet consume the strict publication view
  model. Screen CSS supplies responsive filtering and source evidence; a modest print stylesheet
  makes that same page legible from the browser's own print output, so no second rendering of the
  guide exists. Chromium produces the responsive screenshots the validation report references.
  Renderers do not independently calculate scoring or display semantics.
- **Validation:** structural, provenance, scoring, semantic-render, and visual checks block
  publication on serious errors.

## Dependency strategy

Dependencies are added with the issue that first uses them. The rendering layer therefore carries
Jinja, Pillow, and a small Chrome DevTools client; Chrome/Chromium remains an explicit system
requirement. Issue #4 ingests already obtained local artifacts, while automated network
fetching remains the responsibility of issue #10.

## Determinism

Normalized, review, and consensus records use exact rational values and canonical serialization.
Append-only records are stored separately so concurrent reviews do not rewrite shared history.
Build timestamps are explicit inputs. The consensus input hash covers the complete canonical
dataset and scoring policy. Release manifest schema 1.2 hashes every included artifact except its
explicitly declared desktop and mobile rasterized screenshots; the published whole-bundle hash
still protects those exact files. The release reproducibility guarantee applies to the Linux
deployment environment. Browser checks use emulated CSS viewports and reject horizontal overflow
before capturing screenshots. Tests must not depend on live websites.

## Automatic release boundary

A reviewed publication request binds ledger, dataset and registry file bytes to a source revision.
Read-only PR CI builds the candidate for visual review. After merge, five independent lanes and
the stable check gate admit that exact source; serialized publication promotes its canonical ZIP
through durable issue evidence, one owned Pages upload, and two complete production probes.
The source/tag/bundle/upload identity is one full SHA. GitHub artifact IDs and wrapper digests
are temporary transport evidence, separate from immutable canonical archive identity.

Release policy lives in the declaration, candidate, publication, promotion, and evidence modules.
The workflow adapter binds Actions outputs and GitHub deployment envelopes to those policies;
workflow shell does not reimplement them. Verification-only recovery reads the original Git
object and upload receipt, preserving provenance without rebuilding or uploading. Failed evidence
keeps delivery incomplete and retryable. Historical two-revision lineage checks remain unchanged.

## Offline precinct personalization (#608)

The November2026 general precinct catalog is a hash-bound publication input.
Admission validates the entire reviewed electorate and every covered jurisdiction
before building source-independent contest-ID sets. Publication and the browser
perform no geography network requests. Voter selection changes displayed membership
only, preserving canonical inventory, scoring inputs, source eligibility and existing
section order. The general-only catalog is shared by both list views; primary
archives and legacy payloads remain readable without the optional contract.
The contract contains all geographically applicable public contest IDs, independent
of the general view's race mode. Contested is the general default; an explicit All
override includes eligible uncontested races. Both modes preserve applicable measures.
The browser applies race mode after geography without changing section order.

## Ballot presentation

The November 2026 publication builder consumes the versioned, reviewed
`publication/ballot_orders/wa-2026-general.v1.json` map. It validates the complete
inventory before selecting visible contests and derives the existing shared
section/race view-model order. This presentation input is separate from canonical
inventory/choice order and scoring inputs; no source retrieval occurs in builds.
The map is election-scoped package data, with supplied-PDF provenance and visual
locators. Other elections preserve their legacy presentation. #608 owns voter
membership independently; filtering preserves the supplied relative order.
