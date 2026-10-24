"""Execute the opt-in PR preview composition with real, verified fixture bundles."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
from pathlib import Path
from typing import Any

import pytest
import yaml

from election_guide.hosting import bundle_hash, verify_staged_pages_site
from tests.test_hosting import (  # pyright: ignore[reportPrivateUsage]
    COMMIT,
    PANEL_HASH,
    PROJECT_ROOT,
    REGISTRY_HASH,
    _workflow_staging_surfaces,  # pyright: ignore[reportPrivateUsage]
    _write_release_bundle,  # pyright: ignore[reportPrivateUsage]
)

PRIMARY_VERSION = f"preview-pr-598-primary-{COMMIT}"
PRIMARY_BUILD = "Build an unpublished primary preview at the pull request head"
COMPLETE_STAGE = "Stage and verify both head-built preview bundles"
ORDINARY_STAGE = "Stage and verify the Pages site"


def _deploy_job() -> dict[str, Any]:
    workflow = yaml.safe_load(
        (PROJECT_ROOT / ".github/workflows/deploy-pr-preview.yml").read_text(encoding="utf-8")
    )
    return workflow["jobs"]["deploy"]


def test_complete_preview_remains_in_staging_surface_inventory() -> None:
    assert any("stage_pages_site(" in surface.command for surface in _workflow_staging_surfaces())


@pytest.mark.parametrize(
    ("draft", "complete", "same_repo", "state", "enabled", "deploy_label", "wanted"),
    [
        (True, False, True, "open", "true", True, [ORDINARY_STAGE]),
        (False, False, True, "open", "true", True, [ORDINARY_STAGE]),
        (True, True, True, "open", "true", True, [PRIMARY_BUILD, COMPLETE_STAGE]),
        (False, True, True, "open", "true", True, []),
        (True, True, False, "open", "true", True, []),
        (True, True, True, "closed", "true", True, []),
        (True, True, True, "open", "false", True, []),
        (True, True, True, "open", "true", False, []),
    ],
)
def test_complete_preview_admission_and_default_path(
    draft: bool,
    complete: bool,
    same_repo: bool,
    state: str,
    enabled: str,
    deploy_label: bool,
    wanted: list[str],
) -> None:
    """A missing draft guard or wrong opt-in branch selects the wrong executable steps."""
    labels = (["deploy preview"] if deploy_label else []) + (
        ["preview primary from source"] if complete else []
    )
    context = {
        "repository": "owner/guide",
        "event": {
            "pull_request": {
                "state": state,
                "draft": draft,
                "head": {"repo": {"full_name": "owner/guide" if same_repo else "fork/guide"}},
                "labels": [{"name": label} for label in labels],
            }
        },
    }
    job = _deploy_job()
    # GitHub's label wildcard is projected before evaluating these boolean
    # expressions. Run the real job and step conditions with concrete contexts.
    script = """
