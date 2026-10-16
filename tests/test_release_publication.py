"""Conflict-safe release publication uses GitHub-shaped fixtures, never live writes."""

from __future__ import annotations

import hashlib
import json
import shutil
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
import yaml

from election_guide.hosting.models import PublicationRequest
from election_guide.hosting.pages import bundle_hash, read_site_manifest
from election_guide.release import candidate
from election_guide.release.automation_models import (
    CandidateRecord,
    FileDigest,
    Producer,
    PublicationResult,
)
from election_guide.release.declaration import ReleaseInputs, ResolvedRelease, hash_release_inputs
from election_guide.release.models import release_archive_name
from election_guide.serialization import canonical_json_bytes
from tests.test_hosting import _write_release_bundle  # pyright: ignore[reportPrivateUsage]
from tests.test_hosting_releases import _released_archive  # pyright: ignore[reportPrivateUsage]
from tests.test_release_candidate import _artifact, _git  # pyright: ignore[reportPrivateUsage]


def digest(path: Path) -> FileDigest:
    return FileDigest(
        sha256=hashlib.sha256(path.read_bytes()).hexdigest(), size=path.stat().st_size
    )


@pytest.fixture
def setup_publication(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[Any, ...]:
    from election_guide.release import publication

    root = tmp_path
    paths = [
        root / name
        for name in ("ledger", "inventory", "registry", "dataset", "snapshots", "manifests")
    ]
    for path in paths[:4]:
        path.write_text(path.name)
    for path in paths[4:]:
        path.mkdir()
    inputs = ReleaseInputs(*paths)
    request = PublicationRequest(
        issue_number=550, previous_release_sha="a" * 40, inputs=hash_release_inputs(inputs)
    )
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
                        "source_registry_hash": "c" * 64,
                        "publication_request": request.model_dump(),
                    }
                ],
            }
        )
    )
    (root / "config/calendar").mkdir()
    shutil.copy2(Path("config/calendar/elections.yaml"), root / "config/calendar/elections.yaml")
    (root / ".gitignore").write_text("dist/\n")
    _git(root, "init", "-q")
    _git(root, "config", "user.email", "fixture@example.com")
    _git(root, "config", "user.name", "Fixture")
    _git(root, "add", ".")
    _git(root, "commit", "-qm", "feat: reviewed fixture")
    sha = _git(root, "rev-parse", "HEAD")
    producer = Producer(
        repository="owner/repository", source_sha=sha, workflow_sha=sha, run_id=100, run_attempt=2
    )
    site = read_site_manifest(site_path)
    resolved = ResolvedRelease(site, site.elections[0], inputs, release_archive_name("primary.2"))
    bundle = _write_release_bundle(
        root / "dist/build",
        election_id="wa-2026-primary",
        release_version="primary.2",
        git_commit=sha,
        html=b"guide\n",
        source_registry_hash="c" * 64,
    )
    archive = _released_archive(bundle, "primary.2", root / "dist/build")

    def resolve(_path: Path, *, repository: Path) -> ResolvedRelease:
        assert repository == root
        return resolved

    monkeypatch.setattr(publication, "resolve_release", resolve)
    monkeypatch.setattr(candidate, "resolve_release", resolve)
    candidate.stage_current_candidate(
        resolved, repository=root, bundle_dir=bundle, output_dir=root / "dist/site", source_sha=sha
    )
    record = CandidateRecord(
        declaration=resolved.current,
        site_manifest_sha256=digest(site_path).sha256,
        source_sha=sha,
        generated_at=datetime(2026, 7, 21, 12, tzinfo=UTC),
        inputs=hash_release_inputs(inputs),
        producer=producer,
        archive=digest(archive),
        bundle_sha256=bundle_hash(bundle),
        deployment_manifest_sha256=digest(root / "dist/site/deployment-manifest.json").sha256,
        release_artifact=_artifact(producer, "release", 10),
        site_artifact=_artifact(producer, "site", 11),
    )
    return publication, resolved, record, archive, bundle, root


