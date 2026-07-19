from pathlib import Path

from typer.testing import CliRunner

from election_guide import __version__
from election_guide.cli import app

runner = CliRunner()


def test_help_lists_foundational_commands() -> None:
    result = runner.invoke(app, ["--help"])

    assert result.exit_code == 0
    assert "doctor" in result.stdout
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
