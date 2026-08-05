# Meter v2 — the segmented meter

Design ratified August 4, 2026. This document records the full design and the reasoning behind
each decision so that implementation tickets and future tweaks have one place to resolve
ambiguity. The canonical reference rendering — built from real `wa-2026-primary` data — lives at
`docs/design/METER_V2_2026-08-04.html`; open it in a browser, hover the meters, and click the
candidate chips. Where that mockup and this prose disagree, the mockup is the spec.

Status: implemented on the guide card, the compact ballot, print, and the race headline (#314,
2026-08-04) — `docs/DESIGN.md`'s "One meter" rules now describe this document's design rather
than the retired v1 pill. Two surfaces remain: the race page's candidate-context treatment
(#315) and the social card (#316, `rendering/og_image.py`, still drawing the v1 pill until it
lands).

Ratified August 4, 2026; the same day an adversarial review pass (four independent read-only
reviewers) corrected the factual claims below and added the Edge states section — those
edge-state rules are part of the ratified design.

## Why v1 had to grow

The v1 meter is a single pill: the leader's share as a left-anchored fill, a percentage riding
it. Two strengths made it work and are preserved wholesale:

- **Constant width.** Within any column of cards every meter is the same size (each chrome —
  card, compact ballot, print, race page — has its own fixed footprint), so a column can be
  swept in one eye movement and compared by fill alone.
- **Color and fill-length carry strength.** Teal past half means a majority; amber means no
  majority; longer means stronger.

Five weaknesses motivated the redesign:

- The percentage is redundant — it restates the fill without adding information.
- The meter shows nothing about the rest of the field.
- Below 30 percent the white label bleeds onto the pale track, so a low-fill guard moves it
  outside the fill in muted ink — the label and the fill are fighting for the same pixels.
- Split endorsements are counted fractionally in the arithmetic, but the visible caption prints
  an integer count hedged with "(co-endorsements split)" — the half exists, is never shown, and
  is never explained.
- The meter is not inspectable: it summarizes evidence the reader cannot reach from it.

## The design in one paragraph

The meter is a constant-width bar of equal-width rectangular blocks, **one block per
endorsement**, grouped into runs by candidate in standings order — leader first. A split
endorsement is one block divided horizontally, the two candidates' colors stacked, placed at the
boundary between their runs. At rest on a pointer device the seams between blocks are invisible
and a left-aligned percentage rides the leader's fill, so the meter reads almost exactly like
v1; hovering (or keyboard focus) fades the percentage out and fades hairline seams and
per-block tooltips in, resolving the bar into individual voices. On touch there is no
percentage and the seams are always visible; tapping a block shows its tooltip. At first
inspection the only visible change from v1 is softer corners — inspection begets discovery.

## Anatomy and geometry

| Element | Spec |
| --- | --- |
| Frame | 2rem tall, 1px `--line-strong` border, `.4rem` corner radius, `--meter-track` ground |
| Block | width = track ÷ endorsement count; identical rectangles, no per-block rounding |
| Run | a candidate's blocks, contiguous, in standings order (ties broken by display label) |
| Split block | one block, halved horizontally: higher-ranked candidate on top |
| Seam | 1px between blocks; 1px between split halves |
| Tongue tip radius | `.25rem`, interior corner only (see below) |
| Percentage layer | left-aligned on the fill, v1 typography (bold, tabular-nums); white on teal, navy on amber |

## The discovery model

| Surface | At rest | On engagement |
| --- | --- | --- |
| Pointer devices | Solid stacked fill + percentage; no seams | Hover or focus: percentage fades out; seams and per-block tooltips fade in |
| Keyboard | Same resting state; the meter is one tab stop | Focusing the meter reveals the seams |
| Touch | No percentage; seams always visible | Tap a block for the same tooltip |
| Print | Percentage *and* seams, both static | — |

A block's tooltip contains exactly two lines: the source's display name, and the decision
("Endorsed Jamie Pedersen"; "Split: Hawk + Diaz — ½ each"). Source category is deliberately
omitted — it is race-page information, and including it would require new lens-payload
plumbing.

