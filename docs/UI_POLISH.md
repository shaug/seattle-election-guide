# UI Polish — Approved Cleanup List

Running list of UI/consistency cleanup approved by Scott (2026-07-29 design review).
No architectural or navigation-structure changes beyond what is explicitly listed.
Item IDs match the original review discussion.

## Approved

### A. Site cohesion
- **A1 — One site name everywhere: "Seattle Elections Guide".**
  Headers, `<title>` tags, archive page, About page all currently disagree
  ("Seattle Progressive Elections Guide" / "Seattle Elections Guide" /
  "Seattle election guide"). DECIDED: the guide hero `h1` becomes the brand
  name "Seattle Elections Guide"; the progressive framing moves to the
  tagline (see E20).
- **A2 — Style the `/e/` archive page.** Currently completely unstyled
  (`_archive_html` in `src/election_guide/hosting/pages.py`). Give it the same
  page shell (navy header band, tokens, footer) as About/Sources.
- **A3 — Shared page shell + common nav.** Biggest issue: the guide, Sources,
  and About re-implement the header band/footer/h1 with drift. Consolidate into
  one shared "page shell" style block, and add a light common nav
  (e.g. "Endorsements | Sources | About") in the header or footer of every page
  so the site reads as one site. Sources nav link must be election-scoped
  (`/e/<id>/sources/`).
- **A4 — Favicon + site icon + `og:image`.** DECIDED: concept 1, "The Meter" —
  navy rounded tile, paper pill track, left-anchored teal fill (~72%).
  Reference SVG (64×64 viewBox):
  `<rect width="64" height="64" rx="14" fill="#102a43"/>`
  `<rect x="10" y="25" width="44" height="14" rx="7" fill="#fbfaf6"/>`
  `<rect x="10" y="25" width="31" height="14" rx="7" fill="#087f73"/>`
  Inverted variant for navy header band: teal tile, navy track, mint fill.
  Ship as SVG favicon + PNG fallback + apple-touch-icon; add `og:image`.
- **A5 — Human date formats.** Replace machine dates like "Election 2026-08-04"
  (hero meta, footers) with "August 4, 2026". The "AUGUST 2026 PRIMARY" kicker
  is a label, not a date — it stays.

### B. Color / token discipline
- **B6 — Single accent decision.** Teal (`--teal`) is the brand/data accent
  (hero rule, meters, category borders, race-card top border — currently blue);
  `--blue` reserved for hyperlinks only (unify with the base `a` color, which is
  currently a third blue `#075d75`).
- **B7 — Collapse the six near-identical muted greys**
  (`#52606d #53636d #46596a #44596a #364152 #667784`) to two tokens
  (e.g. `--muted`, `--faint`).
- **B8 — Tokenize the focus ring.** `#f0a928` is hardcoded 6+ times and doesn't
  match `--amber` (`#d99000`). One `--focus` token.
- **B9 — Promote recurring color literals to `base.css` variables**
  (`#829ab1`, `#9ee7df`, `#d7e6ef`, `#176554`, `#8a4b00`, …). No visual change;
  prevents future drift and underpins A2/A3.

### C. Typography
- **C10 — One heading voice.** DECIDED: serif masthead. The hero h1 (and any
  page-shell brand h1s) adopt the Georgia serif treatment already used by
  section h2s and subpage h1s. Sans remains the voice for data and labels.
- **C11 — Font stack portability.** Add `system-ui` ahead of the
  Avenir Next/Helvetica fallbacks so non-Apple platforms keep the designed feel.
- **C12 — De-shout the labels.** Reduce the pervasive 800-weight
  uppercase/letter-spaced small labels to 600–700; reserve maximum weight for
  data (names, percentages).
- **C13 — Drop the repeated "BALLOT SECTION" eyebrow** above every section
  heading (redundant ink).

