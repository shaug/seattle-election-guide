# Contributing

Work is organized through GitHub issues and focused pull requests. Do not commit directly to
`main`.

## Local checks

```bash
uv sync --frozen
make check
```

## Pull requests

- Link the issue that defines the scope.
- Keep collection, normalization, scoring, and rendering concerns separable.
- Add fixture-based tests for every source adapter.
- Never make ordinary tests depend on live websites.
- Document new policy or methodology choices before using them to score real data.
- State exactly what was verified and what remains incomplete.

## Adding sources

Register the organization and its eligibility before collecting results. Record discovery status
even when no current endorsement is found. A new adapter must preserve captures, produce
evidence-linked claims, and include stable local fixtures.

## Adding elections

Create a new election configuration and authoritative race inventory. Do not copy candidates or
races forward from a prior election without current official evidence.