Reasoning: the meter is a sizzle feature — the displayed name is the steak, and what most
readers decide on. The meter is the first confidence dive, the race page the second. The
resting state deliberately preserves v1's aesthetic weight (a returning reader sees nothing to
relearn), and every additional layer of information is earned by curiosity. On touch, where
there is no hover to discover, the voices are simply always present, and the percentage — a
summary derivable from the count — yields entirely to the core information.

Accessibility model: the meter is a single `role="img"` element carrying the full standings as
its accessible name, and it is the meter's **one** tab stop — focusing it reveals the seams
(`:focus-within`), same as hover. Blocks are presentational: they are not focusable and carry
no ARIA of their own (descendants of `role="img"` are pruned by assistive technology, so
per-block labels there would be both invalid and inert). The tooltip is **not** a live region.
Per-source evidence remains keyboard-reachable where it already lives — the race page's source
lists — so no information is hover-only. Reveal transitions are short fades (~150 ms); under
`prefers-reduced-motion` they become instant. Tooltips must satisfy WCAG 1.4.13 in
implementation (dismissible via Escape, content hoverable, tap-away to close on touch);
`hover: none` is the touch signal, which means hybrid touch-laptops get the pointer treatment.

## Color

Exactly three color commitments carry meaning; no other hue does:

| Meaning | Color |
| --- | --- |
| Majority leader | The site's own teal `#087f73` (`base.css --teal`) — the same fill v1 uses |
| Tied leaders | Variations of amber: `#d99000` (`base.css --amber`) and `#8a5d12` (`--meter-tie-deep`) |
| Sole leader without a majority | Amber `#d99000` — v1's no-majority semantic, unchanged |
| Selected candidate (race-page context) | The candidate's color, bold — `saturate(1.5) brightness(.9)` in the mockup; other blocks recede to 30% opacity and the resting percent hides |
| Trailing candidates | The muted set, by rank: slate `#7d95ad` (`--meter-trail-slate`), taupe `#a99e8a` (`--meter-trail-taupe`), plum `#a08296` (`--meter-trail-plum`) |

When a pool runs out — a fourth trailing candidate, a third tied leader — subsequent candidates
continue the last hue stepped progressively toward the track color, so two candidates in one
meter never share a swatch. Every color above enters `base.css` as a named token at
implementation time; `docs/DESIGN.md`'s rule that page CSS never introduces a color literal
applies to the meter like everything else. The tokens landed in #312 under the `--meter-`
family the track already began (`--meter-track`), spelled above and in § Seams: hue names for
the trailing set because the doc, not the stylesheet, owns the rank order. The majority and
no-majority fills are `--teal` and `--amber` themselves — no meter aliases — so a surface
that recolors one recolors the site's own semantic.

Reasoning. The teal was retained deliberately over a slightly greener, more chromatic candidate
that scored better on palette-validation checks: color continuity with the icon, the social
cards, and the shipped meter outweighs chart-theoretic purity, and the meter must keep feeling
like the same trusted object. Trailing candidates are muted because they should be
*distinguishable yet obviously less relevant* — the meter's answer to "who else?" is a texture,
not a rival headline. Strong trailing contrast was judged a nice-to-have, not a requirement:
color is never the sole information channel (per `docs/DESIGN.md`, states explain themselves in
words — here, the tooltips, chips, and captions), so colorblind readers lose polish, not
information.

## Counting and the denominator

- **One block per endorsement; a split counts 1/n to each named candidate** (the equal
  allocation the publication model already enforces on `multi_endorsement` cells — ½ for the
  common two-way split, and the model permits n ≥ 2).
- **Explicit "no endorsement" records carry no block and no denominator weight.** A source that
  looked and declined is the same non-signal to a voter as a source with no opinion. The site is
  about endorsement weight, not sources; fill-length keeps meaning *share of endorsements*,
  exactly as in v1.