class GitHub:
    """Fields follow official Releases/Actions REST response fixtures."""

    def __init__(self, record: CandidateRecord, archive: Path, body: str, state: str):
        self.record, self.archive, self.body = record, archive, body
        self.events: list[str] = []
        self.tag = state not in {"absent", "unrelated", "draft-empty", "draft-zip"}
        self.release: dict[str, Any] | None = (
            None
            if state in {"absent", "orphan"}
            else {
                "id": 20,
                "tag_name": record.declaration.release_version,
                "target_commitish": record.source_sha,
                "name": record.declaration.release_version,
                "body": body,
                "draft": state in {"draft-empty", "draft-zip", "unrelated"},
                "prerelease": False,
            }
        )
        self.assets: list[dict[str, Any]] = (
            []
            if state in {"absent", "orphan", "draft-empty", "unrelated", "missing"}
            else [self.asset()]
        )
        if state == "unrelated":
            assert self.release is not None
            self.release["body"] = "someone else's draft"
        if state == "notes":
            assert self.release is not None
            self.release["body"] = "wrong notes"
        if state == "extra":
            self.assets.append({**self.asset(), "id": 22, "name": "unexpected.txt"})
        if state == "duplicate":
            self.assets.append({**self.asset(), "id": 22})
        self.wrong_tag = state == "wrong-tag"
        self.annotated = state == "annotated"

    def asset(self) -> dict[str, Any]:
        value = digest(self.archive)
        return {
            "id": 21,
            "name": self.archive.name,
            "size": value.size,
            "digest": "sha256:" + value.sha256,
            "state": "uploaded",
        }

    def run(self, command: list[str], failure: str) -> str:
        endpoint = command[2]
        if endpoint.endswith("/tags?per_page=100"):
            return json.dumps(
                [[{"name": self.record.declaration.release_version}] if self.tag else []]
            )
        if endpoint.endswith("/releases?per_page=100"):
            return json.dumps([[self.release] if self.release else []])
        if "/git/ref/tags/" in endpoint:
            return json.dumps(
                {
                    "object": {
                        "sha": "f" * 40
                        if self.annotated
                        else ("e" * 40 if self.wrong_tag else self.record.source_sha),
                        "type": "tag" if self.annotated else "commit",
                    }
                }
            )
        if "/git/tags/" in endpoint:
            return json.dumps({"object": {"sha": self.record.source_sha, "type": "commit"}})
        if endpoint.endswith("/assets?per_page=100"):
            return json.dumps([self.assets])
        if "--method" in command:
            method = command[command.index("--method") + 1]
            if method == "POST":
                self.events.append("draft")
                self.release = {
                    "id": 20,
                    "tag_name": self.record.declaration.release_version,
                    "target_commitish": self.record.source_sha,
                    "name": self.record.declaration.release_version,
                    "body": self.body,
                    "draft": True,
                    "prerelease": False,
                }
                self.tag = True
            elif method == "PATCH":
                self.events.append("publish")
                assert self.release is not None
                self.release["draft"] = False
                self.tag = True
            else:
                raise AssertionError(command)
            return json.dumps(self.release)
        if command[:3] == ["gh", "release", "upload"]:
            assert "--clobber" not in command
            self.events.append("upload")
            self.assets = [{**self.asset(), "name": Path(command[4]).name}]
            return ""
        raise AssertionError(command)

    def download(self, command: list[str], destination: Path, failure: str) -> None:
        self.events.append("download")
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(self.archive, destination)


def install_remote(monkeypatch: pytest.MonkeyPatch, setup: tuple[Any, ...], state: str) -> GitHub:
    publication, _, record, archive, bundle, _ = setup
    remote = GitHub(
        record,
        archive,
        publication.publication_body(record, (bundle / "RELEASE_NOTES.md").read_text()),
        state,
    )
    monkeypatch.setattr(publication, "run_gh", remote.run)
    monkeypatch.setattr(publication, "download_gh", remote.download)
    return remote


def publish(setup: tuple[Any, ...], **kwargs: Any) -> Any:
    publication, _, record, archive, _, root = setup
    return publication.publish_candidate(
        record,
        candidate_artifact=_artifact(record.producer, "candidate", 12),
        repository=root,
        archive_path=archive,
        work_dir=root / "dist/publication",
        existing_receipt=kwargs.get("existing_receipt"),
    )


