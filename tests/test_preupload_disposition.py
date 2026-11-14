"""A proved pre-upload intent remains evidence, not a permanent upload deadlock."""

from __future__ import annotations

import base64
import copy
import hashlib
import io
import json
import zipfile
from pathlib import Path
from typing import Any, cast

import pytest
from typer.testing import CliRunner

from election_guide.serialization import canonical_json_bytes
from tests.test_release_evidence import (
    evidence_setup,  # noqa: F401 # pyright: ignore[reportUnusedImport]
    operation,
    promotion_setup,  # noqa: F401 # pyright: ignore[reportUnusedImport]
    setup_publication,  # noqa: F401 # pyright: ignore[reportUnusedImport]
)

UPLOADER_BLOBS = {
    ".github/workflows/ci.yml": "5b3926bf75720a33ac1e7c3084543d6bbf999b43",
    "src/election_guide/release/workflow.py": "e220e0c1e2d455e0a4d679909010a214cae8fe72",
    "package.json": "537fe9ce0a38520d51664a0c5ead5fc3cbdb3ea2",
    "package-lock.json": "d1b379f8a5dc6f049b984d45df822bd120b1efeb",
    "wrangler.jsonc": "a1c9454057648636ea1f836d0341d7163263f6b3",
}
DISPOSITION_ERROR = "proved pre-upload failure; original intent retained"
ORIGINAL_ERROR = "upload outcome uncertain; operator verification is required before any new upload"


