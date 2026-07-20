# Architecture

## System boundary

The project converts official election inventories and captured endorsement evidence into
reviewed, normalized decisions and publication artifacts. Live collection is separate from a
normal build so identical captured inputs can be rebuilt deterministically.

```text
election and source configuration
              |
              v
content-addressed evidence captures
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
              +-> responsive HTML
              +-> print HTML -> PDF
```

## Authoritative data

Diffable YAML, canonical JSON records, and assembled JSONL files are the authoritative project
records. SQLite may be generated as a query index, but it is not the only copy of canonical data.
Raw captures are addressed by content hash and governed by `SOURCE_POLICY.md`.

## Components

- **Configuration:** elections, jurisdictions, sources, scoring, and rendering policy.
- **Collection:** HTTPX for static content and Playwright only when browser rendering is
  necessary. Collection never runs as an implicit part of publication.
- **Evidence storage:** Locally obtained artifacts are stored by SHA-256 outside Git. Immutable
  JSON manifests preserve retrieval metadata and redistribution constraints; unavailable sources
  remain explicit metadata-only records.
- **Extraction:** source-specific adapters produce evidence-linked claims without deciding
  ambiguous matches silently.
- **Review:** manual transcriptions, approvals, and overrides are append-only data with author,
  reason, evidence locator, capture identity, and review status.
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
  model. Screen CSS supplies responsive filtering and source evidence; print CSS supplies the
  concise US Letter edition. Content that cannot fit at the configured font floor uses a compact
  two-page plus detailed-edition fallback. Chromium renders both, while Pypdf normalizes document
  metadata and Poppler produces page images for inspection. Renderers do not independently
  calculate scoring or display semantics.
- **Validation:** structural, provenance, scoring, semantic-render, and visual checks block
  publication on serious errors.

## Dependency strategy

Dependencies are added with the issue that first uses them. The rendering layer therefore carries
Jinja, Pillow, Pypdf, and a small Chrome DevTools client; Chrome/Chromium and Poppler remain explicit
system requirements. Issue #4 ingests already obtained local artifacts, while automated network
fetching remains the responsibility of issue #10.

## Determinism

Normalized, review, and consensus records use exact rational values and canonical serialization.
Append-only records are stored separately so concurrent reviews do not rewrite shared history.
Build timestamps are explicit inputs. The consensus input hash covers the complete canonical
dataset and scoring policy. Manifests hash configuration, snapshots, normalized data, and
published outputs. PDF metadata is derived from the publication timestamp. Browser checks use an
emulated CSS viewport so mobile validation is identical on macOS and Linux, and reject horizontal
overflow before capturing screenshots. Tests must not depend on live websites.
