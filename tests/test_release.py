"""Release compilation, audit, and packaging tests."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from zipfile import ZipFile

import pytest
import yaml

import election_guide.release.builder as release_builder
from election_guide.normalization.models import CanonicalDataset
from election_guide.release import (
    build_release,
    compile_release_dataset,
    verify_release_compilation,
)
from election_guide.release.models import REQUIRED_RELEASE_ARTIFACTS, ReleaseStatus
from election_guide.serialization import read_json

PROJECT_ROOT = Path(__file__).parents[1]
INVENTORY = PROJECT_ROOT / "data/normalized/wa-2026-primary-inventory.json"
REGISTRY = PROJECT_ROOT / "config/sources/default.yaml"
SCORING = PROJECT_ROOT / "config/scoring/default.yaml"
RENDERING = PROJECT_ROOT / "config/rendering/pdf.yaml"
GENERATED_AT = datetime(2026, 7, 23, 17, 15, tzinfo=UTC)


def test_release_compiler_builds_permitted_provenance_and_resolves_multi_pick(
    tmp_path: Path,
) -> None:
    ledger = _write_ledger(tmp_path)
    dataset_path = tmp_path / "canonical-dataset.json"
    snapshots = tmp_path / "snapshots"
    manifests = tmp_path / "manifests"

    first = compile_release_dataset(
        ledger,
        INVENTORY,
        REGISTRY,
        dataset_path,
        snapshots,
        manifests,
    )
    first_bytes = dataset_path.read_bytes()
    second = compile_release_dataset(
        ledger,
        INVENTORY,
        REGISTRY,
        dataset_path,
        snapshots,
        manifests,
    )

    assert first == second
    assert dataset_path.read_bytes() == first_bytes
    assert len(first.captures) == 2
    assert all(capture.redistribution == "permitted" for capture in first.captures)
    assert len(list(snapshots.glob("sha256/*/*"))) == 2
    assert len(list(manifests.glob("*.json"))) == 2
    assert len(first.endorsements) == 2
    assert {endorsement.reviewed_at for endorsement in first.endorsements} == {
        datetime(2026, 7, 20, 9, 30, tzinfo=UTC)
    }
    assert (
        next(claim for claim in first.claims if claim.source_id == "the-stranger").evidence_excerpt
        is None
    )
    assert len(first.review_items) == len(first.review_decisions) == 1
    assert not (
        {item.id for item in first.review_items}
        - {d.review_item_id for d in first.review_decisions}
    )
    CanonicalDataset.model_validate(read_json(dataset_path))
    verified = verify_release_compilation(
        ledger,
        INVENTORY,
        REGISTRY,
        dataset_path,
        snapshots,
        manifests,
    )
    assert verified == first

    tracked_manifest = next(manifests.glob("*.json"))
    tracked_manifest.write_bytes(tracked_manifest.read_bytes() + b" ")
    with pytest.raises(ValueError, match="differs from compilation"):
        verify_release_compilation(
            ledger,
            INVENTORY,
            REGISTRY,
            dataset_path,
            snapshots,
            manifests,
        )


def test_release_compiler_preserves_review_history_when_data_cutoff_advances(
    tmp_path: Path,
) -> None:
    ledger_payload = _ledger_payload()
    ledger = tmp_path / "release-ledger.yaml"
    ledger.write_text(yaml.safe_dump(ledger_payload, sort_keys=False), encoding="utf-8")
    first = compile_release_dataset(
        ledger,
        INVENTORY,
        REGISTRY,
        tmp_path / "dataset.json",
        tmp_path / "snapshots",
        tmp_path / "manifests",
    )

    ledger_payload["data_as_of"] = "2026-07-21T10:00:00Z"
    ledger.write_text(yaml.safe_dump(ledger_payload, sort_keys=False), encoding="utf-8")
    second = compile_release_dataset(
        ledger,
        INVENTORY,
        REGISTRY,
        tmp_path / "dataset.json",
        tmp_path / "snapshots",
        tmp_path / "manifests",
    )

    assert second == first


def test_release_compiler_rejects_decisions_outside_source_eligibility(tmp_path: Path) -> None:
    ledger = _ledger_payload()
    source = ledger["sources"][0]
    source["source_id"] = "32nd-district-democrats"
    source["captured_at"] = "2026-07-20T14:00:34Z"
    source["reviewed_at"] = "2026-07-20T14:05:00Z"
    source["decisions"][0]["race_id"] = "ld-11-state-representative-1"
    source["decisions"][0]["candidate_ids"] = ["ld-11-state-representative-1--david-hackney"]
    ledger["data_as_of"] = "2026-07-20T14:05:00Z"
    ledger_path = tmp_path / "invalid.yaml"
    ledger_path.write_text(yaml.safe_dump(ledger, sort_keys=False), encoding="utf-8")

    with pytest.raises(ValueError, match="outside eligibility"):
        compile_release_dataset(
            ledger_path,
            INVENTORY,
            REGISTRY,
            tmp_path / "dataset.json",
            tmp_path / "snapshots",
            tmp_path / "manifests",
        )


@pytest.mark.parametrize("failed_target", ["snapshots", "manifests", "dataset"])
def test_release_compiler_rolls_back_every_output_when_publication_fails(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    failed_target: str,
) -> None:
    ledger = _write_ledger(tmp_path)
    dataset_path = tmp_path / "canonical-dataset.json"
    snapshots = tmp_path / "snapshots"
    manifests = tmp_path / "manifests"
    compile_release_dataset(ledger, INVENTORY, REGISTRY, dataset_path, snapshots, manifests)
    expected_dataset = dataset_path.read_bytes()
    expected_snapshots = _tree_bytes(snapshots)
    expected_manifests = _tree_bytes(manifests)

    changed = _ledger_payload()
    changed["sources"][0]["evidence_locator"] = "Changed official locator."
    ledger.write_text(yaml.safe_dump(changed, sort_keys=False), encoding="utf-8")
    targets = {
        "snapshots": snapshots,
        "manifests": manifests,
        "dataset": dataset_path,
    }
    target = targets[failed_target]
    real_replace = __import__("os").replace
    failed = False

    def fail_one_publish(source: Path | str, destination: Path | str) -> None:
        nonlocal failed
        if Path(destination) == target and not failed:
            failed = True
            raise OSError("injected publication failure")
        real_replace(source, destination)

    monkeypatch.setattr("election_guide.release.compiler.os.replace", fail_one_publish)
    with pytest.raises(OSError, match="injected publication failure"):
        compile_release_dataset(ledger, INVENTORY, REGISTRY, dataset_path, snapshots, manifests)

    assert failed
    assert dataset_path.read_bytes() == expected_dataset
    assert _tree_bytes(snapshots) == expected_snapshots
    assert _tree_bytes(manifests) == expected_manifests


def test_release_compiler_rolls_back_when_second_output_backup_fails(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ledger = _write_ledger(tmp_path)
    dataset_path = tmp_path / "canonical-dataset.json"
    snapshots = tmp_path / "snapshots"
    manifests = tmp_path / "manifests"
    compile_release_dataset(ledger, INVENTORY, REGISTRY, dataset_path, snapshots, manifests)
    expected_dataset = dataset_path.read_bytes()
    expected_snapshots = _tree_bytes(snapshots)
    expected_manifests = _tree_bytes(manifests)
    real_replace = __import__("os").replace
    failed = False

    def fail_manifest_backup(source: Path | str, destination: Path | str) -> None:
        nonlocal failed
        destination_path = Path(destination)
        if destination_path.name.startswith(".manifests.previous-") and not failed:
            failed = True
            raise OSError("injected backup failure")
        real_replace(source, destination)

    monkeypatch.setattr("election_guide.release.compiler.os.replace", fail_manifest_backup)
    with pytest.raises(OSError, match="injected backup failure"):
        compile_release_dataset(ledger, INVENTORY, REGISTRY, dataset_path, snapshots, manifests)

    assert failed
    assert dataset_path.read_bytes() == expected_dataset
    assert _tree_bytes(snapshots) == expected_snapshots
    assert _tree_bytes(manifests) == expected_manifests


def test_release_compiler_rolls_back_prior_outputs_when_current_restore_also_fails(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ledger = _write_ledger(tmp_path)
    dataset_path = tmp_path / "canonical-dataset.json"
    snapshots = tmp_path / "snapshots"
    manifests = tmp_path / "manifests"
    compile_release_dataset(ledger, INVENTORY, REGISTRY, dataset_path, snapshots, manifests)
    expected_dataset = dataset_path.read_bytes()
    expected_snapshots = _tree_bytes(snapshots)
    expected_manifests = _tree_bytes(manifests)
    changed = _ledger_payload()
    changed["sources"][0]["evidence_locator"] = "Changed official locator."
    ledger.write_text(yaml.safe_dump(changed, sort_keys=False), encoding="utf-8")
    real_replace = __import__("os").replace
    publish_failed = False

    def fail_publish_and_restore(source: Path | str, destination: Path | str) -> None:
        nonlocal publish_failed
        source_path = Path(source)
        destination_path = Path(destination)
        if source_path.name == "manifests" and destination_path == manifests:
            publish_failed = True
            raise OSError("injected manifest publication failure")
        if source_path.name.startswith(".manifests.previous-") and destination_path == manifests:
            raise OSError("injected manifest restore failure")
        real_replace(source, destination)

    monkeypatch.setattr("election_guide.release.compiler.os.replace", fail_publish_and_restore)
    with pytest.raises(OSError, match="recovery was incomplete"):
        compile_release_dataset(ledger, INVENTORY, REGISTRY, dataset_path, snapshots, manifests)

    assert publish_failed
    assert dataset_path.read_bytes() == expected_dataset
    assert _tree_bytes(snapshots) == expected_snapshots
    assert not manifests.exists()
    manifest_backup = next(tmp_path.glob(".manifests.previous-*"))
    assert _tree_bytes(manifest_backup) == expected_manifests
    monkeypatch.undo()

    with pytest.raises(OSError, match="unrecovered backups"):
        compile_release_dataset(ledger, INVENTORY, REGISTRY, dataset_path, snapshots, manifests)

    assert dataset_path.read_bytes() == expected_dataset
    assert _tree_bytes(snapshots) == expected_snapshots
    assert not manifests.exists()
    assert _tree_bytes(manifest_backup) == expected_manifests


def test_release_compiler_continues_rollback_after_middle_restore_fails(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ledger = _write_ledger(tmp_path)
    dataset_path = tmp_path / "canonical-dataset.json"
    snapshots = tmp_path / "snapshots"
    manifests = tmp_path / "manifests"
    compile_release_dataset(ledger, INVENTORY, REGISTRY, dataset_path, snapshots, manifests)
    expected_dataset = dataset_path.read_bytes()
    expected_snapshots = _tree_bytes(snapshots)
    expected_manifests = _tree_bytes(manifests)
    changed = _ledger_payload()
    changed["sources"][0]["evidence_locator"] = "Changed official locator."
    ledger.write_text(yaml.safe_dump(changed, sort_keys=False), encoding="utf-8")
    real_replace = __import__("os").replace
    dataset_publish_failed = False

    def fail_dataset_publish_and_manifest_restore(
        source: Path | str, destination: Path | str
    ) -> None:
        nonlocal dataset_publish_failed
        source_path = Path(source)
        destination_path = Path(destination)
        if source_path.name == dataset_path.name and destination_path == dataset_path:
            dataset_publish_failed = True
            raise OSError("injected dataset publication failure")
        if source_path.name.startswith(".manifests.previous-") and destination_path == manifests:
            raise OSError("injected manifest rollback failure")
        real_replace(source, destination)

    monkeypatch.setattr(
        "election_guide.release.compiler.os.replace",
        fail_dataset_publish_and_manifest_restore,
    )
    with pytest.raises(OSError, match="recovery was incomplete"):
        compile_release_dataset(ledger, INVENTORY, REGISTRY, dataset_path, snapshots, manifests)

    assert dataset_publish_failed
    assert dataset_path.read_bytes() == expected_dataset
    assert _tree_bytes(snapshots) == expected_snapshots
    assert not manifests.exists()
    manifest_backup = next(tmp_path.glob(".manifests.previous-*"))
    assert _tree_bytes(manifest_backup) == expected_manifests


def test_release_build_packages_complete_deterministic_public_bundle(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ledger = _write_ledger(tmp_path)
    dataset_path = tmp_path / "canonical-dataset.json"
    snapshots = tmp_path / "snapshots"
    compile_release_dataset(
        ledger,
        INVENTORY,
        REGISTRY,
        dataset_path,
        snapshots,
        tmp_path / "manifests",
    )

    def fake_render(
        view_model_path: Path,
        config_path: Path,
        output_dir: Path,
        **_: object,
    ) -> SimpleNamespace:
        assert view_model_path.is_file()
        assert config_path == RENDERING
        pdf_dir = output_dir / "pdf"
        pdf_dir.mkdir(parents=True)
        html = output_dir / "seattle-2026-primary-guide.html"
        pdf = pdf_dir / "Seattle_2026_Primary_Endorsement_Guide.pdf"
        detailed_pdf = pdf_dir / "Seattle_2026_Primary_Endorsement_Guide_Detailed.pdf"
        page = pdf_dir / "pages/page-1.png"
        detailed_page = pdf_dir / "detailed-pages/page-1.png"
        screenshot = output_dir / "screenshots/desktop.png"
        validation = output_dir / "rendering_validation_report.json"
        page.parent.mkdir(parents=True)
        detailed_page.parent.mkdir(parents=True)
        screenshot.parent.mkdir(parents=True)
        html.write_text("<!doctype html><title>Guide</title>", encoding="utf-8")
        pdf.write_bytes(b"%PDF-1.7\nrelease fixture\n")
        detailed_pdf.write_bytes(b"%PDF-1.7\ndetailed release fixture\n")
        page.write_bytes(b"concise page")
        detailed_page.write_bytes(b"detailed page")
        screenshot.write_bytes(b"desktop screenshot")
        validation.write_text('{"passed":true}\n', encoding="utf-8")
        return SimpleNamespace(
            html_path=html,
            pdf_path=pdf,
            detailed_pdf_path=detailed_pdf,
            validation_path=validation,
            page_images=[page],
            detailed_page_images=[detailed_page],
            screenshots=[screenshot],
            validation_report=SimpleNamespace(passed=True, edition="concise_plus_detailed"),
        )

    def accept_test_checkout(_: str) -> None:
        return None

    monkeypatch.setattr("election_guide.release.builder.build_rendered_guide", fake_render)
    monkeypatch.setattr(
        "election_guide.release.builder._verify_checkout_identity", accept_test_checkout
    )
    output = tmp_path / "release"
    first = build_release(
        ledger_path=ledger,
        inventory_path=INVENTORY,
        registry_path=REGISTRY,
        dataset_path=dataset_path,
        scoring_config_path=SCORING,
        rendering_config_path=RENDERING,
        snapshot_root=snapshots,
        manifest_dir=tmp_path / "manifests",
        output_dir=output,
        release_version="2026-primary.1",
        generated_at=GENERATED_AT,
        git_commit="a" * 40,
    )
    first_hash = hashlib.sha256(first.archive_path.read_bytes()).hexdigest()
    second = build_release(
        ledger_path=ledger,
        inventory_path=INVENTORY,
        registry_path=REGISTRY,
        dataset_path=dataset_path,
        scoring_config_path=SCORING,
        rendering_config_path=RENDERING,
        snapshot_root=snapshots,
        manifest_dir=tmp_path / "manifests",
        output_dir=output,
        release_version="2026-primary.1",
        generated_at=GENERATED_AT,
        git_commit="a" * 40,
    )

    assert hashlib.sha256(second.archive_path.read_bytes()).hexdigest() == first_hash
    assert second.status.validation_reports == {"publication": True, "rendering": True}
    assert second.status.restricted_capture_count == 0
    assert second.status.unresolved_high_severity_count == 0
    assert second.status.source_access_failures
    with ZipFile(second.archive_path) as archive:
        names = set(archive.namelist())
    assert "seattle-election-guide/RELEASE_NOTES.md" in names
    assert "seattle-election-guide/release-status.json" in names
    assert "seattle-election-guide/release-manifest.json" in names
    assert "seattle-election-guide/data/canonical-dataset.json" in names
    assert "seattle-election-guide/data/consensus.json" in names
    assert "seattle-election-guide/guide/Seattle_2026_Primary_Endorsement_Guide.pdf" in names
    assert "seattle-election-guide/validation/rendering/pdf/pages/page-1.png" in names
    assert "seattle-election-guide/validation/rendering/screenshots/desktop.png" in names

    release_manifest = json.loads(
        (second.bundle_dir / "release-manifest.json").read_text(encoding="utf-8")
    )
    assert "release-status.json" in release_manifest["artifact_hashes"]
    assert "RELEASE_NOTES.md" in release_manifest["artifact_hashes"]


@pytest.mark.parametrize(
    ("update", "message"),
    [
        ({"source_count": 0}, "at least one active source"),
        ({"captured_source_count": 999}, "cannot exceed"),
        ({"displayed_endorsement_count": 0}, "at least one displayed"),
        ({"unresolved_review_count": 0, "unresolved_high_severity_count": 1}, "cannot exceed"),
        ({"generated_at": datetime(2026, 7, 19, tzinfo=UTC)}, "cannot predate"),
        ({"validation_reports": {"invented": True}}, "not canonical"),
        ({"included_artifacts": []}, "missing rendered guide artifacts"),
        (
            {"detailed_guide_pdf_artifact": "guide/custom-guide.pdf"},
            "must be distinct",
        ),
    ],
)
def test_release_status_rejects_vacuous_or_inconsistent_audit_claims(
    update: dict[str, object],
    message: str,
) -> None:
    valid = {
        "release_version": "test",
        "election_id": "wa-2026-primary",
        "source_panel_id": "test-panel-v2",
        "source_panel_hash": "b" * 64,
        "data_as_of": datetime(2026, 7, 20, 10, tzinfo=UTC),
        "generated_at": GENERATED_AT,
        "git_commit": "a" * 40,
        "source_count": 2,
        "captured_source_count": 2,
        "displayed_endorsement_count": 2,
        "unresolved_review_count": 0,
        "unresolved_high_severity_count": 0,
        "restricted_capture_count": 0,
        "source_access_failures": [],
        "incomplete_races": [],
        "validation_reports": {"publication": True, "rendering": True},
        "rendering_edition": "concise_plus_detailed",
        "guide_html_artifact": "guide/custom-guide.html",
        "guide_pdf_artifact": "guide/custom-guide.pdf",
        "detailed_guide_pdf_artifact": "guide/custom-guide-detailed.pdf",
        "included_artifacts": sorted(
            REQUIRED_RELEASE_ARTIFACTS
            | {
                "guide/custom-guide.html",
                "guide/custom-guide.pdf",
                "guide/custom-guide-detailed.pdf",
                "validation/rendering/pdf/pages/page-1.png",
                "validation/rendering/pdf/detailed-pages/page-1.png",
                "validation/rendering/screenshots/desktop.png",
            }
        ),
        "warnings": [],
    }
    with pytest.raises(ValueError, match=message):
        ReleaseStatus.model_validate(valid | update)


def test_release_status_accepts_configured_concise_only_guide_artifacts() -> None:
    status = ReleaseStatus.model_validate(
        {
            "release_version": "test",
            "election_id": "wa-2026-primary",
            "source_panel_id": "test-panel-v2",
            "source_panel_hash": "b" * 64,
            "data_as_of": datetime(2026, 7, 20, 10, tzinfo=UTC),
            "generated_at": GENERATED_AT,
            "git_commit": "a" * 40,
            "source_count": 2,
            "captured_source_count": 2,
            "displayed_endorsement_count": 2,
            "unresolved_review_count": 0,
            "unresolved_high_severity_count": 0,
            "restricted_capture_count": 0,
            "source_access_failures": [],
            "incomplete_races": [],
            "validation_reports": {"publication": True, "rendering": True},
            "rendering_edition": "concise",
            "guide_html_artifact": "guide/alternate.html",
            "guide_pdf_artifact": "guide/alternate.pdf",
            "detailed_guide_pdf_artifact": None,
            "included_artifacts": sorted(
                REQUIRED_RELEASE_ARTIFACTS
                | {
                    "guide/alternate.html",
                    "guide/alternate.pdf",
                    "validation/rendering/pdf/pages/page-1.png",
                    "validation/rendering/screenshots/mobile.png",
                }
            ),
            "warnings": [],
        }
    )

    assert status.rendering_edition == "concise"


@pytest.mark.parametrize(
    ("commit", "status", "message"),
    [
        ("a" * 40, "", "does not match checkout HEAD"),
        ("b" * 40, " M tracked-file\n", "requires a clean Git checkout"),
    ],
)
def test_release_build_rejects_false_or_dirty_checkout_identity(
    monkeypatch: pytest.MonkeyPatch,
    commit: str,
    status: str,
    message: str,
) -> None:
    def fake_run(command: list[str], **_: object) -> SimpleNamespace:
        output = "b" * 40 if command[1:3] == ["rev-parse", "HEAD"] else status
        return SimpleNamespace(stdout=output)

    monkeypatch.setattr(release_builder.subprocess, "run", fake_run)
    with pytest.raises(ValueError, match=message):
        release_builder._verify_checkout_identity(commit)  # pyright: ignore[reportPrivateUsage]


def _write_ledger(tmp_path: Path) -> Path:
    path = tmp_path / "release-ledger.yaml"
    path.write_text(yaml.safe_dump(_ledger_payload(), sort_keys=False), encoding="utf-8")
    return path


def _tree_bytes(root: Path) -> dict[str, bytes]:
    return {
        path.relative_to(root).as_posix(): path.read_bytes()
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


def _ledger_payload() -> dict[str, Any]:
    return {
        "schema_version": "1.0",
        "election_id": "wa-2026-primary",
        "data_as_of": "2026-07-20T10:00:00Z",
        "reviewer": "release-test",
        "review_note": "Verified against each official 2026 endorsement page.",
        "sources": [
            {
                "source_id": "the-stranger",
                "captured_at": "2026-07-20T09:00:00Z",
                "reviewed_at": "2026-07-20T09:30:00Z",
                "evidence_locator": "Official guide, named race entry.",
                "decisions": [
                    {
                        "race_id": "king-county-assessor",
                        "candidate_ids": ["king-county-assessor--rob-foxcurran"],
                        "evidence_locator": "Official guide, King County Assessor heading.",
                    }
                ],
            },
            {
                "source_id": "king-county-democrats",
                "captured_at": "2026-07-20T09:05:00Z",
                "reviewed_at": "2026-07-20T09:30:00Z",
                "evidence_locator": "Official endorsements, named office entry.",
                "decisions": [
                    {
                        "race_id": "ld-11-state-representative-1",
                        "candidate_ids": [
                            "ld-11-state-representative-1--ashley-fedan",
                            "ld-11-state-representative-1--david-hackney",
                        ],
                        "evidence_excerpt": (
                            "Ashley Fedan and David Hackney, LD 11 Representative Position 1"
                        ),
                        "evidence_locator": "Official endorsements, state offices list.",
                    }
                ],
            },
        ],
    }
