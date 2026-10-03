"""Behavior tests for the pure production-check plan and evaluation (O14)."""

from __future__ import annotations

import json

import pytest

import election_guide.hosting.production_check as production_check
from election_guide.hosting.models import DeploymentManifest, SiteManifest
from election_guide.hosting.production_check import (
    MANIFEST_CHECK,
    CommitCheck,
    Observation,
    ProductionCheckReport,
    RouteCheck,
    RouteCheckResult,
    evaluate_manifest,
    plan_route_checks,
    render_summary_lines,
)

CURRENT_ID = "wa-2026-primary"
COMMIT = "a" * 40


def _site_manifest() -> SiteManifest:
    return SiteManifest.model_validate(
        {
            "schema_version": "1.0",
            "canonical_origin": "https://seattleelections.guide",
            "current_election_id": "wa-2026-general",
            "elections": [
                {
                    "election_id": "wa-2026-general",
                    "bundle_id": "wa-2026-general-2026-general.1",
                    "release_version": "2026-general.1",
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
        }
    )


def _deployment_manifest() -> DeploymentManifest:
    return DeploymentManifest.model_validate(
        {
            "schema_version": "2.0",
            "canonical_origin": "https://seattleelections.guide",
            "current_election_id": "wa-2026-general",
            "elections": [
                {
                    "election_id": "wa-2026-general",
                    "bundle_id": "wa-2026-general-2026-general.1",
                    "release_version": "2026-general.1",
                    "git_commit": COMMIT,
                    "source_panel_id": "general-panel",
                    "source_panel_hash": "1" * 64,
                    "source_registry_hash": "2" * 64,
                    "release_manifest_sha256": "7" * 64,
                },
                {
                    "election_id": "wa-2026-primary",
                    "bundle_id": "wa-2026-primary-2026-primary.2",
                    "release_version": "2026-primary.2",
                    "git_commit": "4" * 40,
                    "source_panel_id": "primary-panel",
                    "source_panel_hash": "3" * 64,
                    "release_manifest_sha256": "5" * 64,
                },
            ],
            "assets": {
                "e/index.html": "8" * 64,
                "e/wa-2026-general/index.html": "9" * 64,
                "e/wa-2026-general/comparisons/index.html": "a" * 64,
                "e/wa-2026-general/races/zeta/index.html": "b" * 64,
                "e/wa-2026-general/races/alpha/index.html": "c" * 64,
                "e/wa-2026-primary/index.html": "d" * 64,
            },
        }
    )


def test_deployment_contract_uses_the_site_manifest_and_selects_the_first_race() -> None:
    check = production_check.evaluate_deployment_contract(
        _site_manifest(), _deployment_manifest(), expected_git_commit=COMMIT
    )

    assert check.ok
    assert check.errors == ()
    assert check.representative_race_path == "/e/wa-2026-general/races/alpha/"


@pytest.mark.parametrize(
    ("mutation", "expected_error"),
    [
        ({"canonical_origin": "https://wrong.example"}, "canonical origin"),
        ({"current_election_id": "wa-2026-primary"}, "current election"),
    ],
)
def test_deployment_contract_rejects_wrong_top_level_manifest_identity(
    mutation: dict[str, str], expected_error: str
) -> None:
    payload = _deployment_manifest().model_dump(mode="json")
    payload.update(mutation)
    if mutation.get("current_election_id") == "wa-2026-primary":
        payload["elections"] = list(reversed(payload["elections"]))
    observed = DeploymentManifest.model_validate(payload)

    check = production_check.evaluate_deployment_contract(
        _site_manifest(), observed, expected_git_commit=COMMIT
    )

    assert not check.ok
    assert any(expected_error in error for error in check.errors)


@pytest.mark.parametrize(
    ("election_index", "field", "value", "expected_error"),
    [
        (0, "release_version", "2026-general.2", "release version"),
        (0, "bundle_id", "wrong-general", "bundle ID"),
        (0, "source_panel_hash", "f" * 64, "source panel hash"),
        (0, "source_registry_hash", "e" * 64, "source registry hash"),
        (1, "release_version", "2026-primary.1", "release version"),
        (1, "git_commit", "f" * 40, "Git commit"),
        (1, "release_manifest_sha256", "e" * 64, "release-manifest hash"),
    ],
)
def test_deployment_contract_rejects_changed_election_identity(
    election_index: int, field: str, value: str, expected_error: str
) -> None:
    payload = _deployment_manifest().model_dump(mode="json")
    payload["elections"][election_index][field] = value
    observed = DeploymentManifest.model_validate(payload)

    check = production_check.evaluate_deployment_contract(
        _site_manifest(), observed, expected_git_commit=COMMIT
    )

    assert not check.ok
    assert any(expected_error in error for error in check.errors)


def test_deployment_contract_rejects_a_missing_historical_election() -> None:
    payload = _deployment_manifest().model_dump(mode="json")
    payload["elections"] = payload["elections"][:1]
    observed = DeploymentManifest.model_validate(payload)

    check = production_check.evaluate_deployment_contract(
        _site_manifest(), observed, expected_git_commit=COMMIT
    )

    assert not check.ok
    assert any("election set/order" in error for error in check.errors)


def test_deployment_contract_requires_the_historical_bundle_pin() -> None:
    payload = _site_manifest().model_dump(mode="json")
    payload["elections"][1]["bundle_sha256"] = None
    site_manifest = SiteManifest.model_validate(payload)

    check = production_check.evaluate_deployment_contract(
        site_manifest, _deployment_manifest(), expected_git_commit=COMMIT
    )

    assert not check.ok
    assert any("historical site declaration lacks bundle hash" in error for error in check.errors)


def test_deployment_contract_rejects_the_wrong_production_candidate() -> None:
    check = production_check.evaluate_deployment_contract(
        _site_manifest(), _deployment_manifest(), expected_git_commit="f" * 40
    )

    assert not check.ok
    assert any("production candidate commit" in error for error in check.errors)


def test_publication_route_plan_covers_the_complete_release_contract() -> None:
    checks = production_check.plan_publication_route_checks(
        _site_manifest(), representative_race_path="/e/wa-2026-general/races/alpha/"
    )

    assert [
        (check.name, check.path, check.expected_status, check.expected_location) for check in checks
    ] == [
        ("home redirect", "/", 307, "/e/wa-2026-general/"),
        ("election archive", "/e/", 200, None),
        ("current election guide", "/e/wa-2026-general/", 200, None),
        ("historical election guide: wa-2026-primary", "/e/wa-2026-primary/", 200, None),
        (
            "representative current-election race",
            "/e/wa-2026-general/races/alpha/",
            200,
            None,
        ),
        ("current election comparisons", "/e/wa-2026-general/comparisons/", 200, None),
        ("unknown election", "/e/production-check-unknown-election/", 404, None),
        (
            "legacy PDF redirect",
            "/e/wa-2026-general/voter-guide.pdf",
            301,
            "/e/wa-2026-general/",
        ),
    ]


def test_archive_index_requires_every_declared_election_and_the_current_marker() -> None:
    body = b"""
    <ul>
      <li><a href="/e/wa-2026-general/">General</a> <strong>(current)</strong></li>
      <li><a href="/e/wa-2026-primary/">Primary</a></li>
    </ul>
    """

    check = production_check.evaluate_archive_index(_site_manifest(), Observation(status=200), body)

    assert check.ok
    assert check.observed_election_ids == ("wa-2026-general", "wa-2026-primary")
    assert check.observed_current_election_id == "wa-2026-general"


@pytest.mark.parametrize(
    ("body", "expected_error"),
    [
        (
            b'<li><a href="/e/wa-2026-general/">General</a> <strong>(current)</strong></li>',
            "election set/order",
        ),
        (
            b'<li><a href="/e/wa-2026-general/">General</a></li>'
            b'<li><a href="/e/wa-2026-primary/">Primary</a> <strong>(current)</strong></li>',
            "current marker",
        ),
    ],
)
def test_archive_index_rejects_missing_elections_or_a_wrong_current_marker(
    body: bytes, expected_error: str
) -> None:
    check = production_check.evaluate_archive_index(_site_manifest(), Observation(status=200), body)

    assert not check.ok
    assert any(expected_error in error for error in check.errors)


def _manifest_bytes(*, current_election_id: str = CURRENT_ID, git_commit: str = COMMIT) -> bytes:
    return json.dumps(
        {
            "schema_version": "2.0",
            "canonical_origin": "https://seattleelections.guide",
            "current_election_id": current_election_id,
            "elections": [
                {
                    "election_id": current_election_id,
                    "bundle_id": f"{current_election_id}-1",
                    "release_version": "primary.1",
                    "git_commit": git_commit,
                    "source_panel_id": "panel",
                    "source_panel_hash": "b" * 64,
                    "release_manifest_sha256": "c" * 64,
                }
            ],
            "assets": {"e/index.html": "d" * 64},
        }
    ).encode("utf-8")


def test_the_route_plan_covers_the_home_election_and_legacy_pdf_paths() -> None:
    checks = plan_route_checks(CURRENT_ID)

    assert checks == [
        RouteCheck(
            name="home redirect",
            path="/",
            expected_status=307,
            expected_location=f"/e/{CURRENT_ID}/",
        ),
        RouteCheck(
            name="current election guide",
            path=f"/e/{CURRENT_ID}/",
            expected_status=200,
        ),
        RouteCheck(
            name="legacy PDF redirect",
            path=f"/e/{CURRENT_ID}/voter-guide.pdf",
            expected_status=301,
            expected_location=f"/e/{CURRENT_ID}/",
        ),
    ]


def test_a_route_result_passes_when_status_and_location_match() -> None:
    check = RouteCheck(
        name="home redirect", path="/", expected_status=307, expected_location="/e/x/"
    )
    result = RouteCheckResult(check=check, observed=Observation(status=307, location="/e/x/"))

    assert result.ok


def test_a_route_result_fails_on_a_wrong_status() -> None:
    check = RouteCheck(name="current election guide", path="/e/x/", expected_status=200)
    result = RouteCheckResult(check=check, observed=Observation(status=404))

    assert not result.ok


def test_a_route_result_fails_on_a_wrong_redirect_target_even_with_the_right_status() -> None:
    check = RouteCheck(
        name="home redirect", path="/", expected_status=307, expected_location="/e/x/"
    )
    result = RouteCheckResult(check=check, observed=Observation(status=307, location="/e/y/"))

    assert not result.ok


def test_a_route_result_fails_when_the_request_itself_failed() -> None:
    check = RouteCheck(name="current election guide", path="/e/x/", expected_status=200)
    result = RouteCheckResult(check=check, observed=Observation(error="connection refused"))

    assert not result.ok


def test_a_commit_check_passes_only_on_an_exact_match() -> None:
    assert CommitCheck(expected=COMMIT, observed=COMMIT).ok
    assert not CommitCheck(expected=COMMIT, observed="f" * 40).ok
    assert not CommitCheck(expected=COMMIT, observed=None).ok


def test_evaluate_manifest_parses_a_healthy_response() -> None:
    observation = Observation(status=200)
    result, manifest, error = evaluate_manifest(observation, _manifest_bytes())

    assert result.check == MANIFEST_CHECK
    assert result.ok
    assert manifest is not None
    assert manifest.current_election_id == CURRENT_ID
    assert error is None


def test_evaluate_manifest_reports_a_non_200_without_attempting_to_parse() -> None:
    observation = Observation(status=404)
    result, manifest, error = evaluate_manifest(observation, b"not json")

    assert not result.ok
    assert manifest is None
    assert error is None


def test_evaluate_manifest_reports_a_transport_failure() -> None:
    observation = Observation(error="timed out")
    result, manifest, error = evaluate_manifest(observation, None)

    assert not result.ok
    assert manifest is None
    assert error is None


def test_evaluate_manifest_reports_unparseable_json_on_an_otherwise_ok_response() -> None:
    observation = Observation(status=200)
    result, manifest, error = evaluate_manifest(observation, b"{not json")

    assert result.ok
    assert manifest is None
    assert error is not None


def test_evaluate_manifest_reports_a_non_utf8_body_instead_of_crashing() -> None:
    """`json.loads` decodes bytes itself; a non-UTF-8 body must FAIL the
    check, not raise an uncaught UnicodeDecodeError past this function."""
    observation = Observation(status=200)

    result, manifest, error = evaluate_manifest(observation, b"\xff\xfe not utf-8 at all")

    assert result.ok
    assert manifest is None
    assert error is not None


def test_evaluate_manifest_reports_a_schema_violation() -> None:
    observation = Observation(status=200)
    body = json.dumps({"schema_version": "2.0"}).encode("utf-8")

    result, manifest, error = evaluate_manifest(observation, body)

    assert result.ok
    assert manifest is None
    assert error is not None


def _healthy_report() -> ProductionCheckReport:
    """Shared across test_production_check.py, test_production_alert.py, and
    test_hosting_check_production_cli.py — imported by the other two rather
    than redefined, matching this repository's cross-file private-import
    convention (e.g. `tests/test_compare_rendering.py` importing `_bundle`
    from `tests/test_comparisons.py`)."""
    manifest_result = RouteCheckResult(check=MANIFEST_CHECK, observed=Observation(status=200))
    route_results = tuple(
        RouteCheckResult(
            check=check,
            observed=Observation(status=check.expected_status, location=check.expected_location),
        )
        for check in plan_route_checks(CURRENT_ID)
    )
    return ProductionCheckReport(
        manifest=manifest_result,
        current_election_id=CURRENT_ID,
        route_results=route_results,
        commit=CommitCheck(expected=COMMIT, observed=COMMIT),
    )


def _failing_report() -> ProductionCheckReport:
    """Shared the same way as `_healthy_report` above."""
    return _healthy_report().model_copy(
        update={"commit": CommitCheck(expected=COMMIT, observed="f" * 40)}
    )


def test_a_fully_healthy_report_is_ok() -> None:
    assert _healthy_report().ok


def test_a_failing_report_is_not_ok() -> None:
    assert not _failing_report().ok


def test_a_report_is_not_ok_when_the_manifest_itself_failed() -> None:
    report = _healthy_report().model_copy(
        update={
            "manifest": RouteCheckResult(check=MANIFEST_CHECK, observed=Observation(status=500))
        }
    )

    assert not report.ok


def test_a_report_is_not_ok_when_the_manifest_could_not_be_parsed() -> None:
    report = _healthy_report().model_copy(update={"manifest_parse_error": "boom"})

    assert not report.ok


def test_a_report_is_not_ok_when_any_route_check_fails() -> None:
    failing = list(_healthy_report().route_results)
    failing[1] = failing[1].model_copy(update={"observed": Observation(status=404)})
    report = _healthy_report().model_copy(update={"route_results": tuple(failing)})

    assert not report.ok


def test_a_report_is_not_ok_when_the_commit_does_not_match() -> None:
    report = _healthy_report().model_copy(
        update={"commit": CommitCheck(expected=COMMIT, observed="f" * 40)}
    )

    assert not report.ok


def test_a_report_with_no_commit_check_is_ok_if_everything_else_passes() -> None:
    report = _healthy_report().model_copy(update={"commit": None})

    assert report.ok


def test_summary_lines_mark_a_healthy_report_all_passing() -> None:
    lines = render_summary_lines(_healthy_report())

    assert all(line.startswith("PASS") for line in lines)
    assert any("deployment manifest" in line for line in lines)
    assert any("home redirect" in line for line in lines)
    assert any("commit" in line for line in lines)


def test_summary_lines_name_a_failing_check_with_expected_and_observed() -> None:
    report = _healthy_report().model_copy(
        update={"commit": CommitCheck(expected=COMMIT, observed="f" * 40)}
    )

    lines = render_summary_lines(report)

    failing = [line for line in lines if line.startswith("FAIL")]
    assert len(failing) == 1
    assert COMMIT in failing[0]
    assert "f" * 40 in failing[0]


def test_summary_lines_report_a_transport_error_on_a_route_check() -> None:
    failing = list(_healthy_report().route_results)
    failing[0] = failing[0].model_copy(update={"observed": Observation(error="connection refused")})
    report = _healthy_report().model_copy(update={"route_results": tuple(failing)})

    lines = render_summary_lines(report)

    assert any("connection refused" in line for line in lines)


def test_summary_lines_report_a_manifest_parse_error() -> None:
    report = _healthy_report().model_copy(update={"manifest_parse_error": "field required"})

    lines = render_summary_lines(report)

    assert any("field required" in line for line in lines)
