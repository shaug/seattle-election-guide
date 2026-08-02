# Seattle Elections Guide — Front-End Code Guidelines

How to structure the code that builds and runs the site's pages. DESIGN.md
governs what the UI looks like and how it behaves; this document governs how
that behavior is implemented: modules, rendering, state, contracts, and
dependencies. Rules here are decidable — each one can reject a real diff. When
a proposal and this document disagree, either follow the document or change it
in the same pull request; never silently diverge.

Every rule names the automated check that enforces it. A rule marked **Check:
pending** is normative now and gains its check in the enforcement ticket of the
front-end architecture epic; until then reviewers apply it by hand. A check's
failure message must name the rule and this document. A noisy or misfiring
check is a bug in the check — fix or amend it, never route around it.

## Modules

- **Every `.mjs` file is a real ES module.** It declares its imports, imports
  what it references, and loads standalone in Node. No module may rely on
  another's names being present through script concatenation or paste order.
  *Check: exists — `tests/js/module-isolation.test.mjs` `import()`s every
  module in isolation, against a shrinking allowlist of the modules that
  cannot yet load alone. A free identifier is a runtime `ReferenceError`, not
  a load failure, so the "imports what it references" clause is covered for
  pure modules by the shared guard and otherwise waits on `tsc --checkJs`.*
- **Each page has one client entry module.** Pages are assembled by bundling
  the entry's import graph (esbuild, exact-pinned) and inlining the result into
  the template. Published pages remain self-contained single files; the module
  graph is a build-time reality, not a runtime one.
- **Templates carry no logic in `<script>`.** A template's inline script is at
  most the bundled text plus a single entry invocation. Behavior lives in
  modules, where it can be imported and tested.
  *Check: exists — `tests/test_frontend_ratchets.py` holds each template to a
  recorded inline-script line ceiling that only decreases, and to a registry
  of the injection placeholders the ceiling excludes (see Adoption).*

## Rendering

- **Interactive regions render through lit-html templates from view-model
  state.** Imperative DOM writes are allowed only in wiring code: event
  listeners, focus management, one-shot boot. No `innerHTML`, no string-built
  markup, no hand-patching of text nodes scattered through handlers.
- **The server renders the complete audited baseline.** Every page stands
  alone for crawlers and readers without JavaScript. Client rendering takes a
  region over only when personalization or interaction requires it; the
  default audited view does zero DOM work.
- **Client and server markup for the same region must agree.** A lit-html
  template rendered with audited data must produce the region the Jinja
  template rendered. *Check: pending — a Node parity test renders the lit
  template with audited view-model data and diffs it against the server
  output.*
- **Repeated lists that re-render use keyed rendering** (lit-html `repeat`),
  so re-renders preserve element identity and focus. A control the reader is
  using must still exist after the render it triggers.

## The data contract

- **The embedded JSON payload is the complete client contract.** Everything
  client code needs — identifiers, display labels, ordering, summaries — comes
  from the payload. Client code never reads state out of rendered markup; the
  DOM is write-only projection.
- **One identifier space.** The payload, the markup's data attributes, and the
  client modules use the same identifier for the same entity. A translation
  map between two of our own identifier spaces is a defect in the contract.
- **The payload is typed from the Pydantic models.** The publication view
  model emits JSON Schema; the build generates TypeScript declarations from
  it; client modules are checked against them (`tsc --checkJs`). A Python
  model change that breaks a client consumer fails `make check`.
  *Check: pending.*
- **`schema_version` is validated at parse time.** A payload the client does
  not understand degrades to the server-rendered baseline with a visible
  notice — never a silent no-op, never a half-enhanced page.

## State and URLs

- **The URL fragment is the only client persistence.** No `localStorage`, no
  `sessionStorage`, no cookies. *Check: exists — the shared guard in
  `tests/js/support/module-guards.mjs` asserts the absence of every storage
  identifier in every module, page wiring included.*
- **Each page's codec module is the sole reader and writer of `location`.**
  One owner per fragment. No second script parses the hash by hand, and no
  handler edits `location` around the codec.
- **Decode and encode failures are surfaced.** A stale, malformed, or
  unencodable state produces a reader-visible notice and a cleaned address
  bar, exactly as the guide's lens notices do today. Silent fallthrough is a
  defect.

## Cross-language mirrors

