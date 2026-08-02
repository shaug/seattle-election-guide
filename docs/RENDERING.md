# HTML and PDF rendering

The renderer turns `publication_view_model.json` into one responsive HTML guide and one concise,
two-page US Letter PDF. Both presentations come from the same autoescaped Jinja document and CSS;
they do not recompute consensus or presentation labels. Print text has a configured 6-point floor.
If the complete content cannot fit at that floor, the renderer emits a compact two-page summary
plus a longer detailed PDF instead of shrinking or clipping text.

The guide presents the progressive consensus and nothing else. Issue 124 retired the per-race
Seattle Times comparison from every guide surface — screen cards, race detail, the personalized
lens, and print — in favour of the Comparisons page below, which is now the one place a reader puts
the Times beside the consensus. The canonical comparison status and legacy badge label remain in the
published view model and audit exports; nothing the guide renders quotes them, and PDF validation
rejects a legacy `Seattle Times AGREES …` run reappearing in the extracted text.

A lens link written before that removal stays valid. `lens-url.mjs` drops a comparison-role token
(for example `stim`, or the `Gcmp` category) while decoding and encoding: the token is ignored,
never rejected, and every other part of the link replays exactly. The published personalization
payload therefore keeps publishing comparison-role sources and categories, so the codec can
recognize such a token in order to discard it.

## Election comparison page

When a release's comparison policy is enabled, hosting publishes
`/e/<election-id>/comparisons/` and adds Comparisons to the shared navigation; the page shipped
at `/e/<election-id>/compare/` before issue 192 renamed it, and that address permanently redirects.
The temporary
`comparison_route_preview` manifest flag stages only the direct current-election route; it does not
change a release's serialized policy or expose navigation on any other page. Releases built before
the policy was enabled keep their disabled policy and do not gain a route or navigation item when a
newer release is staged beside them.

The server-rendered default is `All sources | The Stranger | The Seattle Times`, so the complete
default remains readable without JavaScript. `All sources` is copied exactly from the audited
publication display model; it is never recomputed in the browser. A direct-source column renders
that source's published stance. A category column applies the published equal-weight allocation
contract to its current eligible members. Comparison-role sources and categories remain
hard-excluded from aggregate arithmetic.

Column order is semantic: the first configured column is the selectable reference used by the
visible difference cues and cannot be removed or repositioned. Agreement is an intersection between
leading-pick sets, so a tie or co-endorsement agrees when it shares at least one leading pick. Blank
publication states render as the same dash; `Outside district` comes only from published race
eligibility. At narrow widths the race and reference columns remain fixed while the other configured
columns scroll horizontally; filters and difference-row calculation continue to use the complete
configuration.

Interactive state uses the versioned comparison fragment codec. Its `cols` value is an ordered
concatenation of fixed-width four-character source/category codes, including the reserved `gall`
audited-panel sentinel. The fragment also binds the panel, panel hash, data, and scoring versions
and carries the section, contested-race, and differences-only filters. A same-version fragment
replays exactly. Unknown tokens or mismatched versions degrade to the server-rendered default with
a persistent disclosure; they never silently select a different valid signal.

Each responsive race card uses its core recommendation area—office, recommended choice, consensus meter,
and support context—as one keyboard-focusable link to a stable `#race-<canonical-race-id>` fragment.
The panel eyebrow names both the election and the content type (`August 2026 Primary · Endorsements`) so a
shared fragment remains self-orienting.
The link opens a voter-facing panel organized first by endorsed candidate or choice, with sections ranked by
endorsing-source count. The leading section
contains the consensus meter and exact agreeing-source ratio so the panel does not repeat the leading
choice in a separate summary block. Each source row pairs the organization name with its registered
category badge; multi-candidate endorsements appear once in every candidate section they support. A
comparison-role source contributes no row, no count, and no candidate section here (issue 124): a
candidate only the Times picked gets no section at all. Explicit non-endorsements and decisions that need verification
follow the candidate sections. Split, tied, and verification rows retain the text needed to understand
the distinct decision. Sources that did not cover the race are placed last in a collapsed section.
Evidence-linked decisions make the whole source row clickable; capture and publication metadata remain
in the public view model and audit exports instead of competing with the decision itself. The panel's
`Share link` action copies the stable fragment. Direct fragments and browser back/forward state open or
close the matching panel, and focus returns to the race card's recommendation link on close.