### D. Data display
- **D14a — Standardize meter fill direction (added round 2).** One direction
  everywhere: **left-anchored fill** (matches the brand icon), label riding the
  fill. Applies to the full-view screen meter, compact meter, lens meter,
  race-detail meters, and print meters. (The grander meter redesign remains
  tabled — see D14 below; this is direction-only.)
- **D15 — Quieter meter chrome.** Thinner border, drop the inset shadow; the
  fill is the message.
- **D16 — Trim the filter status line.** Keep the race count; drop the visible
  "· Full · All Seattle ballot races" echo of adjacent control state (may remain
  in the aria-live text).
- **D17 — Fix "Viewing N of M sources" verbiage.** "Viewing" is wrong — sources
  are *counted toward* computed results, not viewed. Rework the Sources page
  wording (candidate: "Counting N of M sources."). The guide-footer instance is
  gone entirely — its whole section is removed per G28.
- **D18 — Footer audit line cleanup.** Truncate the guide footer's 64-char
  panel hash to 12 chars (match Sources page). Rewrite the Sources-page footer
  prose: separate the audit identifiers (compact, mono) from a plain-English
  method note about equal weighting and split endorsements.

### E. Microcopy
- **E19 — Pluralization bug:** "1 endorsements · 0 split" in the
  `source_participation` macro (guide + sources templates).
- **E20 — Proper tagline for the hero deck.** DECIDED:
  **"Seattle's progressive voices, distilled."**
  The old comparison-source caveat moves out of the deck (it already lives on
  the Sources page and in About). This also carries the "progressive" framing
  so the h1 can be the plain brand name (A1). Superseded 2026-07-31: the factual
  subline is removed; the always-present sources strip owns the live count.
- **E21 — "Feedback?" → "Contact"** in the guide footer (and align About's
  mailto label).

### F. Interaction polish
- **F22 — Sticky controls bar surface.** Make it opaque `--paper` (plus a
  hairline shadow when stuck) instead of translucent white over cream.
- **F23 — Compact mode on phones:** two narrow columns instead of collapsing to
  one (currently indistinguishable from Full on mobile).

### G. Lens & comparison display (added round 2, 2026-07-29)
Context: with a source subset active ("My sources") plus the Times comparison
enabled, a race card shows two reference signals in two clashing components —
the Times as a loud pill badge, the full-panel consensus as a quiet info bar.
- **G24 — One component for all alternative-endorsement signals.** Principle:
  anything that is an *alternative* to the result the reader asked for — a
  different calculation (e.g. the "All sources" line while a lens is active)
  or a direct comparison source that never factors into the calculation (the
  Times, which is opt-in, never default) — renders as the same quiet info-bar
  component. The pill badge is retired in every context it appears. Agree/
  differ tone coloring (green `#176554` family / amber `#8a4b00` family /
  neutral grey for not-covered) carries over as the left border + tint; tones
  become tokens per B9. Print PDF keeps its own compact pick treatment.
- **G25 — Tone the consensus line too.** The full-panel consensus info bar
  gets the same agree/differ coloring, encoding whether the reader's selection
  reaches the same leading choice as the full panel (agree = same leader,
  share may differ and is still shown).
- **G26 — Rename "Audited consensus" → "All sources".** DECIDED. The
  full-panel reference line reads "All sources: Danica Noble · 67%". Pairs
  naturally with the "My sources" label (shared noun makes the contrast
  self-explanatory).
- **G27 — Shared grammar for both bars.** Signal name first, then choice:
  "Times differs · Keith Scully" (Times keeps its status verbs — agrees /
  differs / not covered) and "All sources: Danica Noble · 67%". Accessibility
  note: tone tint must not be the only agree/differ carrier — the Times line
  has its verb; the All-sources line should carry an aria-label (or brief
  visible word) stating agreement when the leading choices differ.
