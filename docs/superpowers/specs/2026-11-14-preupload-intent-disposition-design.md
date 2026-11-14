# Preserve and resolve a proved pre-upload intent (#757)

General124's managed GitHub deployment intent was created before Wrangler failed
on a project-metadata GET in its pre-upload path. Both possible lookup sites in
the pinned normal invocation precede resource writes; the retained report does
not identify which lookup threw. The report remains failed/uncertain and is not
a successful upload receipt. Current admission treats every intent as a possible
upload and therefore has no supported resolution for this proved case.

## Constraints

Preserve the original deployment object, negative artifact, reports, producer,
canonical release/tag/asset/archive and last accepted production. Do not change
election facts, rendering, credentials, original source bytes or check policy.
Unknown or actual resource writes continue to require successful-upload evidence
and verification-only recovery. Selected provider metadata is corroboration,
not a complete historical inventory or proof of no deleted deployments.

## Approaches

Moving intent creation after metadata preflight would prevent some future stuck
intents, but does not resolve an existing admitted intent and cannot make an
uncertain upload safe. Deleting an intent or reusing it with another producer
would lose evidence or misstate identity. The selected approach is a separate,
authenticated **pre-upload disposition**, followed by the normal guarded upload
of the correction's legitimately selected fresh release under its own producer
and intent. General124 may remain unshipped and superseded; its original archive
identity is retained and must never be described as accepted production.

This is an application invariant correction through its ordinary reviewed
delivery path. It does not override platform or provider permissions.

## Proof and durable disposition

Add a distinct typed disposition report, carried by the existing authenticated
negative evidence framing, separate from any successful UploadReceipt. Its
carrier remains a failed deployment receipt targeting the original source; the
disposition producer's workflow SHA/run identify the original correcting workflow,
not a claim that its CI lanes tested the old source. It binds the original publication, original producer and exact
managed deployment ID, authenticated failed artifact ID/name/wrapper digest,
whole failed-report digest, the audited uploader contract/classifier and the
trusted-main disposition producer. It expressly asserts pre-upload failure,
never upload success or protected production acceptance.

The caller may supply already-retained original artifact wrapper bytes; validate
them against current authenticated Actions metadata and producing-attempt
boundaries without downloading the artifact again. Extract only safe unique
regular members and verify the complete wrapper's hash/size/CRC. The old report
must match the original producer/source/deployment exactly; returncode must be
exactly1 for this normal failure, and there must be no upload.json or Pages URL. The original intent must
still match its durable publication and have no status suggesting an upload.
Reject any contradictory complete or partial upload evidence, duplicate matching
intents, conflicting dispositions or a later matching successful upload.

Support one explicitly audited classifier initially: the retained normal
Wrangler4.158.0 project-metadata GET503 failure. Bind the complete original source
tree `25653db793a25aaabdcc954410109775cf9cd371`, closing the entrypoint,
transitive imports, locked package identity, normal command and trusted workflow
installation/invocation. Five component blobs alone cannot close this boundary:
a changed caller could write before invoking an unchanged perform_upload. Validate
that complete Git-object contract before accepting its full output shape. Do not
infer pre-write safety from a generic nonzero exit, lack of a URL or arbitrary
GET text. Unsupported versions, scripts, output or paths fail closed. The
classifier's evidence basis and limits must be explicit in the runbook.

