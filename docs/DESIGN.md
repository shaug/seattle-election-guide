# Seattle Elections Guide — UI/UX Guidelines

## Historical presentation (#721, November 9, 2026)

Public historical pages use the current accepted presentation over their original verified
election data. Published archive ZIPs retain their pinned bytes. An approved color or shared
presentation correction therefore reaches the historical overview and its race pages together;
it does not require a replacement election archive. Changes to historical election facts still
require a new reviewed immutable release. Election-specific capabilities remain those supplied
by the archive: a primary does not acquire general-only precinct controls or ballot ordering.
The existing Data updated footer describes the original data; Site updated describes the current
presentation source and build. Count, export, check and certification dates retain their own
meanings. This supersedes the byte-copy/replacement-archive presentation rule below.

## Preliminary results (#696)

Reuse the existing Guide/race result block: names, one-decimal named-choice percentages,
.45rem tally bars and compact contest-count/authority/evidence provenance. The bars remain
neutral navy except for the approved current-leader alignment below. The adjacent
amber badge says only **Unofficial**; certified-result badges say only **Certified**.
The second provenance line at the bottom of the card or race result block carries available
timestamps: **Count updated [time]**, **Export generated [time]**, and the separate
**Last checked [time]**, or **Certified on [date]**. Omit notices about clocks the publisher
did not supply. Export generation never substitutes for count time. All candidates
retain equal emphasis; no winner/outcome chips or trailing treatment. Center the counting
banner. Different authorities retain their own clocks and certification evidence; a County
date is not an election-wide promise. Four approved County examples are a visual excerpt,
not a coverage limit or replacement for functional product controls.

## Result alignment and actual endorsement ties (#711)

