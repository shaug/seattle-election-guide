"""Verify release content across the intentional post-tag commit boundary."""

from __future__ import annotations

import copy
import hashlib
import re
import stat
import subprocess
import tempfile
import zlib
from contextlib import ExitStack
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any, cast
from zipfile import BadZipFile, ZipFile, is_zipfile

from election_guide.release.comparison import (
    VerifiedReleaseBundle,
    verify_release_bundle_artifacts,
)
from election_guide.release.models import ARCHIVE_ROOT_DIR
from election_guide.serialization import canonical_json_bytes, read_json

_FULL_SHA = re.compile(r"[0-9a-f]{40}")
_NORMALIZED_COMMIT = "<commit-bound-git-sha>"
_NORMALIZED_TIMESTAMP = "<commit-bound-generated-at>"
_NORMALIZED_DATE = "<commit-bound-generated-date>"


@dataclass(frozen=True)
class ReleaseLineageReport:
    """Deterministic, attachment-ready result of one lineage comparison."""

    release_candidate_sha: str
    production_candidate_sha: str
    result: str
    identities: dict[str, Any]
    normalized: tuple[dict[str, Any], ...]
    screenshots: dict[str, Any]
    compared_artifacts: tuple[str, ...]
    errors: tuple[str, ...]

    def model_dump(self) -> dict[str, Any]:
        return {
            "schema_version": "1.0",
            "release_candidate_sha": self.release_candidate_sha,
            "production_candidate_sha": self.production_candidate_sha,
            "result": self.result,
            "identities": self.identities,
            "normalized": list(self.normalized),
            "screenshots": self.screenshots,
            "compared_artifacts": list(self.compared_artifacts),
            "errors": list(self.errors),
        }


@dataclass(frozen=True)
class _LoadedBundle:
    verified: VerifiedReleaseBundle
    raw: dict[str, bytes]
    json: dict[str, dict[str, Any]]
    generated_at: str


def verify_release_lineage(
    release_source: Path,
    production_source: Path,
    release_candidate_sha: str,
    production_candidate_sha: str,
    *,
    repository: Path | None = None,
) -> ReleaseLineageReport:
    """Compare two independently verified bundles across a strict Git lineage."""
    errors: list[str] = []
    identities: dict[str, Any] = {}
    normalized_report: tuple[dict[str, Any], ...] = ()
    screenshots: dict[str, Any] = {}
    compared: tuple[str, ...] = ()
    try:
        _verify_candidate_shas(
            release_candidate_sha,
            production_candidate_sha,
            repository=(repository or Path.cwd()),
        )
        with ExitStack() as stack:
            release_dir = _materialize_bundle(release_source, stack)
            production_dir = _materialize_bundle(production_source, stack)
            release = _load_bundle(release_dir, release_candidate_sha)
            production = _load_bundle(production_dir, production_candidate_sha)
            release_identity = _release_identity(release)
            production_identity = _release_identity(production)
            if release_identity != production_identity:
                errors.extend(_mapping_differences(release_identity, production_identity))
                identities = {
                    "release": release_identity,
                    "production": production_identity,
                }
            else:
                identities = release_identity

            release_normalized, release_paths = _normalized_artifacts(
                release, release_candidate_sha
            )
            production_normalized, production_paths = _normalized_artifacts(
                production, production_candidate_sha
            )
            if release_paths != production_paths:
                errors.append("documented normalization paths differ between bundles")
            normalized_report = tuple(
                {"artifact": artifact, "paths": list(paths)}
                for artifact, paths in sorted(release_paths.items())
            )

            release_hashed = set(release.verified.manifest.artifact_hashes)
            production_hashed = set(production.verified.manifest.artifact_hashes)
            if release_hashed != production_hashed:
                errors.append(
                    "deterministic artifact sets differ: "
                    f"release-only={sorted(release_hashed - production_hashed)}, "
                    f"production-only={sorted(production_hashed - release_hashed)}"
                )
            deterministic_paths = sorted(release_hashed | production_hashed)
            for relative in deterministic_paths:
                if release_normalized.get(relative) != production_normalized.get(relative):
                    errors.append(f"release content differs: {relative}")
            if release_normalized.get("release-manifest.json") != production_normalized.get(
                "release-manifest.json"
            ):
                errors.append("release content differs: release-manifest.json")
            compared = tuple([*deterministic_paths, "release-manifest.json"])

            release_screenshots = tuple(release.verified.manifest.unhashed_artifacts)
            production_screenshots = tuple(production.verified.manifest.unhashed_artifacts)
            if release_screenshots != production_screenshots:
                errors.append("screenshot nondeterminism contracts differ between bundles")
            screenshots = {
                "paths": list(release_screenshots),
                "treatment": "verified-present-unhashed-not-compared",
            }
    except (OSError, UnicodeError, ValueError) as error:
        errors.append(str(error))

    return ReleaseLineageReport(
        release_candidate_sha=release_candidate_sha,
        production_candidate_sha=production_candidate_sha,
        result="fail" if errors else "pass",
        identities=identities,
        normalized=normalized_report,
        screenshots=screenshots,
        compared_artifacts=compared,
        errors=tuple(errors),
    )


