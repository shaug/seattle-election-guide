"""Drift checks for the general-release commands changed by issue #448."""

from pathlib import Path

PROJECT_ROOT = Path(__file__).parents[1]


def _marked_bash(document: Path, marker: str) -> str:
    text = document.read_text(encoding="utf-8")
    opening = f"<!-- runbook-command:{marker} -->\n```bash\n"
    start = text.index(opening) + len(opening)
    end = text.index("\n```", start)
    return text[start:end]


def test_general_release_verification_command_cannot_drift() -> None:
    command = _marked_bash(PROJECT_ROOT / "docs" / "RELEASE.md", "verify-general")

    assert (
        command
        == """make release-verify
make check-release-reproducible
unzip -t dist/reproducibility-a/seattle-election-guide-2026-general.2.zip
test -f dist/reproducibility-a/bundle/RELEASE_NOTES.md
test -f dist/reproducibility-a/bundle/validation/rendering/rendering_validation_report.json
test -f dist/reproducibility-a/bundle/validation/rendering/screenshots/desktop.png
test -f dist/reproducibility-a/bundle/validation/rendering/screenshots/mobile.png"""
    )


def test_release_lineage_command_cannot_drift() -> None:
    command = _marked_bash(PROJECT_ROOT / "docs" / "RELEASE.md", "verify-lineage")

    assert (
        command
        == """uv run election-guide release verify-lineage \\
  dist/downloaded/seattle-election-guide-2026-general.2.zip \\
  dist/reproducibility-a/bundle \\
  "$release_candidate_sha" \\
  "$production_candidate_sha" \\
  > dist/release-lineage-report.json"""
    )


def test_github_release_preflight_command_cannot_drift() -> None:
    command = _marked_bash(PROJECT_ROOT / "docs" / "RELEASE.md", "release-preflight")

    assert (
        command
        == """git ls-remote --tags origin refs/tags/2026-general.2 refs/tags/2026-general.2^{}
gh release view 2026-general.2 \\
  --json url,tagName,targetCommitish,isDraft,isPrerelease,name,body,assets"""
    )


def test_github_release_create_command_cannot_drift() -> None:
    command = _marked_bash(PROJECT_ROOT / "docs" / "RELEASE.md", "release-create")

    assert (
        command
        == '''gh release create 2026-general.2 \\
  dist/reproducibility-a/seattle-election-guide-2026-general.2.zip \\
  --title "Seattle 2026 general election endorsement guide — 2026-general.2" \\
  --notes-file dist/reproducibility-a/bundle/RELEASE_NOTES.md \\
  --target "$release_candidate_sha"'''
    )


def test_existing_github_release_upload_command_cannot_drift() -> None:
    command = _marked_bash(PROJECT_ROOT / "docs" / "RELEASE.md", "release-upload")

    assert (
        command
        == """gh release upload 2026-general.2 \\
  dist/reproducibility-a/seattle-election-guide-2026-general.2.zip"""
    )


def test_published_asset_verification_command_cannot_drift() -> None:
    command = _marked_bash(PROJECT_ROOT / "docs" / "RELEASE.md", "verify-published-asset")

    assert (
        command
        == '''mkdir -p dist/downloaded
test ! -e dist/downloaded/seattle-election-guide-2026-general.2.zip
gh release download 2026-general.2 \\
  --pattern seattle-election-guide-2026-general.2.zip \\
  --dir dist/downloaded
local_release_digest="$(shasum -a 256 \\
  dist/reproducibility-a/seattle-election-guide-2026-general.2.zip | awk '{print $1}')"
downloaded_release_digest="$(shasum -a 256 \\
  dist/downloaded/seattle-election-guide-2026-general.2.zip | awk '{print $1}')"
test "$local_release_digest" = "$downloaded_release_digest"
unzip -t dist/downloaded/seattle-election-guide-2026-general.2.zip
git fetch origin tag 2026-general.2
test "$(git rev-parse '2026-general.2^{commit}')" = "$release_candidate_sha"'''
    )


def test_two_election_staging_command_cannot_drift() -> None:
    command = _marked_bash(PROJECT_ROOT / "docs" / "RELEASE.md", "stage-candidate")

    assert (
        command
        == '''make hosting-stage
uv run election-guide hosting verify \\
  config/hosting/site.yaml \\
  dist/cloudflare-site \\
  --expected-git-commit "$production_candidate_sha"'''
    )


def test_read_only_production_probe_command_cannot_drift() -> None:
    command = _marked_bash(PROJECT_ROOT / "docs" / "HOSTING.md", "production-probe")

    assert (
        command
        == """uv run election-guide hosting check-production \\
  https://seattleelections.guide \\
  --site-manifest config/hosting/site.yaml \\
  --expected-git-commit "$production_candidate_sha" \\
  --dry-run \\
  --output dist/production-probe.json"""
    )


def test_runbook_names_the_complete_publication_evidence_and_expiry_rule() -> None:
    release = (PROJECT_ROOT / "docs" / "RELEASE.md").read_text(encoding="utf-8")
    hosting = (PROJECT_ROOT / "docs" / "HOSTING.md").read_text(encoding="utf-8")
    text = release + hosting
    normalized_text = " ".join(text.split())

    for evidence_name in (
        "release_candidate_sha",
        "production_candidate_sha",
        "release asset digest",
        "CI run and artifact",
        "deployment ID",
        "production-probe.json",
    ):
        assert evidence_name in text
    assert "rerun CI for that exact `production_candidate_sha`" in normalized_text
    assert "Never substitute the newer `main` head" in normalized_text
