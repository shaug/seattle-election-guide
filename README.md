# Seattle Elections Guide

An auditable publishing pipeline for comparing endorsements in elections that appear on
Seattle ballots. The immediate release target is the August 4, 2026 Washington primary.

This project is an endorsement aggregation, not an official voter pamphlet and not an
independent evaluation of every candidate. Accuracy, provenance, and explicit uncertainty
take priority over coverage.

## Why this exists

For about two decades I voted the way a lot of Seattle did: I read The Stranger, and
mostly nothing else. "Seattle's Only Newspaper" was never literally true, but it was
honest about its ambition — a progressive city deserved a voice loud enough to speak for
it, and for a long time that voice was theirs.

I don't vote that way any more. The paper changed hands, and my confidence in it as a
sole source didn't survive the change. That is my judgment about my own ballot, not a
finding about theirs; what follows from it is this site.

The mistake, in hindsight, was not trusting The Stranger. It was trusting *one* voice at
all. A single voice can be sold, staffed differently, or simply change its mind, and a
reader who has handed it their ballot is the last to find out. What replaces a trusted
voice is not a better trusted voice — it's evidence you can check yourself.

So this guide counts many voices and shows its work. Every endorsement is listed, linked
to the source that published it, and counted in the open; you choose which sources count
for you, and the numbers recompute in front of you. **The Stranger is still one of those
sources.** Removing them would miss the point entirely — they are a real signal, and this
site's answer to a single voice was never to silence it. It was to stop letting any one
of them speak alone.

The writing here is confident on purpose. Seattle is a progressive city and deserves a
guide that sounds like it believes so. The difference is what the confidence rests on:
not a masthead, not a byline, not anyone's employment history, but an aggregate you can
audit one receipt at a time. See [docs/DESIGN.md](docs/DESIGN.md), "Voice," for the rule
that keeps it honest.

## Status

The authoritative August 2026 Seattle ballot inventory is implemented and validated. The default
source panel is frozen before scoring, with 48 proposed organizations assigned explicit discovery and
panel statuses. Content-addressed local evidence capture, integrity verification, unavailable-source
records, structured manual transcription, deterministic race-scoped normalization, append-only
ambiguity review, and immutable source-adapter refreshes are implemented. No recommendation is
treated as complete coverage. The audited primary ledger contains 521 decisions from 41 represented
source publications; release status explicitly lists the two remaining active sources with access or
discovery constraints. Exact deterministic consensus scoring, coverage signals, audit-only
grade and tie handling, comparison-only Seattle Times results, and the unresolved-review publication
gate are also implemented. Responsive HTML and the
two-page US Letter guide now present candidate-centric endorsement consensus without voter-facing
letter grades, while retaining the complete source matrix and scoring artifacts for audit. Public
guides are composed into a manifest-backed archive under stable `/e/<election-id>/` routes; the
bare domain temporarily redirects to the explicitly declared current election. A site-wide
`/about/` page explains the methodology, source-panel versioning, and correction path in plain
language for voters, with reciprocal navigation to and from every guide.
See [PROJECT.md](PROJECT.md) for the
product specification, [DECISIONS.md](DECISIONS.md) for the launch contract,
[docs/ELECTION_CALENDAR.md](docs/ELECTION_CALENDAR.md) for the declared election cadence and the
milestones it schedules,
[docs/POST_ELECTION_RETROSPECTIVE.md](docs/POST_ELECTION_RETROSPECTIVE.md) for the checklist each
cycle closes with,
[docs/ELECTION_INITIALIZATION.md](docs/ELECTION_INITIALIZATION.md) for starting future elections,
[docs/BALLOT_INVENTORY.md](docs/BALLOT_INVENTORY.md) for inventory scope and reproduction,
[docs/SOURCE_DISCOVERY.md](docs/SOURCE_DISCOVERY.md) for the source panel,
[docs/SOURCE_PANEL_EXPANSION_2026-07-23.md](docs/SOURCE_PANEL_EXPANSION_2026-07-23.md) for the
six-source evaluation and deterministic scoring impact,
[docs/EVIDENCE_CAPTURE.md](docs/EVIDENCE_CAPTURE.md) for evidence handling,
[docs/COLLECTION.md](docs/COLLECTION.md) for automated source refreshes,
[docs/NORMALIZATION.md](docs/NORMALIZATION.md) for matching and review,
[docs/SCORING.md](docs/SCORING.md) for consensus semantics, and
[docs/PUBLICATION_EXPORTS.md](docs/PUBLICATION_EXPORTS.md) for canonical exports and the shared
publication view model, and [docs/RENDERING.md](docs/RENDERING.md) for HTML generation and visual
inspection. [docs/RELEASE.md](docs/RELEASE.md) documents final audit and versioned GitHub
Release publication, and [docs/HOSTING.md](docs/HOSTING.md) documents automatic Cloudflare Pages
deployment with Wrangler. [docs/DEPENDENCY_UPDATES.md](docs/DEPENDENCY_UPDATES.md) documents the
scheduled, grouped Dependabot updates and the election-window exclusion. Deterministic JSON and
CSV exports, provenance and build manifests, the complete source matrix, and the single
renderer-facing view model are implemented.

## Development

Requirements:

- Python 3.12 or newer
- [uv](https://docs.astral.sh/uv/)
- Chrome or Chromium
- Node.js 24 and npm for local Cloudflare Pages preview or deployment

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
uv run election-guide hosting stage --help
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
