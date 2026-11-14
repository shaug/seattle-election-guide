"""Audited dispositions of proved pre-upload failures; never upload or erase an intent."""

from __future__ import annotations

import base64
import binascii
import hashlib
import io
import json
import re
import stat
import zipfile
from pathlib import Path
from typing import Any, Literal, cast

from pydantic import AwareDatetime

from election_guide.release import workflow
from election_guide.release.automation_models import (
    ArtifactRef,
    GitSha,
    OperationalRecord,
    OperationReceipt,
    PositiveId,
    Producer,
    PublicationResult,
    Sha256,
)
from election_guide.release.evidence import (
    PART_BYTES,
    deployment_payload,
    read_pending_preupload_evidence,
    read_preupload_evidence,
    require_publication_evidence,
    retain_evidence,
    validate_deployment,
)
from election_guide.serialization import canonical_json_bytes

DISPOSITION_ERROR = "proved pre-upload failure; original intent retained"
ORIGINAL_ERROR = "upload outcome uncertain; operator verification is required before any new upload"
KIND = "wrangler-4.158.0-project-get-503-v1"
AUDITED_UPLOADER_TREE = "25653db793a25aaabdcc954410109775cf9cd371"
# One audited normal uploader generation, not an intent/source exception list.
# These immutable Git blobs bind npm's locked package, command, config and CI recipe.
# Unknown generations require their own reviewed safety analysis; they fail closed.
UPLOADER_BLOBS = {
    ".github/workflows/ci.yml": "5b3926bf75720a33ac1e7c3084543d6bbf999b43",
    "src/election_guide/release/workflow.py": "e220e0c1e2d455e0a4d679909010a214cae8fe72",
    "package.json": "537fe9ce0a38520d51664a0c5ead5fc3cbdb3ea2",
    "package-lock.json": "d1b379f8a5dc6f049b984d45df822bd120b1efeb",
    "wrangler.jsonc": "a1c9454057648636ea1f836d0341d7163263f6b3",
}
MEMBERS = {
    "deployment.json",
    "upload-report.json",
    "operation.json",
    "finalization-error.json",
    "summary.md",
}


class FailedUploadReport(OperationalRecord):
    producer: Producer
    github_deployment_id: PositiveId
    source_sha: GitSha
    uploaded_at: AwareDatetime
    returncode: int
    stdout: str
    stderr: str


class PreUploadDisposition(OperationalRecord):
    kind: Literal["wrangler-4.158.0-project-get-503-v1"]
    producer: Producer
    publication_sha256: Sha256
    github_deployment_id: PositiveId
    failed_artifact: ArtifactRef
    report_sha256: Sha256
    artifact_metadata_sha256: Sha256
    uploader_blobs: dict[str, GitSha]
    uploader_tree: GitSha


class PreUploadRecoveryRequest(OperationalRecord):
    failed_artifact: ArtifactRef
    github_deployment_id: PositiveId
    wrapper_base64: str


