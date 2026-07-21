.PHONY: sync format check test release-verify hosting-stage hosting-serve hosting-deploy

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

hosting-stage:
	uv run election-guide hosting stage dist/primary-release/bundle \
		--expected-git-commit "$$(git rev-parse HEAD)"

hosting-serve: hosting-stage
	npm run pages:dev

hosting-deploy: hosting-stage
	npm run pages:deploy -- --commit-hash="$$(git rev-parse HEAD)" --commit-dirty=false
