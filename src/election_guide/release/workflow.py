"""Actions adapters: captured artifacts, one owned upload, and read-only recovery."""

from __future__ import annotations

import json
import re
import subprocess
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

from election_guide.github_cli import run_gh
from election_guide.hosting.models import SiteManifest
from election_guide.hosting.promotion import (
    download_actions_artifact,
    promotion_allowed,
    verify_actions_artifact,
)
from election_guide.release.automation_models import (
    ArtifactRef,
    FileDigest,
    OperationReceipt,
    Producer,
    PublicationResult,
    UploadReceipt,
)
from election_guide.release.evidence import (
    DeploymentPayload,
    current_producer,
    deployment_payload,
    latest_production_receipt,
    load_verified_receipts,
    record_evidence_failure,
    require_publication_evidence,
    trusted_site,
    validate_deployment,
    workflow_owned,
)
from election_guide.release.publication import verify_canonical_publication
from election_guide.serialization import canonical_json_bytes


def git(repository: Path, *arguments: str) -> str:
    result = subprocess.run(
        ["git", *arguments], cwd=repository, text=True, capture_output=True, check=False
    )
    if result.returncode:
        raise ValueError(f"could not read captured source: {result.stderr.strip()}")
    return result.stdout.strip()


def capture_source(repository: Path, source_sha: str) -> str:
    if (
        re.fullmatch(r"[0-9a-f]{40}", source_sha) is None
        or git(repository, "rev-parse", "HEAD") != source_sha
    ):
        raise ValueError("captured source must be the full exact checkout SHA")
    return source_sha


def read_object(endpoint: str) -> dict[str, Any]:
    value = json.loads(run_gh(["gh", "api", endpoint], "could not read Actions delivery metadata"))
    if not isinstance(value, dict):
        raise ValueError("invalid Actions delivery metadata")
    return cast(dict[str, Any], value)


def read_rows(endpoint: str, key: str | None = None) -> list[dict[str, Any]]:
    pages = json.loads(
        run_gh(
            ["gh", "api", endpoint, "--paginate", "--slurp"],
            "could not enumerate delivery metadata",
        )
    )
    if not isinstance(pages, list) or not pages:
        raise ValueError("invalid delivery metadata pages")
    rows: list[dict[str, Any]] = []
    for page in cast(list[Any], pages):
        entries: Any = (
            cast(dict[str, Any], page).get(key) if key and isinstance(page, dict) else page
        )
        if not isinstance(entries, list) or any(
            not isinstance(row, dict) for row in cast(list[Any], entries)
        ):
            raise ValueError("invalid delivery metadata page")
        rows.extend(cast(list[dict[str, Any]], entries))
    return rows


def post_object(endpoint: str, payload: dict[str, Any]) -> dict[str, Any]:
    with tempfile.TemporaryDirectory(prefix="release-delivery-") as temporary:
        path = Path(temporary) / "request.json"
        path.write_bytes(canonical_json_bytes(payload))
        result = json.loads(
            run_gh(
                ["gh", "api", endpoint, "--method", "POST", "--input", str(path)],
                "could not record GitHub deployment",
            )
        )
    if not isinstance(result, dict):
        raise ValueError("invalid GitHub deployment response")
    return cast(dict[str, Any], result)


def capture_artifact(
    *, producer: Producer, artifact_id: int, name: str, digest: str
) -> ArtifactRef:
    metadata = read_object(f"repos/{producer.repository}/actions/artifacts/{artifact_id}")
    reference = ArtifactRef(
        id=artifact_id,
        name=name,
        digest=FileDigest(sha256=digest.removeprefix("sha256:"), size=metadata["size_in_bytes"]),
        producer=producer,
    )
    verify_actions_artifact(reference)
    return reference


def deployment_rows(publication: PublicationResult) -> list[dict[str, Any]]:
    candidate = publication.published.candidate
    rows = read_rows(
        f"repos/{candidate.producer.repository}/deployments?sha={candidate.source_sha}&environment=production&per_page=100"
    )
    matches: list[dict[str, Any]] = []
    for row in rows:
        payload = row.get("payload")
        if isinstance(payload, str):
            payload = json.loads(payload)
        if (
            isinstance(payload, dict)
            and cast(dict[str, Any], payload).get("managed_by")
            == "seattle-election-guide/release-automation"
        ):
            # An older attempt may own the one upload for this canonical release.
            prior = load_verified_receipts(
                repository=candidate.producer.repository,
                issue_number=cast(dict[str, Any], payload)["issue_number"],
                release_version=cast(dict[str, Any], payload)["release_version"],
                source_sha=candidate.source_sha,
            )
            matching = [
                r.publication for r in prior if deployment_payload(r.publication) == payload
            ]
            if not matching:
                raise ValueError("managed deployment lacks matching durable publication")
            verify_canonical_publication(matching[0], publication.published)
            validate_deployment(row, matching[0])
            matches.append(row)
    return matches


