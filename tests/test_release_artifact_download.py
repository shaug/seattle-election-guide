"""Actions wrapper storage must not contaminate publication checkouts (issue #550)."""

from __future__ import annotations

import hashlib
import io
import json
import subprocess
import zipfile
from pathlib import Path
from typing import Any, cast

import pytest
from typer.testing import CliRunner

from election_guide.hosting import promotion
from election_guide.release import automation_cli, publication
from election_guide.release.automation_models import ArtifactRef, FileDigest, Producer
from tests.test_release_candidate import _git  # pyright: ignore[reportPrivateUsage]
from tests.test_release_promotion import AdmissionAPI, artifact_metadata


def wrapper_fixture(
    root: Path, monkeypatch: pytest.MonkeyPatch, *, kind: str = "healthy"
) -> tuple[ArtifactRef, list[Path]]:
    _git(root, "init", "-q")
    _git(root, "config", "user.email", "fixture@example.com")
    _git(root, "config", "user.name", "Fixture")
    (root / ".gitignore").write_text("dist/\n")
    _git(root, "add", ".")
    _git(root, "commit", "-qm", "fixture")
    sha = _git(root, "rev-parse", "HEAD")
    producer = Producer(
        repository="owner/repository", source_sha=sha, workflow_sha=sha, run_id=100, run_attempt=2
    )
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("../escaped" if kind == "unsafe" else "candidate.json", b"reviewed bytes")
    content = b"not a ZIP" if kind == "malformed" else buffer.getvalue()
    reference = ArtifactRef(
        id=10,
        name="candidate-100-2",
        producer=producer,
        digest=FileDigest(sha256=hashlib.sha256(content).hexdigest(), size=len(content)),
    )
    api = AdmissionAPI(sha)
    metadata = artifact_metadata(reference, reference)
    metadata["expired"] = False

    def remote(command: list[str], failure: str) -> str:
        if "/actions/artifacts/" in command[2]:
            return json.dumps(metadata)
        return api(command, failure)

    paths: list[Path] = []

    real_run = subprocess.run

    def service(args: list[str], **kwargs: Any) -> Any:
        if args[0] != "gh":
            return cast(Any, real_run(args, **kwargs))
        if args[2].endswith("/zip"):
            assert args[2] == "repos/owner/repository/actions/artifacts/10/zip"
            sink = kwargs["stdout"]
            paths.append(Path(sink.name))
            sink.write(content + b"changed" if kind == "digest" else content)
            return subprocess.CompletedProcess(
                args, int(kind == "download"), stderr=b"fixture failure"
            )
        return subprocess.CompletedProcess(args, 0, stdout=remote(args, "fixture API"), stderr="")

    monkeypatch.setattr(subprocess, "run", service)
    return reference, paths


@pytest.mark.parametrize("kind", ["healthy", "digest", "malformed", "unsafe", "download"])
def test_wrapper_storage_is_removed_after_success_or_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, kind: str
) -> None:
    reference, paths = wrapper_fixture(tmp_path, monkeypatch, kind=kind)
    destination = tmp_path / "dist"
    if kind == "healthy":
        promotion.download_actions_artifact(reference, destination)
        assert (destination / "candidate.json").read_bytes() == b"reviewed bytes"
    else:
        with pytest.raises(ValueError):
            promotion.download_actions_artifact(reference, destination)
    assert len(paths) == 1
    assert not paths[0].exists()
    assert not (tmp_path / "dist.zip").exists()
    assert not (tmp_path / "escaped").exists()
    assert _git(tmp_path, "status", "--porcelain", "--untracked-files=normal") == ""


def test_fetch_artifact_cli_preserves_publication_cleanliness_and_sibling_files(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    reference, paths = wrapper_fixture(tmp_path, monkeypatch)
    monkeypatch.chdir(tmp_path)
    for name, value in {
        "GITHUB_REPOSITORY": "owner/repository",
        "GITHUB_SHA": reference.producer.source_sha,
        "GITHUB_RUN_ID": "100",
        "GITHUB_RUN_ATTEMPT": "2",
    }.items():
        monkeypatch.setenv(name, value)
    # Distinct destinations with the same stem used to share the same wrapper path.
    sibling = tmp_path / "dist.zip"
    sibling.write_bytes(b"existing operator file")
    _git(tmp_path, "add", "dist.zip")
    _git(tmp_path, "commit", "-qm", "fixture: preserve sibling")
    sha = _git(tmp_path, "rev-parse", "HEAD")
    for output in ("dist", "dist/review.one", "dist/review.two"):
        result = CliRunner().invoke(
            automation_cli.app,
            [
                "fetch-artifact",
                "--source-sha",
                reference.producer.source_sha,
                "--artifact-id",
                "10",
                "--name",
                reference.name,
                "--digest",
                reference.digest.sha256,
                "--output-dir",
                output,
                "--output-ref",
                f"{output}/artifact-ref.json",
            ],
        )
        assert result.exit_code == 0, result.output
        assert (tmp_path / output / "candidate.json").read_bytes() == b"reviewed bytes"
        assert json.loads((tmp_path / output / "artifact-ref.json").read_bytes())["id"] == 10
        publication._checkout(tmp_path, sha)  # pyright: ignore[reportPrivateUsage]
    assert sibling.read_bytes() == b"existing operator file"
    assert len(set(paths)) == 3
    assert all(not path.exists() for path in paths)
    sibling.write_bytes(b"unreviewed change")
    with pytest.raises(ValueError, match="clean checkout"):
        publication._checkout(tmp_path, sha)  # pyright: ignore[reportPrivateUsage]
