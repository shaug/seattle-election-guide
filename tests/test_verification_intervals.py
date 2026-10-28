"""Optional cadence preserves legacy slots and measures freshness on real UTC clocks."""

import json
from datetime import date, datetime
from pathlib import Path
from typing import Any

import pytest
import yaml
from typer.testing import CliRunner

from election_guide.cli import app
from election_guide.collection.verification import (
    Activation,
    CheckRecord,
    SourcePolicy,
    check_order,
    plan_verification,
    read_policy,
)
from election_guide.collection.verification_runtime import record_check

ROOT = Path(__file__).parents[1]
SOURCE = "the-stranger"
runner = CliRunner()


def test_late_slot_watch_marker_cannot_replace_an_actual_failure_at_the_same_clock() -> None:
    clock = datetime.fromisoformat("2026-10-10T18:00:00+00:00")
    failure = CheckRecord(
        source_id=SOURCE,
        scheduled_for=date(2026, 10, 9),
        checked_at=clock,
        status="failed",
        event_id="refresh-the-stranger-20261010T180000Z-0123456789ab",
        mode="live",
    )
    missed = CheckRecord(
        source_id=SOURCE,
        scheduled_for=date(2026, 10, 9),
        checked_at=clock,
        status="missed",
        mode="watch",
    )
    # Late interval execution can record absence and its actual attempt at one instant.
    # Their filename/order must not let the administrative marker win latest_attempt.
    assert sorted([failure, missed], key=check_order)[-1].status == "failed"
    reviewed = CheckRecord(
        source_id=SOURCE,
        scheduled_for=date(2026, 10, 9),
        checked_at=clock,
        status="manual",
        mode="human",
        evidence="Actual fixture review, separate from the failed observation.",
    )
    assert sorted([reviewed, failure], key=check_order)[-1].status == "manual"


def interval_policy(tmp_path: Path, interval: object = 3) -> Path:
    path = tmp_path / "policy.yaml"
    path.write_text(
        yaml.safe_dump(
            {
                "schema_version": "1.2",
                "calendar": str(ROOT / "config/calendar/elections.yaml"),
                "elections": [
                    {
                        "election_id": "wa-2026-general",
                        "registry": str(ROOT / "config/sources/wa-2026-general.yaml"),
                        "inventory": str(ROOT / "data/normalized/wa-2026-general-inventory.json"),
                        "sources": [{"source_id": SOURCE, "refresh_interval_days": interval}],
                    }
                ],
            }
        )
    )
    return path


def write_activation(state: Path, **values: object) -> Path:
    path = state / "wa-2026-general/activation.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"activated_on": "2026-09-09", "revision": "a" * 40, **values}))
    return path


def coverage(report: Any, source: str = SOURCE) -> Any:
    return next(c for c in report.elections[0].coverage if c.source_id == source)


def test_explicit_interval_uses_phase_anchors_and_preserves_late_owed_slots(tmp_path: Path) -> None:
    policy = read_policy(interval_policy(tmp_path))
    state = tmp_path / "state"
    write_activation(state, refresh_intervals={SOURCE: 3})
    result = plan_verification(policy, state, date(2026, 9, 22))
    assert [m.scheduled_for.isoformat() for m in result.missed if m.source_id == SOURCE] == [
        "2026-09-09",  # Actual late activation, not fictitious September8 work.
        "2026-09-11",
        "2026-09-14",
        "2026-09-17",
        "2026-09-18",  # Mandatory issuance anchor resets the phase, not a failed check.
        "2026-09-21",
    ]
    lane = coverage(result)
    assert lane.cadence == "interval" and lane.due is True
    assert lane.next_due == date(2026, 9, 22)
    assert lane.scheduled_for == date(2026, 9, 21)
    final = plan_verification(policy, state, date(2026, 11, 4))
    assert any(m.source_id == SOURCE and m.scheduled_for == date(2026, 11, 3) for m in final.missed)


@pytest.mark.parametrize("value", [True, False, 0, -1, 1.5, "3"])
def test_interval_rejects_nonpositive_or_not_whole_number_configuration(
    tmp_path: Path, value: object
) -> None:
    with pytest.raises(ValueError):
        read_policy(interval_policy(tmp_path, value))


def test_intervals_require_versioned_schema_and_do_not_combine_with_daily_override(
    tmp_path: Path,
) -> None:
    path = interval_policy(tmp_path)
    data = yaml.safe_load(path.read_text())
    data["schema_version"] = "1.1"
    path.write_text(yaml.safe_dump(data))
    with pytest.raises(ValueError, match=r"schema 1\.2"):
        read_policy(path)
    data["schema_version"] = "1.2"
    data["elections"][0]["sources"][0]["daily_from_collection"] = True
    path.write_text(yaml.safe_dump(data))
    with pytest.raises(ValueError, match="daily_from_collection"):
        read_policy(path)


