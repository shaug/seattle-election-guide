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

## Registry and panel identity

The source registry has two hashes with different jobs. `source_registry_hash` covers the complete
validated registry and is the release audit identity. `panel_hash` covers only the stable
transport-facing selection contract used by published panel snapshots and personalized links.

The canonical panel projection hashes these fields, in validated transport order:

- panel identity `schema_version`;
- categories: `id`, `code`, `label`, `selectable`, `panel_role`, and the current selectable
  `member_source_codes`;
- sources: `id`, `code`, `name`, `panel_role`, derived `selectable`, `reporting_category_id`, and
  `selection_category_ids`;
- each source's eligibility `kind` and `jurisdiction_ids`;
- each source's `overlap_group_ids`, plus each overlap group's `id`, `label`, and `member_ids`; and
- retired transport codes: `code`, `kind`, `former_id`, `retired_in_panel`, and the user-visible
  migration `reason`.

Overlap collections are set-valued: the projection sorts each source's `overlap_group_ids`,
sorts groups by `id`, and sorts each group's `member_ids`. Reordering these collections changes
the full registry audit hash but preserves panel identity and any matching compatibility binding.

Registry and election IDs, `panel_id`, `panel_version`, freeze and research timestamps, registry
notes, category descriptions, organization and discovery URLs, geographic labels already encoded
by eligibility, publisher provenance, panel rationale, and every discovery field stay outside that
projection. They remain covered by `source_registry_hash`. Excluding the panel ID and version means
an empty version bump cannot manufacture a new contract hash.

A discovery refresh changes `source_registry_hash` and therefore release audit identity. It does
not change `panel_hash` and does not require a panel version bump. A membership, transport-code,
selectable-category, role, eligibility, overlap, attribution, or retired-code migration change
changes `panel_hash` and must be published under a new panel version.

For schema 1.2 registries, `research_cutoff` and `frozen_at` retain the original panel-freeze
history. A later discovery refresh updates that source's `discovery.checked_at` and publication
metadata without moving either historical timestamp. Schema 1.1 registries retain their original
pre-freeze discovery cutoff validation.

Schema 1.2 registries carry one required `panel_hash_compatibility` lineage anchor. For panels
whose legacy full-registry hashes were already published, the anchor preserves that published hash
only while its `contract_hash` exactly matches the current canonical projection; a mismatch makes
the canonical hash the candidate `panel_hash`. The anchor remains on successor versions in the same
lineage, with `panel_id` naming the initially published panel. A new lineage anchors its initial
canonical hash to itself. The compatibility object is covered by `source_registry_hash` but never
enters the panel projection. A differing published hash is accepted only for the exact primary or
general legacy tuple recorded in `sources/models.py`: panel ID, canonical contract hash, and public
legacy hash. These bindings are immutable; editing the registry anchor cannot authorize a changed
contract. All other anchors must have equal `contract_hash` and `published_hash` values.
Retaining the anchor ensures an empty version bump repeats the anchored hash
and is rejected by the catalog, while a structural successor uses its new canonical hash. Schema
1.1 remains readable for immutable historical inputs and retains its historical full-registry
`panel_hash` behavior.

Panel snapshot catalogs are append-only. Re-snapshotting an unchanged published panel is a no-op;
a changed contract under an existing `panel_id` is rejected. Never edit or regenerate an existing
catalog entry to resolve that rejection: review the structural change, assign a new panel version,
and append its snapshot.

## Immutable outputs

The default retained-original refresh (`retain_original`) creates three linked records
on a successful changed refresh:

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
when the storage root is exactly the official store above, and `local_only` otherwise. The
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

## Recurring verification (#497)

