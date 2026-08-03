# Post-election retrospective

Run this after certification, at the `retrospective` calendar milestone —
roughly thirty days past election day, once the county has settled what
actually happened. Its purpose is narrow: carry source-panel and process
lessons into the next cycle instead of re-learning them.

Every item below names a file to open. Where an item asks a question, the
answer belongs in the retrospective note, not in memory. Write the note as
`docs/retrospectives/<election-id>.md` and link it from the next cycle's
planning.

Substitute the election's ID for `<election-id>` throughout; for the 2026
primary that is `wa-2026-primary`.

## 1. Source panel accuracy and gaps

Open `config/sources/default.yaml` and
`data/releases/<election-id>/panel-snapshots.json`.

- Which panel version shipped, and how many versions did the cycle go through?
  Each snapshot carries its `panel_id`, `panel_version`, and `panel_hash` — but
  **the snapshot catalog is not the full history.** It holds only the versions
  that were snapshotted; the `notes` block at the top of
  `config/sources/default.yaml` carries the rest, including the commit at which
  the first version remains reconstructable. Count versions from the notes, not
  from the catalog.
- Which of those versions actually changed scoring? Read the note for each one.
  A version can be purely structural — new identifiers or categories, with
  canonical scoring identical to the version before. **A version bump is not
  evidence of an effect.**
- For every source with `panel_role: consensus`, did it actually publish
  endorsements this cycle? A consensus source that published nothing is a
  weight that silently did not apply.
- For every source with `panel_role: excluded`, does the recorded reason still
  hold, or did the source change in a way that should reopen the question?
- Read `data/releases/<election-id>/source-panel-impact.json`. It records the
  deterministic scoring impact of **one** panel change — and it does not say
  which one. Its `before` and `after` blocks carry `computed_at` timestamps and
  content hashes but no version field, and the registry's `notes` carry no
  timestamps to match them against, so neither file alone answers the question.

  Attribute it from the `before` side: match `before.dataset_hash` and
  `before.input_hash` against the identity table of whichever document records
  that cycle's panel change — for the 2026 primary,
  `docs/SOURCE_PANEL_EXPANSION_2026-07-23.md`. Match on `before` rather than
  `after`, because the report may have been regenerated under later inputs,
  which moves the `after` hashes while leaving the change it measures unchanged.
  **Do not assume it measures the most recent panel version.** Was that impact
  anticipated when the change was made?
- Read its `changes` entries by `changed_fields`, not by count. Adding sources
  moves `eligible_source_count`, `missing_source_count`, and `warnings` on
  nearly every race, so the number of listed races is coverage bookkeeping. The
  editorial effect is the subset that changed `grade`, `winner_candidate_ids`,
  `is_tied`, or `winner_share` — that last one is the percentage the guide
  publishes, so it counts. Compute that subset per race; a per-field tally
  cannot tell you which races moved for bookkeeping reasons **only**.
- Compare `docs/SOURCE_DISCOVERY.md` against the races the ballot actually
  carried. Which offices had no eligible source at all?

Hold every answer against `SOURCE_POLICY.md`. If the policy and the cycle
disagree, amend the policy in the same pass — a policy nobody followed is worse
than no policy.

## 2. Coverage failures

Open `data/normalized/<election-id>-inventory.json` and
`data/releases/<election-id>/source-decisions.yaml`.

- Which races on the ballot ended with zero endorsements? Count them against the
  inventory's full race list, not against the races that happened to appear in
  the guide.
- Which races ended with exactly one? A single-source race is displayed but
  carries no consensus, and repeated single-source races point at a panel gap
  rather than a scoring problem.
- Which sources that could have contributed have no entry in the ledger at all?
  Do not look for an empty `decisions` list — the release schema requires at
  least one decision per ledger entry, so a source that recommended nothing
  findable is absent rather than empty.

  Diff the ledger's `source_id` values against the panel sources whose
  `panel_role` is *not* `excluded`. Excluding the excluded ones is the whole
  trick: they carry `eligibility: {kind: none}` and can never contribute a
  decision, so counting them as gaps manufactures failures the panel chose on
  purpose. Diffing the full panel instead inflates the gap count by the size of
  the excluded set.

- For each source left, read every one of its capture manifests in
  `data/manifests/evidence/` — every one, not the first. Sierra Club Washington
  recorded an `unavailable` capture and then a successful one hours later, and
  it appears in the ledger. Unavailable is a moment, not a verdict.

  Three outcomes matter, and they are different problems:

  - **Unreachable.** An `availability: unavailable` manifest, with the reason on
    the record. Its `discovery.status` is `access_restricted`.
  - **Reached and silent.** An `availability: captured` manifest with a healthy
    HTTP status and still no ledger entry — the organization was reached and
    published nothing findable. Its `discovery.status` is `not_found`. **This is
    not a pipeline bug**, and filing it as one wastes the next cycle. It is the
    easiest of the three to misread, because a successful capture looks like
    success.
  - **Never attempted.** No manifest at all. That is a collection gap, and it is
    the one that should not recur.

  Confirm every call against the source's `discovery.status` in
  `config/sources/default.yaml` and its row in `docs/SOURCE_DISCOVERY.md`. A
  consensus source that is reached and silent two cycles running is a
  panel-membership question, not a collection one.
