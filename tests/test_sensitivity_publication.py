from __future__ import annotations

import csv
import hashlib
import io
import json
from pathlib import Path

import pytest

from election_guide.publication import build_publication_bundle
from election_guide.publication.builder import _validate_publication  # pyright: ignore[reportPrivateUsage]
from election_guide.publication.models import PublicationViewModel
from election_guide.publication.sensitivity import sensitivity_scenarios_csv
from election_guide.release.comparison import verify_release_bundle_artifacts
from election_guide.release.models import (
    REQUIRED_RELEASE_ARTIFACTS,
    UNHASHED_RASTERIZED_ARTIFACTS,
    ReleaseManifest,
    ReleaseStatus,
)
from election_guide.scoring import score_dataset
from election_guide.scoring.sensitivity import build_sensitivity_report, validate_sensitivity_report
from election_guide.scoring.sensitivity_models import SensitivityReport
from election_guide.serialization import canonical_json_bytes
from tests.sensitivity_fixtures import synthetic_dataset
from tests.test_publication import _snapshot_store  # pyright: ignore[reportPrivateUsage]
from tests.test_scoring import NOW, _configuration  # pyright: ignore[reportPrivateUsage]


def test_publication_sidecars_reconcile_with_summary_and_display(tmp_path: Path) -> None:
    dataset = synthetic_dataset(tmp_path, [(2, 1)])
    consensus = score_dataset(dataset, _configuration(), computed_at=NOW)
    bundle = build_publication_bundle(
        dataset, consensus, git_commit="fixture", snapshot_root=_snapshot_store(tmp_path, dataset)
    )
    report = SensitivityReport.model_validate_json(bundle.artifacts["sensitivity.json"])
    validate_sensitivity_report(report, dataset, consensus)
    assert bundle.artifacts["consensus.json"] == canonical_json_bytes(
        consensus.model_dump(mode="json")
    )
    assert bundle.view_model.schema_version == "1.15"
    race = bundle.view_model.sections[0].races[0]
    assert race.sensitivity is not None
    assert race.sensitivity.warning == report.races[0].warning
    assert len(race.sensitivity.scenarios) == 3
    assert "baseline" not in race.sensitivity.model_dump(mode="json")
    rows = list(csv.DictReader(io.StringIO(bundle.artifacts["sensitivity_scenarios.csv"].decode())))
    assert len(rows) == 3
    assert json.loads(rows[0]["baseline"]) == report.races[0].baseline.model_dump(mode="json")
    assert json.loads(rows[0]["after"]) == report.races[0].scenarios[0].after.model_dump(
        mode="json"
    )
    assert json.loads(rows[0]["delta"]) == report.races[0].scenarios[0].delta.model_dump(
        mode="json"
    )
    summary = next(csv.DictReader(io.StringIO(bundle.artifacts["race_summary.csv"].decode())))
    assert summary["sensitivity_classification"] == "source_sensitive"
    assert summary["sensitivity_tested_count"] == "3"
    assert summary["sensitivity_policy_id"] == "source-panel-sensitivity-v1"
    altered = bundle.view_model.model_copy(deep=True)
    display = altered.sections[0].races[0].sensitivity
    assert display is not None
    display.classification = "stable"
    display.warning = None
    assert not next(
        c for c in _validate_publication(dataset, consensus, altered) if c.id == "sensitivity"
    ).passed


def test_empty_suite_csv_retains_headers_and_null_scalar_is_blank(tmp_path: Path) -> None:
    empty = synthetic_dataset(tmp_path / "empty", [], missing_sources=1)
    report = build_sensitivity_report(
        empty, score_dataset(empty, _configuration(), computed_at=NOW), git_commit="fixture"
    )
    text = sensitivity_scenarios_csv(report).decode()
    assert "leading_share_delta" in text
    assert len(text.splitlines()) == 1
    one = synthetic_dataset(tmp_path / "one", [(1, 0)])
    report = build_sensitivity_report(
        one, score_dataset(one, _configuration(), computed_at=NOW), git_commit="fixture"
    )
    row = next(csv.DictReader(io.StringIO(sensitivity_scenarios_csv(report).decode())))
    assert row["after_leading_share"] == ""
    assert row["leading_share_delta"] == ""