Follow [the canonical retained-evidence policy](../SOURCE_POLICY.md#verified-endorsements-survive-failed-access).
A failed request appends its actual failure and retains the previous comparison snapshot; an empty
or incomplete input cannot silently delete verified canonical decisions. A new extraction is a
review proposal, not a ledger edit. Later complete additions, affirmative changes and withdrawals
still pass normal factual review/approval. Access uncertainty can hide additions; it neither proves
withdrawal nor blocks release of retained verified evidence. Actual clocks, retries and counters stay.

The partial approved #589 milestone adds explicit failed-access observations and complete-initial
review qualifications inside the same immutable verification archive. It introduces no fetcher,
scheduler, evidence service, interval setting or source membership change. Generic acknowledgements,
baseline flags and HTTP success do not qualify a complete accepted review. A new permitted failed
check keeps its actual failure and last-success clock while recording a handled limitation;
reader-side reconciliation never backfills old records. Parser, incomplete/conflicting and unknown
cases stay unresolved. The existing publication review/admission gates remain required. See the
[source policy](../SOURCE_POLICY.md#prospective-access-limitations-589-partial-approved-milestone)
and the normal CLI procedure in the daily runbook.

The separate #589 interval capability adds optional strict whole-day source settings in policy
schema 1.2, pinned at first activation. Omission preserves all 46 current frequencies and legacy
record serialization; no current setting is populated. Fixed Pacific obligation dates remain
separate from real-success-anchored elapsed UTC freshness. Date-only evidence gains no invented
time, and an active-cycle interval edit cannot move old or future duties. See
[the source policy](../SOURCE_POLICY.md#optional-source-refresh-intervals-589) and
[the calendar contract](ELECTION_CALENDAR.md#optional-intervals-and-elapsed-freshness-589).

`config/verification.yaml` binds the current frozen election inputs to the six
adapters under `config/adapters/wa-2026-general/`. Other eligible sources receive
finite manual-review obligations. `verification plan`, `run`, `validate`, and
`reconcile` own scheduling, public factual provenance, archive integrity, and daily
review tasks. See [the runbook](runbooks/endorsement-source-daily-verification.md)
for the implemented boundaries, actual limitations, and adoption evidence.

A reviewed `section_pattern` may select exactly one visible publication section
with one capture group. General adapters use reviewed factual passages from #474;
they make no candidate inference. Recurring verification requires official-source review of
every changed byte set, even when its known-fact semantic diff is empty. First
live baselines require explicit reviewer attestations, bound to their snapshots;
fixture runs and unapproved baselines do not count as successful verification.

WFP monitoring collects the complete Washington candidate table directly from
`https://workingfamilies.org/wp-admin/admin-ajax.php` with public URL-encoded
POST parameters `action=more_candidates`, `state=25`, `count=0`. The reviewed
policy permits only this WFP request; ordinary callers remain GET. POST redirects
are refused, and the existing public DNS/peer, TLS, deadline and size limits apply.
Capture manifests identify the actual endpoint, status, method and form parameters;
the registry retains the human-facing candidate discovery URL. Current response
bytes are parsed privately and discarded after facts-only refresh; observed metadata and
content fingerprints remain public.

The October 19 complete response has 17 Washington rows: ten existing approved
in-inventory decisions and seven explicit exclusions outside the frozen inventory.
The source-specific row check preserves adjacent cell whitespace as one row;
unknown rows or malformed shapes fail visibly. Explicitly hidden rows or cells
also fail the complete response check before decision matching. Changed response
bytes always require review. Historical initial-page snapshots and approvals remain
immutable; neither approves the complete response. WFP's exact October 20 factual review
and October 21 native scheduled reuse remain accepted progress. New or changed complete
snapshots still require their own official-source review; the deployed secret-free six-source
process requires its revised scheduled acceptance evidence before adoption can be claimed. Authored fixtures prove parsing and archive
behavior, not live adoption or a new endorsement approval.

SGN discovery recognizes endorsement link text as well as title-bearing URLs,
so short canonical story links are fetched and revisited. Every fetched index
page's content hash participates in the comparison. An index change that the
link matcher cannot classify therefore remains a human-review lead, including
after the prior baseline was approved. Newly learned canonical story URLs are recorded
against the current observed index before later pagination or article work can fail.
They remain required across independent runners and link rotation; these obligations
assert neither a complete successful comparison nor baseline approval.

UFCW 3000 monitoring (#584) captures the complete endorsements landing page and
its relevant current-year official news articles, including the two October 15
initiative publications. The finite landing-page scan follows endorsement links;
it does not traverse the news feed or historical archive. Previously discovered
articles and the two known publications remain required after links rotate away.
Successful discovery records retain these URLs across independent runners. Newly
validated links also receive immutable `discovery-obligations/` records bound to
their current observed landing-page manifest before any required article fetch. These
obligations survive failed article fetches or parsing and later link rotation;
they assert required membership, never a complete comparison or approved baseline.
At most 100 articles and 64 MiB of total HTML are accepted, with the existing
bounded public-peer HTTP checks on every request. Unsafe article identities,
inaccessible required articles, and missing article heading/body structure fail
the check while preserving the prior comparison baseline.

The derived UFCW comparison binds the landing-page bytes and every original
article URL/hash. An article-only correction or withdrawal therefore requires
review even when the landing page and recognized factual mappings are unchanged.
Current HTTP observations retain their actual status and redirect metadata;
the derived comparison is a manual upload without an invented HTTP response.
The reviewed factual mappings remain unchanged. This expanded composite needs
review of its exact new baseline; the earlier landing-page approval does not
approve the new snapshot. Fixture-controlled reuse proves durable mechanics,
not live independent scheduled adoption or completion of #497.

Normal recurring collectors explicitly select `facts_only`; unrelated `collect refresh` callers
still default to `retain_original`. Every successful fetch, even unchanged bytes, creates a current
`availability: observed` manifest with official URL, actual retrieval/HTTP metadata, SHA-256 and
byte length but no storage reference. Derived composites have manual-upload provenance without
invented HTTP responses. A parse failure retains available observation metadata without promoting
a baseline. Unchanged checks reuse the prior factual snapshot/approval and validate the common
source/content-hash link while referencing the new observation.

Endorsement facts, official URL, actual check time and actual reviewer/review time are sufficient
durable evidence. An automated unchanged check does not claim the reviewer re-read the source.
Observed-only manifests establish metadata/facts provenance, not retained original bytes or
publisher authorship; full-page reconstruction is not promised. Private temporary responses are
discarded; normal verification, validation, factual approval, reconciliation and independent reuse
need no evidence key, restored pages, new ciphertext or replacement service. Historical IDs,
records, ciphertext, precise factual approvals, failures and releases remain unchanged. Migration
grants no new approval or fresh source read. Explicit legacy custody commands are documented
separately in [EVIDENCE_CAPTURE.md](EVIDENCE_CAPTURE.md#legacy-encrypted-custody-497).

TRU monitoring (#593/#497) now uses a narrow WordPress archive collector, described
in the [finite October 21 packet](GENERAL_RECHECK_2026-10-21_TRU.md). It traverses
only designated next archive pages to the reviewed September boundary, revisits
both known general articles and retained learned links, and records newly learned
membership before later collection can fail. The complete designated October
article supplies the twelve reviewed formal facts once. Complete archive/article
hashes and the exact linked meaningful JPEG hash drive deterministic comparison;
qualified recommendation text stays context. The known image is required on each
check, with no automatic OCR or replacement-asset discovery. The existing
40-page/100-article/140-capture/64-MiB bounds and HTTP safeguards remain in force.
Real HTML/image responses receive observed-only manifests and complete fingerprints; the
derived comparison has manual-upload provenance and no invented HTTP status.
Exact expanded baseline approval and independent native scheduled acceptance
remain separate outstanding work.
