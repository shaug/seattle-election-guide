"""Build, audit, and package a versioned public release."""

from __future__ import annotations

import hashlib
import os
import re
import shutil
import subprocess
import tempfile
import zipfile
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from election_guide.evidence.models import CapturedManifest
from election_guide.normalization.models import CanonicalDataset
from election_guide.publication import build_publication_bundle, write_publication_bundle
from election_guide.release.compiler import read_release_ledger, verify_release_compilation
from election_guide.release.models import (
    ARCHIVE_ROOT_DIR,
    RaceCoverageStatus,
    ReleaseManifest,
    ReleaseStatus,
    SourceAccessStatus,
    release_archive_name,
)
from election_guide.rendering import build_rendered_guide
from election_guide.results.loader import load_rendering_results
from election_guide.scoring import ConsensusReport, read_scoring_configuration, score_dataset
from election_guide.serialization import canonical_json_bytes
from election_guide.sources.registry import source_registry_hash


@dataclass(frozen=True)
class ReleaseResult:
    output_dir: Path
    bundle_dir: Path
    archive_path: Path
    status: ReleaseStatus


def build_release(
    *,
    ledger_path: Path,
    inventory_path: Path,
    registry_path: Path,
    dataset_path: Path,
    scoring_config_path: Path,
    rendering_config_path: Path,
    snapshot_root: Path,
    manifest_dir: Path,
    output_dir: Path,
    release_version: str,
    generated_at: datetime,
    git_commit: str,
    chrome_path: Path | None = None,
    results_dir: Path = Path("data/results"),
    repository_root: Path = Path("."),
) -> ReleaseResult:
    """Run the complete publication pipeline and atomically publish one release directory.

    `results_dir` is where a certified or amended post-election results file
    would live, if one has been committed for this election (issue #283). It
    is loaded and validated here -- the release build is the one production
    pipeline that produces the published `publication_view_model.json` -- so
    the rendering hook actually reaches a real release rather than only ever
    being exercised directly in tests. With no committed file, this is a
    silent no-op and the release is unchanged from before this hook existed.
    `repository_root` resolves that file's own evidence-manifest references
    (`data/manifests/evidence/...`) and defaults to the current working
    directory, matching every other repo-relative default in this pipeline.
    """
    if generated_at.tzinfo is None or generated_at.utcoffset() is None:
        raise ValueError("release generated_at must include a UTC offset")
    if not re.fullmatch(r"[0-9a-f]{40}", git_commit):
        raise ValueError("release git_commit must be a full lowercase Git commit ID")
    _verify_checkout_identity(git_commit)
    dataset = verify_release_compilation(
        ledger_path,
        inventory_path,
        registry_path,
        dataset_path,
        snapshot_root,
        manifest_dir,
    )
    ledger = read_release_ledger(ledger_path)
    if ledger.election_id != dataset.inventory.election.id:
        raise ValueError("release ledger and canonical dataset target different elections")
    if generated_at < ledger.data_as_of:
        raise ValueError("release build time cannot predate its audited data")

    scoring_config = read_scoring_configuration(scoring_config_path)
    consensus = score_dataset(dataset, scoring_config, computed_at=generated_at)
    results = load_rendering_results(
        dataset.inventory.election.id,
        dataset.inventory,
        results_dir=results_dir,
        repository_root=repository_root,
    )

    output_dir.parent.mkdir(parents=True, exist_ok=True)
    stage = Path(tempfile.mkdtemp(prefix=f".{output_dir.name}.staging-", dir=output_dir.parent))
    stage_bundle = stage / "bundle"
    data_dir = stage_bundle / "data"
    render_dir = stage / "rendered"
    try:
        publication = build_publication_bundle(
            dataset,
            consensus,
            git_commit=git_commit,
            snapshot_root=snapshot_root,
            data_as_of=ledger.data_as_of,
            results=results,
        )
        write_publication_bundle(publication, data_dir)
        (data_dir / "canonical-dataset.json").write_bytes(
            canonical_json_bytes(dataset.model_dump(mode="json"))
        )
        rendered = build_rendered_guide(
            data_dir / "publication_view_model.json",
            rendering_config_path,
            render_dir,
            chrome_path=chrome_path,
        )

        guide_dir = stage_bundle / "guide"
        validation_dir = stage_bundle / "validation"
        guide_dir.mkdir(parents=True)
        validation_dir.mkdir(parents=True)
        shutil.copy2(rendered.html_path, guide_dir / rendered.html_path.name)
        rendering_validation_dir = validation_dir / "rendering"
        for rendered_artifact in sorted({rendered.validation_path, *rendered.screenshots}):
            relative = rendered_artifact.relative_to(render_dir)
            target = rendering_validation_dir / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(rendered_artifact, target)

        included_artifacts = sorted(
            [
                path.relative_to(stage_bundle).as_posix()
                for path in stage_bundle.rglob("*")
                if path.is_file()
            ]
            + ["RELEASE_NOTES.md", "release-manifest.json", "release-status.json"]
        )
        status = _release_status(
            dataset=dataset,
            consensus=consensus,
            ledger_source_count=len(ledger.sources),
            release_version=release_version,
            data_as_of=ledger.data_as_of,
            generated_at=generated_at,
            git_commit=git_commit,
            publication_passed=publication.validation_report.passed,
            rendering_passed=rendered.validation_report.passed,
            guide_html_artifact=(Path("guide") / rendered.html_path.name).as_posix(),
            included_artifacts=included_artifacts,
        )
        (stage_bundle / "release-status.json").write_bytes(
            canonical_json_bytes(status.model_dump(mode="json"))
        )
        (stage_bundle / "RELEASE_NOTES.md").write_text(
            _release_notes(status, dataset.inventory.election.name),
            encoding="utf-8",
        )
        manifest = ReleaseManifest(
            release_version=release_version,
            source_panel_id=dataset.source_registry.id,
            source_panel_hash=source_registry_hash(dataset.source_registry),
            generated_at=generated_at,
            artifact_hashes=_artifact_hashes(stage_bundle),
        )
        (stage_bundle / "release-manifest.json").write_bytes(
            canonical_json_bytes(manifest.model_dump(mode="json"))
        )

        archive_name = release_archive_name(release_version)
        archive_path = stage / archive_name
        _write_deterministic_zip(stage_bundle, archive_path, generated_at)
        _set_public_permissions(stage)
        _replace_output(stage, output_dir)
        stage = Path()
        return ReleaseResult(
            output_dir=output_dir,
            bundle_dir=output_dir / "bundle",
            archive_path=output_dir / archive_name,
            status=status,
        )
    finally:
        if stage != Path() and stage.exists():
            shutil.rmtree(stage, ignore_errors=True)


