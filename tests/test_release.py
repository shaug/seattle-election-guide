"""Release compilation, audit, and packaging tests."""

from __future__ import annotations

import hashlib
import json
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from zipfile import ZipFile

import pytest
import yaml

import election_guide.release.builder as release_builder
from election_guide.evidence.models import CapturedManifest
from election_guide.normalization.models import CanonicalDataset
from election_guide.release import (
    ReleaseResult,
    build_release,
    compile_release_dataset,
    verify_release_compilation,
)
from election_guide.release.models import REQUIRED_RELEASE_ARTIFACTS, ReleaseStatus
from election_guide.serialization import read_json
from tests.test_corrections import _valid_corrections  # pyright: ignore[reportPrivateUsage]
from tests.test_results import _valid_results  # pyright: ignore[reportPrivateUsage]

PROJECT_ROOT = Path(__file__).parents[1]
INVENTORY = PROJECT_ROOT / "data/normalized/wa-2026-primary-inventory.json"
REGISTRY = PROJECT_ROOT / "config/sources/default.yaml"
SCORING = PROJECT_ROOT / "config/scoring/default.yaml"
RENDERING = PROJECT_ROOT / "config/rendering/guide.yaml"
COMMITTED_RELEASE_MANIFESTS = PROJECT_ROOT / "data/releases/wa-2026-primary/manifests"
GENERATED_AT = datetime(2026, 8, 5, 0, 20, tzinfo=UTC)


def test_release_compile_inside_a_repository_reproduces_committed_capture_ids(
    tmp_path: Path,
) -> None:
    """Compilation stages under `output_path.parent`, so its captures are
    written to an unignored in-repository path whenever an operator runs
    `release compile` at its documented default. Capture identity must not
    depend on that: `storage_scope` feeds the capture-ID fingerprint, so a
    scope derived from Git-trackedness rather than from the one official store
    would rewrite every already-committed release manifest, and `release
    verify` recompiles in a system temp directory outside any repository, where
    it could never notice (issue #357)."""
    repository = tmp_path / "repository"
    (repository / "data" / "normalized").mkdir(parents=True)
    subprocess.run(["git", "init", "--quiet", str(repository)], check=True)

    dataset = compile_release_dataset(
        PROJECT_ROOT / "data/releases/wa-2026-primary/source-decisions.yaml",
        INVENTORY,
        REGISTRY,
        repository / "data" / "normalized" / "canonical-dataset.json",
        repository / "snapshots",
        repository / "manifests",
    )

    committed = {path.name for path in COMMITTED_RELEASE_MANIFESTS.glob("*.json")}
    recompiled = {f"{capture.id}.json" for capture in dataset.captures}
    assert recompiled == committed
    scopes = {
        capture.storage_scope
        for capture in dataset.captures
        if isinstance(capture, CapturedManifest)
    }
    assert scopes == {"local_only"}


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
    ledger, dataset_path, snapshots = _compiled_release_inputs(tmp_path)
    _stub_release_render(monkeypatch)
    output = tmp_path / "release"
    first = _build_release(ledger, dataset_path, snapshots, tmp_path, output)
    first_hash = hashlib.sha256(first.archive_path.read_bytes()).hexdigest()
    second = _build_release(ledger, dataset_path, snapshots, tmp_path, output)

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
    assert "seattle-election-guide/guide/seattle-2026-primary-guide.html" in names
    assert "seattle-election-guide/validation/rendering/screenshots/desktop.png" in names
    # Issue 193: the release no longer carries a generated PDF edition.
    assert not any(name.endswith(".pdf") for name in names)

    release_manifest = json.loads(
        (second.bundle_dir / "release-manifest.json").read_text(encoding="utf-8")
    )
    assert "release-status.json" in release_manifest["artifact_hashes"]
    assert "RELEASE_NOTES.md" in release_manifest["artifact_hashes"]


