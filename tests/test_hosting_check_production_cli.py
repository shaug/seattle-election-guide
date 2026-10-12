"""Behavior tests for the `hosting check-production` and `calendar in-window` CLI (O14)."""

from __future__ import annotations

import json
import subprocess
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
import yaml
from typer.testing import CliRunner

from election_guide import cli
from election_guide.hosting.models import SiteManifest
from election_guide.hosting.production_check import (
    MANIFEST_CHECK,
    CommitCheck,
    Observation,
    ProductionCheckReport,
    RouteCheckResult,
    evaluate_archive_index,
    evaluate_deployment_contract,
    plan_publication_route_checks,
)
from tests.test_production_check import (
    COMMIT,
    _deployment_manifest,  # pyright: ignore[reportPrivateUsage]
    _failing_report,  # pyright: ignore[reportPrivateUsage]
    _healthy_report,  # pyright: ignore[reportPrivateUsage]
    _site_manifest,  # pyright: ignore[reportPrivateUsage]
)


def _stub_failing_check(monkeypatch: pytest.MonkeyPatch) -> None:
    def _check(
        base_url: str,
        *,
        expected_git_commit: str,
        timeout: float,
        active_window: bool,
        checked_at: datetime,
        site_manifest: SiteManifest,
    ) -> ProductionCheckReport:
        return _failing_report()

    monkeypatch.setattr(cli, "run_production_check", _check)


@pytest.fixture(autouse=True)
def forbid_subprocess(monkeypatch: pytest.MonkeyPatch) -> None:
    def _never(*args: Any, **kwargs: Any) -> None:
        raise AssertionError("production probes must not invoke GitHub or change alert issues")

    monkeypatch.setattr(subprocess, "run", _never)


def test_a_healthy_run_exits_zero_without_github(monkeypatch: pytest.MonkeyPatch) -> None:
    recorded: dict[str, Any] = {}

    def _check(base_url: str, **kwargs: Any) -> ProductionCheckReport:
        recorded["base_url"] = base_url
        recorded.update(kwargs)
        return _healthy_report()

    monkeypatch.setattr(cli, "run_production_check", _check)
    result = CliRunner().invoke(
        cli.app,
        [
            "hosting",
            "check-production",
            "https://seattleelections.guide",
            "--expected-git-commit",
            COMMIT,
        ],
    )

    assert result.exit_code == 0, result.output
    assert recorded["base_url"] == "https://seattleelections.guide"
    assert recorded["expected_git_commit"] == COMMIT
    assert recorded["site_manifest"].current_election_id == "wa-2026-general"
    assert "PASS" in result.output


def test_a_failing_run_exits_nonzero_without_github(monkeypatch: pytest.MonkeyPatch) -> None:
    _stub_failing_check(monkeypatch)
    result = CliRunner().invoke(
        cli.app,
        [
            "hosting",
            "check-production",
            "https://seattleelections.guide",
            "--expected-git-commit",
            COMMIT,
        ],
    )

    assert result.exit_code == 1
    assert "FAIL" in result.output
    assert result.exception is not None
    assert isinstance(result.exception, SystemExit)


