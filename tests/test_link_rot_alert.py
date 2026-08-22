"""Behavior tests for reconciling the single link-rot alert issue (O17).

Mirrors `test_production_alert.py`'s coverage of the same open/update/close
shape, plus the consecutive-run confirmation this check adds on top of it.
"""

from __future__ import annotations

import json
import subprocess
from subprocess import CompletedProcess
from typing import Any

import pytest

from election_guide.sources.link_check import LinkCheckResult, LinkCheckTarget
from election_guide.sources.link_check_state import LinkCheckState
from election_guide.sources.link_rot_alert import (
    ISSUE_LABELS,
    ISSUE_TITLE,
    MARKER,
    AlertAction,
    LinkRotAlertTracker,
    OpenAlert,
    confirmed_failures,
    next_state,
    plan_alert_action,
    reconcile_alert,
    render_alert_body,
    render_recovery_comment,
)

CHECKED_AT = "2026-08-15T12:00:00+00:00"


@pytest.fixture(autouse=True)
def forbid_subprocess(monkeypatch: pytest.MonkeyPatch) -> None:
    """Mirror `test_production_alert.py`: nothing here may reach a real `gh` by accident."""

    def _forbidden(*args: Any, **kwargs: Any) -> CompletedProcess[str]:
        raise AssertionError(
            f"a test reached subprocess.run{args[:1]}; stub LinkRotAlertTracker or "
            "subprocess.run instead"
        )

    monkeypatch.setattr(subprocess, "run", _forbidden)


def _target(source_id: str, url: str) -> LinkCheckTarget:
    return LinkCheckTarget(source_id=source_id, source_name=f"{source_id} org", url=url)


def _result(source_id: str, url: str, *, ok: bool, error: str | None = None) -> LinkCheckResult:
    return LinkCheckResult(target=_target(source_id, url), ok=ok, error=error)


# --- failure-cause classification ----------------------------------------

# `fetch_http` catches its own failures and re-raises them wrapped, so the
# string `check_link` records is `f"live collection failed: {cause}"` -- the
# shape every failure in issue #399 actually took. The bare causes below are
# how issue #406 quotes them; both forms are exercised, because the bare form
# is the contract as written and the wrapped form is the one that arrives.
#
# These are spelled out as prose on purpose, rather than imported from
# `election_guide.collection.http` the way the classifier itself now is. The
# classifier follows a reworded constant automatically; only an independent
# copy of the expected text can notice that the constant no longer says what
# the check was built to recognize. Rewording one of those constants without
# meaning to turns this file red, which is the whole point of it.
INCONCLUSIVE_CAUSES = (
    "live collection returned HTTP 401",
    "live collection returned HTTP 403",
    "live collection returned HTTP 429",
    "live collection returned HTTP 503",
    "live collection exceeded 10 redirects",
    "live collection refuses an HTTPS downgrade redirect",
    # A timeout during DNS resolution that loses the race to the outer
    # deadline check arrives with its own cause rather than the flat message.
    "live collection exceeded its total timeout during DNS resolution",
    # The deadline timer closing the socket under an in-flight operation,
    # observed live on 2026-08-22 against a page that is not gone.
    "[Errno 9] Bad file descriptor",
)

# The outer handler replaces the cause entirely once the deadline has passed,
# so this one is never wrapped around something else.
TIMEOUT_ERROR = "live collection failed: total timeout exceeded"

ROT_CONFIRMING_CAUSES = (
    "live collection returned HTTP 404",
    "live collection returned HTTP 410",
    "live collection DNS resolution failed for 'dead.example'",
    "live collection DNS resolution returned no addresses for 'dead.example'",
    # `_open_public_connection` re-raises the operating system's own `OSError`,
    # which carries no recognizable marker of its own.
    "[Errno 61] Connection refused",
    "[Errno 65] No route to host",
)


def _wrapped(cause: str) -> str:
    return f"live collection failed: {cause}"


def _confirmed_across(url: str, *causes: str) -> list[LinkCheckResult]:
    """Drive the real multi-run pipeline: fail, carry state forward, fail again.

    Returns what the final run confirms, having asserted that no earlier run
    confirmed anything -- the first can never confirm, and an intermediate one
    that did would make the final result unattributable.
    """
    state = LinkCheckState()
    confirmed: list[LinkCheckResult] = []
    for index, cause in enumerate(causes):
        this_run = [_result("a", url, ok=False, error=cause)]
        confirmed = confirmed_failures(this_run, state)
        if index < len(causes) - 1:
            assert confirmed == [], f"run {index + 1} confirmed before the last run"
        state = next_state(this_run)
    return confirmed


# --- confirmed_failures ------------------------------------------------


def test_a_failure_repeating_from_the_previous_run_is_confirmed() -> None:
    results = [_result("a", "https://a.example", ok=False, error="404")]
    previous = next_state(results)

    assert confirmed_failures(results, previous) == results


