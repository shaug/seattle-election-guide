# Seattle Elections Guide — UI/UX Guidelines

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

Semantics, not decoration. All values are tokens in `base.css`; page CSS
never introduces a color literal. The families and what they mean:

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
| Focus | `--focus` | Every focus ring, everywhere |

**Rule:** a new UI state must first try to inherit an existing family *by
meaning*. Introducing a new hue amends this table and is a design
decision, never just a CSS edit. Example: the "No majority" state joined
the differ/amber family rather than adding a yellow.

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
  every tied candidate takes the differ family, in its own section, marked
  with a "Tied for lead" kicker. Green would say the opposite of what a tie
  means. *(2026-08-04, issue 136 follow-up.)*
- **Don't count a list the reader is looking at.** A heading above a list of
  endorsing sources states no number of them; the count is the list. It
  survives in the visually-hidden accessible summary, because a reader who
  cannot see the rows cannot count them. *(2026-08-04, issue 136 follow-up.)*
- **One meter.** A single chrome everywhere: a constant-width bar of
  equal-width blocks, one per endorsement, grouped into candidate runs in
  standings order — leader first, the site's own teal for a majority,
  ambers for a tie or a sole leader short of one, muted slate/taupe/plum for
  trailing candidates. At rest on a pointer device the seams between blocks
  are invisible and a left-aligned percentage rides the leader's fill, so
  the meter reads almost exactly like the v1 pill it replaced; hover or
  keyboard focus trades that percentage for hairline seams and per-block
  tooltips, and touch shows the seams always and the percentage never. The
  full design — color, seams, splits, edge states, motion, and
  accessibility — is `docs/METER_V2.md`; where this line and that document
  disagree, the document wins. Landed #314 (2026-08-04); the v1 gradient
  pill it replaced is gone from every chrome that draws a meter except the
  social card, which is its own child ticket.
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
