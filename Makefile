.PHONY: sync format check check-js test release-verify hosting-stage hosting-serve hosting-deploy

sync:
	uv sync --frozen
	npm ci

format:
	uv run ruff format .
	uv run ruff check --fix .
	npm run lint:fix

check:
	uv run ruff format --check .
	uv run ruff check .
	uv run pyright
	uv run pytest
	uv run election-guide inventory validate data/normalized/wa-2026-primary-inventory.json
	uv run election-guide sources validate config/sources/default.yaml
	uv run election-guide release verify data/releases/wa-2026-primary/source-decisions.yaml
	$(MAKE) check-js

# Lint and format first, then types, then behavior: a formatting or typing
# failure is cheaper to read than a test failure caused by the same mistake
# (docs/FRONTEND.md, Dependencies and Testing).
check-js:
	npm run lint
	npm run typecheck
	node --test 'tests/js/**/*.test.mjs'

test:
	uv run pytest

release-verify:
	uv run election-guide release verify data/releases/wa-2026-primary/source-decisions.yaml

hosting-stage:
	uv run election-guide hosting stage config/hosting/site.yaml \
		--bundle wa-2026-primary-2026-primary.2=dist/primary-release/bundle \
		--expected-git-commit "$$(git rev-parse HEAD)"

hosting-serve: hosting-stage
	npm run pages:dev

hosting-deploy: hosting-stage
	npm run pages:deploy -- --commit-hash="$$(git rev-parse HEAD)" --commit-dirty=false
