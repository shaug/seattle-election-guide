"""Reviewed declarations, exact-source candidates, and immutable archive publication."""

from __future__ import annotations

import io
import json
import re
import subprocess
import tarfile
import tempfile
from dataclasses import asdict
from pathlib import Path
from typing import Annotated, Any, cast

import typer
import yaml

from election_guide.github_cli import parse_paginated_objects, run_gh
from election_guide.hosting.models import SiteManifest
from election_guide.hosting.promotion import (
    promotion_allowed,
    recover_candidate,
    verify_merged_release_relation,
    verify_merged_release_source,
)
from election_guide.hosting.releases import (
    published_release_tags,
    verify_declared_releases_published,
)
from election_guide.release.automation_models import (
    ArtifactRef,
    CandidateRecord,
    OperationReceipt,
    Producer,
    PublicationResult,
    PublishedArchive,
)
from election_guide.release.candidate import (
    build_current_candidate,
    record_candidate,
    stage_current_candidate,
    verify_candidate,
)
from election_guide.release.declaration import (
    ResolvedRelease,
    prepare_release,
    require_ancestor,
    resolve_release,
    validate_release_request,
    validate_unpublished_predecessor,
)
from election_guide.release.history import generate_changelog_index
from election_guide.release.publication import (
    bind_publication,
    publish_candidate,
    verify_published_release_source,
)
from election_guide.serialization import UniqueKeyLoader, canonical_json_bytes

app = typer.Typer(help="Prepare and validate reviewed release declarations.")
DEFAULT_SITE = Path("config/hosting/site.yaml")


def _git(repository: Path, *arguments: str) -> str:
    result = subprocess.run(
        ["git", *arguments],
        cwd=repository,
        check=False,
        text=True,
        capture_output=True,
    )
    if result.returncode != 0:
        raise ValueError(f"could not read Git objects: {result.stderr.strip()}")
    return result.stdout.strip()


def _repository() -> Path:
    return Path(_git(Path.cwd(), "rev-parse", "--show-toplevel"))


def _manifest_at(repository: Path, revision: str, path: Path) -> SiteManifest:
    return SiteManifest.model_validate(
        yaml.load(
            _git(repository, "show", f"{revision}:{path.as_posix()}"),
            Loader=UniqueKeyLoader,
        )
    )


def _relative_site(repository: Path, path: Path) -> Path:
    try:
        return (repository / path).resolve().relative_to(repository.resolve())
    except ValueError as error:
        raise ValueError("site manifest must be inside the repository") from error


def _remote_versions() -> frozenset[str]:
    versions: set[str] = set()
    for endpoint, key in (("tags", "name"), ("releases", "tag_name")):
        entries = parse_paginated_objects(
            run_gh(
                [
                    "gh",
                    "api",
                    f"repos/{{owner}}/{{repo}}/{endpoint}?per_page=100",
                    "--paginate",
                    "--slurp",
                ],
                f"could not read complete remote {endpoint}",
            ),
            context=f"remote {endpoint}",
        )
        for entry in entries:
            name = entry.get(key)
            if not isinstance(name, str) or not name:
                raise ValueError(f"incomplete remote {endpoint} query")
            if name in versions and endpoint == "tags":
                raise ValueError("duplicate remote tag name")
            versions.add(name)
    return frozenset(versions)


def _remote_commit(endpoint: str, *, allow_tag: bool = False) -> str:
    seen: set[str] = set()
    while True:
        payload: Any = json.loads(
            run_gh(
                ["gh", "api", f"repos/{{owner}}/{{repo}}/{endpoint}"],
                "could not read remote release boundary",
            )
        )
        if not isinstance(payload, dict):
            raise ValueError("incomplete remote Git object")
        target = cast(dict[str, Any], payload).get("object")
        if not isinstance(target, dict):
            raise ValueError("incomplete remote Git object")
        target = cast(dict[str, Any], target)
        sha, kind = target.get("sha"), target.get("type")
        if not isinstance(sha, str) or re.fullmatch(r"[0-9a-f]{40}", sha) is None:
            raise ValueError("remote Git object requires a full lowercase commit SHA")
        if kind == "commit":
            return sha
        if not allow_tag or kind != "tag" or sha in seen:
            raise ValueError("remote release boundary does not resolve to a commit")
        seen.add(sha)
        endpoint = f"git/tags/{sha}"


