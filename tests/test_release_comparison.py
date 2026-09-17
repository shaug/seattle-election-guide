"""Release-bundle comparison tests for complete source-input identity."""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from pathlib import Path

import pytest

from election_guide.release.comparison import verify_release_bundle_artifacts
from election_guide.release.models import (
    REQUIRED_RELEASE_ARTIFACTS,
    UNHASHED_RASTERIZED_ARTIFACTS,
    ReleaseManifest,
    ReleaseStatus,
)


def test_release_verifier_reports_complete_input_drift_when_panel_hashes_match(
    tmp_path: Path,
) -> None:
    included_artifacts = sorted(
        REQUIRED_RELEASE_ARTIFACTS
        | {
            "guide/test-guide.html",
            *UNHASHED_RASTERIZED_ARTIFACTS,
        }
    )
    hashed_artifacts = set(included_artifacts) - {
        "release-manifest.json",
        *UNHASHED_RASTERIZED_ARTIFACTS,
    }
    artifact_hashes: dict[str, str] = {}
    for relative in sorted(hashed_artifacts):
        path = tmp_path / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"")
        artifact_hashes[relative] = hashlib.sha256(b"").hexdigest()
    for relative in sorted(UNHASHED_RASTERIZED_ARTIFACTS):
        path = tmp_path / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"")

    status = ReleaseStatus.model_validate(
        {
            "schema_version": "1.3",
            "release_version": "test",
            "election_id": "wa-2026-primary",
            "source_panel_id": "test-panel-v2",
            "source_panel_hash": "a" * 64,
            "source_registry_hash": "c" * 64,
            "data_as_of": datetime(2026, 7, 20, 10, tzinfo=UTC),
            "generated_at": datetime(2026, 8, 5, 0, 20, tzinfo=UTC),
            "git_commit": "b" * 40,
            "source_count": 1,
            "captured_source_count": 1,
            "displayed_endorsement_count": 1,
            "unresolved_review_count": 0,
            "unresolved_high_severity_count": 0,
            "restricted_capture_count": 0,
            "source_access_failures": [],
            "incomplete_races": [],
            "validation_reports": {"publication": True, "rendering": True},
            "guide_html_artifact": "guide/test-guide.html",
            "included_artifacts": included_artifacts,
            "warnings": [],
        }
    )
    manifest = ReleaseManifest.model_validate(
        {
            "schema_version": "1.3",
            "release_version": "test",
            "source_panel_id": "test-panel-v2",
            "source_panel_hash": "a" * 64,
            "source_registry_hash": "d" * 64,
            "generated_at": datetime(2026, 8, 5, 0, 20, tzinfo=UTC),
            "artifact_hashes": artifact_hashes,
            "unhashed_artifacts": sorted(UNHASHED_RASTERIZED_ARTIFACTS),
        }
    )

    with pytest.raises(ValueError, match="complete source registry hashes differ"):
        verify_release_bundle_artifacts(tmp_path, status=status, manifest=manifest)
