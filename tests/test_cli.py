from typer.testing import CliRunner

from election_guide import __version__
from election_guide.cli import app

runner = CliRunner()


def test_help_lists_foundational_commands() -> None:
    result = runner.invoke(app, ["--help"])

    assert result.exit_code == 0
    assert "doctor" in result.stdout
    assert "inventory" in result.stdout
    assert "version" in result.stdout


def test_version_reports_package_version() -> None:
    result = runner.invoke(app, ["version"])

    assert result.exit_code == 0
    assert result.stdout.strip() == __version__


def test_doctor_accepts_repository_root() -> None:
    result = runner.invoke(app, ["doctor", "--project-root", "."])

    assert result.exit_code == 0
    assert result.stdout.strip() == "foundation: ok"