def _ensure_commit(repository: Path, sha: str) -> None:
    present = subprocess.run(
        ["git", "cat-file", "-e", f"{sha}^{{commit}}"],
        cwd=repository,
        capture_output=True,
        check=False,
    )
    if present.returncode != 0:
        _git(repository, "fetch", "--no-tags", "origin", sha)
    if _git(repository, "rev-parse", "--verify", f"{sha}^{{commit}}") != sha:
        raise ValueError("captured remote revision is not the expected commit")


def _remote_main(
    repository: Path, path: Path, occupied: frozenset[str]
) -> tuple[SiteManifest, str]:
    sha = _remote_commit("git/ref/heads/main")
    main = SiteManifest.model_validate(
        yaml.load(
            run_gh(
                [
                    "gh",
                    "api",
                    f"repos/{{owner}}/{{repo}}/contents/{path.as_posix()}?ref={sha}",
                    "-H",
                    "Accept: application/vnd.github.raw+json",
                ],
                "could not read the captured main declaration",
            ),
            Loader=UniqueKeyLoader,
        )
    )
    selected = main.elections[0]
    if selected.release_version not in occupied and selected.publication_request is not None:
        return main, _unpublished_base_sha(repository, path, main, occupied, base_sha=sha)
    previous_sha = _remote_commit(f"git/ref/tags/{selected.release_version}", allow_tag=True)
    verify_published_release_source("repos/{owner}/{repo}", selected.release_version, previous_sha)
    if selected.git_commit is not None and previous_sha != selected.git_commit:
        raise ValueError("selected published release tag differs from its pinned commit")
    _ensure_commit(repository, previous_sha)
    require_ancestor(previous_sha, repository=repository)
    return main, previous_sha


def _published_sha(repository: Path, site: SiteManifest) -> str:
    selected = site.elections[0]
    sha = _git(
        repository, "rev-parse", "--verify", f"refs/tags/{selected.release_version}^{{commit}}"
    )
    if selected.git_commit is not None and sha != selected.git_commit:
        raise ValueError("selected published release tag differs from its pinned commit")
    require_ancestor(sha, repository=repository)
    return sha


def _unpublished_base_sha(
    repository: Path, path: Path, base: SiteManifest, occupied: frozenset[str], *, base_sha: str
) -> str:
    selected = base.elections[0]
    request = selected.publication_request
    if selected.release_version in occupied or request is None:
        raise ValueError("recovery requires an unreserved unpublished base release")
    # A failed tag lookup or local absence is never evidence of remote absence.
    _ensure_commit(repository, base_sha)
    _ensure_commit(repository, request.previous_release_sha)
    previous = _manifest_at(repository, request.previous_release_sha, path)
    validate_unpublished_predecessor(base, previous)
    predecessor = previous.elections[0]
    if (
        predecessor.git_commit is not None
        and predecessor.git_commit != request.previous_release_sha
    ):
        raise ValueError("previous published declaration differs from its exact source")
    verify_published_release_source(
        "repos/{owner}/{repo}", predecessor.release_version, request.previous_release_sha
    )
    require_ancestor(request.previous_release_sha, repository=repository, source_sha=base_sha)
    return request.previous_release_sha


def _admit_request(
    current: ResolvedRelease,
    *,
    repository: Path,
    path: Path,
    base: SiteManifest,
    base_sha: str,
    changed_paths: tuple[str, ...],
) -> bool:
    if current.site == base:
        return validate_release_request(current, base=base, changed_paths=changed_paths)
    recovery_sha = None
    if base.elections[0].publication_request is not None:
        occupied = _remote_versions()
        if base.elections[0].release_version not in occupied:
            recovery_sha = _unpublished_base_sha(
                repository, path, base, occupied, base_sha=base_sha
            )
    requested = validate_release_request(
        current,
        base=base,
        changed_paths=changed_paths,
        verified_unpublished_base_sha=recovery_sha,
    )
    if requested:
        request = current.current.publication_request
        assert request is not None
        boundary = recovery_sha or _published_sha(repository, base)
        if request.previous_release_sha != boundary:
            raise ValueError("publication request previous release boundary is stale")
        if recovery_sha is None and base.elections[0].publication_request is not None:
            verify_published_release_source(
                "repos/{owner}/{repo}", base.elections[0].release_version, boundary
            )
        require_ancestor(boundary, repository=repository)
    return requested


