"""Immutable, resumable GitHub evidence and read-only production finalization.

A group is identified by the operation's canonical JSON digest. Parts alone are
incomplete. A seal names an index which names every required report part by ID
and hash. Only a complete, authenticated chain yields an operation receipt.
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
import subprocess
import tempfile
from contextlib import suppress
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal, cast

import yaml
from pydantic import Field

from election_guide.calendar import due_milestones, read_election_calendar
from election_guide.github_cli import run_gh
from election_guide.hosting.models import SiteManifest
from election_guide.hosting.production_check import ProductionCheckReport
from election_guide.hosting.production_wait import (
    ProductionWaitReport,
    complete_strict_report,
    wait_for_production,
)
from election_guide.release.automation_models import (
    OperationalRecord,
    OperationReceipt,
    PositiveId,
    Producer,
    PublicationResult,
    Sha256,
    UploadReceipt,
)
from election_guide.release.publication import bind_publication
from election_guide.serialization import UniqueKeyLoader, canonical_json_bytes

BOT = {"login": "github-actions[bot]", "type": "Bot", "id": 41898282}
MARKER = "<!-- release-evidence-v1 "
PART_BYTES = 24000
SITE_PATH = "config/hosting/site.yaml"


class PartMarker(OperationalRecord):
    producer: Producer
    release_version: str = Field(min_length=1, max_length=200)
    phase: Literal["publication", "deployment"]
    group: Sha256
    kind: Literal["report", "index", "seal"]
    report: str = Field(pattern=r"^[A-Za-z0-9_.-]{1,100}$")
    part: PositiveId
    count: PositiveId
    sha256: Sha256
    report_sha256: Sha256


class PartRef(OperationalRecord):
    id: PositiveId
    marker: PartMarker


class EvidenceIndex(OperationalRecord):
    parts: tuple[PartRef, ...]


class DeploymentPayload(OperationalRecord):
    """Exact GitHub deployment payload contract; use deployment_payload to build it."""

    managed_by: Literal["seattle-election-guide/release-automation"]
    issue_number: PositiveId
    release_version: str = Field(min_length=1)
    producer: Producer
    publication_sha256: Sha256


def _bytes(value: OperationalRecord) -> bytes:
    return canonical_json_bytes(value.model_dump(mode="json"))


def _sha(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _object(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError("invalid GitHub evidence object")
    return cast(dict[str, Any], value)


def _id(value: dict[str, Any]) -> int:
    result = value.get("id")
    if type(result) is not int or result <= 0:
        raise ValueError("GitHub evidence requires a positive ID")
    return result


def _owned(value: Any) -> bool:
    return isinstance(value, dict) and all(
        cast(dict[str, Any], value).get(key) == item for key, item in BOT.items()
    )


def _pages(endpoint: str) -> list[dict[str, Any]]:
    value: Any = json.loads(
        run_gh(
            ["gh", "api", endpoint + "?per_page=100", "--paginate", "--slurp"],
            "could not read complete release evidence",
        )
    )
    if not isinstance(value, list) or not value:
        raise ValueError("incomplete release evidence pages")
    rows: list[dict[str, Any]] = []
    for page in cast(list[Any], value):
        if not isinstance(page, list):
            raise ValueError("invalid release evidence page")
        rows.extend(_object(row) for row in cast(list[Any], page))
    return rows


def _body(marker: PartMarker, payload: bytes) -> str:
    body = (
        "Release automation evidence (not editorial approval).\n"
        + base64.b64encode(payload).decode("ascii")
        + "\n"
        + MARKER
        + json.dumps(marker.model_dump(mode="json"), sort_keys=True, separators=(",", ":"))
        + " -->"
    )
    if len(body) >= 60000:
        raise ValueError("evidence framing exceeds comment bound")
    return body


def _parts(
    receipt: OperationReceipt, name: str, payload: bytes, kind: Literal["report", "index", "seal"]
) -> list[tuple[PartMarker, bytes]]:
    # Decode first: chunks must retain whole UTF-8 characters, including JSON strings.
    text = payload.decode("utf-8")
    chunks: list[bytes] = []
    start = 0
    data = text.encode("utf-8")
    while start < len(data):
        end = min(start + PART_BYTES, len(data))
        while end < len(data) and data[end] & 0xC0 == 0x80:
            end -= 1
        chunks.append(data[start:end])
        start = end
    chunks = chunks or [b""]
    return [
        (
            PartMarker(
                producer=receipt.producer,
                release_version=receipt.publication.published.candidate.declaration.release_version,
                phase=receipt.phase,
                group=_sha(_bytes(receipt)),
                kind=kind,
                report=name,
                part=index + 1,
                count=len(chunks),
                sha256=_sha(chunk),
                report_sha256=_sha(data),
            ),
            chunk,
        )
        for index, chunk in enumerate(chunks)
    ]


def _comments(repository: str, issue_number: int) -> dict[int, tuple[PartMarker, bytes]]:
    result: dict[int, tuple[PartMarker, bytes]] = {}
    keys: set[tuple[str, str, str, int]] = set()
    for comment in _pages(f"repos/{repository}/issues/{issue_number}/comments"):
        if not _owned(comment.get("user")):
            continue
        body = comment.get("body")
        if not isinstance(body, str) or MARKER not in body:
            continue
        try:
            lines = body.splitlines()
            marker = PartMarker.model_validate_json(
                lines[-1].removeprefix(MARKER).removesuffix(" -->")
            )
            payload = base64.b64decode(lines[1], validate=True)
            if (
                marker.producer.repository != repository
                or marker.part > marker.count
                or len(payload) > PART_BYTES
                or _sha(payload) != marker.sha256
                or _body(marker, payload) != body
            ):
                raise ValueError("conflicting evidence framing or hash")
            payload.decode("utf-8")
        except (ValueError, IndexError) as error:
            raise ValueError("malformed or conflicting owned evidence part") from error
        key = (marker.group, marker.kind, marker.report, marker.part)
        if key in keys or _id(comment) in result:
            raise ValueError("conflicting duplicate evidence parts")
        keys.add(key)
        result[_id(comment)] = marker, payload
    return result


def _assemble(refs: tuple[PartRef, ...], comments: dict[int, tuple[PartMarker, bytes]]) -> bytes:
    if not refs:
        raise ValueError("incomplete evidence: missing part references")
    first = refs[0].marker
    if len(refs) != first.count:
        raise ValueError("incomplete evidence: missing report parts")
    chunks: list[bytes] = []
    for index, ref in enumerate(refs):
        marker = ref.marker
        if marker != first.model_copy(update={"part": index + 1, "sha256": marker.sha256}):
            raise ValueError("conflicting evidence part identities")
        found = comments.get(ref.id)
        if found is None or found[0] != marker:
            raise ValueError("incomplete evidence: missing or conflicting referenced part")
        chunks.append(found[1])
    payload = b"".join(chunks)
    if _sha(payload) != first.report_sha256:
        raise ValueError("conflicting complete report hash")
    return payload


def _validate_publication(publication: PublicationResult) -> int:
    bind_publication(publication.published, publication.promotion_artifact)
    candidate = publication.published.candidate
    request = candidate.declaration.publication_request
    if request is None or request.inputs != candidate.inputs:
        raise ValueError("publication requires the reviewed request and bound inputs")
    return request.issue_number


def _validate_receipt(receipt: OperationReceipt, reports: dict[str, bytes]) -> None:
    _validate_publication(receipt.publication)
    candidate = receipt.publication.published.candidate
    for producer in (receipt.producer, *([receipt.upload.producer] if receipt.upload else [])):
        if (
            producer.repository != candidate.producer.repository
            or producer.source_sha != candidate.source_sha
        ):
            raise ValueError("receipt producer repository/source conflicts with publication")
    if receipt.upload and (
        receipt.upload.publication != receipt.publication
        or receipt.upload.source_sha != candidate.source_sha
    ):
        raise ValueError("upload conflicts with publication")
    if receipt.phase == "publication" and (
        receipt.upload is not None or receipt.state not in {"published", "failed"}
    ):
        raise ValueError("invalid publication receipt state")
    if receipt.state in {"superseded", "deployment_paused"} and receipt.upload is not None:
        raise ValueError("skipped deployment must not claim an upload")
    if receipt.state == "failed" and not receipt.error:
        raise ValueError("failed receipt requires an error")
    if receipt.state != "failed" and receipt.error is not None:
        raise ValueError("successful or skipped receipt must not claim an error")
    if receipt.verification_sha256 is not None:
        payload = reports.get("production-wait.json")
        if payload is None or _sha(payload) != receipt.verification_sha256:
            raise ValueError("missing or conflicting production report digest")
    if receipt.state == "verified":
        if (
            receipt.phase != "deployment"
            or receipt.upload is None
            or receipt.verification_sha256 is None
        ):
            raise ValueError("verified deployment requires upload and both probes")
        value = _object(json.loads(reports["production-wait.json"]))
        if set(value) != {"attempts", "successful_indices", "timed_out"} or not isinstance(
            value["attempts"], list
        ):
            raise ValueError("invalid production wait report")
        attempts = tuple(
            ProductionCheckReport.model_validate_json(json.dumps(item))
            for item in cast(list[Any], value["attempts"])
        )
        indices = value["successful_indices"]
        if (
            not isinstance(indices, list)
            or any(type(index) is not int for index in cast(list[Any], indices))
            or type(value["timed_out"]) is not bool
        ):
            raise ValueError("invalid production wait report indices")
        indices = cast(list[int], indices)
        wait = ProductionWaitReport(attempts, tuple(indices), value["timed_out"])
        if not wait.ok:
            raise ValueError("verified evidence requires two consecutive successful probes")
        for index in wait.successful_indices:
            probe = attempts[index]
            contract = probe.deployment_contract
            if (
                contract is None
                or contract.expected_git_commit != candidate.source_sha
                or contract.expected_site.elections[0] != candidate.declaration
                or probe.commit is None
                or probe.commit.expected != candidate.source_sha
                or probe.archive_index is None
                or not probe.route_results
            ):
                raise ValueError("verified probes do not bind the publication source/site")
            if not complete_strict_report(
                probe,
                contract.expected_site,
                candidate.source_sha,
                probe.data_freshness is not None,
            ):
                raise ValueError("verified evidence requires complete strict probes")
        if attempts[indices[0]].deployment_contract != attempts[indices[1]].deployment_contract:
            raise ValueError("successful probe contracts conflict")


def _index_parts(
    data: bytes, marker: PartMarker, comments: dict[int, tuple[PartMarker, bytes]], depth: int = 0
) -> tuple[PartRef, ...]:
    if depth > 10:
        raise ValueError("evidence index nesting exceeds framing bound")
    refs = EvidenceIndex.model_validate_json(data).parts
    if not refs or any(
        (
            ref.marker.group,
            ref.marker.producer,
            ref.marker.phase,
            ref.marker.release_version,
        )
        != (marker.group, marker.producer, marker.phase, marker.release_version)
        for ref in refs
    ):
        raise ValueError("conflicting evidence index identities")
    if all(ref.marker.kind == "index" for ref in refs):
        return _index_parts(_assemble(refs, comments), marker, comments, depth + 1)
    if depth == 0 or any(ref.marker.kind != "report" for ref in refs):
        raise ValueError("conflicting evidence index kinds")
    return refs


def _check_canonical_receipts(
    comments: dict[int, tuple[PartMarker, bytes]], extra: OperationReceipt | None = None
) -> None:
    # An unsealed group cannot prove completion, but a complete receipt fragment
    # already binds its canonical upload identity and must not be contradicted.
    groups: dict[str, list[PartRef]] = {}
    for comment_id, (marker, _) in comments.items():
        if marker.kind == "report" and marker.report == "receipt.json":
            groups.setdefault(marker.group, []).append(PartRef(id=comment_id, marker=marker))
    receipts = [extra] if extra is not None else []
    for refs in groups.values():
        ordered = tuple(sorted(refs, key=lambda ref: ref.marker.part))
        if len(ordered) != ordered[0].marker.count:
            continue
        data = _assemble(ordered, comments)
        if _sha(data) != ordered[0].marker.group:
            raise ValueError("conflicting operation receipt digest")
        receipts.append(OperationReceipt.model_validate_json(data))
    # Different observations/runs may coexist; canonical publication and upload may not.
    identities: dict[tuple[str, str, str], tuple[PublicationResult, UploadReceipt | None]] = {}
    for receipt in receipts:
        candidate = receipt.publication.published.candidate
        key = (
            candidate.producer.repository,
            candidate.declaration.release_version,
            candidate.source_sha,
        )
        previous = identities.get(key)
        if previous and (
            previous[0] != receipt.publication
            or (previous[1] and receipt.upload and previous[1] != receipt.upload)
        ):
            raise ValueError("conflicting canonical publication/upload receipts")
        identities[key] = (
            receipt.publication,
            receipt.upload or (previous[1] if previous else None),
        )


def _completed(
    comments: dict[int, tuple[PartMarker, bytes]], issue_number: int
) -> list[tuple[OperationReceipt, dict[str, bytes]]]:
    _check_canonical_receipts(comments)
    completed: list[tuple[OperationReceipt, dict[str, bytes]]] = []
    for marker, payload in comments.values():
        if marker.kind != "seal":
            continue
        if marker.part != 1 or marker.count != 1 or marker.report_sha256 != _sha(payload):
            raise ValueError("invalid evidence seal")

        report_refs = _index_parts(payload, marker, comments)
        by_report: dict[str, list[PartRef]] = {}
        for ref in report_refs:
            if ref.marker.kind != "report" or ref.marker.group != marker.group:
                raise ValueError("conflicting evidence report reference")
            by_report.setdefault(ref.marker.report, []).append(ref)
        reports = {name: _assemble(tuple(refs), comments) for name, refs in by_report.items()}
        if "receipt.json" not in reports or _sha(reports["receipt.json"]) != marker.group:
            raise ValueError("missing or conflicting operation receipt")
        receipt = OperationReceipt.model_validate_json(reports.pop("receipt.json"))
        if (
            _validate_publication(receipt.publication) != issue_number
            or marker.producer != receipt.producer
            or marker.phase != receipt.phase
            or marker.release_version
            != receipt.publication.published.candidate.declaration.release_version
        ):
            raise ValueError("receipt marker conflicts with its reviewed request")
        _validate_receipt(receipt, reports)
        completed.append((receipt, reports))
    return completed


def load_verified_receipts(
    *, repository: str, issue_number: int, release_version: str, source_sha: str
) -> tuple[OperationReceipt, ...]:
    """Load complete authenticated receipts of every state; partial groups are excluded."""
    return tuple(
        receipt
        for receipt, _ in _completed(_comments(repository, issue_number), issue_number)
        if receipt.producer.source_sha == source_sha
        and receipt.publication.published.candidate.declaration.release_version == release_version
    )


def read_evidence_reports(receipt: OperationReceipt, *, issue_number: int) -> dict[str, bytes]:
    for existing, reports in _completed(
        _comments(receipt.producer.repository, issue_number), issue_number
    ):
        if existing == receipt:
            return reports
    raise ValueError("complete evidence receipt is unavailable")


def retain_evidence(
    receipt: OperationReceipt, *, issue_number: int, reports: dict[str, bytes]
) -> tuple[int, ...]:
    """Append missing parts and seal last. Never edit a comment, including human text."""
    receipt = OperationReceipt.model_validate_json(_bytes(receipt))
    if _validate_publication(receipt.publication) != issue_number:
        raise ValueError("evidence issue differs from reviewed request")
    if "receipt.json" in reports:
        raise ValueError("receipt.json is reserved")
    _validate_receipt(receipt, reports)
    comments = _comments(receipt.producer.repository, issue_number)
    _completed(comments, issue_number)
    _check_canonical_receipts(comments, extra=receipt)
    refs: list[PartRef] = []
    all_ids: list[int] = []

    def retain(
        name: str, data: bytes, kind: Literal["report", "index", "seal"]
    ) -> tuple[PartRef, ...]:
        retained: list[PartRef] = []
        for marker, chunk in _parts(receipt, name, data, kind):
            comment_id: int | None = None
            for existing_id, (existing, content) in comments.items():
                if (existing.group, existing.kind, existing.report, existing.part) == (
                    marker.group,
                    marker.kind,
                    marker.report,
                    marker.part,
                ):
                    if existing != marker or content != chunk:
                        raise ValueError("conflicting existing evidence part")
                    comment_id = existing_id
                    break
            if comment_id is None:
                with tempfile.TemporaryDirectory(prefix="release-evidence-") as temporary:
                    path = Path(temporary) / "comment.json"
                    path.write_bytes(canonical_json_bytes({"body": _body(marker, chunk)}))
                    result = _object(
                        json.loads(
                            run_gh(
                                [
                                    "gh",
                                    "api",
                                    f"repos/{receipt.producer.repository}/issues/{issue_number}/comments",
                                    "--method",
                                    "POST",
                                    "--input",
                                    str(path),
                                ],
                                "could not retain release evidence",
                            )
                        )
                    )
                if not _owned(result.get("user")) or result.get("body") != _body(marker, chunk):
                    raise ValueError("posted evidence ownership/body differs")
                comment_id = _id(result)
                comments[comment_id] = marker, chunk
            all_ids.append(comment_id)
            retained.append(PartRef(id=comment_id, marker=marker))
        return tuple(retained)

    for name, data in sorted({**reports, "receipt.json": _bytes(receipt)}.items()):
        # JSON is canonicalized by its producer; reject arbitrary/noncanonical report bytes.
        if canonical_json_bytes(json.loads(data)) != data:
            raise ValueError("evidence reports require canonical UTF-8 JSON")
        refs.extend(retain(name, data, "report"))
    index_data = _bytes(EvidenceIndex(parts=tuple(refs)))
    for depth in range(10):
        index_refs = retain(f"index-{depth}.json", index_data, "index")
        seal = _bytes(EvidenceIndex(parts=index_refs))
        if len(seal) <= PART_BYTES:
            retain("seal.json", seal, "seal")
            break
        if len(seal) >= len(index_data):
            raise ValueError("evidence index cannot fit bounded framing")
        index_data = seal
    else:
        raise ValueError("evidence index nesting exceeds framing bound")
    _completed(comments, issue_number)
    return tuple(all_ids)


def require_publication_evidence(publication: PublicationResult) -> None:
    issue = _validate_publication(publication)
    candidate = publication.published.candidate
    records = load_verified_receipts(
        repository=candidate.producer.repository,
        issue_number=issue,
        release_version=candidate.declaration.release_version,
        source_sha=candidate.source_sha,
    )
    if any(receipt.publication != publication for receipt in records):
        raise ValueError("conflicting durable publication evidence")
    if not any(
        receipt.phase == "publication" and receipt.state == "published" for receipt in records
    ):
        raise ValueError("durable publication evidence is required before upload")


def deployment_payload(publication: PublicationResult) -> dict[str, Any]:
    """For POST deployments: environment=production, ref=source_sha, auto_merge=false.

    The creator and every status must be the fixed GitHub Actions bot. Payload
    is this object (not free-form release text); sha must equal producer.source_sha.
    Mark success only after finalize returns a durably retained verified receipt.
    """
    return DeploymentPayload(
        managed_by="seattle-election-guide/release-automation",
        issue_number=_validate_publication(publication),
        release_version=publication.published.candidate.declaration.release_version,
        producer=publication.published.candidate.producer,
        publication_sha256=_sha(_bytes(publication)),
    ).model_dump(mode="json")


def validate_deployment(deployment: dict[str, Any], publication: PublicationResult) -> None:
    """Validate the automation-owned GitHub deployment envelope and exact payload."""
    payload = deployment.get("payload")
    if isinstance(payload, str):
        payload = json.loads(payload)
    if (
        not _owned(deployment.get("creator"))
        or deployment.get("environment") != "production"
        or deployment.get("sha") != publication.published.candidate.source_sha
        or payload != deployment_payload(publication)
    ):
        raise ValueError("managed GitHub deployment identity conflicts with publication")


def latest_production_receipt(repository: str) -> OperationReceipt | None:
    verified: list[tuple[int, OperationReceipt]] = []
    for deployment in _pages(f"repos/{repository}/deployments"):
        payload = deployment.get("payload")
        if isinstance(payload, str):
            try:
                payload = json.loads(payload)
            except ValueError:
                if _owned(deployment.get("creator")):
                    raise ValueError("invalid owned deployment payload") from None
        if (
            not isinstance(payload, dict)
            or cast(dict[str, Any], payload).get("managed_by")
            != "seattle-election-guide/release-automation"
        ):
            continue
        if not _owned(deployment.get("creator")):
            raise ValueError("managed deployment is not owned by workflow bot")
        identity = DeploymentPayload.model_validate_json(json.dumps(payload))
        if (
            identity.producer.repository != repository
            or deployment.get("sha") != identity.producer.source_sha
            or deployment.get("environment") != "production"
        ):
            raise ValueError("managed deployment identity conflicts")
        statuses = _pages(f"repos/{repository}/deployments/{_id(deployment)}/statuses")
        if not statuses:
            continue
        if any(not _owned(status.get("creator")) for status in statuses):
            raise ValueError("managed deployment status is not owned by workflow bot")
        latest = max(statuses, key=_id)
        if latest.get("state") not in {
            "success",
            "inactive",
            "failure",
            "error",
            "pending",
            "queued",
            "in_progress",
        }:
            raise ValueError("unknown managed deployment status")
        # GitHub may mark a previously successful deployment inactive automatically.
        successful = [status for status in statuses if status.get("state") == "success"]
        if not successful:
            continue
        receipts = load_verified_receipts(
            repository=repository,
            issue_number=identity.issue_number,
            release_version=identity.release_version,
            source_sha=identity.producer.source_sha,
        )
        matches = [
            receipt
            for receipt in receipts
            if receipt.state == "verified"
            and receipt.upload is not None
            and receipt.upload.github_deployment_id == _id(deployment)
            and deployment_payload(receipt.publication) == identity.model_dump(mode="json")
        ]
        if not matches:
            raise ValueError("managed successful deployment lacks matching durable final evidence")
        if latest.get("state") in {"success", "inactive"}:
            verified.append((max(_id(status) for status in successful), matches[-1]))
    return max(verified, key=lambda item: item[0])[1] if verified else None


def trusted_site(publication: PublicationResult) -> SiteManifest:
    """Read exact Git-object bytes, independent of checkout YAML formatting or HEAD."""
    candidate = publication.published.candidate
    result = subprocess.run(
        ["git", "show", f"{candidate.source_sha}:{SITE_PATH}"], capture_output=True, check=False
    )
    if result.returncode or _sha(result.stdout) != candidate.site_manifest_sha256:
        raise ValueError("trusted site declaration byte hash differs")
    site = SiteManifest.model_validate(yaml.load(result.stdout, Loader=UniqueKeyLoader))
    if site.elections[0] != candidate.declaration:
        raise ValueError("trusted declaration differs from publication")
    return site


def current_producer(source_sha: str) -> Producer:
    """Verification dispatches use trusted current workflow code and original source."""
    try:
        return Producer(
            repository=os.environ["GITHUB_REPOSITORY"],
            source_sha=source_sha,
            workflow_sha=os.environ["GITHUB_SHA"],
            run_id=int(os.environ["GITHUB_RUN_ID"]),
            run_attempt=int(os.environ["GITHUB_RUN_ATTEMPT"]),
        )
    except KeyError as error:
        raise ValueError(f"missing current workflow identity: {error}") from error


def _summary(output_dir: Path, message: str) -> None:
    (output_dir / "summary.md").write_text(message + "\n", encoding="utf-8")
    if summary := os.environ.get("GITHUB_STEP_SUMMARY"):
        with Path(summary).open("a", encoding="utf-8") as sink:
            sink.write(message + "\n")


def record_evidence_failure(output_dir: Path, error: Exception) -> None:
    """Persist a retryable nonzero outcome even when issue comments are unavailable."""
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "finalization-error.json").write_bytes(
        canonical_json_bytes(
            {
                "state": "failed",
                "complete": False,
                "error": str(error),
            }
        )
    )
    _summary(output_dir, f"Release evidence incomplete and retryable: {error}")


def finalize_deployment(
    upload: UploadReceipt, *, site_manifest: SiteManifest, producer: Producer, output_dir: Path
) -> OperationReceipt:
    """Resume from one recorded upload; perform only Git reads, probes, and comments."""
    output_dir.mkdir(parents=True, exist_ok=True)
    receipt = OperationReceipt(
        phase="deployment",
        state="published",
        producer=upload.producer,
        publication=upload.publication,
        upload=upload,
        verification_sha256=None,
        error=None,
    )
    reports: dict[str, bytes] = {}
    admitted = False
    try:
        _validate_receipt(receipt, reports)
        if (
            producer.repository != upload.producer.repository
            or producer.source_sha != upload.source_sha
        ):
            raise ValueError("finalization producer repository/source conflicts with upload")
        if trusted_site(upload.publication) != site_manifest:
            raise ValueError("supplied site differs from captured trusted declaration")
        require_publication_evidence(upload.publication)
        deployment = _object(
            json.loads(
                run_gh(
                    [
                        "gh",
                        "api",
                        f"repos/{producer.repository}/deployments/{upload.github_deployment_id}",
                    ],
                    "could not read recorded GitHub deployment",
                )
            )
        )
        if _id(deployment) != upload.github_deployment_id:
            raise ValueError("managed GitHub deployment identity differs from upload")
        validate_deployment(deployment, upload.publication)
        issue = _validate_publication(upload.publication)
        admitted = True
        (output_dir / "upload.json").write_bytes(_bytes(upload))
        retain_evidence(receipt, issue_number=issue, reports={})
        prior = load_verified_receipts(
            repository=producer.repository,
            issue_number=issue,
            release_version=upload.publication.published.candidate.declaration.release_version,
            source_sha=upload.source_sha,
        )
        complete = next(
            (
                item
                for item in reversed(prior)
                if item.state == "verified" and item.upload == upload
            ),
            None,
        )
        if complete is not None:
            reports = read_evidence_reports(complete, issue_number=issue)
            receipt = complete
        else:
            calendar = read_election_calendar(Path("config/calendar/elections.yaml"))
            active = any(
                milestone.kind == "election_day"
                for milestone, _ in due_milestones(
                    calendar, as_of=datetime.now(UTC).date(), lead_days=7
                )
            )
            report = wait_for_production(
                site_manifest.canonical_origin,
                site_manifest=site_manifest,
                expected_git_commit=upload.source_sha,
                active_window=active,
            )
            reports = {"production-wait.json": canonical_json_bytes(report.model_dump(mode="json"))}
            receipt = OperationReceipt(
                phase="deployment",
                state="verified" if report.ok else "failed",
                producer=producer,
                publication=upload.publication,
                upload=upload,
                verification_sha256=_sha(reports["production-wait.json"]),
                error=None if report.ok else "production confirmation failed",
            )
        for name, data in reports.items():
            (output_dir / name).write_bytes(data)
        (output_dir / "operation-receipt.json").write_bytes(_bytes(receipt))
        retain_evidence(receipt, issue_number=issue, reports=reports)
        _summary(
            output_dir,
            f"Release finalization: {receipt.state}. Evidence retained. "
            "This supplies no editorial approval and does not close the issue.",
        )
        return receipt
    except (OSError, ValueError, yaml.YAMLError) as error:
        if admitted:
            failed = receipt.model_copy(
                update={
                    "producer": producer,
                    "state": "failed",
                    "error": str(error),
                }
            )
            (output_dir / "operation-receipt.json").write_bytes(_bytes(failed))
            # Local receipt/report remain available if comments are unavailable.
            with suppress(OSError, ValueError):
                retain_evidence(
                    failed, issue_number=_validate_publication(upload.publication), reports=reports
                )
        record_evidence_failure(output_dir, error)
        raise