Recorded winning/advancing result meters and unique current unofficial vote leaders
receive alignment color (#715 extends #711). If the choice is in the
published aggregate recommendation set, including an aggregate tie, use endorsement green
`#087f73` with remainder `#cee5e3`. Otherwise use terracotta `#b4654c` with remainder
`#f0e0db`. Evaluate multiple recorded advancers independently. A raw leader under insufficient
coverage is not a published recommendation. Keep other result meters, backgrounds, badges,
copy and endorsement UI unchanged. Preliminary color identifies only a raw count lead:
all `advanced` flags remain false, with no outcome chips or threshold/advancement inference.
Compare integer votes, not rounded shares. Tied/zero counts, incomplete named choices,
or an aggregate write-in count at least as large as the top named count stay neutral.
A measure's raw vote lead does not establish passage; a primary lead does not invent
advancement slots. Result alignment uses the audited
aggregate and remains outside source-lens updates, like the result block itself.

Actual endorsement ties have their own purple family: lavender `#bba6d7` first, deep violet
`#654a8b` second, then the existing stepped colors toward the meter track. Keep the existing
navy percentage over lavender, and the existing bold/faded candidate-section treatment.
The existing No majority pill and Tied for lead candidate headers use purple only for a
real tie: light ground `#f4f0f8`, ink `#59416f`, lavender border and deep-violet header edge.
A sole leader at or below 50% remains amber; unrelated amber states do not change. Existing
wording, ordering, accessible meter descriptions and interaction remain the other carriers
of meaning; add no labels. This amends the earlier amber-for-ties rule below.

**Alternatives considered.** Tinted result-section backgrounds impaired badge readability
and meter-remainder appearance. Reusing tied-endorsement brown overloaded its meaning.
Dusty rose and muted violet for result exceptions risked partisan associations. Warm
graphite was neutral but less scannable. Terracotta stood out best among mostly green,
while placement in the result meter distinguishes it from endorsement colors. For actual
endorsement ties, lavender/deep violet was selected over the softer lavender/violet pair:
it separates the two runs more clearly, with lavender first to preserve navy-text contrast.
The approved studies are Library `result-section-tints.png` version 4 and
`tie-purple-palette.png` (November 8, 2026). Their examples are fictional, not election facts.
Pages inside immutable archive ZIPs retain their pinned bytes; these rules govern public rendered pages.

How to build UI that belongs on this site. Rules here are decidable — each
one can reject a real design. When a proposal and this document disagree,
either follow the document or change it; never silently diverge.

## The vibe

A small newsroom product, not a dashboard. The site makes one promise —
*every claim linked to its source* — and the design's whole job is to keep
that promise legible: print-newspaper restraint (serif masthead, paper
ground, navy chrome), data rendered quietly and exactly once, methodology
never more than one obvious click away. Agreement, not a candidate grade.
When in doubt, remove ink.

## Voice

- **Verbs describe what actually happens.** Sources are *counted*, not
  "viewed." A status verb must match what the reader currently sees — a
  comparison that "agrees" must agree with the number beside it, including
  when a personalized lens has changed that number. Test: would the
  sentence still be true in a cropped screenshot?
- **No personalization theater.** No user-facing "my." Imperatives are
  fine: "Customize your sources" is an instruction, not a possessive.
- **States explain themselves in words.** Color, icons, and aria-labels
  never carry a meaning alone; the visible text says the same thing the
  screen reader hears.
- **No system vocabulary in user-facing prose.** The implementation never
  describes itself: "election-scoped paths," "ballot inventory," and
  "panel" outside the audit line are internal words. Test: would you say the
  sentence aloud to a neighbor?
- **Demonstrate, don't advertise.** Provenance is declared by linking and
  counting in place, never claimed in prose.
- **Swagger is allowed where the page earns it.** The register is
  confident on purpose — a progressive city deserves a guide that sounds
  like it believes so — but the confidence is licensed by evidence on
  the same screen, never by assertion. A race page's "Every endorsement
  that matters, with receipts" passes because that page lists every
  endorsement, dims the ones the reader's own selection excludes, and
  links each to the source that published it. The same words over a page
  that showed a number and no rows would be advertising. Test: if a
  reader called the bluff, is the proof already in front of them?
  *(2026-08-04. This qualifies the rule above rather than excepting it:
  the swagger is a claim the demonstration has already paid for. README,
  "Why this exists," is where the register comes from and why it is not
  borrowed.)*
- **Never leave arithmetic doubtful.** Where a count and a share can
  legitimately disagree, say why inline — a race page's
  "(co-endorsements split)" exists so a reader who does the division isn't
  left doubting the math.
- **Labels are declarative and short.** Signal name first, then the
  choice: "All sources: Danica Noble · 67%". Drop words a position already
  implies — a reference bar that agrees with the headline directly above it
  need not repeat the name.

## Color

Semantics, not decoration. Values are tokens in `base.css`; page CSS never
introduces a color literal except the bounded #673 and #711 component tokens below. The families and what they mean:

| Family | Tokens | Meaning |
|---|---|---|
| Navy | `--navy` | Site chrome and state announcements: bands, hero, lens banner |
| Paper / white | `--paper`, `--white` | Content ground / data surfaces (cards, rows) |
| Teal | `--teal` | The brand and data accent: meters, section rules, card borders |
| Blue | `--blue` | Hyperlinks. Nothing else |
| Agree tone | `--tone-agree-*` | Agreement with the current reference; a *clear* leading choice |
| Differ tone | `--tone-differ-*`, `--amber` | Attention and divergence: comparison signals that differ, challenger sections, no-majority states |
| Neutral tone | `--tone-neutral-*` | Not covered; no signal |
| Meter | `--meter-*` | The segmented meter's own palette (docs/METER_V2.md § Color): track, tie depth, trailing ranks, seam ink. Its majority and no-majority fills are `--teal` and `--amber` themselves |
| Actual tie | `--meter-tie`, `--meter-tie-violet`, `--tone-tie-*` | Tied endorsement runs and existing tie framing; never a sole sub-majority leader |
| Result alignment | `--teal`, `--result-aligned-track`, `--result-different`, `--result-different-track` | Recorded winners/advancers or unique current unofficial vote leaders, compared with the aggregate recommendation |
| Focus | `--focus` | Every focus ring, everywhere |
| Compact general controls | `--compact-precinct-surface`, `--compact-expanded-surface`, `--compact-editor-shadow` | Approved C v5 precinct ground, expanded ground and editor shadow; general-only ownership |

**Rule:** a new UI state must first try to inherit an existing family *by
meaning*. Introducing a new hue amends this table and is a design
decision, never just a CSS edit. Example: the "No majority" state joined
the differ/amber family rather than adding a yellow.

The three compact-control tokens are defined only on `[data-compact-filters]` in
optional `precinct.css`: `#edf4ef` for the precinct ground, `#e7f2ef` for expanded
controls, and `#102a4326` for the editor shadow. These exact C v5 values were
already approved. Their local ownership preserves frozen primary/shared
`base.css` bytes; it does not permit other page color literals or a new palette.
Consumers use these tokens, and a change to their meanings or values amends this
contract in the same PR.

The approved #711 palette is scoped to the existing meter/result/tie components in
`guide-race.css`, rather than changing the archived shared shell in `base.css`.
Its tokens are the exact values above; no other component or shell palette changes.
The legacy brown `--meter-tie-deep` remains in the frozen shell for archive compatibility;
fresh tie rendering uses `--meter-tie-violet`.

## Typography

- **Serif is the masthead voice; sans is the data voice.** The Georgia
  serif stack is for page identity: the hero h1, section h2s, subpage h1s.
  The sans stack (`system-ui` first) is for everything that *is* data:
  names, numbers, labels, controls.
- **Maximum weight belongs to data.** Candidate names and percentages get
  the heaviest weight on the page; labels and eyebrows sit at 600–700 and
  never shout over the data.
- **Eyebrows/kickers** are uppercase and letterspaced, colored for their
  ground: mint on navy, teal on paper. (Mint on cream fails contrast — an
  eyebrow's color is chosen by its background, not copied from another
  context.)
- **Reading measure ≠ page frame.** Every page renders the one 76rem
  `.page` frame on the shared backdrop; prose that wants a book measure
  constrains an inner ~46rem column. The frame is the site; the measure is
  the content.
- **Long prose gets room between topics.** How this works uses the same measured
  page head and column as Updates. Short paragraphs sit under serif section
  headings, with a larger gap between sections than between paragraphs.
  Counting, source eligibility, and comparisons are separate topics; a heading
  must not become a catchall for paragraphs that need their own heading.
  *(2026-10-16, issue #551: the Corrections page's restraint is the reference.
  Its public name is now Updates; its tagline remains "We get it right, eventually.")*

## Page vs. modal

- **Modal**: a drill-down into the context you are already in — evidence
  for the thing under your cursor. Ephemeral, hash-addressable, and Escape
  returns you exactly where you were.
- **Page**: a task with its own state and consequences, or standalone
  content people should land on from a link. Gets its own URL, `<title>`,
  nav presence, and footer. Examples: Sources (a form), About, the
  archive, one race.
- Test: if it needs its own `<title>`, an unfurl, or someone would
  bookmark it, it's a page. If it's "show me the receipts for this row,"
  it's a modal.
- The answer is a consequence of requirements, not an identity. Re-run the
  test when requirements change instead of defending the current form.
  *(2026-08-04, issue 136: race detail was a modal while it was
  evidence-on-demand. Sharing a race became a requirement, and a fragment
  over the guide can never carry it — fragments are not sent to the crawler
  that builds a preview, so every "shared race" unfurled as the guide. The
  test above then reads the other way: a race needs its own `<title>`, its
  own unfurl, and its own address, so it is a page, and the modal is gone
  rather than kept as a second copy of the same content.)*
- **A page whose content is one record is named for that record.** The
  plural-noun rule above names page *kinds* — Endorsements, Comparisons,
  Sources — and a race page is not a kind; it is one race. Its h1 and its
  `<title>` segment are the race's own name, with the election still in the
  eyebrow above it, so eyebrow and title read as one name exactly as they do
  everywhere else: "August 2026 Primary · Metropolitan King County Council —
  District 2". *(2026-08-04, issue 136. This is an exception, and it buys
  what an exception must: the address is shareable and the share is legible.
  It bends no other rule — the shell, the eyebrow, the title grammar, and
  the nav all apply unchanged, and the page's nav presence is the
  Endorsements entry it belongs under.)*