def _echo_resolved(resolved: ResolvedRelease) -> None:
    typer.echo(
        json.dumps(
            {
                "site": resolved.site.model_dump(mode="json"),
                "current": resolved.current.model_dump(mode="json"),
                "inputs": {key: str(path) for key, path in asdict(resolved.inputs).items()},
                "archive_name": resolved.archive_name,
            },
            sort_keys=True,
        )
    )


def _failed(error: Exception) -> None:
    typer.echo(f"release automation failed: {error}", err=True)
    raise typer.Exit(code=1) from error


@app.command("resolve")
def resolve(site_manifest: Annotated[Path, typer.Option()] = DEFAULT_SITE) -> None:
    """Write the selected release identity and resolved paths as JSON."""
    try:
        _echo_resolved(resolve_release(site_manifest, repository=_repository()))
    except (OSError, ValueError, yaml.YAMLError) as error:
        _failed(error)


@app.command("prepare")
def prepare(
    issue: Annotated[int, typer.Option(min=1)],
    site_manifest: Annotated[Path, typer.Option()] = DEFAULT_SITE,
) -> None:
    """Refresh the local current declaration against main and remote names."""
    try:
        repository = _repository()
        relative = _relative_site(repository, site_manifest)
        occupied = _remote_versions()
        main, previous_sha = _remote_main(repository, relative, occupied)
        if (
            main.elections[0].release_version not in occupied
            and main.elections[0].publication_request is not None
            and main.elections[0].publication_request.issue_number != issue
        ):
            raise ValueError("unpublished base recovery requires the same owner")
        _echo_resolved(
            prepare_release(
                relative,
                repository=repository,
                issue_number=issue,
                main_manifest=main,
                occupied_versions=occupied,
                previous_release_sha=previous_sha,
            )
        )
    except (OSError, ValueError, yaml.YAMLError) as error:
        _failed(error)


@app.command("validate-request")
def validate_request(
    base_sha: Annotated[str, typer.Option()],
    site_manifest: Annotated[Path, typer.Option()] = DEFAULT_SITE,
) -> None:
    """Admit the exact base-to-HEAD Git comparison, ignoring working-tree bytes."""
    try:
        repository = _repository()
        if _git(repository, "status", "--porcelain", "--untracked-files=no"):
            raise ValueError("request admission requires a clean tracked checkout")
        if re.fullmatch(r"[0-9a-f]{40}", base_sha) is None:
            raise ValueError("base SHA must be a full lowercase Git commit ID")
        require_ancestor(base_sha, repository=repository)
        relative = _relative_site(repository, site_manifest)
        base = _manifest_at(repository, base_sha, relative)
        paths = tuple(
            _git(repository, "diff", "--no-renames", "--name-only", "-z", base_sha, "HEAD")
            .rstrip("\0")
            .split("\0")
        )
        archive = subprocess.run(
            ["git", "archive", "HEAD"],
            cwd=repository,
            check=True,
            capture_output=True,
        ).stdout
        with tempfile.TemporaryDirectory(prefix="release-admission-") as temporary:
            with tarfile.open(fileobj=io.BytesIO(archive)) as tree:
                tree.extractall(temporary, filter="data")
            current = resolve_release(relative, repository=Path(temporary))
            requested = _admit_request(
                current,
                repository=repository,
                path=relative,
                base=base,
                base_sha=base_sha,
                changed_paths=paths,
            )
        typer.echo(json.dumps({"requests_release": requested}, sort_keys=True))
    except (
        OSError,
        ValueError,
        yaml.YAMLError,
        subprocess.CalledProcessError,
        tarfile.TarError,
    ) as error:
        _failed(error)


@app.command("changelog-index")
def changelog_index(output: Annotated[Path, typer.Option()]) -> None:
    """Write the stable published-release index and retained historical sections."""
    try:
        output.write_text(generate_changelog_index(_repository()), encoding="utf-8")
    except (OSError, ValueError) as error:
        _failed(error)