def admit_upload(
    publication: PublicationResult, *, selected: SiteManifest, enabled: bool, output_dir: Path
) -> str:
    require_publication_evidence(publication)
    candidate = publication.published.candidate
    latest = latest_production_receipt(candidate.producer.repository)
    allowed = promotion_allowed(publication, selected=selected, latest_verified=latest)
    state = "superseded" if not allowed else ("eligible" if enabled else "deployment_paused")
    output_dir.mkdir(parents=True, exist_ok=True)
    if state != "eligible":
        receipt = OperationReceipt(
            phase="deployment",
            state=state,
            producer=candidate.producer,
            publication=publication,
            upload=None,
            verification_sha256=None,
            error=None,
        )
        (output_dir / "operation.json").write_bytes(
            canonical_json_bytes(receipt.model_dump(mode="json"))
        )
    elif deployment_rows(publication):
        raise ValueError(
            "an upload was already admitted; use verification-only recovery before any new upload"
        )
    return state


def require_no_unverified_uploads(repository: str) -> None:
    """An uncertain earlier upload must be verified before admitting another release."""
    for row in read_rows(f"repos/{repository}/deployments?environment=production&per_page=100"):
        payload = row.get("payload")
        if isinstance(payload, str):
            payload = json.loads(payload)
        if (
            not isinstance(payload, dict)
            or cast(dict[str, Any], payload).get("managed_by")
            != "seattle-election-guide/release-automation"
        ):
            continue
        identity = DeploymentPayload.model_validate_json(json.dumps(payload))
        records = load_verified_receipts(
            repository=repository,
            issue_number=identity.issue_number,
            release_version=identity.release_version,
            source_sha=identity.producer.source_sha,
        )
        verified = [
            r
            for r in records
            if r.state == "verified"
            and r.upload is not None
            and r.upload.github_deployment_id == row.get("id")
            and deployment_payload(r.publication) == identity.model_dump(mode="json")
        ]
        if not verified:
            raise ValueError(
                "an earlier upload is unverified; "
                "use verification-only recovery before any new upload"
            )
        validate_deployment(row, verified[0].publication)


def create_deployment(publication: PublicationResult) -> int:
    require_publication_evidence(publication)
    if deployment_rows(publication):
        raise ValueError("existing deployment requires verification-only recovery")
    candidate = publication.published.candidate
    require_no_unverified_uploads(candidate.producer.repository)
    deployment = post_object(
        f"repos/{candidate.producer.repository}/deployments",
        {
            "ref": candidate.source_sha,
            "environment": "production",
            "auto_merge": False,
            "required_contexts": [],
            "payload": deployment_payload(publication),
        },
    )
    validate_deployment(deployment, publication)
    identifier = deployment.get("id")
    if type(identifier) is not int or identifier <= 0:
        raise ValueError("invalid deployment ID")
    return identifier


def write_deployment_status(
    publication: PublicationResult, deployment_id: int, *, state: str, url: str
) -> None:
    candidate = publication.published.candidate
    deployment = read_object(f"repos/{candidate.producer.repository}/deployments/{deployment_id}")
    validate_deployment(deployment, publication)
    if deployment.get("id") != deployment_id:
        raise ValueError("deployment ID differs")
    if state == "success":
        statuses = read_rows(
            f"repos/{candidate.producer.repository}/deployments/{deployment_id}/statuses?per_page=100"
        )
        successes = [s for s in statuses if s.get("state") == "success"]
        if successes:
            if any(
                s.get("environment_url") != url or not workflow_owned(s.get("creator"))
                for s in successes
            ):
                raise ValueError("existing success status conflicts with upload")
            return
    status = post_object(
        f"repos/{candidate.producer.repository}/deployments/{deployment_id}/statuses",
        {"state": state, "environment_url": url, "auto_inactive": state == "success"},
    )
    if (
        status.get("state") != state
        or status.get("environment_url") != url
        or not workflow_owned(status.get("creator"))
    ):
        raise ValueError("deployment status differs from requested identity")


def perform_upload(
    publication: PublicationResult, *, deployment_id: int, site_dir: Path, output_dir: Path
) -> UploadReceipt:
    """Invoke the lockfile's Wrangler once and preserve even uncertain outcomes."""
    require_publication_evidence(publication)
    candidate = publication.published.candidate
    producer = current_producer(candidate.source_sha)
    output_dir.mkdir(parents=True, exist_ok=True)
    report: dict[str, Any] = {
        "producer": producer.model_dump(mode="json"),
        "github_deployment_id": deployment_id,
        "source_sha": candidate.source_sha,
        "uploaded_at": datetime.now(UTC).isoformat(),
        "returncode": None,
        "stdout": "",
        "stderr": "",
    }
    try:
        result = subprocess.run(
            [
                "npm",
                "run",
                "pages:deploy",
                "--",
                str(site_dir),
                f"--commit-hash={candidate.source_sha}",
                "--commit-dirty=false",
            ],
            text=True,
            capture_output=True,
            check=False,
        )
        report.update(
            returncode=result.returncode,
            stdout=result.stdout,
            stderr=result.stderr,
            uploaded_at=datetime.now(UTC).isoformat(),
        )
        (output_dir / "upload-report.json").write_bytes(canonical_json_bytes(report))
        urls = set(
            re.findall(
                r"https://[0-9a-f]+\.[a-z0-9-]+\.pages\.dev\b", result.stdout + "\n" + result.stderr
            )
        )
        if result.returncode or len(urls) != 1:
            raise ValueError(
                "upload outcome uncertain; operator verification is required before any new upload"
            )
        upload = UploadReceipt.model_validate_json(
            json.dumps(
                {
                    "publication": publication.model_dump(mode="json"),
                    "producer": producer.model_dump(mode="json"),
                    "github_deployment_id": deployment_id,
                    "deployment_url": urls.pop(),
                    "uploaded_at": report["uploaded_at"],
                    "source_sha": candidate.source_sha,
                }
            )
        )
        # Retain the unique upload URL before any receipt/probe can fail.
        write_deployment_status(
            publication, deployment_id, state="in_progress", url=upload.deployment_url
        )
        (output_dir / "upload.json").write_bytes(
            canonical_json_bytes(upload.model_dump(mode="json"))
        )
        return upload
    finally:
        (output_dir / "upload-report.json").write_bytes(canonical_json_bytes(report))


