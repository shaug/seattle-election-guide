# Runbook: endorsement source daily verification

**Status: proposed, not adopted.** Nothing here is wired into
`config/calendar/elections.yaml`. It is written in runbook form so adopting
it is a matter of resolving the two items in "Preconditions" below, not
designing a process from scratch.

A 2026-08-05 spot audit against a third-party aggregator found seventeen
endorsement decisions, across six consensus sources, published after this
project's original captures and never re-collected — one gap was not
cosmetic, flipping a race from a reported tie to a real plurality. Full
numbers and the before/after are in
`data/releases/wa-2026-primary/source-decisions.yaml` (sources updated
2026-08-05) and `data/releases/wa-2026-primary/source-panel-impact.json`.
The pipeline was not at fault — every decision it held was correctly
transcribed from what each source had published *at capture time*. The gap
was cadence: a source is captured once into the ledger, and nothing checks
it again unless a human happens to.

**What this actually delivers today is narrow, and the rest of this document
says so plainly rather than papering over it.** The project already has the
right tool for a recurring recheck — `collect refresh`
(`docs/COLLECTION.md`), a per-source adapter that fetches or ingests a page,
diffs it semantically against the last known state, and records an immutable
event — but only one source of 48 registered in `config/sources/default.yaml`
has an adapter (`config/adapters/transit-riders-union.yaml`), and even that
one was scheduled at only three pre-election calendar milestones, weeks
apart. Building adapter coverage for more sources is not a detail of this
proposal; it is the proposal. The recurring-schedule and drift-ticket
machinery below is real and worth adopting on its own, but on the day it
ships it protects one source. A "last verified" visibility table (Procedure
step 4) is not a substitute for coverage — this very audit shows that
staleness sitting quietly in a `captured_at` field, unenforced, does not get
noticed on its own.

## Trigger

A recurring `workflow: collect refresh` trigger, `reference:
docs/runbooks/endorsement-source-daily-verification.md`, at two cadences
(exact schema TBD — see Preconditions):

- Weekly, from `collection_opens` (`offset_days: -56`) through `ballots_mail`
  (`offset_days: -18`, both already declared for `wa-2026-general`).
- Daily, from `ballots_mail` (`-18`) through `election_day` (`0`).

The accelerating cadence matches the logic the calendar already uses
elsewhere (`collection_opens` → `refresh-mid-ballot` → `refresh-final` get
denser as the election nears) rather than asserting uniform daily coverage
for the full 56-day window. Endorsers are most active, and a miss is most
costly, in the eighteen days once ballots are actually in voters' hands —
that stretch gets genuinely daily coverage; the quieter weeks before it get
weekly, at a fraction of the fetch and review cost. If a source is known to
publish and revise on a tighter cycle, it can opt into the daily cadence from
`collection_opens` instead — a per-source override, not a reason to make the
default window daily throughout. Seattle Gay News is a concrete first
candidate for that override: this audit's own SGN capture grew from 3
articles to 9 in about two weeks, faster than the proposed weekly cadence
would have caught.

## Autonomy

