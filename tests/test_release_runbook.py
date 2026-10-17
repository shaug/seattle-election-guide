"""Executable release preparation and recovery commands cannot drift (#550)."""

from pathlib import Path

PROJECT_ROOT = Path(__file__).parents[1]


def _marked_bash(document: Path, marker: str) -> str:
    text = document.read_text(encoding="utf-8")
    opening = f"<!-- runbook-command:{marker} -->\n```bash\n"
    start = text.index(opening) + len(opening)
    return text[start : text.index("\n```", start)]


def test_general_release_verification_command_cannot_drift() -> None:
    assert (
        _marked_bash(PROJECT_ROOT / "docs/RELEASE.md", "verify-general")
        == """make release-verify
make check-release-reproducible
uv run election-guide release automation resolve > dist/resolved.json
unzip -t "dist/reproducibility-a/$(jq -r .archive_name dist/resolved.json)"
test -f dist/reproducibility-a/bundle/RELEASE_NOTES.md
test -f dist/reproducibility-a/bundle/validation/rendering/rendering_validation_report.json
test -f dist/reproducibility-a/bundle/validation/rendering/screenshots/desktop.png
test -f dist/reproducibility-a/bundle/validation/rendering/screenshots/mobile.png"""
    )


def test_release_lineage_command_cannot_drift() -> None:
    assert (
        _marked_bash(PROJECT_ROOT / "docs/RELEASE.md", "verify-lineage")
        == """uv run election-guide release verify-lineage \\
  dist/downloaded/seattle-election-guide-2026-general.9.zip \\
  dist/reproducibility-a/bundle \\
  "$release_candidate_sha" \\
  "$production_candidate_sha" \\
  > dist/release-lineage-report.json"""
    )


def test_preparation_and_recovery_commands_cannot_drift() -> None:
    document = PROJECT_ROOT / "docs/RELEASE.md"
    assert (
        _marked_bash(document, "prepare")
        == """uv run election-guide release automation prepare --issue "$issue_number"
uv run election-guide release automation resolve"""
    )
    assert (
        _marked_bash(document, "recover-candidate")
        == 'gh workflow run ci.yml --ref main -f source_sha="$source_sha"'
    )
    assert (
        _marked_bash(document, "retry-evidence")
        == '''gh workflow run verify-release.yml --ref main \\
  -f issue="$issue_number" \\
  -f release_version="$release_version" \\
  -f source_sha="$source_sha" \\
  -f run_id="$run_id" \\
  -f run_attempt="$run_attempt"'''
    )


def test_two_election_staging_command_cannot_drift() -> None:
    assert (
        _marked_bash(PROJECT_ROOT / "docs/RELEASE.md", "stage-candidate")
        == '''source_sha="$(git rev-parse HEAD)"
make hosting-stage
uv run election-guide hosting verify \\
  config/hosting/site.yaml \\
  dist/cloudflare-site \\
  --expected-git-commit "$source_sha"'''
    )


def test_read_only_production_probe_command_cannot_drift() -> None:
    assert (
        _marked_bash(PROJECT_ROOT / "docs/HOSTING.md", "production-probe")
        == """uv run election-guide hosting check-production \\
  https://seattleelections.guide \\
  --site-manifest config/hosting/site.yaml \\
  --expected-git-commit "$source_sha" \\
  --wait \\
  --output dist/production-probe.json"""
    )


def test_runbooks_retire_direct_upload_and_preserve_evidence_contract() -> None:
    text = (PROJECT_ROOT / "docs/RELEASE.md").read_text() + (
        PROJECT_ROOT / "docs/HOSTING.md"
    ).read_text()
    for command in ["gh release create", "gh release upload", "npm run pages:deploy"]:
        assert command not in text
    for term in [
        "release asset digest",
        "CI run and artifact",
        "deployment ID",
        "source_sha",
        "production-wait.json",
        "verification-only",
        "queue: max",
        "deployment_paused",
        "superseded",
    ]:
        assert term in " ".join(text.split())


def test_hosting_runbook_describes_candidate_before_automatic_publication() -> None:
    text = " ".join((PROJECT_ROOT / "docs/HOSTING.md").read_text().split())
    assert "Publish first:" not in text
    assert "Pull request CI validates the current candidate read-only" in text
    assert "After merge, CI automatically publishes" in text
    assert "every historical election must still have a published, non-draft Release" in text
    assert "hosting verify-releases` again with no candidate option" in text
