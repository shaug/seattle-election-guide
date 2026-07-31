# UI Polish — Round 5 candidates (2026-07-30, not yet approved)

Running list from a live-site review of https://seattleelections.guide/ after
rounds 1–4 (#115, #128) shipped. Everything here was checked against the
approved/tabled ledger in `UI_POLISH.md` and the open ticket queue (#116–#124
Compare epic, #136 race URLs/OG images, #140 confidence-flag UX, #65
sensitivity report); nothing below re-opens a decided item or overlaps an
open ticket. Numbering continues the ledger (last used: I56).

## Bugs

- **M57 — Race-dialog leading-choice header collapses at phone widths.**
  At ≤ ~420px (seen at 375px, Chromium) the dialog's candidate heading
  breaks down: the candidate name renders vertically (one character per
  line), the "LEADING CHOICE" kicker overlaps the "12 of 18 endorsing
  sources…" line, and the meter is clipped at the dialog's right edge.
  Root cause in `guide.css`: `.race-detail-candidate-metrics` is
  `flex: 0 0 auto` with a `white-space: nowrap` count span, so the metrics
  block can never shrink below its content width; the 720px media query adds
  `flex-wrap` to the *metrics* block but the *heading* row never wraps, so
  `.race-detail-candidate-title` (min-width: 0) absorbs the entire deficit
  and collapses to ~1ch. The f2fa349 mobile-Safari fix addressed the name's
  own wrapping, not this flex starvation. Fix: let the heading wrap
  (`flex-wrap: wrap` on `.race-detail-candidate-heading`) or let metrics
  shrink (`flex: 0 1 auto; min-width: 0` + `white-space: normal` on the span
  at mobile widths).

- **M58 — Full-view race cards starve candidate names on phones.**
  `.screen-race-result` keeps a two-column grid (`minmax(0,1fr) 8.75rem`) at
  every width, so at 375px the name column is ~150px: "Sharon Tomiko Santos /
  Kelabe Tewolde" becomes six lines of one word each; even "Pramila Jayapal"
  wraps. Compact view already stacks name over a full-width meter and reads
  fine. Candidate fix: below ~480px, stack the full-view result block the
  same way (name, then meter). Complements F23 (which covered compact mode
  only).

- **M59 — The footer floats mid-screen on short pages.** On the archive page
  and on the guide when a narrow lens/filter leaves 1–3 cards, the `.page`
  frame ends right after the footer and the bare html background (#edf1f4)
  fills the bottom half of the viewport — the site looks truncated. Fix in
  `base.css`: make the page frame a min-height:100vh flex column and push
  `.site-footer` to the end (margin-top: auto), so the paper always reaches
  the footer and the footer always reaches the bottom.

## Cross-page consistency

- **M60 — One `<title>` structure site-wide, election-aware.** APPROVED
  2026-07-30. The tab reads bare "Seattle Elections Guide" on the guide page
  while Sources says "Sources — 2026 Washington August Primary — Seattle
  Elections Guide". Define one title template with two forms and apply it
  everywhere: election-scoped pages get
  "<page> — <election> — Seattle Elections Guide" (guide page: just
  "<election> — Seattle Elections Guide"), election-agnostic pages (About,
  archive, 404) get "<page> — Seattle Elections Guide". Same rule feeds
  `og:title`/`twitter:title`. Distinct from #136 (per-*race* URLs/OG
  images).

- **M61 — One canonical human election name.** Three renderings coexist:
  hero "August 2026 Primary", Sources title "2026 Washington August
  Primary", archive link "August 4, 2026 Washington primary". Pick one
  formatting rule per context (display name vs dated archive name) and
  generate all of them from it. Spirit of A5/A1.

- **M62 — "Show races" vs "Races" label collision in the filter bar.**
  DECIDED 2026-07-30: rename the scope select's label to "Ballot"; the
  All|Contested toggle keeps "Races". (Background: two adjacent controls
  were both named "races", and the select mixes ballot sections and
  districts in one optgroup'd list — "Ballot" names the question it
  answers.)

## Data display

- **M63 — Cards don't say a race is tied / lacks a majority.** DECIDED
  DIRECTION 2026-07-30: adopt electioncheatsheet.org's "No majority"
  verbiage and amber distinction in some fashion. (Background: a tied race
  renders as "Sharon Tomiko Santos / Kelabe Tewolde" with a single 50%
  meter — the slash + 50% reads like a joint candidacy; only the dialog
  explains "Tied for lead".) Reference treatment: their race card swaps the
  recommendation for a cream-amber "No majority" pill (bg #fef3d3, text
  #8a6a1a) and gives the agreement bar a yellow variant; their rule is "no
  candidate clears 50.01% ⇒ no majority pick". Ours maps cleanly: when the
  leading share is ≤ 50%, show a "No majority" pill on the card and render
  the meter fill in the existing amber tone family (--tone-differ-bg
  #fff6e8 / --tone-differ-text #8a4b00 / --amber — no new colors needed;
  amber already means "differs/attention" in the dialog and Times
  comparison). To settle at ticket time: (a) whether the meter keeps its %
  label in the amber state; (b) dialog kicker wording alignment ("Tied for
  lead" → "No majority · tied for lead" vs unchanged); (c) lens interaction
  — the pill must be lens-aware like every other computed value (I56
  invariant), since a personalized panel can create or dissolve a majority;
  (d) whether sub-50% single leaders (3-way splits, no tie) also get the
  pill — the rule says yes, verify the data has such races.

- **M64 — Meter end-cap crescent at high fills.** REJECTED 2026-07-30:
  looks fine as-is, and the meter component itself may be replaced by
  something more informationally dense later (see tabled D14). Do nothing.

- **M65 — The lens banner is inert.** "Counting 39 of 40 sources." announces
  the personalized state but offers no path from the announcement to acting
  on it (edit or reset); the reader must rediscover the Sources page in the
  nav. Candidate: inline "Edit sources" (and possibly "Reset") link inside
  the banner. Note (2026-07-30): design together with M68's sticky action
  bar on the Sources page — the two are one family of sticky
  state-plus-actions strips and should rhyme in placement and behavior.

## Sources page (added 2026-07-30)

- **M67 — The Sources page never names its election.** The page is
  election-scoped (`/e/wa-2026-primary/sources/`) but no on-page text says
  which election it configures — only the `<title>` knows. Add election
  context to the masthead area, less pronounced than the guide's hero: e.g.
  the eyebrow/kicker treatment ("AUGUST 2026 PRIMARY · SOURCES") above the
  "Customize your sources" H1. Pairs with M60/M61 (same canonical election
  name feeding all of them).

- **M68 — Make the Sources page feel like the form it is.** The
  Save | Cancel | Reset row sits above the fold before any of the content it
  acts on, and nothing repeats at the end of a two-column list that scrolls
  for several screens — the reader finishes checking boxes at the bottom
  with no way to commit without scrolling back. (Note: the three "buttons"
  are actually styled `<a>` links whose hrefs are updated by script — worth
  revisiting semantics while touching this.) DECIDED 2026-07-30: slim sticky
  action bar. Rationale: it rhymes with the guide page's sticky surfaces —
  the controls bar and especially the lens banner once M65 adds links to it.
  The two bars need not be identical, but placement and behavior should feel
  like the same family: a persistent strip that states the current state and
  carries the actions on it. Color: no strong preference, but DECIDED that
  whatever surface is chosen must be the same on both pages (guide lens
  banner and Sources action bar).

- **M69 — The Sources intro prose sits in an unconsidered measure.** On
  desktop the intro paragraph occupies a single narrow column at the far
  left of a wide page, above a two-column grid — it reads as an accident
  rather than a chosen reading measure. Full-width isn't the answer either
  (line length); design the header block deliberately, likely together with
  M67's masthead work.

- **M70 — Demote the URL-privacy sentence to the About FAQ.** "Your
  selection lives entirely in this page's address — nothing is stored
  anywhere else." is reassuring but not important enough for prime placement
  at the top of the form. Move it to About as an FAQ entry (e.g. "Are my
  choices anonymous?"); the Sources intro keeps only the one sentence of
  instruction.

## Chrome & icons (added 2026-07-30)

- **M71 — Footer "How this works" text link amid the icon row.** DECIDED
  2026-07-30: ⓘ icon button with tooltip, matching the other footer icons.
  Discoverability isn't lost because the masthead links the About page from
  the top of every page — the footer entry is a convenience repeat, not the
  primary path. DECIDED 2026-07-31: the masthead label is "How this works" so
  that primary path names what the page does; the page's own `<title>` remains
  "About" under the M60 template.

- **M72 — Race-dialog header actions as icons.** "Share link" and "Close"
  are text links in the dialog header. Replace with icon buttons: X for
  close (universal), and the same share glyph the footer already uses
  (consistency), each with an accessible label/tooltip. Mobile benefits
  most — the header currently stacks a kicker, a two-line title, and a
  full-width actions row.

## Minor

- **M66 — Sources-page coda lines feel appended.** The two full-width lines
  under the coverage-gaps grid ("Every checked source counts once…" and
  "Panel v4 · … · Data …") hang below the two-column layout without
  belonging to either column. Candidate: fold the counting rule into the
  coverage-gaps left column (it's methodology, same voice) and let the
  panel/data line join the footer audit line, which already carries the same
  identifiers.
