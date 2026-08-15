"""Behavior tests for reconciling the single production-check alert issue (O14).

Unlike calendar milestone tracking, this identity is update-in-place: a
failing check must not duplicate its issue on every run, and a recovered
check must close it.
"""

from __future__ import annotations

import json
import subprocess
from subprocess import CompletedProcess
from typing import Any

import pytest

from election_guide.hosting.production_alert import (
    ISSUE_LABELS,
    ISSUE_TITLE,
    MARKER,
    AlertAction,
    OpenAlert,
    ProductionAlertTracker,
    plan_alert_action,
    reconcile_alert,
    render_alert_body,
    render_recovery_comment,
)
from election_guide.hosting.production_check import (
    MANIFEST_CHECK,
    CommitCheck,
    Observation,
    ProductionCheckReport,
    RouteCheckResult,
    plan_route_checks,
)

CURRENT_ID = "wa-2026-primary"
COMMIT = "a" * 40
BASE_URL = "https://seattleelections.guide"
CHECKED_AT = "2026-08-15T12:00:00+00:00"


@pytest.fixture(autouse=True)
def forbid_subprocess(monkeypatch: pytest.MonkeyPatch) -> None:
    """Mirror `test_calendar_tracking.py`: nothing here may reach a real `gh` by accident."""

    def _forbidden(*args: Any, **kwargs: Any) -> CompletedProcess[str]:
        raise AssertionError(
            f"a test reached subprocess.run{args[:1]}; stub ProductionAlertTracker or "
            "subprocess.run instead"
        )

    monkeypatch.setattr(subprocess, "run", _forbidden)


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


def _failing_report() -> ProductionCheckReport:
    return _healthy_report().model_copy(
        update={"commit": CommitCheck(expected=COMMIT, observed="f" * 40)}
    )


# --- plan_alert_action -------------------------------------------------


def test_a_healthy_check_with_no_open_alert_does_nothing() -> None:
    assert plan_alert_action(healthy=True, existing_alert_number=None) == AlertAction.NONE


def test_a_healthy_check_with_an_open_alert_closes_it() -> None:
    assert plan_alert_action(healthy=True, existing_alert_number=7) == AlertAction.CLOSE


def test_a_failing_check_with_no_open_alert_creates_one() -> None:
    assert plan_alert_action(healthy=False, existing_alert_number=None) == AlertAction.CREATE


def test_a_failing_check_with_an_open_alert_updates_it_instead_of_duplicating() -> None:
    assert plan_alert_action(healthy=False, existing_alert_number=7) == AlertAction.UPDATE


# --- rendering -----------------------------------------------------------


def test_the_alert_body_embeds_the_marker_as_its_final_line() -> None:
    body = render_alert_body(_failing_report(), base_url=BASE_URL, checked_at=CHECKED_AT)

    assert body.rstrip().endswith(MARKER)


def test_the_alert_body_names_the_failing_check_and_the_base_url() -> None:
    body = render_alert_body(_failing_report(), base_url=BASE_URL, checked_at=CHECKED_AT)

    assert BASE_URL in body
    assert CHECKED_AT in body
    assert "FAIL commit" in body
    assert COMMIT in body


def test_the_recovery_comment_names_when_it_recovered() -> None:
    comment = render_recovery_comment(CHECKED_AT)

    assert CHECKED_AT in comment


# --- ProductionAlertTracker -----------------------------------------------


def _completed(command: list[str], stdout: str = "", code: int = 0) -> CompletedProcess[str]:
    return CompletedProcess(command, code, stdout=stdout, stderr="")


def test_find_open_alert_reads_only_open_issues(monkeypatch: pytest.MonkeyPatch) -> None:
    recorded: dict[str, Any] = {}

    def _run(command: list[str], **kwargs: Any) -> CompletedProcess[str]:
        recorded["command"] = command
        return _completed(command, json.dumps([{"number": 5, "body": f"details\n\n{MARKER}\n"}]))

    monkeypatch.setattr(subprocess, "run", _run)

    found = ProductionAlertTracker("owner/repo").find_open_alert()

    assert found == OpenAlert(number=5)
    command = recorded["command"]
    assert command[:3] == ["gh", "issue", "list"]
    assert "--state" in command and command[command.index("--state") + 1] == "open"
    assert command[command.index("--json") + 1] == "number,body"


