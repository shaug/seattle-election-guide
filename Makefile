.PHONY: sync format check check-results check-js check-changelog check-release-reproducible changelog types test release-verify hosting-stage hosting-serve hosting-deploy

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

# The release-reproducibility gate, defined once here and invoked by CI, the way
# check-js and check-changelog already are (issue #367). Two builds of one
# commit must produce one release.
#
# Two comparisons, because they cover different things. `diff -rq` walks the
# unpacked bundles and names the artifact that differs -- which is the whole
# reason this replaced a bare `cmp`, whose single offset into compressed data
# named nothing. `cmp` then holds the archive itself to its exact bytes,
# covering what the bundles cannot show: entry order, timestamps, permissions,
# and compression settings.
#
# Not part of `make check`: `release build` refuses a dirty checkout, so on the
# tree a contributor runs `make check` against it could only fail for a reason
# unrelated to their diff (CONTRIBUTING.md, Local checks). The build timestamp
# comes from the commit, exactly as CI derives it, because `generated_at` is
# recorded in the bundle and two different values would produce two
# legitimately different releases.
RELEASE_A ?= dist/reproducibility-a
RELEASE_B ?= dist/reproducibility-b
RELEASE_ARCHIVE = seattle-election-guide-2026-primary.2.zip

check-release-reproducible:
	rm -rf $(RELEASE_A) $(RELEASE_B)
	uv run election-guide release build data/releases/wa-2026-primary/source-decisions.yaml \
		--release-version 2026-primary.2 \
		--generated-at "$$(git show -s --format=%cI HEAD)" \
		--output-dir $(RELEASE_A)
	uv run election-guide release build data/releases/wa-2026-primary/source-decisions.yaml \
		--release-version 2026-primary.2 \
		--generated-at "$$(git show -s --format=%cI HEAD)" \
		--output-dir $(RELEASE_B)
	diff -rq $(RELEASE_A)/bundle $(RELEASE_B)/bundle
	cmp $(RELEASE_A)/$(RELEASE_ARCHIVE) $(RELEASE_B)/$(RELEASE_ARCHIVE)

hosting-stage:
	uv run election-guide hosting stage config/hosting/site.yaml \
		--bundle wa-2026-primary-2026-primary.2=dist/primary-release/bundle \
		--released-bundle-dir dist/released-bundles \
		--expected-git-commit "$$(git rev-parse HEAD)"

hosting-serve: hosting-stage
	npm run pages:dev

hosting-deploy: hosting-stage
	npm run pages:deploy -- --commit-hash="$$(git rev-parse HEAD)" --commit-dirty=false