@pytest.fixture
def disposed_intent(
    evidence_setup: tuple[Any, ...],  # noqa: F811
    monkeypatch: pytest.MonkeyPatch,
    request: pytest.FixtureRequest,
) -> tuple[Any, ...]:
    from election_guide.release import workflow

    evidence, api, resolved, publication, _, root = evidence_setup
    original = publication.published.candidate.producer
    source = original.source_sha
    damage = getattr(request, "param", "none")
    issuer = original.model_copy(update={"workflow_sha": "b" * 40, "run_id": 200, "run_attempt": 1})
    report: dict[str, Any] = {
        "producer": original.model_dump(mode="json"),
        "source_sha": source,
        "github_deployment_id": 50,
        "returncode": 1,
        "uploaded_at": "2026-10-16T12:00:00+00:00",
        "stdout": (
            "\n> pages:deploy\n"
            "> wrangler pages deploy --branch=${PAGES_BRANCH:-main} "
            f"dist/cloudflare-site --commit-hash={source} --commit-dirty=false\n\n"
            " ⛅️ wrangler 4.158.0\n────────────────────\n\n"
        ),
        "stderr": (
            "✘ [ERROR] Received a malformed response from the API\n\n"
            "  upstream connect error or disconnect/reset before headers. reset reason: "
            "remote connection failure, ... (length = 167)\n"
            "  GET /accounts/0123456789abcdef0123456789abcdef/pages/projects/"
            "seattle-elections -> 503 Service Unavailable\n"
            "  Cloudflare Ray ID: 0123456789abcdef-MSP\n\n"
            "  If you think this is a bug, please open an issue at: "
            "https://github.com/cloudflare/workers-sdk/issues/new/choose\n\n"
            '🪵  Logs were written to "/home/runner/.config/.wrangler/logs/'
            'wrangler-2026-10-16_12-00-00_000.log"\n'
        ),
    }
    if damage == "success":
        report["returncode"] = 0
    elif damage == "interrupted":
        report["returncode"] = -9
    elif damage == "generic-failure":
        report["stderr"] = "A connection failed at an unknown stage."
    elif damage == "post-write":
        report["stdout"] += "Uploading assets... done\n"
    elif damage == "pages-url":
        report["stdout"] += "https://abc123.seattle-elections.pages.dev\n"
    elif damage == "wrong-report-source":
        report["source_sha"] = "f" * 40
    elif damage == "wrong-report-producer":
        report["producer"] = {**report["producer"], "run_id": 999}
    elif damage == "wrong-report-intent":
        report["github_deployment_id"] = 51
    failed = operation(publication, phase="deployment", state="failed", error=ORIGINAL_ERROR)
    members = {
        "deployment.json": canonical_json_bytes({"id": 50}),
        "upload-report.json": canonical_json_bytes(report),
        "operation.json": canonical_json_bytes(failed.model_dump(mode="json")),
        "finalization-error.json": b'{"error":"upload outcome uncertain"}\n',
        "summary.md": b"Failed upload retained.\n",
    }
    if damage == "upload-receipt":
        members["upload.json"] = b"{}\n"
    elif damage == "unsafe-path":
        members["../outside"] = b"unsafe\n"
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, content in members.items():
            archive.writestr(name, content)
        if damage == "duplicate-member":
            with pytest.warns(UserWarning, match="Duplicate name"):
                archive.writestr("upload-report.json", members["upload-report.json"])
    wrapper = stream.getvalue()
    ref: dict[str, Any] = {
        "schema_version": "1.0",
        "id": 70,
        "name": f"upload-{original.run_id}-{original.run_attempt}",
        "digest": {
            "schema_version": "1.0",
            "sha256": hashlib.sha256(wrapper).hexdigest(),
            "size": len(wrapper),
        },
        "producer": original.model_dump(mode="json"),
    }
    metadata: dict[str, Any] = {
        "id": 70,
        "name": ref["name"],
        "digest": "sha256:" + ref["digest"]["sha256"],
        "size_in_bytes": len(wrapper),
        "expired": False,
        "created_at": "2026-10-16T12:00:00Z",
        "workflow_run": {
            "id": original.run_id,
            "head_sha": original.workflow_sha,
            "head_branch": "main",
        },
    }
    if damage == "wrong-artifact-metadata":
        metadata["id"] = 71
    proof: dict[str, Any] = {
        "schema_version": "1.0",
        "kind": "wrangler-4.158.0-project-get-503-v1",
        "producer": issuer.model_dump(mode="json"),
        "publication_sha256": hashlib.sha256(
            canonical_json_bytes(publication.model_dump(mode="json"))
        ).hexdigest(),
        "github_deployment_id": 50,
        "failed_artifact": ref,
        "report_sha256": hashlib.sha256(members["upload-report.json"]).hexdigest(),
        "artifact_metadata_sha256": hashlib.sha256(canonical_json_bytes(metadata)).hexdigest(),
        "uploader_blobs": UPLOADER_BLOBS,
        "uploader_tree": "25653db793a25aaabdcc954410109775cf9cd371",
    }
    if damage == "wrong-proof-digest":
        proof["report_sha256"] = "f" * 64
    elif damage == "wrong-proof-publication":
        proof["publication_sha256"] = "f" * 64
    elif damage == "wrong-proof-producer":
        proof["producer"] = {**proof["producer"], "run_id": 999}
    carrier = operation(
        publication,
        phase="deployment",
        state="failed",
        producer=issuer,
        error=DISPOSITION_ERROR,
    )
    evidence.retain_evidence(operation(publication), issue_number=550, reports={})
    evidence.retain_evidence(failed, issue_number=550, reports={})
    evidence.retain_evidence(
        carrier,
        issue_number=550,
        reports={
            "preupload-disposition.json": canonical_json_bytes(proof),
            "preupload-artifact.json": canonical_json_bytes(
                {"base64": base64.b64encode(wrapper).decode("ascii")}
            ),
            "preupload-artifact-metadata.json": canonical_json_bytes(metadata),
        },
    )
    monkeypatch.setattr(workflow, "run_gh", api.run)
    original_git = workflow.git

    def git(repository: Path, *args: str) -> str:
        if args[0] == "show" and args[-1] in {
            f"{issuer.workflow_sha}:config/hosting/preupload-failure.json",
            f"{'c' * 40}:config/hosting/preupload-failure.json",
        }:
            reviewed_request: dict[str, Any] = {
                "schema_version": "1.0",
                "failed_artifact": copy.deepcopy(ref),
                "github_deployment_id": 50,
                "wrapper_base64": base64.b64encode(wrapper).decode("ascii"),
            }
            if damage == "unbound-issuer-request":
                reviewed_request["failed_artifact"]["id"] = 71
            return json.dumps(reviewed_request)
        if args[0] == "rev-parse" and args[-1].endswith("^{tree}"):
            return (
                "f" * 40
                if damage == "changed-caller"
                else "25653db793a25aaabdcc954410109775cf9cd371"
            )
        if args[0] == "rev-parse" and ":" in args[-1]:
            if damage == "unknown-uploader":
                return "f" * 40
            return UPLOADER_BLOBS[args[-1].split(":", 1)[1]]
        return original_git(repository, *args)

    monkeypatch.setattr(workflow, "git", git)
    original_read = workflow.read_object

    def read_object(endpoint: str) -> dict[str, Any]:
        if endpoint.endswith("/actions/runs/200/attempts/1"):
            return {
                "id": 200,
                "run_attempt": 1,
                "head_sha": "b" * 40,
                "head_branch": "main",
                "event": "pull_request" if damage == "untrusted-issuer" else "push",
                "path": ".github/workflows/ci.yml",
                "repository": {"full_name": original.repository},
            }
        return original_read(endpoint)

    monkeypatch.setattr(workflow, "read_object", read_object)
    return workflow, evidence, api, resolved, publication, issuer, root, proof, wrapper, metadata


