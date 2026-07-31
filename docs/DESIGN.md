# Seattle Elections Guide — UI/UX Guidelines

The design decisions of UI polish rounds 1–5 (`UI_POLISH.md`,
`UI_POLISH_ROUND5.md`), promoted from ~70 dated ledger entries into standing
rules. Each rule cites its ledger origin so the full rationale is one lookup
away. Rules are meant to be decidable: each one can reject a real design. If
a proposal and this doc disagree, either follow the doc or change the doc —
never silently diverge.

## The vibe

A small newsroom product, not a dashboard. The site makes one promise —
*every claim linked to its source* — and the design's whole job is to keep
that promise legible: print-newspaper restraint (serif masthead, paper
ground, navy chrome), data rendered quietly and exactly once, methodology
never more than one obvious click away. Agreement, not a candidate grade.
When in doubt, remove ink.

## Voice

- **Verbs describe what actually happens.** Sources are *counted*, not
  "viewed" (D17). A comparison signal's verb must match what the reader
  currently sees, even under a personalized lens (H31). Test: would the
  sentence still be true in a cropped screenshot?
- **No personalization theater.** No user-facing "my" (H38). Imperatives
  are fine ("Customize your sources" is an instruction, not a possessive).
- **States explain themselves in words.** Color tone, icons, and aria-labels
  never carry a meaning alone; the visible text says the same thing the
  screen reader hears (G27, H32).