def recover_upload(
    *,
    repository: str,
    issue: int,
    release_version: str,
    source_sha: str,
    run_id: int,
    run_attempt: int,
) -> UploadReceipt:
    """Use immutable evidence, or one owned deployment/status plus its retained upload report."""
    records = load_verified_receipts(
        repository=repository,
        issue_number=issue,
        release_version=release_version,
        source_sha=source_sha,
    )
    publications = [
        r.publication
        for r in records
        if r.phase == "publication"
        and r.state == "published"
        and r.publication.published.candidate.producer.run_id == run_id
        and r.publication.published.candidate.producer.run_attempt == run_attempt
    ]
    if not publications or any(p != publications[0] for p in publications):
        raise ValueError("matching durable publication evidence is missing or ambiguous")
    publication = publications[0]
    trusted_site(publication)
    uploads = [r.upload for r in records if r.upload is not None and r.publication == publication]
    if uploads:
        if any(upload != uploads[0] for upload in uploads):
            raise ValueError("conflicting immutable upload evidence")
        return uploads[0]
    deployments = deployment_rows(publication)
    if len(deployments) != 1:
        raise ValueError("upload recovery requires exactly one owned deployment")
    deployment = deployments[0]
    statuses = read_rows(f"repos/{repository}/deployments/{deployment['id']}/statuses?per_page=100")
    urls = {
        s.get("environment_url") for s in statuses if s.get("state") in {"in_progress", "success"}
    }
    if (
        not statuses
        or any(not workflow_owned(s.get("creator")) for s in statuses)
        or len(urls) != 1
    ):
        raise ValueError("owned upload status is missing or ambiguous")
    producer = publication.published.candidate.producer
    name = f"upload-{run_id}-{run_attempt}"
    matches = [
        r
        for r in read_rows(
            f"repos/{repository}/actions/runs/{run_id}/artifacts?per_page=100", "artifacts"
        )
        if r.get("name") == name
    ]
    if len(matches) != 1:
        raise ValueError("retained upload report is missing or ambiguous")
    ref = capture_artifact(
        producer=producer, artifact_id=matches[0]["id"], name=name, digest=matches[0]["digest"]
    )
    with tempfile.TemporaryDirectory(prefix="release-upload-recovery-") as temporary:
        directory = Path(temporary)
        download_actions_artifact(ref, directory)
        report = json.loads((directory / "upload-report.json").read_bytes())
    if (
        report.get("returncode") != 0
        or report.get("producer") != producer.model_dump(mode="json")
        or report.get("github_deployment_id") != deployment["id"]
        or report.get("source_sha") != source_sha
    ):
        raise ValueError("retained upload report conflicts with owned deployment")
    observed_urls = set(
        re.findall(
            r"https://[0-9a-f]+\.[a-z0-9-]+\.pages\.dev\b",
            report["stdout"] + "\n" + report["stderr"],
        )
    )
    if observed_urls != urls:
        raise ValueError("retained upload output differs from owned deployment URL")
    return UploadReceipt.model_validate_json(
        json.dumps(
            {
                "publication": publication.model_dump(mode="json"),
                "producer": report["producer"],
                "github_deployment_id": deployment["id"],
                "deployment_url": next(iter(urls)),
                "uploaded_at": report["uploaded_at"],
                "source_sha": source_sha,
            }
        )
    )


def retain_delivery_failure(publication_path: Path, output_dir: Path, error: Exception) -> None:
    """Keep a failed operation for the credential-free evidence job, even before upload."""
    record_evidence_failure(output_dir, error)
    publication = PublicationResult.model_validate_json(publication_path.read_bytes())
    receipt = OperationReceipt(
        phase="deployment",
        state="failed",
        producer=publication.published.candidate.producer,
        publication=publication,
        upload=None,
        verification_sha256=None,
        error=str(error),
    )
    (output_dir / "operation.json").write_bytes(
        canonical_json_bytes(receipt.model_dump(mode="json"))
    )
