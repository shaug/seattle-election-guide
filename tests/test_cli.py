import json
from datetime import UTC, datetime
from pathlib import Path

from typer.testing import CliRunner

from election_guide import __version__
from election_guide.cli import app
from election_guide.evidence.models import CaptureRequest
from election_guide.evidence.storage import read_capture_manifest, record_capture
from election_guide.inventory.importer import read_inventory
from election_guide.normalization.matching import match_claim
from election_guide.normalization.records import (
    new_extracted_claim,
    write_record,
    write_review_item,
)
from election_guide.sources.registry import read_source_registry

runner = CliRunner()


def test_help_lists_foundational_commands() -> None:
    result = runner.invoke(app, ["--help"])

    assert result.exit_code == 0
    assert "doctor" in result.stdout
    assert "evidence" in result.stdout
    assert "export" in result.stdout
    assert "inventory" in result.stdout
    assert "normalize" in result.stdout
    assert "review" in result.stdout
    assert "sources" in result.stdout
    assert "version" in result.stdout


def test_version_reports_package_version() -> None:
    result = runner.invoke(app, ["version"])

    assert result.exit_code == 0
    assert result.stdout.strip() == __version__


def test_doctor_accepts_repository_root() -> None:
    result = runner.invoke(app, ["doctor", "--project-root", "."])

    assert result.exit_code == 0
    assert result.stdout.strip() == "foundation: ok"


def test_sources_validate_reports_frozen_panel() -> None:
    result = runner.invoke(app, ["sources", "validate", "config/sources/default.yaml"])

    assert result.exit_code == 0
    assert result.stdout.startswith("source registry: valid (")


def test_sources_report_writes_document(tmp_path: Path) -> None:
    output = tmp_path / "report.md"
    result = runner.invoke(app, ["sources", "report", "--output", str(output)])

    assert result.exit_code == 0
    assert output.read_text(encoding="utf-8").startswith("# 2026 Primary Source Discovery Report")


def test_evidence_capture_and_verify_commands(tmp_path: Path) -> None:
    storage_root = tmp_path / "snapshots"
    manifest_dir = tmp_path / "manifests"
    fixture = Path("tests/fixtures/evidence/static.html")
    result = runner.invoke(
        app,
        [
            "evidence",
            "capture",
            str(fixture),
            "--source-id",
            "the-stranger",
            "--requested-url",
            "https://example.org/endorsements",
            "--canonical-url",
            "https://example.org/endorsements",
            "--retrieved-at",
            "2026-07-19T12:00:00Z",
            "--media-type",
            "text/html",
            "--title",
            "Fixture 2026 Primary Endorsements",
            "--capture-method",
            "static_html",
            "--http-status",
            "200",
            "--redistribution",
            "permitted",
            "--redistribution-note",
            "Original fixture content created for repository tests.",
            "--storage-root",
            str(storage_root),
            "--manifest-dir",
            str(manifest_dir),
        ],
    )

    assert result.exit_code == 0, result.output
    manifest = next(manifest_dir.glob("*.json"))
    verified = runner.invoke(
        app,
        [
            "evidence",
            "verify",
            str(manifest),
            "--storage-root",
            str(storage_root),
        ],
    )
    assert verified.exit_code == 0, verified.output
    assert "evidence: valid" in verified.stdout


def test_evidence_unavailable_command_writes_metadata_only_manifest(tmp_path: Path) -> None:
    manifest_dir = tmp_path / "manifests"
    result = runner.invoke(
        app,
        [
            "evidence",
            "unavailable",
            "--source-id",
            "seattle-times-editorial-board",
            "--requested-url",
            "https://www.seattletimes.com/opinion/editorials/",
            "--retrieved-at",
            "2026-07-19T12:00:00Z",
            "--http-status",
            "403",
            "--media-type",
            "text/html",
            "--unavailable-reason",
            "The official page denied unattended access.",
            "--redistribution-note",
            "No page content was retained or redistributed.",
            "--manifest-dir",
            str(manifest_dir),
        ],
    )

    assert result.exit_code == 0, result.output
    payload = next(manifest_dir.glob("*.json")).read_text(encoding="utf-8")
    assert '"availability": "unavailable"' in payload
    assert '"canonical_url": null' in payload
    assert "content_sha256" not in payload


