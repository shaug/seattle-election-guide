# Runbook: endorsement discovery sweep

Locate, capture, and transcribe every panel source's endorsement decisions for one election.
This is the judgment-heavy half of the agentic runtime (`docs/RUNBOOKS.md`): an unbounded
window across many sources with unknown publication times, where the CLI's job is to make each
decision auditable and the executor's job is to decide what a page actually asserts.

The procedure below is the one the 2026 primary's collection followed, written down after the
fact rather than designed in advance. Where the primary got something wrong, the postmortem
notes say so and this document carries the correction.

## Trigger

The `collection_opens` calendar milestone opens the window; the `refresh` milestones re-run the
sweep inside it. For `wa-2026-general` those are 2026-09-08 (`-56`), 2026-10-23
(`refresh-mid-ballot`, `-11`), and 2026-10-30 (`refresh-final`, `-4`).

The real deadline is neither of the refreshes. `guide_publishes` is at `-18` (2026-10-16), so
the **first complete sweep must land before that date** — the refreshes come after publication
and correct a guide voters can already read. Plan the first pass against `-18`, not against
election day.

Cadence inside the window belongs to the source registry, not to this document. Each source's
`discovery.checked_at` in `config/sources/default.yaml` records when it was last looked at, and
the sweep works that field: the oldest `checked_at` is the next source to check. Three declared
milestones across a 56-day window is a floor, not a schedule — see the Postmortem notes for what
that floor cost the primary, and `endorsement-source-daily-verification.md` for a proposed
denser cadence that is not adopted and does not bind this runbook.

## Autonomy

Level 1 (Scheduled) for the trigger, human-launched for the work. The calendar is repository
data and #220's scheduler opens the tracking issue; nothing dispatches the sweep itself.

It stays that way. `docs/RUNBOOKS.md` names endorsement decisions as the example of judgment-heavy
work that "should stay human-launched even when everything around it is automated," and this
runbook agrees rather than treating that as a temporary state to graduate out of. Unlike
`results-capture-election-night.md`, which is mechanical once the URLs are known and is a genuine
level-3 candidate, the expensive step here is deciding whether a sentence is an endorsement — see
Judgment criteria. Sessions may be agent-run; the launch, the transcription review, and the pull
request are human.

## Preconditions

Verify each from the repository alone:

- The election declares `collection_opens` in `config/calendar/elections.yaml`, and
  `uv run election-guide calendar validate config/calendar/elections.yaml` passes.
- `config/elections/<election-id>.yaml` exists (`election init`, `-75`).
- The official ballot inventory is imported (`inventory import-initialized`, `-70`). Every race
  and candidate identifier a decision names has to resolve against it; without the inventory
  there is nothing to transcribe *into*.
- The source panel is frozen (`sources snapshot`, `-60`) and
  `uv run election-guide sources validate config/sources/default.yaml` passes. The freeze is
  what keeps the sweep from selecting sources on the basis of what they turned out to say
  (`METHODOLOGY.md`).
- A working directory under the Git-ignored `tmp/` for downloaded artifacts. Never leave a
  restricted input at an unignored repository path — `evidence capture` rejects it.

## Procedure

### 1. Work the frozen registry, not a search engine

Iterate `config/sources/default.yaml` in `discovery.checked_at` order, oldest first. For each
source with `panel_role: consensus` or `comparison`, resolve its current publication from the
organization's own site — `organization_url`, or the prior cycle's `discovery.canonical_url` as
a starting point, adjusted for the new election.

Search results and third-party aggregators are discovery leads only (`SOURCE_POLICY.md`). A
lead tells you where to look; the official organization page is the evidence. Never transcribe
a decision from an aggregator, even a good one — the primary's own drift audit used one as a
lead and then re-verified all six sources against their live pages before touching the ledger.

### 2. Record a discovery state for every source, including the empty ones

The four preregistration states are `published`, `not_found`, `not_an_endorsement_publisher`,
and `access_restricted`. They describe publication discovery, never a source's decision.

