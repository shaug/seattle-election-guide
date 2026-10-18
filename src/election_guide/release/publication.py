"""Publish immutable release archives, or recover their verified canonical bytes."""

from __future__ import annotations

import hashlib
import json
import re
import subprocess
from pathlib import Path
from typing import Any, cast

from election_guide.github_cli import download_gh, parse_paginated_objects, run_gh, trailing_line
from election_guide.hosting.pages import bundle_hash
from election_guide.hosting.releases import extract_release_bundle
from election_guide.release.automation_models import (
    ArtifactRef,
    CandidateRecord,
    FileDigest,
    PublicationResult,
    PublishedArchive,
)
from election_guide.release.candidate import (
    SITE_MANIFEST,
    stage_current_candidate,
    verify_candidate,
)
from election_guide.release.comparison import (
    compare_release_bundles,
    verify_release_bundle_artifacts,
)
from election_guide.release.declaration import resolve_release
from election_guide.serialization import canonical_json_bytes


def _digest(path: Path) -> FileDigest:
    hasher = hashlib.sha256()
    size = 0
    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            hasher.update(chunk)
            size += len(chunk)
    return FileDigest(sha256=hasher.hexdigest(), size=size)


def publication_body(candidate: CandidateRecord, notes: str) -> str:
    """Final ownership marker binds reviewed inputs and the exact bundled notes."""
    request = candidate.declaration.publication_request
    if request is None:
        raise ValueError("automatic publication requires a reviewed publication request")
    identity = {
        "repository": candidate.producer.repository,
        "version": candidate.declaration.release_version,
        "source_sha": candidate.source_sha,
        "request_sha256": hashlib.sha256(canonical_json_bytes(request.model_dump())).hexdigest(),
        "notes_sha256": hashlib.sha256(notes.encode("utf-8")).hexdigest(),
    }
    marker = "<!-- election-guide-publication " + json.dumps(identity, sort_keys=True) + " -->"
    return notes.rstrip() + "\n\n" + marker


def _object(payload: str) -> dict[str, Any]:
    value: Any = json.loads(payload)
    if not isinstance(value, dict):
        raise ValueError("GitHub returned an invalid object")
    return cast(dict[str, Any], value)


def _read(endpoint: str) -> dict[str, Any]:
    return _object(run_gh(["gh", "api", endpoint], "could not read publication state"))


def _pages(endpoint: str) -> list[dict[str, Any]]:
    return parse_paginated_objects(
        run_gh(
            ["gh", "api", endpoint + "?per_page=100", "--paginate", "--slurp"],
            "could not read complete publication state",
        ),
        context="publication state",
    )


def _id(record: dict[str, Any]) -> int:
    value = record.get("id")
    if type(value) is not int or value <= 0:
        raise ValueError("GitHub publication state requires a positive ID")
    return value


def _tag_commit(base: str, version: str) -> str | None:
    tags = _pages(base + "/tags")
    names = [entry.get("name") for entry in tags]
    if any(not isinstance(name, str) or not name for name in names):
        raise ValueError("GitHub returned an invalid tag name")
    if names.count(version) > 1:
        raise ValueError("GitHub returned duplicate release tags")
    if version not in names:
        return None
    endpoint = base + f"/git/ref/tags/{version}"
    seen: set[str] = set()
    while True:
        target: Any = _read(endpoint).get("object")
        if not isinstance(target, dict):
            raise ValueError("invalid release tag object")
        target = cast(dict[str, Any], target)
        sha, kind = target.get("sha"), target.get("type")
        if not isinstance(sha, str) or re.fullmatch(r"[0-9a-f]{40}", sha) is None:
            raise ValueError("release tag does not identify a full commit")
        if kind == "commit":
            return sha
        if kind != "tag" or sha in seen:
            raise ValueError("release tag cannot be peeled to a commit")
        seen.add(sha)
        endpoint = base + f"/git/tags/{sha}"