def test_proved_preupload_intent_does_not_block_a_distinct_normal_release(
    disposed_intent: tuple[Any, ...],
) -> None:
    workflow, evidence, api, _, publication, _, _, _, _, _ = disposed_intent
    original_rows = copy.deepcopy(api.deployments)
    original_comments = copy.deepcopy(api.comments)

    workflow.require_no_unverified_uploads(publication.published.candidate.producer.repository)

    assert api.deployments == original_rows
    assert api.comments == original_comments
    records = evidence.load_verified_receipts(
        repository=publication.published.candidate.producer.repository,
        issue_number=550,
        release_version=publication.published.candidate.declaration.release_version,
        source_sha=publication.published.candidate.source_sha,
    )
    assert any(record.error == ORIGINAL_ERROR for record in records)
    assert all(record.upload is None and record.state != "verified" for record in records)


@pytest.mark.parametrize(
    "disposed_intent",
    [
        "success",
        "interrupted",
        "generic-failure",
        "post-write",
        "pages-url",
        "wrong-report-source",
        "wrong-report-producer",
        "wrong-report-intent",
        "upload-receipt",
        "unsafe-path",
        "duplicate-member",
        "wrong-artifact-metadata",
        "wrong-proof-digest",
        "wrong-proof-publication",
        "wrong-proof-producer",
        "unknown-uploader",
        "untrusted-issuer",
        "unbound-issuer-request",
    ],
    indirect=True,
)
def test_unproved_or_conflicting_failure_still_blocks_uploads(
    disposed_intent: tuple[Any, ...],
) -> None:
    workflow, _, api, _, publication, _, _, _, _, _ = disposed_intent
    original_rows, original_comments = copy.deepcopy(api.deployments), copy.deepcopy(api.comments)
    with pytest.raises(ValueError):
        workflow.require_no_unverified_uploads(publication.published.candidate.producer.repository)
    assert api.deployments == original_rows and api.comments == original_comments


@pytest.mark.parametrize("disposed_intent", ["changed-caller"], indirect=True)
def test_changed_caller_invalidates_otherwise_matching_uploader_blobs(
    disposed_intent: tuple[Any, ...],
) -> None:
    workflow, _, _, _, publication, _, _, proof, _, _ = disposed_intent
    assert proof["uploader_blobs"] == UPLOADER_BLOBS
    with pytest.raises(ValueError):
        workflow.require_no_unverified_uploads(publication.published.candidate.producer.repository)


