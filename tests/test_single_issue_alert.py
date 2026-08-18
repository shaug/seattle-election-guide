"""Behavior tests for the shared single-issue alert tracker (issue #387).

Direct coverage for `single_issue_alert`'s own logic -- the four-branch
decision table, marker matching, the tracker base class's four `gh`-calling
methods, and the generic reconcile branching -- independent of
`test_production_alert.py` and `test_link_rot_alert.py`, which cover the
same shape only indirectly through the two domain wrappers built on top of
it.
"""

from __future__ import annotations

import json
import subprocess
from subprocess import CompletedProcess
from typing import Any

import pytest

from election_guide.single_issue_alert import (
    AlertAction,
    OpenAlert,
    SingleIssueAlertTracker,
    plan_alert_action,
    reconcile,
)

MARKER = "widget-check:monitor"


@pytest.fixture(autouse=True)
def forbid_subprocess(monkeypatch: pytest.MonkeyPatch) -> None:
    def _forbidden(*args: Any, **kwargs: Any) -> CompletedProcess[str]:
        raise AssertionError(
            f"a test reached subprocess.run{args[:1]}; stub SingleIssueAlertTracker or "
            "subprocess.run instead"
        )

    monkeypatch.setattr(subprocess, "run", _forbidden)


def _tracker(repository: str = "owner/repo") -> SingleIssueAlertTracker:
    return SingleIssueAlertTracker(
        repository,
        marker=MARKER,
        issue_title="A widget stopped working",
        issue_labels=("type: ops", "area: operations"),
        kind="widget-check",
    )


def _completed(command: list[str], stdout: str = "", code: int = 0) -> CompletedProcess[str]:
    return CompletedProcess(command, code, stdout=stdout, stderr="")


# --- plan_alert_action: the four-branch decision table ---------------------


def test_a_healthy_check_with_no_open_alert_does_nothing() -> None:
    assert plan_alert_action(healthy=True, existing_alert_number=None) == AlertAction.NONE


def test_a_healthy_check_with_an_open_alert_closes_it() -> None:
    assert plan_alert_action(healthy=True, existing_alert_number=7) == AlertAction.CLOSE


def test_a_failing_check_with_no_open_alert_creates_one() -> None:
    assert plan_alert_action(healthy=False, existing_alert_number=None) == AlertAction.CREATE


def test_a_failing_check_with_an_open_alert_updates_it_instead_of_duplicating() -> None:
    assert plan_alert_action(healthy=False, existing_alert_number=7) == AlertAction.UPDATE


# --- SingleIssueAlertTracker.find_open_alert: command shape and marker matching ---


