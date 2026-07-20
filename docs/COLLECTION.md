# Source adapter refreshes

Source adapters turn a reviewed official publication into canonical race decisions without
guessing names or statuses. Each YAML adapter is source-specific, complete for the publication it
parses, and validated against the frozen source registry and ballot inventory before a refresh.

The initial production adapter is
`config/adapters/transit-riders-union.yaml`. Static HTML, rendered dynamic HTML, PDF, and image
adapters share the same strict interface and all have local fixture coverage. HTML adapters use
visible text, PDF adapters use page text, SVG adapters use embedded text, and raster images require
separately supplied OCR text and an exact confidence value. Raster OCR decisions are always marked
for review. HTML and SVG decisions are also review-marked because stored markup cannot establish
visibility rules from every external stylesheet; explicit hidden attributes and inline styles are
still excluded before matching.

## Refreshing a source

Ordinary tests and validation never access the network. Use a saved artifact when reviewing a new
or changed parser. Offline artifacts are recorded honestly as manual uploads: their manifests do
not claim that the command observed an HTTP response or redirect chain.

```bash
uv run election-guide collect refresh \
  config/adapters/transit-riders-union.yaml \
  --checked-at 2026-07-20T07:00:00Z \
  --input-path tmp/transit-riders-union.html \
  --media-type text/html
```

After the fixture and parser have been reviewed, a static HTML, PDF, or image adapter may fetch its
registered official URL only with explicit opt-in:

```bash
uv run election-guide collect refresh \
  config/adapters/transit-riders-union.yaml \
  --checked-at 2026-07-20T07:00:00Z \
  --live
```

Live collection refuses non-public DNS results and connection peers on the initial URL and every
redirect. Download size and elapsed time are bounded across the complete redirect and response
sequence.

Dynamic HTML requires a reviewed final-DOM artifact through `--input-path`; a raw HTTP response is
not accepted as rendered evidence. Raster images additionally require `--ocr-text-path` and
`--ocr-confidence`.

## Immutable outputs

Each successful changed refresh creates three linked records:

- a content-addressed raw capture under the local snapshot root and its public provenance manifest;
- an immutable extraction snapshot containing stable canonical decisions;
- an immutable refresh event with added, changed, and removed decision diffs.

Identical content reuses the current capture and extraction snapshot. A page whose bytes changed but
whose canonical decisions did not change creates a new snapshot with an empty semantic diff.
Collection or extraction failures append an explicit failed event and leave the last verified
snapshot in place. A subsequent parser fix can reprocess already captured bytes without creating a
duplicate raw capture. Corrected OCR text or confidence similarly creates a new extraction without
duplicating identical image bytes. Per-source locking, strictly increasing refresh times, and
event-linked heads keep concurrent and interrupted runs from promoting an incomplete snapshot.

Raw official-source artifacts default to restricted, local-only storage. Keep `data/snapshots/`
ignored and publish only permitted excerpts and provenance records under the repository policy.