- **The caption states the count, not the percent**: "21½ of 23 endorsements" — never the
  recommended choice's own name, which the card's headline already states one row up (Decision
  log #22, revised in #314's own review after the drafted "Nilu Jenks — 21½ of 23 endorsements"
  form shipped a name that repeated the headline on every card). The
  count is the more honest statistic — the fractional half is now *visible* as a divided block
  — and the percent is derivable from it. The percent survives only as the resting summary on
  the meter itself. Caption fractions are exact rationals rendered as vulgar-fraction glyphs
  (½, ⅓, ¼, …), formatted by a mirrored Python/JS pair registered in `tests/mirrors.json` like
  every other display string — never by float arithmetic (the mockup's formatter is
  illustrative only). The pair landed in #312 as `endorsement_count_label`
  (`rendering/context.py`) and `endorsementCountLabel` (`guide-format.mjs`). A fractional
  part with no single glyph — reachable the moment splits compound past Unicode's set, a
  quarter plus a third being 7/12 — renders as numerator⁄denominator with the U+2044
  fraction slash, joined to a nonzero whole part by a no-break space: "2 1⁄12". The resting
  percent reuses the existing `percentageLabel` mirror (exact half-up on a `Fraction`), not a
  new rounding.
- Block width therefore varies from race to race (constant track, varying endorsement counts).
  Decided and accepted: the meter helps a voter decide *within* a race, and meter-to-meter
  share comparability matters more than making one endorsement the same width everywhere.

## Splits: placement and the tongue rule

