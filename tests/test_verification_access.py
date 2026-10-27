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
        "Fixture source review; generic acknowledgement alone is insufficient.",
    )
    data = yaml.safe_load(policy.read_text())
    data["schema_version"] = "1.1"
    data["access_failures"] = {"effective_from": "2026-10-27", "disposition": "retain_verified"}
    policy.write_text(yaml.safe_dump(data))
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(verification_access, "_REPOSITORY_ROOT", tmp_path)
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs/accepted-review.md").write_text(
        "Fixture durable complete-publication facts/review packet; no actual source request.\n"
    )
    monkeypatch.setattr(
        verification_access, "utc_now", lambda: datetime.fromisoformat("2026-10-26T20:00:00+00:00")
    )
    return policy, state, fixtures


def qualify(
    root: Path,
    tmp_path: Path,
    *,
    scope: str = "complete_official_publication_and_mappings",
    admitted: bool = True,
    source_id: str = SOURCE,
    official_url: str = "https://www.seattletimes.com/opinion/editorials/endorsements/",
    reviewer: str = "Fixture original reviewer",
    checked_at: str = "2026-10-26T16:00:00Z",
    reviewed_at: str = "2026-10-26T17:00:00Z",
) -> dict[str, Any]:
    result = runner.invoke(
        app,
        [
            "verification",
            "qualify-initial-review",
            str(root),
            "--policy-path",
            str(tmp_path / "policy.yaml"),
            "--source-id",
            source_id,
            "--scope",
            scope,
            "--official-url",
            official_url,
            "--checked-at",
            checked_at,
            "--reviewer",
            reviewer,
            "--reviewed-at",
            reviewed_at,
            "--evidence",
            "docs/accepted-review.md",
            "--recorded-by",
            "Fixture qualification recorder",
        ],
    )
    if scope != "complete_official_publication_and_mappings":
        assert result.exit_code != 0
        return {}
    assert result.exit_code == 0, result.output
    if admitted:
        admit_qualifications(root, tmp_path)
    return json.loads(result.output)


def initialize_admission_repo(repo: Path) -> None:
    import subprocess

    if (repo / ".git").exists():
        return
    for args in [
        ["init", "-q", "--initial-branch=main"],
        ["config", "user.name", "Fixture"],
        ["config", "user.email", "fixture@example.test"],
        ["commit", "--allow-empty", "-qm", "Accepted main fixture"],
        ["update-ref", "refs/remotes/origin/main", "HEAD"],
    ]:
        subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True)


def copy_qualification_proposal(root: Path, repo: Path) -> None:
    import subprocess

    initialize_admission_repo(repo)
    target = repo / "data/verification" / root.name / "source-reviews"
    target.mkdir(parents=True, exist_ok=True)
    for path in (root / "source-reviews").glob("*.json"):
        (target / path.name).write_bytes(path.read_bytes())
    subprocess.run(["git", "add", "data/verification"], cwd=repo, check=True, capture_output=True)
    subprocess.run(
        ["git", "commit", "--allow-empty", "-qm", "Proposed complete-review attestation fixture"],
        cwd=repo,
        check=True,
        capture_output=True,
    )


def admit_qualifications(root: Path, repo: Path) -> None:
    import subprocess

    copy_qualification_proposal(root, repo)
    # Local isolated fixture of the existing trusted, already fetched protected-main authority.
    subprocess.run(
        ["git", "update-ref", "refs/remotes/origin/main", "HEAD"],
        cwd=repo,
        check=True,
        capture_output=True,
    )


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