def _verify_candidate_shas(release_sha: str, production_sha: str, *, repository: Path) -> None:
    for label, candidate in (
        ("release_candidate_sha", release_sha),
        ("production_candidate_sha", production_sha),
    ):
        if _FULL_SHA.fullmatch(candidate) is None:
            raise ValueError(f"{label} must be a full lowercase Git commit ID")
        result = subprocess.run(
            ["git", "cat-file", "-e", f"{candidate}^{{commit}}"],
            cwd=repository,
            check=False,
            capture_output=True,
        )
        if result.returncode:
            raise ValueError(f"{label} is not a commit in the current repository: {candidate}")
    if release_sha == production_sha:
        raise ValueError("release and production candidate commits must be different")
    ancestry = subprocess.run(
        ["git", "merge-base", "--is-ancestor", release_sha, production_sha],
        cwd=repository,
        check=False,
        capture_output=True,
    )
    if ancestry.returncode == 1:
        raise ValueError("release_candidate_sha is not an ancestor of production_candidate_sha")
    if ancestry.returncode != 0:
        raise ValueError("could not verify release-to-production Git ancestry")


def _materialize_bundle(source: Path, stack: ExitStack) -> Path:
    source = source.resolve()
    if source.is_dir():
        return source
    if not source.is_file() or not is_zipfile(source):
        raise ValueError(f"release bundle must be a directory or ZIP archive: {source}")
    temporary = Path(stack.enter_context(tempfile.TemporaryDirectory()))
    try:
        with ZipFile(source) as archive:
            seen: set[str] = set()
            for info in archive.infolist():
                relative = PurePosixPath(info.filename)
                if info.filename in seen:
                    raise ValueError(f"release archive repeats an entry: {info.filename}")
                seen.add(info.filename)
                if relative.is_absolute() or ".." in relative.parts:
                    raise ValueError(f"release archive contains an unsafe path: {info.filename}")
                if not relative.parts or relative.parts[0] != ARCHIVE_ROOT_DIR:
                    raise ValueError(
                        f"release archive entries must be rooted under {ARCHIVE_ROOT_DIR}/"
                    )
                entry_type = stat.S_IFMT(info.external_attr >> 16)
                if entry_type not in {0, stat.S_IFREG, stat.S_IFDIR}:
                    raise ValueError(f"release archive contains a non-file entry: {info.filename}")
            archive.extractall(temporary)
    except (BadZipFile, zlib.error, RuntimeError, NotImplementedError) as error:
        raise ValueError(
            f"release archive {source.name!r} is not a readable ZIP archive: {error}"
        ) from error
    bundle = temporary / ARCHIVE_ROOT_DIR
    if not bundle.is_dir():
        raise ValueError("release archive does not contain its canonical bundle directory")
    return bundle


def _load_bundle(bundle_dir: Path, expected_sha: str) -> _LoadedBundle:
    verified = verify_release_bundle_artifacts(bundle_dir)
    if verified.status.git_commit != expected_sha:
        raise ValueError(
            "bundle commit does not match supplied candidate SHA: "
            f"expected {expected_sha}, found {verified.status.git_commit}"
        )
    actual_files = {
        path.relative_to(bundle_dir).as_posix() for path in bundle_dir.rglob("*") if path.is_file()
    }
    declared_files = set(verified.status.included_artifacts)
    if actual_files != declared_files:
        raise ValueError(
            "release bundle file set differs from release status: "
            f"undeclared={sorted(actual_files - declared_files)}, "
            f"missing={sorted(declared_files - actual_files)}"
        )
    raw = {relative: (bundle_dir / relative).read_bytes() for relative in sorted(actual_files)}
    json_paths = (
        "release-status.json",
        "release-manifest.json",
        "data/build_manifest.json",
        "data/canonical-dataset.json",
        "data/consensus.json",
        "data/provenance_manifest.json",
        "data/publication_view_model.json",
        "data/validation_report.json",
    )
    parsed: dict[str, dict[str, Any]] = {}
    for relative in json_paths:
        value = read_json(bundle_dir / relative)
        if not isinstance(value, dict):
            raise ValueError(f"release artifact must contain a JSON object: {relative}")
        if raw[relative] != canonical_json_bytes(value):
            raise ValueError(f"release JSON artifact is not canonical: {relative}")
        parsed[relative] = value
    generated_at = _require_string(parsed["release-status.json"], "generated_at")
    _verify_internal_identities(parsed, raw, expected_sha, generated_at)
    return _LoadedBundle(verified=verified, raw=raw, json=parsed, generated_at=generated_at)