def test_a_first_time_failure_is_not_confirmed() -> None:
    results = [_result("a", "https://a.example", ok=False, error="404")]

    assert confirmed_failures(results, LinkCheckState()) == []


def test_a_recovered_url_is_never_confirmed_even_if_previously_failing() -> None:
    previous = next_state([_result("a", "https://a.example", ok=False, error="404")])
    results = [_result("a", "https://a.example", ok=True)]

    assert confirmed_failures(results, previous) == []


def test_a_broken_url_is_confirmed_only_after_two_consecutive_failing_runs() -> None:
    """The O17 acceptance scenario: a fixture URL fails twice, one
    `sources check-links` run apart, before it is ever reported."""
    run_one = [_result("broken", "https://dead.example", ok=False, error="HTTP 404")]
    assert confirmed_failures(run_one, LinkCheckState()) == []

    state_after_run_one = next_state(run_one)
    run_two = [_result("broken", "https://dead.example", ok=False, error="HTTP 404")]
    assert confirmed_failures(run_two, state_after_run_one) == run_two


@pytest.mark.parametrize("cause", INCONCLUSIVE_CAUSES)
def test_an_inconclusive_cause_is_never_confirmed_however_often_it_repeats(cause: str) -> None:
    """Access control, rate limiting, a redirect loop, a downgrade refusal, and
    a timeout each say how the site answered a robot, not whether the page is
    gone. Three runs, not two: the point is that no run count reaches confirmed."""
    assert _confirmed_across("https://guarded.example", cause, cause, cause) == []


@pytest.mark.parametrize("cause", INCONCLUSIVE_CAUSES)
def test_an_inconclusive_cause_is_never_confirmed_in_the_form_fetch_http_raises_it(
    cause: str,
) -> None:
    wrapped = _wrapped(cause)

    assert _confirmed_across("https://guarded.example", wrapped, wrapped, wrapped) == []


def test_a_timeout_is_never_confirmed() -> None:
    assert _confirmed_across("https://slow.example", TIMEOUT_ERROR, TIMEOUT_ERROR) == []


@pytest.mark.parametrize("cause", ROT_CONFIRMING_CAUSES)
def test_a_rot_confirming_cause_repeating_is_still_confirmed(cause: str) -> None:
    """Unchanged from before this classification existed: a URL that is gone,
    unresolvable, or unreachable at the socket still alerts on the second run."""
    wrapped = _wrapped(cause)

    assert _confirmed_across("https://dead.example", wrapped, wrapped) == [
        _result("a", "https://dead.example", ok=False, error=wrapped)
    ]


def test_a_cause_that_turns_conclusive_between_runs_is_not_confirmed_from_that_pair() -> None:
    """One 404 after one 403 is one 404, and one is never enough."""
    assert (
        _confirmed_across(
            "https://flaky.example",
            _wrapped("live collection returned HTTP 403"),
            _wrapped("live collection returned HTTP 404"),
        )
        == []
    )


def test_a_cause_that_turns_inconclusive_between_runs_is_not_confirmed_from_that_pair() -> None:
    assert (
        _confirmed_across(
            "https://flaky.example",
            _wrapped("live collection returned HTTP 404"),
            _wrapped("live collection returned HTTP 403"),
        )
        == []
    )


def test_two_rot_confirming_runs_confirm_even_across_different_causes() -> None:
    """Confirmation asks whether both runs were evidence of rot, not whether
    they were evidence of the same rot: a 404 that becomes unresolvable is
    still a page nobody can reach twice running."""
    assert _confirmed_across(
        "https://dead.example",
        _wrapped("live collection returned HTTP 404"),
        _wrapped("live collection DNS resolution failed for 'dead.example'"),
    ) == [
        _result(
            "a",
            "https://dead.example",
            ok=False,
            error=_wrapped("live collection DNS resolution failed for 'dead.example'"),
        )
    ]


# --- next_state ----------------------------------------------------------


def test_next_state_carries_forward_only_this_runs_failing_urls() -> None:
    results = [
        _result("a", "https://a.example", ok=False, error="404"),
        _result("b", "https://b.example", ok=True),
    ]

    assert next_state(results) == LinkCheckState(
        failing_urls=("https://a.example",), rot_confirming_urls=("https://a.example",)
    )


def test_next_state_still_records_an_inconclusive_failure_among_the_failing_urls() -> None:
    """The full failing set stays the operator-facing record of the run; only
    the rot-confirming subset is what the next run confirms against."""
    results = [
        _result(
            "guarded",
            "https://guarded.example",
            ok=False,
            error=_wrapped("live collection returned HTTP 403"),
        ),
        _result(
            "dead",
            "https://dead.example",
            ok=False,
            error=_wrapped("live collection returned HTTP 404"),
        ),
    ]

    assert next_state(results) == LinkCheckState(
        failing_urls=("https://dead.example", "https://guarded.example"),
        rot_confirming_urls=("https://dead.example",),
    )


