# Complete meter preview implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox syntax for tracking.

**Goal:** Deploy an inspectable complete #598 rollback preview while production
and #618 remain held.

**Architecture:** Extend only opt-in PR preview composition. Existing build and
hosting APIs verify two exact-head local bundles; a temporary manifest gives
primary an ephemeral identity without changing published archives or pins.

**Tech Stack:** Existing Python CLI/Pydantic, GitHub Actions, Pages and pytest.

**Spec:** `docs/superpowers/specs/2026-10-24-complete-meter-preview-design.md`.

## Global constraints

- Actual accepted base is `e85f694f9a3fedfd96a7707a12bd8279ed5d93d7`.
- Preserve general929, primary538, data, interactions, historical archives and
  tracked primary.6 declaration. No numeric primary release is selected.
- Full primary preview is explicit opt-in, same-repo, open draft only; upload
  uses `pr-<number>` and existing noindex/teardown/credentials.
- Root alone owns final commit, full gates, review, PR, opt-in and deployment.
  No production merge/deployment or immutable archive publication.

## Review focus

- Opt-in absent: ordinary preview follows its existing published-primary path.
- Fork, closed or non-draft complete-preview request: cannot enter the deploy job.
- Wrong head or mismatched bundle: normal verification fails before upload.
- Temporary manifest: distinct unpublished identity, both actual hashes, no
  tracked declaration or old archive mutation.
- CSS transfer: old browser diagnostics and current data/interaction coverage
  survive; restored transitions use only the approved mechanism.

## Task 1: complete preview composition and exact restoration

**Files:** `.github/workflows/deploy-pr-preview.yml`, focused additions to
`tests/test_hosting.py` or a small executable preview regression file, the exact
two CSS paths in the spec, focused hunks in `tests/test_rendering.py`,
`docs/HOSTING.md` and `docs/RELEASE.md`. Use a small script only if executable
workflow composition cannot stay readable. No hosting/model/compiler API change.

**Interfaces:** Existing `release build` primary defaults; `stage_pages_site`
with both logical bundle assignments; `hosting verify` with the temporary
manifest and exact expected current Git commit. Primary identity is exactly
`preview-pr-<PR>-primary-<fullHEAD>`.

- [ ] Add a meaningful failing regression for explicit opt-in/draft isolation,
  exact-head dual composition and temporary declaration preservation; run it RED.
- [ ] Implement minimal workflow composition using existing APIs. Retain normal
  published-primary verification/path, credential boundaries and teardown.
- [ ] Restore only the approved two CSS bytes and original focused transition
  test hunks; leave every newer diagnostic/test intact.
- [ ] Amend hosting/release documentation only for this unpublished preview
  composition, preserving merged-source publication and production rules.
- [ ] Run focused workflow/hosting/rendering regressions GREEN. Report exact
  diff, preservation and limitations; do not commit, build, publish or run full
  gates while the root is still finalizing the declaration.

## Task 2: root finalization, review and preview delivery

- [ ] Fresh task spec/quality reviews; fix actual findings before finalization.
- [ ] Add accurate preview/preparation Updates entries for each affected
  election, preserving every earlier byte and making no production claim.
  Normally prepare current-general request for #598, commit all final files,
  then run one complete `make check` on that clean committed head. No mid-gate
  edits or redundant same-head full runs.
- [ ] Push and create/attach an explicitly non-mergeable draft PR after those
  checks, obtaining its actual number for the ephemeral primary identity. Do
  not opt in to deployment yet. This draft cannot authorize production.
- [ ] Build/verify both exact-head local bundles, stage and independently verify
  the temporary complete preview. Inspect notes,7DATA/6RENDER and PNGs. Run
  live Updates comparison and fresh complete canonical three-lens review;
  preserve its actual budget. Opt in only after these pass. Existing publication
  checks must remain fail-closed if historical production prerequisites are
  absent; no production readiness claim follows from preview success.
- [ ] Verify the actual deployed alias/source/assets and desktop/mobile general
  and rebuilt primary surfaces; send URL/exact commit/limits to oversight.
  Keep #618 and all production held pending Scott's inspection.