const [job, github, vars, labels] = JSON.parse(process.argv[1]);
const contains = (values, value) => values.includes(value);
const evaluate = expression => Function('github', 'vars', 'labels', 'contains',
  `return (${expression.replaceAll('github.event.pull_request.labels.*.name', 'labels')})`
)(github, vars, labels, contains);
const selected = evaluate(job.if) ? job.steps.filter(step =>
  !step.if || evaluate(step.if)
).map(step => step.name) : [];
process.stdout.write(JSON.stringify(selected));
"""
    result = subprocess.run(
        [
            "node",
            "-e",
            script,
            json.dumps([job, context, {"CLOUDFLARE_PAGES_ENABLED": enabled}, labels]),
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    selected = json.loads(result.stdout)
    assert [
        name for name in selected if name in {PRIMARY_BUILD, COMPLETE_STAGE, ORDINARY_STAGE}
    ] == (wanted)


def _preview_fixture(root: Path, *, primary_commit: str = COMMIT) -> tuple[Path, Path, bytes]:
    """Retain a pinned primary declaration while supplying two fresh local bundles."""
    manifest = yaml.safe_load((PROJECT_ROOT / "config/hosting/site.yaml").read_text())
    general = manifest["elections"][0]
    general.update(
        source_panel_id="test-panel-v2",
        source_panel_hash=PANEL_HASH,
        source_registry_hash=REGISTRY_HASH,
        publication_request=None,
        git_commit=None,
        release_manifest_sha256=None,
        bundle_sha256=None,
    )
    config = root / "config/hosting/site.yaml"
    config.parent.mkdir(parents=True)
    config.write_text(yaml.safe_dump(manifest, sort_keys=False), encoding="utf-8")
    calendar = root / "config/calendar/elections.yaml"
    calendar.parent.mkdir(parents=True)
    shutil.copyfile(PROJECT_ROOT / "config/calendar/elections.yaml", calendar)
    original_bytes = config.read_bytes()
    general_bundle = _write_release_bundle(
        root / "dist/reproducibility-a",
        election_id="wa-2026-general",
        release_version=general["release_version"],
        git_commit=COMMIT,
        html=b"<title>Fresh general overview</title>\n",
        source_registry_hash=REGISTRY_HASH,
    )
    primary_bundle = _write_release_bundle(
        root / "dist/primary-preview",
        election_id="wa-2026-primary",
        release_version=PRIMARY_VERSION,
        git_commit=primary_commit,
        html=b"<title>Fresh primary overview from this head</title>\n",
        source_registry_hash=REGISTRY_HASH,
    )
    return general_bundle, primary_bundle, original_bytes


def _run_complete_stage(root: Path) -> subprocess.CompletedProcess[str]:
    steps = _deploy_job()["steps"]
    matching = [step for step in steps if step.get("name") == COMPLETE_STAGE]
    assert len(matching) == 1, "complete-preview composition step is missing"
    return subprocess.run(
        ["bash", "-e", "-o", "pipefail"],
        input=matching[0]["run"],
        cwd=root,
        env={**os.environ, "UV_PROJECT": str(PROJECT_ROOT), "HEAD_SHA": COMMIT, "PR_NUMBER": "598"},
        capture_output=True,
        text=True,
    )


def test_complete_preview_composes_both_local_heads_without_changing_declared_release(
    tmp_path: Path,
) -> None:
    general, primary, original = _preview_fixture(tmp_path)
    result = _run_complete_stage(tmp_path)
    assert result.returncode == 0, result.stdout + result.stderr
    assert (tmp_path / "config/hosting/site.yaml").read_bytes() == original
    preview_path = tmp_path / "dist/preview-site.yaml"
    preview = yaml.safe_load(preview_path.read_text())
    original_config = yaml.safe_load(original)
    assert preview["elections"][0] == original_config["elections"][0]
    assert preview["elections"][1]["release_version"] == PRIMARY_VERSION
    assert preview["elections"][1]["bundle_id"] == f"wa-2026-primary-{PRIMARY_VERSION}"
    assert preview["elections"][1]["git_commit"] == COMMIT
    assert preview["elections"][1]["source_panel_hash"] == PANEL_HASH
    assert preview["elections"][1]["source_registry_hash"] == REGISTRY_HASH
    assert (
        preview["elections"][1]["release_manifest_sha256"]
        == hashlib.sha256((primary / "release-manifest.json").read_bytes()).hexdigest()
    )
    assert preview["elections"][1]["bundle_sha256"] == bundle_hash(primary)
    site = tmp_path / "dist/cloudflare-site"
    for election, bundle in [("wa-2026-general", general), ("wa-2026-primary", primary)]:
        assert (site / "e" / election / "index.html").read_bytes() == (
            bundle / "guide/guide.html"
        ).read_bytes()
        assert (
            json.loads((site / "e" / election / "release-status.json").read_text())["git_commit"]
            == COMMIT
        )
    verify_staged_pages_site(site, preview_path, expected_current_git_commit=COMMIT)


@pytest.mark.parametrize("fault", ["stale-source", "missing-primary", "mismatched-hash"])
def test_complete_preview_rejects_bad_local_primary_before_staging(
    tmp_path: Path, fault: str
) -> None:
    _, primary, original = _preview_fixture(
        tmp_path, primary_commit="c" * 40 if fault == "stale-source" else COMMIT
    )
    if fault == "missing-primary":
        shutil.rmtree(primary)
    elif fault == "mismatched-hash":
        (primary / "guide/guide.html").write_text("<title>unverified change</title>")
    output = tmp_path / "dist/cloudflare-site"
    output.mkdir()
    sentinel = output / "previous-site.txt"
    sentinel.write_text("keep previous output")

    result = _run_complete_stage(tmp_path)

    assert result.returncode != 0
    assert (tmp_path / "config/hosting/site.yaml").read_bytes() == original
    assert sentinel.read_text() == "keep previous output"
    assert not (output / "deployment-manifest.json").exists()
    expected_error = {
        "stale-source": "Git commit differs",
        "missing-primary": "release-status.json",
        "mismatched-hash": "hash",
    }[fault]
    assert expected_error in result.stderr, result.stdout + result.stderr