def test_availability_mode_probes_without_unpublished_release_expectations(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    recorded: dict[str, Any] = {}

    def _check(base_url: str, **kwargs: Any) -> ProductionCheckReport:
        recorded.update(kwargs)
        return _healthy_report().model_copy(update={"commit": None})

    def _never_calendar(*args: Any, **kwargs: Any) -> None:
        raise AssertionError("availability must not read the publication calendar")

    monkeypatch.setattr(cli, "run_production_check", _check)
    monkeypatch.setattr(cli, "read_election_calendar", _never_calendar)
    result = CliRunner().invoke(
        cli.app,
        [
            "hosting",
            "check-production",
            "https://seattleelections.guide",
            "--availability-only",
        ],
    )

    assert result.exit_code == 0, result.output
    assert recorded["expected_git_commit"] is None
    assert recorded["site_manifest"] is None
    assert recorded["active_window"] is False
    assert "PASS" in result.output
    assert "commit:" not in result.output


@pytest.mark.parametrize(
    "arguments", [[], ["--availability-only", "--expected-git-commit", COMMIT]]
)
def test_production_mode_requires_an_unambiguous_release_expectation(
    monkeypatch: pytest.MonkeyPatch,
    arguments: list[str],
) -> None:
    def _never(*args: Any, **kwargs: Any) -> ProductionCheckReport:
        raise AssertionError("an ambiguous check must fail before probing")

    monkeypatch.setattr(cli, "run_production_check", _never)
    result = CliRunner().invoke(
        cli.app,
        ["hosting", "check-production", "https://seattleelections.guide", *arguments],
    )

    assert result.exit_code == 1
    assert "expected" in result.output.lower()


def _write_calendar(path: Path, *, election_date: date) -> Path:
    calendar_path = path / "elections.yaml"
    calendar_path.write_text(
        yaml.safe_dump(
            {
                "schema_version": "1.0",
                "elections": [
                    {
                        "id": "wa-2027-general",
                        "election_type": "general",
                        "election_scope": "municipal",
                        "election_date": election_date.isoformat(),
                        "state": "WA",
                    }
                ],
                "milestones": [
                    {
                        "election_id": "wa-2027-general",
                        "id": "election-day",
                        "kind": "election_day",
                        "offset_days": 0,
                    },
                    {
                        "election_id": "wa-2027-general",
                        "id": "results-capture-election-night",
                        "kind": "results_capture_election_night",
                        "offset_days": 0,
                    },
                    {
                        "election_id": "wa-2027-general",
                        "id": "results-capture-post-certification",
                        "kind": "results_capture_post_certification",
                        "offset_days": 22,
                    },
                    {
                        "election_id": "wa-2027-general",
                        "id": "results-ingest",
                        "kind": "results_ingest",
                        "offset_days": 22,
                    },
                ],
            }
        ),
        encoding="utf-8",
    )
    return calendar_path


def _write_site_manifest(path: Path) -> Path:
    site_manifest_path = path / "site.yaml"
    site_manifest_path.write_text(
        yaml.safe_dump(
            {
                "schema_version": "1.0",
                "canonical_origin": "https://seattleelections.guide",
                "current_election_id": "wa-2026-general",
                "elections": [
                    {
                        "election_id": "wa-2026-general",
                        "bundle_id": "wa-2026-general-2026-general.3",
                        "release_version": "2026-general.3",
                        "source_panel_id": "general-panel",
                        "source_panel_hash": "1" * 64,
                        "source_registry_hash": "2" * 64,
                    },
                    {
                        "election_id": "wa-2026-primary",
                        "bundle_id": "wa-2026-primary-2026-primary.2",
                        "release_version": "2026-primary.2",
                        "source_panel_id": "primary-panel",
                        "source_panel_hash": "3" * 64,
                        "git_commit": "4" * 40,
                        "release_manifest_sha256": "5" * 64,
                        "bundle_sha256": "6" * 64,
                    },
                ],
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    return site_manifest_path


def test_check_production_refuses_a_base_url_outside_the_site_manifest_authority(
    tmp_path: Path,
) -> None:
    """Removing the manifest-origin guard would let a publication-day check
    attest an arbitrary preview host instead of the canonical production site."""
    site_manifest_path = _write_site_manifest(tmp_path)

    result = CliRunner().invoke(
        cli.app,
        [
            "hosting",
            "check-production",
            "https://preview.example",
            "--expected-git-commit",
            COMMIT,
            "--site-manifest",
            str(site_manifest_path),
        ],
    )

    assert result.exit_code == 1
    assert "base URL must equal site manifest canonical origin" in result.output


def test_check_production_rejects_an_abbreviated_expected_commit_before_probing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    site_manifest_path = _write_site_manifest(tmp_path)

    def _never(*args: Any, **kwargs: Any) -> ProductionCheckReport:
        raise AssertionError("invalid commit identity must fail before the network probe")

    monkeypatch.setattr(cli, "run_production_check", _never)
    result = CliRunner().invoke(
        cli.app,
        [
            "hosting",
            "check-production",
            "https://seattleelections.guide",
            "--expected-git-commit",
            "deadbeef",
            "--site-manifest",
            str(site_manifest_path),
        ],
    )

    assert result.exit_code == 1
    assert "expected Git commit must be a full 40-character lowercase SHA" in result.output


def _attachment_report() -> ProductionCheckReport:
    site_manifest = _site_manifest()
    deployment = _deployment_manifest()
    contract = evaluate_deployment_contract(site_manifest, deployment, expected_git_commit=COMMIT)
    archive = evaluate_archive_index(
        site_manifest,
        Observation(status=200),
        b'<li><a href="/e/wa-2026-general/">General</a> '
        b"<strong>(current)</strong></li>"
        b'<li><a href="/e/wa-2026-primary/">Primary</a></li>',
    )
    routes = tuple(
        RouteCheckResult(
            check=check,
            observed=Observation(
                status=check.expected_status,
                location=check.expected_location,
                raw_location=(
                    f"https://seattleelections.guide{check.expected_location}"
                    if check.expected_location is not None
                    else None
                ),
            ),
        )
        for check in plan_publication_route_checks(
            site_manifest,
            representative_race_path="/e/wa-2026-general/races/alpha/",
        )
    )
    return ProductionCheckReport(
        manifest=RouteCheckResult(check=MANIFEST_CHECK, observed=Observation(status=200)),
        deployment_contract=contract,
        archive_index=archive,
        current_election_id=site_manifest.current_election_id,
        route_results=routes,
        commit=CommitCheck(expected=COMMIT, observed=COMMIT),
    )


@pytest.mark.parametrize("healthy", [True, False])
def test_production_probe_writes_attachment_ready_json_without_github(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, healthy: bool
) -> None:
    site_manifest_path = _write_site_manifest(tmp_path)
    output_path = tmp_path / "production-probe.json"

    def _check(*args: Any, **kwargs: Any) -> ProductionCheckReport:
        report = _attachment_report()
        return (
            report
            if healthy
            else report.model_copy(
                update={"commit": CommitCheck(expected=COMMIT, observed="f" * 40)}
            )
        )

    monkeypatch.setattr(cli, "run_production_check", _check)
    result = CliRunner().invoke(
        cli.app,
        [
            "hosting",
            "check-production",
            "https://seattleelections.guide",
            "--expected-git-commit",
            COMMIT,
            "--site-manifest",
            str(site_manifest_path),
            "--output",
            str(output_path),
        ],
    )

    assert result.exit_code == (0 if healthy else 1), result.output
    evidence = json.loads(output_path.read_text(encoding="utf-8"))
    assert evidence["manifest"]["observed"]["status"] == 200
    assert evidence["deployment_contract"]["observed"]["current_election_id"] == ("wa-2026-general")
    assert evidence["route_results"][0]["observed"]["status"] == 307
    assert evidence["route_results"][0]["observed"]["raw_location"] == (
        "https://seattleelections.guide/e/wa-2026-general/"
    )
    assert evidence["deployment_contract"]["representative_race_path"] == (
        "/e/wa-2026-general/races/alpha/"
    )


def test_check_production_reads_the_active_window_from_the_calendar(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    recorded: dict[str, Any] = {}
    today = datetime.now(UTC).date()
    calendar_path = _write_calendar(tmp_path, election_date=today + timedelta(days=4))

    def _check(
        base_url: str,
        *,
        expected_git_commit: str,
        timeout: float,
        active_window: bool,
        checked_at: datetime,
        site_manifest: SiteManifest,
    ) -> ProductionCheckReport:
        recorded["active_window"] = active_window
        return _healthy_report()

    monkeypatch.setattr(cli, "run_production_check", _check)

    result = CliRunner().invoke(
        cli.app,
        [
            "hosting",
            "check-production",
            "https://seattleelections.guide",
            "--expected-git-commit",
            COMMIT,
            "--calendar",
            str(calendar_path),
        ],
    )

    assert result.exit_code == 0
    assert recorded["active_window"] is True


def test_in_window_is_true_inside_the_pre_election_window(tmp_path: Path) -> None:
    calendar_path = _write_calendar(tmp_path, election_date=date(2027, 11, 2))

    result = CliRunner().invoke(
        cli.app,
        [
            "calendar",
            "in-window",
            str(calendar_path),
            "--before-days",
            "7",
            "--as-of",
            "2027-10-28",
        ],
    )

    assert result.exit_code == 0
    assert result.output.strip() == "true"


def test_in_window_is_false_outside_the_pre_election_window(tmp_path: Path) -> None:
    calendar_path = _write_calendar(tmp_path, election_date=date(2027, 11, 2))

    result = CliRunner().invoke(
        cli.app,
        [
            "calendar",
            "in-window",
            str(calendar_path),
            "--before-days",
            "7",
            "--as-of",
            "2027-10-01",
        ],
    )

    assert result.exit_code == 1
    assert result.output.strip() == "false"


def test_in_window_is_true_on_election_day_itself(tmp_path: Path) -> None:
    calendar_path = _write_calendar(tmp_path, election_date=date(2027, 11, 2))

    result = CliRunner().invoke(
        cli.app,
        [
            "calendar",
            "in-window",
            str(calendar_path),
            "--before-days",
            "7",
            "--as-of",
            "2027-11-02",
        ],
    )

    assert result.exit_code == 0
    assert result.output.strip() == "true"


def test_in_window_is_false_the_day_after_election_day(tmp_path: Path) -> None:
    calendar_path = _write_calendar(tmp_path, election_date=date(2027, 11, 2))

    result = CliRunner().invoke(
        cli.app,
        [
            "calendar",
            "in-window",
            str(calendar_path),
            "--before-days",
            "7",
            "--as-of",
            "2027-11-03",
        ],
    )

    assert result.exit_code == 1
    assert result.output.strip() == "false"