def _release_status(
    *,
    dataset: CanonicalDataset,
    consensus: ConsensusReport,
    ledger_source_count: int,
    release_version: str,
    data_as_of: datetime,
    generated_at: datetime,
    git_commit: str,
    publication_passed: bool,
    rendering_passed: bool,
    guide_html_artifact: str,
    included_artifacts: list[str],
) -> ReleaseStatus:
    unresolved_ids = {item.id for item in dataset.review_items} - {
        decision.review_item_id for decision in dataset.review_decisions
    }
    unresolved = [item for item in dataset.review_items if item.id in unresolved_ids]
    access_failures = [
        SourceAccessStatus(
            source_id=source.id,
            status=source.discovery.status,
            requested_url=source.discovery.requested_url,
            note=source.discovery.notes,
        )
        for source in dataset.source_registry.sources
        if source.panel_role != "excluded" and source.discovery.status != "published"
    ]
    incomplete = [
        RaceCoverageStatus(
            race_id=race.race_id,
            explicit_endorsement_count=race.explicit_endorsement_count,
            eligible_source_count=race.eligible_source_count,
            missing_source_count=race.missing_source_count,
            warning_codes=[warning.code for warning in race.warnings],
        )
        for race in consensus.races
        if race.missing_source_count or race.grade == "Insufficient"
    ]
    restricted_count = sum(
        isinstance(capture, CapturedManifest) and capture.redistribution == "restricted"
        for capture in dataset.captures
    )
    warnings: list[str] = []
    if access_failures:
        warnings.append(f"{len(access_failures)} active sources had access or discovery failures.")
    if incomplete:
        warnings.append(f"{len(incomplete)} displayed races have incomplete source coverage.")
    if ledger_source_count < sum(
        source.panel_role != "excluded" and source.discovery.status == "published"
        for source in dataset.source_registry.sources
    ):
        warnings.append("Some published source pages have not yet been transcribed into decisions.")
    return ReleaseStatus(
        release_version=release_version,
        election_id=dataset.inventory.election.id,
        source_panel_id=dataset.source_registry.id,
        source_panel_hash=source_registry_hash(dataset.source_registry),
        data_as_of=data_as_of,
        generated_at=generated_at,
        git_commit=git_commit,
        source_count=sum(
            source.panel_role != "excluded" for source in dataset.source_registry.sources
        ),
        captured_source_count=ledger_source_count,
        displayed_endorsement_count=len(dataset.endorsements),
        unresolved_review_count=len(unresolved),
        unresolved_high_severity_count=sum(item.severity == "high" for item in unresolved),
        restricted_capture_count=restricted_count,
        source_access_failures=access_failures,
        incomplete_races=incomplete,
        validation_reports={
            "publication": publication_passed,
            "rendering": rendering_passed,
        },
        guide_html_artifact=guide_html_artifact,
        included_artifacts=included_artifacts,
        warnings=warnings,
    )


