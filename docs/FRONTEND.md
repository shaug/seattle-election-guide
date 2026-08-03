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
  a load failure, so the "imports what it references" clause is `tsc
  --checkJs`'s: it reports any name a module uses without declaring or
  importing it (TS2304).*
- **Each page has one client entry module.** Entry modules live beside the
  templates as `<page>-entry.mjs`; the shell-only documents (About, the
  archive) share `shell-entry.mjs`. The 404 is the deliberate exception: it
  declares itself unshareable, renders no Share control, and so ships no
  script at all — an entry there would bundle wiring with nothing to wire.
  Pages are assembled by bundling the entry's import graph (esbuild,
  exact-pinned) and inlining the result into the template. Published pages
  remain self-contained single files; the module graph is a build-time
  reality, not a runtime one.
  *Check: exists — `tests/test_frontend_bundle.py` bundles every
  `*-entry.mjs`, requires each to be covered there, and asserts no import
  survives into the page.*
- **The renderer bundles; there is no prebuild step.** `rendering/bundler.py`
  invokes esbuild during rendering, so nothing has to run before
  `election-guide release build` or `pytest` and no generated bundle lives in
  the tree to go stale. Two consequences bind callers: Node and an installed
  `node_modules` are prerequisites for *rendering*, not only for `make
  check-js`, and the bundler refuses to run an esbuild other than the one
  `package.json` pins, because output is reproducible only per version.
  The bundle is never minified, and each entry leaves exactly one binding in
  the page's module scope — so no module's top-level names reach page scope,
  and the cross-module collision this section warns about cannot occur.
  *Check: exists — `tests/test_frontend_bundle.py` asserts byte-identical
  output across two bundles of each entry and enforces the version pin.*
- **Each page has one CSS entry too, and it is a declared list of parts, not a
  bundle.** `rendering/stylesheets.py` maps every page to the stylesheets it
  ships, in cascade order: `base.css` first — the design tokens and the shell
  every page renders (docs/DESIGN.md) — and `<page>.css` last, so a page can
  override a shared rule without restating it. A rule two pages render, and no
  third, lives in a part they both name (`guide-sources.css`), never copied
  into both. A page writes no rules in its template: nothing overrides
  `base.html.j2`'s `styles` slot.

  The parts are concatenated rather than bundled, which is the one place this
  seam deliberately differs from the script side above. Scripts needed a
  bundler because modules resolving each other by paste order was a
  correctness problem; CSS has no import graph, no name collisions, and
  nothing to tree-shake, so esbuild's CSS support would buy nothing a list does
  not — while reprinting every rule and dropping the comments that explain
  them. Concatenation keeps the shipped bytes the authored bytes.

  Scope: this rule governs which *page* stylesheets a page reads. `base.css`
  stays whole and shared by DESIGN.md's rule, so a page still carries shell
  groups it happens not to render — the footer on Comparisons and the sources
  editor, the filter bar on the site-wide pages. Splitting `base.css` by
  component is a separate decision about the shell, not this one.
  *Check: exists — `tests/test_page_stylesheets.py` holds every page to its
  declared parts, holds every stylesheet on disk to a page that reads it,
  asserts no page ships a class styled only by another page's own stylesheet,
  and holds `base.html.j2` to being the only template that opens a `<style>`
  element or fills the styles slot, since rules written in a template would
  ship outside the entry and so outside every other assertion here.*
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
- **The takeover idiom.** A region is one element that carries a `data-` hook,
  and lit owns that element's children — never the element itself, which the
  server keeps. Takeover is explicit and one-way: the wiring clears the
  server's children once, renders, and owns the region from then on. It
  happens at the latest moment the reader's intent requires:
  - A region whose *content* is a projection of state is left exactly as the
    server rendered it until the state stops being the audited default. The
    Comparisons table's row groups are this case, and an ordinary visit now
    does no DOM work on them at all.
  - A region that *carries its own controls* is taken over at boot, because
    the audited baseline cannot render those controls: a `<button>` the server
    ships is a control that does nothing for a reader without JavaScript. The
    Comparisons table's `<thead>` is this case — the server renders the same
    column labels as static text — and it is the reason the bullet above says
    "the default audited view" rather than "the default audited page".
  - A region that is a *field of controls the reader operates* is taken over at
    boot too, and the reason is stated where it is done. The first takeover
    replaces the region's children, so one triggered by the reader's own click
    would destroy the control they are holding and drop their focus, which the
    keyed-rendering rule below forbids. The sources editor's tree is this case:
    it keeps the server's audited markup and re-renders it identically at boot,
    which is what the parity check makes checkable.

  The audited restore is not a saved copy of the server's markup. Returning to
  the audited default renders the same template with the audited view model,
  which the parity check below is what makes equivalent.