- **G28 — Remove the footer "sources summary" section (round 3).** The guide
  footer block containing "Viewing 40 of 40 sources." and the "Customize your
  sources" link (`.sources-summary`) is deleted entirely — vestigial holdover
  from the previous accordion layout; the Sources entry point lives above the
  fold (and in the A3 shared nav). This supersedes the guide-footer half of
  D17; D17's verbiage fix still applies to the Sources page itself. The
  aria-live "comparison shown" status that lives in this block moves to (or is
  covered by) the existing top-of-page lens notice.
  Superseded in part 2026-07-31: the footer block stays deleted, but the
  always-present sticky sources strip is now the primary in-page entry point.
- **G29 — Sources page: comparison category copy (round 3).** DECIDED.
  Category header reads "Comparison only" (not "Centrist comparison"),
  followed by exactly: "Shown for comparison; never counted toward the
  scores." (replaces the current three-clause paragraph). Also collapse the
  race-detail dialog's redundant double badge ("Centrist comparison" +
  "Comparison only") to a single label consistent with this header.

### L. Site shell (round 4, 2026-07-29 — post-#126 review)
Context: A1–G29 shipped in PR #126 and verified live. Round 4 is the full
second cleanup pass, approved 2026-07-29: site shell (L), lens/comparison
correctness (G2), lens presentation (H), data ink (H2), card anatomy (I),
color/tokens (J), and chrome/microcopy (K) sections below.

- **L53 — One frame for every page.** Every page renders the same `.page`
  shell at one width (76rem, set by the guide's grid) on the shared `#edf1f4`
  backdrop, with the same horizontal padding rail. Pages wanting a narrower
  *reading measure* (About prose, archive list) constrain an inner column
  (~46rem measure) — the frame is the site; the measure is the content.
  Replaces today's three systems: `.screen-guide` 76rem / Sources `.page`
  override 64rem / base `.page` 46rem. Result: band width and nav position
  identical across pages; all h1s start on the same left rail.
- **L54 — One masthead, brand always present.** Remove `show_brand` from
  `site_band_html` (shell.py); every page, the guide included, carries
  icon + "Seattle Elections Guide" + nav. DECIDED (Option 1): the guide hero
  h1 becomes the election ("August 2026 Primary"); the brand lives solely in
  the band. Every page h1 then describes its page (election / Customize your
  sources / About… / Guide archive) — also semantically right for
  election-scoped `/e/<id>/` URLs as the archive grows. The hero-meta block
  ("Election August 4, 2026" + "N races") is removed as redundant with the
  new h1 and the controls-bar count (absorbs candidate H33). DECIDED: the
  hero kicker becomes the exact election day — "ELECTION DAY · AUGUST 4"
  (templated per election) — above the h1; day and month/year each stated
  once at different precision.
- **L55 — Shared, redesigned footer (first-principles).** One implementation
  (mirroring `site_band_html`), same frame on every page. Three jobs only:
  exit ramps, provenance, closing the frame. Anatomy:
  1. Navy band mirroring the masthead: left, the same icon + wordmark lockup;
     right, an icon action cluster — Share, Printable PDF (election-scoped
     pages only), Contact (envelope), GitHub mark (CONFIRMED: replaces
     "Source and audit files" text; the audit-line commit link below is the
     separate deep path) — with `aria-label` + `title` + focus ring +
     adequate tap targets; plus one text link "How this works" → `/about/`.
  2. Compact mono audit line: election date · built date · Data/Code hashes ·
     Panel id+hash; the Code hash links to the GitHub commit. Global pages
     (About, archive) render the site-level variant without election/panel
     parts.
  3. Deleted: "ABOUT THIS GUIDE" kicker, "Agreement, not a candidate grade."
     h2, the percentages explainer, and "The Seattle Times is a separate
     comparison signal." — all owned by About ("What this guide is — and is
     not"). Page-specific method notes (e.g. the Sources page equal-weighting
     sentence from D18) move into the page body near what they explain; the
     shared footer carries only shared content. The hidden print
     source-directory and sr-only status regions are unaffected.