- Read `data/normalized/canonical-dataset.json` for `review_items`. How many
  claims needed human resolution, and did any category recur enough to deserve a
  matching rule?

## 3. Sources that moved or disappeared

Open `data/manifests/evidence/` and `data/collection/refreshes/`.

- Which sources have an `availability: unavailable` manifest **and no later
  successful capture**, and what does each `unavailable_reason` say? Those are
  the ones the cycle could not reach without bypassing an access control; their
  `discovery.status` reads `access_restricted`. A source with a later successful
  capture was reached — see the Sierra Club case in section 2 — so counting
  unavailable manifests rather than unreachable sources overstates this list.
- Which refresh events carry `status: failed`? A source that failed late in the
  cycle is a different problem from one that failed before collection opened.
  Note that `data/collection/refreshes/` is where `collect refresh` writes and a
  cycle need not commit it, so an absent directory is not evidence that nothing
  failed.
- Which sources moved? The move record is `discovery.redirect_chain` in
  `config/sources/default.yaml`, mirrored in the "Redirects observed" section of
  `docs/SOURCE_DISCOVERY.md`. A source that moved need not have produced an
  evidence manifest at all — an excluded source never does — which is why the
  registry rather than the manifests is the place to look.

  Do not read a `redirect_chain` in a *capture manifest* as a move. Those record
  how one retrieval resolved, not where the source now lives: the 11th District
  Democrats' newsletter capture redirects through a Mailchimp short link every
  time, while its registered official URL never changed. Treating that as a move
  would replace an official organization page with a campaign-archive link,
  which `SOURCE_POLICY.md` ranks below it.

  Where a source did move, update `config/sources/default.yaml` now, while the
  evidence is in front of you, rather than rediscovering the move next cycle.
- Which sources required `browser_required: true` or a manual transcription?
  Those are the expensive ones; note whether the cost was worth the coverage.

## 4. Publication timing

Compare `config/calendar/elections.yaml` against what actually happened.

- For each milestone the election declared, what date did the work actually
  land? Read the git history of `data/releases/<election-id>/` and the capture
  records under `data/releases/<election-id>/manifests/` — capture records, not
  release manifests, which `docs/RELEASE.md` reserves for the artifacts inside a
  built release. These date collection rather than publication.
- Did the guide publish on the day ballots mailed, as the `guide_publishes`
  offset intends? If it slipped, by how long, and what was the blocking step?
- Were the refresh points worth their offsets — did either one actually catch a
  late endorsement?
- Did the election-night and post-certification captures happen? These are the
  unrecoverable ones. If either was missed, say so plainly in the note and fix
  the mechanism, not the milestone.
- Confirm the shipped release version in `config/hosting/site.yaml` matches the
  published GitHub Release. `election-guide hosting verify-releases` answers
  this directly.

Any offset that was wrong in the same direction twice is a calendar bug. Amend
the offsets in `config/calendar/elections.yaml` and record why in
`docs/ELECTION_CALENDAR.md`.

## 5. Corrections issued

- Read `review_decisions` and `overrides` in
  `data/normalized/canonical-dataset.json`. That is where a released cycle's
  human resolutions end up. Each decision carries its action, author, reason,
  evidence, and the review item it resolved; each override carries the field
  changed, the old and new values, the reason, the evidence, and the author.
- `data/review/decisions/` and `data/overrides/` are where the `review` and
  `review override` commands write before compilation. **Do not start there.** A
  cycle may commit neither, so an empty or absent directory is not evidence that
  no corrections were issued. They are working directories; the canonical
  dataset is the record.
- For each correction, answer one question: could the pipeline have caught this
  before publication? A correction that only a human reader could have caught is
  a different lesson from one a validation rule would have prevented.

## 6. Process changes for the next cycle

Close the loop by writing down what changes, and where:

- panel membership and eligibility → `config/sources/default.yaml` and
  `SOURCE_POLICY.md`;
- milestone offsets → `config/calendar/elections.yaml` and
  `docs/ELECTION_CALENDAR.md`;
- scoring or display rules → `DECISIONS.md`, which is the launch contract, not a
  scratchpad;
- validation rules that would have caught a correction → the relevant
  `election-guide … validate` command; and
- anything requiring a product decision → a filed issue, not a note.

An entry with no destination file is not a process change. It is a wish.
