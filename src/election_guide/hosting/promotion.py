"""Recover exact-source candidates and admit only non-stale production promotion."""

from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import zipfile
from datetime import datetime
from pathlib import Path, PurePosixPath
from typing import Any, cast

from election_guide.github_cli import download_gh, run_gh
from election_guide.hosting.models import SiteManifest
from election_guide.release.automation_models import (
    ArtifactRef,
    CandidateRecord,
    FileDigest,
    OperationReceipt,
    Producer,
    PublicationResult,
)
from election_guide.release.candidate import SITE_MANIFEST, verify_artifact_ref, verify_candidate
from election_guide.release.declaration import hash_release_inputs, resolve_release
from election_guide.release.publication import bind_publication
from election_guide.serialization import canonical_json_bytes

# The five required CI lanes include all four test matrix partitions.
REQUIRED_JOBS = frozenset(
    {
        "Python static checks",
        "Client checks",
        "Repository contracts",
        "pytest (unit)",
        "pytest (integration-comparisons)",
        "pytest (integration-rendering)",
        "pytest (integration-artifacts)",
        "Publication build",
    }
)


def _git(repository: Path, *arguments: str) -> str:
    result = subprocess.run(
        ["git", *arguments], cwd=repository, capture_output=True, text=True, check=False
    )
    if result.returncode:
        raise ValueError(f"release source Git operation failed: {result.stderr.strip()}")
    return result.stdout.strip()


def _run(command: list[str], *, repository: Path) -> None:
    result = subprocess.run(command, cwd=repository, check=False)
    if result.returncode:
        raise ValueError(f"exact-source recovery gate failed: {' '.join(command)}")


def _read(endpoint: str) -> dict[str, Any]:
    value: Any = json.loads(run_gh(["gh", "api", endpoint], "could not read release admission"))
    if not isinstance(value, dict):
        raise ValueError("invalid GitHub admission object")
    return cast(dict[str, Any], value)


def _mapping(value: Any, context: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"invalid GitHub {context} object")
    return cast(dict[str, Any], value)


def _pages(endpoint: str, key: str | None = None) -> list[dict[str, Any]]:
    value: Any = json.loads(
        run_gh(
            ["gh", "api", endpoint, "--paginate", "--slurp"],
            "could not read complete release admission",
        )
    )
    if not isinstance(value, list) or not value:
        raise ValueError("incomplete GitHub admission pages")
    records: list[dict[str, Any]] = []
    for page in cast(list[Any], value):
        entries: Any = (
            cast(dict[str, Any], page).get(key) if key and isinstance(page, dict) else page
        )
        if not isinstance(entries, list):
            raise ValueError("invalid GitHub admission page")
        for entry in cast(list[Any], entries):
            if not isinstance(entry, dict):
                raise ValueError("invalid GitHub admission record")
            records.append(cast(dict[str, Any], entry))
    return records


def _repository_name(repository: Path) -> str:
    remote = _git(repository, "remote", "get-url", "origin")
    match = re.fullmatch(
        r"(?:https://github\.com/|git@github\.com:)([A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+?)(?:\.git)?",
        remote,
    )
    if match is None:
        raise ValueError("release admission requires a GitHub origin repository")
    return match[1]


def _merged_pr(repository: Path, source_sha: str) -> tuple[str, int]:
    if re.fullmatch(r"[0-9a-f]{40}", source_sha) is None:
        raise ValueError("release admission requires a full lowercase source SHA")
    if _git(repository, "rev-parse", "--verify", f"{source_sha}^{{commit}}") != source_sha:
        raise ValueError("release admission source is not the exact commit")
    name = _repository_name(repository)
    base = f"repos/{name}"
    relation = _read(base + f"/compare/{source_sha}...main")
    if (
        relation.get("status") not in {"ahead", "identical"}
        or _mapping(relation.get("merge_base_commit"), "lineage").get("sha") != source_sha
    ):
        raise ValueError("release source is not on main")
    prs = _pages(base + f"/commits/{source_sha}/pulls?per_page=100")
    matches: list[dict[str, Any]] = []
    for pr in prs:
        target = _mapping(pr.get("base"), "PR base")
        if (
            pr.get("merged_at")
            and pr.get("merge_commit_sha") == source_sha
            and target.get("ref") == "main"
            and _mapping(target.get("repo"), "PR repository").get("full_name") == name
        ):
            matches.append(pr)
    if len(matches) != 1 or type(matches[0].get("number")) is not int or matches[0]["number"] <= 0:
        raise ValueError("release source requires one exact merged main PR association")
    return name, matches[0]["number"]