- **A page's actions are its masthead's.** A race page's Share is the
  masthead Share, which copies the address the reader is on — that race's
  own. No second per-race share control exists anywhere, because there is
  now no context in which one would copy a different link.
  *(2026-08-04, issue 136: the dialog's own Share button was the only way to
  copy a race's link while race detail was a modal; opening the race is what
  copies it now.)*

## Text vs. icons

An icon may stand alone only when at least one of these holds:

1. The glyph is universal in context (× close, share arrow), or
2. A text path to the same destination exists on the same page (the
   footer's info icon may be icon-only because the masthead links the
   About page in words).

Every icon-only control carries `aria-label` + `title` tooltip + a visible
focus ring + an adequate tap target. The *primary* path to the methodology
is always words — trust links don't hide behind glyphs.

**Collapsing a text path costs a word.** A control that collapses a text
path carries a visible label, because collapsing is precisely the removal
of the text path that would have licensed an icon-only control. The
masthead's mobile nav control is therefore the word "Pages", with no glyph
at all — matching the band's own logic, where the brand is the one lockup
carrying a mark and every other member is words. Note that clause 2 above
licenses the footer's info icon by way of a masthead text path; keep that
dependency in view when changing how the masthead collapses.

**Emoji are text, not iconography.** They may appear only in purely
textual contexts — a `<title>` label, a plain-text email — never as UI
icons. Rendered UI uses real SVG icons from a standard library (Lucide or
similar): they take the surrounding color, stroke, and focus treatment,
while emoji render differently on every platform and can't be styled.

## Titles & naming

- **`<title>` grammar.** Election-scoped pages:
  `"<page> — <election> — Seattle Elections Guide"`, the guide page
  included. Election-agnostic pages (About, archive, 404):
  `"<page> — Seattle Elections Guide"`. The same values feed `og:title`.
  *(2026-08-01, issue 192: the guide page's exemption from the page
  segment is retired. It bought a lighter social unfurl and cost a
  carve-out in the rule that makes eyebrow, h1, nav, and title agree
  everywhere else — a cheap exception with an expensive cascade.)*
- **One canonical election name per context** — one display form (hero),
  one dated archive form — both generated from election data, never
  hand-typed.
- **The brand lives in the band; the h1 is the page's own name.** Every
  page, the guide included, names itself in its h1 and agrees with its nav
  label: Endorsements, Comparisons, Sources, How this works. The election
  is the eyebrow above it, never the h1. No page h1 repeats the site name.
  *(2026-08-01, issue 192: this inverts the previous rule, under which the
  guide's h1 was the election. That made the strongest identity on screen
  change size ~4x between page types, and left the guide as the one page
  not naming itself.)*
- **Election-scoped pages are named with a plural noun**; agnostic pages
  are named with a phrase. Eyebrow and h1 then read as one name — "August
  2026 Primary Comparisons" — so the naming itself marks which pages are
  election-scoped. Rejects "Compare" (a verb) and "Customize your sources"
  (an instruction) as page names.
- **Dates are for humans**: "August 4, 2026", never "2026-08-04". A kicker
  states the same fact at a different precision, not twice: "ELECTION DAY
  · AUGUST 4" above "August 2026 Primary".

## Site shell

> **Status (2026-08-01).** Adopted, and now applied to every page. **New
> pages must use the `shell.page_head` macro
> (`rendering/templates/_shell.html.j2`); do not hand-roll a header.**

**Exceptions are allowed; cascades are not.** An exception must name what
it buys, and must not require a second rule to bend to accommodate it.
Test: trace every rule the exception touches; if any needs amending to
survive it, change the exception's shape, not the other rules. *(This is
why the mobile nav control is a word rather than a hamburger: an icon-only
menu would break "text vs. icons", whose own clause licensing the footer's
info icon depends on the masthead linking About in words — two rules
bending for one convenience.)*

