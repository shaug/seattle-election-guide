# HTML and PDF rendering

The renderer turns `publication_view_model.json` into one responsive HTML guide and one concise,
two-page US Letter PDF. Both presentations come from the same autoescaped Jinja document and CSS;
they do not recompute consensus or presentation labels. Print text has a configured 6-point floor.
If the complete content cannot fit at that floor, the renderer emits a compact two-page summary
plus a longer detailed PDF instead of shrinking or clipping text.

Seattle Times comparisons use one outlined, softly tinted result chip beneath the consensus choice.
Bold `Times agrees` or `Times differs` status text is separated from the lighter choice by a centered
dot; a restrained neutral `Times · not covered` chip means the captured guide has no Times
endorsement. Badge contents use a small optical correction so the visible glyphs, rather than
merely their CSS line boxes, appear vertically centered. Color is never the only status signal.
The canonical comparison status and legacy badge label remain available in audit exports.

The concise PDF uses a scan-first, two-column briefing layout. Print typography is sans serif,
candidate or choice names carry the strongest row emphasis, alternating race backgrounds separate
adjacent choices, and each race forms a three-line unit: office; choice with a fixed-width,
right-filled consensus meter; then the Times comparison and explicitly endorsing source count
aligned beneath the fields they explain. Shared meter widths make shares comparable down each
column. Fine meter outlines, soft empty tracks, and optically centered tabular percentages keep
the quantitative encoding legible without dominating the choice. Section bars and flex-distributed
race rows use the available page height instead of
shrinking into the top of the sheet. The explicit midpoint split repeats a continued section bar
when a category crosses columns.
Page two groups methodology into independent column panels so short sections do not force unrelated
content into dense or oversized shared rows.

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
`Seattle_2026_Primary_Endorsement_Guide_Detailed.pdf` and `pdf/detailed-pages/`. The validation
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
    ├── Seattle_2026_Primary_Endorsement_Guide.pdf
    └── pages/
        ├── page-1.png
        └── page-2.png
```

## Blocking validation

The generation fails unless:

- responsive HTML contains every canonical race in order and every display value; each affirmative
  endorser appears under every endorsed candidate or choice with its own evidence link;
- the configured desktop and mobile captures use their exact CSS viewport dimensions without
  horizontal overflow, expose every race and the filter controls, and contain visible pixels;
- the PDF has exactly two nonblank US Letter pages with selectable text, URI links, and configured
  title, author, and subject metadata, plus document, heading, article, and paragraph structure tags;
- a normal concise PDF contains every published race display value; when overflow invokes the
  fallback, the compact PDF retains the race, recommendation, consensus share, explicit-source
  count, Seattle Times comparison, and insufficient-evidence warning while the detailed PDF
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
