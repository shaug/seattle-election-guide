"""Declared release versions must exist as published GitHub Releases."""

from __future__ import annotations

import hashlib
import json
import re
import shutil
import subprocess
import zipfile
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
import yaml
from typer.testing import CliRunner

from election_guide import cli
from election_guide.hosting import (
    bundle_hash,
    releases,
    stage_pages_site,
    verify_staged_pages_site,
)
from election_guide.hosting.models import PublishedElection, SiteManifest
from election_guide.hosting.releases import (
    RELEASE_QUERY_LIMIT,
    _extract_bundle,  # pyright: ignore[reportPrivateUsage]
    _published_tags,  # pyright: ignore[reportPrivateUsage]
    published_release_tags,
    verify_declared_releases_published,
)
from election_guide.release.builder import (
    _write_deterministic_zip,  # pyright: ignore[reportPrivateUsage]
)
from election_guide.release.models import ARCHIVE_ROOT_DIR, release_archive_name
from tests.test_hosting import (
    COMMIT,
    CURRENT_BUNDLE_ID,
    OLDER_BUNDLE_ID,
    _manifest_election,  # pyright: ignore[reportPrivateUsage]
    _write_archive_bundles,  # pyright: ignore[reportPrivateUsage]
    _write_site_manifest,  # pyright: ignore[reportPrivateUsage]
)

CURRENT_ID = "wa-2026-primary"
OLDER_ID = "wa-2025-general"
PANEL_HASH = "b" * 64


def _manifest(*elections: tuple[str, str]) -> SiteManifest:
    return SiteManifest.model_validate(
        {
            "canonical_origin": "https://seattleelections.guide",
            "current_election_id": elections[0][0],
            "elections": [
                {
                    "election_id": election_id,
                    "bundle_id": f"{election_id}-{release_version}",
                    "release_version": release_version,
                    "source_panel_id": "test-panel-v2",
                    "source_panel_hash": PANEL_HASH,
                }
                for election_id, release_version in elections
            ],
        }
    )


def test_every_declared_version_published_passes() -> None:
    manifest = _manifest((CURRENT_ID, "2026-primary.2"), (OLDER_ID, "2025-general.1"))

    verify_declared_releases_published(manifest, {"2026-primary.2", "2025-general.1", "unused.1"})


def test_unpublished_version_names_the_election_and_the_tag() -> None:
    manifest = _manifest((CURRENT_ID, "2026-primary.3"))

    with pytest.raises(ValueError) as error:
        verify_declared_releases_published(manifest, {"2026-primary.2"})

    message = str(error.value)
    assert CURRENT_ID in message
    assert "2026-primary.3" in message
    assert "no published GitHub Release" in message


def test_every_unpublished_version_is_reported() -> None:
    manifest = _manifest((CURRENT_ID, "2026-primary.3"), (OLDER_ID, "2025-general.9"))

    with pytest.raises(ValueError) as error:
        verify_declared_releases_published(manifest, set())

    message = str(error.value)
    assert CURRENT_ID in message
    assert "2026-primary.3" in message
    assert OLDER_ID in message
    assert "2025-general.9" in message


def test_no_declared_release_is_satisfied_by_a_draft() -> None:
    manifest = _manifest((CURRENT_ID, "2026-primary.2"))
    payload = json.dumps(
        [
            {"tagName": "2026-primary.1", "isDraft": False},
            {"tagName": "2026-primary.2", "isDraft": True},
        ]
    )

    assert _published_tags(payload) == frozenset({"2026-primary.1"})
    with pytest.raises(ValueError, match=re.escape("2026-primary.2")):
        verify_declared_releases_published(manifest, _published_tags(payload))


def test_malformed_release_listing_is_rejected() -> None:
    with pytest.raises(ValueError, match="not an array"):
        _published_tags(json.dumps({"tagName": "2026-primary.2"}))
    with pytest.raises(ValueError, match="without a tag name"):
        _published_tags(json.dumps([{"isDraft": False}]))


