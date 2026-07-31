"""Strict model-boundary tests for election archive manifests."""

from __future__ import annotations

import pytest

from election_guide.hosting.models import DeploymentManifest, SiteManifest

CURRENT_ID = "wa-2026-primary"
CURRENT_BUNDLE_ID = "wa-2026-primary-release"
COMMIT = "a" * 40
PANEL_HASH = "b" * 64


def _published_election() -> dict[str, str]:
    return {
        "election_id": CURRENT_ID,
        "bundle_id": CURRENT_BUNDLE_ID,
        "release_version": "primary.2",
        "source_panel_id": "test-panel-v2",
        "source_panel_hash": PANEL_HASH,
    }


def _deployed_election() -> dict[str, str]:
    return {
        "election_id": CURRENT_ID,
        "bundle_id": CURRENT_BUNDLE_ID,
        "release_version": "primary.2",
        "git_commit": COMMIT,
        "source_panel_id": "test-panel-v2",
        "source_panel_hash": PANEL_HASH,
        "release_manifest_sha256": "d" * 64,
    }


@pytest.mark.parametrize(
    "invalid_origin",
    [
        "not-an-origin",
        "http://seattleelections.guide",
        "https://:",
        "https://seattleelections.guide:bad",
        "https://user:password@seattleelections.guide",
        "https://seattleelections.guide/e/",
        "https://seattleelections.guide?current=1",
        "https://seattleelections.guide#current",
    ],
)
def test_manifests_reject_noncanonical_origins(invalid_origin: str) -> None:
    site = {
        "schema_version": "1.0",
        "canonical_origin": invalid_origin,
        "current_election_id": CURRENT_ID,
        "elections": [_published_election()],
    }
    deployment = {
        "schema_version": "2.0",
        "canonical_origin": invalid_origin,
        "current_election_id": CURRENT_ID,
        "elections": [_deployed_election()],
        "assets": {"e/index.html": "e" * 64},
    }

    with pytest.raises(ValueError):
        SiteManifest.model_validate(site)
    with pytest.raises(ValueError):
        DeploymentManifest.model_validate(deployment)


@pytest.mark.parametrize(
    "invalid_path",
    [
        "",
        ".",
        "/absolute",
        "../escape",
        "e/../escape",
        r"e\guide.pdf",
        r"..\escape",
        "deployment-manifest.json",
    ],
)
def test_deployment_manifest_rejects_noncanonical_asset_paths(invalid_path: str) -> None:
    with pytest.raises(ValueError, match="invalid asset paths"):
        DeploymentManifest.model_validate(
            {
                "schema_version": "2.0",
                "canonical_origin": "https://seattleelections.guide",
                "current_election_id": CURRENT_ID,
                "elections": [_deployed_election()],
                "assets": {invalid_path: "e" * 64},
            }
        )