@app.command("build")
def build(
    source_sha: Annotated[str, typer.Option()],
    output_dir: Annotated[Path, typer.Option()],
) -> None:
    """Build twice, compare, and stage the exact selected source revision."""
    try:
        repository = _repository()
        typer.echo(
            build_current_candidate(
                resolve_release(DEFAULT_SITE, repository=repository),
                repository=repository,
                output_dir=output_dir,
                source_sha=source_sha,
            )
        )
    except (OSError, ValueError, yaml.YAMLError) as error:
        _failed(error)


@app.command("stage")
def stage(
    bundle_dir: Annotated[Path, typer.Option()],
    output_dir: Annotated[Path, typer.Option()],
    source_sha: Annotated[str, typer.Option()],
) -> None:
    """Stage and independently verify the complete declared archive."""
    try:
        repository = _repository()
        resolved = resolve_release(DEFAULT_SITE, repository=repository)
        verify_declared_releases_published(
            resolved.site, published_release_tags(), candidate_bundle_id=resolved.current.bundle_id
        )
        stage_current_candidate(
            resolved,
            repository=repository,
            bundle_dir=bundle_dir,
            output_dir=output_dir,
            source_sha=source_sha,
        )
    except (OSError, ValueError, yaml.YAMLError) as error:
        _failed(error)


@app.command("record")
def record(
    producer_file: Annotated[Path, typer.Option()],
    release_artifact_file: Annotated[Path, typer.Option()],
    site_artifact_file: Annotated[Path, typer.Option()],
    output: Annotated[Path, typer.Option()],
    recovered_from_file: Annotated[Path | None, typer.Option()] = None,
) -> None:
    """Bind the two already-uploaded artifact identities into canonical JSON."""
    try:
        repository = _repository()
        result = record_candidate(
            resolve_release(DEFAULT_SITE, repository=repository),
            repository=repository,
            output_dir=output.parent,
            producer=Producer.model_validate_json(producer_file.read_bytes()),
            release_artifact=ArtifactRef.model_validate_json(release_artifact_file.read_bytes()),
            site_artifact=ArtifactRef.model_validate_json(site_artifact_file.read_bytes()),
            recovered_from=(
                Producer.model_validate_json(recovered_from_file.read_bytes())
                if recovered_from_file
                else None
            ),
        )
        output.write_bytes(canonical_json_bytes(result.model_dump(mode="json")))
    except (OSError, ValueError, yaml.YAMLError) as error:
        _failed(error)


@app.command("verify-candidate")
def verify_candidate_command(
    record: Annotated[Path, typer.Option()],
    archive: Annotated[Path, typer.Option()],
    site_dir: Annotated[Path, typer.Option()],
) -> None:
    """Verify downloaded release and site bytes against the captured candidate."""
    try:
        verify_candidate(
            CandidateRecord.model_validate_json(record.read_bytes()),
            repository=_repository(),
            archive_path=archive,
            site_dir=site_dir,
        )
    except (OSError, ValueError, yaml.YAMLError) as error:
        _failed(error)


@app.command("publish")
def publish(
    record: Annotated[Path, typer.Option()],
    candidate_artifact_file: Annotated[Path, typer.Option()],
    archive: Annotated[Path, typer.Option()],
    output_dir: Annotated[Path, typer.Option()],
    existing_receipt: Annotated[Path | None, typer.Option()] = None,
) -> None:
    """Publish or recover a canonical archive and independently verified promotion site."""
    try:
        publish_candidate(
            CandidateRecord.model_validate_json(record.read_bytes()),
            candidate_artifact=ArtifactRef.model_validate_json(
                candidate_artifact_file.read_bytes()
            ),
            repository=_repository(),
            archive_path=archive,
            work_dir=output_dir,
            existing_receipt=(
                PublicationResult.model_validate_json(existing_receipt.read_bytes())
                if existing_receipt
                else None
            ),
        )
    except (OSError, ValueError, yaml.YAMLError) as error:
        _failed(error)


@app.command("bind-publication")
def bind_publication_command(
    published: Annotated[Path, typer.Option()],
    promotion_artifact_file: Annotated[Path, typer.Option()],
    output: Annotated[Path, typer.Option()],
) -> None:
    """Capture the promotion artifact identity after its Actions upload completes."""
    try:
        result = bind_publication(
            PublishedArchive.model_validate_json(published.read_bytes()),
            ArtifactRef.model_validate_json(promotion_artifact_file.read_bytes()),
        )
        output.write_bytes(canonical_json_bytes(result.model_dump(mode="json")))
    except (OSError, ValueError) as error:
        _failed(error)