def test_first_fixture_run_pins_only_explicit_intervals_and_uses_no_source_network(
    tmp_path: Path,
) -> None:
    policy = interval_policy(tmp_path)
    state, fixtures = tmp_path / "state", tmp_path / "fixtures"
    fixtures.mkdir()
    result = runner.invoke(
        app,
        [
            "verification",
            "run",
            str(policy),
            "--state-root",
            str(state),
            "--fixtures",
            str(fixtures),
            "--checked-at",
            "2026-09-09T18:00:00Z",
        ],
    )
    assert result.exit_code == 0, result.output
    activation = json.loads((state / "wa-2026-general/activation.json").read_text())
    assert activation["activated_on"] == "2026-09-09"
    assert activation["refresh_intervals"] == {SOURCE: 3}
    assert len(activation["revision"]) == 40
    assert json.loads(result.output)["automatic"] == []
    before = {p: p.read_bytes() for p in state.rglob("*.json")}
    same_slot = runner.invoke(
        app,
        [
            "verification",
            "run",
            str(policy),
            "--state-root",
            str(state),
            "--fixtures",
            str(fixtures),
            "--checked-at",
            "2026-09-09T20:00:00Z",
        ],
    )
    assert same_slot.exit_code == 0, same_slot.output
    assert {p: p.read_bytes() for p in state.rglob("*.json")} == before


@pytest.mark.parametrize("pin", [None, {SOURCE: 2}, {SOURCE: 3, "sage-leaders": 1}])
def test_active_cycle_recadence_fails_before_any_new_archive_write(
    tmp_path: Path, pin: dict[str, int] | None
) -> None:
    policy = interval_policy(tmp_path)
    state, fixtures = tmp_path / "state", tmp_path / "fixtures"
    fixtures.mkdir()
    write_activation(state, **({"refresh_intervals": pin} if pin is not None else {}))
    before = {p: p.read_bytes() for p in state.rglob("*.json")}
    result = runner.invoke(
        app,
        [
            "verification",
            "run",
            str(policy),
            "--state-root",
            str(state),
            "--fixtures",
            str(fixtures),
            "--checked-at",
            "2026-09-11T18:00:00Z",
        ],
    )
    assert result.exit_code == 1 and "activation" in result.output
    assert {p: p.read_bytes() for p in state.rglob("*.json")} == before


