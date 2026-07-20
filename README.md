# Seattle Election Endorsement Consensus Guide

An auditable publishing pipeline for comparing endorsements in elections that appear on
Seattle ballots. The immediate release target is the August 4, 2026 Washington primary.

This project is an endorsement aggregation, not an official voter pamphlet and not an
independent evaluation of every candidate. Accuracy, provenance, and explicit uncertainty
take priority over coverage.

## Status

The authoritative August 2026 Seattle ballot inventory is implemented and validated. The
default source panel is frozen before scoring, with 42 proposed organizations assigned explicit
discovery and panel statuses. Content-addressed local evidence capture, integrity verification,
unavailable-source records, structured manual transcription, deterministic race-scoped
normalization, append-only ambiguity review, and immutable source-adapter refreshes are implemented.
No recommendation is treated as complete coverage. The audited primary ledger contains 383
decisions from 32 represented official source publications; release status explicitly lists the
five remaining active sources with access or discovery constraints. Exact deterministic consensus
scoring, coverage signals,
grade and tie handling, comparison-only Seattle Times results, and the unresolved-review
publication gate are also implemented. Responsive HTML and the two-page US Letter guide now render
from the shared publication view model with semantic, viewport, PDF, and page-image validation.
See [PROJECT.md](PROJECT.md) for the
product specification, [DECISIONS.md](DECISIONS.md) for the launch contract,
[docs/ELECTION_INITIALIZATION.md](docs/ELECTION_INITIALIZATION.md) for starting future elections,
[docs/BALLOT_INVENTORY.md](docs/BALLOT_INVENTORY.md) for inventory scope and reproduction,
[docs/SOURCE_DISCOVERY.md](docs/SOURCE_DISCOVERY.md) for the source panel,
[docs/EVIDENCE_CAPTURE.md](docs/EVIDENCE_CAPTURE.md) for evidence handling,
[docs/COLLECTION.md](docs/COLLECTION.md) for automated source refreshes,
[docs/NORMALIZATION.md](docs/NORMALIZATION.md) for matching and review,
[docs/SCORING.md](docs/SCORING.md) for consensus semantics, and
[docs/PUBLICATION_EXPORTS.md](docs/PUBLICATION_EXPORTS.md) for canonical exports and the shared
publication view model, and [docs/RENDERING.md](docs/RENDERING.md) for HTML/PDF generation and
visual inspection. [docs/RELEASE.md](docs/RELEASE.md) documents final audit and versioned GitHub
Release publication. Deterministic JSON and CSV exports, provenance and build manifests, the
complete source matrix, and the single renderer-facing view model are implemented.

## Development

Requirements:

- Python 3.12 or newer
- [uv](https://docs.astral.sh/uv/)
- Chrome or Chromium
- Poppler's `pdftoppm`

Install the locked environment and run the checks:

```bash
uv sync --frozen
uv run election-guide --help
uv run election-guide election init --help
uv run election-guide inventory import-initialized --help
uv run election-guide inventory validate
uv run election-guide sources validate
uv run election-guide sources report
uv run election-guide evidence --help
uv run election-guide evidence verify --help
uv run election-guide collect refresh --help
uv run election-guide normalize --help
uv run election-guide review --help
uv run election-guide score --help
uv run election-guide export build --help
uv run election-guide render build --help
uv run election-guide release verify data/releases/wa-2026-primary/source-decisions.yaml
uv run election-guide release build --help
uv run ruff format --check .
uv run ruff check .
uv run pyright
uv run pytest
```

The `Makefile` provides the same common entry points:

```bash
make sync
make check
```

## Repository policy

Source metadata, permitted evidence excerpts, normalized records, review decisions, and
provenance manifests belong in Git. Full copyrighted or access-controlled source captures do
not. See [SOURCE_POLICY.md](SOURCE_POLICY.md) and [data/README.md](data/README.md).

## License

Code and original documentation are licensed under the MIT License. Third-party election and
endorsement material retains its original ownership and is not relicensed by this repository.