def _verify_internal_identities(
    parsed: dict[str, dict[str, Any]], raw: dict[str, bytes], expected_sha: str, generated_at: str
) -> None:
    status = parsed["release-status.json"]
    manifest = parsed["release-manifest.json"]
    consensus = parsed["data/consensus.json"]
    provenance = parsed["data/provenance_manifest.json"]
    publication = parsed["data/publication_view_model.json"]
    validation = parsed["data/validation_report.json"]
    build = parsed["data/build_manifest.json"]
    metadata = _require_mapping(publication, "metadata")
    election_id = _require_string(status, "election_id")
    for relative, value in (
        ("data/consensus.json", consensus),
        ("data/provenance_manifest.json", provenance),
        ("data/validation_report.json", validation),
        ("data/build_manifest.json", build),
    ):
        if _require_string(value, "election_id") != election_id:
            raise ValueError(f"{relative} election identity differs from release status")
    if _require_string(metadata, "election_id") != election_id:
        raise ValueError("publication view model election identity differs from release status")
    dataset_election = _canonical_dataset_election(parsed["data/canonical-dataset.json"])
    if dataset_election != election_id:
        raise ValueError("canonical dataset election identity differs from release status")
    for relative, value in (
        ("release-manifest.json", manifest),
        ("data/consensus.json", consensus),
        ("data/provenance_manifest.json", provenance),
        ("data/validation_report.json", validation),
        ("data/build_manifest.json", build),
    ):
        timestamp_key = "generated_at" if relative != "data/consensus.json" else "computed_at"
        if _require_string(value, timestamp_key) != generated_at:
            raise ValueError(f"{relative} timestamp differs from release status")
    if _require_string(metadata, "generated_at") != generated_at:
        raise ValueError("publication view model timestamp differs from release status")
    if (
        _require_string(build, "git_commit") != expected_sha
        or _require_string(metadata, "git_commit") != expected_sha
    ):
        raise ValueError("commit-bound bundle metadata differs from supplied candidate SHA")
    for key in ("source_panel_id", "source_panel_hash", "source_registry_hash"):
        if metadata.get(key) != status.get(key):
            raise ValueError(f"publication view model {key} differs from release status")
    dataset_digest = hashlib.sha256(raw["data/canonical-dataset.json"]).hexdigest()
    if _require_string(consensus, "dataset_hash") != dataset_digest:
        raise ValueError("consensus dataset hash differs from the canonical dataset")
    if provenance.get("dataset_hash") != dataset_digest:
        raise ValueError("provenance dataset hash differs from the canonical dataset")
    consensus_digest = hashlib.sha256(raw["data/consensus.json"]).hexdigest()
    if build.get("consensus_output_hash") != consensus_digest:
        raise ValueError("build manifest consensus hash differs from consensus.json")
    if provenance.get("consensus_output_hash") != consensus_digest:
        raise ValueError("provenance manifest consensus hash differs from consensus.json")
    if _require_mapping(build, "input_snapshot_hashes") != _require_mapping(
        provenance, "input_snapshot_hashes"
    ):
        raise ValueError("build and provenance manifests name different source inputs")
    artifact_hashes = _require_mapping(build, "artifact_hashes")
    for relative, digest in artifact_hashes.items():
        if not isinstance(digest, str):
            raise ValueError("build manifest artifact hashes must map paths to hashes")
        artifact = f"data/{relative}"
        if artifact not in raw:
            raise ValueError(f"build manifest names a missing publication artifact: {artifact}")
        if hashlib.sha256(raw[artifact]).hexdigest() != digest:
            raise ValueError(f"build manifest artifact hash mismatch: {artifact}")