**Slots.** Every page renders one sequence, and slots may be absent but
are never reordered or restyled per page:

**Masthead → Context → Body**, where the masthead is the band plus the
teal rule that closes it, Context is the election-day banner, and the Body
opens with the page head (unless the dial has pulled it into the masthead),
then any sticky strip, then content.

- **The dial.** The masthead's navy ends after the band — except on the
  page the brand lockup links to, where the page head sits *inside* the
  masthead, above the closing rule, on navy. Exactly one page qualifies by
  construction, and it stays correct on its own if home ever moves.
- **Presence follows the page's kind, not its identity.** The eyebrow and
  the Context banner appear iff the page is election-scoped; their absence
  is the only marker agnostic pages need. Share appears iff the page is
  shareable — the same flag that governs its social card, which is why the
  404 has neither.
- **Primacy is bought with named exceptions, and they are enumerated.**
  Being the brand-link target currently buys exactly one: the extended
  masthead. A second must be argued and written down here, not accrued.
- **Width changes what is visible, never what is said.** Slot order,
  presence, and copy are width-invariant. Only presentation adapts — an
  action may change how it is presented (a visible control, or a labelled
  item inside the nav disclosure) but may never disappear. Rejects a
  desktop-only tagline or a mobile-only warning.
- **Desktop's dividend is simultaneity.** Extra width buys more visible at
  once — nav inline instead of behind a control, provenance on one line —
  never additional content or a second tier of chrome.
- **Masthead = actions on the page; footer = meta about the site.** Share
  belongs to the masthead because it acts on what you are reading;
  Contact, source files, and the methodology link belong to the footer.
- **Every in-site link is root-relative.** An absolute production URL walks
  readers off any other origin — a local preview, a staging deploy, a PR
  preview — straight to the live site. Only links that genuinely leave the
  site carry an origin.
- **Every off-site link opens in a new tab**, with `rel="noopener"`, so a
  reader checking a receipt keeps their place in the guide. The referrer is
  left intact so the organizations we cite can see the traffic. An icon-only
  external control carries the new-tab hint in its accessible name, since it
  has no visible text to carry it.
- **A page's path matches its name.** Renaming a page renames its URL, with
  a permanent redirect from the old address so nothing already linked
  breaks. *(2026-08-01: `/compare/` became `/comparisons/`.)* A page that
  arrives where a fragment used to be is the same promise: a `#race-…` link
  shared before race detail had an address is forwarded to that address,
  carrying whatever selection the reader had. *(2026-08-04, issue 136.)*
- **Nav order follows dependency, not traffic.** Endorsements is the
  destination, Sources is what feeds it, Comparisons is a view derived from
  those sources, and How this works explains all three. *(2026-08-01: this
  reverses the order issue 197 shipped, which placed Comparisons second.)*
- One masthead band and one footer implementation, shared by every page —
  never re-implemented per page. One page head likewise, in two measure
  modes: full-bleed, or constrained to its page's reading column when that
  page sets one, so a tagline never outruns the prose beneath it.
- The footer has exactly three jobs: exit ramps (the icon cluster and the
  methodology link), provenance, and closing the frame. It is one navy band
  mirroring the masthead: provenance is a two-line whisper beside the brand,
  becoming one full-width line below brand and actions under squeeze. Content
  that *explains* the guide belongs to the About page, not the footer.
- **Sticky strips are one family.** A persistent surface states current
  state *and carries its actions*: the guide's controls bar, its always-present
  sources strip ("Counting all 40 sources" by default; "39 of 40" under a
  lens), and the Sources action bar. Same placement logic and surface
  treatment everywhere; two strips doing the same job must rhyme.
- **Shared controls are actual components.** A segmented choice uses the
  shared radio structure and focus treatment; a task page does not draw a
  button group that merely resembles it. Election filter bars, labeled selects,
  segmented radios, and their status placement share one rendered component;
  pages provide only labels, options, IDs, and behavior hooks.

## Data display

