# Source and Evidence Policy

## Acceptable evidence

Prefer, in order:

1. An official organization endorsement page or voter guide.
2. An official organization PDF, image, or embedded guide.
3. An official organization social account when no more authoritative publication exists.
4. A documented manual transcription from evidence the reviewer may legitimately access.

Search snippets and third-party reporting are discovery leads, not endorsement evidence.

## Capture requirements

Each capture record includes the organization, requested and canonical URLs, title, retrieval
time, publication or update date when available, media type, capture method, content hash,
storage reference when original bytes are retained, and redistribution note. An observed-only
manifest instead records `availability: observed`, content SHA-256 and byte length without a
storage reference; it describes a successful observation, not retained original bytes.

Each extracted claim includes an evidence locator such as a heading, selector, table row, PDF
page, screenshot reference, or short excerpt.

## Public repository boundaries

The repository may contain official URLs, metadata, hashes, normalized facts, original review
notes, and short excerpts needed for verification. Do not commit plaintext complete third-party pages,
paywalled articles, browser profiles, credentials, personal data, or captures whose
redistribution rights are unclear.

Public provenance URLs must not contain authentication credentials, signed-access parameters, or
tokens. Record a clean official URL and keep credential-bearing retrieval details outside Git.

Restricted captures may be stored locally or in a separately controlled evidence store. Their
manifests must still permit authorized reviewers to verify integrity.

Recurring verification (#497) retains endorsement facts, official URLs, actual check timestamps,
and the actual reviewer and review timestamp as sufficient durable evidence. Current responses
are fetched and parsed in private temporary storage, then discarded. New recurring records contain
public factual snapshots, observed-only metadata, hashes, checks and review attestations; they
contain no full-page plaintext or ciphertext. Full-page reconstruction is not required or promised.
A hash and observed-only manifest provide metadata/facts provenance and comparison integrity;
they cannot prove retained original bytes or publisher authorship.

Normal verification, validation, factual baseline review, reconciliation and independent reuse
require no evidence key, restored historical pages or replacement evidence service. Every first,
changed or unapproved baseline requires official-source review. An unchanged automated check
references the existing exact factual approval and its actual reviewer/date; it does not assert a
new personal source read. Existing approvals retain their precise facts, actor and date. Migration
grants no approval, fresh check, backdated observation or reset of recorded failures.

Legacy recurring-verification ciphertext under `data/verification/<election>/vault/` remains
unchanged, along with historical records, IDs, approvals, failures and releases. The former
AES-256-GCM custody exception permitted full publicly accessible responses only as authenticated
ciphertext with a separate key. Explicit legacy seal/restore commands remain available for that
history; they are not prerequisites for normal operation or migration. They do not authorize
redistribution, access-control bypass, public raw-content logs, credentials, private personal data,
browser profiles, access-controlled material or uploaded decrypted artifacts. See
[the evidence documentation](docs/EVIDENCE_CAPTURE.md#legacy-encrypted-custody-497).

The default implementation stores artifact bytes by SHA-256 beneath the Git-ignored
`data/snapshots/` directory and writes metadata-only manifests beneath
`data/manifests/evidence/`. Manifests use relative content addresses rather than machine-specific
absolute paths. Manual transcriptions are stored separately under `data/review/manual/` and must
reference a verified capture.

Official-authority artifacts — election results published by a counting authority — are the one
class whose plaintext bytes are committed, beneath `data/evidence/official/`. They are
public records, so the paragraph above's prohibitions do not reach them, and committing them is
what keeps them from dying with the session that captured them. `docs/COLLECTION.md` records the
decision and its rationale.

Collection must not bypass authentication, paywalls, robots controls, or other access controls.
An inaccessible source receives an explicit status and may enter the manual review path.

## Prospective access limitations (#589, partial approved milestone)

Scott approved retaining accepted endorsements after a **pure access failure following a
complete accepted initial official-publication and mapping review**, with an explicit limitation.
The schema-1.1 verification policy applies this default only to new observations for Pacific
slots from October 27, 2026. Current weekly/daily frequencies, calendar boundaries, normal
automatic attempts and three-distinct-failed-slot escalation are unchanged. #589 remains open
for its unapproved interval/configuration and other remaining criteria.

A complete initial review uses one explicit immutable `source-reviews` attestation in the
existing verification archive: exact election/source, complete official-publication/mapping
scope, official URLs, actual original check time, original reviewer/review time and an ordinary
durable reference to the existing facts/review packet. Record the new writing actor/time
separately. Normal protected versioned review establishes acceptance. Existing facts/review
packets may use their ordinary durable reference formats.
Normal protected review establishes that the explicit publication URLs belong to the registered
source. An official embedded guide, social account, separate publication host or `www` alias
need not share the organization's homepage host; hostname equality cannot establish legitimacy.

A proposal is not authority merely because it exists on the pending archive branch. Before a
new failed check can use it, its exact bytes must exist in the normal canonical archive path
in the already available local `origin/main` snapshot. No fetch is performed; unavailable or
different admitted bytes leave the obligation unresolved. The normal workflow already fetches
and incorporates main. Structural archive validation permits a pending proposal without treating
it as accepted. Later ref availability never backfills an old check.

Completeness is an explicit assertion assessed through normal protected review, never inferred
from a generic acknowledgement, HTTP 200, extractor `complete` flag, baseline approval, partial
supplied snapshot or fixture. Do not attest incomplete or unsupported review scope. Missing actual
review evidence stays unresolved; heterogeneous formatting alone does not disqualify it. This
change creates no production attestations or retrospective source approvals.

Only a failed HTTP-fetch observation with a typed HTTP 401/403/408/429/500/502/503/504,
deadline, DNS or TLS diagnostic can use this disposition. HTTP 404/410, response-integrity,
redirect/access-safety, generic network/OS errors, unknown diagnostics, parser/incomplete
publications and new/conflicting evidence remain unresolved. Successful partial responses
never become access failures. A known intervening changed publication or unclassified/content
failure requires a later complete review before another access limitation may be handled.

The permitted disposition is stored on the **new failed check**, referencing the qualification
and policy fingerprint already in force. Reconciliation never derives one for an old check from
a later policy or qualification. Retained facts stay unchanged; the failed status/event, actual
last success, latest attempt, freshness limitation, normal next attempt, counts and escalation
remain distinct. This is not fresh verification, a withdrawal, collector-baseline adoption,
release approval or permission to bypass access controls. No accepted deployment is taken down.
The normal publication gates and pending source-review work remain required.

An operator may resolve that finite dated access obligation after its other requirements pass.
Handled-only observations can be appended to an already closed daily task without reopening it;
new unresolved observations still reopen it. The reconciler does not automatically close whole
tasks. Earlier dated SEIU exceptions/closures and #616 recovery remain separately scoped and
are not granted by this future policy.

Source discovery uses four preregistration states: `published`, `not_found`,
`not_an_endorsement_publisher`, and `access_restricted`. These describe publication discovery,
not a source's decision in any race. In particular, `not_found` must never be normalized as an
explicit no-endorsement claim.

## Changes and history

Never overwrite historical captures. A refresh creates a new capture and a semantic diff.
Removed or changed endorsements remain auditable through prior manifests and factual snapshots.
For observed-only history, this preserves the recorded facts and provenance rather than an old page.