def test_normalize_match_writes_a_safe_canonical_endorsement(tmp_path: Path) -> None:
    manifest_dir = tmp_path / "manifests"
    capture = read_capture_manifest(
        record_capture(
            CaptureRequest.model_validate(
                {
                    "source_id": "the-stranger",
                    "requested_url": "https://www.thestranger.com/endorsements/fixture",
                    "canonical_url": "https://www.thestranger.com/endorsements/fixture",
                    "retrieved_at": "2026-07-19T12:00:00Z",
                    "http_status": 200,
                    "media_type": "text/html",
                    "title": "Fixture endorsements",
                    "published_at": "2026-07-02",
                    "capture_method": "static_html",
                    "redistribution": "permitted",
                    "redistribution_note": "Repository-authored fixture.",
                }
            ),
            Path("tests/fixtures/evidence/static.html"),
            tmp_path / "snapshots",
            manifest_dir,
        )
    )
    claim = new_extracted_claim(
        capture_id=capture.id,
        source_id=capture.source_id,
        raw_race_text="King County Assessor",
        raw_candidate_text="Rob Foxcurran",
        raw_status_text="Endorsed",
        raw_notes=None,
        evidence_excerpt="Rob Foxcurran for King County Assessor",
        evidence_locator="Endorsement list, item 1",
        extractor="fixture",
        extractor_version="1.0",
        extraction_confidence="1",
        requires_review=False,
    )
    claim_path = write_record(claim, tmp_path / "claims")
    output_dir = tmp_path / "endorsements"

    result = runner.invoke(
        app,
        [
            "normalize",
            "match",
            str(claim_path),
            "--created-at",
            "2026-07-19T13:00:00Z",
            "--manifest-dir",
            str(manifest_dir),
            "--queue-dir",
            str(tmp_path / "queue"),
            "--output-dir",
            str(output_dir),
        ],
    )

    assert result.exit_code == 0, result.output
    assert "normalized endorsement:" in result.stdout
    payload = next(output_dir.glob("*.json")).read_text(encoding="utf-8")
    assert '"status": "endorsed"' in payload
    assert '"king-county-assessor--rob-foxcurran": "1"' in payload


def test_review_commands_show_and_resolve_an_ambiguous_record(tmp_path: Path) -> None:
    queue_dir = tmp_path / "queue"
    decisions_dir = tmp_path / "decisions"
    manifest_dir = tmp_path / "manifests"
    capture = read_capture_manifest(
        record_capture(
            CaptureRequest.model_validate(
                {
                    "source_id": "the-stranger",
                    "requested_url": "https://www.thestranger.com/endorsements/review-fixture",
                    "canonical_url": "https://www.thestranger.com/endorsements/review-fixture",
                    "retrieved_at": "2026-07-19T12:00:00Z",
                    "http_status": 200,
                    "media_type": "text/html",
                    "title": "Review fixture",
                    "capture_method": "static_html",
                    "redistribution": "permitted",
                    "redistribution_note": "Repository-authored fixture.",
                }
            ),
            Path("tests/fixtures/evidence/static.html"),
            tmp_path / "snapshots",
            manifest_dir,
        )
    )
    claim = new_extracted_claim(
        capture_id=capture.id,
        source_id="the-stranger",
        raw_race_text="King County Assessor",
        raw_candidate_text="Unknown Person",
        raw_status_text="Endorsed",
        raw_notes=None,
        evidence_excerpt="Fixture endorsement excerpt.",
        evidence_locator="Fixture heading, line 1",
        extractor="fixture",
        extractor_version="1.0",
        extraction_confidence="1",
        requires_review=False,
    )
    claim_path = write_record(claim, tmp_path / "claims")
    outcome = match_claim(
        claim,
        read_inventory(Path("data/normalized/wa-2026-primary-inventory.json")),
        created_at=datetime(2026, 7, 19, 13, tzinfo=UTC),
        source_registry=read_source_registry(Path("config/sources/default.yaml")),
    )
    assert outcome.review_item is not None
    write_review_item(outcome.review_item, queue_dir)

    listed = runner.invoke(
        app,
        [
            "review",
            "list",
            "--queue-dir",
            str(queue_dir),
            "--decisions-dir",
            str(decisions_dir),
        ],
    )
    assert listed.exit_code == 0, listed.output
    assert outcome.review_item.id in listed.stdout

    shown = runner.invoke(
        app,
        ["review", "show", outcome.review_item.id, "--queue-dir", str(queue_dir)],
    )
    assert shown.exit_code == 0, shown.output
    assert '"reason": "candidate_unmatched"' in shown.stdout

    invalid_approval = runner.invoke(
        app,
        [
            "review",
            "approve",
            outcome.review_item.id,
            "--author",
            "reviewer",
            "--reason",
            "This invalid resolution must not claim the terminal slot.",
            "--evidence",
            "Capture heading, line 1",
            "--created-at",
            "2026-07-19T13:04:00Z",
            "--race-id",
            "nonexistent-race",
            "--status",
            "endorsed",
            "--candidate-id",
            "nonexistent-candidate",
            "--claim-path",
            str(claim_path),
            "--manifest-dir",
            str(manifest_dir),
            "--queue-dir",
            str(queue_dir),
            "--decisions-dir",
            str(decisions_dir),
        ],
    )
    assert invalid_approval.exit_code == 1
    assert not list(decisions_dir.glob("*.json"))

    approved = runner.invoke(
        app,
        [
            "review",
            "approve",
            outcome.review_item.id,
            "--author",
            "reviewer",
            "--reason",
            "Verified against the captured source.",
            "--evidence",
            "Capture heading, line 1",
            "--created-at",
            "2026-07-19T13:05:00Z",
            "--race-id",
            "king-county-assessor",
            "--status",
            "endorsed",
            "--candidate-id",
            "king-county-assessor--rob-foxcurran",
            "--claim-path",
            str(claim_path),
            "--manifest-dir",
            str(manifest_dir),
            "--queue-dir",
            str(queue_dir),
            "--decisions-dir",
            str(decisions_dir),
        ],
    )
    assert approved.exit_code == 0, approved.output

    repeated = runner.invoke(
        app,
        [
            "review",
            "reject",
            outcome.review_item.id,
            "--author",
            "reviewer",
            "--reason",
            "A second decision must not be allowed.",
            "--evidence",
            "Capture heading, line 1",
            "--created-at",
            "2026-07-19T13:06:00Z",
            "--queue-dir",
            str(queue_dir),
            "--decisions-dir",
            str(decisions_dir),
        ],
    )
    assert repeated.exit_code == 1
    assert "already has a terminal decision" in repeated.output


