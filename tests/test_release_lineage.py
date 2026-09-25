"""Release-to-deployment lineage verification at the supported CLI boundary."""

from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

import pytest
from typer.testing import CliRunner

from election_guide.cli import app
from election_guide.release.models import (
    REQUIRED_RELEASE_ARTIFACTS,
    UNHASHED_RASTERIZED_ARTIFACTS,
)


def test_release_verify_lineage_accepts_only_commit_bound_provenance_changes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repository, release_sha, production_sha, release_bundle, production_bundle = _lineage_fixture(
        tmp_path
    )
    published_archive = _archive_bundle(release_bundle, tmp_path / "published.zip")
    monkeypatch.chdir(repository)

    result = CliRunner().invoke(
        app,
        [
            "release",
            "verify-lineage",
            str(published_archive),
            str(production_bundle),
            release_sha,
            production_sha,
        ],
    )

    assert result.exit_code == 0, result.output
    report = json.loads(result.stdout)
    assert report["result"] == "pass"
    assert report["release_candidate_sha"] == release_sha
    assert report["production_candidate_sha"] == production_sha
    assert report["identities"]["election_id"] == "wa-2026-general"
    assert report["screenshots"] == {
        "paths": sorted(UNHASHED_RASTERIZED_ARTIFACTS),
        "treatment": "verified-present-unhashed-not-compared",
    }
    assert {item["artifact"] for item in report["normalized"]} >= {
        "RELEASE_NOTES.md",
        "data/build_manifest.json",
        "data/consensus.json",
        "data/provenance_manifest.json",
        "data/publication_view_model.json",
        "data/validation_report.json",
        "guide/guide.html",
        "release-manifest.json",
        "release-status.json",
    }


@pytest.mark.parametrize(
    "relative",
    [
        "data/canonical-dataset.json",
        "data/consensus.json",
        "data/endorsement_records.csv",
        "data/recommendations.json",
        "guide/template.html",
        "guide/styles.css",
        "guide/client.js",
        "guide/routes.json",
        "data/archive.json",
    ],
)
def test_release_verify_lineage_rejects_every_protected_content_class(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    relative: str,
) -> None:
    repository, release_sha, production_sha, release_bundle, production_bundle = _lineage_fixture(
        tmp_path
    )
    path = production_bundle / relative
    if relative == "data/canonical-dataset.json":
        payload = json.loads(path.read_text(encoding="utf-8"))
        payload["records"] = ["changed"]
        path.write_bytes(_json_bytes(payload))
    elif relative == "data/consensus.json":
        payload = json.loads(path.read_text(encoding="utf-8"))
        payload["input_hash"] = "8" * 64
        path.write_bytes(_json_bytes(payload))
    else:
        path.write_bytes(path.read_bytes() + b"changed\n")
    _rehash_release_manifest(production_bundle, relative)
    monkeypatch.chdir(repository)

    result = _invoke_lineage(
        release_bundle,
        production_bundle,
        release_sha,
        production_sha,
    )

    assert result.exit_code == 1
    report = json.loads(result.stdout)
    assert report["result"] == "fail"
    if relative == "data/canonical-dataset.json":
        expected = "canonical dataset"
    elif relative == "data/consensus.json":
        expected = "consensus"
    else:
        expected = relative
    assert any(expected in error for error in report["errors"])