### G2. Lens & comparison correctness (round 4)
- **H30 — One canonical co-endorsement order.** The server card label and the
  JS-built labels order tied candidates differently ("Sharon Tomiko Santos /
  Kelabe Tewolde" vs "Kelabe Tewolde / Sharon Tomiko Santos"): the client
  joins `winnerIds` in engine order while the server label has its own order.
  Invariant: identical order everywhere a tie is rendered (cards, All-sources
  lines, dialog, print). Mechanism is implementation's choice (emit the
  server's order in the payload, or make both sides sort identically).
- **H31 — The Times verb must describe what the reader sees.** Times
  agree/differ/not-covered status is baked in server-side against the audited
  result and never recomputed when a lens changes the displayed leader, so it
  can read "agrees" while differing from the number beside it. While a lens
  is active, recompute the Times tone and verb client-side against the
  displayed (personalized) result — same rule the All-sources bar already
  follows. Default view and print keep the server-rendered status.
- **H32 — No aria-only explanations.** The neutral Times state currently
  tells screen readers "…progressive sources have no consensus" while
  sighted users see only a verbless "Times · Mike Diaz". Whatever the
  wording, the visible bar must carry the same explanation the aria-label
  carries. Companion: the dialog's bare "Confidence warning" flag becomes
  self-explaining microcopy (what is warned about, e.g. small sample), and
  any state that triggers it must be visible on the card presentation too,
  not only in the dialog summary.

### H. Lens presentation (round 4)
- **H38 — Retire the per-card "My sources" pill; the caption carries the
  lens (mock-up Variant D, DECIDED 2026-07-29).** The outlined pill after
  every race label repeats page-level state 32× and lands unpredictably
  (variable-length race labels). Instead, the support caption — already in a
  fixed position under the meter (per I39) — becomes
  "Based on N of M selected sources" while a lens is active; the default
  caption is unchanged ("Based on N endorsing sources"). No new elements;
  the fact survives cropped screenshots and race deep links.
  Companion (DECIDED, same rationale — "we aren't personalizing this"):
  de-possessivize lens labels site-wide; no user-facing "my" remains.
  "Customize your sources" (an instruction, not a possessive claim) stays.
  The dialog's "My sources" section itself is deleted outright by I56 —
  no rename needed there. Note: G26's "All sources" label is unchanged and
  stands on its own after this — its original pairs-with-"My sources"
  rationale is superseded; the contrast now reads against the caption's
  "selected sources" phrasing.

- **I56 — The race-detail dialog must agree with the active lens.** With a
  lens active, the dialog's lens block shows the personalized result (e.g.
  "Kelabe Tewolde · 65% · Based on 10 endorsing sources") while everything
  below it — candidate sections, "Tied for lead" kickers, per-candidate
  counts and meters, source rows — still renders the audited full panel
  ("7 endorsing sources · 50%") with no marking of which rows are selected:
  one panel, two contradictory answers. Root cause: candidate sections are
  server-rendered (`race_detail_candidate_sections`) and the client payload
  carries race-level cells only, no per-candidate source attribution, so the
  lens script cannot re-render them. DECIDED 2026-07-29 — option (b), with
  a hard invariant: **no quantity appears with two values.** Every computed
  number in the dialog — per-candidate endorsing counts, shares, meters, and
  the "Leading choice"/"Tied for lead" kickers — must equal the lens numbers
  shown on the main page while a lens is active. Unselected sources remain
  fully visible as evidence: their rows stay in place, visibly de-emphasized
  and marked as not counted; the audited full-panel baseline stays available
  through the existing "All sources" reference line (G26/G27 idiom), never
  as unmarked candidate metrics. With the body itself lens-aware, the
  dialog's top "My sources" summary section (heading, restated result line,
  and selected-source chip list) is DELETED as redundant — the highlighted/
  dimmed rows carry the selection in place. Its two useful remnants rehome:
  the divergent "All sources" reference line renders once in the dialog body
  (same quiet-bar component as the card), and the confidence flag follows
  H32 onto the visible presentation. Implementation note: recomputing
  per-candidate numbers requires per-candidate attribution client-side —
  either extend the payload with a per-candidate source map, or derive it
  from the dialog's own candidate-grouped rows (source codes on rows +
  the existing client scoring engine); mechanism is implementation's choice,
  the invariant is not.