def _release_identity(bundle: _LoadedBundle) -> dict[str, Any]:
    status = bundle.json["release-status.json"]
    dataset = bundle.json["data/canonical-dataset.json"]
    consensus = bundle.json["data/consensus.json"]
    provenance = bundle.json["data/provenance_manifest.json"]
    build = bundle.json["data/build_manifest.json"]
    dataset_election = _canonical_dataset_election(dataset)
    return {
        "canonical_dataset_election_id": dataset_election,
        "canonical_dataset_sha256": hashlib.sha256(
            bundle.raw["data/canonical-dataset.json"]
        ).hexdigest(),
        "configuration_hash": _require_string(build, "configuration_hash"),
        "consensus_dataset_hash": _require_string(consensus, "dataset_hash"),
        "consensus_input_hash": _require_string(consensus, "input_hash"),
        "election_id": _require_string(status, "election_id"),
        "normalized_data_hash": _require_string(build, "normalized_data_hash"),
        "release_version": _require_string(status, "release_version"),
        "source_decision_inputs": _require_mapping(provenance, "input_snapshot_hashes"),
        "source_panel_hash": _require_string(status, "source_panel_hash"),
        "source_panel_id": _require_string(status, "source_panel_id"),
        "source_registry_hash": _require_string(status, "source_registry_hash"),
    }