def _selected_main(repository: Path) -> SiteManifest:
    """Capture main once, then read that exact selection immediately before upload."""
    sha = _remote_commit("git/ref/heads/main")
    return SiteManifest.model_validate(
        yaml.load(
            run_gh(
                [
                    "gh",
                    "api",
                    f"repos/{{owner}}/{{repo}}/contents/{DEFAULT_SITE.as_posix()}?ref={sha}",
                    "-H",
                    "Accept: application/vnd.github.raw+json",
                ],
                "could not read final main selection",
            ),
            Loader=UniqueKeyLoader,
        )
    )


@app.command("admit")
def admit(
    source_sha: Annotated[str, typer.Option()],
    base_sha: Annotated[str, typer.Option()],
    preflight: Annotated[bool, typer.Option()] = False,
) -> None:
    """Admit after five current CI lanes pass; --preflight only checks request readiness.

    Recovery dispatches export RELEASE_SOURCE_SHA for the captured source while
    GITHUB_SHA identifies the trusted main workflow revision.
    """
    try:
        repository = _repository()
        number = (
            verify_merged_release_relation(repository, source_sha=source_sha)
            if preflight
            else verify_merged_release_source(repository, source_sha=source_sha)
        )
        if re.fullmatch(r"[0-9a-f]{40}", base_sha) is None:
            raise ValueError("base SHA must be a full lowercase Git commit ID")
        if _git(repository, "merge-base", base_sha, source_sha) != base_sha:
            raise ValueError("admission base must be an ancestor of source")
        base = _manifest_at(repository, base_sha, DEFAULT_SITE)
        paths = tuple(
            _git(repository, "diff", "--no-renames", "--name-only", "-z", base_sha, source_sha)
            .rstrip("\0")
            .split("\0")
        )
        archive = subprocess.run(
            ["git", "archive", source_sha], cwd=repository, check=True, capture_output=True
        ).stdout
        with tempfile.TemporaryDirectory(prefix="merged-release-admission-") as temporary:
            with tarfile.open(fileobj=io.BytesIO(archive)) as tree:
                tree.extractall(temporary, filter="data")
            current = resolve_release(DEFAULT_SITE, repository=Path(temporary))
            requested = _admit_request(
                current,
                repository=repository,
                path=DEFAULT_SITE,
                base=base,
                base_sha=base_sha,
                changed_paths=paths,
            )
        typer.echo(
            json.dumps(
                {
                    "eligible": requested and not preflight,
                    "requests_release": requested,
                    "ci_verified": not preflight,
                    "state": ("pending_ci" if preflight else "eligible")
                    if requested
                    else "not_requested",
                    "source_sha": source_sha,
                    "pull_request": number,
                },
                sort_keys=True,
            )
        )
    except (
        OSError,
        ValueError,
        yaml.YAMLError,
        subprocess.CalledProcessError,
        tarfile.TarError,
    ) as error:
        typer.echo(
            json.dumps({"eligible": False, "state": "failed", "error": str(error)}, sort_keys=True)
        )
        _failed(error)


@app.command("recover")
def recover(
    record: Annotated[Path, typer.Option()],
    output_dir: Annotated[Path, typer.Option()],
) -> None:
    """Recover captured files; fresh artifact uploads and recording follow in Actions."""
    try:
        archive = recover_candidate(
            CandidateRecord.model_validate_json(record.read_bytes()),
            repository=_repository(),
            work_dir=output_dir,
        )
        typer.echo(
            json.dumps(
                {
                    "archive": str(archive),
                    "original_candidate": str(output_dir / "original-candidate.json"),
                },
                sort_keys=True,
            )
        )
    except (OSError, ValueError, yaml.YAMLError) as error:
        _failed(error)