# --- plan_alert_action -------------------------------------------------


def test_no_confirmed_failures_with_no_open_alert_does_nothing() -> None:
    assert plan_alert_action(has_confirmed=False, existing_alert_number=None) == AlertAction.NONE


def test_no_confirmed_failures_with_an_open_alert_closes_it() -> None:
    assert plan_alert_action(has_confirmed=False, existing_alert_number=7) == AlertAction.CLOSE


def test_confirmed_failures_with_no_open_alert_creates_one() -> None:
    assert plan_alert_action(has_confirmed=True, existing_alert_number=None) == AlertAction.CREATE


def test_confirmed_failures_with_an_open_alert_updates_it_instead_of_duplicating() -> None:
    assert plan_alert_action(has_confirmed=True, existing_alert_number=7) == AlertAction.UPDATE


# --- rendering -----------------------------------------------------------


def test_the_alert_body_embeds_the_marker_as_its_final_line() -> None:
    body = render_alert_body(
        [_result("a", "https://a.example", ok=False, error="404")], checked_at=CHECKED_AT
    )

    assert body.rstrip().endswith(MARKER)


def test_the_alert_body_names_every_confirmed_failing_source_and_url() -> None:
    confirmed = [
        _result("the-stranger", "https://a.example", ok=False, error="HTTP 404"),
        _result("urbanist", "https://b.example", ok=False, error="DNS failure"),
    ]

    body = render_alert_body(confirmed, checked_at=CHECKED_AT)

    assert "the-stranger" in body
    assert "https://a.example" in body
    assert "HTTP 404" in body
    assert "urbanist" in body
    assert "https://b.example" in body
    assert "DNS failure" in body
    assert CHECKED_AT in body


def test_the_recovery_comment_names_when_it_recovered() -> None:
    assert CHECKED_AT in render_recovery_comment(CHECKED_AT)


# --- LinkRotAlertTracker -----------------------------------------------


def _completed(command: list[str], stdout: str = "", code: int = 0) -> CompletedProcess[str]:
    return CompletedProcess(command, code, stdout=stdout, stderr="")


def test_find_open_alert_reads_only_open_issues(monkeypatch: pytest.MonkeyPatch) -> None:
    recorded: dict[str, Any] = {}

    def _run(command: list[str], **kwargs: Any) -> CompletedProcess[str]:
        recorded["command"] = command
        return _completed(command, json.dumps([{"number": 5, "body": f"details\n\n{MARKER}\n"}]))

    monkeypatch.setattr(subprocess, "run", _run)

    found = LinkRotAlertTracker("owner/repo").find_open_alert()

    assert found == OpenAlert(number=5)
    command = recorded["command"]
    assert command[:3] == ["gh", "issue", "list"]
    assert "--state" in command and command[command.index("--state") + 1] == "open"


