"""Declared release versions must exist as published GitHub Releases."""

from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path
from typing import Any

import pytest
import yaml
from typer.testing import CliRunner

from election_guide import cli
from election_guide.hosting.models import SiteManifest
from election_guide.hosting.releases import (
    RELEASE_QUERY_LIMIT,
    _published_tags,  # pyright: ignore[reportPrivateUsage]
    published_release_tags,
    verify_declared_releases_published,
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
