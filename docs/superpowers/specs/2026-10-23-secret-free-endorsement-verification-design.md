# Secret-free endorsement verification

Scope: [#497](https://github.com/shaug/seattle-election-guide/issues/497).

## Accepted product decision

On October 23 the maintainer explicitly chose endorsement facts, official URL, actual check date and actual reviewer as sufficient durable evidence. Full historical source pages and later reconstruction of them are not requirements. Plan the secret-free implementation and update #497 accordingly. This does not approve previously unreviewed facts or make the implementation/adoption complete.

## Required guarantees

Keep reviewed endorsement facts and their official source URLs, actual check timestamps and reviewer attestations in ordinary versioned JSON. Preserve the current six-source automatic tranche and the 46-source frozen-panel coverage record. Source discovery, parser/completeness checks, failed/missed checks, three-failure escalation, manual due tasks and idempotent daily routing remain. Publication/withdrawal interpretation and ledger edits still require review. No cadence, source, scoring, UI or access-boundary change is implied.

A source observation records what was fetched and when: clean requested/canonical official URLs, actual HTTP metadata when observed, content hash/size and extractor identity. Existing extraction snapshots hold the factual decisions; existing approvals hold the named reviewer and actual review time. Join these records rather than copying a human name onto every automated check. An unchanged automated check references the approved factual baseline; it does not claim that reviewer personally re-read the page that day. A changed or first unreviewed baseline remains review work. Every successful fetch writes a new observed-only manifest, including unchanged bytes, so the current URL, actual retrieval time and HTTP metadata remain available. An unchanged event references this current observation while reusing the prior factual snapshot and approval; validate their common source/content-hash join. A parse failure after a successful fetch retains its available observation without promoting a baseline.

## Chosen approach and alternatives

Use the existing Git-backed manifests, extractions, events, checks and approvals. Introduce one explicit metadata-only observation manifest for future recurring checks. Fetch/parse original responses in private temporary storage and discard them at transaction end. Keep hashes for comparison/integrity; a hash does not recover a historical page or prove the publisher authored a claim. Trust stays in official-source review and the protected repository workflow.

Remove evidence-key reads, archive decryption and new ciphertext creation from normal verification, validation, reconciliation, baseline review and independent scheduled reuse. No replacement secret, evidence service, database, signature framework or encrypted backup system is needed. Existing GitHub job/App authentication for writes and deployment credentials remain outside this evidence-key scope.

Keeping raw pages in another private store would retain the availability/credential dependency. Publishing complete third-party pages would conflict with the repository's public-content boundary. Both add guarantees the maintainer has declined. The selected factual-record approach matches the accepted evidence need.

## Narrow implementation boundary

Preserve the existing `CapturedManifest` model and its serialization/ID rules. Add an `ObservedManifest` with `availability: observed`, source/request metadata, content SHA-256 and byte length, its identified record hash, and no retained artifact/storage reference. Extend the existing manifest reader explicitly; byte-verification/manual-transcription paths must continue to distinguish observed facts from retained original bytes.

Reuse the shared refresh operation with an explicit retention choice, defaulting to its current retained-original contract for unrelated callers. Recurring verification selects `facts_only`. Its baseline integrity checks validate identified public manifests/snapshots/approvals and their source/hash references without opening previous raw bytes. Existing adapters, semantic comparison and immutable writers remain the implementation. Do not fork six new collectors or change matching/scoring behavior.

Thread the same explicit retention choice through existing composite/index collectors so observations are created with truthful identities at collection time. Keep all URLs, article/body/image fingerprints, remembered article membership and incomplete-discovery failures. Re-fetch current required articles; historical raw bodies are not necessary to compare their public fingerprints. Never turn absent/unclassified articles or a failed parser into successful zero diff. SGN must also remember newly learned story URLs before required article work can fail, using the existing durable discovery-obligation pattern. A URL discovered during a failed run remains required after it rotates off the index; normal validation dispatches SGN obligations to its own explicit reader, alongside existing UFCW/TRU readers.

## Migration and history

Keep all existing committed records, approvals, ciphertext and release artifacts unchanged. Legacy public metadata remains readable and schema/reference validated without decrypting its original. Explicit legacy restore/seal commands may remain available for historical use, but are never on the normal new verification path. Existing retained-artifact manual-transcription consumers explicitly reject observed-only records; that compatibility boundary does not add an original-page requirement to the new factual-baseline approval path. Do not remove or rotate the existing secret in this change; simply remove its workflow/runtime dependency. Do not require it to complete migration.

Reuse valid existing factual approvals for precisely the facts/revision they reviewed. New/changed/unapproved facts require actual official-source review with the named human or explicitly delegated reviewer and a real review timestamp. Do not promote old unapproved snapshots, invent original-page review, relabel historical failures, reset failure counters or manufacture scheduled checks. Previously accepted WFP review/reuse remains accepted progress; demonstrate the deployed new runtime's key-free operation separately.

## Acceptance and delivery

With `ENDORSEMENT_EVIDENCE_KEY` absent and no restored historical pages, fixture tests must prove all normal operations and a fresh-runner baseline reuse work. Retain tests for additions, changes, removals, new articles, article-only edits, missing known articles, unsafe URLs, parser/fetch failure, missing slots and concurrent/same-day reconciliation. Test that no new vault entries/full pages/credentials appear in Git or outputs. Test actual reviewer/date separation and unchanged legacy bytes.

Ship runtime, workflow, policy and operator documentation together through normal gates/fresh review/protected publication. Keep the runbook proposed until real due-source scheduled execution and later independent reuse of approved factual baselines are evidenced. A fixture, operator dispatch, no-due success or green release cannot substitute. Resolve actual SEIU failures or document an explicitly approved coverage decision; do not silently shrink the tranche. Confirm all 46 source lanes and finite manual due tasks, including honest access limitations. Then publish the finite adoption record and mark the runbook adopted/close #497 through the normal reviewed process.

Historical full-page reconstruction is deliberately not promised. Current content is fetched solely for legitimate collection/review; access restrictions and bounds remain enforced. No new public UI or automatic endorsement judgment is included.