Level 2 (Watched), per `docs/RUNBOOKS.md`'s table, for the detection half:
the refresh itself is deterministic and unattended (level 1 territory — "no
agent involved"), and a missed, failed, or suspicious refresh escalates to a
tracking issue rather than resolving itself (the level 2 addition). Folding a
diff into the ledger — verifying it, editing `source-decisions.yaml`,
regenerating fixtures, opening a PR — is judgment work and stays
human-launched, per `docs/RUNBOOKS.md`'s own guidance that judgment-heavy
work "should stay human-launched even when everything around it is
automated." That resolution step is a plausible level 3 (Dispatched)
candidate later — a tracking issue triggering an unattended agent run whose
only output is a PR for human review, never an auto-merge — but it stays at
a lower level until this runbook has real execution history, the same
reasoning `results-capture-election-night.md` applies to itself.

## Preconditions

Two items block this from running at all; everything else in "Open
questions" below is a real but non-blocking design choice.

- **Adapter coverage.** `collect refresh` only exists for
  `transit-riders-union`. Building `config/adapters/<source-id>.yaml` for at
  least the sources most prone to drift is prerequisite work. Most of the
  sources that drifted in the 2026-08-05 audit (Transit Riders Union, Sage
  Leaders, SEIU 775, UFCW 3000, Working Families Party, Seattle Gay News)
  publish a single static endorsements page or index — the cheapest adapter
  kind `docs/COLLECTION.md` documents (`static_html`).
- **Milestone generation.** `config/calendar/elections.yaml` is flat and
  hand-authored (`docs/ELECTION_CALENDAR.md`); a literal milestone entry per
  day is not in that spirit, and today's milestone `kind` is a closed
  vocabulary (`src/election_guide/calendar/models.py`'s `MilestoneKind`,
  enforced by the calendar validator) that does not include a recurring
  cadence. Before this can be scheduled at all, whoever owns the calendar and
  the scheduler (`#220`) needs to decide the mechanism — a cadence field on
  one milestone, or the scheduler expanding one milestone into a recurring
  trigger — and extend that closed vocabulary and validator accordingly. This
  is a real design decision, not something to default silently, and it is
  the one item in this document that is genuinely undecided rather than
  merely unbuilt.
- `--live` fetches remain opt-in per `docs/COLLECTION.md` and refuse
  non-public DNS/connection peers; nothing here changes that safety
  boundary.
- A place to land tracking issues — reuse whatever labeling convention
  `#220`/`#279` already established, so drift tickets are not a new
  taxonomy.

## Procedure

1. **Per the cadence above, for each adapter-covered source:**
   ```bash
   uv run election-guide collect refresh \
     config/adapters/<source-id>.yaml \
     --checked-at <UTC now> \
     --live
   ```
2. **Read the refresh event, and batch same-day results into one ticket.**
   A refresh event's semantic diff is computed against the *previous*
   captured snapshot per race (`docs/COLLECTION.md`), so a page redesign
   that breaks an adapter's parser does not hide silently — any decision the
   parser stops finding shows up as a `removed` entry in the diff, which is
   non-empty and already routes through the "non-empty diff" case below. The
   one case that mechanism cannot catch is a source's very *first* live
   refresh: with no prior snapshot, a broken adapter that extracts nothing
   just looks like a source with no endorsements yet.
   - Zero-diff on a refresh with a prior baseline to compare against:
     nothing to do. The event itself is the audit trail that the check ran
     and found no change.
   - **A source's first live refresh**: spot-check it against the actual
     page by hand before trusting it as the baseline every future refresh
     diffs against — this is an adapter-correctness check, not a drift
     check, and its fix is different in kind from the other two cases below.
     If the spot-check finds a problem, the fault is the adapter itself:
     fix `config/adapters/<source-id>.yaml`, open a PR for that fix, and
     once merged re-run `collect refresh --live` to produce a clean baseline
     before this source's next scheduled refresh runs. Note the correction
     in that day's ticket (open or join it as below) for the record, but its
     resolution is "fix the adapter and rebaseline," not "update
     `source-decisions.yaml`" — Step 3 is written for the other two cases
     only; do not run its ledger-edit checklist against a baseline-
     correction section.
   - Non-empty diff, or `failed` status, on a refresh that already has a
     prior baseline: both feed the same per-day ticket.
     If nothing has landed yet for that calendar day, open one issue titled
     `Endorsement drift: <date>`; if one is already open for that day (a
     second source drifted, or failed, the same day), add a section to it
     instead of opening a new one — do not wait to see whether more sources
     drift before creating the first issue. The 2026-08-05 audit found six
     sources drift at once, and per-source tickets right before an election,
     when volume peaks and capacity is thinnest, is a flooding risk worth
     designing around. Each section: the source id, whether it's a diff or a
     failure, the added/changed/removed decisions or the error, and a link
     to the refresh event's record.
   - Interpreting a `removed` entry specifically: it means either the source
     genuinely retracted a decision, or the adapter broke and stopped
     matching it — the diff alone cannot tell you which. Step 3's live-page
     check resolves that ambiguity the same way it resolves any other; see
     also Escalation for how to represent a genuine retraction once
     confirmed as real.
3. **Working a drift ticket** (human-launched; see Autonomy). This step is
   for the ticket's ordinary drift and `failed`-status sections; a baseline-
   correction section (Step 2) is resolved there, not here. A batched
   ticket's sections are independent — work, verify, and land each source's
   fix as its own PR rather than waiting to fix all of that day's sources
   before shipping any of them; the ticket stays open, with each section
   checked off, until every source it lists has landed. For each ordinary
   section:
   - Verify the diff against the source's live page directly — an adapter
     parses text with a regex; confirm it did not mis-split a name or miss a
     dual endorsement.
   - Update `data/releases/wa-2026-primary/source-decisions.yaml`: bump the
     source's `captured_at`/`reviewed_at`, add the new decision(s).
   - `uv run election-guide release compile data/releases/wa-2026-primary/source-decisions.yaml`
   - `uv run election-guide release verify data/releases/wa-2026-primary/source-decisions.yaml`
   - Regenerate every fixture the change touches — the fixture tests name
     their own regeneration commands in their failure messages
     (`uv run python -m tests.compare_parity`, `tests.page_parity`,
     `tests.mirror_parity`, `election-guide export lens-parity`); run
     `uv run pytest` and follow whatever else it names.
   - If the change moves a race's winner, tie state, or the leading-picks
     that any comparison signal disagrees with, also regenerate
     `source-panel-impact.json` (refresh `after` only, keep `before` pinned
     — `docs/POST_ELECTION_RETROSPECTIVE.md` § 1 explains why) and the
     hand-verified difference oracle at
     `tests/fixtures/comparison-default-differences.json`.
   - Open the PR; check off that source's section on merge; close the ticket
     once every section is checked.
4. **A source without an adapter** — the common case until the adapter-
   coverage precondition above is addressed — falls back to this session's
   manual method: fetch the live page, compare named decisions against the
   ledger by hand. This is not on any enforced cadence; it is whatever a
   human chooses to spend time on. Making that gap visible rather than
   silent is worth doing regardless — a per-source "last verified" date,
   surfaced in a generated table (`docs/SOURCE_DISCOVERY.md` would fit the
   existing pattern) — but treat it as a way to *see* the gap, not as a
   substitute for closing it. The 2026-08-05 audit is direct evidence that
   an unenforced timestamp does not get checked on its own.

## Verification

Once the Trigger milestone mechanism above is decided and wired in:

- Every scheduled week or day produces one refresh event per adapter-covered
  source; the event's *absence* is what would indicate the scheduled check
  itself stopped running. A zero-diff event on a refresh with a prior
  baseline is a pass. A source's first live refresh is never a pass on
  diff alone, zero or not — it only passes once Step 2's hand spot-check
  against the live page clears.
- Every non-empty diff and every `failed` status has a section in that day's
  tracking issue.
- No section of a drift ticket is checked off without a merged, green-tests
  PR — touching `source-decisions.yaml` for an ordinary drift section, or
  the adapter under `config/adapters/` for a baseline-correction section
  (Procedure step 2) — and the ticket itself closes only once every section
  is checked.

## Escalation

- **Any single `failed` refresh** joins that day's tracking issue immediately
  (Procedure step 2) — this is not itself an emergency.
- **The same adapter fails three consecutive scheduled refreshes**: escalate
  the severity of its section in the open ticket (or open one if none is
  open) and flag it explicitly as a likely page redesign needing the adapter
  rewritten, not just retried.
- **A drift ticket's diff includes a *removed* decision that Step 3
  confirms is a genuine retraction**, not an adapter break — flag for
  editorial judgment about how to represent the change in the public record;
  this is rarer and more consequential than an addition.

## Open questions

- **Adapter coverage order.** Prioritize by decision count already in the
  ledger (`seiu-775` and `ufcw-3000` each carry 23+ decisions, where one
  missed race is easy to overlook) rather than by which sources happened to
  drift in this one audit, since that list is a sample of one, not a
  ranking.
- **Third-party cross-checks as a second signal.** Independent of adapter
  coverage, an occasional automated comparison against a second aggregator
  (as this session did manually) is a cheap way to catch drift in sources
  that will never get a first-party adapter — but it inherits that
  aggregator's own scope and errors, so a disagreement is a lead to verify
  against the primary source, never ground truth on its own.

## Postmortem notes

- Not yet executed. Not yet adopted. First execution depends on both
  Preconditions items landing: adapter coverage beyond `transit-riders-union`
  and a decided milestone-generation mechanism.