`not_found` must never be normalized as an explicit no-endorsement claim. A source that
published nothing contributes no decisions and no points, and that is a *different* fact from a
source that published "we are not endorsing in this race."

### 3. Capture the artifact

```bash
uv run election-guide evidence capture tmp/<artifact> \
  --source-id <source-id> \
  --requested-url <url followed> \
  --canonical-url <final url> \
  --retrieved-at <UTC timestamp of the fetch> \
  --http-status 200 \
  --media-type <text/html | application/pdf | image/jpeg> \
  --title "<organization> <election> endorsements" \
  --capture-method <static_html | pdf | image | browser> \
  --redistribution restricted \
  --redistribution-note "Full third-party page retained locally for review only."
```

Capture methods and their constraints are in `docs/EVIDENCE_CAPTURE.md`: direct methods require
the observed 2xx, a browser capture must record `--browser-required`, and a changed canonical
URL needs the full `--redirect-url` chain beginning at the requested URL.

When the page cannot be reached without bypassing an access control, record the metadata-only
form instead and move on. Do not work around the control:

```bash
uv run election-guide evidence unavailable \
  --source-id <source-id> \
  --requested-url <url> \
  --retrieved-at <UTC timestamp> \
  --http-status 403 \
  --media-type text/html \
  --unavailable-reason "The official page denied unattended access." \
  --redistribution-note "No page content was retained or redistributed."
```

An adapter-covered source takes the deterministic path instead — today that is
`transit-riders-union` alone (`config/adapters/`). `collect refresh` captures, extracts, and
diffs against the previous snapshot in one command (`docs/COLLECTION.md`):

```bash
uv run election-guide collect refresh \
  config/adapters/<source-id>.yaml \
  --checked-at <UTC now> \
  --live
```

Its semantic diff is the only mechanism in the pipeline that notices a source changed its mind.
Every source without an adapter is checked by a human or not at all.

### 4. Apply the judgment criteria

This is the step that cannot be automated, and it is where a sweep goes wrong. `REVIEW_GUIDE.md`
governs; the criteria below are how the primary applied it.

**What counts as an endorsement.** An official decision by the registered organization for the
target election. Discussion, praise, an interview list, a candidate questionnaire, a "who we're
watching" post, polling, and reporting are not endorsements. If the wording will not survive
being quoted back — "we recommend," "we endorse," a check mark in the organization's own guide —
it is not one.

**Match the race before matching the choice.** Jurisdiction, office, district, and position all
have to agree. Then every named choice must resolve to a candidate or ballot option in that race
in the frozen inventory. A name that does not resolve is an escalation, not a judgment call.

**Co-endorsements.** A source naming more than one candidate in one race is one decision with
several `candidate_ids`, never several decisions:

```yaml
- race_id: supreme-court-justice-3
  candidate_ids: [supreme-court-justice-3--jaime-michelle-hawk, supreme-court-justice-3--mike-diaz]
```

The source still contributes exactly one point, split equally — a dual endorsement gives `1/2`
to each choice, larger co-endorsements split the same way (`docs/SCORING.md`). Order carries no
meaning: record the order the source published and read nothing into it. A multi-candidate
decision deliberately raises a high-severity review item and a linked approval from the ledger
reviewer at compile time (`docs/RELEASE.md`); that is the ambiguity boundary working, not a
failure to fix.

Three things that look like co-endorsements and are not:

- **A top-two primary advancing two candidates.** The ballot's structure is irrelevant to what
  the source said. Two names endorsed is still one point split two ways.
- **Ranked, preferred, or "acceptable also" language.** The frozen policy is an exact equal
  split unless the source states an explicit allocation (`METHODOLOGY.md`). A stated preference
  order is not an allocation. If a source really does publish weights, escalate rather than
  inventing the arithmetic.
- **A list of candidates the organization interviewed, rated, or invited.** Not a decision.

**Explicit no-endorsement.** When a source publishes that it is not endorsing in a race, record
it:

