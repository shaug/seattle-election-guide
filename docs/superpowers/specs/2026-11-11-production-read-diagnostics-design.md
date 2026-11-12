# Production request diagnostics (#742)

The existing production checker loses response framing, timing and exception-chain identity when a whole-body read fails. Retain bounded diagnostic metadata while preserving every request and acceptance outcome.

Add an optional nested diagnostic record to Observation. At the shared production request boundary record UTC request start, elapsed/header/body timing, phase, available response status, normalized framing headers, expected/received length and a partial digest when IncompleteRead provides bytes. Keep exception type chains bounded; retain no new exception messages, raw body, credentials, cookies or arbitrary headers. Keep legacy reports readable.

Use the existing opener, User-Agent, redirect behavior and response.read() operation. Preserve failed-body statusNone/bodyNone, error strings, hashing, deadlines and two consecutive strict passes. Header-only routes must remain header-only. Diagnostic collection must not mask original outcomes.

A nested record in existing JSON is the smallest approach. A separate event log would introduce unrelated storage/correlation; changing the client or retry policy would change the requested behavior. The user delegated these implementation choices and explicitly declined another design/permission gate. This is engineering instrumentation, separate from exact-source production acceptance and PR741.