@app.command("promotion-check")
def promotion_check(
    publication: Annotated[Path, typer.Option()],
    output: Annotated[Path, typer.Option()],
    latest_verified: Annotated[Path | None, typer.Option()] = None,
) -> None:
    """Under the workflow lock, check the captured main selection before the sole upload."""
    try:
        allowed = promotion_allowed(
            PublicationResult.model_validate_json(publication.read_bytes()),
            selected=_selected_main(_repository()),
            latest_verified=(
                OperationReceipt.model_validate_json(latest_verified.read_bytes())
                if latest_verified
                else None
            ),
        )
        output.write_bytes(
            canonical_json_bytes(
                {"eligible": allowed, "state": "eligible" if allowed else "superseded"}
            )
        )
    except (OSError, ValueError, yaml.YAMLError) as error:
        output.write_bytes(
            canonical_json_bytes({"eligible": False, "state": "failed", "error": str(error)})
        )
        _failed(error)


@app.command("retain-publication")
def retain_publication_command(publication: Annotated[Path, typer.Option()]) -> None:
    """Reconstruct missing durable evidence from the captured canonical publication."""
    from election_guide.release.evidence import record_evidence_failure, retain_evidence

    try:
        result = PublicationResult.model_validate_json(publication.read_bytes())
        request = result.published.candidate.declaration.publication_request
        if request is None:
            raise ValueError("publication evidence requires a reviewed request")
        receipt = OperationReceipt(
            phase="publication",
            state="published",
            producer=result.published.candidate.producer,
            publication=result,
            upload=None,
            verification_sha256=None,
            error=None,
        )
        ids = retain_evidence(receipt, issue_number=request.issue_number, reports={})
        typer.echo(json.dumps({"state": "published", "comment_ids": ids}))
    except (OSError, ValueError) as error:
        record_evidence_failure(publication.parent, error)
        _failed(error)


@app.command("record-upload")
def record_upload_command(
    publication: Annotated[Path, typer.Option()],
    github_deployment_id: Annotated[int, typer.Option(min=1)],
    deployment_url: Annotated[str, typer.Option()],
    uploaded_at: Annotated[str, typer.Option()],
    output: Annotated[Path, typer.Option()],
) -> None:
    """Record an existing upload; publication evidence must already be durable."""
    from election_guide.release.automation_models import UploadReceipt
    from election_guide.release.evidence import (
        current_producer,
        record_evidence_failure,
        require_publication_evidence,
    )

    try:
        result = PublicationResult.model_validate_json(publication.read_bytes())
        require_publication_evidence(result)
        source_sha = result.published.candidate.source_sha
        upload = UploadReceipt.model_validate_json(
            json.dumps(
                {
                    "publication": result.model_dump(mode="json"),
                    "producer": current_producer(source_sha).model_dump(mode="json"),
                    "github_deployment_id": github_deployment_id,
                    "deployment_url": deployment_url,
                    "uploaded_at": uploaded_at,
                    "source_sha": source_sha,
                }
            )
        )
        if upload.producer.repository != result.published.candidate.producer.repository:
            raise ValueError("upload workflow repository differs from publication")
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_bytes(canonical_json_bytes(upload.model_dump(mode="json")))
    except (OSError, ValueError) as error:
        record_evidence_failure(output.parent, error)
        _failed(error)


@app.command("finalize")
def finalize_command(
    upload: Annotated[Path, typer.Option()],
    output_dir: Annotated[Path, typer.Option()],
) -> None:
    """Retain the captured upload and verify production without deploying again."""
    from election_guide.release.automation_models import UploadReceipt
    from election_guide.release.evidence import (
        current_producer,
        finalize_deployment,
        record_evidence_failure,
        trusted_site,
    )

    try:
        receipt = UploadReceipt.model_validate_json(upload.read_bytes())
        result = finalize_deployment(
            receipt,
            site_manifest=trusted_site(receipt.publication),
            producer=current_producer(receipt.source_sha),
            output_dir=output_dir,
        )
        if result.state != "verified":
            raise ValueError(result.error or "production finalization incomplete")
    except (OSError, ValueError, yaml.YAMLError) as error:
        record_evidence_failure(output_dir, error)
        _failed(error)


@app.command("latest-production")
def latest_production_command(
    repository: Annotated[str, typer.Option()],
    output: Annotated[Path, typer.Option()],
) -> None:
    """Write a verified predecessor or JSON null only after a complete successful lookup."""
    from election_guide.release.evidence import latest_production_receipt

    try:
        result = latest_production_receipt(repository)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_bytes(canonical_json_bytes(result.model_dump(mode="json") if result else None))
    except (OSError, ValueError) as error:
        _failed(error)


