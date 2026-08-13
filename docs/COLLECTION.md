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

## Where captured bytes live

Raw third-party artifacts default to restricted, local-only storage. Keep `data/snapshots/`
ignored and publish only permitted excerpts and provenance records under the repository policy.

**Official-authority artifacts are the exception: their bytes are committed.** A capture from a
counting authority — King County Elections, the Secretary of State — is `redistribution: permitted`
and is stored in the tracked `data/evidence/official/` root.

The reason is that redistribution and durability are two decisions, and treating them as one lost
real evidence. The 2026-08-04 election-night capture verified at capture time, recorded four
sha256 values in `docs/runbooks/results-capture-election-night.md`, and then vanished: its bytes
went to the Git-ignored `data/snapshots/` inside a disposable worktree, so nothing tracked them,
nothing pushed them, and removing the worktree deleted them. Those four hashes now describe
artifacts that exist nowhere, and the capture cannot be re-fetched — those URLs serve a later drop
(issue #357). The restricted default that sent them there was never a judgment about *these*
bytes. Election results published by a government counting authority are public records: not
paywalled, not copyrighted, not access-controlled. `DECISIONS.md` already permits committing a
full capture when "redistribution is clearly permitted," so this applies the existing rule to a
class nobody had distinguished rather than relaxing it. The volume is small — the four lost
artifacts totalled roughly 600 KB.

Storage scope is derived, never asserted. `evidence capture` records `storage_scope: repository`
when the storage root is the official store above (or inside it), and `local_only` otherwise. The
command already refuses to put a restricted artifact at an unignored repository path, so a
committed artifact is a permitted one by construction.

Scope keys on that one named store rather than on "tracked by Git" for a specific reason: the
scope feeds the capture-ID fingerprint, and other commands write captures to unignored
in-repository paths for their own reasons — `release compile` stages under `data/normalized/`. A
trackedness rule would hand those captures new identities and silently rewrite every release
manifest already committed.

Two rules follow, and both are enforced rather than documented-only:

- **A capture that cannot outlive its session fails before reporting success.** `evidence capture`
  refuses a Git-ignored storage root inside a linked worktree — the exact 2026-08-04 mechanism.
  Capture from the primary checkout, store the bytes at a tracked path, or use a storage root
  outside the repository.
- **Byte presence is swept, not assumed.** `election-guide evidence verify-all` verifies every
  manifest in `data/manifests/evidence/` against its bytes and reports each as `present`,
  `missing`, `corrupt`, `expected-absent`, or `no-artifact`. `make check` and CI both run it, so
  a manifest committed without its official-authority bytes fails the pull request.

`expected-absent` is the one status that needs stating explicitly, because it is where the sweep
deliberately does not fail. Restricted bytes are never in CI, so a sweep that demanded them would
fail on every restricted artifact — the tension that made this a single decision rather than two.
So an absent `local_only` artifact is reported `expected-absent` and passes: no environment but
the capturing machine ever holds those bytes, and a second checkout holds none of them. An
operator auditing a machine that is supposed to hold everything passes `--require-local` to drop
the exemption, which is the loud check for restricted evidence.

The exemption is decided per artifact, not by checking whether the store directory exists. Those
look equivalent and are not: the first local capture creates `data/snapshots/`, which the
endorsement sweep runbook has an operator do routinely, and a store-shaped test would from then on
report every artifact that machine never held as a loss — turning `make check` red on evidence
nothing is wrong with, which is how a mandated gate gets ignored.

Two things are never exempt. A `repository`-scope artifact must be present, because its bytes
travel with history: anywhere the repository is, they are. And bytes that are present but do not
match their manifest are `corrupt` under either scope.