```yaml
- race_id: us-house-7
  status: no_endorsement
```

It counts as resolved source coverage and contributes no points. `declined_to_endorse` is the
same shape for a source that says it declined. Neither may name candidates.

**Silence is not no-endorsement.** A source that simply skipped a race gets no entry at all.
Omission and `no_endorsement` produce different published numbers, and conflating them
manufactures coverage the source never provided.

**Eligibility is the registry's, not yours.** A legislative-district organization counts on any
Seattle-ballot race it explicitly decides — federal, statewide, judicial, countywide, citywide,
municipal court, ballot measures — but only on its *own* district's legislative contests
(`docs/SCORING.md`). The Seattle Times is comparison-only and never enters the consensus.

**Ambiguity stays ambiguous.** An unresolvable match is left unresolved rather than guessed.
Every claim carries an `evidence_locator` specific enough to reconstruct it — a heading, a
table row, a PDF page, a carousel slide, a check mark — not a bare URL.

### 5. Transcribe into the release ledger

Add or update the source's block in `data/releases/<election-id>/source-decisions.yaml`:

```yaml
  - source_id: <source-id>
    captured_at: <when the publication was actually checked>
    reviewed_at: <when the transcription was verified>
    evidence_locator: Official 2026 endorsement guide, named race heading.
    decisions:
      - race_id: <race-id>
        candidate_ids: [<candidate-id>]
```

`captured_at` is when the reviewer looked at the page, not when the file was edited. Update the
ledger's top-level `data_as_of`, `reviewer`, and `review_note` to describe the sweep honestly —
including what could not be verified.

A transcription taken from a screenshot or a restricted capture goes through the manual-entry
adapter rather than straight into the ledger (`docs/EVIDENCE_CAPTURE.md`):

```bash
uv run election-guide evidence manual validate manual-entry.yaml
uv run election-guide evidence manual import manual-entry.yaml
```

### 6. Compile, verify, and land

```bash
uv run election-guide release compile data/releases/<election-id>/source-decisions.yaml
uv run election-guide release verify data/releases/<election-id>/source-decisions.yaml
make check
```

`release compile` validates eligibility, races, candidates, publication state, timestamps,
allocation, and review provenance before writing the canonical dataset. `release verify`
recompiles into temporary storage and byte-compares. Regenerate every fixture the change
touches — the fixture tests name their own regeneration commands in their failure messages.

Open a pull request per `CONTRIBUTING.md`, stating which sources were swept, which are still
outstanding, and what was left unverified.

### 7. Re-sweep at each `refresh` milestone

Repeat steps 1 through 6 for the whole panel, not just the sources that were empty last time. A
source that published in September revises in October; the primary's most consequential error was
assuming otherwise.

## Verification

- `uv run election-guide sources validate config/sources/default.yaml` passes, and every panel
  source carries a `discovery.status` with a `checked_at` inside this election's window.
- `uv run election-guide evidence verify data/manifests/evidence/<capture-id>.json` passes for
  every capture taken during the sweep — it recomputes the SHA-256 and byte length from the
  stored bytes.
- `release compile` followed by `release verify` succeeds: verification byte-compares the
  canonical dataset, every permitted snapshot, and every capture manifest.
- Every eligible source resolves to exactly one of: a decision block in the ledger, or a
  non-`published` discovery state explaining its absence. The 2026 primary's 43 eligible sources
  ended at 41 blocks plus one `access_restricted` and one `not_found` — that arithmetic closing
  is the check.
- `release-status.json` reports the gaps rather than hiding them: `captured_source_count`,
  `source_access_failures`, and `incomplete_races` are the sweep's honest coverage record.
- `make check` is green.

## Escalation

Stop and ask a human when:

- **A source's publication is behind an access control.** Record `evidence unavailable` and stop.
  Never bypass authentication, a paywall, or robots controls, and never substitute a candidate's
  own claim or a third-party list for the organization's publication.