def test_find_open_alert_ignores_an_issue_without_the_marker(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def _run(command: list[str], **kwargs: Any) -> CompletedProcess[str]:
        return _completed(command, json.dumps([{"number": 5, "body": "an unrelated open issue"}]))

    monkeypatch.setattr(subprocess, "run", _run)

    assert LinkRotAlertTracker("owner/repo").find_open_alert() is None


def test_find_open_alert_returns_none_when_nothing_is_open(monkeypatch: pytest.MonkeyPatch) -> None:
    def _run(command: list[str], **kwargs: Any) -> CompletedProcess[str]:
        return _completed(command, "[]")

    monkeypatch.setattr(subprocess, "run", _run)

    assert LinkRotAlertTracker("owner/repo").find_open_alert() is None


def test_create_opens_a_titled_labeled_issue_carrying_the_body(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    recorded: dict[str, Any] = {}

    def _run(command: list[str], **kwargs: Any) -> CompletedProcess[str]:
        recorded["command"] = command
        return _completed(command, "https://github.com/owner/repo/issues/9\n")

    monkeypatch.setattr(subprocess, "run", _run)
    body = render_alert_body(
        [_result("a", "https://a.example", ok=False, error="404")], checked_at=CHECKED_AT
    )

    url = LinkRotAlertTracker("owner/repo").create(body)

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

    LinkRotAlertTracker("owner/repo").comment(5, "body text")

    command = recorded["command"]
    assert command[:3] == ["gh", "issue", "comment"]
    assert command[3] == "5"
    assert command[command.index("--body") + 1] == "body text"


def test_close_closes_with_a_recovery_comment(monkeypatch: pytest.MonkeyPatch) -> None:
    recorded: dict[str, Any] = {}

    def _run(command: list[str], **kwargs: Any) -> CompletedProcess[str]:
        recorded["command"] = command
        return _completed(command)

    monkeypatch.setattr(subprocess, "run", _run)

    LinkRotAlertTracker("owner/repo").close(5, comment="recovered")

    command = recorded["command"]
    assert command[:3] == ["gh", "issue", "close"]
    assert command[3] == "5"
    assert command[command.index("--comment") + 1] == "recovered"


def test_a_failing_cli_is_reported(monkeypatch: pytest.MonkeyPatch) -> None:
    def _run(command: list[str], **kwargs: Any) -> CompletedProcess[str]:
        return _completed(command, "", code=1)

    monkeypatch.setattr(subprocess, "run", _run)

    with pytest.raises(ValueError, match="could not list open link-rot-check issues"):
        LinkRotAlertTracker("owner/repo").find_open_alert()


# --- reconcile_alert -------------------------------------------------------


def _existing(monkeypatch: pytest.MonkeyPatch, alert: OpenAlert | None) -> None:
    def _find(self: LinkRotAlertTracker) -> OpenAlert | None:
        return alert

    monkeypatch.setattr(LinkRotAlertTracker, "find_open_alert", _find)


def _forbid_create(monkeypatch: pytest.MonkeyPatch, reason: str) -> None:
    def _create(self: LinkRotAlertTracker, body: str) -> str:
        pytest.fail(reason)

    monkeypatch.setattr(LinkRotAlertTracker, "create", _create)


def _forbid_comment(monkeypatch: pytest.MonkeyPatch, reason: str) -> None:
    def _comment(self: LinkRotAlertTracker, number: int, body: str) -> None:
        pytest.fail(reason)

    monkeypatch.setattr(LinkRotAlertTracker, "comment", _comment)


def _forbid_close(monkeypatch: pytest.MonkeyPatch, reason: str) -> None:
    def _close(self: LinkRotAlertTracker, number: int, *, comment: str) -> None:
        pytest.fail(reason)

    monkeypatch.setattr(LinkRotAlertTracker, "close", _close)


def test_reconcile_creates_on_a_first_confirmed_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    _existing(monkeypatch, None)
    created: list[str] = []

    def _create(self: LinkRotAlertTracker, body: str) -> str:
        created.append(body)
        return "https://github.com/owner/repo/issues/9"

    monkeypatch.setattr(LinkRotAlertTracker, "create", _create)
    _forbid_comment(monkeypatch, "must not comment on a first confirmed failure")
    _forbid_close(monkeypatch, "must not close on a failure")

    outcome = reconcile_alert(
        LinkRotAlertTracker("owner/repo"),
        [_result("a", "https://a.example", ok=False, error="404")],
        checked_at=CHECKED_AT,
    )

    assert created
    assert "opened" in outcome


def test_reconcile_updates_rather_than_duplicates_on_a_repeat_confirmed_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _existing(monkeypatch, OpenAlert(number=5))
    commented: list[tuple[int, str]] = []

    def _comment(self: LinkRotAlertTracker, number: int, body: str) -> None:
        commented.append((number, body))

    _forbid_create(monkeypatch, "must not duplicate an open alert")
    monkeypatch.setattr(LinkRotAlertTracker, "comment", _comment)
    _forbid_close(monkeypatch, "must not close on a failure")

    outcome = reconcile_alert(
        LinkRotAlertTracker("owner/repo"),
        [_result("a", "https://a.example", ok=False, error="404")],
        checked_at=CHECKED_AT,
    )

    assert commented == [(5, commented[0][1])]
    assert "updated" in outcome


def test_reconcile_closes_on_recovery(monkeypatch: pytest.MonkeyPatch) -> None:
    _existing(monkeypatch, OpenAlert(number=5))
    closed: list[tuple[int, str]] = []

    def _close(self: LinkRotAlertTracker, number: int, *, comment: str) -> None:
        closed.append((number, comment))

    _forbid_create(monkeypatch, "must not create on recovery")
    _forbid_comment(monkeypatch, "must not comment on recovery")
    monkeypatch.setattr(LinkRotAlertTracker, "close", _close)

    outcome = reconcile_alert(LinkRotAlertTracker("owner/repo"), [], checked_at=CHECKED_AT)

    assert closed == [(5, closed[0][1])]
    assert "closed" in outcome


def test_reconcile_does_nothing_when_nothing_is_confirmed_and_no_open_alert(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _existing(monkeypatch, None)
    _forbid_create(monkeypatch, "must not create when nothing is confirmed")
    _forbid_comment(monkeypatch, "must not comment when nothing is confirmed")
    _forbid_close(monkeypatch, "must not close with nothing open")

    outcome = reconcile_alert(LinkRotAlertTracker("owner/repo"), [], checked_at=CHECKED_AT)

    assert "no open alert" in outcome or "healthy" in outcome