def test_release_build_wires_a_committed_results_file_into_the_view_model(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Issue #283: the real release pipeline -- not only a direct
    `build_publication_bundle` call -- must load and attach a committed
    certified results file, or the rendering hook never reaches a published
    guide."""
    ledger, dataset_path, snapshots = _compiled_release_inputs(tmp_path)
    _stub_release_render(monkeypatch)

    results_dir, results_root = _committed_results(tmp_path)

    output = tmp_path / "release"
    release = _build_release(
        ledger,
        dataset_path,
        snapshots,
        tmp_path,
        output,
        results_dir=results_dir,
        repository_root=results_root,
    )

    published = json.loads(
        (release.bundle_dir / "data" / "publication_view_model.json").read_text(encoding="utf-8")
    )
    assert published["results"] is not None
    assert published["results"]["election_id"] == "wa-2026-primary"
    assert published["results"]["status"] == "certified"

    # The default `results_dir` (no committed file) leaves the release exactly
    # as it was before this hook existed.
    second_output = tmp_path / "release-without-results"
    without_results = _build_release(
        ledger,
        dataset_path,
        snapshots,
        tmp_path,
        second_output,
        results_dir=tmp_path / "no-such-results-directory",
    )
    published_without_results = json.loads(
        (without_results.bundle_dir / "data" / "publication_view_model.json").read_text(
            encoding="utf-8"
        )
    )
    assert published_without_results["results"] is None


def test_release_build_wires_the_certification_date_into_the_view_model(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Issue #285: the real release pipeline reads the declared calendar's
    `certification` milestone for this election and carries it into
    `PublicationMetadata.certification_date`, the same way `election_date`
    already reaches the view model -- so the banner's counting state can
    actually trigger for a real release, not only a direct
    `build_publication_bundle` call."""
    ledger, dataset_path, snapshots = _compiled_release_inputs(tmp_path)
    _stub_release_render(monkeypatch)

    # The real, committed calendar declares `wa-2026-primary`'s certification
    # 14 days after its election day (config/calendar/elections.yaml, RCW 29A.60.190).
    output = tmp_path / "release"
    release = _build_release(ledger, dataset_path, snapshots, tmp_path, output)
    published = json.loads(
        (release.bundle_dir / "data" / "publication_view_model.json").read_text(encoding="utf-8")
    )
    assert published["metadata"]["certification_date"] == "2026-08-18"

    # A calendar path that resolves to nothing -- missing entirely -- is a
    # silent no-op, matching `results_dir`'s own "no committed file" grace.
    second_output = tmp_path / "release-without-calendar"
    without_calendar = _build_release(
        ledger,
        dataset_path,
        snapshots,
        tmp_path,
        second_output,
        calendar_path=tmp_path / "no-such-calendar.yaml",
    )
    published_without_calendar = json.loads(
        (without_calendar.bundle_dir / "data" / "publication_view_model.json").read_text(
            encoding="utf-8"
        )
    )
    assert published_without_calendar["metadata"]["certification_date"] is None


def test_release_build_resolves_the_results_capture_url_into_the_view_model(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Issue #286: the real release pipeline reads the committed results
    file's own current capture (`results.current_results_capture`) and
    resolves its evidence manifest's `canonical_url`, carrying it into
    `PublicationMetadata.results_capture_url` -- so every candidate race's
    results-strip provenance line can link a real receipt, not only a direct
    `build_publication_bundle` call supplied one by hand."""
    ledger, dataset_path, snapshots = _compiled_release_inputs(tmp_path)
    _stub_release_render(monkeypatch)

    results_dir, results_root = _committed_results(tmp_path)

    output = tmp_path / "release"
    release = _build_release(
        ledger,
        dataset_path,
        snapshots,
        tmp_path,
        output,
        results_dir=results_dir,
        repository_root=results_root,
    )
    published = json.loads(
        (release.bundle_dir / "data" / "publication_view_model.json").read_text(encoding="utf-8")
    )
    assert published["metadata"]["results_capture_url"] == "https://example.org/results/certified"

    # The default `results_dir` (no committed file) leaves the release
    # exactly as it was before this parameter existed.
    second_output = tmp_path / "release-without-results"
    without_results = _build_release(
        ledger,
        dataset_path,
        snapshots,
        tmp_path,
        second_output,
        results_dir=tmp_path / "no-such-results-directory",
    )
    published_without_results = json.loads(
        (without_results.bundle_dir / "data" / "publication_view_model.json").read_text(
            encoding="utf-8"
        )
    )
    assert published_without_results["metadata"]["results_capture_url"] is None


def test_release_build_succeeds_with_a_real_results_capture_and_corrections_link(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Issue #353: `build_release`'s real rendering step -- not a stubbed one
    -- must actually succeed once a committed results file resolves a real
    capture URL and a committed corrections file is present, exactly the
    reproduction the issue walked through by hand
    (`election-guide evidence capture` + `results ingest` + `release build`).
    Before the fix, this failed with `release build failed: rendered guide
    validation failed: html-source-evidence: HTML source-detail rows are
    incomplete: document: unexpected or missing links`, because
    `validate_rendered_guide`'s own `expected_html_links` accounted for
    neither the results-strip provenance link (#286) nor the Corrections nav
    link (#290). Only checkout identity is stubbed here (no real Git commit
    backs this fixture); rendering runs for real, the same real Chromium path
    `test_chromium_build_is_semantically_faithful_and_visually_safe` proves
    elsewhere."""

    def accept_test_checkout(_: str) -> None:
        return None

    monkeypatch.setattr(release_builder, "_verify_checkout_identity", accept_test_checkout)
    ledger, dataset_path, snapshots = _compiled_release_inputs(tmp_path)
    results_dir, results_root = _committed_results(tmp_path)

    corrections_dir = tmp_path / "corrections"
    corrections_dir.mkdir()
    (corrections_dir / "wa-2026-primary.yaml").write_text(
        yaml.safe_dump(_valid_corrections().model_dump(mode="json")), encoding="utf-8"
    )

    output = tmp_path / "release"
    release = _build_release(
        ledger,
        dataset_path,
        snapshots,
        tmp_path,
        output,
        results_dir=results_dir,
        repository_root=results_root,
        corrections_dir=corrections_dir,
    )

    assert release.status.validation_reports == {"publication": True, "rendering": True}
    published = json.loads(
        (release.bundle_dir / "data" / "publication_view_model.json").read_text(encoding="utf-8")
    )
    capture_url = published["metadata"]["results_capture_url"]
    assert capture_url == "https://example.org/results/certified"
    guide_html = (release.bundle_dir / release.status.guide_html_artifact).read_text(
        encoding="utf-8"
    )
    assert f'href="{capture_url}"' in guide_html
    assert 'href="/e/wa-2026-primary/corrections/">Corrections</a>' in guide_html


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
        ({"guide_html_artifact": "guide/custom-guide.pdf"}, "invalid file types"),
        ({"guide_html_artifact": "elsewhere/custom-guide.html"}, "canonical paths under guide/"),
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
        "guide_html_artifact": "guide/custom-guide.html",
        "included_artifacts": sorted(
            REQUIRED_RELEASE_ARTIFACTS
            | {
                "guide/custom-guide.html",
                "guide/custom-guide.pdf",
                "validation/rendering/screenshots/desktop.png",
            }
        ),
        "warnings": [],
    }
    with pytest.raises(ValueError, match=message):
        ReleaseStatus.model_validate(valid | update)


def test_release_status_accepts_a_configured_html_guide_artifact() -> None:
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
            "guide_html_artifact": "guide/alternate.html",
            "included_artifacts": sorted(
                REQUIRED_RELEASE_ARTIFACTS
                | {
                    "guide/alternate.html",
                    "validation/rendering/screenshots/mobile.png",
                }
            ),
            "warnings": [],
        }
    )

    assert status.guide_html_artifact == "guide/alternate.html"


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