def test_release_verify_lineage_rejects_unexpected_manifest_fields(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repository, release_sha, production_sha, release_bundle, production_bundle = _lineage_fixture(
        tmp_path
    )
    manifest_path = production_bundle / "release-manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["new_commit_bound_field"] = production_sha
    manifest_path.write_bytes(_json_bytes(manifest))
    monkeypatch.chdir(repository)

    result = _invoke_lineage(
        release_bundle,
        production_bundle,
        release_sha,
        production_sha,
    )

    assert result.exit_code == 1
    assert "Extra inputs are not permitted" in result.stdout


def test_release_verify_lineage_fails_closed_for_a_new_unallowlisted_normalized_field(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repository, release_sha, production_sha, release_bundle, production_bundle = _lineage_fixture(
        tmp_path
    )
    build_path = production_bundle / "data/build_manifest.json"
    build = json.loads(build_path.read_text(encoding="utf-8"))
    build["deployment_commit"] = production_sha
    build_path.write_bytes(_json_bytes(build))
    _rehash_release_manifest(production_bundle, "data/build_manifest.json")
    monkeypatch.chdir(repository)

    result = _invoke_lineage(
        release_bundle,
        production_bundle,
        release_sha,
        production_sha,
    )

    assert result.exit_code == 1
    report = json.loads(result.stdout)
    assert "release content differs: data/build_manifest.json" in report["errors"]


def test_release_verify_lineage_does_not_normalize_guide_tokens_outside_the_audit_footer(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repository, release_sha, production_sha, release_bundle, production_bundle = _lineage_fixture(
        tmp_path
    )
    for bundle, sha, generated_at in (
        (release_bundle, release_sha, "2026-10-16T16:00:00Z"),
        (production_bundle, production_sha, "2026-10-16T17:00:00Z"),
    ):
        guide_path = bundle / "guide/guide.html"
        guide_path.write_text(
            guide_path.read_text(encoding="utf-8")
            + (
                '<p class="copied-provenance">Site updated '
                f"{generated_at[:10]} /commit/{sha} {sha[:12]}</p>"
            ),
            encoding="utf-8",
        )
        _rehash_release_manifest(bundle, "guide/guide.html")
    monkeypatch.chdir(repository)

    result = _invoke_lineage(
        release_bundle,
        production_bundle,
        release_sha,
        production_sha,
    )

    assert result.exit_code == 1
    report = json.loads(result.stdout)
    assert "release content differs: guide/guide.html" in report["errors"]


@pytest.mark.parametrize("invalid_side", ["release", "production"])
def test_release_verify_lineage_rejects_an_invalid_bundle_before_comparison(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    invalid_side: str,
) -> None:
    repository, release_sha, production_sha, release_bundle, production_bundle = _lineage_fixture(
        tmp_path
    )
    invalid_bundle = release_bundle if invalid_side == "release" else production_bundle
    (invalid_bundle / "guide/client.js").write_bytes(b"tampered")
    monkeypatch.chdir(repository)

    result = _invoke_lineage(
        release_bundle,
        production_bundle,
        release_sha,
        production_sha,
    )

    assert result.exit_code == 1
    report = json.loads(result.stdout)
    assert report["errors"] == ["release artifact hash mismatch: guide/client.js"]
    assert report["compared_artifacts"] == []


def test_release_verify_lineage_rejects_undeclared_archive_content(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repository, release_sha, production_sha, release_bundle, production_bundle = _lineage_fixture(
        tmp_path
    )
    archive = _archive_bundle(release_bundle, tmp_path / "published.zip")
    with ZipFile(archive, "a", compression=ZIP_DEFLATED) as bundle:
        bundle.writestr("seattle-election-guide/undeclared.txt", "surprise\n")
    monkeypatch.chdir(repository)

    result = _invoke_lineage(archive, production_bundle, release_sha, production_sha)

    assert result.exit_code == 1
    assert "undeclared.txt" in result.stdout


@pytest.mark.parametrize("invalid_kind", ["abbreviated", "wrong", "unrelated", "reversed"])
def test_release_verify_lineage_rejects_invalid_candidate_identities(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    invalid_kind: str,
) -> None:
    repository, release_sha, production_sha, release_bundle, production_bundle = _lineage_fixture(
        tmp_path
    )
    supplied_release = release_sha
    supplied_production = production_sha
    if invalid_kind == "abbreviated":
        supplied_release = release_sha[:12]
    elif invalid_kind == "wrong":
        marker = repository / "marker"
        marker.write_text("later\n", encoding="utf-8")
        subprocess.run(["git", "commit", "-qam", "later"], cwd=repository, check=True)
        supplied_production = _git(repository, "rev-parse", "HEAD")
    elif invalid_kind == "unrelated":
        tree = _git(repository, "mktree")
        supplied_production = subprocess.run(
            ["git", "commit-tree", tree, "-m", "unrelated"],
            cwd=repository,
            check=True,
            text=True,
            capture_output=True,
        ).stdout.strip()
    else:
        release_bundle, production_bundle = production_bundle, release_bundle
        supplied_release, supplied_production = production_sha, release_sha
    monkeypatch.chdir(repository)

    result = _invoke_lineage(
        release_bundle,
        production_bundle,
        supplied_release,
        supplied_production,
    )

    assert result.exit_code == 1
    report = json.loads(result.stdout)
    assert report["result"] == "fail"
    assert report["errors"]


def test_release_verify_lineage_report_is_deterministic(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repository, release_sha, production_sha, release_bundle, production_bundle = _lineage_fixture(
        tmp_path
    )
    monkeypatch.chdir(repository)

    first = _invoke_lineage(
        release_bundle,
        production_bundle,
        release_sha,
        production_sha,
    )
    second = _invoke_lineage(
        release_bundle,
        production_bundle,
        release_sha,
        production_sha,
    )

    assert first.exit_code == second.exit_code == 0
    assert first.stdout == second.stdout


def _lineage_fixture(root: Path) -> tuple[Path, str, str, Path, Path]:
    repository, release_sha, production_sha = _git_lineage(root)
    release_bundle = _write_bundle(
        root / "release",
        git_commit=release_sha,
        generated_at="2026-10-16T16:00:00Z",
        screenshot_suffix=b"release",
    )
    production_bundle = _write_bundle(
        root / "production",
        git_commit=production_sha,
        generated_at="2026-10-16T17:00:00Z",
        screenshot_suffix=b"production",
    )
    return repository, release_sha, production_sha, release_bundle, production_bundle


def _git_lineage(root: Path) -> tuple[Path, str, str]:
    repository = root / "repository"
    repository.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=repository, check=True)
    subprocess.run(["git", "config", "user.name", "Lineage Test"], cwd=repository, check=True)
    subprocess.run(
        ["git", "config", "user.email", "lineage@example.invalid"],
        cwd=repository,
        check=True,
    )
    marker = repository / "marker"
    marker.write_text("release\n", encoding="utf-8")
    subprocess.run(["git", "add", "marker"], cwd=repository, check=True)
    subprocess.run(["git", "commit", "-qm", "release"], cwd=repository, check=True)
    release_sha = _git(repository, "rev-parse", "HEAD")
    marker.write_text("production\n", encoding="utf-8")
    subprocess.run(["git", "commit", "-qam", "production"], cwd=repository, check=True)
    return repository, release_sha, _git(repository, "rev-parse", "HEAD")


def _git(repository: Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=repository, check=True, text=True, capture_output=True
    ).stdout.strip()


def _write_bundle(
    root: Path,
    *,
    git_commit: str,
    generated_at: str,
    screenshot_suffix: bytes,
) -> Path:
    root.mkdir()
    dataset = _json_bytes({"election": "wa-2026-general", "records": ["same"]})
    dataset_hash = hashlib.sha256(dataset).hexdigest()
    consensus = _json_bytes(
        {
            "computed_at": generated_at,
            "dataset_hash": dataset_hash,
            "election_id": "wa-2026-general",
            "input_hash": "7" * 64,
            "races": [{"computed_at": generated_at, "race_id": "city-council-1"}],
        }
    )
    publication = _json_bytes(
        {
            "metadata": {
                "election_id": "wa-2026-general",
                "generated_at": generated_at,
                "git_commit": git_commit,
                "source_panel_hash": "2" * 64,
                "source_panel_id": "wa-2026-general-default-sources-v1",
                "source_registry_hash": "3" * 64,
            },
            "recommendations": ["same"],
        }
    )
    validation = _json_bytes(
        {"election_id": "wa-2026-general", "generated_at": generated_at, "passed": True}
    )
    provenance = _json_bytes(
        {
            "consensus_output_hash": hashlib.sha256(consensus).hexdigest(),
            "dataset_hash": dataset_hash,
            "election_id": "wa-2026-general",
            "generated_at": generated_at,
            "input_snapshot_hashes": {"source-decisions.yaml": "4" * 64},
        }
    )
    publication_artifacts = {
        "consensus.json": consensus,
        "publication_view_model.json": publication,
        "provenance_manifest.json": provenance,
        "validation_report.json": validation,
    }
    build_manifest = _json_bytes(
        {
            "artifact_hashes": {
                name: hashlib.sha256(content).hexdigest()
                for name, content in publication_artifacts.items()
            },
            "configuration_hash": "5" * 64,
            "consensus_output_hash": hashlib.sha256(consensus).hexdigest(),
            "election_id": "wa-2026-general",
            "generated_at": generated_at,
            "git_commit": git_commit,
            "input_snapshot_hashes": {"source-decisions.yaml": "4" * 64},
            "normalized_data_hash": "6" * 64,
        }
    )
    files: dict[str, bytes] = {
        "RELEASE_NOTES.md": (
            f"# General release\n\n- Built at: {generated_at}\n- Code revision: `{git_commit}`\n"
        ).encode(),
        "data/build_manifest.json": build_manifest,
        "data/canonical-dataset.json": dataset,
        "data/consensus.json": consensus,
        "data/endorsement_records.csv": b"source_id,race_id,candidate_id\nsame,race,pick\n",
        "data/archive.json": b'{"archived":"same"}\n',
        "data/provenance_manifest.json": provenance,
        "data/publication_view_model.json": publication,
        "data/race_summary.csv": b"race_id,recommendation\nrace,pick\n",
        "data/recommendations.json": b'{"recommendation":"same"}\n',
        "data/source_matrix.csv": b"source_id,race_id,state\nsame,race,endorsement\n",
        "data/source_metadata.csv": b"source_id,name\nsame,Same\n",
        "data/unresolved_review_items.csv": b"id,severity\n",
        "data/validation_report.json": validation,
        "guide/guide.html": (
            '<!doctype html><span class="audit-site">Site updated '
            f'{generated_at[:10]} (<a href="https://github.com/shaug/'
            "seattle-election-guide/commit/"
            f'{git_commit}">{git_commit[:12]}</a>)</span>'
        ).encode(),
        "guide/client.js": b"export const recommendation = 'same';\n",
        "guide/routes.json": b'{"routes":["/e/wa-2026-general/"]}\n',
        "guide/styles.css": b"body { color: black; }\n",
        "guide/template.html": b"<template>same</template>\n",
        "validation/rendering/rendering_validation_report.json": b'{"passed":true}\n',
        "validation/rendering/screenshots/desktop.png": b"desktop-" + screenshot_suffix,
        "validation/rendering/screenshots/mobile.png": b"mobile-" + screenshot_suffix,
    }
    included_artifacts = sorted({*REQUIRED_RELEASE_ARTIFACTS, *files, "release-status.json"})
    status = {
        "captured_source_count": 1,
        "data_as_of": "2026-10-15T23:00:00Z",
        "displayed_endorsement_count": 1,
        "election_id": "wa-2026-general",
        "generated_at": generated_at,
        "git_commit": git_commit,
        "guide_html_artifact": "guide/guide.html",
        "included_artifacts": included_artifacts,
        "incomplete_races": [],
        "release_version": "2026-general.1",
        "restricted_capture_count": 0,
        "schema_version": "1.3",
        "source_access_failures": [],
        "source_count": 1,
        "source_panel_hash": "2" * 64,
        "source_panel_id": "wa-2026-general-default-sources-v1",
        "source_registry_hash": "3" * 64,
        "unresolved_high_severity_count": 0,
        "unresolved_review_count": 0,
        "validation_reports": {"publication": True, "rendering": True},
        "warnings": [],
    }
    files["release-status.json"] = _json_bytes(status)
    for relative, content in files.items():
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
    manifest = {
        "artifact_hashes": {
            relative: hashlib.sha256(content).hexdigest()
            for relative, content in sorted(files.items())
            if relative not in UNHASHED_RASTERIZED_ARTIFACTS
        },
        "generated_at": generated_at,
        "release_version": "2026-general.1",
        "schema_version": "1.3",
        "source_panel_hash": "2" * 64,
        "source_panel_id": "wa-2026-general-default-sources-v1",
        "source_registry_hash": "3" * 64,
        "unhashed_artifacts": sorted(UNHASHED_RASTERIZED_ARTIFACTS),
    }
    (root / "release-manifest.json").write_bytes(_json_bytes(manifest))
    return root


def _archive_bundle(bundle: Path, archive_path: Path) -> Path:
    with ZipFile(archive_path, "w", compression=ZIP_DEFLATED) as archive:
        for path in sorted(bundle.rglob("*")):
            if path.is_file():
                archive.write(path, (Path("seattle-election-guide") / path.relative_to(bundle)))
    return archive_path


def _invoke_lineage(
    release_bundle: Path,
    production_bundle: Path,
    release_sha: str,
    production_sha: str,
):
    return CliRunner().invoke(
        app,
        [
            "release",
            "verify-lineage",
            str(release_bundle),
            str(production_bundle),
            release_sha,
            production_sha,
        ],
    )


def _rehash_release_manifest(bundle: Path, relative: str) -> None:
    manifest_path = bundle / "release-manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["artifact_hashes"][relative] = hashlib.sha256(
        (bundle / relative).read_bytes()
    ).hexdigest()
    manifest_path.write_bytes(_json_bytes(manifest))


def _json_bytes(value: object) -> bytes:
    return (json.dumps(value, indent=2, sort_keys=True) + "\n").encode()