Transport the already-retained wrapper once as base64 in a reviewed operational
JSON request in this correction's Git tree, with its ArtifactRef and exact old
intent identity. It contains no credential or signed download URL. This is data
reuse, not another artifact download. Authenticate its metadata/attempt boundary
when recording the disposition, then retain the complete wrapper and metadata
attestation inside the existing sealed durable evidence reports. Reads validate
that durable proof without requiring a temporary artifact to remain available.
The complete metadata snapshot fits one existing evidence part and sorts first.
After an interrupted journal write, the recorder may complete only the exact
matching pending group under its original issuer, using that retained metadata
and the issuer's immutable reviewed request. All existing report parts must
match before any missing part is posted. Unrelated, conflicting or multiple
pending groups remain blocked; incomplete evidence never grants admission.
The admission consumer independently checks current original-intent ownership,
statuses, upload receipts and incomplete evidence groups for contradictions. A
historical source-proof journal entry alone grants no upload admission. Its
writer needs Actions/issue access, while the existing deployment job owns the
live deployment reads; preserve both existing permission maps. The original source contract is
read from immutable Git objects. A repeated identical operation is idempotent;
ambiguity or conflicting replay is rejected. Preserve the original negative
receipt and its wording. Keep the original deployment row in enumerations and
preserve the existing same-source admission/create guards unchanged. Only the
global unresolved-upload guard distinguishes a validated pre-upload disposition
from an unresolved possible upload. This path does not authorize another upload
of the disposed source. A real upload/partial upload record targeting the old
intent invalidates its disposition; verified uploads of the new correction's
different intent/source do not.

## Trusted-code bootstrap and upload

1. Deliver one draft correction PR against actual main. Source/workflow changes
   are release-affecting under declaration.py; use normal owning prepare and the
   actual complete catalog to select an unreserved fresh version and published
   predecessor. Keep election facts/rendering unchanged. Run the full required
   gate, exact-head CI, candidate inspection and independent canonical review
   before ordinary merge. Do not add an exemption to release admission.
2. The correction's normal main CI checks out and tests its actual merged
   source. Its existing whole-workflow verified-release-mainline concurrency
   group serializes publication, disposition and upload. Add the credential-free
   source-proof recording step to the existing publication-evidence job, whose
   successful completion is already required by deploy. The deployment job then
   performs fresh live-intent contradiction checks before global admission.
   Add no GitHub permission. There is no new workflow,
   manual uploader, duplicate watcher or old-source dispatch/rerun.
3. Validate and retain the pre-upload disposition using the reviewed retained
   negative wrapper. No Cloudflare credential or upload is available to this
   disposition step. Stop on any unproved or contradictory condition.
4. Continue the correction release's existing admission/Updates/canonical
   promotion checks and create its own normal intent. Its publication producer,
   upload producer and intent are the normal single producing CI attempt; no
   publication from an older run is relabeled or fetched through current-producer
   adapters. Preserve all old catalog objects, including published General124.
5. Invoke the normal pinned uploader once, with credentials only on that step.
   Preserve the new upload's exact producer and evidence separately from both
   earlier failures. Persist its actual receipt before status writes.
6. Finalize using the existing complete strict production probe pair, durable
   verification evidence and deployment-status rules. A failed/uncertain new
   upload is not automatically retried or classified safe.
7. Independently inspect the correction's public archive and actual production
   source/manifest/content, then reconcile issue/PR status and guard custody.
   General124 remains published-but-unshipped/superseded rather than accepted.
   Only afterward advance PR756 against the actual accepted predecessor.

## Verification

First show an offline regression failing at the base: a genuine authenticated
pre-upload disposition should permit a different normally admitted correction
release while preserving the old deployment/failure; current global admission
rejects it. Same-source second uploads remain rejected. Then demonstrate the complete
negative matrix: generic/late/nonzero failures; successful upload or receipt;
forged/mismatched source, producer, workflow, artifact/report/deployment; unsafe
ZIP; duplicate/ambiguous/conflicting disposition; contradictory statuses or
receipts; duplicate upload admission and another unresolved source.

Exercise the CLI/workflow boundaries and durable evidence round-trip with fixture
services. Run make check and all applicable normal candidate/release gates.
Use the installed repository review-fix-loop local_commit contract, all three
independent lenses plus aggregate, strict filesystem read-only reviewer isolation
and no reviewer messaging/delegation/network/provider/test/build activity. No
formal GitHub APPROVED review. Keep the issue open until post-merge deployment
and independent acceptance actually pass.
