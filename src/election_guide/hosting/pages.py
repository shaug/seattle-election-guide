"""Stage an audited release bundle for Cloudflare Pages."""

from __future__ import annotations

import hashlib
import os
import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path

from election_guide.release.models import ReleaseManifest, ReleaseStatus
from election_guide.serialization import canonical_json_bytes, read_json

PAGES_HEADERS = """/*
  Cache-Control: public, max-age=0, must-revalidate
  Referrer-Policy: strict-origin-when-cross-origin
  X-Content-Type-Options: nosniff
  X-Frame-Options: DENY
  Permissions-Policy: camera=(), geolocation=(), microphone=()
"""

PAGES_WORKER = """const CANONICAL_HOST = "seattleelections.guide";
const LEGACY_HOSTS = new Set([
  "seattle-elections.dobravoda.dev",
  "seattle-elections.guide",
]);

export default {
  async fetch(request, env) {
    const url = new URL(request.url);

    if (LEGACY_HOSTS.has(url.hostname)) {
      url.protocol = "https:";
      url.hostname = CANONICAL_HOST;
      url.port = "";
      return Response.redirect(url.toString(), 301);
    }

    return env.ASSETS.fetch(request);
  },
};
"""


@dataclass(frozen=True)
class StagedPagesSite:
    """Files prepared for one immutable Pages deployment."""

    output_dir: Path
    release_version: str
    git_commit: str
    source_panel_id: str
    source_panel_hash: str
    html_path: Path
    pdf_paths: tuple[Path, ...]


def stage_pages_site(
    bundle_dir: Path,
    output_dir: Path,
    *,
    expected_git_commit: str | None = None,
) -> StagedPagesSite:
    """Verify a release bundle and atomically stage only its public guide assets."""
    bundle_dir = bundle_dir.resolve()
    output_dir = output_dir.resolve()
    _validate_distinct_paths(bundle_dir, output_dir)

    status = ReleaseStatus.model_validate(read_json(bundle_dir / "release-status.json"))
    if expected_git_commit is not None and status.git_commit != expected_git_commit:
        raise ValueError(
            "release bundle was built from a different Git commit: "
            f"expected {expected_git_commit}, found {status.git_commit}"
        )

    manifest = ReleaseManifest.model_validate(read_json(bundle_dir / "release-manifest.json"))
    if manifest.release_version != status.release_version:
        raise ValueError("release manifest and release status versions differ")
    if manifest.generated_at != status.generated_at:
        raise ValueError("release manifest and release status timestamps differ")
    if (
        manifest.source_panel_id != status.source_panel_id
        or manifest.source_panel_hash != status.source_panel_hash
    ):
        raise ValueError("release manifest and release status source panels differ")
    artifact_hashes = manifest.artifact_hashes
    expected_artifacts = set(status.included_artifacts) - {"release-manifest.json"}
    if set(artifact_hashes) != expected_artifacts:
        raise ValueError("release manifest does not cover the complete release artifact set")
    _verify_artifact_hashes(bundle_dir, artifact_hashes)

    html_source = bundle_dir / status.guide_html_artifact
    pdf_sources = [bundle_dir / status.guide_pdf_artifact]
    if status.detailed_guide_pdf_artifact is not None:
        pdf_sources.append(bundle_dir / status.detailed_guide_pdf_artifact)

    output_dir.parent.mkdir(parents=True, exist_ok=True)
    stage = Path(tempfile.mkdtemp(prefix=f".{output_dir.name}.staging-", dir=output_dir.parent))
    try:
        html_path = stage / "index.html"
        shutil.copy2(html_source, html_path)
        staged_pdfs: list[Path] = []
        for source in pdf_sources:
            target = stage / source.name
            shutil.copy2(source, target)
            staged_pdfs.append(target)
        shutil.copy2(bundle_dir / "release-status.json", stage / "release-status.json")
        (stage / "_headers").write_text(PAGES_HEADERS, encoding="utf-8")
        (stage / "_worker.js").write_text(PAGES_WORKER, encoding="utf-8")
        deployment_manifest = {
            "schema_version": "1.0",
            "release_version": status.release_version,
            "git_commit": status.git_commit,
            "source_panel_id": status.source_panel_id,
            "source_panel_hash": status.source_panel_hash,
            "data_as_of": status.data_as_of.isoformat(),
            "generated_at": status.generated_at.isoformat(),
            "assets": _artifact_hashes(stage),
        }
        (stage / "deployment-manifest.json").write_bytes(canonical_json_bytes(deployment_manifest))
        _replace_output(stage, output_dir)
        stage = Path()
    finally:
        if stage != Path() and stage.exists():
            shutil.rmtree(stage, ignore_errors=True)

    return StagedPagesSite(
        output_dir=output_dir,
        release_version=status.release_version,
        git_commit=status.git_commit,
        source_panel_id=status.source_panel_id,
        source_panel_hash=status.source_panel_hash,
        html_path=output_dir / "index.html",
        pdf_paths=tuple(output_dir / source.name for source in pdf_sources),
    )


def _verify_artifact_hashes(bundle_dir: Path, artifact_hashes: dict[str, str]) -> None:
    for relative, expected in sorted(artifact_hashes.items()):
        path = bundle_dir / relative
        if not path.is_file():
            raise ValueError(f"release artifact is missing: {relative}")
        actual = hashlib.sha256(path.read_bytes()).hexdigest()
        if actual != expected:
            raise ValueError(f"release artifact hash mismatch: {relative}")


def _artifact_hashes(root: Path) -> dict[str, str]:
    return {
        path.relative_to(root).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


def _validate_distinct_paths(bundle_dir: Path, output_dir: Path) -> None:
    if not bundle_dir.is_dir():
        raise ValueError(f"release bundle directory does not exist: {bundle_dir}")
    if (
        bundle_dir == output_dir
        or bundle_dir in output_dir.parents
        or output_dir in bundle_dir.parents
    ):
        raise ValueError("release bundle and Pages output directories must not overlap")


def _replace_output(stage: Path, output_dir: Path) -> None:
    backup: Path | None = None
    if output_dir.exists():
        backup = output_dir.with_name(f".{output_dir.name}.backup-{os.getpid()}")
        if backup.exists():
            raise ValueError(f"Pages output backup path already exists: {backup}")
        os.replace(output_dir, backup)
    try:
        os.replace(stage, output_dir)
    except OSError:
        if backup is not None and backup.exists() and not output_dir.exists():
            os.replace(backup, output_dir)
        raise
    if backup is not None:
        shutil.rmtree(backup, ignore_errors=True)