def test_new_schema_requires_sensitivity_but_historical_schema_reads_without_it(
    tmp_path: Path,
) -> None:
    dataset = synthetic_dataset(tmp_path, [(2, 1)])
    consensus = score_dataset(dataset, _configuration(), computed_at=NOW)
    bundle = build_publication_bundle(
        dataset, consensus, git_commit="fixture", snapshot_root=_snapshot_store(tmp_path, dataset)
    )
    payload = bundle.view_model.model_dump(mode="json")
    payload["sections"][0]["races"][0].pop("sensitivity")
    with pytest.raises(ValueError, match="requires sensitivity"):
        PublicationViewModel.model_validate(payload)
    payload["schema_version"] = "1.14"
    payload["methodology"].pop("sensitivity_policy")
    payload["metadata"].pop("sensitivity_report_hash")
    historical = PublicationViewModel.model_validate(payload)
    assert historical.sections[0].races[0].sensitivity is None


@pytest.mark.parametrize("missing", ["sensitivity.json", "sensitivity_scenarios.csv"])
def test_release_requires_sidecars_even_after_inventories_are_rewritten(
    tmp_path: Path, missing: str
) -> None:
    dataset = synthetic_dataset(tmp_path / "inputs", [(2, 1)])
    consensus = score_dataset(dataset, _configuration(), computed_at=NOW)
    bundle = build_publication_bundle(
        dataset,
        consensus,
        git_commit="f" * 40,
        snapshot_root=_snapshot_store(tmp_path / "inputs", dataset),
    )
    root = tmp_path / "release"
    included = sorted(
        REQUIRED_RELEASE_ARTIFACTS
        | {f"data/{name}" for name in bundle.artifacts}
        | {"guide/test.html", *UNHASHED_RASTERIZED_ARTIFACTS}
    )
    for relative in included:
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"")
    for name, content in bundle.artifacts.items():
        (root / "data" / name).write_bytes(content)
    (root / "data/canonical-dataset.json").write_bytes(
        canonical_json_bytes(dataset.model_dump(mode="json"))
    )
    metadata = bundle.view_model.metadata
    status = ReleaseStatus.model_validate(
        {
            "schema_version": "1.3",
            "release_version": "test",
            "election_id": metadata.election_id,
            "source_panel_id": metadata.source_panel_id,
            "source_panel_hash": metadata.source_panel_hash,
            "source_registry_hash": metadata.source_registry_hash,
            "data_as_of": NOW,
            "generated_at": NOW,
            "git_commit": "f" * 40,
            "source_count": 4,
            "captured_source_count": 3,
            "displayed_endorsement_count": 3,
            "unresolved_review_count": 0,
            "unresolved_high_severity_count": 0,
            "restricted_capture_count": 0,
            "source_access_failures": [],
            "incomplete_races": [],
            "validation_reports": {"publication": True, "rendering": True},
            "guide_html_artifact": "guide/test.html",
            "included_artifacts": included,
            "warnings": [],
        }
    )
    manifest = ReleaseManifest.model_validate(
        {
            "schema_version": "1.3",
            "release_version": "test",
            "source_panel_id": metadata.source_panel_id,
            "source_panel_hash": metadata.source_panel_hash,
            "source_registry_hash": metadata.source_registry_hash,
            "generated_at": NOW,
            "artifact_hashes": {
                relative: hashlib.sha256((root / relative).read_bytes()).hexdigest()
                for relative in included
                if relative not in {"release-manifest.json", *UNHASHED_RASTERIZED_ARTIFACTS}
            },
            "unhashed_artifacts": sorted(UNHASHED_RASTERIZED_ARTIFACTS),
        }
    )
    verify_release_bundle_artifacts(root, status=status, manifest=manifest)
    relative = f"data/{missing}"
    (root / relative).unlink()
    status = status.model_copy(
        update={"included_artifacts": [p for p in included if p != relative]}
    )
    manifest = manifest.model_copy(
        update={
            "artifact_hashes": {p: h for p, h in manifest.artifact_hashes.items() if p != relative}
        }
    )
    with pytest.raises(ValueError, match="requires sensitivity artifacts"):
        verify_release_bundle_artifacts(root, status=status, manifest=manifest)
