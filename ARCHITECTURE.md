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

Diffable YAML and JSONL files are the authoritative project records. SQLite may be generated as
a query index, but it is not the only copy of canonical data. Raw captures are addressed by
content hash and governed by `SOURCE_POLICY.md`.

## Components

- **Configuration:** elections, jurisdictions, sources, scoring, and rendering policy.
- **Collection:** HTTPX for static content and Playwright only when browser rendering is
  necessary. Collection never runs as an implicit part of publication.
- **Extraction:** source-specific adapters produce evidence-linked claims without deciding
  ambiguous matches silently.
- **Review:** approvals and overrides are append-only data with author, reason, and evidence.
- **Normalization:** race and candidate matching is constrained to the authoritative election
  inventory.
- **Scoring:** exact allocations, configured eligibility, coverage signals, ties, grades, and a
  separate Seattle Times comparison.
- **Rendering:** Jinja templates build one view model for responsive HTML and Chromium PDF.
- **Validation:** structural, provenance, scoring, semantic-render, and visual checks block
  publication on serious errors.

## Dependency strategy

The initial package deliberately includes only CLI, validation, and test dependencies. HTTP,
browser, PDF, and rendering dependencies are added with the issue that first uses them. This
keeps the bootstrap reviewable and avoids choosing adapters before discovery evidence exists.

## Determinism

Normalized records use stable identifiers and canonical serialization. Build timestamps are
inputs. Manifests hash configuration, snapshots, normalized data, and published outputs. Tests
must not depend on live websites.