def test_disposition_does_not_relax_same_source_admission(
    disposed_intent: tuple[Any, ...], monkeypatch: pytest.MonkeyPatch
) -> None:
    workflow, _, _, resolved, publication, _, root, _, _, _ = disposed_intent

    def latest(repository: str) -> None:
        return None

    def allowed(*args: Any, **kwargs: Any) -> bool:
        return True

    monkeypatch.setattr(workflow, "latest_production_receipt", latest)
    monkeypatch.setattr(workflow, "promotion_allowed", allowed)
    with pytest.raises(ValueError, match="verification-only"):
        workflow.admit_upload(
            publication, selected=resolved.site, enabled=True, output_dir=root / "delivery"
        )
    with pytest.raises(ValueError, match="verification-only"):
        workflow.create_deployment(publication)


@pytest.mark.parametrize("state", ["in_progress", "success", "failure"])
def test_later_original_intent_status_invalidates_disposition(
    disposed_intent: tuple[Any, ...], state: str
) -> None:
    workflow, _, api, _, publication, _, _, _, _, _ = disposed_intent
    from tests.test_release_evidence import BOT

    api.statuses[50] = [
        {"id": 91, "state": state, "creator": BOT, "environment_url": "https://abc.pages.dev"}
    ]
    with pytest.raises(ValueError):
        workflow.require_no_unverified_uploads(publication.published.candidate.producer.repository)


def test_partial_upload_receipt_blocks_even_without_a_completed_seal(
    disposed_intent: tuple[Any, ...],
    evidence_setup: tuple[Any, ...],  # noqa: F811
) -> None:
    workflow, evidence, api, _, publication, _, _, _, _, _ = disposed_intent
    upload = evidence_setup[4]
    evidence.retain_evidence(
        operation(
            publication,
            phase="deployment",
            state="failed",
            upload=upload,
            error="upload completed; status write failed",
        ),
        issue_number=550,
        reports={},
    )
    api.comments.pop()  # Uploaded receipt remains; the final seal did not survive.
    with pytest.raises(ValueError):
        workflow.require_no_unverified_uploads(publication.published.candidate.producer.repository)


def test_later_verified_original_upload_contradicts_disposition(
    disposed_intent: tuple[Any, ...],
    evidence_setup: tuple[Any, ...],  # noqa: F811
) -> None:
    from tests.test_release_evidence import successful_report

    workflow, evidence, _, _, publication, _, _, _, _, _ = disposed_intent
    report = canonical_json_bytes(successful_report(evidence_setup).model_dump())
    evidence.retain_evidence(
        operation(
            publication,
            phase="deployment",
            state="verified",
            upload=evidence_setup[4],
            verification_sha256=hashlib.sha256(report).hexdigest(),
        ),
        issue_number=550,
        reports={"production-wait.json": report},
    )
    with pytest.raises(ValueError):
        workflow.require_no_unverified_uploads(publication.published.candidate.producer.repository)