@pytest.mark.parametrize("content_changed", [True, False, None])
def test_intervening_observed_content_failure_blocks_access_disposition(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, content_changed: bool | None
) -> None:
    from datetime import date, datetime

    from election_guide.collection import verification_access
    from election_guide.collection.refresh import record_refresh_failure
    from election_guide.collection.verification import CheckRecord
    from election_guide.collection.verification_runtime import record_check
    from election_guide.evidence.models import CaptureRequest
    from election_guide.evidence.storage import read_capture_manifest, record_observation

    policy, state, fixtures = setup_access_policy(tmp_path, monkeypatch)
    root = state / "wa-2026-general"
    qualify(root, tmp_path)
    at = datetime.fromisoformat("2026-10-27T17:00:00+00:00")
    capture_id = None
    if content_changed is None:
        path = tmp_path / "uncompared-publication.html"
        path.write_text("Fixture publication observed but not successfully compared.\n")
        request = CaptureRequest(
            source_id=SOURCE,
            requested_url="https://www.seattletimes.com/opinion/editorials/",
            canonical_url="https://www.seattletimes.com/opinion/editorials/",
            retrieved_at=at,
            title="Uncompared fixture publication; no real source request",
            media_type="text/html",
            capture_method="manual_upload",
            redistribution="restricted",
            redistribution_note="Authored local fixture observation; no publisher access.",
        )
        capture_id = read_capture_manifest(record_observation(request, path, root / "manifests")).id
    event = record_refresh_failure(
        SOURCE,
        at,
        "Fixture observed publication could not be parsed completely",
        root / "refreshes",
        extraction_dir=root / "extractions",
        content_changed=content_changed,
        capture_id=capture_id,
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


def test_old_ambiguous_failure_stays_unresolved_without_blocking_new_typed_access_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from datetime import datetime

    from election_guide.collection import verification_access
    from election_guide.collection.refresh import record_refresh_failure
    from election_guide.collection.verification import CheckRecord, read_policy
    from election_guide.collection.verification_runtime import consecutive_failures, record_check
    from election_guide.collection.verification_tasks import task_sections

    policy, state, fixtures = setup_access_policy(tmp_path, monkeypatch)
    root = state / "wa-2026-general"
    qualify(root, tmp_path)
    at = datetime.fromisoformat("2026-10-27T17:00:00+00:00")
    event = record_refresh_failure(
        SOURCE,
        at,
        "Source check failed (ValueError); inspect official access and adapter.",
        root / "refreshes",
        extraction_dir=root / "extractions",
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
    old_bytes = {p: p.read_bytes() for p in root.rglob("*.json")}
    monkeypatch.setattr(
        verification_access, "utc_now", lambda: datetime.fromisoformat("2026-10-28T19:00:00+00:00")
    )
    run_fixture(policy, state, fixtures, "2026-10-28")
    new = failure(policy, state, "2026-10-28")
    assert new["access_disposition"]["disposition"] == "retained_verified_with_limitation"
    assert new["status"] == "failed"
    assert consecutive_failures(root, SOURCE) == 2
    old_sections = task_sections(
        read_policy(policy), state, date(2026, 10, 27), "example/guide", "a" * 40, watch=False
    )
    assert all(
        not item.get("handled", False) for item in old_sections if item["source_id"] == SOURCE
    )
    assert all(p.read_bytes() == raw for p, raw in old_bytes.items())


@pytest.mark.parametrize("reason", ["parse", "incomplete_publication", "conflicting_evidence"])
def test_explicit_intervening_review_reason_blocks_until_later_complete_review(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, reason: Any
) -> None:
    from datetime import datetime

    from election_guide.collection import verification_access
    from election_guide.collection.refresh import record_refresh_failure
    from election_guide.collection.verification import CheckRecord
    from election_guide.collection.verification_runtime import record_check

    policy, state, fixtures = setup_access_policy(tmp_path, monkeypatch)
    root = state / "wa-2026-general"
    qualify(root, tmp_path)
    at = datetime.fromisoformat("2026-10-27T17:00:00+00:00")
    event = record_refresh_failure(
        SOURCE,
        at,
        "Fixture positively identified incomplete or conflicting publication",
        root / "refreshes",
        extraction_dir=root / "extractions",
        review_required=reason,
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
    old_bytes = {p: p.read_bytes() for p in root.rglob("*.json")}
    monkeypatch.setattr(
        verification_access, "utc_now", lambda: datetime.fromisoformat("2026-10-28T19:00:00+00:00")
    )
    run_fixture(policy, state, fixtures, "2026-10-28")
    failed = failure(policy, state, "2026-10-28")
    assert "access_disposition" not in failed
    qualify(
        root,
        tmp_path,
        checked_at="2026-10-28T16:00:00Z",
        reviewed_at="2026-10-28T17:00:00Z",
        reviewer="Fixture later complete reviewer",
    )
    monkeypatch.setattr(
        verification_access, "utc_now", lambda: datetime.fromisoformat("2026-10-29T19:00:00+00:00")
    )
    run_fixture(policy, state, fixtures, "2026-10-29")
    assert failure(policy, state, "2026-10-29")["access_disposition"]["disposition"] == (
        "retained_verified_with_limitation"
    )
    assert all(p.read_bytes() == raw for p, raw in old_bytes.items())
    assert "access_disposition" not in failed


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


def test_pending_changed_attestation_cannot_replace_admitted_original_actor(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from datetime import datetime

    from election_guide.collection import verification_access
    from election_guide.evidence.models import evidence_fingerprint

    policy, state, fixtures = setup_access_policy(tmp_path, monkeypatch)
    root = state / "wa-2026-general"
    original = qualify(root, tmp_path)
    qualify(root, tmp_path, admitted=False, reviewer="Unreviewed changed actor fixture")
    monkeypatch.setattr(
        verification_access, "utc_now", lambda: datetime.fromisoformat("2026-10-27T19:00:00+00:00")
    )
    run_fixture(policy, state, fixtures, "2026-10-27")
    check = failure(policy, state, "2026-10-27")
    assert check["access_disposition"]["qualification_id"] == evidence_fingerprint(original)
    assert original["original_reviewer"] == "Fixture original reviewer"


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
    monkeypatch.setattr(verification_access, "_REPOSITORY_ROOT", tmp_path)
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs/accepted-review.md").write_text(
        "Fixture source facts/review packet, no real source access.\n"
    )
    monkeypatch.setattr(
        verification_access, "utc_now", lambda: datetime.fromisoformat("2026-10-26T20:00:00+00:00")
    )
    if qualified:
        qualify(
            state / "wa-2026-general",
            tmp_path,
            source_id=source,
            official_url="https://seiu775.org/endorsements/",
            reviewer="Fixture source reviewer",
        )

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
    assert failure_result["baseline_reviewed"] is False
    assert failure_result["consecutive_failures"] == 1


def test_admission_requires_exact_attestation_bytes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import subprocess
    from datetime import datetime

    from election_guide.collection import verification_access

    policy, state, fixtures = setup_access_policy(tmp_path, monkeypatch)
    root = state / "wa-2026-general"
    qualify(root, tmp_path)
    admitted = next((tmp_path / "data/verification/wa-2026-general/source-reviews").glob("*.json"))
    admitted.write_bytes(admitted.read_bytes() + b"\n")
    subprocess.run(
        ["git", "add", str(admitted.relative_to(tmp_path))],
        cwd=tmp_path,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "commit", "-qm", "Different admitted bytes fixture"],
        cwd=tmp_path,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "update-ref", "refs/remotes/origin/main", "HEAD"],
        cwd=tmp_path,
        check=True,
        capture_output=True,
    )
    monkeypatch.setattr(
        verification_access, "utc_now", lambda: datetime.fromisoformat("2026-10-27T19:00:00+00:00")
    )
    run_fixture(policy, state, fixtures, "2026-10-27")
    assert "access_disposition" not in failure(policy, state, "2026-10-27")


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


def test_pending_attestation_is_not_authority_without_main_admission(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import subprocess
    from datetime import datetime

    from election_guide.collection import verification_access
    from election_guide.evidence.models import evidence_fingerprint

    policy, state, fixtures = setup_access_policy(tmp_path, monkeypatch)
    root = state / "wa-2026-general"
    qualify(root, tmp_path, admitted=False)
    initialize_admission_repo(tmp_path)
    subprocess.run(
        ["git", "switch", "-c", "codex/endorsement-verification-state"],
        cwd=tmp_path,
        check=True,
        capture_output=True,
    )
    copy_qualification_proposal(root, tmp_path)
    monkeypatch.setattr(
        verification_access, "utc_now", lambda: datetime.fromisoformat("2026-10-27T19:00:00+00:00")
    )
    run_fixture(policy, state, fixtures, "2026-10-27")
    old = failure(policy, state, "2026-10-27")
    assert "access_disposition" not in old
    old_path = root / "checks" / (evidence_fingerprint(old) + ".json")
    old_bytes = old_path.read_bytes()
    admit_qualifications(root, tmp_path)
    assert failure(policy, state, "2026-10-27") == old  # No late main admission backfill.
    monkeypatch.setattr(
        verification_access, "utc_now", lambda: datetime.fromisoformat("2026-10-28T19:00:00+00:00")
    )
    run_fixture(policy, state, fixtures, "2026-10-28")
    assert (
        failure(policy, state, "2026-10-28")["access_disposition"]["disposition"]
        == "retained_verified_with_limitation"
    )
    assert old_path.read_bytes() == old_bytes


def test_complete_review_attestation_accepts_ordinary_durable_reference(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    policy, state, _fixtures = setup_access_policy(tmp_path, monkeypatch)
    path = tmp_path / "docs/accepted-review.md"
    path.parent.mkdir(exist_ok=True)
    path.write_text(
        "Fixture complete official-publication/mapping review; no new source request.\n"
    )
    result = runner.invoke(
        app,
        [
            "verification",
            "qualify-initial-review",
            str(state / "wa-2026-general"),
            "--policy-path",
            str(policy),
            "--source-id",
            SOURCE,
            "--scope",
            "complete_official_publication_and_mappings",
            "--official-url",
            "https://www.seattletimes.com/opinion/editorials/endorsements/",
            "--checked-at",
            "2026-10-26T16:00:00Z",
            "--reviewer",
            "Fixture original reviewer",
            "--reviewed-at",
            "2026-10-26T17:00:00Z",
            "--evidence",
            "docs/accepted-review.md",
            "--recorded-by",
            "Fixture qualification recorder",
        ],
    )
    assert result.exit_code == 0, result.output
    attestation = json.loads(result.output)
    assert attestation["checked_at"] == "2026-10-26T16:00:00Z"
    assert attestation["evidence"] == "docs/accepted-review.md"
    assert attestation["original_reviewer"] == "Fixture original reviewer"
    assert attestation["recorded_by"] == "Fixture qualification recorder"


@pytest.mark.parametrize(
    "source_id,official_url",
    [
        (
            "washington-stonewall-democrats",
            "https://sites.google.com/wastonewalldems.com/wadems2026endorsement/endorsement-guide",
        ),
        ("citizens-against-aipac-corruption", "https://www.trackaipac.com/endorsements"),
        ("seattle-subway", "https://seattlesubway.org/election-endorsements/"),
        ("washington-for-peace-and-justice", "https://www.instagram.com/wa4pj/p/Deh8Qd4gZen/"),
    ],
)
def test_complete_review_accepts_reviewed_official_publication_on_another_host(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, source_id: str, official_url: str
) -> None:
    _policy, state, _fixtures = setup_access_policy(tmp_path, monkeypatch)
    # These publication identities already occur in the accepted registry/review
    # records. The fixture proposes an attestation; it makes no publisher request
    # and does not infer acceptance from the URL or write an organization URL.
    attestation = qualify(
        state / "wa-2026-general",
        tmp_path,
        source_id=source_id,
        official_url=official_url,
        admitted=False,
    )
    assert attestation["source_id"] == source_id
    assert attestation["official_urls"] == [official_url]
    assert attestation["scope"] == "complete_official_publication_and_mappings"
    assert not (tmp_path / ".git").exists()


@pytest.mark.parametrize(
    "source_id,official_url",
    [
        ("not-a-registered-source", "https://example.test/official/"),
        (SOURCE, "file:///tmp/not-a-publication.html"),
        (SOURCE, "https://example.test/official/?access_token=fixture"),
    ],
)
def test_review_proposal_still_requires_registered_source_and_clean_http_url(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, source_id: str, official_url: str
) -> None:
    from datetime import datetime

    from election_guide.collection.verification import read_policy
    from election_guide.collection.verification_access import qualify_initial_review

    policy, state, _fixtures = setup_access_policy(tmp_path, monkeypatch)
    root = state / "wa-2026-general"
    with pytest.raises(ValueError):
        qualify_initial_review(
            read_policy(policy),
            root,
            source_id,
            "complete_official_publication_and_mappings",
            [official_url],
            datetime.fromisoformat("2026-10-26T16:00:00+00:00"),
            "Fixture original reviewer",
            datetime.fromisoformat("2026-10-26T17:00:00+00:00"),
            "docs/accepted-review.md",
            "Fixture qualification recorder",
        )
    assert not (root / "source-reviews").exists()


def test_unrelated_cwd_main_cannot_supply_qualification_admission(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from datetime import datetime

    from election_guide.collection import verification_access

    policy, state, fixtures = setup_access_policy(tmp_path, monkeypatch)
    qualify(state / "wa-2026-general", tmp_path)
    # cwd has the test attestation in its main; the actual runtime repository does not.
    monkeypatch.setattr(
        verification_access,
        "_REPOSITORY_ROOT",
        Path(verification_access.__file__).resolve().parents[3],
        raising=False,
    )
    monkeypatch.setattr(
        verification_access, "utc_now", lambda: datetime.fromisoformat("2026-10-27T19:00:00+00:00")
    )
    run_fixture(policy, state, fixtures, "2026-10-27")
    assert "access_disposition" not in failure(policy, state, "2026-10-27")


def test_unavailable_main_proof_keeps_access_unresolved(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import subprocess
    from datetime import datetime

    from election_guide.collection import verification_access

    policy, state, fixtures = setup_access_policy(tmp_path, monkeypatch)
    qualify(state / "wa-2026-general", tmp_path)
    subprocess.run(
        ["git", "update-ref", "-d", "refs/remotes/origin/main"],
        cwd=tmp_path,
        check=True,
        capture_output=True,
    )
    monkeypatch.setattr(
        verification_access, "utc_now", lambda: datetime.fromisoformat("2026-10-27T19:00:00+00:00")
    )
    run_fixture(policy, state, fixtures, "2026-10-27")
    assert "access_disposition" not in failure(policy, state, "2026-10-27")
