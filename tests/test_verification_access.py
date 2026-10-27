"""Prospective access limitations preserve evidence, failure clocks and finite tasks."""

import json
from datetime import date
from pathlib import Path
from typing import Any

import pytest
from typer.testing import CliRunner

from election_guide.cli import app
from tests.test_verification_runtime import run_fixture, setup_verification_fixture

runner = CliRunner()
SOURCE = "seattle-times-editorial-board"


def test_manual_access_failure_is_a_failed_observation_not_a_successful_acknowledgement(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    policy, state, fixtures = setup_verification_fixture(tmp_path, monkeypatch)
    run_fixture(policy, state, fixtures, "2026-10-26")
    root = state / "wa-2026-general"
    old = {p: p.read_bytes() for p in root.rglob("*.json")}
    result = runner.invoke(
        app,
        [
            "verification",
            "record-access-failure",
            str(policy),
            "--state-root",
            str(state),
            "--election-id",
            "wa-2026-general",
            "--source-id",
            SOURCE,
            "--scheduled-for",
            "2026-10-26",
            "--checked-at",
            "2026-10-26T20:00:00Z",
            "--reviewer",
            "Fixture observer",
            "--evidence",
            "Fixture failed-access observation; no real publisher request.",
            "--category",
            "http_status",
            "--http-status",
            "403",
        ],
    )
    assert result.exit_code == 0, result.output
    check = json.loads(result.output)
    assert check["status"] == "failed" and check["mode"] == "human"
    assert check["checked_at"] == "2026-10-26T20:00:00Z"
    assert "access_disposition" not in check
    event = json.loads((root / "refreshes" / f"{check['event_id']}.json").read_text())
    assert event["status"] == "failed" and event["capture_id"] is None
    assert event["snapshot_id"] is None and event["content_changed"] is None
    assert event["access_failure"] == {
        "stage": "http_fetch",
        "category": "http_status",
        "http_status": 403,
    }
    assert all(p.read_bytes() == raw for p, raw in old.items())
    repeated = runner.invoke(app, access_failure_arguments(policy, state))
    assert repeated.exit_code == 0 and json.loads(repeated.output) == check
    assert len(list((root / "refreshes").glob(f"refresh-{SOURCE}-*.json"))) == 1


def access_failure_arguments(policy: Path, state: Path) -> list[str]:
    return [
        "verification",
        "record-access-failure",
        str(policy),
        "--state-root",
        str(state),
        "--election-id",
        "wa-2026-general",
        "--source-id",
        SOURCE,
        "--scheduled-for",
        "2026-10-26",
        "--checked-at",
        "2026-10-26T20:00:00Z",
        "--reviewer",
        "Fixture observer",
        "--evidence",
        "Fixture failed-access observation; no real publisher request.",
        "--category",
        "http_status",
        "--http-status",
        "403",
    ]


def setup_access_policy(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[Path, Path, Path]:
    from datetime import datetime

    import yaml

    from election_guide.collection import verification_access
    from election_guide.collection.verification_review import acknowledge_manual

    policy, state, fixtures = setup_verification_fixture(tmp_path, monkeypatch)
    run_fixture(policy, state, fixtures, "2026-10-26")
    acknowledge_manual(
        state / "wa-2026-general",
        SOURCE,
        date(2026, 10, 26),
        "Fixture original reviewer",
        datetime.fromisoformat("2026-10-26T18:00:00+00:00"),
        "Fixture original accepted source review; generic acknowledgement alone is insufficient.",
    )
    data = yaml.safe_load(policy.read_text())
    data["schema_version"] = "1.1"
    data["access_failures"] = {"effective_from": "2026-10-27", "disposition": "retain_verified"}
    policy.write_text(yaml.safe_dump(data))
    monkeypatch.chdir(tmp_path)
    evidence = tmp_path / "data/review"
    evidence.mkdir(parents=True)
    (evidence / "complete-review.json").write_text(
        json.dumps(
            {
                "source_id": SOURCE,
                "election_id": "wa-2026-general",
                "reviewer": "Fixture original reviewer",
                "reviewed_at": "2026-10-26T17:00:00Z",
                "scope": "complete official publication and all supported mappings",
                "facts": ["fixture fact"],
            }
        )
    )
    (evidence / "acceptance.json").write_text(
        json.dumps(
            {
                "source_id": SOURCE,
                "election_id": "wa-2026-general",
                "accepted_by": "Fixture original accepter",
                "accepted_at": "2026-10-26T18:00:00Z",
                "accepted_review": "complete-review.json",
            }
        )
    )
    monkeypatch.setattr(
        verification_access, "utc_now", lambda: datetime.fromisoformat("2026-10-26T20:00:00+00:00")
    )
    return policy, state, fixtures


def qualify(
    root: Path, tmp_path: Path, *, scope: str = "complete_official_publication_and_mappings"
) -> dict[str, Any]:
    import hashlib

    refs: list[dict[str, Any]] = []
    for name in ("complete-review.json", "acceptance.json"):
        path = tmp_path / "data/review" / name
        refs.append(
            {"path": f"data/review/{name}", "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
        )
    refs[1].update({"actor_pointer": "/accepted_by", "time_pointer": "/accepted_at"})
    payload = {
        "source_id": SOURCE,
        "election_id": "wa-2026-general",
        "scope": scope,
        "official_urls": ["https://www.seattletimes.com/opinion/editorials/endorsements/"],
        "original_reviewer": "Fixture original reviewer",
        "reviewed_at": "2026-10-26T17:00:00Z",
        "accepted_by": "Fixture original accepter",
        "accepted_at": "2026-10-26T18:00:00Z",
        "review_evidence": refs[0],
        "acceptance_evidence": refs[1],
    }
    path = tmp_path / "qualification-input.json"
    path.write_text(json.dumps(payload))
    result = runner.invoke(
        app,
        [
            "verification",
            "qualify-initial-review",
            str(root),
            str(path),
            "--recorded-by",
            "Fixture qualification recorder",
            "--policy-path",
            str(tmp_path / "policy.yaml"),
        ],
    )
    if scope != "complete_official_publication_and_mappings":
        assert result.exit_code != 0
        return {}
    assert result.exit_code == 0, result.output
    return json.loads(result.output)


def failure(policy: Path, state: Path, day: str) -> dict[str, Any]:
    args = access_failure_arguments(policy, state)
    args[args.index("--scheduled-for") + 1] = day
    args[args.index("--checked-at") + 1] = day + "T18:00:00Z"
    result = runner.invoke(app, args)
    assert result.exit_code == 0, result.output
    return json.loads(result.output)


def test_qualified_future_failure_is_handled_without_advancing_last_success(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from datetime import date, datetime

    from election_guide.collection import verification_access
    from election_guide.collection.verification import plan_verification, read_policy
    from election_guide.collection.verification_tasks import task_sections

    policy, state, fixtures = setup_access_policy(tmp_path, monkeypatch)
    original = {p: p.read_bytes() for p in (state / "wa-2026-general").rglob("*.json")}
    qualification = qualify(state / "wa-2026-general", tmp_path)
    assert qualification["original_reviewer"] == "Fixture original reviewer"
    assert qualification["reviewed_at"] == "2026-10-26T17:00:00Z"
    assert qualification["recorded_by"] == "Fixture qualification recorder"
    assert qualification["recorded_at"] == "2026-10-26T20:00:00Z"
    monkeypatch.setattr(
        verification_access, "utc_now", lambda: datetime.fromisoformat("2026-10-27T19:00:00+00:00")
    )
    run_fixture(policy, state, fixtures, "2026-10-27")
    check = failure(policy, state, "2026-10-27")
    assert (
        check["status"] == "failed"
        and check["access_disposition"]["disposition"] == "retained_verified_with_limitation"
    )
    coverage = plan_verification(read_policy(policy), state, date(2026, 10, 27)).model_dump(
        mode="json"
    )
    lane = next(c for c in coverage["elections"][0]["coverage"] if c["source_id"] == SOURCE)
    assert lane["last_successful_check"] == "2026-10-26T18:00:00Z"
    assert lane["latest_attempt"]["status"] == "failed" and lane["freshness"] == "access_limited"
    assert lane["next_due"] == "2026-10-28" and lane["due"] is False
    sections = [
        s
        for s in task_sections(
            read_policy(policy), state, date(2026, 10, 27), "example/guide", "a" * 40, watch=False
        )
        if s["source_id"] == SOURCE and s["day"] == "2026-10-27"
    ]
    assert len(sections) == 1 and sections[0]["handled"] is True
    assert "not a successful verification" in sections[0]["body"]
    assert "Fixture original reviewer" in sections[0]["body"]
    assert "HTTP 403" in sections[0]["body"]
    assert all(p.read_bytes() == raw for p, raw in original.items())


def test_generic_manual_ack_and_partial_review_do_not_qualify(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from datetime import datetime

    from election_guide.collection import verification_access

    policy, state, fixtures = setup_access_policy(tmp_path, monkeypatch)
    qualify(state / "wa-2026-general", tmp_path, scope="retained_subset_only")
    monkeypatch.setattr(
        verification_access, "utc_now", lambda: datetime.fromisoformat("2026-10-27T19:00:00+00:00")
    )
    run_fixture(policy, state, fixtures, "2026-10-27")
    check = failure(policy, state, "2026-10-27")
    assert "access_disposition" not in check


def test_later_qualification_and_new_policy_never_backfill_old_dispositions(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from datetime import date, datetime

    from election_guide.collection import verification_access
    from election_guide.collection.verification import read_policy
    from election_guide.collection.verification_tasks import task_sections

    policy, state, fixtures = setup_access_policy(tmp_path, monkeypatch)
    monkeypatch.setattr(
        verification_access, "utc_now", lambda: datetime.fromisoformat("2026-10-27T19:00:00+00:00")
    )
    run_fixture(policy, state, fixtures, "2026-10-27")
    check = failure(policy, state, "2026-10-27")
    old = {p: p.read_bytes() for p in state.rglob("*.json")}
    qualify(state / "wa-2026-general", tmp_path)
    sections = task_sections(
        read_policy(policy), state, date(2026, 10, 27), "example/guide", "a" * 40, watch=False
    )
    assert all(not s.get("handled", False) for s in sections if s["source_id"] == SOURCE)
    assert "access_disposition" not in check
    assert all(p.read_bytes() == raw for p, raw in old.items())


@pytest.mark.parametrize(
    "error",
    [
        "parser found no decisions",
        "incomplete publication",
        "conflicting choices",
        "unknown ValueError",
    ],
)
def test_intervening_unresolved_content_or_unknown_failure_blocks_access_disposition(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, error: str
) -> None:
    from datetime import date, datetime

    from election_guide.collection import verification_access
    from election_guide.collection.refresh import record_refresh_failure
    from election_guide.collection.verification import CheckRecord
    from election_guide.collection.verification_runtime import record_check

    policy, state, fixtures = setup_access_policy(tmp_path, monkeypatch)
    root = state / "wa-2026-general"
    qualify(root, tmp_path)
    at = datetime.fromisoformat("2026-10-27T17:00:00+00:00")
    event = record_refresh_failure(
        SOURCE, at, error, root / "refreshes", extraction_dir=root / "extractions"
    )
    record_check(
        root,
        CheckRecord(
            source_id=SOURCE,
            scheduled_for=date(2026, 10, 27),
            checked_at=at,
            status="failed",
            mode="live",
            event_id=event.id,
        ),
    )
    monkeypatch.setattr(
        verification_access, "utc_now", lambda: datetime.fromisoformat("2026-10-28T19:00:00+00:00")
    )
    run_fixture(policy, state, fixtures, "2026-10-28")
    assert "access_disposition" not in failure(policy, state, "2026-10-28")


def test_failures_keep_distinct_slot_escalation_and_recovery_uses_real_time(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from datetime import date, datetime

    from election_guide.collection import verification_access
    from election_guide.collection.verification import plan_verification, read_policy
    from election_guide.collection.verification_review import acknowledge_manual
    from election_guide.collection.verification_runtime import consecutive_failures
    from election_guide.collection.verification_tasks import task_sections

    policy, state, fixtures = setup_access_policy(tmp_path, monkeypatch)
    root = state / "wa-2026-general"
    qualify(root, tmp_path)
    monkeypatch.setattr(
        verification_access, "utc_now", lambda: datetime.fromisoformat("2026-10-30T19:00:00+00:00")
    )
    for day in ("2026-10-27", "2026-10-28", "2026-10-29"):
        run_fixture(policy, state, fixtures, day)
        assert failure(policy, state, day) == failure(policy, state, day)
    assert consecutive_failures(root, SOURCE) == 3
    sections = task_sections(
        read_policy(policy), state, date(2026, 10, 29), "example/guide", "a" * 40, watch=False
    )
    assert any(s["source_id"] == SOURCE and s["handled"] and s["escalated"] for s in sections)
    recovered = datetime.fromisoformat("2026-10-29T20:00:00+00:00")
    acknowledge_manual(
        root,
        SOURCE,
        date(2026, 10, 29),
        "Fixture recovery reviewer",
        recovered,
        "Actual fixture recovery review",
    )
    assert consecutive_failures(root, SOURCE) == 0
    lane = next(
        c
        for c in plan_verification(read_policy(policy), state, date(2026, 10, 29))
        .elections[0]
        .coverage
        if c.source_id == SOURCE
    )
    assert lane.last_successful_check == recovered and lane.freshness == "current"


def test_handled_only_comment_does_not_reopen_but_unresolved_observation_does(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from election_guide.collection import verification_tasks as tasks

    issue = {
        "number": 7,
        "state": "CLOSED",
        "body": "endorsement-verification: wa-2026-general/2026-10-27",
    }
    comments: list[dict[str, str]] = []
    calls: list[list[str]] = []

    def fake_gh(args: list[str], _error: str) -> str:
        calls.append(args)
        if args[1:3] == ["issue", "list"]:
            return json.dumps([issue])
        if args[1:3] == ["issue", "view"]:
            return json.dumps({"comments": comments})
        if args[1:3] == ["issue", "comment"]:
            comments.append({"body": Path(args[args.index("--body-file") + 1]).read_text()})
        elif args[1:3] == ["issue", "reopen"]:
            issue["state"] = "OPEN"
        else:
            raise AssertionError(args)
        return ""

    monkeypatch.setattr(tasks, "run_gh", fake_gh)
    section = {
        "election_id": "wa-2026-general",
        "day": "2026-10-27",
        "source_id": SOURCE,
        "marker": "endorsement-observation: handled-fixture",
        "body": "Failed, handled limitation\n\nendorsement-observation: handled-fixture",
        "handled": True,
        "escalated": False,
    }
    tasks.reconcile_tasks([section], "example/guide")
    assert issue["state"] == "CLOSED" and len(comments) == 1
    tasks.reconcile_tasks([section], "example/guide")
    assert len(comments) == 1
    section = {
        **section,
        "handled": False,
        "marker": "endorsement-observation: parser-fixture",
        "body": "Unresolved parser failure\n\nendorsement-observation: parser-fixture",
    }
    tasks.reconcile_tasks([section], "example/guide")
    assert issue["state"] == "OPEN" and len(comments) == 2


def test_qualification_cannot_relabel_the_original_review_actor(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    policy, state, _fixtures = setup_access_policy(tmp_path, monkeypatch)
    root = state / "wa-2026-general"
    qualify(root, tmp_path)
    path = tmp_path / "qualification-input.json"
    data = json.loads(path.read_text())
    data["original_reviewer"] = "Someone who did not perform this review"
    path.write_text(json.dumps(data))
    result = runner.invoke(
        app,
        [
            "verification",
            "qualify-initial-review",
            str(root),
            str(path),
            "--recorded-by",
            "Fixture qualifier",
            "--policy-path",
            str(policy),
        ],
    )
    assert result.exit_code != 0
    assert len(list((root / "source-reviews").glob("*.json"))) == 1


def test_policy_activation_does_not_handle_an_older_dated_obligation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from datetime import datetime

    from election_guide.collection import verification_access

    policy, state, _fixtures = setup_access_policy(tmp_path, monkeypatch)
    qualify(state / "wa-2026-general", tmp_path)
    monkeypatch.setattr(
        verification_access, "utc_now", lambda: datetime.fromisoformat("2026-10-28T19:00:00+00:00")
    )
    # Even a newly recorded, later failed attempt cannot apply the future default to an old slot.
    result = runner.invoke(app, access_failure_arguments(policy, state))
    assert result.exit_code == 0, result.output
    assert "access_disposition" not in json.loads(result.output)


@pytest.mark.parametrize(
    "problem,qualified,handled",
    [
        ("http403", True, True),
        ("http403", False, False),
        ("http404", True, False),
        ("unknown", True, False),
        ("network_ebadf", True, False),
        ("http200_partial", True, False),
    ],
)
def test_automatic_access_failure_requires_qualification_and_typed_transport_proof(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, problem: str, qualified: bool, handled: bool
) -> None:
    import hashlib
    from datetime import datetime

    import yaml

    from election_guide.collection import verification_access
    from election_guide.collection.http import HttpArtifact
    from election_guide.collection.verification import read_policy
    from election_guide.collection.verification_runtime import run_verification

    source = "seiu-775"
    policy_path, state, fixtures = setup_verification_fixture(tmp_path, monkeypatch, source)
    run_verification(
        read_policy(policy_path),
        state,
        datetime.fromisoformat("2026-10-26T16:00:00+00:00"),
        live=False,
        fixtures=fixtures,
    )
    data = yaml.safe_load(policy_path.read_text())
    data.update(
        schema_version="1.1",
        access_failures={"effective_from": "2026-10-27", "disposition": "retain_verified"},
    )
    policy_path.write_text(yaml.safe_dump(data))
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        verification_access, "utc_now", lambda: datetime.fromisoformat("2026-10-26T20:00:00+00:00")
    )
    if qualified:
        directory = tmp_path / "data/review"
        directory.mkdir(parents=True)
        review = directory / "review.json"
        accepted = directory / "accepted.json"
        review.write_text(
            json.dumps(
                {
                    "source_id": source,
                    "election_id": "wa-2026-general",
                    "reviewer": "Fixture source reviewer",
                    "reviewed_at": "2026-10-26T17:00:00Z",
                }
            )
        )
        accepted.write_text(
            json.dumps(
                {
                    "source_id": source,
                    "election_id": "wa-2026-general",
                    "reviewer": "Fixture source accepter",
                    "reviewed_at": "2026-10-26T18:00:00Z",
                }
            )
        )
        evidence = {
            "source_id": source,
            "election_id": "wa-2026-general",
            "scope": "complete_official_publication_and_mappings",
            "official_urls": ["https://seiu775.org/endorsements/"],
            "original_reviewer": "Fixture source reviewer",
            "reviewed_at": "2026-10-26T17:00:00Z",
            "accepted_by": "Fixture source accepter",
            "accepted_at": "2026-10-26T18:00:00Z",
            "review_evidence": {
                "path": "data/review/review.json",
                "sha256": hashlib.sha256(review.read_bytes()).hexdigest(),
            },
            "acceptance_evidence": {
                "path": "data/review/accepted.json",
                "sha256": hashlib.sha256(accepted.read_bytes()).hexdigest(),
            },
        }
        input_path = tmp_path / "initial-review.json"
        input_path.write_text(json.dumps(evidence))
        result = runner.invoke(
            app,
            [
                "verification",
                "qualify-initial-review",
                str(state / "wa-2026-general"),
                str(input_path),
                "--recorded-by",
                "Fixture qualifier",
                "--policy-path",
                str(policy_path),
            ],
        )
        assert result.exit_code == 0, result.output

    def fetch(url: str) -> HttpArtifact:
        if problem == "http200_partial":
            return HttpArtifact(
                b"<p>Partial publication, no recognized choices.</p>", 200, url, [], "text/html"
            )
        if problem == "network_ebadf":
            raise OSError(9, "Bad file descriptor")
        if problem == "unknown":
            raise ValueError("Unclassified problem")
        raise ValueError(
            "live collection returned HTTP " + ("403" if problem == "http403" else "404")
        )

    monkeypatch.setattr("election_guide.collection.verification_runtime.fetch_http", fetch)
    report = run_verification(
        read_policy(policy_path),
        state,
        datetime.fromisoformat("2026-10-27T18:00:00+00:00"),
        live=True,
        fixtures=None,
    )
    failure_result = report["automatic"][0]
    assert failure_result["status"] == "failed"
    assert bool(failure_result.get("access_disposition")) is handled
    assert failure_result["baseline_reviewed"] is False  # Qualification is NOT collector adoption.
    assert failure_result["consecutive_failures"] == 1


def test_explicitly_incomplete_original_is_not_overridden_by_qualification_scope(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import hashlib

    policy, state, _fixtures = setup_access_policy(tmp_path, monkeypatch)
    root = state / "wa-2026-general"
    qualify(root, tmp_path)
    # A supplied retained subset is not an initial complete official-publication review.
    review = tmp_path / "data/review/complete-review.json"
    data = json.loads(review.read_text())
    data["complete_live_website_or_linked_publication_discovery"] = False
    review.write_text(json.dumps(data))
    payload_path = tmp_path / "qualification-input.json"
    payload = json.loads(payload_path.read_text())
    payload["review_evidence"]["sha256"] = hashlib.sha256(review.read_bytes()).hexdigest()
    payload_path.write_text(json.dumps(payload))
    result = runner.invoke(
        app,
        [
            "verification",
            "qualify-initial-review",
            str(root),
            str(payload_path),
            "--recorded-by",
            "Fixture qualifier",
            "--policy-path",
            str(policy),
        ],
    )
    assert result.exit_code != 0
    assert len(list((root / "source-reviews").glob("*.json"))) == 1


def test_genuine_legacy_run_keeps_its_immutable_serialization_identity() -> None:
    from election_guide.collection.verification import RunAudit
    from election_guide.evidence.models import evidence_fingerprint

    original = sorted((Path(__file__).parents[1] / "data/verification/runs").glob("*.json"))[0]
    raw = json.loads(original.read_text())
    assert evidence_fingerprint(raw) == original.stem
    assert RunAudit.model_validate(raw).model_dump(mode="json") == raw


def test_genuine_legacy_markers_leave_closed630_636_unchanged(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from datetime import datetime

    from election_guide.collection import verification_tasks as tasks
    from election_guide.collection.refresh import read_refresh_event, record_refresh_failure
    from election_guide.collection.verification import CheckRecord, read_checks, read_policy
    from election_guide.collection.verification_runtime import record_check
    from election_guide.evidence.models import evidence_fingerprint

    repo = Path(__file__).parents[1]
    historical = repo / "data/verification/wa-2026-general"
    state = tmp_path / "state"
    root = state / "wa-2026-general"
    for name in ("checks", "refreshes", "extractions"):
        (root / name).mkdir(parents=True)
    filenames = [
        "9b7b1d4e7ceeaf567b30256183a369b3aee7f3029153a5a0680e86e642d01840",
        "a14fb233a9a11113c063d8c551a867569042ea2ff5380c437d52f2f4c1f2945d",
    ]
    for identity in filenames:
        original = historical / "checks" / (identity + ".json")
        raw = json.loads(original.read_text())
        (root / "checks" / original.name).write_bytes(original.read_bytes())
        event_path = historical / "refreshes" / (raw["event_id"] + ".json")
        (root / "refreshes" / event_path.name).write_bytes(event_path.read_bytes())
        event = read_refresh_event(event_path)
        assert event.model_dump(mode="json") == json.loads(event_path.read_text())
        if event.previous_snapshot_id:
            snapshot = historical / "extractions" / (event.previous_snapshot_id + ".json")
            (root / "extractions" / snapshot.name).write_bytes(snapshot.read_bytes())
    for check in read_checks(root):
        raw_path = root / "checks" / (evidence_fingerprint(check.model_dump(mode="json")) + ".json")
        assert check.model_dump(mode="json") == json.loads(raw_path.read_text())
        assert check.access_disposition is None
    policy = read_policy(repo / "config/verification.yaml")
    sections = tasks.task_sections(
        policy, state, date(2026, 10, 28), "example/guide", "a" * 40, watch=False
    )
    assert {s["marker"].rsplit("/", 1)[1] for s in sections} == set(filenames)
    issues = [
        {
            "number": number,
            "state": "CLOSED",
            "body": f"endorsement-verification: wa-2026-general/{day}",
        }
        for number, day in [(630, "2026-10-25"), (636, "2026-10-26"), (700, "2026-10-28")]
    ]
    comments = {
        str(number): [{"body": next(s["marker"] for s in sections if s["day"] == day)}]
        for number, day in [(630, "2026-10-25"), (636, "2026-10-26")]
    }
    comments["700"] = []
    reopen_count = 0

    def fake_gh(args: list[str], _error: str) -> str:
        nonlocal reopen_count
        if args[1:3] == ["issue", "list"]:
            return json.dumps(issues)
        if args[1:3] == ["issue", "view"]:
            return json.dumps({"comments": comments[args[3]]})
        if args[1:3] == ["issue", "reopen"]:
            next(i for i in issues if str(i["number"]) == args[3])["state"] = "OPEN"
            reopen_count += 1
        elif args[1:3] == ["issue", "comment"]:
            comments[args[3]].append(
                {"body": Path(args[args.index("--body-file") + 1]).read_text()}
            )
        elif args[1:3] != ["issue", "edit"]:
            raise AssertionError(args)
        return ""

    monkeypatch.setattr(tasks, "run_gh", fake_gh)
    assert tasks.reconcile_tasks(sections, "example/guide") == []
    assert all(i["state"] == "CLOSED" for i in issues) and reopen_count == 0
    at = datetime.fromisoformat("2026-10-28T18:00:00+00:00")
    event = record_refresh_failure(
        "seiu-775",
        at,
        "New unresolved parser failure fixture",
        root / "refreshes",
        extraction_dir=root / "extractions",
    )
    record_check(
        root,
        CheckRecord(
            source_id="seiu-775",
            scheduled_for=date(2026, 10, 28),
            checked_at=at,
            status="failed",
            mode="live",
            event_id=event.id,
        ),
    )
    sections = tasks.task_sections(
        policy, state, date(2026, 10, 28), "example/guide", "a" * 40, watch=False
    )
    tasks.reconcile_tasks(sections, "example/guide")
    assert [i["state"] for i in issues] == ["CLOSED", "CLOSED", "OPEN"] and reopen_count == 1
    tasks.reconcile_tasks(sections, "example/guide")
    assert (
        reopen_count == 1
        and len(comments["630"]) == len(comments["636"]) == len(comments["700"]) == 1
    )
