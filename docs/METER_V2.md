# Meter v2 — the segmented meter

Design ratified August 4, 2026. This document records the full design and the reasoning behind
each decision so that implementation tickets and future tweaks have one place to resolve
ambiguity. The canonical reference rendering — built from real `wa-2026-primary` data — lives at
`docs/design/METER_V2_2026-08-04.html`; open it in a browser, hover the meters, and click the
candidate chips. Where that mockup and this prose disagree, the mockup is the spec.

Status: designed, not implemented. Until the implementation lands, `docs/DESIGN.md`'s "One
meter" rules describe the shipped v1 pill; this document describes what replaces it.

## Why v1 had to grow

The v1 meter is a single pill: the leader's share as a left-anchored fill, a percentage riding
it. Two strengths made it work and are preserved wholesale:

- **Constant width.** Every meter is the same size, so a column of them can be swept in one eye
  movement and compared by fill alone.
- **Color and fill-length carry strength.** Teal past half means a majority; amber means no
  majority; longer means stronger.

Five weaknesses motivated the redesign:

- The percentage is redundant — it restates the fill without adding information.
- The meter shows nothing about the rest of the field.
- Below 50 percent, the fill-plus-label layout degrades (the low-fill guard exists because of
  this).
- Split endorsements are counted fractionally ("16½ of 19") but nothing in the meter explains
  where a half comes from.
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
| Pointer devices | Solid stacked fill + percentage; no seams | Hover or `:focus-within`: percentage fades out; seams and per-block tooltips fade in |
| Touch | No percentage; seams always visible | Tap a block for the same tooltip |

Reasoning: the meter is a sizzle feature — the displayed name is the steak, and what most
readers decide on. The meter is the first confidence dive, the race page the second. The
resting state deliberately preserves v1's aesthetic weight (a returning reader sees nothing to
relearn), and every additional layer of information is earned by curiosity. On touch, where
there is no hover to discover, the voices are simply always present, and the percentage — a
summary derivable from the count — yields entirely to the core information.

Each block is focusable and carries an aria-label naming its source and decision; the meter
itself is `role="img"` with the full standings as its label, so the screen-reader summary never
depends on the visual layers.

## Color

Exactly three color commitments carry meaning; no other hue does:

| Meaning | Color |
| --- | --- |
| Majority leader | The site's own teal `#087f73` — the same fill v1 uses |
| Tied leaders | Variations of amber: `#d19000` and `#8a5d12` |
| Sole leader without a majority | Amber `#d19000` — v1's no-majority semantic, unchanged |
| Selected candidate (race-page context) | The candidate's color, bold (saturated, slightly deepened); other blocks recede |
| Trailing candidates | The muted set, by rank: slate `#7d95ad`, taupe `#a99e8a`, plum `#a08296` |

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

- **One block per endorsement; splits count ½ to each named candidate** (the equal allocation
  the publication model already enforces on `multi_endorsement` cells).
- **Explicit "no endorsement" records carry no block and no denominator weight.** A source that
  looked and declined is the same non-signal to a voter as a source with no opinion. The site is
  about endorsement weight, not sources; fill-length keeps meaning *share of endorsements*,
  exactly as in v1.
- **The caption states the count, not the percent**: "Nilu Jenks — 21½ of 23 endorsements". The
  count is the more honest statistic — the fractional half is now *visible* as a divided block
  — and the percent is derivable from it. The percent survives only as the resting summary on
  the meter itself.
- Block width therefore varies from race to race (constant track, varying endorsement counts).
  Decided and accepted: the meter helps a voter decide *within* a race, and meter-to-meter
  share comparability matters more than making one endorsement the same width everywhere.

## Splits: placement and the tongue rule

A split block sits at the boundary between its two candidates' runs; consecutive splits form a
band. Each half-run in a band is a **tongue** — the leader's top halves reach rightward into
the partner's run, the partner's bottom halves reach leftward into the leader's. A split
between non-adjacent candidates (a third candidate's run intervenes) renders as one divided
block at the end of the higher-ranked candidate's run.

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
  (`#1a2530`).
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

## Implementation notes (pointers, not bindings)

- This is a **replace-in-place** on the shared meter chrome: `meterView` in
  `src/election_guide/rendering/templates/guide-card.mjs` and every consumer (guide card, race
  headline, per-candidate meters) move together, preserving the one-definition rule the module
  documents. It cannot be split into add-then-retire (see the carving history on #136).
- Sequencing: after the front-end architecture work (epic #232 — the esbuild bundler and
  lit-html land first), since the meter gains real interactivity.
- The v1 low-fill guard's job shrinks to the desktop resting label; touch drops the label and
  hover removes it.
- The rendered-HTML validator, `tests/mirrors.json` entries, and page-parity fixtures that
  reference meter markup and `percentage_label` must move in the same change.
- No new pipeline data is needed: `source_cells` already carry candidate ids and exact
  allocations, and the excluded groups (comparison-role sources, no-endorsement records)
  already have names in the rendering context.

## The platform

Meter v2 is a visual platform, not a one-off: the primitive is *a block is an endorsement*, and
planned features extend it without redesign. Source weighting becomes variable block widths.
Post-election annotation (docs/RESULTS.md) can mark blocks or runs in place. The Comparisons
page and social cards can render the same bar at any size because the resting state is a plain
stacked fill. The site icon keeps the v1 pill: the pill remains the symbol; meter v2 is what
the symbol opens into.

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
