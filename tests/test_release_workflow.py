"""Actions adapters use fixture services and never upload during recovery."""

from __future__ import annotations

import importlib
import importlib.util
import json
import subprocess
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from election_guide.release.automation_models import PublicationResult
from tests.test_release_evidence import (
    BOT,
    evidence_setup,  # noqa: F401 # pyright: ignore[reportUnusedImport]
    operation,
    promotion_setup,  # noqa: F401 # pyright: ignore[reportUnusedImport]
    setup_publication,  # noqa: F401 # pyright: ignore[reportUnusedImport]
)


def constant(value: Any) -> Callable[..., Any]:
    def result(*args: Any, **kwargs: Any) -> Any:
        return value

    return result


def adapter() -> Any:
    assert importlib.util.find_spec("election_guide.release.workflow") is not None, (
        "Actions adapter is missing"
    )
    return importlib.import_module("election_guide.release.workflow")


def test_source_capture_requires_full_exact_checkout(monkeypatch: pytest.MonkeyPatch) -> None:
    module = adapter()
    monkeypatch.setattr(module, "git", constant("a" * 40))
    assert module.capture_source(Path("."), "a" * 40) == "a" * 40
    for source in ["a" * 7, "b" * 40, "main", "HEAD"]:
        with pytest.raises(ValueError):
            module.capture_source(Path("."), source)


@pytest.mark.parametrize(
    "enabled,allowed,state",
    [(True, True, "eligible"), (False, True, "deployment_paused"), (True, False, "superseded")],
)
def test_upload_admission_preserves_paused_and_superseded_evidence(
    evidence_setup: tuple[Any, ...],  # noqa: F811
    monkeypatch: pytest.MonkeyPatch,
    enabled: bool,
    allowed: bool,
    state: str,
) -> None:
    module = adapter()
    evidence, api, resolved, publication, _, root = evidence_setup
    evidence.retain_evidence(operation(publication), issue_number=550, reports={})
    monkeypatch.setattr(module, "latest_production_receipt", constant(None))
    monkeypatch.setattr(module, "promotion_allowed", constant(allowed))
    monkeypatch.setattr(module, "deployment_rows", constant([]))
    result = module.admit_upload(
        publication, selected=resolved.site, enabled=enabled, output_dir=root / "delivery"
    )
    assert result == state
    if state != "eligible":
        receipt = json.loads((root / "delivery/operation.json").read_bytes())
        assert receipt["state"] == state and receipt["upload"] is None
    assert api.deployments[0]["id"] == 50


