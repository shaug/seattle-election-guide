.PHONY: sync format check test release-verify

sync:
	uv sync --frozen

format:
	uv run ruff format .
	uv run ruff check --fix .

check:
	uv run ruff format --check .
	uv run ruff check .
	uv run pyright
	uv run pytest
	uv run election-guide inventory validate data/normalized/wa-2026-primary-inventory.json
	uv run election-guide sources validate config/sources/default.yaml
	uv run election-guide release verify data/releases/wa-2026-primary/source-decisions.yaml

test:
	uv run pytest

release-verify:
	uv run election-guide release verify data/releases/wa-2026-primary/source-decisions.yaml
