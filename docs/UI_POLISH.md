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
  Followed by one factual subline, e.g. "Endorsement agreement across
  40 organizations in all 32 Seattle races — every claim linked to its source."
  (counts templated per election, not hardcoded). The old comparison-source
  caveat moves out of the deck (it already lives on the Sources page and in
  About). This also carries the "progressive" framing so the h1 can be the
  plain brand name (A1).
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
- **G29 — Sources page: comparison category copy (round 3).** DECIDED.
  Category header reads "Comparison only" (not "Centrist comparison"),
  followed by exactly: "Shown for comparison; never counted toward the
  scores." (replaces the current three-clause paragraph). Also collapse the
  race-detail dialog's redundant double badge ("Centrist comparison" +
  "Comparison only") to a single label consistent with this header.

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