def verify_merged_release_relation(repository: Path, *, source_sha: str) -> int:
    """Source-only preflight; this does not authorize publication before CI passes."""
    return _merged_pr(repository, source_sha)[1]


def _require_producer_run(producer: Producer, run: dict[str, Any]) -> None:
    if (
        run.get("id") != producer.run_id
        or run.get("run_attempt") != producer.run_attempt
        or run.get("head_sha") != producer.workflow_sha
        or run.get("head_branch") != "main"
        or run.get("event") not in {"push", "workflow_dispatch"}
        or run.get("path") != ".github/workflows/ci.yml"
        or _mapping(run.get("repository"), "producer repository").get("full_name")
        != producer.repository
    ):
        raise ValueError("artifact producer or exact-source CI run identity differs")


def _producer_run(producer: Producer) -> dict[str, Any]:
    run = _read(
        f"repos/{producer.repository}/actions/runs/{producer.run_id}/attempts/{producer.run_attempt}"
    )
    _require_producer_run(producer, run)
    return run


def _timestamp(value: Any) -> datetime:
    if not isinstance(value, str):
        raise ValueError("artifact attempt evidence requires timezone-aware timestamps")
    try:
        timestamp = datetime.fromisoformat(value)
    except ValueError as error:
        raise ValueError("artifact attempt evidence contains a malformed timestamp") from error
    if timestamp.tzinfo is None or timestamp.utcoffset() is None:
        raise ValueError("artifact attempt evidence requires timezone-aware timestamps")
    return timestamp


def _require_artifact_attempt(metadata: dict[str, Any], producer: Producer) -> None:
    started = _timestamp(_producer_run(producer).get("run_started_at"))
    created = _timestamp(metadata.get("created_at"))
    # The current attempt supplies interval boundaries only. Artifact selection
    # always uses the captured ID, including when later attempts now exist.
    latest = _read(f"repos/{producer.repository}/actions/runs/{producer.run_id}")
    latest_attempt = latest.get("run_attempt")
    if type(latest_attempt) is not int or latest_attempt < producer.run_attempt:
        raise ValueError("artifact attempt boundaries are unverifiable")
    _require_producer_run(producer.model_copy(update={"run_attempt": latest_attempt}), latest)
    latest_started = _timestamp(latest.get("run_started_at"))
    if (
        created < started
        or (latest_attempt == producer.run_attempt and latest_started != started)
        or (latest_attempt > producer.run_attempt and latest_started <= started)
    ):
        raise ValueError("artifact creation differs from captured producing attempt")
    if latest_attempt > producer.run_attempt:
        next_attempt = producer.run_attempt + 1
        next_run = _producer_run(producer.model_copy(update={"run_attempt": next_attempt}))
        next_started = _timestamp(next_run.get("run_started_at"))
        if (
            next_started <= started
            or next_started > latest_started
            or (next_attempt == latest_attempt and next_started != latest_started)
            or created >= next_started
        ):
            raise ValueError("artifact creation differs from captured producing attempt")


def verify_source_ci(producer: Producer) -> None:
    """Read all successful lane results, even before the parent run completes."""
    run = _producer_run(producer)
    if producer.workflow_sha != producer.source_sha and run.get("event") != "workflow_dispatch":
        raise ValueError("different source requires a trusted main recovery dispatch")
    if run.get("status") not in {"in_progress", "completed"} or (
        run.get("status") == "completed" and run.get("conclusion") != "success"
    ):
        raise ValueError("exact-source CI run failed or is not ready")
    jobs = _pages(
        f"repos/{producer.repository}/actions/runs/{producer.run_id}"
        f"/attempts/{producer.run_attempt}/jobs?per_page=100",
        "jobs",
    )
    for name in REQUIRED_JOBS:
        matches = [job for job in jobs if job.get("name") == name]
        if len(matches) != 1 or any(
            job.get("head_sha") != producer.workflow_sha
            or job.get("status") != "completed"
            or job.get("conclusion") != "success"
            for job in matches
        ):
            raise ValueError(f"exact-source CI lane has not succeeded: {name}")