def test_later_distinct_verified_release_does_not_invalidate_original_disposition(
    disposed_intent: tuple[Any, ...],
    evidence_setup: tuple[Any, ...],  # noqa: F811
) -> None:
    from election_guide.release.automation_models import PublicationResult, UploadReceipt
    from tests.test_release_evidence import BOT, successful_report

    workflow, evidence, api, _, publication, _, _, _, _, _ = disposed_intent
    candidate = publication.published.candidate
    old_version = candidate.declaration.release_version
    prefix, _, suffix = old_version.rpartition(".")
    new_version = f"{prefix}.{int(suffix) + 1}"

    def advance(value: Any) -> Any:
        if isinstance(value, dict):
            return {key: advance(item) for key, item in cast(dict[str, Any], value).items()}
        if isinstance(value, list):
            return [advance(item) for item in cast(list[Any], value)]
        if value == candidate.source_sha:
            return "c" * 40
        if isinstance(value, str):
            return value.replace(old_version, new_version)
        return value

    next_publication = PublicationResult.model_validate_json(
        json.dumps(advance(publication.model_dump(mode="json")))
    )
    uploaded = advance(evidence_setup[4].model_dump(mode="json"))
    uploaded["github_deployment_id"] = 60
    upload = UploadReceipt.model_validate_json(json.dumps(uploaded))
    api.deployments.append(
        {
            "id": 60,
            "creator": BOT,
            "environment": "production",
            "sha": "c" * 40,
            "payload": evidence.deployment_payload(next_publication),
        }
    )
    api.statuses[60] = []
    report = canonical_json_bytes(advance(successful_report(evidence_setup).model_dump()))
    evidence.retain_evidence(operation(next_publication), issue_number=550, reports={})
    evidence.retain_evidence(
        operation(
            next_publication,
            phase="deployment",
            state="verified",
            upload=upload,
            verification_sha256=hashlib.sha256(report).hexdigest(),
        ),
        issue_number=550,
        reports={"production-wait.json": report},
    )
    before = copy.deepcopy(api.comments)
    workflow.require_no_unverified_uploads(candidate.producer.repository)
    assert api.comments == before


def test_durable_proof_survives_temporary_artifact_expiry(
    disposed_intent: tuple[Any, ...], monkeypatch: pytest.MonkeyPatch
) -> None:
    workflow, _, _, _, publication, _, _, _, _, _ = disposed_intent
    from election_guide.hosting import promotion

    def expired(*args: Any, **kwargs: Any) -> None:
        raise ValueError("captured Actions artifact is missing or expired")

    monkeypatch.setattr(promotion, "verify_actions_artifact", expired)
    workflow.require_no_unverified_uploads(publication.published.candidate.producer.repository)


def recovery_request(setup: tuple[Any, ...]) -> dict[str, Any]:
    proof, wrapper = setup[7:9]
    return {
        "schema_version": "1.0",
        "failed_artifact": copy.deepcopy(proof["failed_artifact"]),
        "github_deployment_id": 50,
        "wrapper_base64": base64.b64encode(wrapper).decode("ascii"),
    }


def test_disposition_recording_authenticates_retained_wrapper_without_downloading(
    disposed_intent: tuple[Any, ...], monkeypatch: pytest.MonkeyPatch
) -> None:
    from election_guide.hosting import promotion
    from election_guide.release import preupload

    workflow, _, api, _, publication, issuer, _, proof, _, metadata = disposed_intent
    # Start from the real original failed receipt, with no disposition yet.
    api.comments[:] = [
        comment
        for comment in api.comments
        if json.loads(comment["body"].splitlines()[-1].split(" ", 2)[2][:-4])["producer"]["run_id"]
        != 200
    ]
    original = publication.published.candidate.producer
    run = {
        "id": original.run_id,
        "run_attempt": original.run_attempt,
        "head_sha": original.workflow_sha,
        "head_branch": "main",
        "event": "push",
        "path": ".github/workflows/ci.yml",
        "repository": {"full_name": original.repository},
        "run_started_at": "2026-10-16T11:59:00Z",
    }
    calls: list[str] = []

    def github(command: list[str], failure: str) -> str:
        endpoint = command[2]
        calls.append(endpoint)
        assert not endpoint.endswith("/zip"), "retained artifact must not be downloaded again"
        assert "/deployments" not in endpoint, "evidence writer has no deployment capability"
        if endpoint.endswith("/actions/artifacts/70"):
            return json.dumps(metadata)
        if f"/actions/runs/{original.run_id}" in endpoint:
            if "/artifacts?" in endpoint:
                return json.dumps([{"artifacts": [metadata]}])
            return json.dumps(run)
        return api.run(command, failure)

    monkeypatch.setattr(workflow, "run_gh", github)
    monkeypatch.setattr(promotion, "run_gh", github)
    result = preupload.resolve_preupload_failure(recovery_request(disposed_intent), producer=issuer)

    assert result.model_dump(mode="json") == proof
    assert any(endpoint.endswith("/actions/artifacts/70") for endpoint in calls)
    assert api.deployments[0]["id"] == 50 and api.statuses[50] == []
    monkeypatch.setattr(workflow, "run_gh", api.run)
    workflow.require_no_unverified_uploads(original.repository)