- **An `aria-live` element is never a region lit owns; it is one lit renders
  into.** A live region announces a change only if it was already in the
  accessibility tree when the change happened, so an element the client created
  — even one render before it filled it, in the same task — announces nothing.
  The server renders every announcing element and it stays for the life of the
  page; lit owns its text. The guide's banner status and lens notice, and the
  sources editor's count line, are all this shape. #248 shipped a lit-owned
  lens strip first and had to undo it: every notice the guide raises is a
  boot-time one, so a strip lit created would have told a screen-reader reader
  nothing about the broken link they followed.
  *Check: partial — `guide-client.test.mjs` asserts element identity across
  `wireGuide` for both announcing elements on the audited, unreadable-link, and
  same-version-link paths, and `guide-markup-parity.test.mjs` asserts it against
  the real audited page. Nothing checks that a new `aria-live` element has not
  been introduced somewhere else.*
- **A region is one element per value, not a pair.** A value that changes
  between the audited and the personalized view is carried by the element the
  server rendered it in; there is no empty twin beside it for the client to
  fill, and no CSS rule choosing between them. #248 retired the guide's
  `[data-lens-only]`/`[data-lens-hidden]` twins from the race card for this
  reason: two elements holding one quantity is how the card and the dialog came
  to disagree about it. The dialog's own twins survive only because #136 is
  deleting that markup outright (Adoption, below).
- **Client and server markup for the same region must agree.** A lit-html
  template rendered with audited data must produce the region the Jinja
  template rendered. *Check: exists for every region lit renders. Each page's
  parity test boots its audited page in the lightweight DOM and diffs what lit
  rendered against what Jinja did: `compare-markup-parity.test.mjs` for the
  Comparisons table's row groups, `guide-markup-parity.test.mjs` for all three
  card regions of every race on the ballot after a lens is applied and cleared,
  and `sources-markup-parity.test.mjs` for the sources tree and count line at
  boot. The audited pages are committed
  under `tests/js/fixtures/`, rendered by `tests/page_parity.py` and
  `tests/compare_parity.py`, and held to a fresh render by
  `tests/test_rendering.py` and `tests/test_compare_rendering.py`. The
  comparison is of parsed markup — every tag, attribute, and run of text —
  ignoring only comments, whitespace, attribute order, and the difference
  between a relative and an absolute form of the same URL;
  `tests/js/support/markup-parity.mjs` states that list and takes a region. A
  head that the server does not render interactively has no region to compare,
  and is covered instead by the behavior tests in
  `tests/test_compare_rendering.py`.*
- **Repeated lists that re-render use keyed rendering** (lit-html `repeat`),
  so re-renders preserve element identity and focus. A control the reader is
  using must still exist after the render it triggers.
- **A form control's live value is bound with `live()`.** A checkbox is the one
  binding whose DOM value changes without a render — the browser sets it on a
  click and restores it on a back-navigation, both behind lit's record of what
  it last wrote — so an ordinary property binding can decide a repair is a
  no-op and skip it. `live()` compares against the element instead. The sources
  tree binds `checked` and `indeterminate` this way, and also writes the
  `checked` *attribute*, which is what a no-JS reader and the parity check see.

## The data contract

- **The embedded JSON payload is the complete client contract.** Everything
  client code needs — identifiers, display labels, ordering, summaries — comes
  from the payload. Client code never reads state out of rendered markup; the
  DOM is write-only projection. Locating a render target is projection, not a
  read: a `dataset` lookup that answers "which element is this" stays.
  Each page publishes exactly one payload element,
  `<script type="application/json" data-client-payload>`, and admits it
  through `client-payload.mjs` rather than parsing it by hand.
  *Check: exists — `tests/test_rendering.py` names each read the guide's
  client code used to make and fails if one returns, sweeping the whole
  bundle rather than one script block, and asserts the payload it replaced
  them with equals the rendered markup it was read from: the dialog's
  candidates and summary, the card's race label, and the Ballot filter's own
  options.*