def test_find_open_alert_ignores_an_issue_without_the_marker(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def _run(command: list[str], **kwargs: Any) -> CompletedProcess[str]:
        return _completed(command, json.dumps([{"number": 5, "body": "an unrelated open issue"}]))

    monkeypatch.setattr(subprocess, "run", _run)

    assert ProductionAlertTracker("owner/repo").find_open_alert() is None


def test_find_open_alert_returns_none_when_nothing_is_open(monkeypatch: pytest.MonkeyPatch) -> None:
    def _run(command: list[str], **kwargs: Any) -> CompletedProcess[str]:
        return _completed(command, "[]")

    monkeypatch.setattr(subprocess, "run", _run)

    assert ProductionAlertTracker("owner/repo").find_open_alert() is None


def test_a_quoted_marker_does_not_count(monkeypatch: pytest.MonkeyPatch) -> None:
    """Only the last non-empty line counts, matching the calendar tracker's convention."""

    def _run(command: list[str], **kwargs: Any) -> CompletedProcess[str]:
        quoting = f"This system posts a line like\n\n    {MARKER}\n\nat the end of its issues."
        return _completed(command, json.dumps([{"number": 5, "body": quoting}]))

    monkeypatch.setattr(subprocess, "run", _run)

    assert ProductionAlertTracker("owner/repo").find_open_alert() is None


def test_create_opens_a_titled_labeled_issue_carrying_the_body(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    recorded: dict[str, Any] = {}

    def _run(command: list[str], **kwargs: Any) -> CompletedProcess[str]:
        recorded["command"] = command
        return _completed(command, "https://github.com/owner/repo/issues/9\n")

    monkeypatch.setattr(subprocess, "run", _run)
    body = render_alert_body(_failing_report(), base_url=BASE_URL, checked_at=CHECKED_AT)

    url = ProductionAlertTracker("owner/repo").create(body)

    assert url == "https://github.com/owner/repo/issues/9"
    command = recorded["command"]
    assert command[:3] == ["gh", "issue", "create"]
    assert command[command.index("--title") + 1] == ISSUE_TITLE
    assert command[command.index("--body") + 1] == body
    assert [command[i + 1] for i, part in enumerate(command) if part == "--label"] == list(
        ISSUE_LABELS
    )


def test_comment_posts_the_body_to_the_existing_issue(monkeypatch: pytest.MonkeyPatch) -> None:
    recorded: dict[str, Any] = {}

    def _run(command: list[str], **kwargs: Any) -> CompletedProcess[str]:
        recorded["command"] = command
        return _completed(command)

    monkeypatch.setattr(subprocess, "run", _run)
    body = render_alert_body(_failing_report(), base_url=BASE_URL, checked_at=CHECKED_AT)

    ProductionAlertTracker("owner/repo").comment(5, body)

    command = recorded["command"]
    assert command[:3] == ["gh", "issue", "comment"]
    assert command[3] == "5"
    assert command[command.index("--body") + 1] == body


def test_close_closes_with_a_recovery_comment(monkeypatch: pytest.MonkeyPatch) -> None:
    recorded: dict[str, Any] = {}

    def _run(command: list[str], **kwargs: Any) -> CompletedProcess[str]:
        recorded["command"] = command
        return _completed(command)

    monkeypatch.setattr(subprocess, "run", _run)

    ProductionAlertTracker("owner/repo").close(5, comment="recovered")

    command = recorded["command"]
    assert command[:3] == ["gh", "issue", "close"]
    assert command[3] == "5"
    assert command[command.index("--comment") + 1] == "recovered"


def test_a_failing_cli_is_reported(monkeypatch: pytest.MonkeyPatch) -> None:
    def _run(command: list[str], **kwargs: Any) -> CompletedProcess[str]:
        return _completed(command, "", code=1)

    monkeypatch.setattr(subprocess, "run", _run)

    with pytest.raises(ValueError, match="could not list open production-check issues"):
        ProductionAlertTracker("owner/repo").find_open_alert()


def test_a_missing_cli_is_reported(monkeypatch: pytest.MonkeyPatch) -> None:
    def _run(command: list[str], **kwargs: Any) -> CompletedProcess[str]:
        raise FileNotFoundError(command[0])

    monkeypatch.setattr(subprocess, "run", _run)

    with pytest.raises(ValueError, match="GitHub CLI is required"):
        ProductionAlertTracker("owner/repo").find_open_alert()


# --- reconcile_alert -------------------------------------------------------
#
# Stubs monkeypatch ProductionAlertTracker's own methods, matching how
# test_calendar_tracking.py stubs GitHubIssueTracker, rather than passing a
# duck-typed double — reconcile_alert takes a real ProductionAlertTracker.


def _existing(monkeypatch: pytest.MonkeyPatch, alert: OpenAlert | None) -> None:
    def _find(self: ProductionAlertTracker) -> OpenAlert | None:
        return alert

    monkeypatch.setattr(ProductionAlertTracker, "find_open_alert", _find)


def _forbid_create(monkeypatch: pytest.MonkeyPatch, reason: str) -> None:
    def _create(self: ProductionAlertTracker, body: str) -> str:
        pytest.fail(reason)

    monkeypatch.setattr(ProductionAlertTracker, "create", _create)


def _forbid_comment(monkeypatch: pytest.MonkeyPatch, reason: str) -> None:
    def _comment(self: ProductionAlertTracker, number: int, body: str) -> None:
        pytest.fail(reason)

    monkeypatch.setattr(ProductionAlertTracker, "comment", _comment)


def _forbid_close(monkeypatch: pytest.MonkeyPatch, reason: str) -> None:
    def _close(self: ProductionAlertTracker, number: int, *, comment: str) -> None:
        pytest.fail(reason)

    monkeypatch.setattr(ProductionAlertTracker, "close", _close)


def test_reconcile_creates_on_a_first_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    _existing(monkeypatch, None)
    created: list[str] = []

    def _create(self: ProductionAlertTracker, body: str) -> str:
        created.append(body)
        return "https://github.com/owner/repo/issues/9"

    monkeypatch.setattr(ProductionAlertTracker, "create", _create)
    _forbid_comment(monkeypatch, "must not comment on a first failure")
    _forbid_close(monkeypatch, "must not close on a failure")

    outcome = reconcile_alert(
        ProductionAlertTracker("owner/repo"),
        _failing_report(),
        base_url=BASE_URL,
        checked_at=CHECKED_AT,
    )

    assert created
    assert "opened" in outcome


def test_reconcile_updates_rather_than_duplicates_on_a_repeat_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _existing(monkeypatch, OpenAlert(number=5))
    commented: list[tuple[int, str]] = []

    def _comment(self: ProductionAlertTracker, number: int, body: str) -> None:
        commented.append((number, body))

    _forbid_create(monkeypatch, "must not duplicate an open alert")
    monkeypatch.setattr(ProductionAlertTracker, "comment", _comment)
    _forbid_close(monkeypatch, "must not close on a failure")

    outcome = reconcile_alert(
        ProductionAlertTracker("owner/repo"),
        _failing_report(),
        base_url=BASE_URL,
        checked_at=CHECKED_AT,
    )

    assert commented == [(5, commented[0][1])]
    assert "updated" in outcome


def test_reconcile_closes_on_recovery(monkeypatch: pytest.MonkeyPatch) -> None:
    _existing(monkeypatch, OpenAlert(number=5))
    closed: list[tuple[int, str]] = []

    def _close(self: ProductionAlertTracker, number: int, *, comment: str) -> None:
        closed.append((number, comment))

    _forbid_create(monkeypatch, "must not create on recovery")
    _forbid_comment(monkeypatch, "must not comment on recovery")
    monkeypatch.setattr(ProductionAlertTracker, "close", _close)

    outcome = reconcile_alert(
        ProductionAlertTracker("owner/repo"),
        _healthy_report(),
        base_url=BASE_URL,
        checked_at=CHECKED_AT,
    )

    assert closed == [(5, closed[0][1])]
    assert "closed" in outcome


def test_reconcile_does_nothing_when_healthy_with_no_open_alert(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _existing(monkeypatch, None)
    _forbid_create(monkeypatch, "must not create when healthy")
    _forbid_comment(monkeypatch, "must not comment when healthy")
    _forbid_close(monkeypatch, "must not close with nothing open")

    outcome = reconcile_alert(
        ProductionAlertTracker("owner/repo"),
        _healthy_report(),
        base_url=BASE_URL,
        checked_at=CHECKED_AT,
    )

    assert "no open alert" in outcome or "healthy" in outcome