### H2. Data ink (round 4)
- **H33 — absorbed by L54.** (Hero-meta "N races" removal.)
- **H34 — Compact captions drop the sentence.** Full view keeps
  "Based on N endorsing sources" (and H38's lens variant). Compact mode,
  where the caption wraps to two lines per card, shortens to "N sources"
  (default) / "N of M selected" (lens).
- **H35 — Suppress "· 0 split" on the Sources page.** Print the split count
  only when nonzero; a real split becomes more visible once forty zeros
  disappear. Applies to the shared `source_participation` macro (both
  templates + the renderer validator mirror — the already-noted deferred
  extraction of that macro into one source should ride along here).
- **H36 — Demote the dialog category chips.** Every endorser row carries a
  bordered pill; the taxonomy outweighs the data. DECIDED: keep row order,
  drop the pill chrome — category renders as plain right-aligned muted text.
  (Grouping rows by category with run-in labels was considered and can be
  revisited if the plain text still feels heavy.)
- **H37 — "Times agrees" drops the redundant name.** In the agrees state the
  choice is by definition the headline name directly above; render the verb
  alone. Differs keeps the differing name; not-covered/neutral unchanged
  (subject to H32's visible-explanation rule).

### I. Card anatomy (round 4)
- **I39 — Ungroup the caption sandwich; two clean card blocks.** Today a race
  card interleaves signal / caption / signal: the Times info bar renders
  *above* "Based on N endorsing sources" (inside the card's anchor), and the
  lens's "All sources" bar is appended *after* the anchor — so with a lens
  plus the Times active, two sibling reference bars are split by a floating
  right-aligned caption. New order:
  1. Primary block: race label → name + meter → "Based on N endorsing
     sources" directly under the meter row → insufficiency warning when
     present.
  2. Reference block at the card foot, bars adjacent, no interleaving:
     "All sources" first, then Times (ordered by proximity of meaning — the
     full-panel recomputation before the external comparison signal). Default
     view (no lens, no Times) renders neither; Times-only renders one bar as
     today.
  Implementation note: the detailed-edition print validator anchors each
  comparison's extracted text against the support summary that *follows* it
  (guide.html.j2 comment near the comparisons block); moving the support line
  above the Times bar requires re-anchoring that validator check in the
  renderer mirror, not just reordering markup.
- **I40 — One meter chrome.** The card meter (border `--line-strong`, track
  `#edf2f4`) and dialog meter (border `--tone-agree-border`, track `#fff`)
  differ for no reason. Unify on the card treatment; see J45 for the track
  token.
- **I41 — Low-fill label guard.** The white % label rides the fill,
  left-anchored; below roughly 30% fill (reachable under a lens and in
  dialog candidate meters) it bleeds onto the pale track and vanishes.
  Below the threshold, render the label after the fill in muted ink.
  Defensive only — explicitly not the tabled D14 meter redesign.
- **I42 — Compact rows must scan as rows.** Variable-height race labels
  (1–3 lines) push names and meters to different baselines across a grid
  row, defeating cross-card comparison. Reserve consistent label space or
  align the name+meter block across the row (subgrid or min-height;
  mechanism open) so a row of meters can be swept in one eye movement.

### J. Color & tokens (round 4)
- **J43 — Teal checkboxes.** No `accent-color` is set anywhere; the Sources
  page renders default browser-blue checks beside a teal Save button. Set
  `accent-color: var(--teal)` globally.
- **J44 — The eyebrow needs a paper variant.** `.eyebrow` is mint
  (`#9ee7df`), designed for the navy band; the Sources page reuses it for
  "RESEARCH STATUS" on cream at ~1.3:1 contrast — effectively invisible and
  a WCAG failure. Add a paper-context eyebrow (teal, matching the category
  headers) and use it everywhere an eyebrow sits on a light ground.
- **J45 — Tokenize the meter track.** `#edf2f4` appears 4× (screen + print
  meters); promote to `--meter-track` and use it in I40's unified chrome.
- **J46 — Bring print under B6/B7.** The print stylesheet still uses blue
  race accents (`border-left: var(--blue)`, blue header kickers) where
  screen moved to teal-for-data, and the pre-B7 near-duplicate greys
  (`#53636d`, `#44596a`, `#364152` vs `--muted: #52606d`). Align print's
  accents and greys with the token system; `--blue` in print returns to
  links only.
- **J47 — One tone for "Times comparison shown."** The same message renders
  amber (`.sources-comparison-status`) on the Sources page and blue-grey
  (`.lens-notice`) on the guide. DECIDED: unify on the amber comparison tone
  — amber is the Times/comparison identity everywhere else (Sources
  category, differ tints).
- **J48 — Residual literal sweep (B9 continuation).** Promote the remaining
  recurring screen-CSS literals (`#7794a8`, `#526f83`, hover tints
  `#f3f9f8`/`#c0d8d4`, badge borders `#c7d3dc`, row separators `#e0e7ed`, …)
  to tokens. No visual change; drift prevention.

### K. Chrome & microcopy (round 4)
- **K48 — Styled 404.** The worker returns bare `text/plain` "Not found"
  (`_pages_worker` in hosting/pages.py) — the only unshelled surface left.
  Serve a minimal branded page (band, rule, one line, links to the current
  guide and the archive), still `noindex`.
- **K49 — Rename the race-set toggle options.** "Complete | Contested" is
  ambiguous ("complete races"?). Legend stays "Races"; options become
  "All | Contested".
- **K50 — absorbed by L55.** ("About" vs "About & FAQ": the shared footer
  replaces the page-footer links; the page is called "About" in nav,
  "How this works" is the footer's framing.)
- **K51 — Defuse the split-endorsement math trap.** The dialog header can
  read "12 of 16 endorsing sources · 72%" where 12/16 ≠ 72% because
  co-endorsements split a source's point. Wherever count and share diverge
  due to splits, add a brief visible hint (e.g. "co-endorsements split" as
  a suffix or adjacent note; exact wording at implementation) so a reader
  who does the division isn't left doubting the arithmetic.
- **K52 — Space the sr-only filter status.** The hidden status parts
  concatenate as "32 races shown· Full· All Seattle ballot races"; add
  separator spacing so assistive tech reads it as a sentence.

## Tabled (explicitly deferred)
- **D14 — Meter redesign.** Scott has grander plans for the meter; only the
  fill-direction standardization (D14a) is in scope now.

## Open decisions
Round 1 all resolved 2026-07-29: icon = "The Meter" (A4); tagline =
"Seattle's progressive voices, distilled." (E20); serif masthead (C10);
"progressive" moves from h1 to tagline (A1/E20).

Round 2 all resolved 2026-07-29:
1. G24 applies site-wide — the pill badge is retired in default view too.
2. G26 label: "All sources: <name> · <share>".

Round 4 resolved 2026-07-29:
1. L54 kicker = "ELECTION DAY · AUGUST 4" (templated per election).
2. L55 GitHub mark confirmed (repo front door), alongside the audit-line
   commit deep link.
3. H38 = mock-up Variant D (caption "Based on N of M selected sources");
   possessive "my" removed from all lens labels.
4. I56 = option (b) with the no-two-values invariant: computed numbers
   (counts, shares, kickers) are lens-aware and match the main page;
   unselected sources stay visible but dimmed/marked as not counted; the
   dialog's "My sources" summary section is deleted as redundant.
5. All remaining round-4 candidates approved wholesale 2026-07-29 ("full
   cleanup second pass"): H30–H37, I40–I42, J43–J48, K48–K52 (H33/K50
   absorbed by L54/L55). Per-item sub-decisions recorded inline (H36 demote
   chips, J47 amber, K49 "All | Contested", I41 muted label past threshold).