def _normalized_artifacts(
    bundle: _LoadedBundle, candidate_sha: str
) -> tuple[dict[str, bytes], dict[str, tuple[str, ...]]]:
    normalized = dict(bundle.raw)
    fields: dict[str, tuple[str, ...]] = {}
    timestamp = bundle.generated_at

    consensus = copy.deepcopy(bundle.json["data/consensus.json"])
    consensus_paths = ["/computed_at"]
    consensus["computed_at"] = _NORMALIZED_TIMESTAMP
    races = consensus.get("races")
    if not isinstance(races, list):
        raise ValueError("consensus races must be a list")
    for index, race in enumerate(cast(list[object], races)):
        if not isinstance(race, dict):
            raise ValueError("consensus races must contain objects")
        typed_race = cast(dict[str, Any], race)
        if typed_race.get("computed_at") != timestamp:
            raise ValueError("consensus race timestamp differs from release status")
        typed_race["computed_at"] = _NORMALIZED_TIMESTAMP
        consensus_paths.append(f"/races/{index}/computed_at")
    normalized["data/consensus.json"] = canonical_json_bytes(consensus)
    fields["data/consensus.json"] = tuple(consensus_paths)

    publication = copy.deepcopy(bundle.json["data/publication_view_model.json"])
    metadata = _require_mapping(publication, "metadata")
    metadata["generated_at"] = _NORMALIZED_TIMESTAMP
    metadata["git_commit"] = _NORMALIZED_COMMIT
    normalized["data/publication_view_model.json"] = canonical_json_bytes(publication)
    fields["data/publication_view_model.json"] = (
        "/metadata/generated_at",
        "/metadata/git_commit",
    )

    validation = copy.deepcopy(bundle.json["data/validation_report.json"])
    validation["generated_at"] = _NORMALIZED_TIMESTAMP
    normalized["data/validation_report.json"] = canonical_json_bytes(validation)
    fields["data/validation_report.json"] = ("/generated_at",)

    normalized_consensus_hash = hashlib.sha256(normalized["data/consensus.json"]).hexdigest()
    provenance = copy.deepcopy(bundle.json["data/provenance_manifest.json"])
    provenance["generated_at"] = _NORMALIZED_TIMESTAMP
    provenance["consensus_output_hash"] = normalized_consensus_hash
    normalized["data/provenance_manifest.json"] = canonical_json_bytes(provenance)
    fields["data/provenance_manifest.json"] = (
        "/consensus_output_hash",
        "/generated_at",
    )

    notes = bundle.raw["RELEASE_NOTES.md"].decode("utf-8")
    built_line = f"- Built at: {timestamp}"
    commit_line = f"- Code revision: `{candidate_sha}`"
    if notes.count(built_line) != 1 or notes.count(commit_line) != 1:
        raise ValueError("release notes do not contain the documented commit-bound provenance")
    notes = notes.replace(built_line, f"- Built at: {_NORMALIZED_TIMESTAMP}")
    notes = notes.replace(commit_line, f"- Code revision: `{_NORMALIZED_COMMIT}`")
    normalized["RELEASE_NOTES.md"] = notes.encode()
    fields["RELEASE_NOTES.md"] = ("line:Built at", "line:Code revision")

    guide_path = bundle.verified.status.guide_html_artifact
    guide = bundle.raw[guide_path].decode("utf-8")
    short_commit = candidate_sha[:12]
    audit_site_pattern = re.compile(
        rf'(<span class="audit-site">Site updated ){re.escape(timestamp[:10])}'
        rf'( \(<a href="[^"]*/commit/){re.escape(candidate_sha)}'
        rf'("[^>]*>){re.escape(short_commit)}(</a>\)</span>)'
    )
    audit_site_matches = list(audit_site_pattern.finditer(guide))
    if len(audit_site_matches) != 1:
        raise ValueError(
            "rendered guide must contain exactly one documented audit-site provenance field"
        )
    match = audit_site_matches[0]
    normalized_audit_site = (
        f"{match.group(1)}{_NORMALIZED_DATE}{match.group(2)}"
        f"{_NORMALIZED_COMMIT}{match.group(3)}"
        f"{_NORMALIZED_COMMIT[:12]}{match.group(4)}"
    )
    guide = f"{guide[: match.start()]}{normalized_audit_site}{guide[match.end() :]}"
    normalized[guide_path] = guide.encode()
    fields[guide_path] = (
        "html:commit-link",
        "html:commit-label",
        "html:site-updated-date",
    )

    build = copy.deepcopy(bundle.json["data/build_manifest.json"])
    build["generated_at"] = _NORMALIZED_TIMESTAMP
    build["git_commit"] = _NORMALIZED_COMMIT
    build["consensus_output_hash"] = normalized_consensus_hash
    build_hashes = _require_mapping(build, "artifact_hashes")
    build_paths = ["/consensus_output_hash", "/generated_at", "/git_commit"]
    for relative in sorted(build_hashes):
        artifact = f"data/{relative}"
        normalized_digest = hashlib.sha256(normalized[artifact]).hexdigest()
        if build_hashes[relative] != normalized_digest:
            build_paths.append(f"/artifact_hashes/{relative}")
        build_hashes[relative] = normalized_digest
    normalized["data/build_manifest.json"] = canonical_json_bytes(build)
    fields["data/build_manifest.json"] = tuple(build_paths)

    status = copy.deepcopy(bundle.json["release-status.json"])
    status["generated_at"] = _NORMALIZED_TIMESTAMP
    status["git_commit"] = _NORMALIZED_COMMIT
    normalized["release-status.json"] = canonical_json_bytes(status)
    fields["release-status.json"] = ("/generated_at", "/git_commit")

    manifest = copy.deepcopy(bundle.json["release-manifest.json"])
    manifest["generated_at"] = _NORMALIZED_TIMESTAMP
    manifest_hashes = _require_mapping(manifest, "artifact_hashes")
    manifest_paths = ["/generated_at"]
    for relative in sorted(manifest_hashes):
        normalized_digest = hashlib.sha256(normalized[relative]).hexdigest()
        if manifest_hashes[relative] != normalized_digest:
            manifest_paths.append(f"/artifact_hashes/{relative}")
        manifest_hashes[relative] = normalized_digest
    normalized["release-manifest.json"] = canonical_json_bytes(manifest)
    fields["release-manifest.json"] = tuple(manifest_paths)
    return normalized, fields


def _mapping_differences(first: dict[str, Any], second: dict[str, Any]) -> list[str]:
    return [
        f"release identity differs: {key}"
        for key in sorted(set(first) | set(second))
        if first.get(key) != second.get(key)
    ]


def _canonical_dataset_election(dataset: dict[str, Any]) -> str:
    election = dataset.get("election")
    if isinstance(election, str):
        return election
    inventory = _require_mapping(dataset, "inventory")
    return _require_string(_require_mapping(inventory, "election"), "id")


def _require_mapping(value: dict[str, Any], key: str) -> dict[str, Any]:
    nested = value.get(key)
    if not isinstance(nested, dict):
        raise ValueError(f"release metadata field must be an object: {key}")
    return cast(dict[str, Any], nested)


def _require_string(value: dict[str, Any], key: str) -> str:
    nested = value.get(key)
    if not isinstance(nested, str) or not nested:
        raise ValueError(f"release metadata field must be a non-empty string: {key}")
    return nested