- **A comment is not a contract.** Any logic implemented in both Python and
  JavaScript — labels, formatting, scoring, encoding — requires a generated
  parity fixture: the Python side emits golden cases, the Node tests assert
  them. `lens-score`'s parity fixture is the pattern. *Check: pending for
  labels and percentage formatting; exists for scoring.*
- **Prefer deleting a mirror to fixing one.** Where the contract can carry
  the computed value instead (a label in the payload rather than a formatter
  on each side), carry the value.

## Shared names

- **Names shared across template, JS, and CSS are declared once.** `data-*`
  attributes, root state classes, breakpoints, and grade strings live in one
  contract module; templates, stylesheets, and client code consume it, and
  tests import it rather than restating literals. *Check: pending — a
  manifest test fails on shared names not declared in the contract module.*

## Server-side templates

- **Full HTML documents are Jinja templates extending the shared layout.** No
  new Python-string documents or fragments; autoescaping is the default, not a
  per-call discipline. The existing f-string pages are grandfathered on a
  shrinking allowlist. *Check: exists — `tests/test_frontend_ratchets.py`
  parses every module under `src/` and reports each function whose own body
  holds a string literal beginning `<!doctype`, whether it is returned
  directly or named first, then holds that set to the allowlist. Fragments are
  not covered.*

## Dependencies

- **Runtime: lit-html, and nothing else without amending this document.**
  Exact-pinned, bundled at build time, shipped inline in the page like our own
  modules. Nothing is fetched at runtime; every shipped byte remains readable
  in the page source.
- **Dev-time dependencies are few, shallow, and exact-pinned.** The build
  toolchain is esbuild, typescript (as a checker), and the schema-to-types
  generator. Installs use the committed lockfile (`npm ci`). Adding a dev
  dependency requires the issue that first uses it, as with Python
  dependencies (ARCHITECTURE.md).

## Testing

- **Pure modules get Node tests plus a purity guard** — a test that asserts
  the module's source references no DOM, network, storage, or viewport
  identifier. The identifier set lives once in
  `tests/js/support/module-guards.mjs`; every module's test imports it and
  declares which of its two tiers applies, so tightening the set tightens
  every module at once. Page wiring names DOM identifiers by design and takes
  the storage tier only.
- **Render functions get Node tests against view-model fixtures**, in a
  lightweight DOM (happy-dom) where one is needed. Headless-Chrome tests
  remain the integration layer; they are not the first line of coverage for
  logic.
- **Every discipline in this document that can be checked, is checked, in
  `make check`.** A rule without a check is either pending (named above) or
  reviewer-applied by explicit note here.

## Adoption

This document describes the target state; the codebase does not yet comply.
The transition is legislated, not implied:

- **Existing violations are grandfathered, new ones are not.** The epic's
  first ticket lands the checks above with today's measurements frozen into
  `tests/frontend_ratchets.json`: per-template inline-script ceilings and
  their injection-placeholder registry, the f-string page allowlist, and the
  modules that do not yet load standalone. Ceilings and allowlists only
  shrink, and the checks enforce that in both directions — a ceiling that is
  now too high fails until it is lowered. New code complies immediately.
- **Migration tickets lower ceilings.** Each ticket that moves glue into
  modules, or a page onto the shared layout, updates the recorded ceiling in
  the same pull request. The epic's closeout deletes the grandfather lists.
- **Unwired code is not presumed dead.** Shipped-but-unwired surfaces may be
  landing zones for in-flight work. Check open issues before proposing
  removal; prefer an inventory to a sweep while epics are open.
- **Sequencing for new client work.** The bundler and lit-html foundation
  land before new client rendering is written. In particular, the race-page
  migration (#136) writes its client rendering lit-native on that foundation
  rather than porting the dialog's imperative renderer and rewriting it
  later.

## Open questions

Decided by their implementing tickets, then recorded here:

- The shared fragment-codec core: how much of `compare-url` / `lens-url` is
  parameterized into one module, and the shape of its page-schema parameter.
- The takeover idiom for lens-aware regions: the exact container boundary at
  which lit-html assumes ownership from the server baseline, and how the
  audited restore is expressed.
- Per-page CSS entry points: whether stylesheets move to the same
  entry-per-page model as scripts, and what replaces the shared
  `base.css + guide.css` concatenation.