- **Never leave arithmetic doubtful.** Where a count and a share can
  disagree (co-endorsement splits), say why inline ("co-endorsements
  split", K51).
- **Labels are declarative and short.** Signal name first, then the choice:
  "All sources: Danica Noble · 67%", "Times differs · Keith Scully" (G27).
  Drop words a position already implies ("Times agrees" needs no name —
  the name is the headline above, H37).

## Color

Semantics, not decoration. All values are tokens in `base.css`; page CSS
never introduces a color literal (B9, J48). The families and what they mean:

| Family | Tokens | Meaning |
|---|---|---|
| Navy | `--navy` | Site chrome and state announcements: bands, hero, lens banner |
| Paper / white | `--paper`, `--white` | Content ground / data surfaces (cards, rows) |
| Teal | `--teal` | The brand & data accent: meters, section rules, card borders (B6) |
| Blue | `--blue` | Hyperlinks, only (B6) |
| Agree/green tone | `--tone-agree-*` | Agreement with the baseline; leading choice |
| Differ/amber tone | `--tone-differ-*`, `--amber` | Attention & divergence: comparison-only, Times differs, challengers, no-majority (J47, M63) |
| Neutral tone | `--tone-neutral-*` | Not covered / no signal |
| Focus | `--focus` | Every focus ring, everywhere (B8) |

**Rule:** a new UI state must first try to inherit an existing family *by
meaning*. Introducing a new hue is a design decision that amends this table,
not a CSS edit. Shipped example: "No majority" adopted the differ/amber
family rather than a new yellow (M63).

## Typography

- **Serif is the masthead voice; sans is the data voice.** Georgia-stack
  serif for the hero h1, section h2s, and subpage h1s (C10). Sans
  (`system-ui` first, C11) for names, numbers, labels, controls.
- **Maximum weight belongs to data.** Candidate names and percentages get
  the heaviest weight; labels and eyebrows sit at 600–700 and never shout
  over the data (C12).
- **Eyebrows/kickers** are uppercase, letterspaced, and context-colored:
  mint on navy, teal on paper (J44 — mint on cream is a contrast failure).
- **Reading measure ≠ page frame.** Every page renders the one 76rem
  `.page` frame; prose that wants a book measure constrains an inner
  ~46rem column (L53). The frame is the site; the measure is the content.

## Page vs. modal

- **Modal**: a drill-down into the context you are already in — evidence
  for the thing under your cursor. Ephemeral state, hash-addressable,
  Escape returns you exactly where you were. Canonical: the race-detail
  dialog.
- **Page**: a task with its own state and consequences, or standalone
  content people should land on from a link. Gets its own URL, `<title>`,
  nav presence, and footer. Canonical: Sources (a form), About, archive.
- Test: if it needs its own `<title>` or someone would bookmark it, it's a
  page. If it's "show me the receipts for this row," it's a modal.

## Text vs. icons

An icon may stand alone only when at least one holds (M71, M72):

1. The glyph is universal in context (× close, share arrow), or
2. A text path to the same destination exists on the same page (the footer
   ⓘ can be icon-only because the masthead links the About page in words).

Every icon-only control carries `aria-label` + `title` tooltip + visible
focus ring + adequate tap target (L55). The *primary* path to the
methodology is always words — trust links don't hide behind glyphs.

## Titles & naming

- **`<title>` grammar** (M60): election-scoped pages
  `"<page> — <election> — Seattle Elections Guide"`; the guide page itself
  `"<election> — Seattle Elections Guide"`; election-agnostic pages
  `"<page> — Seattle Elections Guide"`. Same values feed `og:title`.
- **One canonical election name per context** (M61): one display form
  (hero), one dated archive form — both generated, never hand-typed.
- **The brand lives in the band; the h1 describes the page** (A1, L54).
  Hero h1 = the election; Sources h1 = the task; About h1 = the promise.
- **Dates are for humans**: "August 4, 2026", never "2026-08-04" (A5).
  Kickers state the same fact at a different precision, not twice
  ("ELECTION DAY · AUGUST 4" above "August 2026 Primary", L54).

## Site shell

- One masthead band and one footer implementation on every page — never
  re-implemented per page (A3, L54, L55).
- The footer has exactly three jobs: exit ramps (icon cluster + How this
  works), provenance (the mono audit line), and closing the frame. Content
  that explains the guide belongs to About, not the footer (L55).
- **Sticky strips are one family** (M65, M68): a persistent surface that
  states current state *and carries its actions* — the guide's controls
  bar, the lens banner ("Counting 39 of 40 sources · Edit sources"), the
  Sources action bar. Same placement logic and same surface treatment on
  every page; two strips that do the same job must rhyme.

## Data display

- **Every quantity has exactly one value on screen** (the I56 invariant).
  Under a lens, every computed number — counts, shares, meters, kickers —
  shows the lens value; the audited baseline appears only as the explicitly
  labeled "All sources" reference line, never as an unmarked second number.
- **One meter.** Single chrome everywhere (I40), left-anchored fill
  matching the brand icon (D14a), label rides the fill with the low-fill
  fallback to muted ink (I41). The meter itself is under redesign (tabled
  D14) — extend it nowhere until that lands.
- **Alternative signals share one quiet component.** Anything that is an
  *alternative* to the result the reader asked for — the full-panel
  baseline under a lens, the Times comparison — renders as the same
  tone-tinted info bar, never as pills or badges (G24, G25). Reference
  bars sit together at the card foot, never interleaved with the primary
  data (I39).
- **Data-ink discipline.** Page-level state never repeats on every card
  (H38); zero-counts are suppressed rather than printed forty times (H35);
  taxonomy renders as plain muted text, not chrome (H36); rows in a grid
  align so a row of meters can be swept in one eye movement (I42).
- **Absence of a majority is information** (M63): leading share ≤ 50% gets
  the "No majority" treatment in the differ/amber family — confidence is
  never overstated by default styling.

## Accessibility

Woven through the above, stated once: tone is never the only carrier
(G27); visible text and aria text agree (H32); one `--focus` ring token on
every interactive element (B8); sr-only status strings read as sentences,
with real separators (K52); every page keeps the skip link.

## Non-goals & tabled

This doc does not govern: the **print/PDF editions** (own compact idiom,
aligned on tokens via J46 but with independent layout rules); the
**Compare pages** (mid-design, #116–#123); **dark mode** (none exists;
adding one is a project, not a patch). Explicitly tabled: the **D14 meter
redesign** — the current meter is maintained but not extended.

## Changing this doc

Same protocol as the polish ledgers: amendments are dated `DECIDED`
entries, made in the PR that ships the change or in a review round.
A polish round isn't done until any new *rationale* it produced is
promoted here. Precedence while a round is in flight: the newest dated
ledger decision wins over this doc; promotion reconciles them.