def test_later_ci_caller_reuses_original_disposition_without_relabeling(
    disposed_intent: tuple[Any, ...], monkeypatch: pytest.MonkeyPatch
) -> None:
    from election_guide.hosting import promotion
    from election_guide.release import preupload

    _, _, api, _, _, issuer, _, proof, _, _ = disposed_intent
    before = copy.deepcopy(api.comments)
    later = issuer.model_copy(update={"workflow_sha": "c" * 40, "run_id": 300})

    def expired(*args: Any, **kwargs: Any) -> None:
        raise ValueError("old artifact has expired")

    monkeypatch.setattr(promotion, "verify_actions_artifact", expired)
    result = preupload.resolve_preupload_failure(recovery_request(disposed_intent), producer=later)

    assert result.model_dump(mode="json") == proof
    assert result.producer == issuer
    assert api.comments == before


def test_conflicting_recovery_request_cannot_replace_original_proof(
    disposed_intent: tuple[Any, ...],
) -> None:
    from election_guide.release import preupload

    _, _, api, _, _, issuer, _, _, _, _ = disposed_intent
    request = recovery_request(disposed_intent)
    request["failed_artifact"]["id"] = 71
    before = copy.deepcopy(api.comments)
    with pytest.raises(ValueError, match="conflicts"):
        preupload.resolve_preupload_failure(request, producer=issuer)
    assert api.comments == before


def test_human_disposition_marker_does_not_clear_admission(
    disposed_intent: tuple[Any, ...],
) -> None:
    workflow, _, api, _, publication, _, _, _, _, _ = disposed_intent
    for comment in api.comments:
        marker = json.loads(comment["body"].splitlines()[-1].split(" ", 2)[2][:-4])
        if marker["producer"]["run_id"] == 200:
            comment["user"] = {"login": "human", "type": "User", "id": 1}
    with pytest.raises(ValueError):
        workflow.require_no_unverified_uploads(publication.published.candidate.producer.repository)


def test_two_authenticated_dispositions_are_ambiguous_and_cannot_clear_admission(
    disposed_intent: tuple[Any, ...], monkeypatch: pytest.MonkeyPatch
) -> None:
    workflow, evidence, api, _, publication, issuer, _, proof, _, _ = disposed_intent
    later = issuer.model_copy(update={"workflow_sha": "c" * 40, "run_id": 300})
    original_carrier = operation(
        publication, phase="deployment", state="failed", producer=issuer, error=DISPOSITION_ERROR
    )
    reports = evidence.read_evidence_reports(original_carrier, issue_number=550)
    second = copy.deepcopy(proof)
    second["producer"] = later.model_dump(mode="json")
    evidence.retain_evidence(
        operation(
            publication, phase="deployment", state="failed", producer=later, error=DISPOSITION_ERROR
        ),
        issue_number=550,
        reports={**reports, "preupload-disposition.json": canonical_json_bytes(second)},
    )
    read = workflow.read_object

    def read_object(endpoint: str) -> dict[str, Any]:
        if endpoint.endswith("/actions/runs/300/attempts/1"):
            return {
                "id": 300,
                "run_attempt": 1,
                "head_sha": "c" * 40,
                "head_branch": "main",
                "event": "push",
                "path": ".github/workflows/ci.yml",
                "repository": {"full_name": issuer.repository},
            }
        return read(endpoint)

    monkeypatch.setattr(workflow, "read_object", read_object)
    before = copy.deepcopy(api.comments)
    with pytest.raises(ValueError, match="ambiguous"):
        workflow.require_no_unverified_uploads(publication.published.candidate.producer.repository)
    assert api.comments == before