def verify_merged_release_source(repository: Path, *, source_sha: str) -> int:
    """Admit exact merged source after this captured current run's five lanes pass.

    Actions supplies GITHUB_SHA (workflow SHA), GITHUB_RUN_ID/RUN_ATTEMPT,
    and GITHUB_REF. A recovery dispatch must additionally export the captured
    RELEASE_SOURCE_SHA uniformly to all lanes and final admission. Its trusted
    workflow checks out that original source for every check and build.
    """
    name, number = _merged_pr(repository, source_sha)
    try:
        producer = Producer(
            repository=name,
            source_sha=source_sha,
            workflow_sha=os.environ["GITHUB_SHA"],
            run_id=int(os.environ["GITHUB_RUN_ID"]),
            run_attempt=int(os.environ["GITHUB_RUN_ATTEMPT"]),
        )
    except (KeyError, ValueError) as error:
        raise ValueError("admission requires a captured current CI producing attempt") from error
    if os.environ.get("GITHUB_REF") != "refs/heads/main":
        raise ValueError("current CI admission requires the main ref")
    captured_source = os.environ.get("RELEASE_SOURCE_SHA", producer.workflow_sha)
    if captured_source != source_sha:
        raise ValueError("current CI captured release source differs from admission source")
    verify_source_ci(producer)
    return number


def _artifact_available(reference: ArtifactRef) -> bool:
    try:
        metadata = _read(f"repos/{reference.producer.repository}/actions/artifacts/{reference.id}")
    except ValueError as error:
        if re.search(r"\bHTTP 404\b", str(error)):
            return False
        raise
    workflow = _mapping(metadata.get("workflow_run"), "artifact producer")
    if (
        metadata.get("id") != reference.id
        or metadata.get("name") != reference.name
        or metadata.get("size_in_bytes") != reference.digest.size
        or metadata.get("digest") != "sha256:" + reference.digest.sha256
        or type(metadata.get("expired")) is not bool
        or workflow.get("id") != reference.producer.run_id
        or workflow.get("head_sha") != reference.producer.workflow_sha
        or workflow.get("head_branch") != "main"
    ):
        raise ValueError("artifact metadata differs from captured identity")
    _require_artifact_attempt(metadata, reference.producer)
    observed = ArtifactRef(
        id=metadata["id"],
        name=metadata["name"],
        digest=reference.digest,
        producer=reference.producer,
    )
    verify_artifact_ref(reference, observed)
    return not metadata["expired"]


def _download_artifact(reference: ArtifactRef, destination: Path) -> None:
    wrapper = destination.with_suffix(".zip")
    download_gh(
        [
            "gh",
            "api",
            f"repos/{reference.producer.repository}/actions/artifacts/{reference.id}/zip",
        ],
        wrapper,
        "could not download captured Actions artifact",
    )
    content = wrapper.read_bytes()
    if (
        FileDigest(sha256=hashlib.sha256(content).hexdigest(), size=len(content))
        != reference.digest
    ):
        raise ValueError("artifact download differs from captured wrapper digest")
    try:
        with zipfile.ZipFile(wrapper) as archive:
            names = archive.namelist()
            if len(names) != len(set(names)):
                raise ValueError("artifact wrapper contains duplicate members")
            for name in names:
                path = PurePosixPath(name)
                if (
                    not name
                    or path.is_absolute()
                    or ".." in path.parts
                    or "\\" in name
                    or path.as_posix() != name.rstrip("/")
                ):
                    raise ValueError("artifact wrapper contains invalid members")
                target = destination / name
                if name.endswith("/"):
                    target.mkdir(parents=True, exist_ok=True)
                else:
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.write_bytes(archive.read(name))
    except (zipfile.BadZipFile, RuntimeError, NotImplementedError) as error:
        raise ValueError("artifact wrapper is unreadable") from error


