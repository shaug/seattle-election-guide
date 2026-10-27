"""Exact-source candidate and uploaded artifact identity contracts (issue 550)."""

from __future__ import annotations

import hashlib
import json
import subprocess
import zipfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
import yaml

from election_guide.hosting.pages import read_site_manifest, stage_pages_site
from election_guide.release import candidate
from election_guide.release.automation_models import (
    ArtifactRef,
    CandidateRecord,
    FileDigest,
    Producer,
)
from election_guide.release.declaration import ReleaseInputs, ResolvedRelease
from election_guide.release.models import release_archive_name
from tests.release_fixtures import minimal_publication_view_model
from tests.test_hosting import _write_release_bundle  # pyright: ignore[reportPrivateUsage]
from tests.test_hosting_releases import _released_archive  # pyright: ignore[reportPrivateUsage]


def _git(root: Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=root, check=True, capture_output=True, text=True
    ).stdout.strip()


@pytest.fixture
def prepared(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> tuple[ResolvedRelease, Producer, Path]:
    root = tmp_path
    _git(root, "init", "-q")
    _git(root, "config", "user.email", "fixture@example.com")
    _git(root, "config", "user.name", "Fixture")
    (root / ".gitignore").write_text("dist/\n")
    site_path = root / "config/hosting/site.yaml"
    site_path.parent.mkdir(parents=True)
    site_path.write_text(
        yaml.safe_dump(
            {
                "current_election_id": "wa-2026-primary",
                "canonical_origin": "https://example.com",
                "elections": [
                    {
                        "election_id": "wa-2026-primary",
                        "bundle_id": "wa-2026-primary-primary.2",
                        "release_version": "primary.2",
                        "source_panel_id": "test-panel-v2",
                        "source_panel_hash": "b" * 64,
                    }
                ],
            }
        )
    )
    paths = [
        root / name
        for name in ("ledger", "inventory", "registry", "dataset", "snapshots", "manifests")
    ]
    for path in paths[:4]:
        path.write_text(path.name + "\n")
    for path in paths[4:]:
        path.mkdir()
    _git(root, "add", ".")
    _git(root, "commit", "-qm", "feat: fixture source")
    sha = _git(root, "rev-parse", "HEAD")
    producer = Producer(
        repository="owner/repository", source_sha=sha, workflow_sha=sha, run_id=100, run_attempt=2
    )
    site = read_site_manifest(site_path)
    resolved = ResolvedRelease(
        site, site.elections[0], ReleaseInputs(*paths), release_archive_name("primary.2")
    )
    output = root / "dist"
    bundle = _write_release_bundle(
        output / "reproducibility-a",
        election_id="wa-2026-primary",
        release_version="primary.2",
        git_commit=sha,
        html=b"guide\n",
        view_model=minimal_publication_view_model(),
    )
    _released_archive(bundle, "primary.2", output / "reproducibility-a")
    stage_pages_site(
        site_path,
        {resolved.current.bundle_id: bundle},
        output / "cloudflare-site",
        expected_current_git_commit=sha,
    )

    def fixture_resolver(_path: Path, *, repository: Path) -> ResolvedRelease:
        assert repository == root
        return resolved

    monkeypatch.setattr(candidate, "resolve_release", fixture_resolver)
    return resolved, producer, output


def _artifact(producer: Producer, kind: str, artifact_id: int) -> ArtifactRef:
    return ArtifactRef(
        id=artifact_id,
        name=f"{kind}-{producer.run_id}-{producer.run_attempt}",
        digest=FileDigest(sha256="d" * 64, size=123),
        producer=producer,
    )


def _record(prepared: tuple[ResolvedRelease, Producer, Path]) -> CandidateRecord:
    resolved, producer, output = prepared
    return candidate.record_candidate(
        resolved,
        repository=output.parent,
        output_dir=output,
        producer=producer,
        release_artifact=_artifact(producer, "release", 10),
        site_artifact=_artifact(producer, "site", 11),
    )


@pytest.mark.parametrize(
    "changed",
    ["archive", "asset", "manifest", "declaration", "ledger", "dataset", "registry", "source"],
)
def test_candidate_binds_full_source_and_all_bytes(
    prepared: tuple[ResolvedRelease, Producer, Path], changed: str
) -> None:
    resolved, producer, output = prepared
    record = _record(prepared)
    archive = output / "reproducibility-a" / resolved.archive_name
    assert record.source_sha == record.producer.source_sha == producer.source_sha
    assert record.archive.sha256 == hashlib.sha256(archive.read_bytes()).hexdigest()
    candidate.verify_candidate(
        record, repository=output.parent, archive_path=archive, site_dir=output / "cloudflare-site"
    )
    paths = {
        "archive": archive,
        "asset": output / "cloudflare-site/about/index.html",
        "manifest": output / "cloudflare-site/deployment-manifest.json",
        "declaration": output.parent / "config/hosting/site.yaml",
        "ledger": resolved.inputs.ledger,
        "dataset": resolved.inputs.dataset,
        "registry": resolved.inputs.registry,
    }
    if changed == "source":
        record = record.model_copy(update={"source_sha": "e" * 40})
    else:
        with paths[changed].open("ab") as stream:
            stream.write(b"\n# changed" if changed == "declaration" else b"\nchanged")
    with pytest.raises(ValueError):
        candidate.verify_candidate(
            record,
            repository=output.parent,
            archive_path=archive,
            site_dir=output / "cloudflare-site",
        )


@pytest.mark.parametrize(
    "changed", ["attempt", "id", "source", "repository", "workflow", "name", "digest"]
)
def test_artifact_attempt_cannot_be_substituted(
    prepared: tuple[ResolvedRelease, Producer, Path], changed: str
) -> None:
    _, producer, _ = prepared
    expected = _artifact(producer, "release", 10)
    updates: dict[str, Any] = {}
    if changed in {"attempt", "source", "repository", "workflow"}:
        key, value = {
            "attempt": ("run_attempt", 3),
            "source": ("source_sha", "e" * 40),
            "repository": ("repository", "other/repo"),
            "workflow": ("workflow_sha", "e" * 40),
        }[changed]
        updates["producer"] = producer.model_copy(update={key: value})
    else:
        updates = {
            "id": {"id": 99},
            "name": {"name": "release-100-3"},
            "digest": {"digest": FileDigest(sha256="e" * 64, size=123)},
        }[changed]
    with pytest.raises(ValueError):
        candidate.verify_artifact_ref(expected, expected.model_copy(update=updates))


def test_record_does_not_reference_its_own_artifact(
    prepared: tuple[ResolvedRelease, Producer, Path],
) -> None:
    record = _record(prepared)
    payload = record.model_dump(mode="json")
    assert set(key for key in payload if key.endswith("_artifact")) == {
        "release_artifact",
        "site_artifact",
    }
    assert record.archive.sha256 != record.release_artifact.digest.sha256
    assert json.loads((prepared[2] / "candidate.json").read_bytes()) == payload


@pytest.mark.parametrize("member", ["seattle-election-guide/unexpected.txt", "../escape"])
def test_record_rejects_extra_zip_members(
    prepared: tuple[ResolvedRelease, Producer, Path], member: str
) -> None:
    resolved, _, output = prepared
    with zipfile.ZipFile(output / "reproducibility-a" / resolved.archive_name, "a") as archive:
        archive.writestr(member, b"extra")
    with pytest.raises(ValueError):
        _record(prepared)


@pytest.mark.parametrize(
    "updates",
    [
        {"source_sha": "A" * 40},
        {"workflow_sha": "abc"},
        {"run_id": 0},
        {"run_attempt": True},
        {"repository": "missing-owner"},
        {"extra": "forbidden"},
        {"schema_version": "2.0"},
    ],
)
def test_producer_rejects_invalid_fields(updates: dict[str, Any]) -> None:
    payload = {
        "repository": "owner/repo",
        "source_sha": "a" * 40,
        "workflow_sha": "b" * 40,
        "run_id": 1,
        "run_attempt": 1,
        **updates,
    }
    with pytest.raises(ValueError):
        Producer.model_validate(payload)


@pytest.mark.parametrize("updates", [{"sha256": "A" * 64}, {"size": -1}, {"size": True}])
def test_file_digest_rejects_invalid_fields(updates: dict[str, Any]) -> None:
    with pytest.raises(ValueError):
        FileDigest.model_validate({"sha256": "a" * 64, "size": 0, **updates})


def test_record_rejects_dirty_or_different_checkout(
    prepared: tuple[ResolvedRelease, Producer, Path],
) -> None:
    _, producer, output = prepared
    with pytest.raises(ValueError):
        _record((prepared[0], producer.model_copy(update={"source_sha": "e" * 40}), output))
    prepared[0].inputs.ledger.write_text("dirty")
    with pytest.raises(ValueError):
        _record(prepared)


def test_candidate_timestamp_must_be_aware(
    prepared: tuple[ResolvedRelease, Producer, Path],
) -> None:
    record = _record(prepared)
    with pytest.raises(ValueError):
        type(record).model_validate({**record.model_dump(), "generated_at": datetime(2026, 1, 1)})
    assert record.generated_at.tzinfo is not None
    assert record.generated_at < datetime.now(UTC)


@pytest.mark.parametrize("requested", [False, True], ids=["legacy", "publication-request"])
def test_candidate_build_uses_resolved_inputs_and_one_commit_timestamp(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, requested: bool
) -> None:
    """Real output catches dropped inputs, history, source, or build-A selection."""
    import shutil

    from election_guide.release.builder import build_release
    from election_guide.release.declaration import resolve_release
    from tests.test_release import (  # pyright: ignore[reportPrivateUsage]
        PROJECT_ROOT,
        RENDERING,
        _stub_release_render,  # pyright: ignore[reportPrivateUsage]
    )

    root = tmp_path
    shutil.copytree(PROJECT_ROOT / "config", root / "config")
    (root / "data").symlink_to(PROJECT_ROOT / "data", target_is_directory=True)
    (root / "node_modules").symlink_to(PROJECT_ROOT / "node_modules", target_is_directory=True)
    shutil.copy2(PROJECT_ROOT / "cliff.toml", root / "cliff.toml")
    (root / ".gitignore").write_text("dist/\nnode_modules/\n")
    path = root / "config/hosting/site.yaml"
    payload = yaml.safe_load(path.read_text())
    payload["elections"] = payload["elections"][:1]
    payload["elections"][0].pop("publication_request", None)
    path.write_text(yaml.safe_dump(payload))
    _git(root, "init", "-q")
    _git(root, "config", "user.email", "fixture@example.com")
    _git(root, "config", "user.name", "Fixture")
    _git(root, "add", ".")
    _git(root, "commit", "-qm", "feat: source fixture")
    previous_sha = _git(root, "rev-parse", "HEAD")
    resolved = resolve_release(candidate.SITE_MANIFEST, repository=root)
    if requested:
        inputs = resolved.inputs
        payload["elections"][0]["publication_request"] = {
            "issue_number": 550,
            "previous_release_sha": previous_sha,
            "inputs": {
                "ledger_sha256": hashlib.sha256(inputs.ledger.read_bytes()).hexdigest(),
                "dataset_sha256": hashlib.sha256(inputs.dataset.read_bytes()).hexdigest(),
                "registry_sha256": hashlib.sha256(inputs.registry.read_bytes()).hexdigest(),
            },
        }
        path.write_text(yaml.safe_dump(payload))
        _git(root, "add", ".")
        _git(root, "commit", "-qm", "fix: reviewed declaration")
        resolved = resolve_release(candidate.SITE_MANIFEST, repository=root)
    sha = _git(root, "rev-parse", "HEAD")
    _stub_release_render(
        monkeypatch, screenshot_versions=[(b"first", b"first"), (b"second", b"second")]
    )

    def build_with_fixture_renderer(**kwargs: Any) -> Any:
        assert kwargs["rendering_config_path"] == root / "config/rendering/guide.yaml"
        kwargs["rendering_config_path"] = RENDERING
        return build_release(**kwargs)

    monkeypatch.setattr(candidate, "build_release", build_with_fixture_renderer)
    output = root / "dist"
    archive_path = candidate.build_current_candidate(
        resolved, repository=root, output_dir=output, source_sha=sha
    )
    assert archive_path == output / "reproducibility-a" / resolved.archive_name
    with zipfile.ZipFile(archive_path) as archive:
        status = json.loads(archive.read("seattle-election-guide/release-status.json"))
        assert status["git_commit"] == sha
        assert datetime.fromisoformat(status["generated_at"]) == datetime.fromisoformat(
            _git(root, "show", "-s", "--format=%cI", sha)
        )
        assert (
            archive.read("seattle-election-guide/validation/rendering/screenshots/desktop.png")
            == b"first"
        )
        notes = archive.read("seattle-election-guide/RELEASE_NOTES.md").decode()
        assert ("## Software changes" in notes) is requested
        if requested:
            assert "Reviewed declaration" in notes
    assert (output / "cloudflare-site/deployment-manifest.json").is_file()
    assert _git(root, "status", "--porcelain") == ""


def test_operational_records_validate_nested_fields_and_pages_upload_identity(
    prepared: tuple[ResolvedRelease, Producer, Path],
) -> None:
    from election_guide.release.automation_models import (
        OperationReceipt,
        PublicationResult,
        PublishedArchive,
        UploadReceipt,
    )

    record = _record(prepared)
    producer = prepared[1]
    published = PublishedArchive(
        candidate=record,
        candidate_artifact=_artifact(producer, "candidate", 12),
        release_id=20,
        asset_id=21,
        asset_name=prepared[0].archive_name,
        archive=record.archive,
        release_manifest_sha256="a" * 64,
        canonical_bundle_sha256=record.bundle_sha256,
        promotion_manifest_sha256="b" * 64,
    )
    publication = PublicationResult(
        published=published, promotion_artifact=_artifact(producer, "promotion", 13)
    )
    upload = UploadReceipt(
        publication=publication,
        producer=producer,
        github_deployment_id=30,
        deployment_url="https://abc123.guide.pages.dev",
        uploaded_at=datetime.now(UTC),
        source_sha=producer.source_sha,
    )
    operation = OperationReceipt(
        phase="deployment",
        state="verified",
        producer=producer,
        publication=publication,
        upload=upload,
        verification_sha256="c" * 64,
        error=None,
    )
    for model in (record, published, publication, upload, operation):
        assert type(model).model_validate_json(model.model_dump_json()) == model
        with pytest.raises(ValueError):
            type(model).model_validate({**model.model_dump(), "extra": "forbidden"})
    for updates in ({"asset_id": 0}, {"release_id": True}, {"canonical_bundle_sha256": "A" * 64}):
        with pytest.raises(ValueError):
            PublishedArchive.model_validate({**published.model_dump(), **updates})
    for updates in (
        {"uploaded_at": datetime(2026, 1, 1)},
        {"source_sha": "short"},
        {"github_deployment_id": 0},
        {"deployment_url": "https://guide.pages.dev"},
        {"deployment_url": "https://main.guide.pages.dev"},
        {"deployment_url": "https://seattleelections.guide"},
        {"deployment_url": "http://abc123.guide.pages.dev"},
    ):
        with pytest.raises(ValueError):
            UploadReceipt.model_validate({**upload.model_dump(), **updates})
    for updates in ({"state": "success"}, {"phase": "upload"}, {"verification_sha256": "short"}):
        with pytest.raises(ValueError):
            OperationReceipt.model_validate({**operation.model_dump(), **updates})


def test_record_and_verify_commands_bind_captured_upload_outputs(
    prepared: tuple[ResolvedRelease, Producer, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    from typer.testing import CliRunner

    from election_guide.cli import app
    from election_guide.release import automation_cli

    resolved, producer, output = prepared

    def repository() -> Path:
        return output.parent

    def resolve(_path: Path, *, repository: Path) -> ResolvedRelease:
        assert repository == output.parent
        return resolved

    monkeypatch.setattr(automation_cli, "_repository", repository)
    monkeypatch.setattr(automation_cli, "resolve_release", resolve)
    producer_path = output / "producer.json"
    release_path = output / "release-artifact.json"
    site_path = output / "site-artifact.json"
    producer_path.write_text(producer.model_dump_json())
    release_path.write_text(_artifact(producer, "release", 10).model_dump_json())
    site_path.write_text(_artifact(producer, "site", 11).model_dump_json())
    record_path = output / "candidate.json"
    runner = CliRunner()
    result = runner.invoke(
        app,
        [
            "release",
            "automation",
            "record",
            "--producer-file",
            str(producer_path),
            "--release-artifact-file",
            str(release_path),
            "--site-artifact-file",
            str(site_path),
            "--output",
            str(record_path),
        ],
    )
    assert result.exit_code == 0, result.output
    payload = json.loads(record_path.read_bytes())
    assert payload["release_artifact"]["id"] == 10
    assert payload["site_artifact"]["id"] == 11
    arguments = [
        "release",
        "automation",
        "verify-candidate",
        "--record",
        str(record_path),
        "--archive",
        str(output / "reproducibility-a" / resolved.archive_name),
        "--site-dir",
        str(output / "cloudflare-site"),
    ]
    result = runner.invoke(app, arguments)
    assert result.exit_code == 0, result.output
    payload["release_artifact"]["producer"]["run_attempt"] = 3
    record_path.write_text(json.dumps(payload))
    result = runner.invoke(app, arguments)
    assert result.exit_code == 1
    assert "producer differs" in result.output


def test_build_rejects_dirty_or_different_source_before_producing_artifacts(
    prepared: tuple[ResolvedRelease, Producer, Path],
) -> None:
    resolved, producer, output = prepared
    with pytest.raises(ValueError, match="checkout HEAD"):
        candidate.build_current_candidate(
            resolved, repository=output.parent, output_dir=output, source_sha="e" * 40
        )
    resolved.inputs.ledger.write_text("dirty")
    with pytest.raises(ValueError, match="clean Git checkout"):
        candidate.build_current_candidate(
            resolved, repository=output.parent, output_dir=output, source_sha=producer.source_sha
        )