def _release(base: str, version: str) -> dict[str, Any] | None:
    releases = _pages(base + "/releases")
    if any(not isinstance(entry.get("tag_name"), str) for entry in releases):
        raise ValueError("GitHub returned an invalid release tag name")
    matches = [entry for entry in releases if entry["tag_name"] == version]
    if len(matches) > 1:
        raise ValueError("multiple releases claim the candidate version")
    return matches[0] if matches else None


def _check_release(
    release: dict[str, Any], candidate: CandidateRecord, body: str, notes: str
) -> None:
    _id(release)
    if release.get("tag_name") != candidate.declaration.release_version:
        raise ValueError("release tag name differs from candidate")
    if type(release.get("draft")) is not bool or release.get("prerelease") is not False:
        raise ValueError("release has an invalid draft or prerelease state")
    actual = release.get("body")
    if actual != body and (release["draft"] or actual != notes):
        raise ValueError("release notes or ownership marker conflicts with candidate")
    if release["draft"] and (
        release.get("target_commitish") != candidate.source_sha
        or trailing_line(str(actual)) != trailing_line(body)
    ):
        raise ValueError("draft ownership or target conflicts with candidate")


def _assets(base: str, release: dict[str, Any], name: str) -> list[dict[str, Any]]:
    assets = _pages(base + f"/releases/{_id(release)}/assets")
    if len(assets) > 1 or any(asset.get("name") != name for asset in assets):
        raise ValueError("release contains duplicate or unrecognized assets")
    if not assets and not release["draft"]:
        raise ValueError("published release is missing its canonical archive")
    for asset in assets:
        _id(asset)
        if asset.get("state") != "uploaded":
            raise ValueError("release asset upload is incomplete")
        size, digest = asset.get("size"), asset.get("digest")
        if type(size) is not int or size < 0 or not isinstance(digest, str):
            raise ValueError("release asset is missing size or SHA-256 metadata")
        if re.fullmatch(r"sha256:[0-9a-f]{64}", digest) is None:
            raise ValueError("release asset digest must be SHA-256")
    return assets


def _artifact(
    reference: ArtifactRef, candidate: CandidateRecord, kind: str, used_ids: set[int]
) -> None:
    if reference.producer != candidate.producer:
        raise ValueError(f"{kind} artifact producer differs from candidate")
    if reference.name != f"{kind}-{candidate.producer.run_id}-{candidate.producer.run_attempt}":
        raise ValueError(f"{kind} artifact name differs from producing attempt")
    if reference.id in used_ids:
        raise ValueError("publication artifacts must have distinct IDs")


def _checkout(repository: Path, source_sha: str) -> None:
    for args, expected in (
        (["rev-parse", "HEAD"], source_sha),
        (["status", "--porcelain", "--untracked-files=normal"], ""),
    ):
        result = subprocess.run(
            ["git", *args], cwd=repository, text=True, capture_output=True, check=False
        )
        if result.returncode or result.stdout.strip() != expected:
            raise ValueError("publication requires a clean checkout of the exact reviewed source")


def _bundle(archive: Path, destination: Path, candidate: CandidateRecord) -> None:
    extract_release_bundle(archive, destination, candidate.declaration)
    verified = verify_release_bundle_artifacts(destination)
    actual = {
        path.relative_to(destination).as_posix()
        for path in destination.rglob("*")
        if path.is_file()
    }
    if actual != set(verified.status.included_artifacts):
        raise ValueError("release ZIP member set differs from declared artifacts")
    if (
        verified.status.git_commit != candidate.source_sha
        or verified.status.generated_at != candidate.generated_at
    ):
        raise ValueError("release ZIP source or timestamp differs from reviewed candidate")


