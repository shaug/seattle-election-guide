"""Build and bind a complete release candidate to one exact source revision."""

from __future__ import annotations

import hashlib
import re
import subprocess
import tempfile
import zipfile
import zlib
from contextlib import chdir
from datetime import datetime
from pathlib import Path, PurePosixPath

from election_guide.hosting.pages import (
    bundle_hash,
    read_site_manifest,
    stage_pages_site,
    verify_staged_pages_site,
)
from election_guide.release.automation_models import (
    ArtifactRef,
    CandidateRecord,
    FileDigest,
    Producer,
)
from election_guide.release.builder import build_release
from election_guide.release.comparison import (
    compare_release_bundles,
    verify_release_bundle_artifacts,
)
from election_guide.release.declaration import ResolvedRelease, hash_release_inputs, resolve_release
from election_guide.release.history import generate_software_history
from election_guide.release.models import ARCHIVE_ROOT_DIR
from election_guide.serialization import canonical_json_bytes

SITE_MANIFEST = Path("config/hosting/site.yaml")


def _git(repository: Path, *arguments: str) -> str:
    result = subprocess.run(
        ["git", *arguments], cwd=repository, capture_output=True, text=True, check=False
    )
    if result.returncode:
        raise ValueError(f"candidate Git identity unavailable: {result.stderr.strip()}")
    return result.stdout.strip()


def _require_checkout(repository: Path, source_sha: str) -> None:
    if re.fullmatch(r"[0-9a-f]{40}", source_sha) is None:
        raise ValueError("candidate requires a full lowercase source SHA")
    if _git(repository, "rev-parse", "HEAD") != source_sha:
        raise ValueError("candidate source SHA differs from checkout HEAD")
    if _git(repository, "status", "--porcelain", "--untracked-files=normal"):
        raise ValueError("candidate requires a clean Git checkout")


def _digest(path: Path) -> FileDigest:
    content = path.read_bytes()
    return FileDigest(sha256=hashlib.sha256(content).hexdigest(), size=len(content))


def _require_declaration(resolved: ResolvedRelease, repository: Path) -> None:
    if read_site_manifest(repository / SITE_MANIFEST) != resolved.site:
        raise ValueError("resolved site declaration differs from repository bytes")
    request = resolved.current.publication_request
    if request is not None and request.inputs != hash_release_inputs(resolved.inputs):
        raise ValueError("candidate reviewed input hashes differ from publication request")


def stage_current_candidate(
    resolved: ResolvedRelease,
    *,
    repository: Path,
    bundle_dir: Path,
    output_dir: Path,
    source_sha: str,
) -> None:
    """Stage current source plus pinned published archives and independently verify it."""
    _require_declaration(resolved, repository)
    stage_pages_site(
        repository / SITE_MANIFEST,
        {resolved.current.bundle_id: bundle_dir},
        output_dir,
        expected_current_git_commit=source_sha,
        released_bundle_dir=output_dir.parent / "released-bundles",
        calendar_path=repository / "config/calendar/elections.yaml",
    )
    verify_staged_pages_site(
        output_dir, repository / SITE_MANIFEST, expected_current_git_commit=source_sha
    )


def build_current_candidate(
    resolved: ResolvedRelease, *, repository: Path, output_dir: Path, source_sha: str
) -> Path:
    repository, output_dir = repository.resolve(), output_dir.resolve()
    _require_checkout(repository, source_sha)
    _require_declaration(resolved, repository)
    generated_at = datetime.fromisoformat(
        _git(repository, "show", "-s", "--format=%cI", source_sha)
    )
    request = resolved.current.publication_request
    history = (
        generate_software_history(
            repository,
            previous_release_sha=request.previous_release_sha,
            source_sha=source_sha,
            release_version=resolved.current.release_version,
            generated_at=generated_at,
        )
        if request is not None
        else None
    )
    inputs = resolved.inputs
    with chdir(repository):
        for suffix in ("a", "b"):
            build_release(
                ledger_path=inputs.ledger,
                inventory_path=inputs.inventory,
                registry_path=inputs.registry,
                dataset_path=inputs.dataset,
                snapshot_root=inputs.snapshots,
                manifest_dir=inputs.manifests,
                scoring_config_path=repository / "config/scoring/default.yaml",
                rendering_config_path=repository / "config/rendering/guide.yaml",
                output_dir=output_dir / f"reproducibility-{suffix}",
                release_version=resolved.current.release_version,
                generated_at=generated_at,
                git_commit=source_sha,
                repository_root=repository,
                software_history=history,
            )
    first = output_dir / "reproducibility-a"
    compare_release_bundles(first / "bundle", output_dir / "reproducibility-b/bundle")
    archive = first / resolved.archive_name
    with tempfile.TemporaryDirectory(prefix="candidate-archive-") as temporary:
        _verified_archive(archive, Path(temporary))
        if bundle_hash(Path(temporary)) != bundle_hash(first / "bundle"):
            raise ValueError("candidate ZIP differs from selected build A bundle")
    stage_current_candidate(
        resolved,
        repository=repository,
        bundle_dir=first / "bundle",
        output_dir=output_dir / "cloudflare-site",
        source_sha=source_sha,
    )
    _require_checkout(repository, source_sha)
    return archive


