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
- **Never leave arithmetic doubtful.** Where a count and a share can
  legitimately disagree, say why inline — the race dialog's
  "(co-endorsements split)" exists so a reader who does the division isn't
  left doubting the math.
- **Labels are declarative and short.** Signal name first, then the
  choice: "All sources: Danica Noble · 67%", "Times differs · Keith
  Scully." Drop words a position already implies: "Times agrees" names no
  one, because the name is the headline directly above.

## Color

Semantics, not decoration. All values are tokens in `base.css`; page CSS
never introduces a color literal. The families and what they mean:

| Family | Tokens | Meaning |
|---|---|---|
| Navy | `--navy` | Site chrome and state announcements: bands, hero, lens banner |
| Paper / white | `--paper`, `--white` | Content ground / data surfaces (cards, rows) |
| Teal | `--teal` | The brand and data accent: meters, section rules, card borders |
| Blue | `--blue` | Hyperlinks. Nothing else |
| Agree tone | `--tone-agree-*` | Agreement with the baseline; the leading choice |
| Differ tone | `--tone-differ-*`, `--amber` | Attention and divergence: comparison signals that differ, challenger sections, no-majority states |
| Neutral tone | `--tone-neutral-*` | Not covered; no signal |
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
  archive.
- Test: if it needs its own `<title>`, an unfurl, or someone would
  bookmark it, it's a page. If it's "show me the receipts for this row,"
  it's a modal.
- The answer is a consequence of requirements, not an identity. Race
  detail renders as a modal while it is evidence-on-demand; if races are
  ever meant to be shared, unfurled, and landed on directly, the same test
  makes them pages. Re-run the test when requirements change instead of
  defending the current form.

## Text vs. icons

An icon may stand alone only when at least one of these holds:

1. The glyph is universal in context (× close, share arrow), or
2. A text path to the same destination exists on the same page (the
   footer's info icon may be icon-only because the masthead links the
   About page in words).

Every icon-only control carries `aria-label` + `title` tooltip + a visible
focus ring + an adequate tap target. The *primary* path to the methodology
is always words — trust links don't hide behind glyphs.

**Emoji are text, not iconography.** They may appear only in purely
textual contexts — a `<title>` label, a plain-text email — never as UI
icons. Rendered UI uses real SVG icons from a standard library (Lucide or
similar): they take the surrounding color, stroke, and focus treatment,
while emoji render differently on every platform and can't be styled.

## Titles & naming

- **`<title>` grammar.** Election-scoped pages:
  `"<page> — <election> — Seattle Elections Guide"`. The guide page
  itself: `"<election> — Seattle Elections Guide"`. Election-agnostic
  pages (About, archive, 404): `"<page> — Seattle Elections Guide"`.
  The same values feed `og:title`.
- **One canonical election name per context** — one display form (hero),
  one dated archive form — both generated from election data, never
  hand-typed.
- **The brand lives in the band; the h1 describes the page.** The hero h1
  is the election; the Sources h1 is the task; the About h1 is the
  promise. No page h1 repeats the site name.
- **Dates are for humans**: "August 4, 2026", never "2026-08-04". A kicker
  states the same fact at a different precision, not twice: "ELECTION DAY
  · AUGUST 4" above "August 2026 Primary".

## Site shell

- One masthead band and one footer implementation, shared by every page —
  never re-implemented per page.
- The footer has exactly three jobs: exit ramps (the icon cluster and the
  methodology link), provenance, and closing the frame. It is one navy band
  mirroring the masthead: provenance is a two-line whisper beside the brand,
  becoming one full-width line below brand and actions under squeeze. Content
  that *explains* the guide belongs to the About page, not the footer.
- **Sticky strips are one family.** A persistent surface states current
  state *and carries its actions*: the guide's controls bar, the lens
  banner ("Counting 39 of 40 sources · Edit sources"), the Sources action
  bar. Same placement logic and surface treatment everywhere; two strips
  doing the same job must rhyme.

## Data display

- **Every quantity has exactly one value on screen.** Under a personalized
  lens, every computed number — counts, shares, meters, "Leading choice"
  kickers — shows the lens value; the audited baseline appears only as the
  explicitly labeled "All sources" reference line, never as an unmarked
  second number.
- **One meter.** A single chrome everywhere, left-anchored fill matching
  the brand icon, label riding the fill (falling back to muted ink beside
  a low fill). The meter is slated for redesign: maintain it, don't extend
  it.
- **Alternative signals share one quiet component.** Anything that is an
  *alternative* to the result the reader asked for — the full-panel
  baseline under a lens, an external comparison source — renders as the
  same tone-tinted info bar. No pills, no badges. Reference bars sit
  together at the card foot, never interleaved with the primary data.
- **Data-ink discipline.** Page-level state never repeats on every card;
  zero-counts are suppressed rather than printed forty times; taxonomy
  renders as plain muted text, not chrome; rows in a grid align so a row
  of meters can be swept in one eye movement.
- **Absence of a majority is information.** A leading share at or below
  50% gets the "No majority" treatment in the differ/amber family —
  default styling never overstates confidence.

## Accessibility

Stated once, applies everywhere: color tone is never the only carrier of a
meaning; visible text and aria text agree; one `--focus` ring token on
every interactive element; screen-reader-only status strings read as real
sentences with real separators; every page keeps the skip link.

## Non-goals

This document does not govern the **print/PDF editions** (they share the
color tokens but follow their own compact layout idiom), the
**election-comparison pages** (under active design), or **dark mode**
(none exists; adding one is a project, not a patch).

## Changing this document

Amend it in the pull request that changes the rule, as a dated decision.
If shipped UI and this document disagree, one of them is wrong — fix
whichever it is, deliberately. A design change isn't done until any new
rule or rationale it produced lands here.