def sha(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def wrapper_members(reference: ArtifactRef, content: bytes) -> dict[str, bytes]:
    if len(content) != reference.digest.size or sha(content) != reference.digest.sha256:
        raise ValueError("pre-upload wrapper differs from authenticated artifact")
    if len(content) > 1_000_000:
        raise ValueError("pre-upload wrapper exceeds the supported proof bound")
    try:
        with zipfile.ZipFile(io.BytesIO(content)) as archive:
            infos = archive.infolist()
            if len(infos) != len(MEMBERS) or {item.filename for item in infos} != MEMBERS:
                raise ValueError("pre-upload wrapper has missing, duplicate or unsupported members")
            if sum(item.file_size for item in infos) > 1_000_000 or any(
                item.is_dir()
                or item.flag_bits & 1
                or stat.S_IFMT(item.external_attr >> 16) not in {0, stat.S_IFREG}
                for item in infos
            ):
                raise ValueError("pre-upload wrapper contains unsafe or oversized members")
            return {item.filename: archive.read(item) for item in infos}
    except (zipfile.BadZipFile, RuntimeError, NotImplementedError) as error:
        raise ValueError("pre-upload wrapper is unreadable") from error


def _lines(value: str) -> tuple[str, ...]:
    clean = re.sub(r"\x1b\[[0-?]*[ -/]*[@-~]", "", value)
    return tuple(line.strip() for line in clean.splitlines() if line.strip())


def classify_report(report: FailedUploadReport) -> None:
    """Recognize only the audited normal pre-write path, never generic failure."""
    expected_stdout = (
        "> pages:deploy",
        "> wrangler pages deploy --branch=${PAGES_BRANCH:-main} "
        f"dist/cloudflare-site --commit-hash={report.source_sha} --commit-dirty=false",
        "⛅️ wrangler 4.158.0",
        "────────────────────",
    )
    stderr = _lines(report.stderr)
    if (
        report.returncode != 1
        or _lines(report.stdout) != expected_stdout
        or len(stderr) != 6
        or stderr[0] != "✘ [ERROR] Received a malformed response from the API"
        or re.fullmatch(
            r"upstream connect error or disconnect/reset before headers\. reset reason: "
            r"remote connection failure, \.\.\. \(length = [0-9]+\)",
            stderr[1],
        )
        is None
        or re.fullmatch(
            r"GET /accounts/[0-9a-f]{32}/pages/projects/seattle-elections "
            r"-> 503 Service Unavailable",
            stderr[2],
        )
        is None
        or re.fullmatch(r"Cloudflare Ray ID: [0-9a-f]+-[A-Z]+", stderr[3]) is None
        or stderr[4]
        != "If you think this is a bug, please open an issue at: "
        "https://github.com/cloudflare/workers-sdk/issues/new/choose"
        or re.fullmatch(
            r'🪵\s+Logs were written to "/home/runner/\.config/\.wrangler/logs/'
            r'wrangler-[0-9_-]+\.log"',
            stderr[5],
        )
        is None
    ):
        raise ValueError("failed output does not prove the supported pre-upload path")


def validate_metadata(reference: ArtifactRef, metadata: dict[str, Any]) -> None:
    raw_workflow_run = metadata.get("workflow_run")
    workflow_run = (
        cast(dict[str, Any], raw_workflow_run) if isinstance(raw_workflow_run, dict) else {}
    )
    if (
        metadata.get("id") != reference.id
        or metadata.get("name") != reference.name
        or metadata.get("size_in_bytes") != reference.digest.size
        or metadata.get("digest") != "sha256:" + reference.digest.sha256
        or metadata.get("expired") is not False
        or not isinstance(raw_workflow_run, dict)
        or workflow_run.get("id") != reference.producer.run_id
        or workflow_run.get("head_sha") != reference.producer.workflow_sha
        or workflow_run.get("head_branch") != "main"
        # This snapshot sorts first and must be one complete existing report
        # part, so any later POST failure leaves enough proof to resume it.
        or len(canonical_json_bytes(metadata)) > PART_BYTES
    ):
        raise ValueError("retained pre-upload metadata conflicts with original artifact")


def validate_proof(
    proof: PreUploadDisposition,
    publication: PublicationResult,
    deployment_id: int,
    content: bytes,
    metadata: dict[str, Any],
) -> None:
    candidate = publication.published.candidate
    original = candidate.producer
    if (
        proof.publication_sha256 != sha(canonical_json_bytes(publication.model_dump(mode="json")))
        or proof.github_deployment_id != deployment_id
        or proof.failed_artifact.producer != original
        or proof.failed_artifact.name != f"upload-{original.run_id}-{original.run_attempt}"
        or original.workflow_sha != original.source_sha
        or proof.producer.repository != original.repository
        or proof.producer.source_sha != original.source_sha
        or proof.producer.run_id == original.run_id
        or proof.uploader_blobs != UPLOADER_BLOBS
        or proof.uploader_tree != AUDITED_UPLOADER_TREE
        or proof.artifact_metadata_sha256 != sha(canonical_json_bytes(metadata))
    ):
        raise ValueError("pre-upload disposition identity or original contract differs")
    validate_metadata(proof.failed_artifact, metadata)
    # The complete audited tree closes the entrypoint and transitive import
    # boundary: pinning only perform_upload would miss a changed caller that
    # writes before it invokes the otherwise unchanged uploader.
    if (
        workflow.git(Path.cwd(), "rev-parse", f"{original.source_sha}^{{tree}}")
        != AUDITED_UPLOADER_TREE
    ):
        raise ValueError("original complete uploader source tree is not the audited contract")
    for path, expected in UPLOADER_BLOBS.items():
        if workflow.git(Path.cwd(), "rev-parse", f"{original.source_sha}:{path}") != expected:
            raise ValueError("original uploader contract is not the audited generation")
    run = workflow.read_object(
        f"repos/{original.repository}/actions/runs/{proof.producer.run_id}"
        f"/attempts/{proof.producer.run_attempt}"
    )
    if (
        run.get("id") != proof.producer.run_id
        or run.get("run_attempt") != proof.producer.run_attempt
        or run.get("head_sha") != proof.producer.workflow_sha
        or run.get("head_branch") != "main"
        or run.get("event") not in {"push", "workflow_dispatch"}
        or run.get("path") != ".github/workflows/ci.yml"
        or not isinstance(run.get("repository"), dict)
        or run["repository"].get("full_name") != original.repository
    ):
        raise ValueError("pre-upload disposition requires its original trusted-main issuer")
    reviewed = PreUploadRecoveryRequest.model_validate_json(
        workflow.git(
            Path.cwd(),
            "show",
            f"{proof.producer.workflow_sha}:config/hosting/preupload-failure.json",
        )
    )
    if (
        reviewed.failed_artifact != proof.failed_artifact
        or reviewed.github_deployment_id != deployment_id
        or base64.b64decode(reviewed.wrapper_base64, validate=True) != content
    ):
        raise ValueError("pre-upload disposition differs from its issuer's reviewed request")
    members = wrapper_members(proof.failed_artifact, content)
    failed = OperationReceipt.model_validate_json(members["operation.json"])
    report = FailedUploadReport.model_validate_json(members["upload-report.json"])
    if (
        failed.phase != "deployment"
        or failed.state != "failed"
        or failed.error != ORIGINAL_ERROR
        or failed.publication != publication
        or failed.producer != original
        or failed.upload is not None
        or failed.verification_sha256 is not None
        or report.producer != original
        or report.source_sha != candidate.source_sha
        or report.github_deployment_id != proof.github_deployment_id
        or json.loads(members["deployment.json"]) != {"id": proof.github_deployment_id}
        or sha(members["upload-report.json"]) != proof.report_sha256
    ):
        raise ValueError("original failed report conflicts with pre-upload disposition")
    classify_report(report)


def read_recorded_dispositions(
    publication: PublicationResult, deployment_id: int
) -> tuple[PreUploadDisposition, ...]:
    """Read historical proof only; this does not admit an upload or read deployments."""
    records = read_preupload_evidence(publication)
    matches: list[PreUploadDisposition] = []
    for receipt, reports in records:
        if "preupload-disposition.json" not in reports:
            continue
        proof = PreUploadDisposition.model_validate_json(reports["preupload-disposition.json"])
        if proof.github_deployment_id != deployment_id:
            continue
        if (
            receipt.phase != "deployment"
            or receipt.state != "failed"
            or receipt.error != DISPOSITION_ERROR
            or receipt.producer != proof.producer
        ):
            raise ValueError("pre-upload disposition carrier conflicts with proof")
        try:
            raw_encoded = json.loads(reports["preupload-artifact.json"])
            if not isinstance(raw_encoded, dict):
                raise ValueError("invalid pre-upload wrapper report")
            encoded = cast(dict[str, Any], raw_encoded)
            if set(encoded) != {"base64"} or not isinstance(encoded["base64"], str):
                raise ValueError("invalid pre-upload wrapper report")
            content = base64.b64decode(encoded["base64"], validate=True)
            metadata = json.loads(reports["preupload-artifact-metadata.json"])
            if not isinstance(metadata, dict):
                raise ValueError("invalid original artifact metadata report")
        except (KeyError, TypeError, binascii.Error) as error:
            raise ValueError("pre-upload disposition lacks complete original proof") from error
        validate_proof(
            proof, receipt.publication, deployment_id, content, cast(dict[str, Any], metadata)
        )
        matches.append(proof)
    if not matches:
        return ()
    if len(matches) != 1:
        raise ValueError("duplicate or ambiguous pre-upload dispositions")
    return tuple(matches)


def load_preupload_dispositions(
    publication: PublicationResult, deployment: dict[str, Any]
) -> tuple[PreUploadDisposition, ...]:
    """Consume proof only after fresh owned-intent and status checks under admission."""
    validate_deployment(deployment, publication)
    matches = read_recorded_dispositions(publication, deployment["id"])
    if not matches:
        return ()
    candidate = publication.published.candidate
    rows = workflow.deployment_rows(publication)
    if len(rows) != 1 or rows[0].get("id") != deployment.get("id"):
        raise ValueError("pre-upload disposition requires one original owned intent")
    statuses = workflow.read_rows(
        f"repos/{candidate.producer.repository}/deployments/{deployment['id']}/statuses?per_page=100"
    )
    if statuses:
        raise ValueError("original intent status contradicts pre-upload disposition")
    return matches


def resolve_preupload_failure(
    request: dict[str, Any], *, producer: Producer
) -> PreUploadDisposition:
    """Authenticate retained bytes and append a distinct failed-operation disposition.

    Existing complete proof is reused with its original issuer, even by later CI
    producers and after temporary artifact expiry. No download, deployment/status
    mutation or uploader is invoked here. An interrupted record resumes only its
    exact original group, using the authenticated metadata part written first.
    """
    from election_guide.hosting.promotion import verify_actions_artifact

    parsed = PreUploadRecoveryRequest.model_validate_json(json.dumps(request))
    reference = parsed.failed_artifact
    try:
        content = base64.b64decode(parsed.wrapper_base64, validate=True)
    except binascii.Error as error:
        raise ValueError("invalid retained pre-upload wrapper encoding") from error
    members = wrapper_members(reference, content)
    original_failure = OperationReceipt.model_validate_json(members["operation.json"])
    publication = original_failure.publication
    require_publication_evidence(publication)
    pending = read_pending_preupload_evidence(publication, error=DISPOSITION_ERROR)
    if pending:
        original_carrier, reports = pending
        producer = original_carrier.producer
        try:
            raw_metadata = json.loads(reports["preupload-artifact-metadata.json"])
        except KeyError as error:
            raise ValueError(
                "pending disposition lacks its authenticated metadata snapshot"
            ) from error
        if not isinstance(raw_metadata, dict):
            raise ValueError("invalid pending artifact metadata snapshot")
        metadata = cast(dict[str, Any], raw_metadata)
    else:
        existing = read_recorded_dispositions(publication, parsed.github_deployment_id)
        if existing:
            if (
                existing[0].failed_artifact != reference
                or existing[0].github_deployment_id != parsed.github_deployment_id
            ):
                raise ValueError("repeated recovery request conflicts with original disposition")
            return existing[0]
        artifacts = [
            row
            for row in workflow.read_rows(
                f"repos/{reference.producer.repository}/actions/runs/{reference.producer.run_id}"
                "/artifacts?per_page=100",
                "artifacts",
            )
            if row.get("name") == reference.name
        ]
        if len(artifacts) != 1:
            raise ValueError("original failed artifact is missing or ambiguous")
        metadata = artifacts[0]
        validate_metadata(reference, metadata)
        verify_actions_artifact(reference)
    proof = PreUploadDisposition(
        kind=KIND,
        producer=producer,
        publication_sha256=sha(canonical_json_bytes(publication.model_dump(mode="json"))),
        github_deployment_id=parsed.github_deployment_id,
        failed_artifact=reference,
        report_sha256=sha(members["upload-report.json"]),
        artifact_metadata_sha256=sha(canonical_json_bytes(metadata)),
        uploader_blobs=UPLOADER_BLOBS,
        uploader_tree=AUDITED_UPLOADER_TREE,
    )
    validate_proof(proof, publication, parsed.github_deployment_id, content, metadata)
    issue = deployment_payload(publication)["issue_number"]
    carrier = OperationReceipt(
        phase="deployment",
        state="failed",
        producer=producer,
        publication=publication,
        upload=None,
        verification_sha256=None,
        error=DISPOSITION_ERROR,
    )
    retain_evidence(
        carrier,
        issue_number=issue,
        reports={
            "preupload-disposition.json": canonical_json_bytes(proof.model_dump(mode="json")),
            "preupload-artifact.json": canonical_json_bytes({"base64": parsed.wrapper_base64}),
            "preupload-artifact-metadata.json": canonical_json_bytes(metadata),
        },
    )
    recovered = read_recorded_dispositions(publication, parsed.github_deployment_id)
    if recovered != (proof,):
        raise ValueError("recorded pre-upload disposition could not be independently recovered")
    return proof
