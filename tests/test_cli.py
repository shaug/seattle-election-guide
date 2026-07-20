from pathlib import Path

from typer.testing import CliRunner

from election_guide import __version__
from election_guide.cli import app

runner = CliRunner()


def test_help_lists_foundational_commands() -> None:
    result = runner.invoke(app, ["--help"])

    assert result.exit_code == 0
    assert "doctor" in result.stdout
    assert "evidence" in result.stdout
    assert "inventory" in result.stdout
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
            "--canonical-url",
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
    assert "content_sha256" not in payload
