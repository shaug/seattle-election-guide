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

### One gate `make check` does not run

CI builds the primary release twice and checks that both builds are the same
release. `make check` does not, and cannot: `election-guide release build`
refuses a dirty checkout, so on the tree you actually run `make check` against
it would fail for a reason unrelated to your diff. Run it yourself, on a clean
tree, before pushing anything that touches rendering, templates, CSS, the client
modules, or the release builder:

```bash
make check-release-reproducible
```

It commits nothing and takes about half a minute. Nothing else here needs it —
a docs-only change cannot move the release build.

**When CI fails this gate.** `diff -rq` names the artifact whose bytes differ
between the two builds; if it passes and `cmp` still fails, the difference is in
the archive container rather than its contents. Every artifact is held to exact
bytes, so a difference means something in the pipeline is not a pure function of
its inputs — an unordered iteration, a clock read, a filesystem order — or, if
it is one of the two screenshots, that the rendered page itself moved. It
reproduces locally with the command above, which is the same target CI runs.

It is not a flake to re-run past. If a re-run goes green without a change,
say so on the pull request rather than merging on the second attempt.

## Pull requests

- Link the issue that defines the scope.
- Keep collection, normalization, scoring, and rendering concerns separable.
- Add fixture-based tests for every source adapter.
- Never make ordinary tests depend on live websites.
- Document new policy or methodology choices before using them to score real data.
- State exactly what was verified and what remains incomplete.

Write commit subjects in the conventional form (`feat:`, `fix:`, `docs:`, `build:`) — they become the
text of the changelog entry. `CHANGELOG.md` is generated from history by
[git-cliff](https://git-cliff.org) and must never be hand-edited; `make check` regenerates it and
fails when the committed copy differs.

An ordinary pull request does not touch it. The file records tagged releases only, so it changes
once per release, as part of publishing one — see [RELEASE.md](docs/RELEASE.md).

## Adding sources

Register the organization and its eligibility before collecting results. Record discovery status
even when no current endorsement is found. A new adapter must preserve captures, produce
evidence-linked claims, and include stable local fixtures.

## Adding elections

Create a new election configuration and authoritative race inventory. Do not copy candidates or
races forward from a prior election without current official evidence.