- **One identifier space.** The payload, the markup's data attributes, and the
  client modules use the same identifier for the same entity. A translation
  map between two of our own identifier spaces is a defect in the contract.
  The panel's transport `code` is that identifier: the markup addresses a
  source by code, and no client module translates between code and id.
  Not finished, and unowned: the personalization contract the payload inlines
  still carries its internal ids — one of which, `retired_codes[].former_id`,
  the migration resolvers read — and its `sources` overlap the payload's own
  code-only list. No ticket narrows the inlined contract yet; the closeout
  walk (#245) disposes of this rather than letting the bullet read as done.
- **The payload is typed from the Pydantic models.** The publication view
  model emits JSON Schema; the build generates TypeScript declarations from
  it; client modules are checked against them (`tsc --checkJs`). A Python
  model change that breaks a client consumer fails `make check`.
  *Check: partial — `rendering/payload.py` models the three page payloads and
  renders `templates/types/client-payload.d.ts` from their schema (`make
  types`); `tests/test_client_payload_types.py` fails when the committed
  declarations are not what the models generate, and `tsc --checkJs` holds
  every client module to them without running Python. Only names no payload
  field carries — the share result, the prior-panel snapshot — stay
  hand-written, in `types/client-runtime.d.ts` beside them. Issue #239 closed
  the last gap: `GuidePayload`, `SourcesPayload`, and the race-display and
  panel types they carry now have `.mjs` consumers, because the glue that
  reads them is modules rather than inline script, so a rename in those models
  fails `tsc` instead of leaving a reader addressing a field that is gone.*
- **`schema_version` is validated at parse time.** A payload the client does
  not understand degrades to the server-rendered baseline with a visible
  notice — never a silent no-op, never a half-enhanced page.
  *Check: partial — `tests/js/client-payload.test.mjs` holds
  `parseClientPayload` to refusing an absent, malformed, unversioned, or
  future-versioned payload, and requires every page to render exactly one
  payload element and exactly one notice element, so neither end of the
  reveal can be dropped silently.
  `tests/test_client_payload_types.py` requires every page payload to declare
  `schema_version` and holds the client's own literal to the Python constant,
  so a version bump cannot ship a build that refuses its own payload. What
  runs unexercised is the reveal itself — `readClientPayload` writing the
  notice, and the entry throwing. The lightweight DOM this was waiting on has
  landed (#238, Testing below), so what remains is an unwritten test rather
  than a missing capability; it belongs to #236's follow-up, not to the ticket
  that brought the DOM in.*

## State and URLs

- **The URL fragment is the only client persistence.** No `localStorage`, no
  `sessionStorage`, no cookies. *Check: exists — the shared guard in
  `tests/js/support/module-guards.mjs` asserts the absence of every storage
  identifier in every module, page wiring included.*
- **Each page's codec module is the sole reader and writer of `location`.**
  One owner per fragment. No second script parses the hash by hand, and no
  handler edits `location` around the codec. A page whose codec is pure pairs
  it with one router module that holds the `location` and `history` calls and
  parses nothing itself — `lens-url.mjs` with `lens-route.mjs` is that pair
  for the guide and the sources editor.
  *Check: partial — `tests/js/lens-route.test.mjs` sweeps every client module
  for `location` or `history` and fails on one that is neither an owner nor a
  recorded exception, so a new access is a change to that list. Two exceptions
  are recorded there today: `share-link.mjs`, which copies the address
  verbatim and interprets no segment of it, and `compare-client.mjs`, whose
  page has its own fragment and its own codec — issue #243 gives Comparisons
  the router half.*
- **Decode and encode failures are surfaced.** A stale, malformed, or
  unencodable state produces a reader-visible notice and a cleaned address
  bar, exactly as the guide's lens notices do today. Silent fallthrough is a
  defect. It binds both directions: a selection that cannot be *written* into
  a link is as much a failure as a link that cannot be read, and the reader is
  told rather than handed a link that quietly drops it.
  *Check: partial — `tests/js/guide-client.test.mjs` and
  `tests/js/sources-client.test.mjs` hold each page to a notice for an
  unreadable incoming fragment and for a rejected encode, and to leaving an
  ordinary in-page anchor alone. `selectionFragment` in `lens-selection.mjs`
  is what makes the encode half unmissable: it returns a rejection a caller
  has to dispose of rather than an empty string. Comparisons is not covered
  yet; that is issue #243.*

## Cross-language mirrors

- **A comment is not a contract.** Any logic implemented in both Python and
  JavaScript — labels, formatting, scoring, encoding — requires a generated
  parity fixture: the Python side emits golden cases, the Node tests assert
  them. `lens-score`'s parity fixture is the pattern. *Check: exists for
  scoring; partial for the comparison table's labels and percentages — the
  markup-parity test (Rendering, above) diffs both sides' output for every
  cell the audited page renders, which is what caught `toFixed` rounding a
  9/16 share to 56.3% where the audited renderer's half-to-even gives 56.2%.
  It cannot reach a value the audited page does not render, so a generated
  golden-case fixture is still owed for the shares only a category column
  produces.*
- **Prefer deleting a mirror to fixing one.** Where the contract can carry
  the computed value instead (a label in the payload rather than a formatter
  on each side), carry the value. The audited candidate order and the audited
  accessible summary are carried this way: the renderer publishes the text and
  the order it rendered, so nothing recomputes them client-side to restore
  them. So is every string the sources tree renders — its per-source
  endorsement count and its "also in" category tags — which is why #248 gave
  that tree to lit without adding a second implementation of either. The count
  grammar that used to be a Jinja macro is now `source_participation_label` in
  `rendering/payload.py`, feeding the template and the payload from one
  definition.

## Shared names

- **Names shared across template, JS, and CSS are declared once.** `data-*`
  attributes, root state classes, breakpoints, and grade strings live in one
  contract module; templates, stylesheets, and client code consume it, and
  tests import it rather than restating literals. A name with a Python origin
  is declared there — the grade strings are `scoring/models.py`'s `Grade`,
  reaching the client as `ComputedGrade` through the payload generator, so the
  presentation-only names are what remains for a JavaScript contract module.
  *Check: partial — `tests/test_client_payload_types.py` fails when the
  client's grade vocabulary stops matching the audited engine's; the manifest
  test for presentation-only names is pending.*

## Server-side templates

- **Full HTML documents are Jinja templates extending the shared layout.** No
  new Python-string documents or fragments; autoescaping is the default, not a
  per-call discipline. `base.html.j2` owns the document skeleton and leaves
  four slots — `head_meta`, `styles`, `body`, and `scripts` — and the shell
  grammar (band, page head, footer) is macros in `_shell.html.j2`, reached
  through the `shell` environment global rather than imported per page. A page
  whose shell slot needs real markup authors that markup in its own template:
  the page head's tagline is the caller's `{% call %}` block, so a literal
  entity is literal and an interpolated value is escaped, instead of Python
  handing in pre-escaped HTML the way `tagline_html` used to require.
  *Check: exists — `tests/test_frontend_ratchets.py` parses every module under
  `src/` and reports each function whose own body holds a string literal
  beginning `<!doctype`, whether it is returned directly or named first, then
  holds that set to the allowlist, which issue 241 emptied. The same module
  covers the templates: exactly one `.j2` may open a `<!doctype`, and every
  other non-partial template must name `base.html.j2` in an `extends`, so a new
  page cannot restate the document instead of extending it. Fragments are not
  covered.*

## Dependencies

- **Runtime: lit-html, and nothing else without amending this document.**
  Exact-pinned, bundled at build time, shipped inline in the page like our own
  modules. Nothing is fetched at runtime; every shipped byte remains readable
  in the page source. It is the standalone `lit-html` package — not `lit`,
  and no reactive-element or decorator layer with it — because what the pages
  need is a template renderer over view-model state, which is what Rendering
  above describes. Its BSD-3-Clause notice travels with it: esbuild collects
  the licences of everything it bundles into one comment at the end of the
  inlined script, which is the redistribution the licence asks for and stays
  readable like the rest.
  *Check: exists — `tests/test_frontend_bundle.py` asserts that lit-html's
  source is in the bundle rather than fetched, that no import survives into a
  page, and that every declared dependency is an exact version.*
- **Dev-time dependencies are few, shallow, and exact-pinned.** The toolchain
  is:
  - **esbuild** — bundles each page's entry (Modules, above).
  - **typescript** — `tsc --noEmit --checkJs` over the client modules. A
    checker only: no transform step, no build output, and the modules stay
    runnable `.mjs`. Types are carried in JSDoc.
  - **Biome** — one tool for lint and format across the client modules and
    their Node tests, replacing a separate linter and formatter.
  - **happy-dom** — the lightweight DOM the Node tests render in (Testing,
    below). A test dependency only: nothing it provides is shipped, and
    headless Chrome remains the integration layer.
  - **json-schema-to-typescript** — the schema-to-types generator, run by
    `make types` to emit the payload declarations (The data contract, above).
    Its output is committed and a Python test fails when that output is
    stale, so `tsc` holds the modules to the declarations without a Python
    run; the staleness test itself does regenerate, inside `pytest`, which
    already needs `node_modules` for the bundler.

  Installs use the committed lockfile (`npm ci`), and every version is pinned
  exactly, because a checker or formatter that drifts between machines fails
  the diff rather than the code. Adding a dev dependency requires the issue
  that first uses it, as with Python dependencies (ARCHITECTURE.md).
  *Check: exists — `make check-js` runs Biome, then `tsc`, then the Node
  tests, and CI runs the same target.*

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
  logic. `tests/js/support/dom.mjs` installs the DOM; a test that needs one
  calls it rather than building its own, so there is one answer to what a
  client module may assume exists.
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