@pytest.mark.parametrize(
    "state, succeeds",
    [
        ("absent", True),
        ("draft-empty", True),
        ("draft-zip", True),
        ("published", True),
        ("annotated", True),
        ("unrelated", False),
        ("wrong-tag", False),
        ("notes", False),
        ("extra", False),
        ("missing", False),
        ("duplicate", False),
        ("orphan", False),
    ],
)
def test_publication_preflight_states(
    setup_publication: tuple[Any, ...], monkeypatch: pytest.MonkeyPatch, state: str, succeeds: bool
) -> None:
    remote = install_remote(monkeypatch, setup_publication, state)
    if succeeds:
        result = publish(setup_publication)
        assert result.release_id == 20
        assert result.asset_id == 21
        if state in {"published", "annotated"}:
            assert remote.events == ["download"]
    else:
        with pytest.raises(ValueError):
            publish(setup_publication)
        assert not set(remote.events) & {"draft", "upload", "publish"}


def test_uploaded_archive_is_downloaded_before_publish(
    setup_publication: tuple[Any, ...], monkeypatch: pytest.MonkeyPatch
) -> None:
    remote = install_remote(monkeypatch, setup_publication, "absent")
    result = publish(setup_publication)
    assert remote.events == ["draft", "upload", "download", "publish"]
    assert remote.release is not None and remote.release["draft"] is False
    assert (
        result.promotion_manifest_sha256
        == digest(
            setup_publication[-1] / "dist/publication/promotion-site/deployment-manifest.json"
        ).sha256
    )


@pytest.mark.parametrize("deterministic", [False, True])
def test_published_screenshot_difference_preserves_original_zip(
    setup_publication: tuple[Any, ...], monkeypatch: pytest.MonkeyPatch, deterministic: bool
) -> None:
    publication, _, record, _, bundle, root = setup_publication
    remote = install_remote(monkeypatch, setup_publication, "published")
    relative = (
        "guide/guide.html" if deterministic else "validation/rendering/screenshots/desktop.png"
    )
    original_bytes = (bundle / relative).read_bytes()
    original_archive = digest(remote.archive)
    original_path = root / "dist/original" / remote.archive.name
    original_path.parent.mkdir()
    shutil.copy2(remote.archive, original_path)
    remote.archive = original_path
    (bundle / relative).write_bytes(b"new rendering")
    if deterministic:
        manifest_path = bundle / "release-manifest.json"
        manifest = json.loads(manifest_path.read_bytes())
        manifest["artifact_hashes"][relative] = digest(bundle / relative).sha256
        manifest_path.write_bytes(canonical_json_bytes(manifest))
    new_archive = _released_archive(bundle, "primary.2", root / "dist/build")
    record = record.model_copy(
        update={"archive": digest(new_archive), "bundle_sha256": bundle_hash(bundle)}
    )
    # Candidate site is bound to the new build before recovery, just as Task 3 does.
    publication.stage_current_candidate(
        setup_publication[1],
        repository=root,
        bundle_dir=bundle,
        output_dir=root / "dist/new-site",
        source_sha=record.source_sha,
    )
    record = record.model_copy(
        update={
            "deployment_manifest_sha256": digest(
                root / "dist/new-site/deployment-manifest.json"
            ).sha256
        }
    )
    revised = (*setup_publication[:2], record, new_archive, bundle, root)
    if deterministic:
        with pytest.raises(ValueError, match="deterministic"):
            publish(revised)
    else:
        recovered = publish(revised)
        assert recovered.asset_id == 21
        assert recovered.archive == original_archive
        assert (
            root / "dist/publication/canonical-bundle" / relative
        ).read_bytes() == original_bytes
        assert (
            root / "dist/publication" / remote.archive.name
        ).read_bytes() == original_path.read_bytes()
        assert record.archive != recovered.archive
    assert remote.events == ["download"]


def test_receipt_conflict_fails_without_remote_writes(
    setup_publication: tuple[Any, ...], monkeypatch: pytest.MonkeyPatch
) -> None:
    remote = install_remote(monkeypatch, setup_publication, "published")
    result = publish(setup_publication)
    receipt = setup_publication[0].bind_publication(
        result, _artifact(result.candidate.producer, "promotion", 13)
    )
    shutil.rmtree(setup_publication[-1] / "dist/publication")
    assert publish(setup_publication, existing_receipt=receipt) == result
    shutil.rmtree(setup_publication[-1] / "dist/publication")
    wrong = PublicationResult(
        published=result.model_copy(update={"asset_id": 99}),
        promotion_artifact=receipt.promotion_artifact,
    )
    with pytest.raises(ValueError, match="receipt"):
        publish(setup_publication, existing_receipt=wrong)
    assert not set(remote.events) & {"draft", "upload", "publish"}


