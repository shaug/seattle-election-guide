.PHONY: sync format check check-results check-js check-changelog changelog types test release-verify hosting-stage hosting-serve hosting-deploy

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
	uv run election-guide calendar validate config/calendar/elections.yaml
	uv run election-guide release verify data/releases/wa-2026-primary/source-decisions.yaml
	$(MAKE) check-results
	$(MAKE) check-js
	$(MAKE) check-changelog

# Validate every committed results file (issue #283). No file is committed
# there yet -- #284 owns ingestion -- so this is a no-op until one lands, but
# every file that does land is enforced from here on.
check-results:
	for results_file in data/results/*.yaml; do \
		[ -e "$$results_file" ] || continue; \
		uv run election-guide results validate "$$results_file" || exit 1; \
	done

changelog:
	npm run changelog

# CHANGELOG.md is generated, so the committed copy has to be the one the current
# history produces. Regenerate into a scratch file and compare (issue 216).
check-changelog:
	npm run changelog:version
	mkdir -p dist
	npx git-cliff --config cliff.toml --output dist/CHANGELOG.check.md
	cmp CHANGELOG.md dist/CHANGELOG.check.md

# Lint and format first, then types, then behavior: a formatting or typing
# failure is cheaper to read than a test failure caused by the same mistake
# (docs/FRONTEND.md, Dependencies and Testing).
check-js:
	npm run lint
	npm run typecheck
	node --test 'tests/js/**/*.test.mjs'

# Regenerate the client payload declarations from the Pydantic models
# (docs/FRONTEND.md, The data contract). Committing the output is what lets
# `tsc` hold every client module to it without a Python run;
# `tests/test_client_payload_types.py` regenerates during `pytest` and fails
# when the committed file and the models disagree.
types:
	uv run python -c "from election_guide.rendering.payload import generate_client_payload_types as g; g()"

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
