# Seattle Elections Guide — Front-End Code Guidelines

How to structure the code that builds and runs the site's pages. DESIGN.md
governs what the UI looks like and how it behaves; this document governs how
that behavior is implemented: modules, rendering, state, contracts, and
dependencies. Rules here are decidable — each one can reject a real diff. When
a proposal and this document disagree, either follow the document or change it
in the same pull request; never silently diverge.

Every rule names what holds it. A rule ends either with **Check:** naming the
automated check that enforces it — `exists` when the check covers the rule,
`partial` when it covers part and says which part — or with
**Reviewer-applied:** stating plainly that nothing automated holds it and what a
reviewer is looking for. There is no third state: the front-end architecture
epic (#232) closed with #245 walking this document top to bottom, and a bullet
with no marker is a bullet nobody has read since. A check's failure message must
name the rule and this document. A noisy or misfiring check is a bug in the
check — fix or amend it, never route around it.

A `Check:` line is a claim about what a check can *observe*, not about what it
is named. Four times in this epic a check shipped blind to its own gap — a
comment-stripping owner sweep, a self-exempting shared-names module, a
line-anchored placeholder scan, and a mirror inventory whose derivation missed a
live mirror. Before writing or believing one of these lines, break the rule on
purpose and watch the check fail.

## Modules

- **Every `.mjs` file is a real ES module.** It declares its imports, imports
  what it references, and loads standalone in Node. No module may rely on
  another's names being present through script concatenation or paste order.
  *Check: exists — `tests/js/module-isolation.test.mjs` `import()`s every
  module in isolation. It read an allowlist of the modules that could not yet
  load alone; #234 emptied that list and #245 deleted it, so there is no
  exemption to add to and the first module that stops loading fails. A free
  identifier is a runtime `ReferenceError`, not a load failure, so the "imports
  what it references" clause is `tsc --checkJs`'s: it reports any name a module
  uses without declaring or importing it (TS2304).*
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
  override a shared rule without restating it. A rule *group* two pages render,
  and no third, lives in a part they both name (`guide-sources.css`), never
  copied into both. That is about components — the class-based groups a page
  owns; a page's own `main` frame rules stay page-local even where two pages'
  happen to match, because hoisting a padding value is not what keeps the
  groups apart. A page writes no rules in its template: nothing overrides
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
  groups it happens not to render — the filter bar and the election-day banner
  on the site-wide pages, the action strip on Comparisons. Splitting `base.css`
  by component is a separate decision about the shell, not this one.
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
  of the injection placeholders the ceiling excludes (see Adoption). Every
  scripted page now sits at the floor of 1. The scan reads a `<script>` element
  in any case and closed with any trailing whitespace, and registers a
  placeholder written with Jinja whitespace control or a dotted name; each of
  those forms has a case that fails when its pattern is reverted. One limit is
  accepted rather than closed: the registry's unit is the whole line, so a
  `| safe` sharing its line with other content is counted by the ceiling in an
  ordinary `<script>` — the safe direction — but inside a `type="application/json"`
  payload, whose lines the ceiling skips, it is read by neither half. Closing it
  would move the registry's unit from the line to the occurrence; no template
  writes that form, and `tests/frontend_ratchets.json` says so where a reviewer
  adding one would look.*

## Rendering

- **Interactive regions render through lit-html templates from view-model
  state.** Imperative DOM writes are allowed only in wiring code: event
  listeners, focus management, one-shot boot. No `innerHTML`, no string-built
  markup, no hand-patching of text nodes scattered through handlers.
  *Reviewer-applied, and this is the rule the epic did not finish. What is
  checked is that the regions lit **does** own render correctly: the parity
  tests below diff every converted region against the server's, and the purity
  guard keeps computing modules away from the DOM entirely. Nothing sweeps for
  an imperative write, because a sweep would need an allowlist and #245's whole
  job was deleting those. The residue a reviewer is holding the line against,
  named so a future reader finds it stated rather than wonders whether it was
  missed:*
  - *The race-detail dialog's imperative renderer — `renderRaceDetail` and its
    helpers in `guide-lens.mjs`. #239 extracted it unconverted, #248 explicitly
    excluded it, and **#136 deletes it outright** in favor of real race pages
    (Adoption, below). It is not being ported; do not extend it.*
  - *The Sources link's `href`, written imperatively in `guide-client.mjs`'s
    `renderChrome` and again in `sources-client.mjs`. #248's convert list
    promised a lit binding and could not deliver one: a second
    `[data-sources-link]` is rendered by the shared shell band on every page, so
    binding it through lit would give lit shell markup. Behavior is correct and
    tested — both links carry the same live href on every selection and fragment
    change. The same shape covers `lensNotice.hidden` and the other booleans
    projected onto a **region root**, which the takeover idiom keeps as the
    server's element and so puts out of lit's reach. **Unowned:** the resolution
    is to convert the strip link and the band together when the shell band moves
    onto lit, and no ticket says that yet.*
  - *`election-day.mjs` writes `innerHTML` from a string built by concatenation
    in `electionDayStatement` — a direct violation of this bullet's last
    sentence, and the only one in the shipped client. The banner is in-flight
    from the site-operations epic rather than this one. **Unowned.***
  - *Text written straight onto a server-rendered status or notice element:
    `share-link.mjs` and `guide-dialog.mjs`'s copy-status lines,
    `sources-client.mjs`'s `showNotice`, `client-payload.mjs`'s payload notice,
    and `compare-client.mjs`'s scroll hint, status, and notice. These are named
    as a shape rather than a closed list — a `textContent` sweep of the shipped
    modules is the inventory, and it moves. **Unowned.***
  - *The `createElement` loop in `guide-filters.mjs`'s `apply`, which is a lit
    template written by hand. **Unowned.***
- **The server renders the complete audited baseline.** Every page stands
  alone for crawlers and readers without JavaScript. Client rendering takes a
  region over only when personalization or interaction requires it; the
  default audited view does zero DOM work.
  *Check: exists for the region that proves it — `compare-markup-parity.test.mjs`
  boots the audited Comparisons page and asserts the first row group is the
  same element object afterward, so a client that rebuilt the audited default
  fails rather than merely rendering something equal to it. The "stands alone"
  half is the parity fixtures themselves: they are the server's real output,
  held to a fresh render by `tests/test_rendering.py` and
  `tests/test_compare_rendering.py`.*
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
  *Check: partial — each of the three timings has the test that distinguishes
  it. `compare-markup-parity.test.mjs` asserts the projection region is
  untouched at boot and taken over only once state leaves the audited default,
  and that the `<thead>` carrying controls **is** taken over at boot;
  `sources-markup-parity.test.mjs` asserts the control field re-renders
  identically at boot; `guide-markup-parity.test.mjs` asserts the audited
  restore after a lens is applied and cleared. What no check states is the
  idiom in general — that a new region hooks one element and owns only its
  children. A reviewer applies that to the next region converted.*
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
  *Reviewer-applied. A twin is two elements that agree today, so nothing derived
  from the rendered page can tell one from a value legitimately shown twice; the
  defect appears only once they drift. The markup-parity diffs catch a drift
  between the server's element and lit's — the case that actually bit — but
  declining the second element is the reviewer's. The dialog's surviving twins
  are the known exception, and #136 removes them with the markup.*
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
  *Check: exists — and the assertion that carries it is a narrower one than it
  looks. Element identity is asserted in several places (`a === b`, not a markup
  diff), but keyed and unkeyed rendering are indistinguishable while the list
  itself holds still: reusing the element at each index gives the same answer.
  What distinguishes them is a render that **changes the list**, and each
  template has exactly one such case. `compare-table.test.mjs` drops a race from
  the body and asserts a surviving row is the same element;
  `sources-tree.test.mjs` drops a source from a category and asserts the
  surviving checkbox is the same element and still holds focus. Replacing
  `repeat` with an unkeyed `.map` fails those two and nothing else — the
  head-column and re-render cases keep their lists steady and pass either way,
  which is why they are not what holds this rule.*
- **A form control's live value is bound with `live()`.** A checkbox is the one
  binding whose DOM value changes without a render — the browser sets it on a
  click and restores it on a back-navigation, both behind lit's record of what
  it last wrote — so an ordinary property binding can decide a repair is a
  no-op and skip it. `live()` compares against the element instead. The sources
  tree binds `checked` and `indeterminate` this way, and also writes the
  `checked` *attribute*, which is what a no-JS reader and the parity check see.
  *Check: exists — `sources-tree.test.mjs` sets a checkbox's DOM property behind
  lit's back, re-renders with unchanged state, and asserts the repair happened;
  it also holds the content attribute and the live property to each other in
  both directions, and covers `indeterminate`, which has no attribute at all.
  Dropping `live()` from the template fails it.*

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
  *Reviewer-applied, and deferred beyond this epic — #245's disposition, so the
  bullet does not read as done. The rule holds for the surface the client
  actually addresses: `tests/test_shared_names.py` catches an identifier that
  gains or loses a surface, and `tsc --checkJs` catches a client module reading
  a payload field that is gone. What no check states is the negative — that no
  translation map exists — and one place still needs one. The personalization
  contract the payload inlines carries its internal ids, including
  `retired_codes[].former_id`, which the migration resolvers read, and its
  `sources` overlap the payload's own code-only list. Narrowing that inlined
  contract to codes is real work on the publication models, not a rename, and
  **no ticket owns it.** A reviewer's job here is to refuse a *new* translation
  map; the existing one is recorded, not blessed.*
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
  than a missing capability. #236 closed without filing that follow-up, and
  #245 records the deferral rather than smuggling the test in: **unowned**, one
  test away, and the gap is precisely that a payload the client refuses is
  proven refused but not proven to say so.*

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
  for the guide and the sources editor, and `compare-url.mjs` with
  `compare-route.mjs` is that pair for Comparisons. One owner per fragment
  means the two routers are deliberately separate: the pages read different
  schemas against different contexts.
  *Check: exists — `tests/js/lens-route.test.mjs` sweeps every client module
  for `location` or `history` and fails on one that is neither an owner nor a
  recorded exception, so a new access is a change to that list. One exception
  is recorded there: `share-link.mjs`, which copies the address verbatim and
  interprets no segment of it, so there is no fragment for a codec to own.*
- **The codecs share a vocabulary, not an engine.** The structural rules both
  fragments obey live once, in `fragment-codec.mjs`: the token grammar,
  admission against the current panel's catalogs, the four published
  identifiers that make a stale link recognizable as stale, the
  repeated-parameter refusal, and the published sharing limit in both
  directions. That module is deliberately *not* a schema-driven codec. It
  covers about a quarter of either page codec; the rest is each page's real
  content — the lens's two modes, its category-before-source ordering and its
  legacy `#race-…` permalinks; Comparisons' ordered columns, its two-to-three
  column bound, its reserved lowercase-`g` namespace, its filter parameters
  and its refusal to read a lens link — and expressing that as configuration
  would cost more than the sharing saves while moving a page's rules out of
  the page's own codec. Each codec still reads top to bottom as the grammar it
  owns. The one parameter that crosses the seam is the page's own failure
  factory: the same structural problem is `malformed` when decoding and
  `rejected` when encoding, and each page names reasons the shared module has
  never heard of, so a shared helper that can fail returns what the caller's
  factory built. A third fragment would extend this module only where it
  genuinely restates one of those rules.
  *Check: exists — `tests/js/fragment-codec.test.mjs` states the shared rules
  where they live, including the two whose ordering a page depends on: the
  token scan reports the leftmost token breaking any rule, the caller's own
  rule included, and a token is ranked for case confusion only inside the
  catalog its own prefix names. The guard in `module-guards.test.mjs` keeps
  the module pure. Both page suites are unchanged by the extraction, which is
  what makes them its regression test.*
- **Decode and encode failures are surfaced.** A stale, malformed, or
  unencodable state produces a reader-visible notice and an address bar that
  names a state a link can reproduce — cleaned when it holds a fragment the
  page could not use, left alone when it already names the state that
  survived. Silent fallthrough is a defect. It binds both directions: a
  selection that cannot be *written* into a link is as much a failure as a
  link that cannot be read, and the reader is told rather than handed a link
  that quietly drops it. Every status the codec can return needs a branch;
  a status with no branch is indistinguishable from one the page ignored.
  *Check: exists — `tests/js/guide-client.test.mjs`,
  `tests/js/sources-client.test.mjs`, and `tests/js/compare-client.test.mjs`
  hold each page to a notice for an unreadable incoming fragment and for a
  rejected encode, and to leaving an ordinary in-page anchor alone. The
  Comparisons tests additionally cover each migration outcome and prove a
  refused change is reverted rather than half-applied.
  `selectionFragment` in `lens-selection.mjs` is what makes the encode half
  unmissable for the guide and the sources editor: it returns a rejection a
  caller has to dispose of rather than an empty string. On Comparisons that
  role belongs to `commit`, which is the only way a reader's change reaches
  the address bar and has nowhere to drop a rejection.*

## Cross-language mirrors

- **A comment is not a contract.** Any logic implemented in both Python and
  JavaScript — labels, formatting, scoring, encoding — requires a generated
  parity fixture: the Python side emits golden cases, the Node tests assert
  them. `lens-score`'s parity fixture is the pattern.
  *Check: exists — `tests/mirrors.json` is the inventory of surviving mirrors
  and the proof that holds each one; `tests/mirror_parity.py` runs the shipped
  server implementations over real publication bundles and emits
  `tests/js/fixtures/mirror-parity.json`, which `tests/js/mirror-parity.test.mjs`
  asserts against the client. `tests/test_mirrors.py` regenerates the fixture
  during `pytest`, so a committed golden file cannot go stale while staying
  green. The first thing the fixture found was a real divergence: the meter's
  spoken label read the visible `N/A` aloud where the audited renderer says
  "not available", on the null share no audited page renders and no markup diff
  can reach.*
- **The inventory of mirrors is derived, not listed.**
  `tests/cross_language_mirrors.py` finds candidates two ways — the same
  display-text template written on both sides, and a definition on one side
  that the other names — and `tests/test_mirrors.py` holds `tests/mirrors.json`
  to the union in both directions. The second signal is the rule above read
  mechanically: a comment claiming a mirror is what puts that mirror on the
  inventory, so the claim can no longer be the only thing documenting it. For a
  mirror whose whole content is one shared string, that derivation is the proof:
  drop the wording from either side and the declared evidence stops being
  derived.

  **Both sides are read the same way**, which took four corrections to get right
  and is where this scan kept missing real mirrors. A lit template is markup
  with text in it, exactly as a `.j2` file is, so both are split on their tags
  and on Jinja control flow: the text on either side of an `{% if %}`/`{% else %}`
  is two templates the page renders separately, not one blob. A Jinja
  expression's own literals and `~` concatenations are read by Jinja's own
  parser — the one that renders these files — and string literals are read by a
  brace-balanced scan rather than a pattern, so a literal inside a `${...}` is
  read to any depth — including the
  `` html`...` `` sub-template lit uses for a conditional fragment. A single
  token counts as display text unless it looks like syntax, because requiring a
  space discarded the meter's `N/A` and the comparison table's `Race` heading.
  Each of those was a blind spot invisible to the scan that had it, which is the
  entire argument for reviewing the inventory rather than trusting it.

  **The derivation is a floor, not a ceiling**, and four limits say why an entry
  may exist that no signal pins. Symbol matching is restricted to multiword
  names, because `text` and `boot` are defined on both sides and mean nothing to
  each other, and to functions and classes rather than every binding — a
  constant mirrored across the boundary is left to its own check, as
  `CLIENT_PAYLOAD_SCHEMA_VERSION` is to `tests/test_client_payload_types.py`. A mirror that shares no words with its counterpart is invisible to
  both signals — the Comparisons fragment encoding is exactly that, and is on
  the inventory because a reviewer put it there — so arithmetic and encoding
  mirrors carry golden cases rather than evidence keys. Attribute text is
  dropped with the tag that holds it, so a `title` or `aria-label` spelled on
  both sides is left to the markup diff. And an evidence key records that a
  template is spelled on each side, not where or how many times, so a text-backed
  entry catches wording dropped from a side but not one implementation of it
  moving while another occurrence anywhere on that side keeps the key alive.
  Adding
  an entry after reading the code is the intended way to close what those limits
  leave; `tests/mirrors.json` is reviewed, not merely generated.
  *Check: exists — `tests/test_mirrors.py` derives the candidate set with
  `tests/cross_language_mirrors.py` and holds `tests/mirrors.json` to it in both
  directions, so an undeclared mirror and a stale declaration each fail; it also
  holds every text-backed entry's evidence to text the derivation still finds,
  which is what makes a dropped wording fail. Deleting an entry from the
  inventory fails `pytest`. The four limits above are the check's stated
  ceiling, not a gap someone forgot: within them the derivation is complete,
  and beyond them a reviewer adds the entry.*
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
  definition. `tests/mirrors.json` records the deletions alongside the
  survivors, so a reader looking for a mirror an old issue named can see it was
  removed rather than go hunting for it.
  *Reviewer-applied. Nothing tests the `deleted` map and nothing usefully could:
  its keys describe code that no longer exists, so there is no identifier left
  for a derivation to look for. What holds the rule mechanically is the bullet
  above — a deleted mirror that comes back is derived again and fails until it
  is declared, which forces the choice into the open. Making that choice
  *deletion* is the reviewer's, and the map is where the argument is written
  down.*

## Shared names

- **Names shared across template, JS, and CSS are declared once.** `data-*`
  attributes, class names that reach executable code, and breakpoints are
  declared in `tests/shared_names.json`, which records for each name the exact
  set of surfaces that spell it: template, stylesheet, client, python, test. A
  rename that reaches three of them and misses the fourth changes the derived
  set and fails `make check`.

  **The declaration is enforced by a scan, not by a generator**, and the
  stylesheet is why. An attribute or class name is selector *syntax*, while a
  custom property holds a *value*: `[var(--x)]` is not a selector and
  `@media (max-width: var(--bp))` is not a query, so a stylesheet cannot consume
  a generated name. Substituting names in during the build is not open either —
  each page's stylesheet is concatenated precisely so the shipped bytes are the
  authored bytes (Modules, above). Any generator would therefore leave the one
  surface a rename most often misses still restating every literal, so the
  contract is enforced by reading every surface instead of emitting into some.
  Declared once here means one place says what the shared names are, and every
  restatement is held to it.

  **Names with a Python origin are not declared here**, because they already
  have a generator and a value may not have two. The grade strings are
  `scoring/models.py`'s `Grade`, reaching the client as `ComputedGrade` through
  the payload generator (The data contract, above); this contract covers the
  presentation-only names, and checks that no grade string appears in it.

  Class names are in scope when a `.mjs` module or a Python probe string spells
  them, not when only a template and a stylesheet do. That pair is every class
  in the codebase and a miss there renders unstyled — loud. The quiet ones are
  what this covers, and the sharpest is a class name inside a Chrome audit
  probe: `rendering/browser.py` selects `.screen-race-context` in four probe
  strings, and a rename that misses one makes the probe match zero elements and
  report *success*. That case is why the scope is class names that cross into
  code rather than root state classes alone.
  *Check: exists — `tests/test_shared_names.py` derives the shared-name map
  from the tree and holds it to `tests/shared_names.json` in both directions, so
  an undeclared shared name, a stale declaration, and a name that gained or lost
  a surface each fail. Each scanner is exercised on a source small enough to
  read, as the inline-script metric is. `tests/test_client_payload_types.py`
  separately fails when the client's grade vocabulary stops matching the audited
  engine's. Two limits are deliberate: surfaces are recorded by kind rather than
  by file, so a miss within one language is left to that language's own checker;
  and the scan is textual, so a name a comment mentions counts as spelled
  there.*

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
  beginning `<!doctype`, whether it is returned directly or named first, and
  requires that set to be empty. Issue 241 emptied the allowlist it used to
  read and #245 deleted it, so a Python-string document is now a failure with
  nowhere to be recorded. The same module
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
  source is in the bundle rather than fetched, that the browser build is the one
  bundled, that no import or `fetch(` survives into a page, and that every
  declared dependency is an exact version. The "and nothing else" clause is an
  equality on `package.json`'s `dependencies`, not a membership test: #245 found
  the membership form, under which a second runtime dependency passed every
  check in the file, and adding one now fails until this document is amended in
  the same pull request — which is what the rule says must happen.*
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
  *Check: partial — the pinning half is
  `tests/test_frontend_bundle.py`, which holds every `dependencies` and
  `devDependencies` entry to an exact version (a `^` fails), and separately
  holds the *installed* esbuild to the version `package.json` pins, so a tree
  that drifted from the lockfile fails rather than bundling with the wrong
  compiler. The lockfile half is CI: both workflows install with `npm ci`, which
  refuses a `package.json` and `package-lock.json` that disagree. `make check-js`
  runs Biome, then `tsc`, then the Node tests, and CI runs the same target,
  which is what makes each listed tool actually load.*
  *Reviewer-applied: "few and shallow" is a judgment no check makes, and so is
  "adding a dev dependency requires the issue that first uses it." The list
  above is the whole **front-end** toolchain, not the whole `devDependencies`
  block: `git-cliff` generates the changelog and `wrangler` deploys the site, so
  they answer to CONTRIBUTING.md and the hosting configuration rather than to
  this document — while still being held to exact pins by the same check, which
  reads every entry. A pull request that lengthens either set is making an
  argument, and the reviewer is who reads it.*

## Testing

- **Pure modules get Node tests plus a purity guard** — a test that asserts
  the module's source references no DOM, network, storage, or viewport
  identifier. The identifier set lives once in
  `tests/js/support/module-guards.mjs`; every module's test imports it and
  declares which of its two tiers applies, so tightening the set tightens
  every module at once. Page wiring names DOM identifiers by design and takes
  the storage tier only.
  *Check: exists — `module-guards.test.mjs` holds `MODULE_KINDS` to the modules
  on disk, so a new module cannot arrive untiered; requires a
  `<name>.test.mjs` for each; and runs the guard itself over every module
  rather than reading the test files for the call, because a text match would
  pass a skipped test. Naming `document` in a pure module fails it. One limit:
  the scan strips comments and is otherwise textual, so it reads identifiers,
  not reachability.*
- **Render functions get Node tests against view-model fixtures**, in a
  lightweight DOM (happy-dom) where one is needed. Headless-Chrome tests
  remain the integration layer; they are not the first line of coverage for
  logic. `tests/js/support/dom.mjs` installs the DOM; a test that needs one
  calls it rather than building its own, so there is one answer to what a
  client module may assume exists.
  *Check: exists for the single-installer clause — `module-guards.test.mjs`
  sweeps every Node test and support file for an import of the DOM package,
  static or dynamic, and fails on any but `support/dom.mjs`. It reads import
  specifiers rather than text, because a textual scan for the package name
  matched the scanner, and the fix for that is not to exempt the scanner. Which
  render functions have fixtures is not counted; the parity harnesses above are
  what make the rendered ones checkable.*
- **Every discipline in this document that can be checked, is checked, in
  `make check`.** A rule without a check carries a `Reviewer-applied:`
  annotation saying so and naming what a reviewer is looking for. #245 walked
  every bullet to establish that, and the annotations are deliberately narrower
  than the rules: where a check covers part of a rule it says which part, and
  the rest is written down as unheld rather than implied to be covered.
  *Check: exists — `tests/test_frontend_ratchets.py` reads this document and
  fails on a rule between Modules and Adoption that carries none of the three
  markers, so the walk does not have to be repeated by hand and a rule added
  later cannot arrive silently unheld. Its unit is the bullet, not the bold
  name: an earlier version matched the name, could not read one that wrapped
  onto a second line, and was silently blind to four rules — this one included
  — each of which also lent its marker to the rule above it. A definition that
  every rule satisfies by construction is what removed that, rather than a
  second scan counting what the first one missed. It holds the *form*, not the
  truth of the claim: writing `Check: exists` is what the sweep sees, and
  whether the named
  check can observe a violation is the preamble's instruction to break the rule
  and watch it fail. Adoption and Open questions are outside the sweep, because
  they record how the epic ran and what it decided rather than stating rules a
  diff can violate.*

## Adoption

The front-end architecture epic (#232) ran this transition and is done. The
codebase complies with this document except where a bullet above says
otherwise, in its own words, next to the rule it fails — which is the form the
exceptions take now, rather than a list here that would go stale on its own.

This section records how the transition ran and which disciplines outlive it.
Its bullets carry no `Check:` marker and are outside the sweep above: they are
process, not rules a diff can violate. The two that bind ongoing work say who
applies them.

- **The grandfather lists are gone.** The epic's first ticket (#233) landed the
  checks above with the measurements of the day frozen into
  `tests/frontend_ratchets.json`: per-template inline-script ceilings and their
  injection-placeholder registry, the f-string page allowlist, and the modules
  that did not yet load standalone. #241 emptied the f-string allowlist, #234
  emptied the isolation exemptions, and #245 deleted both — the lists and the
  code that read them — because an empty allowlist is still somewhere to add an
  entry. Those two rules now fail on the first violation, with nowhere to record
  it. What survives in that file is not debt: the ceilings sit at the floor the
  rule permits (one entry invocation per scripted page, zero for the 404) and
  the placeholder registry is permanent.
- **Ratchets still only move one way.** A ceiling may shrink in a pull request
  and may never grow (AGENTS.md), and the checks enforce that in both
  directions — a ceiling that is now too high fails until it is lowered. There
  are no migration tickets left to lower one; the next change to that file is a
  new template arriving.
- **A rule this codebase does not yet satisfy is stated as such.** #245 walked
  every bullet and annotated it rather than declaring the epic clean. The one
  substantive shortfall is the first Rendering bullet: imperative content
  rendering survives in the race dialog (#136 deletes it), in the Sources link
  and the other values projected onto server-owned region roots, in
  `election-day.mjs`'s `innerHTML`, and in a handful of status lines and one
  hand-built node loop. Each is named where the rule is, with its owner or with
  the fact that it has none.
- **Unwired code is not presumed dead.** Shipped-but-unwired surfaces may be
  landing zones for in-flight work. Check open issues before proposing
  removal; prefer an inventory to a sweep while epics are open.
  Reviewer-applied, and restated in AGENTS.md because it binds every diff, not
  only front-end ones. No check can tell a landing zone from dead code; the open
  issues are what distinguishes them.
- **Sequencing for new client work.** The bundler and lit-html foundation
  land before new client rendering is written — both have landed. In
  particular, the race-page migration (#136) writes its client rendering
  lit-native on that foundation rather than porting the dialog's imperative
  renderer and rewriting it later. Reviewer-applied: this is a scheduling
  constraint on tickets, and the foundation it was waiting for now exists, so
  what remains is the instruction to #136 not to port the dialog.

## Open questions

Decided by their implementing tickets, then recorded here.

**None outstanding.** All three the epic opened with were answered, and each
answer is a rule above rather than a note here:

- *The shared fragment-codec core: how much of `compare-url` / `lens-url` is
  parameterized into one module, and the shape of its page-schema parameter.*
  Answered by #244 — State and URLs, "The codecs share a vocabulary, not an
  engine." A shared vocabulary rather than a parameterized codec, and no
  page-schema parameter at all beyond each page's own failure factory.
- *The takeover idiom for lens-aware regions: the exact container boundary at
  which lit-html assumes ownership from the server baseline, and how the audited
  restore is expressed.* Answered by #238 and #248 — Rendering, "The takeover
  idiom." The boundary is one element carrying a `data-` hook whose *children*
  lit owns and whose element the server keeps; takeover is explicit, one-way,
  and timed by what the region is (projection, own controls, or field of
  controls). The audited restore is not a saved copy: it re-renders the same
  template with the audited view model, which the parity checks are what make
  equivalent.
- *Per-page CSS entry points: whether stylesheets move to the same entry-per-page
  model as scripts, and what replaces the shared `base.css + guide.css`
  concatenation.* Answered by #246 — Modules, "Each page has one CSS entry too."
  Yes to entry-per-page, no to bundling: a declared list of parts concatenated in
  cascade order, so the shipped bytes stay the authored bytes.

Two decisions the epic *deferred* are recorded where the rules are, not here, so
they cannot be mistaken for open design questions: narrowing the inlined
personalization contract to one identifier space (The data contract), and
testing the `schema_version` reveal itself (The data contract). Both are
unowned.