The concise PDF uses a scan-first, two-column briefing layout. Print typography is sans serif,
candidate or choice names carry the strongest row emphasis, alternating race backgrounds separate
adjacent choices, and each race forms a three-line unit: office; choice with a fixed-width,
right-filled consensus meter; then the explicitly endorsing source count
aligned beneath the fields it explains. That third line keeps the height its retired comparison chip
set, so the caption stays clear of the warning line beneath it in extracted PDF text.
Shared meter widths make shares comparable down each
column. Fine meter outlines, soft empty tracks, and optically centered tabular percentages keep
the quantitative encoding legible without dominating the choice. Section bars and flex-distributed
race rows use the available page height instead of
shrinking into the top of the sheet. The explicit midpoint split repeats a continued section bar
when a category crosses columns.
Page two groups methodology into independent column panels so short sections do not force unrelated
content into dense or oversized shared rows.

Races follow the ballot's section order: Federal, State, County, State Supreme Court, then City.
The grouping follows the office's governing jurisdiction, so Seattle Municipal Court appears under
City while Washington Supreme Court positions appear under State Supreme Court.

The concise and detailed print editions use Helvetica where available, with Liberation Sans and
the generic sans-serif as portable fallbacks. Before printing, the document measures the visible
glyph bounds and applies the small per-label offset required to balance top and bottom whitespace.
Arial is not used in the PDF, no font file is redistributed, and the responsive guide's typography
is unchanged.

## Requirements

- Chrome or Chromium. Set `CHROME_PATH` or pass `--chrome-path` when it is not discoverable.
- Poppler's `pdftoppm`. Set `PDFTOPPM_PATH` or pass `--pdftoppm-path` when needed.

Install the locked Python environment with `uv sync --frozen`.

## Build

First create the canonical exports, then render the shared view model:

```bash
uv run election-guide export build \
  --dataset-path data/normalized/canonical-dataset.json \
  --consensus-path data/normalized/consensus.json \
  --output-dir build

uv run election-guide render build \
  --view-model-path build/publication_view_model.json \
  --config-path config/rendering/pdf.yaml \
  --output-dir output/rendered
```

Overflow generations additionally contain
`Seattle_2026_Primary_Elections_Guide_Detailed.pdf` and `pdf/detailed-pages/`. The validation
report records `concise_plus_detailed` and the detailed page count when that fallback is used.

The rendering destination must be absent or empty. The renderer stages the complete generation
beside that destination and publishes it only after every validation passes.

The source directory includes only sources with usable published endorsement decisions. Active
organizations whose official results were not found or could not be accessed appear separately as
coverage gaps, with their official links and research status. They remain in the publication view
model and audit exports but are not presented as contributing sources.

```text
output/rendered/
├── seattle-2026-primary-guide.html
├── rendering_validation_report.json
├── screenshots/
│   ├── desktop.png
│   └── mobile.png
└── pdf/
    ├── Seattle_2026_Primary_Elections_Guide.pdf
    └── pages/
        ├── page-1.png
        └── page-2.png
```

## Blocking validation

The generation fails unless:

- responsive HTML contains every canonical race in order and every display value; each affirmative
  endorser appears under every endorsed candidate or choice with its own evidence link;
- every race-detail view contains every canonical tallying source decision in the correct
  voter-facing outcome section, with affirmative multi-candidate decisions repeated once per selected
  candidate, comparison-role decisions absent entirely (issue 124), and the exact state and evidence
  link when one exists;
- desktop and mobile browser checks exercise copied permalinks, direct fragments, back/forward restoration,
  close-button and Escape behavior, focus placement/return, dialog naming, and viewport containment;
- the configured desktop and mobile captures use their exact CSS viewport dimensions without
  horizontal overflow, expose every race and the filter controls, and contain visible pixels;
- the PDF has exactly two nonblank US Letter pages with selectable text, URI links, and configured
  title, author, and subject metadata, plus document, heading, article, and paragraph structure tags;
- a normal concise PDF contains every published race display value; when overflow invokes the
  fallback, the compact PDF retains the race, recommendation, consensus share, explicit-source
  count, and insufficient-evidence warning while the detailed PDF
  retains the complete voter-facing values and methodology;
- Chrome print-layout measurements find no text below the configured font floor, clipped card text,
  underfilled or imbalanced race columns, overflowing methodology panel, or footer overlap, and
  Poppler page images do not touch the outer safety edge;
- an approved coarse perceptual baseline catches wholesale hierarchy, palette, or layout changes
  while tolerating minor browser and font-rasterization differences.

`rendering_validation_report.json` records the machine checks and page-image measurements. Review
both page PNGs and both responsive screenshots after every meaningful template or CSS change; the
image checks catch structural regressions but do not replace human inspection of wrapping,
hierarchy, contrast, and legibility.

Browser and font rasterization can vary across operating-system and Chrome versions. Canonical
values and PDF metadata are deterministic inputs; macOS and Linux therefore have separately
approved coarse visual signatures under the same tight tolerance. Independent blank-image,
dimension, overflow, and safe-edge checks remain strict. Human review remains required for every
meaningful design change.
