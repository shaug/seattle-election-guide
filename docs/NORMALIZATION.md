# Normalization and review

Normalization turns evidence-linked extracted claims into canonical source/race decisions. It is
deterministic, constrained to the official ballot inventory, and deliberately refuses to guess
when a race, candidate, or endorsement meaning is ambiguous.

## Record model

The canonical dataset composes the already validated election inventory, source registry, and
capture manifests with these content-addressed records:

- extracted claims preserve source wording, evidence excerpts and locators, extractor identity,
  exact confidence, and review state;
- normalized endorsements preserve distinct singular, dual, multiple, no-endorsement,
  not-covered, not-published, unavailable, unverified, and ambiguous states;
- review items preserve the raw claim evidence, competing race or candidate matches, exact match
  scores, capture identity, severity, and creation time;
- review decisions append an approval or rejection with author, reason, evidence, and timestamp;
- overrides append the old and new JSON values with field, reason, evidence, author, and timestamp.

Every record ID is derived from its canonical JSON content. Changing a record without changing
its ID fails validation. Record files are write-once: repeating an identical write is harmless,
while attempting to replace an existing record with different bytes fails. Queue items are stored
under their claim ID so repeated normalization cannot create duplicate reviews. Terminal decisions
are stored under their review-item ID so concurrent reviewers atomically compete for the same
single decision slot; content IDs remain inside both records.

Explicit candidate endorsements use rational allocations serialized as strings (`1`, `1/2`,
`1/3`). Candidate IDs and allocation keys must agree exactly, every share must be positive, and
the total must equal one without floating-point rounding. Non-candidate states cannot carry an
allocation.

## Matching rules

Race and candidate matching proceeds through exact aliases, normalized aliases, then fuzzy
matching. Normalization handles capitalization, accents, apostrophes, punctuation, and spacing.
Candidate matches are drawn only from the already selected race and frozen source eligibility. A
tie within the configured ambiguity margin returns an ambiguous result with no selected ID.

Unknown endorsement wording, unmatched records, and ambiguous records create high-severity
review items. They never select the first or highest-scoring candidate silently.

## Commands

Validate a complete canonical dataset and its cross-record provenance:

```bash
uv run election-guide normalize validate path/to/canonical-dataset.json
```

Match an extracted claim. Its filename must equal its content-derived ID:

```bash
uv run election-guide normalize match \
  data/extracted/claim-0123456789abcdef.json \
  --created-at 2026-07-19T13:00:00Z \
  --manifest-dir data/manifests/evidence
```

The command loads the claim's capture manifest and frozen source registry. A safe singular or
non-candidate decision is written beneath `data/normalized/endorsements/`; a flagged,
multi-candidate, contradictory, unmatched, or ambiguous claim is queued instead.

An uncertain match is written beneath `data/review/queue/`. Inspect the unresolved queue and a
specific record with:

```bash
uv run election-guide review list
uv run election-guide review show review-0123456789abcdef
```

Append exactly one terminal decision for an item:

```bash
uv run election-guide review approve review-0123456789abcdef \
  --author reviewer-handle \
  --reason "Verified the candidate and race against the capture." \
  --evidence "Capture heading, paragraph 2" \
  --created-at 2026-07-19T13:10:00Z \
  --race-id king-county-assessor \
  --status endorsed \
  --candidate-id king-county-assessor--rob-foxcurran \
  --claim-path data/extracted/claim-0123456789abcdef.json
```

Approval validates the claim, capture, inventory, frozen source eligibility, selected race, and
candidate set before claiming the terminal slot. `review reject` accepts the same audit options
but needs no resolution fields. A second approval or rejection for the same item is rejected;
history is not overwritten.

Append a correction as data rather than a code exception:

```bash
uv run election-guide review override endorsement-0123456789abcdef \
  --target-path data/normalized/endorsements/endorsement-0123456789abcdef.json \
  --field status \
  --old-value '"ambiguous"' \
  --new-value '"no_endorsement"' \
  --reason "The source explicitly says it made no endorsement." \
  --evidence "Capture paragraph 3" \
  --author reviewer-handle \
  --created-at 2026-07-19T13:15:00Z
```

Override values are JSON, so strings need JSON quotes. Use `null`, booleans, numbers, arrays, or
objects directly when those are the actual field values. The target must be an intact canonical
record. Overrides for one target field are serialized, and each timestamp must be strictly later
than the current chain head.

## Validation boundaries

Complete-dataset validation rejects unknown sources, captures, claims, races, candidates, review
items, and override targets; duplicate source/race decisions; source-ineligible races; candidate
aliases that collide after normalization; candidate matches outside their selected race;
publication dates not carried by the capture; claim/endorsement semantic drift without an
approved structured resolution; stale override old values; inconsistent provenance; and multiple
terminal decisions.

An unavailable capture may support only a `source_unavailable` decision. Its extracted claim is
limited to the unavailable metadata and cannot claim candidate or page content that was never
captured.