- **A named choice does not resolve against the frozen inventory.** This is either an inventory
  gap or a misread race, and both need a human. Do not create the identifier.
- **A source publishes a decision in a race its registered eligibility excludes** — most often a
  legislative-district organization in another district's contest. The registry decides; the
  sweep does not widen eligibility to fit a decision it found.
- **A source appears to belong on the panel and is not on it, or vice versa.** The panel is
  frozen for the cycle. Changing it is a reviewed version bump with a documented reason
  (`config/sources/default.yaml` notes), never an in-sweep edit.
- **A previously recorded decision turns out to be wrong.** Corrections are data records with the
  prior value, new value, reason, evidence, author, and timestamp (`REVIEW_GUIDE.md`), landed as
  their own reviewed change — not a quiet overwrite.
- **A source states an explicit non-equal allocation across co-endorsed candidates.** The frozen
  policy is an exact equal split; anything else is a methodology decision.
- **The first complete sweep will not finish before `guide_publishes` (`-18`).** Publishing with
  known-missing sources is a decision to make deliberately and disclose, not to discover.

## Postmortem notes

*(Appended after each execution.)*

- **2026-07-19 through 2026-08-05 — `wa-2026-primary`, first execution.** The panel froze at
  `wa-2026-primary-default-sources-v4`, 2026-07-23T17:10:00Z: 48 registered sources — 42
  consensus, 1 comparison, 5 excluded — resolving to 42 `published`, 2 `not_found`, 3
  `not_an_endorsement_publisher`, and 1 `access_restricted`. The sweep landed 538 decisions
  across 41 source blocks, of which 31 were co-endorsements and 9 were explicit no-endorsements.
  The two eligible sources without blocks are the Washington State Democratic Party
  (`access_restricted` — unattended access blocked, and no candidate or third-party list was
  substituted) and the Environment and Climate Caucus (`not_found` — its page documents an
  endorsement *process* and publishes no candidate decisions).

  What the execution actually taught:

  - **Effectively all of it was manual.** One adapter existed (`transit-riders-union`), so
    `collect refresh` covered 1 source of 48 and every other decision was located, captured, and
    transcribed by hand. Budget the sweep as transcription work, because that is what it is.
  - **A single capture per source is the failure mode.** A 2026-08-05 spot audit against a
    third-party aggregator found six consensus sources — Transit Riders Union, Working Families
    Party, Sage Leaders, SEIU 775, UFCW 3000, and Seattle Gay News — had published decisions
    after their 2026-07-20/07-23 captures that were never re-collected. Nothing had been
    transcribed incorrectly; the pipeline recorded exactly what each page said at capture time.
    The gap was cadence. One missed pair of endorsements had been rendering Legislative District
    37 Representative Position 1 as an exact 7–7 tie; with them counted it is a 9–7 plurality.
    Step 7 of this runbook exists because of that race.
  - **A first capture is a floor, not a snapshot.** Seattle Gay News grew from three endorsement
    articles to nine in roughly two weeks — faster than any of the primary's declared milestones
    would have caught.
  - **Four claims were left untouched on purpose.** Tech 4 Taxes, Tech 4 Housing, one Washington
    for Peace and Justice carousel slide, and one Working Families Party claim could not be
    re-verified against their live pages during the drift audit, so they were not edited on the
    aggregator's authority. Leaving a claim alone is a legitimate outcome; transcribing an
    unverified one is not.
  - **Social-only publishers are normal, not exceptional.** Several sources publish endorsements
    solely on Instagram, Facebook, or Bluesky, including one as a Facebook image
    (`image/jpeg`, Washington State Stonewall Democrats) that required manual transcription
    through the evidence adapter. Expect the manual path for a meaningful minority of the panel.
  - **Sources arrive late and unevenly.** Stonewall Democrats landed 2026-07-21, after the main
    coverage pass, and a panel expansion on 2026-07-23 added six more publishers — inside the
    last two weeks before an 2026-08-04 election. A sweep that treats its first pass as complete
    will be wrong.