def test_publisher_requires_request(
    setup_publication: tuple[Any, ...], monkeypatch: pytest.MonkeyPatch
) -> None:
    remote = install_remote(monkeypatch, setup_publication, "absent")
    record = setup_publication[2]
    revised = (
        *setup_publication[:2],
        record.model_copy(
            update={
                "declaration": record.declaration.model_copy(update={"publication_request": None})
            }
        ),
        *setup_publication[3:],
    )
    with pytest.raises(ValueError, match="request"):
        publish(revised)
    assert remote.events == []


@pytest.mark.parametrize("changed", ["name", "producer", "id"])
def test_bind_publication_rejects_wrong_upload(
    setup_publication: tuple[Any, ...], monkeypatch: pytest.MonkeyPatch, changed: str
) -> None:
    install_remote(monkeypatch, setup_publication, "published")
    published = publish(setup_publication)
    reference = _artifact(published.candidate.producer, "promotion", 13)
    update = (
        {"name": "promotion-100-3"}
        if changed == "name"
        else {"id": 12}
        if changed == "id"
        else {
            "producer": published.candidate.producer.model_copy(update={"workflow_sha": "f" * 40})
        }
    )
    with pytest.raises(ValueError):
        setup_publication[0].bind_publication(published, reference.model_copy(update=update))


def test_failed_download_cannot_finalize_a_draft(
    setup_publication: tuple[Any, ...], monkeypatch: pytest.MonkeyPatch
) -> None:
    remote = install_remote(monkeypatch, setup_publication, "draft-zip")

    def corrupt(command: list[str], destination: Path, failure: str) -> None:
        remote.events.append("download")
        destination.write_bytes(b"damaged")

    monkeypatch.setattr(setup_publication[0], "download_gh", corrupt)
    with pytest.raises(ValueError, match="asset metadata"):
        publish(setup_publication)
    assert remote.events == ["download"]
    assert remote.release is not None and remote.release["draft"] is True
    assert not (setup_publication[-1] / "dist/publication/published-archive.json").exists()


@pytest.mark.parametrize("state", ["absent", "draft-empty", "draft-zip"])
def test_receipt_for_missing_or_draft_release_cannot_write(
    setup_publication: tuple[Any, ...], monkeypatch: pytest.MonkeyPatch, state: str
) -> None:
    install_remote(monkeypatch, setup_publication, "published")
    previous = publish(setup_publication)
    receipt = setup_publication[0].bind_publication(
        previous, _artifact(previous.candidate.producer, "promotion", 13)
    )
    shutil.rmtree(setup_publication[-1] / "dist/publication")
    remote = install_remote(monkeypatch, setup_publication, state)
    with pytest.raises(ValueError, match="receipt"):
        publish(setup_publication, existing_receipt=receipt)
    assert remote.events == []


def test_publish_and_bind_commands_capture_separate_outputs(
    setup_publication: tuple[Any, ...], monkeypatch: pytest.MonkeyPatch
) -> None:
    from typer.testing import CliRunner

    from election_guide.cli import app
    from election_guide.release import automation_cli

    _, _, record, archive, _, root = setup_publication
    install_remote(monkeypatch, setup_publication, "published")
    monkeypatch.setattr(automation_cli, "_repository", lambda: root)
    record_path = root / "dist/record.json"
    candidate_ref = root / "dist/candidate-ref.json"
    promotion_ref = root / "dist/promotion-ref.json"
    record_path.write_text(record.model_dump_json())
    candidate_ref.write_text(_artifact(record.producer, "candidate", 12).model_dump_json())
    promotion_ref.write_text(_artifact(record.producer, "promotion", 13).model_dump_json())
    runner = CliRunner()
    result = runner.invoke(
        app,
        [
            "release",
            "automation",
            "publish",
            "--record",
            str(record_path),
            "--candidate-artifact-file",
            str(candidate_ref),
            "--archive",
            str(archive),
            "--output-dir",
            str(root / "dist/publication"),
        ],
    )
    assert result.exit_code == 0, result.output
    published_path = root / "dist/publication/published-archive.json"
    assert json.loads(published_path.read_bytes())["candidate"] == record.model_dump(mode="json")
    output = root / "dist/publication.json"
    result = runner.invoke(
        app,
        [
            "release",
            "automation",
            "bind-publication",
            "--published",
            str(published_path),
            "--promotion-artifact-file",
            str(promotion_ref),
            "--output",
            str(output),
        ],
    )
    assert result.exit_code == 0, result.output
    receipt = PublicationResult.model_validate_json(output.read_bytes())
    assert receipt.promotion_artifact.id == 13
    assert receipt.published.archive != receipt.promotion_artifact.digest