def test_review_override_requires_json_values_and_records_audit_fields(tmp_path: Path) -> None:
    overrides_dir = tmp_path / "overrides"
    target = new_extracted_claim(
        capture_id="capture-the-stranger-20260719T120000Z-0123456789ab",
        source_id="the-stranger",
        raw_race_text="King County Assessor",
        raw_candidate_text="Unknown Person",
        raw_status_text="Endorsed",
        raw_notes=None,
        evidence_excerpt="Fixture endorsement excerpt.",
        evidence_locator="Fixture heading",
        extractor="fixture",
        extractor_version="1.0",
        extraction_confidence="1",
        requires_review=False,
    )
    outcome = match_claim(
        target,
        read_inventory(Path("data/normalized/wa-2026-primary-inventory.json")),
        created_at=datetime(2026, 7, 19, 13, tzinfo=UTC),
        source_registry=read_source_registry(Path("config/sources/default.yaml")),
    )
    assert outcome.review_item is not None
    review_target = outcome.review_item
    target_path = write_review_item(review_target, tmp_path / "queue")
    result = runner.invoke(
        app,
        [
            "review",
            "override",
            review_target.id,
            "--field",
            "summary",
            "--old-value",
            json.dumps(review_target.summary),
            "--new-value",
            '"Reviewer annotation"',
            "--reason",
            "The source explicitly made no endorsement.",
            "--evidence",
            "Capture paragraph 2",
            "--author",
            "reviewer",
            "--created-at",
            "2026-07-19T13:10:00Z",
            "--target-path",
            str(target_path),
            "--overrides-dir",
            str(overrides_dir),
        ],
    )

    assert result.exit_code == 0, result.output
    payload = next(overrides_dir.glob("*.json")).read_text(encoding="utf-8")
    assert f'"old_value": {json.dumps(review_target.summary)}' in payload
    assert '"new_value": "Reviewer annotation"' in payload
    assert '"author": "reviewer"' in payload

    backdated = runner.invoke(
        app,
        [
            "review",
            "override",
            review_target.id,
            "--field",
            "summary",
            "--old-value",
            '"Reviewer annotation"',
            "--new-value",
            '"Backdated annotation"',
            "--reason",
            "This must not reorder append-only history.",
            "--evidence",
            "Capture paragraph 2",
            "--author",
            "reviewer",
            "--created-at",
            "2026-07-19T13:00:00Z",
            "--target-path",
            str(target_path),
            "--overrides-dir",
            str(overrides_dir),
        ],
    )
    assert backdated.exit_code == 1
    assert "timestamp must be later" in backdated.output

    invalid_type = runner.invoke(
        app,
        [
            "review",
            "override",
            review_target.id,
            "--field",
            "summary",
            "--old-value",
            '"Reviewer annotation"',
            "--new-value",
            "123",
            "--reason",
            "This invalid projected value must not be written.",
            "--evidence",
            "Capture paragraph 2",
            "--author",
            "reviewer",
            "--created-at",
            "2026-07-19T13:20:00Z",
            "--target-path",
            str(target_path),
            "--overrides-dir",
            str(overrides_dir),
        ],
    )
    assert invalid_type.exit_code == 1
    assert len(list(overrides_dir.glob("*.json"))) == 1