- **Sparse endorsements still name the measured leader on the guide card.**
  When endorsements exist but fall below the consensus floor, the heading
  names the candidate or choice. The warning below explains that there are
  too few endorsements to measure agreement; the meter and source count stay
  visible. With no endorsements, the heading remains "Too few endorsements".
  This display does not create a consensus recommendation (issue
  [#532](https://github.com/shaug/seattle-election-guide/issues/532)).
- **Every quantity has exactly one value on screen.** Under a personalized
  lens, every computed number — counts, shares, meters, "Leading choice"
  kickers — shows the lens value; the audited baseline appears only as the
  explicitly labeled "All sources" reference line, never as an unmarked
  second number.
- **A name appears once per page.** A page that states a result and then
  lists what produced it must not head both with the same name: one of the
  two is the heading. On a race page the headline *is* the leading choice's
  heading, which is why that candidate's section renders none.
  *(2026-08-04, issue 136 follow-up: the two were rendered independently and
  captioned each other's numbers — "Based on 11 endorsing sources" above
  "8 of 11" — which is the drift a single heading makes impossible.)*
- **Agree tone claims a favourite, so a tie never wears it.** A tie is a
  warning that the reader has to choose, not a recommendation to accept:
  every tied candidate takes the actual-tie purple family, in its own section, marked
  with a "Tied for lead" kicker. Green would say the opposite of what a tie
  means. *(2026-08-04, issue 136 follow-up.)*
- **Don't count a list the reader is looking at.** A heading above a list of
  endorsing sources states no number of them; the count is the list. It
  survives in the visually-hidden accessible summary, because a reader who
  cannot see the rows cannot count them. *(2026-08-04, issue 136 follow-up.)*
- **One meter — scoped per page.** One chrome, a constant-width bar of
  equal-width blocks, one per endorsement, grouped into candidate runs in
  standings order — leader first, the site's own teal for a majority,
  lavender/deep violet for an actual tie, amber for a sole leader short of one, muted slate/taupe/plum for
  trailing candidates — but not one *instance* everywhere: the guide and
  ballot overview render one shared meter per race, and the race-detail page
  renders one per candidate, each colorized and context-marked for that one
  candidate. The blanket "a single chrome everywhere" rule held while a
  meter was expensive enough that only one per race made sense; #325
  (2026-08-05) found the platform could compute and render one per candidate
  from the same once-per-race block layout at negligible cost, at which
  point a page whose whole subject is comparing candidates gained more from
  a meter beside each name than from one meter borrowed via clickable chips
  — which is what #315 tried first, shipped, and then had to retract when
  live testing showed the chips could highlight one candidate's share inside
  a *different* candidate's own card. At rest on every device the seams
  between blocks are invisible and a left-aligned percentage overlays the
  leader's blocks; hover or keyboard focus trades that percentage for hairline
  seams and per-block tooltips. On touch, a press-and-hold reveals the same
  detail; sliding across the meter updates the source popup under the finger,
  and release restores the percentage. Short taps and ordinary swipes keep
  the resting view and native page scrolling. *(2026-10-17, issue #561:
  replaces always-visible touch seams and the hidden touch percentage.)*
  A candidate section's own meter states no resting
  percentage inside the track at all — its count and percent ride in a
  label beside the meter instead, since a percentage does not fit inside a
  half-endorsement sliver of highlighted bar. The full design — color,
  seams, splits, edge states, motion, and accessibility — is
  `docs/METER_V2.md`; where this line and that document disagree, the
  document wins. This is the only endorsement-meter design: a standalone
  gradient fill and permanently segmented pointer overview are both invalid.
  The retired percentage-only pill is gone from every chrome that draws a meter,
  the social card included
  (#316, 2026-08-05, `rendering/og_image.py`) — a static image has no hover
  to trade the percentage for seams, so it renders the resting
  pointer-device state permanently rather than the print row's static-both
  one (docs/METER_V2.md, Decision log #23).
  Archived guides follow the same rule. Hosting rejects the retired `--meter-fill`
  chrome in every served HTML page. Current presentation uses verified archived data without
  serving its old chrome; original ZIP bytes remain available for audit. Original source1.0
  staging still applies its retired-input rule because it serves copied overview bytes.
- **The meter's own caption states a count, not a percentage — and never the
  recommended choice's own name.** "21½ of 23 endorsements," using the same
  formatter the meter's split blocks make honest: a co-endorsement's half is
  a divided block, so the caption's fraction is no longer invented after the
  fact. The name is left out deliberately: the card's headline one row up
  already states it, so a name in the caption too would only repeat what the
  reader just read. A tie or a race with no single recommended choice has no
  one count to lead with, so the caption falls back to naming only the
  denominator, exactly as it did before the count-caption existed.
  *(2026-08-04, meter v2 / #314; name dropped in the same ticket's own
  review.)*
- **Alternative signals share one quiet component.** Anything that is an
  *alternative* to the result the reader asked for — today, the full-panel
  baseline under a lens — renders as a tone-tinted info bar. No pills, no
  badges. Reference bars sit at the card foot, never interleaved with the
  primary data. *(2026-08-01: issue 124 moved the one external comparison
  source off the guide entirely; comparing sources is the Comparisons
  page's job.)*
- **Data-ink discipline.** Page-level state never repeats on every card;
  zero-counts are suppressed rather than printed forty times; taxonomy
  renders as plain muted text, not chrome; rows in a grid align so a row
  of meters can be swept in one eye movement.

  *Comparison-page decision recorded July 31, 2026:*

- **Comparison starts from one explicit reference role.** The first column is
  stable in position and cannot be removed, but its signal is selectable. Every
  agreement, difference tint, and difference count is relative to that chosen
  reference. All sources is the published default, not an immutable baseline.
  Every column shows its full identity at rest and becomes an editor only while
  the reader is changing it. Position and accessible names carry the reference
  semantics; the header does not repeat a visible “Reference” label. The Race
  header contains only “Race.” When another column can be added, an icon-only
  plus action lives in the last comparison header and opens the new column's
  identity editor immediately. At capacity the plus disappears; capacity is
  implicit and no maximum message or disabled control is shown.
- **One quiet difference encoding.** A comparison cell carries its choice and
  an amber tint when it differs. Agreement recedes; the race identity carries
  the single visible and accessible “Differs” label. Shared conventions do not
  need a repeated legend.
- **Responsive comparison context stays attached.** At narrow widths the Race
  and reference columns remain fixed while the remaining comparison columns
  scroll horizontally in discrete column-sized steps. A directional cue states
  when more columns are offscreen. The fully supported viewport floor is 320px:
  at and below that width the Race column keeps a 5rem minimum and source
  columns keep a 6.35rem minimum. Narrower viewports may show less of the next
  comparison, but those columns never compress further or collapse into stacked
  cards; the comparison rail remains independently scrollable and the page
  itself never pans horizontally.
- **Absence of a majority is information.** A leading share at or below
  50% gets the "No majority" treatment in the differ/amber family —
  default styling never overstates confidence.

## Accessibility

Stated once, applies everywhere: color tone is never the only carrier of a
meaning; visible text and aria text agree; one `--focus` ring token on
every interactive element; screen-reader-only status strings read as real
sentences with real separators; every page keeps the skip link.

## Non-goals

This document governs the screen. Printing is the same page with its
chrome suppressed (issue 193 retired the separate PDF edition), so the
print stylesheet inherits these rules rather than restating them. This
document does not govern **dark mode** (none exists; adding one is a
project, not a patch).

## Changing this document

Amend it in the pull request that changes the rule, as a dated decision.
If shipped UI and this document disagree, one of them is wrong — fix
whichever it is, deliberately. A design change isn't done until any new
rule or rationale it produced lands here.

## Voting precinct control (#608)

The November2026 general guide places Precinct in the shared filter bar on
Endorsements and Comparisons. The #673 compact-bar revision below supersedes the
original wrapping headers and inline clear control. An unset choice shows Precinct;
a selected choice shows its precinct identity. Clear precinct selection is inside
the editor. The action opens an attached native
dialog with one searchable field and Select and Cancel buttons. The October28
#657 revision below supersedes the original native precinct suggestions and
Find my precinct link. Search edits a draft: only Select applies it;
Cancel and Escape preserve the applied choice, URL and device memory. Opening or
canceling this ephemeral editor does not change the query or fragment. Opening
focuses search; native modal focus containment and return focus preserve keyboard
context. The compact bar adapts within narrow containers. There is no separate search strip
or explanatory line above it. (Scott's explicit preview revision, October 25, 2026.)
There is no setup section, district questionnaire or embedded map. The first-version
no-address restriction is superseded by the optional #657 voting-address path below.
Both general list views default to Contested, visibly selected; All remains enabled
and adds applicable uncontested races within existing public eligibility. Selecting
a precinct constrains both modes to applicable covered races and measures. Ballot remains enabled and intersects its original scope with precinct membership.
Offer only scopes with at least one applicable covered contest, including measures,
before All/Contested visibility or source preferences. Keep a valid selected scope;
fall back to All only when it becomes inapplicable, with the control, rows and URL
agreeing. Clear restores the full scope list and retains a valid scope and race mode.
Full/Differing remains enabled while a precinct is selected. Differing intersects
the eligible rows with differences between the selected source columns; it does
not change geographic membership, source eligibility or scoring. Changing or
clearing precinct preserves View as well as Races.
Source choices and comparison columns remain independent. Clear removes geography
while preserving race mode. Selected precinct text uses stronger weight; control
bodies align vertically in the compact bar. Unsupported choices never claim an exact ballot. Primary has no
precinct control.

## Optional voting-address path (#657, October28,2026)

The Precinct dialog has one address-or-precinct combobox and one styled
suggestion list. Reviewed precinct matches appear immediately; debounced address
matches join the same list. Numeric queries may match both. Each row has a small,
right-aligned Address or Precinct label. There are no mode buttons, native datalist
or old Find my precinct text link. A later explicit October28 revision adds one
compact upper-right circled-i link to the same county precinct search. It keeps the
historic new-tab/no-referrer semantics, has a descriptive accessible name, visible
focus and a phone-sized target, and never carries search text. It joins the native
focus loop without changing the initial input focus or Select/Cancel behavior.

Selecting a suggestion fills the shared draft; only Select commits it. Raw text,
an exact typed code or the first suggestion never silently chooses. Direct precinct
suggestions stay usable for away/overseas voters and lookup failures. No second
form or device position is requested. Canonical street/building scope does not
verify an omitted unit or voter registration; ambiguous or unsupported scope fails
closed. Loading, empty results and failures are announced without result counts or
prompts to type more. The modal keeps a stable size and position across those states;
suggestions overlay the content below the field instead of increasing modal height.
Keep that scrollable surface inside the modal, with usable focus/actions at a narrowed
visual viewport or when the keyboard changes its height. Arrows activate real options;
Enter chooses the active option without submitting; Tab never chooses. First Escape
closes suggestions, next Escape cancels. Composition input must finish before lookup.
Preserve native modal focus containment/return and usable phone scrolling/wrapping.

An address is only a lookup aid. After Select, the summary and reopened editor show
its resolved precinct, exactly as direct precinct selection does. Cancel preserves
the applied precinct. Cancel, close, re-edit and history discard transient address
drafts; no address label remains as applied state. Clear removes the precinct;
history, reload and shared links restore precinct identity. No address enters URL
or device memory. Explain County/Esri transmission and possible provider retention
beside the unified field before lookup. SEG retains only the existing precinct code.
See ADDRESS_LOOKUP.md.

## November 2026 ballot sequence

Approved October 26, 2026, issue #609: the November guide uses the official
ballot's contest sequence with ten flat headings: State measures; Federal;
State; County; State Supreme Court; Court of Appeals, Division 1, District 1;
West Electoral District; City of Seattle; Seattle Municipal Court; City of
Seattle — measures. Existing heading styling applies; there is no new ballot
column/page layout. Legislative districts ascend numerically, with senator then
House positions 1–2 within each district. The Seattle measure follows all
municipal-court positions.

Endorsements, compact overview, print and Comparisons consume the same supplied
section/race order. Filters retain relative order and omit empty sections.
Existing control mechanisms and source/scoring/visibility policies remain in
force. The guide's existing Ballot filter tokens keep their prior meanings,
independent of the new display grouping; this does not introduce location setup.
See BALLOT_INVENTORY.md for the source, literal-versus-SEG heading distinctions,
and the explicit November-only boundary. Historical primary publications do not
inherit this mapping.

## Adaptive compact general filter bar (#673)

On precinct-enabled general Endorsements and Comparisons, the earlier wrapping
header row is replaced by one centered 46px control row:
**Precinct → View → Races → Ballot**. Keep the existing reactive race-count
phrase visible and intact. It sits beside the centered group when its whole
phrase fits in the remaining side space; otherwise it occupies its own centered
line below. The control row remains 46px, while the bar grows for that count line.
An empty precinct trigger says “Precinct”; the editor retains its “Select” action.
View, Races and Ballot use real HTML selects and native option menus. Their
closed faces keep the approved icons and readable values; the actual select
owns pointer/keyboard input, the accessible name and complete current value.
There is no separate dialog, editor heading, Cancel button or repeated value paragraph.
Each trigger has a matching outline SVG (pin, eye, filter lines, ballot box),
readable text, a 44px minimum target and visible keyboard focus. When the actual
bar can fit the wide presentation, the Ballot trigger shows only its approved closed
summary: “All ballot races” by default, without a “Ballot” prefix or
redundant “Seattle”. Constrained/mobile bars show only “Ballot” and its own-scope
active dot; the current value is already evident below and in the native select.
The full selected scope remains in its accessible name/title, selected native
option and complete option menu in both treatments. The October31 constrained, centered treatment shortens only 13 exact known closed
faces: Congressional District 7 and 9 become “Congressional D7” and
“Congressional D9”; Legislative District 11/32/34/36/37/43/46 become
“Legislative D11/D32/D34/D36/D37/D43/D46”; Metropolitan King County Council
District 2/4/8 become “King County Council D2/D4/D8”; Seattle City Council
District 5 becomes “Seattle City Council D5”. Each choice retains its own number;
`D` immediately precedes that number without a space, as in `D7`. The other 11 choices keep their full wording. This is a
presentation mapping, not a change to native labels, values, accessible names or
titles. Unknown values and changed full labels remain complete; do not derive
new abbreviations or truncate. Measure the complete closed-summary family in the
actual font/container, rather than copying the study's 231px reservation. Keep
the existing centered location and order.
A subtle teal dot marks only a non-All Ballot scope. Merely
selecting a precinct does not activate it.

Reserve each control’s width for its complete value family within the admitted
fit mode: all View and Races alternatives, approved closed scope summaries or narrow Ballot,
and the catalog’s complete full or safely shortened precinct identities. Ordinary
selection changes retain these track widths and edges; font/container changes may
select a different fitting mode. These are role-specific measured reservations,
not four equal columns or fixed mockup breakpoints. Unknown long labels must
remain complete rather than being clipped to a reservation.
Retain measured fractional widths; independently rounding each track upward must
not create overflow where the complete families fit.

The actual container and rendered font/content decide the cue: arrows without
underlines when the full contents fit, underlines without arrows when constrained.
If even the underline layout overflows, reclaim inline padding based on its
measured deficit. Only if that is insufficient, remove remaining gaps and move
the scope dot above the text into the Ballot trigger’s top corner; preserve its
visibility, every label, font size, icon and target minimum. If that zero-spacing
inline layout still overflows, place each icon above its single-line value inside
the same 46px control, with a 2px vertical gap and 2px inline inset separating adjacent labels. Keep 14px icons and text and the
44px target minimum; this is not wrapped Ballot text. Measure again on every fit
and return to the inline layout whenever it fits.
Do not use the mockup's measured 354px as a universal viewport breakpoint. Full
precinct names appear when they fit. Only an exact `SEA DD-NNNN` catalog name
with a unique shortened form may display `DD-NNNN` under constraint. Keep every
digit, other prefix and distinguishing suffix; keep the full name in the editor,
accessible name and title. Applied text is always precinct identity, never an
address draft. No ellipsis is used to make identity appear to fit.

Scott’s October31 native-selection refinement supersedes the earlier three
filter dialogs: a normal native option commit applies View, Races or Ballot
immediately, with focus remaining on the select. Native menu navigation and
dismissal follow the platform; opening or canceling an uncommitted menu creates
no extra selection state. Do not imitate these menus with a renamed custom popup.
Escape retains a selection that normal native input has already committed.
Native menu opening, uncommitted Escape and real option commits require the
[mandatory interactive acceptance](FRONTEND.md#native-select-verification); automated
headless selection/state checks do not replace that evidence.
Precinct alone opens an attached, viewport-clamped native dialog with a transparent
backdrop. It tracks its anchor and visual viewport across rotation, zoom and
layout movement, keeping its search, suggestions and actions reachable. It
retains its own draft, Select, Cancel, Clear, address privacy, Escape and focus
return behavior.
The normal suggestion overlay keeps at least 8px before the first action,
including Clear. A complete-option fallback for a zoomed viewport uses editor
scrolling while preserving that action boundary.
The compact surface changes no availability, fallback, race visibility, measures,
source/scoring, URL/history or precinct-only persistence rule. Primary keeps its
legacy controls and archive styles.


## Guide Sources and filters group (#679, November 1, 2026)

Scott approved the existing Sources-group study and its mobile space tradeoff.
On the precinct-enabled general Endorsements guide, Precinct, View, Races and
Ballot retain their ordered row. Sources joins that centered group when the
complete controls, source summary and intact live race-count phrase fit the
actual container in the resolved font. Otherwise the four controls stay on row
one and Sources shares row two with the count. Both rows remain sticky at every
supported width; there is no third count row or auto-hide. This supersedes the
Guide's separate navy source strip and its previous separate count line, while
Comparisons keeps its existing composition.

Sources remains an underlined navigation link to the existing Sources page,
with the shared outline icon family and forward arrow. Its visible summary is
“All N” or “N of M,” derived from the current source selection; its accessible
name states the full counting sentence. It has its own source state and does
not borrow Ballot's scope indicator. Native control targets, complete precinct
identity, independent menu cues, compact centered Ballot and focus behavior stay
as specified above. The measured sticky height clears in-page anchors and
includes visible notices. The study's 47px wide and 92px narrow examples describe
the approved geometry, not a fixed viewport breakpoint.


Within the two-row group, Sources and the count must fit the actual row as well.
Reclaim only the needed space between them; if that is insufficient, Sources may
place its unchanged prefix above its complete value inside the existing 44px
navigation target. The icons keep their size, the count stays on one line, and
the group keeps two sticky rows. Measure the complete family again in that face
and restore ordinary spacing and the one-line face when space returns. A wide
viewport does not grant a minimum size to a constrained Guide container.

## Shared selection styling (#672)

The current general Guide and Comparisons keep the one-field custom Precinct
search and their real finite HTML selects. There is no second Results control,
datalist, new provider behavior or additional selection state. Shared selection
surfaces use paper ground, navy text, the screen-sans family at 14px and existing
borders. Hover/active options use a white surface and navy outline, without a navy
fill. Amber remains the keyboard-focus cue; a native checked option retains its
checkmark and stronger weight, independently of hover or focus. Options have a
44px minimum target, complete readable text, native groups and disabled semantics.

Progressive styling opts both the select and `::picker(select)` into
`appearance: base-select` only when that value and the picker selector are
supported. It uses the browser's real select and picker, not a custom menu
imitating one. The ordinary native menu remains the fallback. A customizable
picker can replace an OS-specific mobile sheet; pixel-identical menus across
operating systems are not promised. The existing compact face, measured tracks,
full accessible values, Sources fit, sticky count and independent filters remain
unchanged. Picker geometry is bounded to the actual viewport without a copied
demo offset or clipped option labels.

Actual candidate-bound interaction and visual acceptance remain required under
FRONTEND's native-select verification. Headless geometry/pixels can establish the
enhanced app surface they actually measure, not physical-device, spoken
screen-reader, IME or unavailable interactive-session results. Immutable primary
archives and their existing presentation are preserved.

## Election Updates (#676)

### Individual updates (#677)

An index headline is a descriptive link while retaining its existing serif type, color and full
entry beneath it. The linked page uses the same election shell and measured text column, with
Updates current in navigation. Show Back to Updates, election identity, the existing headline as
the single H1, original publication date, action badges and topic labels, complete body and existing
affected-page/evidence links. Topics link to the same election's filtered index; the ordinary Back
links return to its full log. Include a return link after the content. There is no filter toolbar,
sidebar, comments or recommendation panel on a detail. Preserve existing colors, external-link
safety, visible keyboard focus and readable narrow/mobile layout. Native browser Back restores
the prior index filter and reading position. Stable election-scoped URLs and direct/no-JavaScript
reading are part of this treatment, not a client-only modal or generated headline slug.

The approved version-2 study uses the existing measured election shell and serif entry headlines.
The tagline is “What changed in this election’s endorsements, sources and results.” Dates mean
publication in this guide. Quiet action tags and topic labels accompany each dated chronological
entry; evidence and affected-page links remain visible. No illustrative events become production data.

Scott’s November 1 refinement replaces the study’s four choices with exactly three text buttons:
Endorsements, Sources, Results. The topics toggle independently with OR matching. None selected
is the default and shows all updates; clearing the final selected topic restores the complete log.
All three selected remain selected. There is no All updates button or extra focus stop. Navy/high-contrast highlight and `aria-pressed` expose selection. Buttons have
centered labels with no checks, icons, placeholders or reserved icon space; targets are at least
44px. Below 40rem the three choices wrap naturally, filling each row without a reserved empty
cell or horizontal page overflow.
Keyboard Tab order follows the labels; native Enter/Space activate the focused button with the
shared focus-token outline. Selection preserves focus and announces the matching count through
a persistent polite status element. An empty result says so and explains that clearing selections
restores the complete log.

Topic-selection and date-explanation helper paragraphs are omitted below the topic bar.

The complete log remains readable without JavaScript; server controls are disabled until enhanced
and the page explains that filtering needs JavaScript. Topics never inherit ballot, precinct or
source selections. Software release history is linked to GitHub Releases. This is an additive topic
group, not the shared mutually exclusive radio component. Legacy immutable schema1.0 pages retain
the original Corrections template and stylesheet until an explicitly scoped current-log migration.
