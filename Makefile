.PHONY: sync format check test

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

test:
	uv run pytest