A split block sits at the boundary between its two candidates' runs; consecutive splits form a
band. Each half-run in a band is a **tongue** — the leader's top halves reach rightward into
the partner's run, the partner's bottom halves reach leftward into the leader's. A split
between non-adjacent candidates (a third candidate's run intervenes) renders as one divided
block at the end of the higher-ranked candidate's run, ordered so the split whose partner is
nearest sits closest to the next run. A split naming n > 2 candidates renders as n stacked
bands in one block, top-to-bottom in standings order, and its tooltip says "1/n each."

Canonical block order: within a run, solid blocks sort by source display label ascending, then
splits by partner distance as above. Both renderers (server template and client re-render) must
sort by the same rule — the markup-parity tests require identical output, and the server and
lens payloads deliver cells in different orders.

Two consequences of boundary placement are accepted, not accidental: a candidate whose entire
support is split halves has no run of their own — their weight appears as bottom halves inside
their partners' runs, with the chips and caption carrying their identity — and a candidate with
zero endorsements has no block at all, exactly as they have no weight in today's tally.
Band-edge detection (which block is a band's first or last) must be run-aware in the
implementation; the mockup's neighbor-type heuristic is sufficient only for two-run bands.

The whole of this section — the standings order, the run grouping, the split placement, the
canonical order, and the band and tongue-corner flags — landed in #313 as the mirrored pair
`meter_layout_blocks` (`rendering/context.py`) and `meterLayoutBlocks` (`meter-layout.mjs`),
registered in `tests/mirrors.json` like every other. It returns an ordered block list — block
type, width in units, candidate ids, band and tongue flags — that both renderers consume
verbatim rather than each deriving from its neighbors. Ahead of the surfaces, as the counting
pair was, so nothing draws a block from it yet.

Placement optimizes **visual continuity, not pixel precision**: a divided block occupies a full
block width while counting ½ to each side, so a run's pixel length may overstate its tally by
half a block per split. Accepted; at realistic block counts the discrepancy is invisible, and
the caption carries the exact number.

Corner rule: **a curve appears only where two candidates' colors meet.** Each tongue tip rounds
its single interior corner (`.25rem`) — bottom-right for a top tongue, top-left for a bottom
tongue — and the exposed notch shows the color the tongue rests on. Corners touching the
meter's own top or bottom edge stay square; a tongue ending at the meter's outer edge stays
square entirely. The frame's `.4rem` is the only other curve, and it marks the meter's
boundary. Block rounding says "another candidate continues here"; frame rounding says "the
meter ends here"; the two never overlap.

## Seams

Seams are hairline (1px), **darker than the fill**, and minimally contrasting — a step off the
fill, not a line on it:

- Between blocks of the **same candidate**: the fill mixed 88% with a dark ink pole
  (`#1a2530`, `base.css --meter-seam-pole`).
- Between blocks of **different candidates**, and between the halves of a split block: the
  50/50 blend of the two facing colors, mixed 86% with the same pole. The hue change itself is
  the separator, so the seam never has to shout.
- At rest (pointer devices) seams are invisible by construction: a solid block's border shows
  its own fill; a split block's resting border paints its own half colors, except a band's
  first block, whose border rests on the leader's solid color so the straight border never
  fragments against the rounded tongue corner.

Reasoning: lighter-than-fill grout made the blocks read as tiles sitting on the page; the
darker seam reads as one scored slab — a lightly segmented whole representing many individual
voices coming together, which is the meter's thesis.

The seam *colors* are normative; the mockup's mechanism (`border-image` gradients,
`color-mix()`) is not — any technique producing a 1px seam of the specified mixes satisfies
the spec.

## Edge states

All ratified with the rest of the design (added in the August 4 review pass):

- **N/A (null share).** Zero endorsements — or a personalized lens that leaves a race unscored,
  which is reachable in the browser today — renders the empty track with v1's muted "N/A"
  label, no blocks, no seams, and the accessible name "No endorsements recorded". The
  `meter-unavailable-label` mirror keeps its literal.
- **Insufficient grade.** The meter renders normally — unchanged from v1's policy, where an
  Insufficient race already shows a full fill. A single-endorsement race is one full-width teal
  block; the grade label ("Too few endorsements") and the caption ("1 of 1 endorsements") carry
  the insufficiency. The count-based caption makes this *more* honest than v1's anonymous 100%.
- **Minimum block width.** When a chrome's width divided by the endorsement count drops below
  ~3px per block, per-block seams are dropped and the meter degrades to plain candidate runs
  (boundaries and split bands only). Countability yields before legibility does.
- **Chrome geometry.** v2 inherits each chrome's existing footprint: card 11rem × 2rem
  (8.75rem under 720px), compact ballot 100% × 1.6rem, print 7.5rem × 1.2rem, race headline
  full-width. Print renders the static percent-plus-seams state. The race page's leader-only
  mini-meter (v1's "per-candidate meter") **retires**: the candidate-context treatment on the
  shared bar — selected candidate bold, everything else receding — replaces it.

## Implementation notes (pointers, not bindings)

- This is a **replace-in-place** on the shared meter chrome, preserving the one-definition rule
  `guide-card.mjs` documents. The movers: `meterView` and its JS consumers (`guide-lens.mjs`,
  `race-client.mjs`, `race-detail.mjs`), the audited Jinja twins (`guide.html.j2`,
  `race.html.j2` — each hard-codes the low-fill threshold), the chrome CSS (`guide-race.css`,
  `race.css`, `guide.css` compact/print rules), **and `rendering/og_image.py`**, which draws
  the same meter in Python for race social cards with its own copy of the fill, colors, and
  low-fill threshold. It cannot be split into add-then-retire — the shared-presentation carving
  constraint proven during the #136 race-page work (landed via #305–#308).
- Sequencing: unblocked. The front-end architecture epic (#232) closed with #245; esbuild and
  lit-html are already in place.
- The v1 low-fill guard's job shrinks to the desktop resting label (the percent must still
  survive a short leader run); touch drops the label and hover removes it.
- The rendered-HTML validator, `tests/mirrors.json` entries, and page-parity fixtures that
  reference meter markup and `percentage_label` must move in the same change; the new caption
  formatter registers as a mirror pair.
- No new pipeline data is needed: `source_cells` already carry candidate ids and exact
  allocations, no-endorsement rows are already named in the rendering context, and
  comparison-role sources never render a block at all.
- **Caption matrix, ruled in #314, revised in #314's own review** (Decision log #22): the
  meter's own caption — I39's caption block, `screen_support_summary`/`supportSummary` and their
  compact siblings — is redefined to state the recommended choice's own exact count against the
  same denominator the sentence already used, rather than only the denominator: "21½ of 23
  endorsements" audited, "21½ of 19 selected sources" personalized (H38's denominator is
  unchanged — the reader's current selection total, not this race's own — only the numerator is
  new). The name originally drafted into this ruling — "Nilu Jenks — 21½ of 23 endorsements" —
  was cut in review: every card the caption renders on already carries that name one row up, in
  the card's own headline, so stating it again in the caption directly beneath was pure
  restatement, confirmed by screenshots of real cards (LD-32 State Senator, LD-34 Position 1,
  LD-34 Position 2, LD-34 State Senator, LD-36 Position 1, LD-36 Position 2) where the same name
  appeared twice in one card, headline and caption. Both the full and compact forms now state
  only the count — the compact form dropped the name from the start (the card's own heading
  already carries it), and the full form now matches it exactly except for the fallback
  sentence's own wording. A tie or a race with no single recommended choice has no one count to
  lead with, so both forms fall back to the caption's pre-v2 wording, which states only the
  denominator — the same fallback `race_detail_support_summary`/`raceDetailSupportSummary`
  already used for the identical reason. That function, and the accessible-summary sentence it
  composes into (`race_detail_accessible_summary`), are unchanged and out of this ruling's scope:
  they narrate the race page's visually-hidden description, which has no adjacent headline to
  lean on, not the meter's caption, and keep their own "N of M endorsing sources agree"
  phrasing. The meter's *accessible name* — a separate string, the `role="img"` element's own —
  is not a caption at all: it states the full standings (§ The discovery model's accessibility
  model), replacing v1's `screen_share_accessible_label`/`shareAccessibleLabel`, which #314
  deleted.

## The platform

Meter v2 is a visual platform, not a one-off: the primitive is *a block is an endorsement*, and
planned features extend it without redesign. Source weighting becomes variable block widths.
Post-election annotation (docs/RESULTS.md) can mark blocks or runs in place. The social cards
already draw the meter (in Python — see the consumer list above) and adopt the resting state
with the implementation; the Comparisons page can render the same bar at any size because the
resting state is a plain stacked fill. The site icon keeps the v1 pill: the pill remains the
symbol; meter v2 is what the symbol opens into.

## Decision log

All ratified August 4, 2026.

| # | Decision | Ruling |
| --- | --- | --- |
| 1 | Block structure | One equal-width block per endorsement; grouped by candidate; constant-width bar |
| 2 | Split rendering | Stacked top/bottom halves in one block, at the run boundary |
| 3 | Denominator | Endorsements only; explicit "no endorsement" carries no weight |
| 4 | Block width across races | Varies; per-meter comparability beats per-block weight |
| 5 | Split placement | Visual continuity over pixel precision |
| 6 | Caption | Count ("21½ of 23 endorsements"), not percent |
| 7 | Block shape | Identical rectangles; no rounded block ends |
| 8 | Frame | `.4rem` corner radius — a nod to the pill, nothing more |
| 9 | Majority color | The site's own teal `#087f73`, unchanged from v1 |
| 10 | Tie / no-majority | Amber variations / amber — v1's semantic, unchanged |
| 11 | Trailing colors | Muted slate/taupe/plum; recessive by intent |
| 12 | Selected candidate | Bold; everything else recedes |
| 13 | Seams | 1px hairline, darker than fill, minimal contrast; invisible at rest on pointer devices |
| 14 | Reveal | Hover/focus trades the percent for seams and tooltips; touch always shows seams, never the percent |
| 15 | Tongue tips | `.25rem` on the single interior corner; square at every meter edge |
| 16 | N/A state | Empty track, muted "N/A", no blocks — v1's semantic |
| 17 | Insufficient grade | Meter renders; the grade label and count caption carry the insufficiency |
| 18 | Color-pool exhaustion | Overflow candidates step toward the track; never a shared swatch |
| 19 | Minimum block width | Below ~3px per block, degrade to plain candidate runs |
| 20 | Per-candidate mini-meter | Retired; the candidate-context treatment on the shared bar replaces it |
| 21 | n-way splits | n stacked bands in one block, standings order, "1/n each" |
| 22 | Caption matrix | The recommended choice's own count replaces the bare denominator, audited and personalized alike, but never the choice's own name — the card's headline already states it, so the caption states only the count; a tie or no single choice falls back to the pre-v2 sentence; the accessible name is a separate, unrelated string (the full standings) |