@pytest.mark.parametrize("failed", [False, True])
def test_download_gh_streams_binary_and_removes_failed_download(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, failed: bool
) -> None:
    import subprocess

    from election_guide.github_cli import download_gh

    payload = b"PK\x00\xff\xfe\x80"

    def run(command: list[str], **kwargs: Any) -> subprocess.CompletedProcess[bytes]:
        assert "capture_output" not in kwargs
        assert "text" not in kwargs
        kwargs["stdout"].write(payload)
        return subprocess.CompletedProcess(command, int(failed), stderr=b"download denied")

    monkeypatch.setattr(subprocess, "run", run)
    destination = tmp_path / "nested/archive.zip"
    if failed:
        with pytest.raises(ValueError, match="download denied"):
            download_gh(["gh", "api", "asset"], destination, "archive failed")
        assert not destination.exists()
    else:
        download_gh(["gh", "api", "asset"], destination, "archive failed")
        assert destination.read_bytes() == payload
        with pytest.raises(ValueError, match="already exists"):
            download_gh(["gh", "api", "asset"], destination, "archive failed")
        assert destination.read_bytes() == payload


@pytest.mark.parametrize("changed", ["tag_name", "body"])
def test_final_release_tag_name_must_still_match(
    setup_publication: tuple[Any, ...], monkeypatch: pytest.MonkeyPatch, changed: str
) -> None:
    remote = install_remote(monkeypatch, setup_publication, "draft-zip")
    run = remote.run

    def renamed(command: list[str], failure: str) -> str:
        result = run(command, failure)
        if "PATCH" in command:
            value = json.loads(result)
            value[changed] = (
                "unrelated-version"
                if changed == "tag_name"
                else (setup_publication[4] / "RELEASE_NOTES.md").read_text()
            )
            return json.dumps(value)
        return result

    monkeypatch.setattr(setup_publication[0], "run_gh", renamed)
    with pytest.raises(ValueError, match=r"tag name|ownership marker"):
        publish(setup_publication)
    assert not (setup_publication[-1] / "dist/publication/published-archive.json").exists()


def test_finalization_compares_stable_asset_identity_after_download(
    setup_publication: tuple[Any, ...], monkeypatch: pytest.MonkeyPatch
) -> None:
    remote = install_remote(monkeypatch, setup_publication, "draft-zip")
    remote.assets[0]["download_count"] = 0
    download = remote.download

    def counted_download(command: list[str], destination: Path, failure: str) -> None:
        download(command, destination, failure)
        remote.assets[0]["download_count"] += 1

    monkeypatch.setattr(setup_publication[0], "download_gh", counted_download)
    assert publish(setup_publication).asset_id == 21
    assert remote.assets[0]["download_count"] == 1


@pytest.mark.parametrize("state", ["absent", "draft-empty"])
def test_renamed_candidate_archive_fails_before_remote_mutation(
    setup_publication: tuple[Any, ...], monkeypatch: pytest.MonkeyPatch, state: str
) -> None:
    remote = install_remote(monkeypatch, setup_publication, state)
    original = setup_publication[3]
    renamed = original.with_name("candidate.zip")
    shutil.copy2(original, renamed)
    assert digest(renamed) == setup_publication[2].archive
    revised = (*setup_publication[:3], renamed, *setup_publication[4:])

    with pytest.raises(ValueError) as error:
        publish(revised)

    assert remote.events == []
    assert "canonical archive filename" in str(error.value)
