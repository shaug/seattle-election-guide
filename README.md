# Seattle Election Endorsement Consensus Guide

An auditable publishing pipeline for comparing endorsements in elections that appear on
Seattle ballots. The immediate release target is the August 4, 2026 Washington primary.

This project is an endorsement aggregation, not an official voter pamphlet and not an
independent evaluation of every candidate. Accuracy, provenance, and explicit uncertainty
take priority over coverage.

## Status

The authoritative August 2026 Seattle ballot inventory is implemented and validated. No
endorsement data or voter recommendation has been published yet. See [PROJECT.md](PROJECT.md)
for the product specification, [DECISIONS.md](DECISIONS.md) for the launch contract, and
[docs/BALLOT_INVENTORY.md](docs/BALLOT_INVENTORY.md) for inventory scope and reproduction.

## Development

Requirements:

- Python 3.12 or newer
- [uv](https://docs.astral.sh/uv/)

Install the locked environment and run the checks:

```bash
uv sync --frozen
uv run election-guide --help
uv run election-guide inventory validate
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
