"""Cloudflare Pages staging tests."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest
import yaml
from typer.testing import CliRunner

from election_guide.cli import app
from election_guide.hosting import stage_pages_site
from election_guide.release.models import REQUIRED_RELEASE_ARTIFACTS, ReleaseStatus
from election_guide.serialization import canonical_json_bytes

COMMIT = "a" * 40
PROJECT_ROOT = Path(__file__).parents[1]


def test_stage_pages_site_publishes_only_verified_public_assets(tmp_path: Path) -> None:
    bundle = _write_release_bundle(tmp_path)
    output = tmp_path / "site"
    output.mkdir()
    (output / "stale.txt").write_text("old deployment", encoding="utf-8")

    result = stage_pages_site(bundle, output, expected_git_commit=COMMIT)

    assert result.output_dir == output
    assert result.release_version == "test.1"
    assert result.git_commit == COMMIT
    assert (output / "index.html").read_bytes() == b"<!doctype html><title>Guide</title>\n"
    assert (output / "Seattle_Primary_Guide.pdf").read_bytes() == b"%PDF-1.7\n"
    assert not (output / "stale.txt").exists()
    assert "X-Frame-Options: DENY" in (output / "_headers").read_text(encoding="utf-8")
    assert (output / "release-status.json").is_file()
    deployment = json.loads((output / "deployment-manifest.json").read_text(encoding="utf-8"))
    assert deployment["release_version"] == "test.1"
    assert deployment["git_commit"] == COMMIT
    assert set(deployment["assets"]) == {
        "Seattle_Primary_Guide.pdf",
        "_headers",
        "index.html",
        "release-status.json",
    }


def test_stage_pages_site_rejects_tampered_release_without_replacing_output(
    tmp_path: Path,
) -> None:
    bundle = _write_release_bundle(tmp_path)
    output = tmp_path / "site"
    output.mkdir()
    (output / "sentinel.txt").write_text("keep", encoding="utf-8")
    (bundle / "guide/guide.html").write_text("tampered", encoding="utf-8")

    with pytest.raises(ValueError, match=r"artifact hash mismatch: guide/guide\.html"):
        stage_pages_site(bundle, output, expected_git_commit=COMMIT)

    assert (output / "sentinel.txt").read_text(encoding="utf-8") == "keep"


def test_stage_pages_site_rejects_release_from_another_revision(tmp_path: Path) -> None:
    bundle = _write_release_bundle(tmp_path)

    with pytest.raises(ValueError, match="built from a different Git commit"):
        stage_pages_site(bundle, tmp_path / "site", expected_git_commit="b" * 40)


def test_hosting_stage_cli_reports_a_staged_site(tmp_path: Path) -> None:
    bundle = _write_release_bundle(tmp_path)
    output = tmp_path / "site"

    result = CliRunner().invoke(
        app,
        [
            "hosting",
            "stage",
            str(bundle),
            "--output-dir",
            str(output),
            "--expected-git-commit",
            COMMIT,
        ],
    )

    assert result.exit_code == 0, result.output
    assert f"Pages site: {output}" in result.output
    assert (output / "index.html").is_file()


def test_wrangler_and_workflow_keep_deployment_pinned_and_gated() -> None:
    wrangler = json.loads((PROJECT_ROOT / "wrangler.jsonc").read_text(encoding="utf-8"))
    package = json.loads((PROJECT_ROOT / "package.json").read_text(encoding="utf-8"))
    workflow = yaml.load(
        (PROJECT_ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8"),
        Loader=yaml.BaseLoader,
    )

    assert wrangler["name"] == "seattle-elections"
    assert wrangler["pages_build_output_dir"] == "./dist/cloudflare-site"
    assert package["devDependencies"]["wrangler"] == "4.113.0"
    deploy = workflow["jobs"]["deploy"]
    assert deploy["needs"] == "check"
    assert deploy["environment"]["name"] == "production"
    assert deploy["concurrency"]["cancel-in-progress"] == "false"
    assert "vars.CLOUDFLARE_PAGES_ENABLED == 'true'" in deploy["if"]
    deploy_step = next(
        step for step in deploy["steps"] if step.get("name") == "Deploy production site"
    )
    assert deploy_step["env"] == {
        "CLOUDFLARE_ACCOUNT_ID": "${{ secrets.CLOUDFLARE_ACCOUNT_ID }}",
        "CLOUDFLARE_API_TOKEN": "${{ secrets.CLOUDFLARE_API_TOKEN }}",
    }
    check_steps = workflow["jobs"]["check"]["steps"]
    assert not any("secrets" in json.dumps(step) for step in check_steps)


def _write_release_bundle(tmp_path: Path) -> Path:
    bundle = tmp_path / "bundle"
    html_relative = "guide/guide.html"
    pdf_relative = "guide/Seattle_Primary_Guide.pdf"
    included = sorted(
        REQUIRED_RELEASE_ARTIFACTS
        | {
            html_relative,
            pdf_relative,
            "validation/rendering/pdf/pages/page-1.png",
            "validation/rendering/screenshots/desktop.png",
        }
    )
    for relative in included:
        if relative in {"release-manifest.json", "release-status.json"}:
            continue
        path = bundle / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        if relative == html_relative:
            path.write_bytes(b"<!doctype html><title>Guide</title>\n")
        elif relative == pdf_relative:
            path.write_bytes(b"%PDF-1.7\n")
        else:
            path.write_text(f"fixture for {relative}\n", encoding="utf-8")

    status = ReleaseStatus.model_validate(
        {
            "release_version": "test.1",
            "election_id": "test-election",
            "data_as_of": "2026-07-20T12:00:00Z",
            "generated_at": "2026-07-21T12:00:00Z",
            "git_commit": COMMIT,
            "source_count": 1,
            "captured_source_count": 1,
            "displayed_endorsement_count": 1,
            "unresolved_review_count": 0,
            "unresolved_high_severity_count": 0,
            "restricted_capture_count": 0,
            "source_access_failures": [],
            "incomplete_races": [],
            "validation_reports": {"publication": True, "rendering": True},
            "rendering_edition": "concise",
            "guide_html_artifact": html_relative,
            "guide_pdf_artifact": pdf_relative,
            "detailed_guide_pdf_artifact": None,
            "included_artifacts": included,
            "warnings": [],
        }
    )
    (bundle / "release-status.json").write_bytes(
        canonical_json_bytes(status.model_dump(mode="json"))
    )
    hashes = {
        path.relative_to(bundle).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(bundle.rglob("*"))
        if path.is_file()
    }
    (bundle / "release-manifest.json").write_bytes(
        canonical_json_bytes(
            {
                "schema_version": "1.0",
                "release_version": status.release_version,
                "generated_at": status.generated_at.isoformat(),
                "artifact_hashes": hashes,
            }
        )
    )
    return bundle