def test_find_open_alert_lists_only_open_issues_scoped_to_the_repository(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    recorded: dict[str, Any] = {}

    def _run(command: list[str], **kwargs: Any) -> CompletedProcess[str]:
        recorded["command"] = command
        return _completed(command, json.dumps([{"number": 5, "body": f"details\n\n{MARKER}\n"}]))

    monkeypatch.setattr(subprocess, "run", _run)

    found = _tracker().find_open_alert()

    assert found == OpenAlert(number=5)
    command = recorded["command"]
    assert command[:3] == ["gh", "issue", "list"]
    assert command[command.index("--repo") + 1] == "owner/repo"
    assert command[command.index("--state") + 1] == "open"
    assert command[command.index("--json") + 1] == "number,body"


def test_find_open_alert_ignores_an_issue_without_the_marker(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def _run(command: list[str], **kwargs: Any) -> CompletedProcess[str]:
        return _completed(command, json.dumps([{"number": 5, "body": "an unrelated open issue"}]))

    monkeypatch.setattr(subprocess, "run", _run)

    assert _tracker().find_open_alert() is None


def test_find_open_alert_ignores_a_different_trackers_marker(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Two `SingleIssueAlertTracker` instances must not answer for each other."""

    def _run(command: list[str], **kwargs: Any) -> CompletedProcess[str]:
        return _completed(
            command, json.dumps([{"number": 5, "body": "details\n\nother-check:monitor\n"}])
        )

    monkeypatch.setattr(subprocess, "run", _run)

    assert _tracker().find_open_alert() is None


def test_a_quoted_marker_does_not_count(monkeypatch: pytest.MonkeyPatch) -> None:
    """Only the last non-empty line counts, matching the calendar tracker's convention."""

    def _run(command: list[str], **kwargs: Any) -> CompletedProcess[str]:
        quoting = f"This system posts a line like\n\n    {MARKER}\n\nat the end of its issues."
        return _completed(command, json.dumps([{"number": 5, "body": quoting}]))

    monkeypatch.setattr(subprocess, "run", _run)

    assert _tracker().find_open_alert() is None


def test_find_open_alert_returns_none_when_nothing_is_open(monkeypatch: pytest.MonkeyPatch) -> None:
    def _run(command: list[str], **kwargs: Any) -> CompletedProcess[str]:
        return _completed(command, "[]")

    monkeypatch.setattr(subprocess, "run", _run)

    assert _tracker().find_open_alert() is None


def test_find_open_alert_refuses_to_truncate(monkeypatch: pytest.MonkeyPatch) -> None:
    from election_guide.github_cli import ISSUE_QUERY_LIMIT

    payload = json.dumps([{"number": index + 1, "body": "x"} for index in range(ISSUE_QUERY_LIMIT)])

    def _run(command: list[str], **kwargs: Any) -> CompletedProcess[str]:
        return _completed(command, payload)

    monkeypatch.setattr(subprocess, "run", _run)

    with pytest.raises(ValueError, match="listing limit"):
        _tracker().find_open_alert()


def test_a_failing_cli_is_reported_with_the_trackers_own_kind(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def _run(command: list[str], **kwargs: Any) -> CompletedProcess[str]:
        return _completed(command, "", code=1)

    monkeypatch.setattr(subprocess, "run", _run)

    with pytest.raises(ValueError, match="could not list open widget-check issues"):
        _tracker().find_open_alert()


def test_a_missing_cli_is_reported(monkeypatch: pytest.MonkeyPatch) -> None:
    def _run(command: list[str], **kwargs: Any) -> CompletedProcess[str]:
        raise FileNotFoundError(command[0])

    monkeypatch.setattr(subprocess, "run", _run)

    with pytest.raises(ValueError, match="GitHub CLI is required"):
        _tracker().find_open_alert()


# --- SingleIssueAlertTracker.create -----------------------------------------


def test_create_opens_a_titled_labeled_issue_carrying_the_body(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    recorded: dict[str, Any] = {}

    def _run(command: list[str], **kwargs: Any) -> CompletedProcess[str]:
        recorded["command"] = command
        return _completed(command, "https://github.com/owner/repo/issues/9\n")

    monkeypatch.setattr(subprocess, "run", _run)

    url = _tracker().create("the body")

    assert url == "https://github.com/owner/repo/issues/9"
    command = recorded["command"]
    assert command[:3] == ["gh", "issue", "create"]
    assert command[command.index("--title") + 1] == "A widget stopped working"
    assert command[command.index("--body") + 1] == "the body"
    assert [command[i + 1] for i, part in enumerate(command) if part == "--label"] == [
        "type: ops",
        "area: operations",
    ]


def test_a_failing_create_is_reported_with_the_trackers_own_kind(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def _run(command: list[str], **kwargs: Any) -> CompletedProcess[str]:
        return _completed(command, "", code=1)

    monkeypatch.setattr(subprocess, "run", _run)

    with pytest.raises(ValueError, match="could not open the widget-check alert issue"):
        _tracker().create("the body")


# --- SingleIssueAlertTracker.comment ----------------------------------------


def test_comment_posts_the_body_to_the_existing_issue(monkeypatch: pytest.MonkeyPatch) -> None:
    recorded: dict[str, Any] = {}

    def _run(command: list[str], **kwargs: Any) -> CompletedProcess[str]:
        recorded["command"] = command
        return _completed(command)

    monkeypatch.setattr(subprocess, "run", _run)

    _tracker().comment(5, "an update")

    command = recorded["command"]
    assert command[:3] == ["gh", "issue", "comment"]
    assert command[3] == "5"
    assert command[command.index("--body") + 1] == "an update"


def test_a_failing_comment_is_reported_with_the_trackers_own_kind(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def _run(command: list[str], **kwargs: Any) -> CompletedProcess[str]:
        return _completed(command, "", code=1)

    monkeypatch.setattr(subprocess, "run", _run)

    with pytest.raises(ValueError, match="could not update widget-check alert issue #5"):
        _tracker().comment(5, "an update")


# --- SingleIssueAlertTracker.close ------------------------------------------


def test_close_closes_with_a_recovery_comment(monkeypatch: pytest.MonkeyPatch) -> None:
    recorded: dict[str, Any] = {}

    def _run(command: list[str], **kwargs: Any) -> CompletedProcess[str]:
        recorded["command"] = command
        return _completed(command)

    monkeypatch.setattr(subprocess, "run", _run)

    _tracker().close(5, comment="recovered")

    command = recorded["command"]
    assert command[:3] == ["gh", "issue", "close"]
    assert command[3] == "5"
    assert command[command.index("--comment") + 1] == "recovered"


def test_a_failing_close_is_reported_with_the_trackers_own_kind(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def _run(command: list[str], **kwargs: Any) -> CompletedProcess[str]:
        return _completed(command, "", code=1)

    monkeypatch.setattr(subprocess, "run", _run)

    with pytest.raises(ValueError, match="could not close widget-check alert issue #5"):
        _tracker().close(5, comment="recovered")


# --- reconcile ---------------------------------------------------------------
#
# Stubs monkeypatch the tracker's own methods, matching how the two domain
# wrappers' own tests stub their trackers, rather than a duck-typed double --
# reconcile takes a real SingleIssueAlertTracker.


def _existing(monkeypatch: pytest.MonkeyPatch, alert: OpenAlert | None) -> None:
    def _find(self: SingleIssueAlertTracker) -> OpenAlert | None:
        return alert

    monkeypatch.setattr(SingleIssueAlertTracker, "find_open_alert", _find)


def _forbid_render(reason: str) -> Any:
    def _render() -> str:
        pytest.fail(reason)

    return _render


def test_reconcile_creates_on_a_first_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    _existing(monkeypatch, None)
    created: list[str] = []

    def _create(self: SingleIssueAlertTracker, body: str) -> str:
        created.append(body)
        return "https://github.com/owner/repo/issues/9"

    monkeypatch.setattr(SingleIssueAlertTracker, "create", _create)

    outcome = reconcile(
        _tracker(),
        healthy=False,
        render_body=lambda: "the body",
        render_recovery_comment=_forbid_render("must not render a recovery comment on a failure"),
    )

    assert created == ["the body"]
    assert "opened" in outcome


def test_reconcile_updates_rather_than_duplicates_on_a_repeat_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _existing(monkeypatch, OpenAlert(number=5))
    commented: list[tuple[int, str]] = []

    def _comment(self: SingleIssueAlertTracker, number: int, body: str) -> None:
        commented.append((number, body))

    def _forbid_create(self: SingleIssueAlertTracker, body: str) -> str:
        pytest.fail("must not duplicate an open alert")

    monkeypatch.setattr(SingleIssueAlertTracker, "comment", _comment)
    monkeypatch.setattr(SingleIssueAlertTracker, "create", _forbid_create)

    outcome = reconcile(
        _tracker(),
        healthy=False,
        render_body=lambda: "the body",
        render_recovery_comment=_forbid_render("must not render a recovery comment on a failure"),
    )

    assert commented == [(5, "the body")]
    assert "updated" in outcome


def test_reconcile_closes_on_recovery(monkeypatch: pytest.MonkeyPatch) -> None:
    _existing(monkeypatch, OpenAlert(number=5))
    closed: list[tuple[int, str]] = []

    def _close(self: SingleIssueAlertTracker, number: int, *, comment: str) -> None:
        closed.append((number, comment))

    monkeypatch.setattr(SingleIssueAlertTracker, "close", _close)

    outcome = reconcile(
        _tracker(),
        healthy=True,
        render_body=_forbid_render("must not render a body on recovery"),
        render_recovery_comment=lambda: "recovered",
    )

    assert closed == [(5, "recovered")]
    assert "closed" in outcome


def test_reconcile_does_nothing_when_healthy_with_no_open_alert(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _existing(monkeypatch, None)

    outcome = reconcile(
        _tracker(),
        healthy=True,
        render_body=_forbid_render("must not render a body when healthy"),
        render_recovery_comment=_forbid_render(
            "must not render a recovery comment with nothing open"
        ),
    )

    assert "no open alert" in outcome or "healthy" in outcome
