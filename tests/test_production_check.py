"""Behavior tests for the pure production-check plan and evaluation (O14)."""

from __future__ import annotations

import json

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


def test_evaluate_manifest_reports_a_schema_violation() -> None:
    observation = Observation(status=200)
    body = json.dumps({"schema_version": "2.0"}).encode("utf-8")

    result, manifest, error = evaluate_manifest(observation, body)

    assert result.ok
    assert manifest is None
    assert error is not None


def _healthy_report() -> ProductionCheckReport:
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


def test_a_fully_healthy_report_is_ok() -> None:
    assert _healthy_report().ok


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