@app.command("retain-operation")
def retain_operation_command(receipt: Annotated[Path, typer.Option()]) -> None:
    """Retain a skipped/failed operation; its reviewed request supplies the owning issue."""
    from election_guide.release.evidence import record_evidence_failure, retain_evidence

    try:
        result = OperationReceipt.model_validate_json(receipt.read_bytes())
        request = result.publication.published.candidate.declaration.publication_request
        if request is None:
            raise ValueError("operation evidence requires a reviewed request")
        reports: dict[str, bytes] = {}
        if result.verification_sha256 is not None:
            reports["production-wait.json"] = (receipt.parent / "production-wait.json").read_bytes()
        ids = retain_evidence(result, issue_number=request.issue_number, reports=reports)
        typer.echo(json.dumps({"state": result.state, "comment_ids": ids}))
    except (OSError, ValueError) as error:
        record_evidence_failure(receipt.parent, error)
        _failed(error)


@app.command("capture-source")
def capture_source_command(
    source_sha: Annotated[str, typer.Option()],
    output_dir: Annotated[Path, typer.Option()],
    base_sha: Annotated[str | None, typer.Option()] = None,
) -> None:
    """Capture one full checkout SHA and the exact admission base for every lane."""
    import os

    from election_guide.release.evidence import current_producer
    from election_guide.release.workflow import capture_source

    try:
        repository = _repository()
        source = capture_source(repository, source_sha)
        base = base_sha or _git(repository, "rev-parse", f"{source}^1")
        if re.fullmatch(r"[0-9a-f]{40}", base) is None:
            raise ValueError("admission base must be a full SHA")
        if os.environ.get("GITHUB_EVENT_NAME") != "pull_request":
            if os.environ.get("GITHUB_REF") != "refs/heads/main":
                raise ValueError("release delivery requires main")
            verify_merged_release_relation(repository, source_sha=source)
        output_dir.mkdir(parents=True, exist_ok=True)
        (output_dir / "source.json").write_bytes(
            canonical_json_bytes({"source_sha": source, "base_sha": base})
        )
        (output_dir / "producer.json").write_bytes(
            canonical_json_bytes(current_producer(source).model_dump(mode="json"))
        )
        if destination := os.environ.get("GITHUB_OUTPUT"):
            with Path(destination).open("a") as stream:
                stream.write(f"source_sha={source}\nbase_sha={base}\n")
    except (OSError, ValueError) as error:
        _failed(error)


@app.command("capture-artifact")
def capture_artifact_command(
    source_sha: Annotated[str, typer.Option()],
    artifact_id: Annotated[int, typer.Option(min=1)],
    name: Annotated[str, typer.Option()],
    digest: Annotated[str, typer.Option()],
    output: Annotated[Path, typer.Option()],
) -> None:
    """Bind action upload outputs to independently validated API metadata."""
    from election_guide.release.evidence import current_producer
    from election_guide.release.workflow import capture_artifact

    try:
        reference = capture_artifact(
            producer=current_producer(source_sha), artifact_id=artifact_id, name=name, digest=digest
        )
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_bytes(canonical_json_bytes(reference.model_dump(mode="json")))
    except (OSError, ValueError) as error:
        _failed(error)


@app.command("fetch-artifact")
def fetch_artifact_command(
    source_sha: Annotated[str, typer.Option()],
    artifact_id: Annotated[int, typer.Option(min=1)],
    name: Annotated[str, typer.Option()],
    digest: Annotated[str, typer.Option()],
    output_dir: Annotated[Path, typer.Option()],
    output_ref: Annotated[Path, typer.Option()],
) -> None:
    """Fetch an exact artifact ID, enforcing producer and wrapper byte identity."""
    from election_guide.hosting.promotion import download_actions_artifact
    from election_guide.release.evidence import current_producer
    from election_guide.release.workflow import capture_artifact

    try:
        reference = capture_artifact(
            producer=current_producer(source_sha), artifact_id=artifact_id, name=name, digest=digest
        )
        download_actions_artifact(reference, output_dir)
        output_ref.parent.mkdir(parents=True, exist_ok=True)
        output_ref.write_bytes(canonical_json_bytes(reference.model_dump(mode="json")))
    except (OSError, ValueError) as error:
        _failed(error)