def test_removing_active_interval_is_rejected_and_legacy_omission_needs_no_git_history(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    policy = read_policy(ROOT / "config/verification.yaml")
    state = tmp_path / "state"
    activation = write_activation(state, refresh_intervals={SOURCE: 3})
    with pytest.raises(ValueError, match="activation"):
        plan_verification(policy, state, date(2026, 10, 27))
    activation.write_text('{"activated_on":"2026-09-09","revision":"' + "a" * 40 + '"}')

    def no_history(*args: object, **kwargs: object) -> None:
        pytest.fail("Omitted legacy settings must not introduce a Git-history dependency")

    monkeypatch.setattr("subprocess.run", no_history)
    report = plan_verification(policy, state, date(2026, 9, 10))
    assert coverage(report).cadence == "weekly"
    assert coverage(report, "seattle-gay-news").cadence == "daily"
    assert "refresh_interval_days" not in SourcePolicy(source_id=SOURCE).model_dump(mode="json")
    assert Activation.model_validate_json(activation.read_bytes()).model_dump(mode="json") == {
        "activated_on": "2026-09-09",
        "revision": "a" * 40,
    }
    assert len(report.elections[0].coverage) == 46
    assert all(
        "refresh_interval_days" not in s.model_dump(mode="json")
        for s in policy.elections[0].sources
    )


def manual_success(state: Path, checked_at: str, scheduled_for: str) -> None:
    record_check(
        state / "wa-2026-general",
        CheckRecord(
            source_id=SOURCE,
            scheduled_for=date.fromisoformat(scheduled_for),
            checked_at=datetime.fromisoformat(checked_at),
            status="manual",
            mode="human",
            evidence="Fixture original review and actual timestamp; no live source credit.",
        ),
    )


@pytest.mark.parametrize(
    ("clock", "due", "overdue"),
    [
        ("2026-11-01T18:59:59+00:00", False, False),
        ("2026-11-01T19:00:00+00:00", True, False),
        ("2026-11-01T19:00:01+00:00", True, True),
    ],
)
def test_fall_dst_freshness_is_elapsed_utc_not_pacific_wall_clock(
    tmp_path: Path, clock: str, due: bool, overdue: bool
) -> None:
    policy = read_policy(interval_policy(tmp_path, 1))
    state = tmp_path / "state"
    write_activation(state, activated_on="2026-10-31", refresh_intervals={SOURCE: 1})
    manual_success(state, "2026-10-31T19:00:00+00:00", "2026-10-31")  # Noon PDT.
    lane = coverage(
        plan_verification(policy, state, date(2026, 11, 1), as_of_at=datetime.fromisoformat(clock))
    )
    assert lane.freshness_due_at.isoformat() == "2026-11-01T19:00:00+00:00"  # 11am PST.
    assert lane.freshness_due is due and lane.freshness_overdue is overdue
    assert lane.last_successful_check.isoformat() == "2026-10-31T19:00:00+00:00"
    assert lane.due is True and lane.scheduled_for == date(2026, 11, 1)


def test_spring_dst_and_cli_clock_preserve_a_full_elapsed_day(tmp_path: Path) -> None:
    path = interval_policy(tmp_path, 1)
    data = yaml.safe_load(path.read_text())
    calendar = yaml.safe_load((ROOT / "config/calendar/elections.yaml").read_text())
    next(e for e in calendar["elections"] if e["id"] == "wa-2026-general")["election_date"] = date(
        2026, 3, 10
    )
    fixture_calendar = tmp_path / "synthetic-calendar.yaml"
    fixture_calendar.write_text(yaml.safe_dump(calendar))
    data["calendar"] = str(fixture_calendar)
    path.write_text(yaml.safe_dump(data))
    state = tmp_path / "state"
    write_activation(state, activated_on="2026-03-07", refresh_intervals={SOURCE: 1})
    manual_success(state, "2026-03-07T20:00:00+00:00", "2026-03-07")  # Noon PST.
    result = runner.invoke(
        app,
        [
            "verification",
            "plan",
            str(path),
            "--state-root",
            str(state),
            "--as-of",
            "2026-03-08",
            "--as-of-at",
            "2026-03-08T19:59:59Z",
        ],
    )
    assert result.exit_code == 0, result.output
    lane = next(
        c for c in json.loads(result.output)["elections"][0]["coverage"] if c["source_id"] == SOURCE
    )
    assert lane["freshness_due_at"] == "2026-03-08T20:00:00Z"  # 1pm PDT.
    assert lane["freshness_due"] is False and lane["freshness_overdue"] is False


@pytest.mark.parametrize("clock", ["2026-10-27T12:00:00", "2026-10-28T18:00:00+00:00"])
def test_evaluation_clock_requires_timezone_and_matching_pacific_date(
    tmp_path: Path, clock: str
) -> None:
    policy = read_policy(interval_policy(tmp_path))
    with pytest.raises(ValueError, match=r"timezone|Pacific"):
        plan_verification(
            policy, tmp_path / "state", date(2026, 10, 27), as_of_at=datetime.fromisoformat(clock)
        )


def test_date_only_evaluation_and_untimed_review_never_invent_freshness(tmp_path: Path) -> None:
    policy = read_policy(interval_policy(tmp_path))
    state = tmp_path / "state"
    write_activation(state, refresh_intervals={SOURCE: 3})
    (tmp_path / "accepted-factual-review.md").write_text(
        "Accepted fixture review dated2026-09-09; actual check instant unavailable."
    )
    lane = coverage(plan_verification(policy, state, date(2026, 9, 10))).model_dump(mode="json")
    assert lane["last_successful_check"] is None
    assert "freshness_due_at" not in lane and "freshness_due" not in lane
    manual_success(state, "2026-09-09T18:00:00+00:00", "2026-09-09")
    lane = coverage(plan_verification(policy, state, date(2026, 9, 10))).model_dump(mode="json")
    assert lane["freshness_due_at"] == "2026-09-12T18:00:00Z"
    assert "freshness_due" not in lane and "freshness_evaluated_at" not in lane


@pytest.mark.parametrize(
    ("success", "expected"),
    [
        ("2026-09-10T18:00:00+00:00", "2026-09-17T18:00:00+00:00"),
        ("2026-09-17T18:00:00+00:00", "2026-09-18T18:00:00+00:00"),
        ("2026-09-16T18:00:00+00:00", "2026-09-18T07:00:00+00:00"),
    ],
)
def test_default_transition_shortens_future_weekly_deadline_without_postponing_old_debt(
    tmp_path: Path, success: str, expected: str
) -> None:
    policy = read_policy(ROOT / "config/verification.yaml")
    state = tmp_path / "state"
    write_activation(state)
    manual_success(state, success, success[:10])
    lane = coverage(
        plan_verification(
            policy,
            state,
            date(2026, 9, 18),
            as_of_at=datetime.fromisoformat("2026-09-18T19:00:00+00:00"),
        )
    )
    assert lane.freshness_due_at.isoformat() == expected
    assert lane.freshness_due is True


def test_unrepresentable_deadline_is_rejected_before_runtime_writes(tmp_path: Path) -> None:
    path = interval_policy(tmp_path, 10**30)
    state = tmp_path / "state"
    write_activation(state, refresh_intervals={SOURCE: 10**30})
    manual_success(state, "2026-09-09T18:00:00+00:00", "2026-09-09")
    before = {p: p.read_bytes() for p in state.rglob("*.json")}
    with pytest.raises(ValueError, match="deadline"):
        plan_verification(read_policy(path), state, date(2026, 9, 10))
    assert {p: p.read_bytes() for p in state.rglob("*.json")} == before


def test_late_interval_failures_count_real_slots_once_then_real_recovery_updates_success(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from election_guide.collection.http import HttpArtifact
    from election_guide.collection.verification import read_checks
    from election_guide.collection.verification_review import approve_baseline
    from election_guide.collection.verification_runtime import run_verification
    from tests.test_verification_runtime import setup_verification_fixture

    path, state, _ = setup_verification_fixture(tmp_path, monkeypatch, "seiu-775")
    data = yaml.safe_load(path.read_text())
    data["schema_version"] = "1.2"
    data["elections"][0]["sources"][0]["refresh_interval_days"] = 3
    path.write_text(yaml.safe_dump(data))
    policy = read_policy(path)
    body = b"<p>Seattle City Council District 5: Nilu Jenks</p>"

    def fetch(url: str) -> HttpArtifact:
        return HttpArtifact(body, 200, url, [], "text/html")

    monkeypatch.setattr("election_guide.collection.verification_runtime.fetch_http", fetch)

    def run(day: int) -> dict[str, Any]:
        return run_verification(
            policy,
            state,
            datetime.fromisoformat(f"2026-10-{day:02}T18:00:00+00:00"),
            live=True,
            fixtures=None,
        )

    baseline = run(6)["automatic"][0]
    root = state / "wa-2026-general"
    approve_baseline(
        root,
        baseline["snapshot_id"],
        "Fixture reviewer",
        datetime.fromisoformat("2026-10-06T19:00:00+00:00"),
        "Controlled full fixture, no publisher/adoption credit.",
    )
    baseline_bytes = {p: p.read_bytes() for p in (root / "extractions").glob("*.json")}
    assert run(7)["automatic"] == []
    body = b"<p>Incomplete fixture response.</p>"
    for day, slot, count in [(10, 9, 1), (12, 12, 2), (15, 15, 3)]:
        report = run(day)
        result = report["automatic"][0]
        assert result["status"] == "failed" and result["consecutive_failures"] == count
        assert result["escalated"] is (count == 3)
        lane = next(
            c
            for c in report["coverage"]["elections"][0]["coverage"]
            if c["source_id"] == "seiu-775"
        )
        assert lane["last_successful_check"] == "2026-10-06T18:00:00Z"
        assert lane["freshness_due_at"] == "2026-10-09T18:00:00Z"
        assert any(
            c.source_id == "seiu-775"
            and c.status == "failed"
            and c.scheduled_for == date(2026, 10, slot)
            for c in read_checks(root)
        )
        before = {p: p.read_bytes() for p in state.rglob("*.json")}
        assert run(day)["automatic"] == []
        assert {p: p.read_bytes() for p in state.rglob("*.json")} == before
    assert all(p.read_bytes() == raw for p, raw in baseline_bytes.items())
    old = {p: p.read_bytes() for p in root.rglob("*.json")}
    body = b"<p>Seattle City Council District 5: Nilu Jenks</p>"
    recovered = run(18)
    assert recovered["automatic"][0]["status"] == "unchanged"
    assert recovered["automatic"][0]["consecutive_failures"] == 0
    lane = next(
        c for c in recovered["coverage"]["elections"][0]["coverage"] if c["source_id"] == "seiu-775"
    )
    assert lane["last_successful_check"] == "2026-10-18T18:00:00Z"
    assert lane["freshness_due_at"] == "2026-10-21T18:00:00Z"
    assert all(p.read_bytes() == raw for p, raw in old.items())