def test_admission_never_reuploads_an_existing_attempt(
    evidence_setup: tuple[Any, ...],  # noqa: F811
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = adapter()
    evidence, api, resolved, publication, _, root = evidence_setup
    evidence.retain_evidence(operation(publication), issue_number=550, reports={})
    monkeypatch.setattr(module, "latest_production_receipt", constant(None))
    monkeypatch.setattr(module, "promotion_allowed", constant(True))
    monkeypatch.setattr(module, "deployment_rows", constant(api.deployments))
    with pytest.raises(ValueError, match="verification-only"):
        module.admit_upload(
            publication, selected=resolved.site, enabled=True, output_dir=root / "delivery"
        )


@pytest.mark.parametrize("exit_code", [0, 1])
def test_single_upload_retains_output_and_records_unique_url(
    evidence_setup: tuple[Any, ...],  # noqa: F811
    monkeypatch: pytest.MonkeyPatch,
    exit_code: int,
) -> None:
    module = adapter()
    evidence, _, _, publication, upload, root = evidence_setup
    evidence.retain_evidence(operation(publication), issue_number=550, reports={})
    monkeypatch.setattr(module, "current_producer", constant(upload.producer))
    calls: list[Any] = []

    def run(command: list[str], **kwargs: Any) -> Any:
        calls.append(command)
        return subprocess.CompletedProcess(
            command, exit_code, "Success! https://abc123.example.pages.dev\n", "warning\n"
        )

    monkeypatch.setattr(module.subprocess, "run", run)

    def record_status(*args: Any, **kwargs: Any) -> None:
        calls.append("status")

    monkeypatch.setattr(module, "write_deployment_status", record_status)
    directory = root / "upload"
    if exit_code:
        with pytest.raises(ValueError, match="uncertain"):
            module.perform_upload(
                publication, deployment_id=50, site_dir=root / "site", output_dir=directory
            )
    else:
        result = module.perform_upload(
            publication, deployment_id=50, site_dir=root / "site", output_dir=directory
        )
        assert result.deployment_url == upload.deployment_url
        assert calls[-1] == "status"
        assert (directory / "upload.json").is_file()
    assert sum(isinstance(c, list) for c in calls) == 1
    report = json.loads((directory / "upload-report.json").read_bytes())
    assert report["returncode"] == exit_code and report["stderr"] == "warning\n"
    assert report["producer"] == upload.producer.model_dump(mode="json")


def test_verification_recovery_keeps_original_upload_producer(
    evidence_setup: tuple[Any, ...],  # noqa: F811
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = adapter()
    evidence, _, _, publication, upload, _ = evidence_setup
    evidence.retain_evidence(operation(publication), issue_number=550, reports={})
    evidence.retain_evidence(
        operation(publication, phase="deployment", upload=upload), issue_number=550, reports={}
    )

    def never(*args: Any, **kwargs: Any) -> Any:
        raise AssertionError("verification must not upload or relabel the producer")

    monkeypatch.setattr(module, "perform_upload", never)
    monkeypatch.setattr(module, "current_producer", never)
    recovered = module.recover_upload(
        repository=upload.producer.repository,
        issue=550,
        release_version=publication.published.candidate.declaration.release_version,
        source_sha=upload.source_sha,
        run_id=upload.producer.run_id,
        run_attempt=upload.producer.run_attempt,
    )
    assert recovered == upload


def next_attempt(publication: Any) -> Any:
    document = publication.model_dump(mode="json")
    candidate = document["published"]["candidate"]
    candidate["producer"]["run_attempt"] += 1
    refs = [
        candidate["release_artifact"],
        candidate["site_artifact"],
        document["published"]["candidate_artifact"],
        document["promotion_artifact"],
    ]
    for ref in refs:
        ref["producer"] = dict(candidate["producer"])
        ref["id"] += 100
        ref["name"] = ref["name"].rsplit("-", 1)[0] + f"-{candidate['producer']['run_attempt']}"
    return PublicationResult.model_validate_json(json.dumps(document))


def test_new_attempt_requires_its_own_durable_receipt(evidence_setup: tuple[Any, ...]) -> None:  # noqa: F811
    evidence, _, _, publication, _, _ = evidence_setup
    evidence.retain_evidence(operation(publication), issue_number=550, reports={})
    fresh = next_attempt(publication)
    with pytest.raises(ValueError, match="durable publication evidence"):
        evidence.require_publication_evidence(fresh)
    evidence.retain_evidence(
        operation(fresh, producer=fresh.published.candidate.producer), issue_number=550, reports={}
    )
    evidence.require_publication_evidence(fresh)
    evidence.require_publication_evidence(publication)


def test_success_status_retry_does_not_reorder_old_production(
    evidence_setup: tuple[Any, ...],  # noqa: F811
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = adapter()
    _, api, _, publication, upload, _ = evidence_setup
    monkeypatch.setattr(module, "read_object", constant(api.deployments[0]))
    monkeypatch.setattr(
        module,
        "read_rows",
        constant(
            [
                {
                    "id": 100,
                    "creator": BOT,
                    "state": "success",
                    "environment_url": upload.deployment_url,
                },
                {
                    "id": 200,
                    "creator": BOT,
                    "state": "inactive",
                    "environment_url": upload.deployment_url,
                },
            ]
        ),
    )

    def never(*args: Any, **kwargs: Any) -> Any:
        raise AssertionError("old success must not be posted again")

    monkeypatch.setattr(module, "post_object", never)
    module.write_deployment_status(publication, 50, state="success", url=upload.deployment_url)


def test_delivery_cli_failure_retains_failed_operation(
    evidence_setup: tuple[Any, ...],  # noqa: F811
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from typer.testing import CliRunner

    from election_guide.release import automation_cli
    from election_guide.serialization import canonical_json_bytes

    _, _, _, publication, _, root = evidence_setup
    path = root / "publication.json"
    path.write_bytes(canonical_json_bytes(publication.model_dump(mode="json")))

    def failed(*args: Any, **kwargs: Any) -> Any:
        raise ValueError("fixture selection lookup failed")

    monkeypatch.setattr(automation_cli, "_selected_main", failed)
    result = CliRunner().invoke(
        automation_cli.app,
        ["delivery-check", "--publication", str(path), "--output-dir", str(root / "failed")],
    )
    assert result.exit_code == 1
    receipt = json.loads((root / "failed/operation.json").read_bytes())
    assert receipt["state"] == "failed" and receipt["upload"] is None
    assert "selection lookup failed" in receipt["error"]


def test_unverified_older_upload_blocks_another_release(
    evidence_setup: tuple[Any, ...],  # noqa: F811
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = adapter()
    _, api, _, publication, _, _ = evidence_setup
    monkeypatch.setattr(module, "read_rows", constant(api.deployments))
    gate = getattr(module, "require_no_unverified_uploads", None)
    assert callable(gate), "any unresolved owned upload must block new uploads"
    with pytest.raises(ValueError, match="verification-only"):
        gate(publication.published.candidate.producer.repository)


@pytest.mark.parametrize("same_time", [False, True])
def test_late_first_success_cannot_reorder_actual_uploads(
    evidence_setup: tuple[Any, ...],  # noqa: F811
    monkeypatch: pytest.MonkeyPatch,
    same_time: bool,
) -> None:
    from datetime import timedelta

    from tests.test_release_promotion import receipt

    evidence, api, _, publication, upload, _ = evidence_setup
    original = receipt(publication)
    text = publication.model_dump_json().replace(upload.source_sha, "b" * 40)
    version = publication.published.candidate.declaration.release_version
    newer = PublicationResult.model_validate_json(text.replace(version, version + "0"))
    recent = receipt(newer)
    assert recent.upload is not None and original.upload is not None
    recent = recent.model_copy(
        update={
            "upload": recent.upload.model_copy(
                update={
                    "github_deployment_id": 51,
                    "uploaded_at": original.upload.uploaded_at
                    + timedelta(seconds=0 if same_time else 60),
                }
            )
        }
    )
    api.deployments.append(
        {
            "id": 51,
            "creator": BOT,
            "environment": "production",
            "sha": recent.producer.source_sha,
            "payload": evidence.deployment_payload(newer),
        }
    )
    # The old upload's FIRST success was delayed until after the newer upload's success.
    api.statuses[50] = [{"id": 200, "creator": BOT, "state": "success"}]
    api.statuses[51] = [{"id": 100, "creator": BOT, "state": "success"}]

    def retained(**kwargs: Any) -> tuple[Any, ...]:
        return (original,) if kwargs["source_sha"] == original.producer.source_sha else (recent,)

    monkeypatch.setattr(evidence, "load_verified_receipts", retained)
    assert evidence.latest_production_receipt(upload.producer.repository) == recent


def test_latest_production_rejects_conflicting_upload_time(
    evidence_setup: tuple[Any, ...],  # noqa: F811
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from datetime import timedelta

    from tests.test_release_promotion import receipt

    evidence, api, _, publication, upload, _ = evidence_setup
    original = receipt(publication)
    assert original.upload is not None
    conflict = original.model_copy(
        update={
            "upload": original.upload.model_copy(
                update={"uploaded_at": original.upload.uploaded_at + timedelta(seconds=1)}
            )
        }
    )
    api.statuses[50] = [{"id": 200, "creator": BOT, "state": "success"}]
    monkeypatch.setattr(evidence, "load_verified_receipts", constant((original, conflict)))
    with pytest.raises(ValueError, match="upload identity/time"):
        evidence.latest_production_receipt(upload.producer.repository)


def retained_upload_artifact(
    setup: tuple[Any, ...], monkeypatch: pytest.MonkeyPatch, directory: Path
) -> dict[str, Any]:
    """Serve real wrapper bytes through the existing artifact/attempt validators."""
    import hashlib
    import io
    import zipfile

    from election_guide.hosting import promotion
    from election_guide.release.automation_models import ArtifactRef, FileDigest
    from tests.test_release_promotion import AdmissionAPI, artifact_metadata

    _, api, _, publication, _, _ = setup
    candidate = publication.published.candidate
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        for path in directory.iterdir():
            archive.writestr(path.name, path.read_bytes())
    wrapper = buffer.getvalue()
    reference = ArtifactRef(
        id=14,
        name=f"upload-{candidate.producer.run_id}-{candidate.producer.run_attempt}",
        digest=FileDigest(sha256=hashlib.sha256(wrapper).hexdigest(), size=len(wrapper)),
        producer=candidate.producer,
    )
    metadata = artifact_metadata(candidate, reference)
    metadata["expired"] = False
    attempts = AdmissionAPI(candidate.source_sha)
    observed: dict[str, Any] = {"metadata": metadata, "wrapper": wrapper, "downloads": []}

    def gh(command: list[str], failure: str) -> str:
        endpoint = command[2]
        if endpoint.endswith("/artifacts?per_page=100"):
            return json.dumps([{"artifacts": [metadata]}])
        if "/actions/artifacts/" in endpoint:
            assert endpoint.endswith("/14")
            return json.dumps(metadata)
        if "/actions/" in endpoint:
            return attempts(command, failure)
        if "/statuses" in endpoint and "--method" in command:
            payload = json.loads(Path(command[command.index("--input") + 1]).read_bytes())
            status = {**payload, "id": len(api.statuses[50]) + 1, "creator": BOT}
            api.statuses[50].append(status)
            return json.dumps(status)
        return api.run(command, failure)

    def download(command: list[str], destination: Path, failure: str) -> None:
        assert command[2].endswith("/actions/artifacts/14/zip")
        observed["downloads"].append(reference.id)
        destination.write_bytes(observed["wrapper"])

    monkeypatch.setattr(adapter(), "run_gh", gh)
    monkeypatch.setattr(promotion, "run_gh", gh)
    monkeypatch.setattr(promotion, "download_gh", download)
    return observed


def test_successful_upload_status_failure_recovers_without_another_upload(
    evidence_setup: tuple[Any, ...],  # noqa: F811
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from typer.testing import CliRunner

    from election_guide.release import automation_cli
    from election_guide.release.automation_models import UploadReceipt
    from tests.test_release_evidence import successful_report

    module = adapter()
    evidence, api, _, publication, original, root = evidence_setup
    evidence.retain_evidence(operation(publication), issue_number=550, reports={})
    monkeypatch.setattr(module, "run_gh", api.run)
    monkeypatch.setattr(module, "current_producer", constant(original.producer))
    real_run: Callable[..., subprocess.CompletedProcess[Any]] = subprocess.run
    uploads: list[list[str]] = []

    def run(command: list[str], **kwargs: Any) -> Any:
        if command[:3] == ["npm", "run", "pages:deploy"]:
            uploads.append(command)
            return subprocess.CompletedProcess(command, 0, original.deployment_url, "warning")
        return real_run(command, **kwargs)

    monkeypatch.setattr(module.subprocess, "run", run)
    directory = root / "upload"
    publication_path, deployment_path = root / "publication.json", root / "deployment.json"
    publication_path.write_text(publication.model_dump_json())
    deployment_path.write_text('{"id":50}')

    def unavailable(*args: Any, **kwargs: Any) -> Any:
        raise ValueError("initial status write unavailable")

    runner = CliRunner()
    with monkeypatch.context() as status_failure:
        status_failure.setattr(module, "post_object", unavailable)
        result = runner.invoke(
            automation_cli.app,
            [
                "upload",
                "--publication",
                str(publication_path),
                "--deployment",
                str(deployment_path),
                "--site-dir",
                str(root / "dist/site"),
                "--output-dir",
                str(directory),
            ],
        )
    assert result.exit_code == 1 and "initial status write unavailable" in result.output
    assert api.statuses[50] == []
    # The receipt must survive the failed metadata request, alongside the report.
    saved = UploadReceipt.model_validate_json((directory / "upload.json").read_bytes())
    assert saved.producer == original.producer and saved.source_sha == original.source_sha
    report = json.loads((directory / "upload-report.json").read_bytes())
    assert saved.uploaded_at.isoformat() == report["uploaded_at"]
    # Exercise the normal failed-operation consumer before verification-only recovery.
    retained = runner.invoke(
        automation_cli.app, ["retain-operation", "--receipt", str(directory / "operation.json")]
    )
    assert retained.exit_code == 0, retained.output
    artifact = retained_upload_artifact(evidence_setup, monkeypatch, directory)
    recovered_path = root / "recovered.json"
    recovered = runner.invoke(
        automation_cli.app,
        [
            "recover-upload",
            "--repository",
            original.producer.repository,
            "--issue",
            "550",
            "--release-version",
            publication.published.candidate.declaration.release_version,
            "--source-sha",
            original.source_sha,
            "--run-id",
            str(original.producer.run_id),
            "--run-attempt",
            str(original.producer.run_attempt),
            "--output",
            str(recovered_path),
        ],
    )
    assert recovered.exit_code == 0, recovered.output
    assert artifact["downloads"] == [14]
    assert UploadReceipt.model_validate_json(recovered_path.read_bytes()) == saved
    verification_producer = original.producer.model_copy(
        update={"run_id": 201, "workflow_sha": "f" * 40}
    )
    monkeypatch.setattr(evidence, "current_producer", constant(verification_producer))
    probes: list[bool] = []

    def probe(*args: Any, **kwargs: Any) -> Any:
        probes.append(True)
        return successful_report(evidence_setup)

    monkeypatch.setattr(evidence, "wait_for_production", probe)
    for _ in range(2):
        result = runner.invoke(
            automation_cli.app,
            ["finalize", "--upload", str(recovered_path), "--output-dir", str(root / "finalized")],
        )
        assert result.exit_code == 0, result.output
        status = runner.invoke(
            automation_cli.app, ["deployment-status", "--upload", str(recovered_path)]
        )
        assert status.exit_code == 0, status.output
    assert len(uploads) == len(probes) == len(api.statuses[50]) == 1
    assert api.statuses[50][0]["state"] == "success"
    assert evidence.latest_production_receipt(original.producer.repository).upload == saved


@pytest.mark.parametrize(
    "case",
    [
        "absent-status",
        "report-only",
        "matching-status",
        "conflicting-status",
        "wrong-host-status",
        "path-status",
        "alias-status",
        "ambiguous-status",
        "foreign-status",
        "failed-status",
        "failed-upload",
        "ambiguous-output",
        "missing-url",
        "conflicting-receipt",
        "foreign-producer",
        "wrong-wrapper",
        "wrong-attempt",
    ],
)
def test_upload_recovery_authenticates_retained_evidence(
    evidence_setup: tuple[Any, ...],  # noqa: F811
    monkeypatch: pytest.MonkeyPatch,
    case: str,
) -> None:
    module = adapter()
    evidence, api, _, publication, upload, root = evidence_setup
    evidence.retain_evidence(operation(publication), issue_number=550, reports={})
    directory = root / "retained"
    directory.mkdir()
    report: dict[str, Any] = {
        "producer": upload.producer.model_dump(mode="json"),
        "github_deployment_id": 50,
        "source_sha": upload.source_sha,
        "uploaded_at": upload.uploaded_at.isoformat(),
        "returncode": 0,
        "stdout": upload.deployment_url,
        "stderr": "",
    }
    other_url = "https://def456.example.pages.dev"
    if case.endswith("status") and case != "absent-status":
        api.statuses[50] = [
            {
                "id": 1,
                "creator": BOT,
                "state": "in_progress",
                "environment_url": upload.deployment_url,
            }
        ]
    if case == "conflicting-status":
        api.statuses[50][0]["environment_url"] = other_url
    elif case in {"wrong-host-status", "path-status", "alias-status"}:
        api.statuses[50][0]["environment_url"] = {
            "wrong-host-status": "https://abc123.other.pages.dev/",
            "path-status": upload.deployment_url + "guide",
            "alias-status": "https://example.pages.dev/",
        }[case]
    elif case == "ambiguous-status":
        api.statuses[50].append({**api.statuses[50][0], "id": 2, "environment_url": other_url})
    elif case == "foreign-status":
        api.statuses[50][0]["creator"] = {**BOT, "id": 1}
    elif case == "failed-status":
        api.statuses[50][0]["state"] = "failure"
    elif case == "failed-upload":
        report["returncode"] = 1
    elif case == "ambiguous-output":
        report["stdout"] += " " + other_url
    elif case == "missing-url":
        report["stdout"] = ""
    elif case == "foreign-producer":
        report["producer"]["run_id"] += 1
    if case != "report-only":
        receipt = upload.model_dump(mode="json")
        if case == "conflicting-receipt":
            receipt["uploaded_at"] = "2026-10-16T01:00:00Z"
        (directory / "upload.json").write_text(json.dumps(receipt))
    (directory / "upload-report.json").write_text(json.dumps(report))
    artifact = retained_upload_artifact(evidence_setup, monkeypatch, directory)
    if case == "wrong-wrapper":
        artifact["wrapper"] += b"different bytes"
    elif case == "wrong-attempt":
        artifact["metadata"]["created_at"] = "2026-10-16T11:59:59Z"

    def recover() -> Any:
        return module.recover_upload(
            repository=upload.producer.repository,
            issue=550,
            release_version=publication.published.candidate.declaration.release_version,
            source_sha=upload.source_sha,
            run_id=upload.producer.run_id,
            run_attempt=upload.producer.run_attempt,
        )

    if case in {"absent-status", "report-only", "matching-status"}:
        assert recover() == upload
        assert artifact["downloads"] == [14]
    else:
        with pytest.raises(ValueError):
            recover()


@pytest.fixture
def captured_artifact_service(monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    """Replace only external gh processes; retain the real identity validators."""
    from election_guide.hosting import promotion
    from election_guide.release.automation_models import Producer
    from tests.test_release_promotion import AdmissionAPI

    producer = Producer(
        repository="owner/repository",
        source_sha="a" * 40,
        workflow_sha="a" * 40,
        run_id=100,
        run_attempt=2,
    )
    metadata = {
        "id": 13,
        "name": "promotion-100-2",
        "size_in_bytes": 19,
        "digest": "sha256:" + "b" * 64,
        "expired": False,
        "created_at": "2026-10-16T12:30:00Z",
        "workflow_run": {"id": 100, "head_sha": "a" * 40, "head_branch": "main"},
    }
    endpoint = "repos/owner/repository/actions/artifacts/13"
    api = AdmissionAPI("a" * 40)
    state: dict[str, Any] = {
        "producer": producer,
        "metadata": metadata,
        "api": api,
        "endpoint": endpoint,
        "reads": [],
        "failures": [],
        "delays": [],
        "returncode": 1,
    }

    def run(command: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        assert command[:2] == ["gh", "api"] and len(command) == 3
        if command[2] == endpoint:
            state["reads"].append(command[2])
            failure = state["failures"].pop(0) if state["failures"] else None
            if failure is not None:
                return subprocess.CompletedProcess(command, state["returncode"], "", failure)
            payload = state.get("payload", json.dumps(metadata))
        else:
            payload = api(command, "fixture")
        return subprocess.CompletedProcess(command, 0, payload, "")

    monkeypatch.setattr(subprocess, "run", run)
    monkeypatch.setattr(adapter(), "sleep", state["delays"].append, raising=False)
    # Both layers call the shared real run_gh; no validator is replaced.
    assert promotion.run_gh is adapter().run_gh
    return state


def capture_fixture_artifact(state: dict[str, Any]) -> Any:
    return adapter().capture_artifact(
        retry_visibility=True,
        producer=state["producer"],
        artifact_id=13,
        name="promotion-100-2",
        digest="sha256:" + "b" * 64,
    )


@pytest.mark.parametrize("failures,reads,delays", [(1, 3, [5.0]), (2, 4, [5.0, 10.0])])
def test_capture_new_artifact_recovers_visibility_404_without_changing_identity(
    captured_artifact_service: dict[str, Any], failures: int, reads: int, delays: list[float]
) -> None:
    state = captured_artifact_service
    state["failures"] = ["gh: Not Found (HTTP 404)"] * failures
    result = capture_fixture_artifact(state)
    assert result.id == 13 and result.name == "promotion-100-2"
    assert result.producer.repository == "owner/repository"
    assert result.producer.source_sha == "a" * 40
    assert result.producer.run_id == 100 and result.producer.run_attempt == 2
    assert result.digest.size == 19 and result.digest.sha256 == "b" * 64
    assert state["reads"] == [state["endpoint"]] * reads
    assert state["delays"] == delays


def test_capture_new_artifact_exhaustion_stops_after_three_reads(
    captured_artifact_service: dict[str, Any],
) -> None:
    from election_guide.github_cli import GitHubCliError

    state = captured_artifact_service
    state["failures"] = ["gh: Not Found (HTTP 404)"] * 5
    with pytest.raises(GitHubCliError, match="Not Found") as error:
        capture_fixture_artifact(state)
    assert error.value.returncode == 1 and error.value.stderr == "gh: Not Found (HTTP 404)"
    assert len(state["reads"]) == 3 and len(state["failures"]) == 2
    assert state["delays"] == [5.0, 10.0]


@pytest.mark.parametrize("status", [401, 403, 429, 500])
def test_capture_new_artifact_does_not_retry_other_http_errors(
    captured_artifact_service: dict[str, Any], status: int
) -> None:
    from election_guide.github_cli import GitHubCliError

    state = captured_artifact_service
    state["failures"] = [f"gh: request failed (HTTP {status})"]
    with pytest.raises(GitHubCliError, match=str(status)):
        capture_fixture_artifact(state)
    assert len(state["reads"]) == 1 and state["delays"] == []


def test_capture_new_artifact_does_not_retry_other_exit_status(
    captured_artifact_service: dict[str, Any],
) -> None:
    from election_guide.github_cli import GitHubCliError

    state = captured_artifact_service
    state["returncode"] = 2
    state["failures"] = ["gh: Not Found (HTTP 404)"]
    with pytest.raises(GitHubCliError):
        capture_fixture_artifact(state)
    assert len(state["reads"]) == 1 and state["delays"] == []


@pytest.mark.parametrize("payload", ["{", "[]"])
def test_capture_new_artifact_does_not_retry_malformed_metadata(
    captured_artifact_service: dict[str, Any], payload: str
) -> None:
    state = captured_artifact_service
    state["payload"] = payload
    with pytest.raises(ValueError):
        capture_fixture_artifact(state)
    assert len(state["reads"]) == 1 and state["delays"] == []


def test_capture_new_artifact_does_not_retry_an_error_message_lookalike(
    monkeypatch: pytest.MonkeyPatch, captured_artifact_service: dict[str, Any]
) -> None:
    seen: list[str] = []

    def read(endpoint: str) -> dict[str, Any]:
        seen.append(endpoint)
        raise ValueError("could not read Actions delivery metadata: gh: Not Found (HTTP 404)")

    monkeypatch.setattr(adapter(), "read_object", read)
    with pytest.raises(ValueError, match="Not Found"):
        capture_fixture_artifact(captured_artifact_service)
    assert len(seen) == 1 and captured_artifact_service["delays"] == []


@pytest.mark.parametrize(
    "bad",
    [
        "id",
        "name",
        "digest",
        "run",
        "source",
        "branch",
        "expired",
        "created",
        "repository",
        "attempt",
    ],
)
def test_capture_visibility_retry_still_rejects_wrong_identity(
    captured_artifact_service: dict[str, Any], bad: str
) -> None:
    state = captured_artifact_service
    state["failures"] = ["gh: Not Found (HTTP 404)"]
    metadata = state["metadata"]
    if bad == "id":
        metadata["id"] = 14
    elif bad == "name":
        metadata["name"] = "promotion-999-2"
    elif bad == "digest":
        metadata["digest"] = "sha256:" + "c" * 64
    elif bad == "run":
        metadata["workflow_run"]["id"] = 101
    elif bad == "source":
        metadata["workflow_run"]["head_sha"] = "c" * 40
    elif bad == "branch":
        metadata["workflow_run"]["head_branch"] = "other"
    elif bad == "expired":
        metadata["expired"] = True
    elif bad == "created":
        metadata["created_at"] = "2026-10-16T11:59:59Z"
    elif bad == "repository":
        state["api"].run["repository"]["full_name"] = "another/repository"
    else:
        state["api"].run["run_attempt"] = 3
    with pytest.raises(ValueError, match="artifact"):
        capture_fixture_artifact(state)
    assert len(state["reads"]) == 3 and state["delays"] == [5.0]


def test_capture_visibility_retry_never_restarts_strict_validation(
    captured_artifact_service: dict[str, Any],
) -> None:
    state = captured_artifact_service
    state["failures"] = ["gh: Not Found (HTTP 404)", None, "gh: Not Found (HTTP 404)"]
    with pytest.raises(ValueError, match="missing or expired"):
        capture_fixture_artifact(state)
    assert len(state["reads"]) == 3 and state["delays"] == [5.0]


def test_capture_existing_artifact_lookup_keeps_fail_fast_behavior(
    captured_artifact_service: dict[str, Any],
) -> None:
    from election_guide.github_cli import GitHubCliError

    state = captured_artifact_service
    state["failures"] = ["gh: Not Found (HTTP 404)"]
    with pytest.raises(GitHubCliError, match="Not Found"):
        adapter().capture_artifact(
            producer=state["producer"],
            artifact_id=13,
            name="promotion-100-2",
            digest="sha256:" + "b" * 64,
        )
    assert len(state["reads"]) == 1 and state["delays"] == []


def test_fresh_capture_cli_opts_into_metadata_visibility_wait(
    captured_artifact_service: dict[str, Any], monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    from typer.testing import CliRunner

    from election_guide.cli import app

    state = captured_artifact_service
    state["failures"] = ["gh: Not Found (HTTP 404)"]
    for name, value in {
        "GITHUB_REPOSITORY": "owner/repository",
        "GITHUB_SHA": "a" * 40,
        "GITHUB_RUN_ID": "100",
        "GITHUB_RUN_ATTEMPT": "2",
    }.items():
        monkeypatch.setenv(name, value)
    output = tmp_path / "captured.json"
    result = CliRunner().invoke(
        app,
        [
            "release",
            "automation",
            "capture-artifact",
            "--source-sha",
            "a" * 40,
            "--artifact-id",
            "13",
            "--name",
            "promotion-100-2",
            "--digest",
            "sha256:" + "b" * 64,
            "--output",
            str(output),
        ],
    )
    assert result.exit_code == 0, result.output
    captured = json.loads(output.read_bytes())
    assert captured["id"] == 13 and captured["producer"]["run_attempt"] == 2
    assert len(state["reads"]) == 3 and state["delays"] == [5.0]