def _release_notes(status: ReleaseStatus, election_name: str) -> str:
    access_lines = (
        "\n".join(
            f"- `{item.source_id}`: {item.status} — {item.note}"
            for item in status.source_access_failures
        )
        or "- None."
    )
    warning_lines = "\n".join(f"- {warning}" for warning in status.warnings) or "- None."
    return f"""# {election_name} endorsement consensus guide

Release `{status.release_version}` packages the public HTML guide with its canonical JSON, CSV,
review, validation, provenance, build, and release manifests.

## Audit identity

- Data as of: {status.data_as_of.isoformat()}
- Built at: {status.generated_at.isoformat()}
- Code revision: `{status.git_commit}`
- Source panel: `{status.source_panel_id}`
- Source panel hash: `{status.source_panel_hash}`
- Reviewed source extracts: {status.captured_source_count} of {status.source_count} active sources
- Displayed source decisions: {status.displayed_endorsement_count}
- Unresolved review items: {status.unresolved_review_count}

## Source access and discovery failures

{access_lines}

## Known limitations

{warning_lines}

Missing coverage is not counted as opposition. The guide aggregates selected organizations'
endorsements; it is not an official voter pamphlet or independent candidate evaluation. Full
third-party page captures are excluded. Every included decision is backed by a permitted,
content-addressed structured extract and a public official URL.
"""


def _artifact_hashes(bundle_dir: Path) -> dict[str, str]:
    return {
        path.relative_to(bundle_dir).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(bundle_dir.rglob("*"))
        if path.is_file() and path.name != "release-manifest.json"
    }


def _write_deterministic_zip(bundle_dir: Path, output: Path, generated_at: datetime) -> None:
    timestamp = generated_at.timetuple()[:6]
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for path in sorted(bundle_dir.rglob("*")):
            if not path.is_file():
                continue
            relative = Path(ARCHIVE_ROOT_DIR) / path.relative_to(bundle_dir)
            info = zipfile.ZipInfo(relative.as_posix(), date_time=timestamp)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o100644 << 16
            info.create_system = 3
            archive.writestr(
                info,
                path.read_bytes(),
                compress_type=zipfile.ZIP_DEFLATED,
                compresslevel=9,
            )


def _replace_output(stage: Path, destination: Path) -> None:
    backup = destination.with_name(f".{destination.name}.previous")
    if backup.exists():
        shutil.rmtree(backup)
    if destination.exists():
        os.replace(destination, backup)
    try:
        os.replace(stage, destination)
    except OSError:
        if backup.exists():
            os.replace(backup, destination)
        raise
    shutil.rmtree(backup, ignore_errors=True)


def _verify_checkout_identity(git_commit: str) -> None:
    try:
        head = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
        status = subprocess.run(
            ["git", "status", "--porcelain", "--untracked-files=normal"],
            check=True,
            capture_output=True,
            text=True,
        ).stdout
    except subprocess.CalledProcessError as error:
        raise ValueError("release build requires a Git checkout") from error
    if git_commit != head:
        raise ValueError(f"release git_commit {git_commit!r} does not match checkout HEAD {head!r}")
    if status:
        raise ValueError("publishable release build requires a clean Git checkout")


def _set_public_permissions(root: Path) -> None:
    for path in sorted(root.rglob("*")):
        path.chmod(0o755 if path.is_dir() else 0o644)
    root.chmod(0o755)