def verify_artifact_ref(expected: ArtifactRef, observed: ArtifactRef) -> None:
    """Verify all captured upload identity fields after every artifact download."""
    if expected != observed:
        raise ValueError("artifact identity differs from captured producing run and attempt")


def _verified_archive(archive_path: Path, destination: Path) -> None:
    prefix = f"{ARCHIVE_ROOT_DIR}/"
    try:
        with zipfile.ZipFile(archive_path) as archive:
            members = archive.namelist()
            if len(members) != len(set(members)):
                raise ValueError("candidate ZIP contains duplicate members")
            for name in members:
                relative = name.removeprefix(prefix)
                path = PurePosixPath(relative)
                if (
                    not name.startswith(prefix)
                    or not relative
                    or path.is_absolute()
                    or ".." in path.parts
                    or "\\" in name
                    or path.as_posix() != relative
                    or name.endswith("/")
                ):
                    raise ValueError("candidate ZIP contains an invalid member")
                target = destination / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(archive.read(name))
            verified = verify_release_bundle_artifacts(destination)
            expected = {prefix + relative for relative in verified.status.included_artifacts}
            if set(members) != expected:
                raise ValueError(
                    "candidate ZIP member set differs from declared included artifacts"
                )
    except (zipfile.BadZipFile, zlib.error, RuntimeError, NotImplementedError) as error:
        raise ValueError("candidate ZIP is unreadable") from error


def record_candidate(
    resolved: ResolvedRelease,
    *,
    repository: Path,
    output_dir: Path,
    producer: Producer,
    release_artifact: ArtifactRef,
    site_artifact: ArtifactRef,
    recovered_from: Producer | None = None,
) -> CandidateRecord:
    _require_checkout(repository, producer.source_sha)
    _require_declaration(resolved, repository)
    archive = output_dir / "reproducibility-a" / resolved.archive_name
    with tempfile.TemporaryDirectory(prefix="candidate-record-") as temporary:
        bundle = Path(temporary)
        _verified_archive(archive, bundle)
        verified = verify_release_bundle_artifacts(bundle)
        record = CandidateRecord(
            declaration=resolved.current,
            site_manifest_sha256=_digest(repository / SITE_MANIFEST).sha256,
            source_sha=producer.source_sha,
            generated_at=verified.status.generated_at,
            inputs=hash_release_inputs(resolved.inputs),
            producer=producer,
            archive=_digest(archive),
            bundle_sha256=bundle_hash(bundle),
            deployment_manifest_sha256=_digest(
                output_dir / "cloudflare-site/deployment-manifest.json"
            ).sha256,
            release_artifact=release_artifact,
            site_artifact=site_artifact,
            recovered_from=recovered_from,
        )
    verify_candidate(
        record, repository=repository, archive_path=archive, site_dir=output_dir / "cloudflare-site"
    )
    (output_dir / "candidate.json").write_bytes(
        canonical_json_bytes(record.model_dump(mode="json"))
    )
    return record


def verify_candidate(
    record: CandidateRecord, *, repository: Path, archive_path: Path, site_dir: Path
) -> None:
    # Revalidate even caller-created model_copy instances at this trust boundary.
    record = CandidateRecord.model_validate(record.model_dump())
    resolved = resolve_release(SITE_MANIFEST, repository=repository)
    _require_declaration(resolved, repository)
    if record.declaration != resolved.current:
        raise ValueError("candidate declaration differs from selected site declaration")
    if record.site_manifest_sha256 != _digest(repository / SITE_MANIFEST).sha256:
        raise ValueError("candidate site manifest bytes differ")
    if record.inputs != hash_release_inputs(resolved.inputs):
        raise ValueError("candidate reviewed input hashes differ")
    if record.archive != _digest(archive_path):
        raise ValueError("candidate release archive bytes differ")
    with tempfile.TemporaryDirectory(prefix="candidate-verify-") as temporary:
        bundle = Path(temporary)
        _verified_archive(archive_path, bundle)
        verified = verify_release_bundle_artifacts(bundle)
        status = verified.status
        if status.git_commit != record.source_sha or status.generated_at != record.generated_at:
            raise ValueError("candidate archive source or timestamp differs")
        if bundle_hash(bundle) != record.bundle_sha256:
            raise ValueError("candidate whole-bundle hash differs")
        deployment = verify_staged_pages_site(
            site_dir, repository / SITE_MANIFEST, expected_current_git_commit=record.source_sha
        )
        if (
            deployment.elections[0].release_manifest_sha256
            != _digest(bundle / "release-manifest.json").sha256
        ):
            raise ValueError("candidate staged release manifest differs from archive")
    if record.deployment_manifest_sha256 != _digest(site_dir / "deployment-manifest.json").sha256:
        raise ValueError("candidate deployment manifest bytes differ")
