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

from election_guide.github_cli import run_gh
from election_guide.hosting.models import SiteManifest
from election_guide.hosting.releases import (
    published_release_tags,
    verify_declared_releases_published,
)
from election_guide.release.automation_models import (
    ArtifactRef,
    CandidateRecord,
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
)
from election_guide.release.history import generate_changelog_index
from election_guide.release.publication import bind_publication, publish_candidate
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
        payload: Any = json.loads(
            run_gh(
                [
                    "gh",
                    "api",
                    f"repos/{{owner}}/{{repo}}/{endpoint}?per_page=100",
                    "--paginate",
                    "--slurp",
                ],
                f"could not read complete remote {endpoint}",
            )
        )
        if not isinstance(payload, list) or not payload:
            raise ValueError(f"incomplete remote {endpoint} query")
        for page in cast(list[Any], payload):
            if not isinstance(page, list):
                raise ValueError(f"incomplete remote {endpoint} query")
            for entry in cast(list[Any], page):
                if not isinstance(entry, dict):
                    raise ValueError(f"incomplete remote {endpoint} query")
                name = cast(dict[str, Any], entry).get(key)
                if not isinstance(name, str) or not name:
                    raise ValueError(f"incomplete remote {endpoint} query")
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


def _remote_main(repository: Path, path: Path) -> tuple[SiteManifest, str]:
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
    previous_sha = _remote_commit(f"git/ref/tags/{selected.release_version}", allow_tag=True)
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
        main, previous_sha = _remote_main(repository, relative)
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
            requested = validate_release_request(current, base=base, changed_paths=paths)
            if requested:
                request = current.current.publication_request
                assert request is not None
                if request.previous_release_sha != _published_sha(repository, base):
                    raise ValueError("publication request previous release boundary is stale")
                require_ancestor(request.previous_release_sha, repository=repository)
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