def _committed_results(tmp_path: Path) -> tuple[Path, Path]:
    """A committed certified results file under its own `results_dir`, ready
    for `build_release`'s `results_dir=`/`repository_root=` overrides: the
    results directory and its repository root."""
    results_root = tmp_path / "results-repository-root"
    results_dir = results_root / "data" / "results"
    results_dir.mkdir(parents=True)
    results = _valid_results(results_root)
    (results_dir / "wa-2026-primary.yaml").write_text(
        yaml.safe_dump(results.model_dump(mode="json")), encoding="utf-8"
    )
    return results_dir, results_root


def _compiled_release_inputs(tmp_path: Path) -> tuple[Path, Path, Path]:
    """A release ledger and a compiled canonical dataset ready for
    `build_release`: the ledger path, the dataset path, and the snapshot
    root every `build_release` test needs."""
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
    return ledger, dataset_path, snapshots


def _stub_release_render(monkeypatch: pytest.MonkeyPatch) -> None:
    """Stub the rendering and checkout-identity steps `build_release` calls,
    so a test can exercise the rest of the pipeline without a real browser or
    a real Git checkout."""

    def fake_render(
        view_model_path: Path,
        config_path: Path,
        output_dir: Path,
        **_: object,
    ) -> SimpleNamespace:
        assert view_model_path.is_file()
        assert config_path == RENDERING
        output_dir.mkdir(parents=True, exist_ok=True)
        html = output_dir / "seattle-2026-primary-guide.html"
        screenshot = output_dir / "screenshots/desktop.png"
        validation = output_dir / "rendering_validation_report.json"
        screenshot.parent.mkdir(parents=True)
        html.write_text("<!doctype html><title>Guide</title>", encoding="utf-8")
        screenshot.write_bytes(b"desktop screenshot")
        validation.write_text('{"passed":true}\n', encoding="utf-8")
        return SimpleNamespace(
            html_path=html,
            validation_path=validation,
            screenshots=[screenshot],
            validation_report=SimpleNamespace(passed=True),
        )

    def accept_test_checkout(_: str) -> None:
        return None

    monkeypatch.setattr("election_guide.release.builder.build_rendered_guide", fake_render)
    monkeypatch.setattr(
        "election_guide.release.builder._verify_checkout_identity", accept_test_checkout
    )


def _build_release(
    ledger: Path,
    dataset_path: Path,
    snapshots: Path,
    tmp_path: Path,
    output_dir: Path,
    **overrides: object,
) -> ReleaseResult:
    """One `build_release` call carrying this file's fixed test fixture
    arguments, varying only what each call site actually varies (`output_dir`
    plus whatever `overrides` supplies -- `results_dir`, `repository_root`,
    `calendar_path`)."""
    return build_release(
        ledger_path=ledger,
        inventory_path=INVENTORY,
        registry_path=REGISTRY,
        dataset_path=dataset_path,
        scoring_config_path=SCORING,
        rendering_config_path=RENDERING,
        snapshot_root=snapshots,
        manifest_dir=tmp_path / "manifests",
        output_dir=output_dir,
        release_version="2026-primary.1",
        generated_at=GENERATED_AT,
        git_commit="a" * 40,
        **overrides,  # type: ignore[arg-type]
    )


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