def test_published_release_tags_reads_the_github_cli(monkeypatch: pytest.MonkeyPatch) -> None:
    recorded: dict[str, Any] = {}

    def _run(command: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        recorded["command"] = command
        return subprocess.CompletedProcess(
            command,
            0,
            stdout=json.dumps([{"tagName": "2026-primary.1", "isDraft": False}]),
            stderr="",
        )

    monkeypatch.setattr(subprocess, "run", _run)

    assert published_release_tags() == frozenset({"2026-primary.1"})
    assert recorded["command"][:3] == ["gh", "release", "list"]
    assert str(RELEASE_QUERY_LIMIT) in recorded["command"]


def test_published_release_tags_reports_a_failing_cli(monkeypatch: pytest.MonkeyPatch) -> None:
    def _run(command: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(command, 1, stdout="", stderr="gh: not authenticated")

    monkeypatch.setattr(subprocess, "run", _run)

    with pytest.raises(ValueError, match="gh: not authenticated"):
        published_release_tags()


def test_published_release_tags_reports_a_missing_cli(monkeypatch: pytest.MonkeyPatch) -> None:
    def _run(command: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        raise FileNotFoundError(command[0])

    monkeypatch.setattr(subprocess, "run", _run)

    with pytest.raises(ValueError, match="GitHub CLI is required"):
        published_release_tags()


def _write_manifest(path: Path, release_version: str) -> Path:
    manifest_path = path / "site.yaml"
    manifest_path.write_text(
        yaml.safe_dump(
            {
                "schema_version": "1.0",
                "canonical_origin": "https://seattleelections.guide",
                "current_election_id": CURRENT_ID,
                "elections": [
                    {
                        "election_id": CURRENT_ID,
                        "bundle_id": f"{CURRENT_ID}-{release_version}",
                        "release_version": release_version,
                        "source_panel_id": "test-panel-v2",
                        "source_panel_hash": PANEL_HASH,
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    return manifest_path


def test_cli_fails_on_an_unpublished_declared_version(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    manifest_path = _write_manifest(tmp_path, "2026-primary.3")
    monkeypatch.setattr(cli, "published_release_tags", lambda: frozenset({"2026-primary.2"}))

    result = CliRunner().invoke(cli.app, ["hosting", "verify-releases", str(manifest_path)])

    assert result.exit_code == 1
    assert "hosting verify-releases failed" in result.output
    assert CURRENT_ID in result.output
    assert "2026-primary.3" in result.output


def test_cli_passes_when_every_declared_version_is_published(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    manifest_path = _write_manifest(tmp_path, "2026-primary.2")
    monkeypatch.setattr(cli, "published_release_tags", lambda: frozenset({"2026-primary.2"}))

    result = CliRunner().invoke(cli.app, ["hosting", "verify-releases", str(manifest_path)])

    assert result.exit_code == 0
    assert "Declared releases: verified (1 declared)" in result.output


def _released_archive(bundle_dir: Path, release_version: str, destination: Path) -> Path:
    """A real published-shaped archive for one bundle, written by the release packer."""
    destination.mkdir(parents=True, exist_ok=True)
    archive_path = destination / release_archive_name(release_version)
    _write_deterministic_zip(
        bundle_dir,
        archive_path,
        datetime(2026, 7, 21, 12, 0, tzinfo=UTC),
    )
    return archive_path


def _delivering_download(archive_path: Path) -> Callable[..., Path]:
    """Stand in for `download_release_archive`.

    Staging renders HTML, which shells out to the pinned esbuild, so these tests
    replace the one download boundary rather than every subprocess call.
    """

    def _download(declaration: PublishedElection, destination: Path) -> Path:
        destination.mkdir(parents=True, exist_ok=True)
        target = destination / archive_path.name
        shutil.copy2(archive_path, target)
        return target

    return _download


def _older_declaration(**overrides: str) -> PublishedElection:
    declaration = dict(_manifest_election(OLDER_ID, OLDER_BUNDLE_ID, "general.1"))
    declaration.update(overrides)
    return PublishedElection.model_validate(declaration)


def test_two_election_manifest_stages_and_verifies_from_a_published_release(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The historical election is never built here — only downloaded and verified."""
    current, older = _write_archive_bundles(tmp_path / "bundles")
    archive = _released_archive(older, "general.1", tmp_path / "published")
    manifest_path = _write_site_manifest(
        tmp_path, current_first=True, older_bundle_sha256=bundle_hash(older)
    )
    monkeypatch.setattr(releases, "download_release_archive", _delivering_download(archive))
    output = tmp_path / "site"

    result = stage_pages_site(
        manifest_path,
        {CURRENT_BUNDLE_ID: current},
        output,
        expected_current_git_commit=COMMIT,
        released_bundle_dir=tmp_path / "released",
    )

    assert result.election_paths == (
        output / "e" / CURRENT_ID,
        output / "e" / OLDER_ID,
    )
    assert (output / "e" / OLDER_ID / "index.html").read_bytes() == b"older\n"
    deployment = verify_staged_pages_site(output, manifest_path, expected_current_git_commit=COMMIT)
    assert [election.election_id for election in deployment.elections] == [CURRENT_ID, OLDER_ID]


def test_a_tampered_historical_archive_fails_the_build(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    current, older = _write_archive_bundles(tmp_path / "bundles")
    pinned = bundle_hash(older)
    (older / "guide" / "guide.html").write_bytes(b"tampered\n")
    archive = _released_archive(older, "general.1", tmp_path / "published")
    manifest_path = _write_site_manifest(tmp_path, current_first=True, older_bundle_sha256=pinned)
    monkeypatch.setattr(releases, "download_release_archive", _delivering_download(archive))

    with pytest.raises(ValueError) as error:
        stage_pages_site(
            manifest_path,
            {CURRENT_BUNDLE_ID: current},
            tmp_path / "site",
            released_bundle_dir=tmp_path / "released",
        )

    assert str(error.value) == "release artifact hash mismatch: guide/guide.html"


def test_tampering_that_also_rewrites_the_release_manifest_is_caught_by_the_pin(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The archive's own manifest cannot vouch for it, which is why the pin exists."""
    current, older = _write_archive_bundles(tmp_path / "bundles")
    pinned = bundle_hash(older)
    tampered = b"tampered\n"
    (older / "guide" / "guide.html").write_bytes(tampered)
    manifest_path_in_bundle = older / "release-manifest.json"
    manifest = json.loads(manifest_path_in_bundle.read_text(encoding="utf-8"))
    manifest["artifact_hashes"]["guide/guide.html"] = hashlib.sha256(tampered).hexdigest()
    manifest_path_in_bundle.write_text(json.dumps(manifest), encoding="utf-8")
    archive = _released_archive(older, "general.1", tmp_path / "published")
    manifest_path = _write_site_manifest(tmp_path, current_first=True, older_bundle_sha256=pinned)
    monkeypatch.setattr(releases, "download_release_archive", _delivering_download(archive))

    with pytest.raises(ValueError) as error:
        stage_pages_site(
            manifest_path,
            {CURRENT_BUNDLE_ID: current},
            tmp_path / "site",
            released_bundle_dir=tmp_path / "released",
        )

    message = str(error.value)
    assert OLDER_BUNDLE_ID in message
    assert "bundle hash differs" in message


def test_a_missing_historical_archive_fails_the_build(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    current, older = _write_archive_bundles(tmp_path / "bundles")
    manifest_path = _write_site_manifest(
        tmp_path, current_first=True, older_bundle_sha256=bundle_hash(older)
    )

    def _failing_gh(command: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(command, 1, stdout="", stderr="release not found")

    monkeypatch.setattr(subprocess, "run", _failing_gh)

    with pytest.raises(ValueError) as error:
        stage_pages_site(
            manifest_path,
            {CURRENT_BUNDLE_ID: current},
            tmp_path / "site",
            released_bundle_dir=tmp_path / "released",
        )

    message = str(error.value)
    assert "could not download archive" in message
    assert "general.1" in message
    assert "release not found" in message


def test_an_unpinned_historical_election_refuses_to_resolve(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Without a pin nothing vouches for the download, so it must not be used."""
    current, older = _write_archive_bundles(tmp_path / "bundles")
    archive = _released_archive(older, "general.1", tmp_path / "published")
    manifest_path = _write_site_manifest(tmp_path, current_first=True)
    monkeypatch.setattr(releases, "download_release_archive", _delivering_download(archive))

    with pytest.raises(ValueError, match="must declare bundle_sha256"):
        stage_pages_site(
            manifest_path,
            {CURRENT_BUNDLE_ID: current},
            tmp_path / "site",
            released_bundle_dir=tmp_path / "released",
        )


def test_an_archive_escaping_the_bundle_root_is_rejected(tmp_path: Path) -> None:
    archive_path = tmp_path / "evil.zip"
    with zipfile.ZipFile(archive_path, "w") as archive:
        archive.writestr(f"{ARCHIVE_ROOT_DIR}/release-status.json", "{}")
        archive.writestr("../escaped.txt", "nope")
    declaration = _older_declaration(bundle_sha256="d" * 64)

    with pytest.raises(ValueError, match="outside"):
        _extract_bundle(archive_path, tmp_path / "out", declaration)


def test_supplying_every_bundle_locally_downloads_nothing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Current single-election behavior: nothing to resolve, so no release is read."""
    current, older = _write_archive_bundles(tmp_path / "bundles")
    manifest_path = _write_site_manifest(tmp_path, current_first=True)

    def _forbidden(declaration: PublishedElection, destination: Path) -> Path:
        raise AssertionError(f"no release should be read, but downloaded {declaration.bundle_id}")

    monkeypatch.setattr(releases, "download_release_archive", _forbidden)

    result = stage_pages_site(
        manifest_path,
        {CURRENT_BUNDLE_ID: current, OLDER_BUNDLE_ID: older},
        tmp_path / "site",
        expected_current_git_commit=COMMIT,
        released_bundle_dir=tmp_path / "released",
    )

    assert result.current_election_id == CURRENT_ID


def test_the_cli_reports_an_unreadable_archive_without_a_traceback(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    current, older = _write_archive_bundles(tmp_path / "bundles")
    published = tmp_path / "published"
    published.mkdir()
    archive = published / release_archive_name("general.1")
    archive.write_bytes(b"404: Not Found\n")
    manifest_path = _write_site_manifest(
        tmp_path, current_first=True, older_bundle_sha256=bundle_hash(older)
    )
    monkeypatch.setattr(releases, "download_release_archive", _delivering_download(archive))

    result = CliRunner().invoke(
        cli.app,
        [
            "hosting",
            "stage",
            str(manifest_path),
            "--bundle",
            f"{CURRENT_BUNDLE_ID}={current}",
            "--released-bundle-dir",
            str(tmp_path / "released"),
            "--output-dir",
            str(tmp_path / "site"),
        ],
    )

    assert result.exit_code == 1
    assert "hosting stage failed" in result.output
    assert "is not a readable ZIP archive" in result.output
    assert OLDER_BUNDLE_ID in result.output


def _corrupt_deflated_member(archive_path: Path, member: str) -> None:
    """Damage one deflated member's body in place, leaving the ZIP structure intact."""
    with zipfile.ZipFile(archive_path) as archive:
        info = archive.getinfo(member)
        assert info.compress_type == zipfile.ZIP_DEFLATED, "the packer deflates every entry"
        body_offset = info.header_offset + 30 + len(info.filename.encode()) + len(info.extra or b"")
    raw = bytearray(archive_path.read_bytes())
    for index in range(body_offset + 4, body_offset + 68):
        raw[index] ^= 0xFF
    archive_path.write_bytes(bytes(raw))


def test_a_corrupt_archive_member_fails_with_a_clear_message(tmp_path: Path) -> None:
    """In-place corruption of a real archive raises zlib.error, not BadZipFile."""
    _, older = _write_archive_bundles(tmp_path / "bundles")
    archive = _released_archive(older, "general.1", tmp_path / "published")
    _corrupt_deflated_member(archive, f"{ARCHIVE_ROOT_DIR}/data/publication_view_model.json")

    with pytest.raises(ValueError) as error:
        _extract_bundle(archive, tmp_path / "out", _older_declaration(bundle_sha256="d" * 64))

    message = str(error.value)
    assert "is not a readable ZIP archive" in message
    assert OLDER_BUNDLE_ID in message


def test_an_encrypted_archive_member_fails_with_a_clear_message(tmp_path: Path) -> None:
    archive_path = tmp_path / release_archive_name("general.1")
    with zipfile.ZipFile(archive_path, "w") as archive:
        archive.writestr(f"{ARCHIVE_ROOT_DIR}/release-status.json", "{}")
    raw = bytearray(archive_path.read_bytes())
    raw[6] |= 0x01  # the local header's general-purpose "encrypted" flag
    central = raw.index(b"PK\x01\x02")
    raw[central + 8] |= 0x01  # and the central directory's, which is the one read
    archive_path.write_bytes(bytes(raw))
    declaration = _older_declaration(bundle_sha256="d" * 64)

    with pytest.raises(ValueError, match="is not a readable ZIP archive"):
        _extract_bundle(archive_path, tmp_path / "out", declaration)


def test_the_cli_prints_the_pin_a_historical_election_must_declare(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Issue 270: the one value `site.yaml` must carry, obtainable without private API."""
    current, older = _write_archive_bundles(tmp_path / "bundles")
    archive = _released_archive(older, "general.1", tmp_path / "published")

    printed = CliRunner().invoke(cli.app, ["hosting", "bundle-hash", str(older)])

    assert printed.exit_code == 0
    pin = printed.output.strip()
    assert re.fullmatch(r"[0-9a-f]{64}", pin), pin
    manifest_path = _write_site_manifest(tmp_path, current_first=True, older_bundle_sha256=pin)
    monkeypatch.setattr(releases, "download_release_archive", _delivering_download(archive))

    result = stage_pages_site(
        manifest_path,
        {CURRENT_BUNDLE_ID: current},
        tmp_path / "site",
        expected_current_git_commit=COMMIT,
        released_bundle_dir=tmp_path / "released",
    )

    assert result.election_paths == (
        tmp_path / "site" / "e" / CURRENT_ID,
        tmp_path / "site" / "e" / OLDER_ID,
    )


def test_the_cli_refuses_a_directory_that_is_not_a_release_bundle(tmp_path: Path) -> None:
    """A pin computed from the wrong tree is wrong silently, which is worse than no pin."""
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    (elsewhere / "notes.txt").write_text("nothing to do with a release", encoding="utf-8")

    result = CliRunner().invoke(cli.app, ["hosting", "bundle-hash", str(elsewhere)])

    assert result.exit_code == 1
    assert "hosting bundle-hash failed" in result.output
    assert "release-status.json" in result.output


def test_a_mismatched_pin_names_both_the_declared_and_the_computed_digest(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Issue 270: a mismatch that withholds what it found leaves nothing to act on."""
    current, older = _write_archive_bundles(tmp_path / "bundles")
    computed = bundle_hash(older)
    archive = _released_archive(older, "general.1", tmp_path / "published")
    declared = "d" * 64
    manifest_path = _write_site_manifest(tmp_path, current_first=True, older_bundle_sha256=declared)
    monkeypatch.setattr(releases, "download_release_archive", _delivering_download(archive))

    with pytest.raises(ValueError) as error:
        stage_pages_site(
            manifest_path,
            {CURRENT_BUNDLE_ID: current},
            tmp_path / "site",
            released_bundle_dir=tmp_path / "released",
        )

    message = str(error.value)
    assert "bundle hash differs" in message
    assert declared in message
    assert computed in message