def test_cli_records_historical_proof_without_deployment_capability(
    disposed_intent: tuple[Any, ...], monkeypatch: pytest.MonkeyPatch
) -> None:
    from election_guide.release.automation_cli import app

    _, _, api, _, _, issuer, root, proof, _, _ = disposed_intent
    request_path = root / "preupload-request.json"
    request_path.write_bytes(canonical_json_bytes(recovery_request(disposed_intent)))
    output = root / "disposition.json"
    monkeypatch.setenv("GITHUB_ACTIONS", "true")
    monkeypatch.setenv("GITHUB_REF", "refs/heads/main")
    monkeypatch.setenv("GITHUB_REPOSITORY", issuer.repository)
    monkeypatch.setenv("GITHUB_SHA", issuer.workflow_sha)
    monkeypatch.setenv("GITHUB_RUN_ID", str(issuer.run_id))
    monkeypatch.setenv("GITHUB_RUN_ATTEMPT", str(issuer.run_attempt))
    before = copy.deepcopy(api.comments)

    result = CliRunner().invoke(
        app,
        [
            "record-preupload-disposition",
            "--request",
            str(request_path),
            "--output",
            str(output),
        ],
    )

    assert result.exit_code == 0, result.output
    assert json.loads(output.read_bytes()) == proof
    assert api.comments == before and api.statuses[50] == []


def test_cli_rejects_non_main_execution_before_any_evidence_write(
    disposed_intent: tuple[Any, ...], monkeypatch: pytest.MonkeyPatch
) -> None:
    from election_guide.release.automation_cli import app

    _, _, api, _, _, _, root, _, _, _ = disposed_intent
    request_path = root / "preupload-request.json"
    request_path.write_bytes(canonical_json_bytes(recovery_request(disposed_intent)))
    output = root / "disposition.json"
    monkeypatch.setenv("GITHUB_ACTIONS", "true")
    monkeypatch.setenv("GITHUB_REF", "refs/heads/feature")
    before = copy.deepcopy(api.comments)
    result = CliRunner().invoke(
        app,
        ["record-preupload-disposition", "--request", str(request_path), "--output", str(output)],
    )
    assert result.exit_code != 0 and not output.exists()
    assert api.comments == before


def test_control_correction_still_requires_a_fresh_release_declaration(
    disposed_intent: tuple[Any, ...],
) -> None:
    from dataclasses import replace

    from election_guide.release.declaration import validate_release_request

    resolved = disposed_intent[3]
    current = resolved.current.model_copy(
        update={"release_version": "2026-primary.2", "bundle_id": "wa-2026-primary-2026-primary.2"}
    )
    resolved = replace(
        resolved, current=current, site=resolved.site.model_copy(update={"elections": [current]})
    )
    with pytest.raises(ValueError, match="version increment"):
        validate_release_request(
            resolved,
            base=resolved.site,
            changed_paths=("src/election_guide/release/preupload.py", ".github/workflows/ci.yml"),
        )


def test_reviewed_request_preserves_real_failed_bytes_and_closed_source_contract() -> None:
    from election_guide.release import preupload, workflow

    root = Path(__file__).parents[1]
    request = preupload.PreUploadRecoveryRequest.model_validate_json(
        (root / "config/hosting/preupload-failure.json").read_bytes()
    )
    wrapper = base64.b64decode(request.wrapper_base64, validate=True)
    members = preupload.wrapper_members(request.failed_artifact, wrapper)
    report = preupload.FailedUploadReport.model_validate_json(members["upload-report.json"])
    assert report.returncode == 1 and report.github_deployment_id == request.github_deployment_id
    assert report.producer == request.failed_artifact.producer
    assert report.source_sha == request.failed_artifact.producer.source_sha
    preupload.classify_report(report)
    assert (
        workflow.git(root, "rev-parse", f"{report.source_sha}^{{tree}}")
        == preupload.AUDITED_UPLOADER_TREE
    )
