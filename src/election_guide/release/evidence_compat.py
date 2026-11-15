"""Current-workflow, lossless preparation for unmodified historical readers.

Compatibility comments encode an existing operation, not a new operation by its
original producer. The exporter identity is kept separately in the output report.
This module has no upload, production probe or deployment-write capability.
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
from pathlib import Path
from typing import Any, cast

from election_guide.release import evidence, workflow
from election_guide.release.automation_models import OperationReceipt, Producer
from election_guide.serialization import canonical_json_bytes

MAX_NEW_COMMENTS = 256


def _exporter(repository: str) -> Producer:
    if (
        os.environ.get("GITHUB_ACTIONS") != "true"
        or os.environ.get("GITHUB_REF") != "refs/heads/main"
    ):
        raise ValueError("compatibility preparation requires trusted main Actions execution")
    if os.environ.get("GITHUB_REPOSITORY") != repository:
        raise ValueError("compatibility repository differs from current workflow")
    try:
        sha = os.environ["GITHUB_SHA"]
        producer = Producer(
            repository=repository,
            source_sha=sha,
            workflow_sha=sha,
            run_id=int(os.environ["GITHUB_RUN_ID"]),
            run_attempt=int(os.environ["GITHUB_RUN_ATTEMPT"]),
        )
    except KeyError as error:
        raise ValueError(f"missing compatibility workflow identity: {error}") from error
    actual = subprocess.run(
        ["git", "rev-parse", "HEAD"], capture_output=True, text=True, check=False
    )
    if actual.returncode or actual.stdout.strip() != sha:
        raise ValueError("compatibility reader checkout differs from trusted workflow SHA")
    return producer


def _group(receipt: OperationReceipt) -> str:
    return hashlib.sha256(canonical_json_bytes(receipt.model_dump(mode="json"))).hexdigest()


def _write_report(output_dir: Path, report: dict[str, Any]) -> None:
    (output_dir / "compatibility-report.json").write_bytes(canonical_json_bytes(report))


def _managed(repository: str) -> list[tuple[dict[str, Any], evidence.DeploymentPayload]]:
    rows = workflow.read_rows(f"repos/{repository}/deployments?environment=production&per_page=100")
    result: list[tuple[dict[str, Any], evidence.DeploymentPayload]] = []
    for row in rows:
        payload = row.get("payload")
        if isinstance(payload, str):
            try:
                payload = json.loads(payload)
            except ValueError:
                if evidence.workflow_owned(row.get("creator")):
                    raise ValueError(
                        "invalid owned deployment payload during preparation"
                    ) from None
                continue
        if not isinstance(payload, dict):
            continue
        payload = cast(dict[str, Any], payload)
        if payload.get("managed_by") != "seattle-election-guide/release-automation":
            continue
        identity = evidence.DeploymentPayload.model_validate_json(json.dumps(payload))
        if (
            not evidence.workflow_owned(row.get("creator"))
            or identity.producer.repository != repository
            or row.get("sha") != identity.producer.source_sha
            or row.get("environment") != "production"
        ):
            raise ValueError("managed deployment identity conflicts during preparation")
        result.append((row, identity))
    return result


def prepare_historical_evidence(
    repository: str, issue_number: int, output_dir: Path
) -> dict[str, Any]:
    """Append bounded missing v1 compatibility records; preserve all operations."""
    output_dir.mkdir(parents=True, exist_ok=True)
    report: dict[str, Any] = {
        "schema_version": "1.0",
        "kind": "historical-evidence-compatibility",
        "complete": False,
        "exporter": None,
        "issues": [],
        "operations": [],
        "observed_new_comment_ids": [],
        "max_new_comments": MAX_NEW_COMMENTS,
        "new_upload_or_verification": False,
        "existing_comments_edited_or_deleted": False,
    }
    current_issue: int | None = None
    prior_ids: set[int] = set()
    try:
        report["exporter"] = _exporter(repository).model_dump(mode="json")
        if type(issue_number) is not int or issue_number <= 0:
            raise ValueError("compatibility preparation requires a positive owning issue")
        managed = _managed(repository)
        issues = sorted({issue_number, *(identity.issue_number for _, identity in managed)})
        report["issues"] = issues
        # Validate the whole relevant custody set before posting any missing part.
        states = {issue: evidence.read_issue_evidence(repository, issue) for issue in issues}
        for state in states.values():
            if state.pending_compressed_groups:
                raise ValueError(
                    "incomplete compressed evidence must be resumed before preparation"
                )
        for row, identity in managed:
            publications = [
                operation.publication
                for operation, _ in states[identity.issue_number].completed
                if evidence.deployment_payload(operation.publication)
                == identity.model_dump(mode="json")
            ]
            if not publications:
                raise ValueError("managed deployment lacks matching complete publication evidence")
            evidence.validate_deployment(row, publications[0])

        remaining = MAX_NEW_COMMENTS
        for current_issue, state in states.items():
            selected = [
                (operation, reports)
                for operation, reports in state.completed
                if _group(operation) in state.complete_compressed_groups
            ]
            if frozenset(_group(operation) for operation, _ in selected) != (
                state.complete_compressed_groups
            ):
                raise ValueError("compressed operation cannot preserve its original receipt bytes")
            prior_ids = set(state.comments)
            for operation, reports in selected:
                group = _group(operation)
                report["pending_operation"] = {
                    "issue": current_issue,
                    "group": group,
                    "original_producer": operation.producer.model_dump(mode="json"),
                }
                ids = evidence.retain_v1_evidence(
                    operation,
                    issue_number=current_issue,
                    reports=reports,
                    max_new_comments=remaining,
                )
                fresh = evidence.read_issue_evidence(repository, current_issue)
                new_ids = sorted(set(fresh.comments) - prior_ids)
                remaining -= len(new_ids)
                report["observed_new_comment_ids"].extend(new_ids)
                report["operations"].append(
                    {
                        "issue": current_issue,
                        "group": group,
                        "original_producer": operation.producer.model_dump(mode="json"),
                        "v1_comment_ids": list(ids),
                        "report_sha256": {
                            name: hashlib.sha256(data).hexdigest() for name, data in reports.items()
                        },
                        "complete": True,
                    }
                )
                prior_ids = set(fresh.comments)
                report.pop("pending_operation", None)
        report["complete"] = True
        _write_report(output_dir, report)
        (output_dir / "summary.md").write_text(
            "Historical evidence compatibility complete; original operations preserved. "
            "No upload, probe or deployment status was performed.\n",
            encoding="utf-8",
        )
        return report
    except (OSError, ValueError) as error:
        report["error"] = str(error)
        if current_issue is not None:
            # A failed POST may have been stored. Observe it, never blindly retry it.
            try:
                fresh = evidence.read_issue_evidence(repository, current_issue)
                report["observed_new_comment_ids"].extend(sorted(set(fresh.comments) - prior_ids))
            except (OSError, ValueError) as reconciliation_error:
                report["reconciliation_error"] = str(reconciliation_error)
        _write_report(output_dir, report)
        evidence.record_evidence_failure(output_dir, error)
        raise