def recover_candidate(candidate: CandidateRecord, *, repository: Path, work_dir: Path) -> Path:
    """Reuse captured healthy artifacts or rerun every gate at the original detached source.

    Replacement uploads and the fresh candidate record belong to the workflow. This
    function preserves the original evidence and never rewrites a published archive.
    """
    candidate = CandidateRecord.model_validate(candidate.model_dump())
    repository, work_dir = repository.resolve(), work_dir.resolve()
    available = [
        _artifact_available(ref) for ref in (candidate.release_artifact, candidate.site_artifact)
    ]
    if work_dir.exists():
        raise ValueError("candidate recovery requires a fresh work directory")
    name, _ = _merged_pr(repository, candidate.source_sha)
    if name != candidate.producer.repository:
        raise ValueError("recovery repository differs from captured producer")
    work_dir.mkdir(parents=True)
    (work_dir / "original-candidate.json").write_bytes(
        canonical_json_bytes(candidate.model_dump(mode="json"))
    )
    checkout = work_dir / "source"
    _git(repository, "worktree", "add", "--detach", str(checkout), candidate.source_sha)
    try:
        resolved = resolve_release(SITE_MANIFEST, repository=checkout)
        if (
            resolved.current != candidate.declaration
            or hash_release_inputs(resolved.inputs) != candidate.inputs
            or hashlib.sha256((checkout / SITE_MANIFEST).read_bytes()).hexdigest()
            != candidate.site_manifest_sha256
        ):
            raise ValueError("recovery source declaration or reviewed inputs differ")
        if all(available):
            _download_artifact(candidate.release_artifact, work_dir / "reproducibility-a")
            _download_artifact(candidate.site_artifact, work_dir / "cloudflare-site")
        else:
            for command in (["uv", "sync", "--frozen"], ["npm", "ci"], ["make", "check"]):
                _run(command, repository=checkout)
            _run(
                [
                    "uv",
                    "run",
                    "election-guide",
                    "release",
                    "automation",
                    "build",
                    "--source-sha",
                    candidate.source_sha,
                    "--output-dir",
                    str(work_dir),
                ],
                repository=checkout,
            )
        archive = work_dir / "reproducibility-a" / resolved.archive_name
        # Rebuilt screenshots may vary under the explicit schema exclusion. New
        # byte identities are captured by record_candidate after fresh uploads.
        if all(available):
            verify_candidate(
                candidate,
                repository=checkout,
                archive_path=archive,
                site_dir=work_dir / "cloudflare-site",
            )
        elif not archive.is_file():
            raise ValueError("exact-source build did not produce its release archive")
        if _git(checkout, "rev-parse", "HEAD") != candidate.source_sha or _git(
            checkout, "status", "--porcelain", "--untracked-files=normal"
        ):
            raise ValueError("recovery checkout changed during checks")
        return archive
    finally:
        _git(repository, "worktree", "remove", "--force", str(checkout))


def promotion_allowed(
    publication: PublicationResult,
    *,
    selected: SiteManifest,
    latest_verified: OperationReceipt | None,
) -> bool:
    """Call under the mainline lock immediately before the sole Pages upload.

    False means a newer declaration superseded this publication. Unverifiable or
    conflicting state raises so the caller records a failed operation instead.
    """
    publication = PublicationResult.model_validate(publication.model_dump())
    selected = SiteManifest.model_validate(selected.model_dump())
    bind_publication(publication.published, publication.promotion_artifact)
    candidate = publication.published.candidate
    if (
        candidate.declaration.publication_request is None
        or candidate.inputs != candidate.declaration.publication_request.inputs
    ):
        raise ValueError("candidate conflicts with reviewed publication request")
    current = selected.elections[0]
    if current != candidate.declaration:
        old = candidate.declaration
        old_version, _, old_number = old.release_version.rpartition(".")
        new_version, _, new_number = current.release_version.rpartition(".")
        if (
            current.election_id == old.election_id
            and new_version == old_version
            and old_number.isdigit()
            and new_number.isdigit()
            and int(new_number) > int(old_number)
            and current.publication_request is not None
        ):
            return False
        raise ValueError("selected declaration conflicts with candidate publication")
    if latest_verified is None:
        return True
    prior = OperationReceipt.model_validate(latest_verified.model_dump())
    previous = prior.publication.published.candidate
    if (
        prior.phase != "deployment"
        or prior.state != "verified"
        or prior.error is not None
        or prior.verification_sha256 is None
        or prior.upload is None
        or prior.upload.publication != prior.publication
        or prior.upload.source_sha != previous.source_sha
        or prior.producer != prior.upload.producer
        or prior.producer.source_sha != previous.source_sha
        or prior.producer.repository != candidate.producer.repository
        or previous.producer.repository != candidate.producer.repository
    ):
        raise ValueError("latest durable production receipt is unverifiable")
    bind_publication(prior.publication.published, prior.publication.promotion_artifact)
    if previous.source_sha == candidate.source_sha:
        fields = (
            "release_id",
            "asset_id",
            "asset_name",
            "archive",
            "release_manifest_sha256",
            "canonical_bundle_sha256",
            "promotion_manifest_sha256",
        )
        if previous.declaration != candidate.declaration or any(
            getattr(prior.publication.published, field) != getattr(publication.published, field)
            for field in fields
        ):
            raise ValueError("same-source production publication conflicts with canonical identity")
        return True
    relation = _read(
        f"repos/{candidate.producer.repository}/compare/{previous.source_sha}...{candidate.source_sha}"
    )
    if (
        relation.get("status") != "ahead"
        or _mapping(relation.get("merge_base_commit"), "lineage").get("sha") != previous.source_sha
    ):
        raise ValueError("production lineage is older, incomparable, or unverifiable")
    return True