@app.command("delivery-check")
def delivery_check_command(
    publication: Annotated[Path, typer.Option()], output_dir: Annotated[Path, typer.Option()]
) -> None:
    """Final serialized selection/switch check; skipped states remain durable evidence."""
    import os

    from election_guide.release.workflow import admit_upload, retain_delivery_failure

    try:
        result = PublicationResult.model_validate_json(publication.read_bytes())
        state = admit_upload(
            result,
            selected=_selected_main(_repository()),
            enabled=os.environ.get("CLOUDFLARE_PAGES_ENABLED") == "true",
            output_dir=output_dir,
        )
        if destination := os.environ.get("GITHUB_OUTPUT"):
            with Path(destination).open("a") as stream:
                stream.write(f"state={state}\n")
        typer.echo(state)
    except (OSError, ValueError, yaml.YAMLError) as error:
        retain_delivery_failure(publication, output_dir, error)
        _failed(error)


@app.command("create-deployment")
def create_deployment_command(
    publication: Annotated[Path, typer.Option()], output: Annotated[Path, typer.Option()]
) -> None:
    """Create one owned GitHub deployment envelope before the sole upload."""
    from election_guide.release.workflow import create_deployment, retain_delivery_failure

    try:
        identifier = create_deployment(
            PublicationResult.model_validate_json(publication.read_bytes())
        )
        output.write_bytes(canonical_json_bytes({"id": identifier}))
    except (OSError, ValueError) as error:
        retain_delivery_failure(publication, output.parent, error)
        _failed(error)


@app.command("upload")
def upload_command(
    publication: Annotated[Path, typer.Option()],
    deployment: Annotated[Path, typer.Option()],
    site_dir: Annotated[Path, typer.Option()],
    output_dir: Annotated[Path, typer.Option()],
) -> None:
    """Run pinned Wrangler once, preserving its output and owned unique URL."""
    from election_guide.release.workflow import perform_upload, retain_delivery_failure

    try:
        perform_upload(
            PublicationResult.model_validate_json(publication.read_bytes()),
            deployment_id=json.loads(deployment.read_bytes())["id"],
            site_dir=site_dir,
            output_dir=output_dir,
        )
    except (OSError, ValueError) as error:
        retain_delivery_failure(publication, output_dir, error)
        _failed(error)


@app.command("deployment-status")
def deployment_status_command(upload: Annotated[Path, typer.Option()]) -> None:
    """Mark success only after exact-upload durable verified finalization."""
    from election_guide.release.automation_models import UploadReceipt
    from election_guide.release.evidence import load_verified_receipts
    from election_guide.release.workflow import write_deployment_status

    try:
        receipt = UploadReceipt.model_validate_json(upload.read_bytes())
        candidate = receipt.publication.published.candidate
        request = candidate.declaration.publication_request
        if request is None:
            raise ValueError("missing reviewed request")
        records = load_verified_receipts(
            repository=receipt.producer.repository,
            issue_number=request.issue_number,
            release_version=candidate.declaration.release_version,
            source_sha=receipt.source_sha,
        )
        if not any(r.state == "verified" and r.upload == receipt for r in records):
            raise ValueError("deployment success requires durable verified finalization")
        write_deployment_status(
            receipt.publication,
            receipt.github_deployment_id,
            state="success",
            url=receipt.deployment_url,
        )
    except (OSError, ValueError) as error:
        _failed(error)


@app.command("recover-upload")
def recover_upload_command(
    repository: Annotated[str, typer.Option()],
    issue: Annotated[int, typer.Option(min=1)],
    release_version: Annotated[str, typer.Option()],
    source_sha: Annotated[str, typer.Option()],
    run_id: Annotated[int, typer.Option(min=1)],
    run_attempt: Annotated[int, typer.Option(min=1)],
    output: Annotated[Path, typer.Option()],
) -> None:
    """Load original immutable upload evidence; never rebuild or upload."""
    from election_guide.release.workflow import recover_upload

    try:
        receipt = recover_upload(
            repository=repository,
            issue=issue,
            release_version=release_version,
            source_sha=source_sha,
            run_id=run_id,
            run_attempt=run_attempt,
        )
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_bytes(canonical_json_bytes(receipt.model_dump(mode="json")))
    except (OSError, ValueError) as error:
        _failed(error)
