# HTML rendering

The renderer turns `publication_view_model.json` into one responsive HTML guide from one
autoescaped Jinja document and its CSS; it does not recompute consensus or presentation labels.
There is no generated PDF edition (issue 193): the guide carries a modest `@media print` block so
the reader's own browser prints a legible copy, which is what the kitchen-table case — printing the
guide to fill in a mail ballot — actually needs.

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

Races follow the ballot's section order: Federal, State, County, State Supreme Court, then City.
The grouping follows the office's governing jurisdiction, so Seattle Municipal Court appears under
City while Washington Supreme Court positions appear under State Supreme Court.

Printing suppresses the chrome a reader cannot use on paper — the brand band, the sticky filter
controls, the lens banner, the footer's action cluster — flattens the screen surfaces onto white,
holds the race grid at two columns whichever on-screen density is active, and keeps each race card
whole across a page break. The shell rules live in `base.css` so every page prints; the guide's own
rules live in `guide.css`; and the page margins and lens-notice suppression it shares with the
sources editor live in `guide-sources.css` (`rendering/stylesheets.py` declares which parts each
page reads). No font file is redistributed and the responsive typography is unchanged.

## Modules

The rendering package is split one concern per module, and nothing imports across a seam that
is not listed here (issue 242):

| Module | Owns |
|---|---|
| `rendering/config.py` | Reading the strict rendering contract, beside the model it validates into. |
| `rendering/context.py` | Derived display values over the view model. No markup, no I/O. |
| `rendering/documents.py` | The Jinja environment and the four document renderers. |
| `rendering/validation.py` | Reparsing a rendered document and checking it against the view model. |
| `rendering/browser.py` | Chrome process management, the CDP client, and screenshot capture. |
| `rendering/pipeline.py` | `build_rendered_guide`: render, capture, validate, publish. |

`rendering/__init__.py` re-exports the build entry points (`build_rendered_guide`,
`render_html_document`, `read_rendering_configuration`, `validate_rendered_guide`, and their
models); import anything else from the module that owns it. There is no `renderer.py` façade —
a caller's import names the concern it depends on.

## Requirements

Chrome or Chromium, used for the rendering validation captures. Set `CHROME_PATH` or pass
`--chrome-path` when it is not discoverable. Install the locked Python environment with
`uv sync --frozen`.

## Build

First create the canonical exports, then render the shared view model:

```bash
uv run election-guide export build \
  --dataset-path data/normalized/canonical-dataset.json \
  --consensus-path data/normalized/consensus.json \
  --output-dir build

uv run election-guide render build \
  --view-model-path build/publication_view_model.json \
  --config-path config/rendering/guide.yaml \
  --output-dir output/rendered
```

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
└── screenshots/
    ├── desktop.png
    └── mobile.png
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
  horizontal overflow, expose every race and the filter controls, and contain visible pixels; and
- an approved coarse perceptual baseline catches wholesale hierarchy, palette, or layout changes
  while tolerating minor browser and font-rasterization differences.

`rendering_validation_report.json` records the machine checks. Review both responsive screenshots
after every meaningful template or CSS change; the image checks catch structural regressions but do
not replace human inspection of wrapping, hierarchy, contrast, and legibility. Print is not
machine-validated: check it in a browser's print preview when a change touches the print rules.

Browser and font rasterization can vary across operating-system and Chrome versions. Canonical
values are deterministic inputs; macOS and Linux therefore have separately approved coarse visual
signatures under the same tight tolerance. Independent blank-image, dimension, and overflow checks
remain strict. Human review remains required for every meaningful design change.
