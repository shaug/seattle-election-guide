# Contributing

Work is organized through GitHub issues and focused pull requests. Do not commit directly to
`main`.

## Local checks

```bash
make sync
make check
```

`make sync` installs both toolchains from their lockfiles (`uv sync --frozen`
and `npm ci`). Node is not optional: rendering bundles each page's client entry
module with the pinned esbuild, so `pytest` and `election-guide release build`
both need `node_modules` present (docs/FRONTEND.md, Modules).

`make check` ends in `make check-js`, which lints and format-checks the client
modules with Biome, type-checks them with `tsc --noEmit --checkJs`, and then
runs the Node tests. `make format` fixes both languages: ruff for Python,
`biome check --write` for JavaScript.

`make types` regenerates the client payload declarations from the Pydantic
models (docs/FRONTEND.md, The data contract). Run it after changing anything
the payload publishes and commit the result; `make check` fails while the
committed declarations and the models disagree.

## Pull requests

- Link the issue that defines the scope.
- Keep collection, normalization, scoring, and rendering concerns separable.
- Add fixture-based tests for every source adapter.
- Never make ordinary tests depend on live websites.
- Document new policy or methodology choices before using them to score real data.
- State exactly what was verified and what remains incomplete.

Write commit subjects in the conventional form (`feat:`, `fix:`, `docs:`, `build:`) — they are the
text of the changelog entry. `CHANGELOG.md` is generated from history by
[git-cliff](https://git-cliff.org) and must never be hand-edited; `make check` regenerates it and
fails when the committed copy differs. After a merge changes history, run:

```bash
npm run changelog
```

## Adding sources

Register the organization and its eligibility before collecting results. Record discovery status
even when no current endorsement is found. A new adapter must preserve captures, produce
evidence-linked claims, and include stable local fixtures.

## Adding elections

Create a new election configuration and authoritative race inventory. Do not copy candidates or
races forward from a prior election without current official evidence.