def verify_canonical_publication(receipt: PublicationResult, published: PublishedArchive) -> None:
    previous = receipt.published
    identity = (
        "release_id",
        "asset_id",
        "asset_name",
        "archive",
        "release_manifest_sha256",
        "canonical_bundle_sha256",
        "promotion_manifest_sha256",
    )
    candidate_identity = (
        "declaration",
        "site_manifest_sha256",
        "source_sha",
        "generated_at",
        "inputs",
    )
    if (
        any(getattr(previous, field) != getattr(published, field) for field in identity)
        or any(
            getattr(previous.candidate, field) != getattr(published.candidate, field)
            for field in candidate_identity
        )
        or previous.candidate.producer.repository != published.candidate.producer.repository
    ):
        raise ValueError("conflicting canonical release in existing publication receipt")
    bind_publication(previous, receipt.promotion_artifact)


def publish_candidate(
    candidate: CandidateRecord,
    *,
    candidate_artifact: ArtifactRef,
    repository: Path,
    archive_path: Path,
    work_dir: Path,
    existing_receipt: PublicationResult | None,
) -> PublishedArchive:
    """Finalize only verified archives; existing published bytes always remain canonical."""
    candidate = CandidateRecord.model_validate(candidate.model_dump())
    candidate_artifact = ArtifactRef.model_validate(candidate_artifact.model_dump())
    if candidate.declaration.publication_request is None:
        raise ValueError("automatic publication requires a reviewed publication request")
    _artifact(
        candidate_artifact,
        candidate,
        "candidate",
        {candidate.release_artifact.id, candidate.site_artifact.id},
    )
    _checkout(repository, candidate.source_sha)
    resolved = resolve_release(SITE_MANIFEST, repository=repository)
    if (
        candidate.declaration != resolved.current
        or candidate.inputs != candidate.declaration.publication_request.inputs
    ):
        raise ValueError("candidate differs from reviewed publication request")
    if archive_path.name != resolved.archive_name:
        raise ValueError(f"candidate must use canonical archive filename {resolved.archive_name!r}")
    if _digest(archive_path) != candidate.archive:
        raise ValueError("candidate archive bytes differ")
    if work_dir.exists():
        raise ValueError("publication requires a fresh work directory")
    work_dir.mkdir(parents=True)
    fresh_bundle = work_dir / "candidate-bundle"
    _bundle(archive_path, fresh_bundle, candidate)
    stage_current_candidate(
        resolved,
        repository=repository,
        bundle_dir=fresh_bundle,
        output_dir=work_dir / "candidate-site",
        source_sha=candidate.source_sha,
    )
    verify_candidate(
        candidate,
        repository=repository,
        archive_path=archive_path,
        site_dir=work_dir / "candidate-site",
    )
    notes = (fresh_bundle / "RELEASE_NOTES.md").read_text(encoding="utf-8")
    body = publication_body(candidate, notes)
    base = f"repos/{candidate.producer.repository}"
    version = candidate.declaration.release_version
    tag = _tag_commit(base, version)
    release = _release(base, version)
    if tag is not None and tag != candidate.source_sha:
        raise ValueError("release tag targets a different source commit")
    if release is None and tag is not None:
        raise ValueError("orphan release tag requires operator inspection")
    if release is None and existing_receipt is not None:
        raise ValueError("publication receipt exists without its release")
    assets: list[dict[str, Any]] = []
    if release is not None:
        _check_release(release, candidate, body, notes)
        if not release["draft"] and tag is None:
            raise ValueError("published release has no source tag")
        assets = _assets(base, release, resolved.archive_name)
        if existing_receipt is not None and release["draft"]:
            raise ValueError("publication receipt cannot identify a draft")
    if release is None:
        release = _object(
            run_gh(
                [
                    "gh",
                    "api",
                    base + "/releases",
                    "--method",
                    "POST",
                    "-f",
                    f"tag_name={version}",
                    "-f",
                    f"target_commitish={candidate.source_sha}",
                    "-f",
                    f"name={version}",
                    "-f",
                    f"body={body}",
                    "-F",
                    "draft=true",
                    "-F",
                    "prerelease=false",
                ],
                "could not create owned release draft",
            )
        )
        _check_release(release, candidate, body, notes)
        if release["draft"] is not True:
            raise ValueError("new release did not remain a draft")
        assets = _assets(base, release, resolved.archive_name)
    if not assets:
        run_gh(
            [
                "gh",
                "release",
                "upload",
                version,
                str(archive_path),
                "--repo",
                candidate.producer.repository,
            ],
            "could not upload missing release archive",
        )
        assets = _assets(base, release, resolved.archive_name)
        if len(assets) != 1:
            raise ValueError("draft upload did not produce one canonical archive")
    asset = assets[0]
    canonical_archive = work_dir / resolved.archive_name
    download_gh(
        [
            "gh",
            "api",
            base + f"/releases/assets/{_id(asset)}",
            "-H",
            "Accept: application/octet-stream",
        ],
        canonical_archive,
        "could not download canonical release archive",
    )
    archive_digest = _digest(canonical_archive)
    if archive_digest.size != asset["size"] or "sha256:" + archive_digest.sha256 != asset["digest"]:
        raise ValueError("downloaded archive differs from GitHub asset metadata")
    canonical_bundle = work_dir / "canonical-bundle"
    _bundle(canonical_archive, canonical_bundle, candidate)
    compare_release_bundles(fresh_bundle, canonical_bundle)
    promotion = work_dir / "promotion-site"
    stage_current_candidate(
        resolved,
        repository=repository,
        bundle_dir=canonical_bundle,
        output_dir=promotion,
        source_sha=candidate.source_sha,
    )
    published = PublishedArchive(
        candidate=candidate,
        candidate_artifact=candidate_artifact,
        release_id=_id(release),
        asset_id=_id(asset),
        asset_name=resolved.archive_name,
        archive=archive_digest,
        release_manifest_sha256=_digest(canonical_bundle / "release-manifest.json").sha256,
        canonical_bundle_sha256=bundle_hash(canonical_bundle),
        promotion_manifest_sha256=_digest(promotion / "deployment-manifest.json").sha256,
    )
    if existing_receipt is not None:
        verify_canonical_publication(
            PublicationResult.model_validate(existing_receipt.model_dump()), published
        )
    _checkout(repository, candidate.source_sha)
    if release["draft"]:
        final = _object(
            run_gh(
                [
                    "gh",
                    "api",
                    base + f"/releases/{_id(release)}",
                    "--method",
                    "PATCH",
                    "-F",
                    "draft=false",
                    "-f",
                    "make_latest=false",
                ],
                "could not publish verified release draft",
            )
        )
        _check_release(final, candidate, body, notes)
        if final.get("body") != body:
            raise ValueError("finalized release ownership marker changed")
        if final["draft"] or _id(final) != published.release_id:
            raise ValueError("release did not finalize publication")
        final_assets = _assets(base, final, resolved.archive_name)
        identity_fields = ("id", "name", "size", "digest", "state")
        if _tag_commit(base, version) != candidate.source_sha or any(
            final_assets[0][field] != asset[field] for field in identity_fields
        ):
            raise ValueError("finalized release identity changed")
    (work_dir / "published-archive.json").write_bytes(
        canonical_json_bytes(published.model_dump(mode="json"))
    )
    return published


def bind_publication(
    published: PublishedArchive, promotion_artifact: ArtifactRef
) -> PublicationResult:
    """Bind captured upload-action metadata; Python never uploads Actions artifacts."""
    published = PublishedArchive.model_validate(published.model_dump())
    promotion_artifact = ArtifactRef.model_validate(promotion_artifact.model_dump())
    candidate = published.candidate
    _artifact(
        published.candidate_artifact,
        candidate,
        "candidate",
        {candidate.release_artifact.id, candidate.site_artifact.id},
    )
    _artifact(
        promotion_artifact,
        candidate,
        "promotion",
        {
            candidate.release_artifact.id,
            candidate.site_artifact.id,
            published.candidate_artifact.id,
        },
    )
    return PublicationResult(published=published, promotion_artifact=promotion_artifact)
