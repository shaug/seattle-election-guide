"""Durable evidence uses paginated GitHub fixtures; finalization is read-only."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from functools import partial
from pathlib import Path
from typing import Any

import pytest
from typer.testing import CliRunner

from election_guide.release.automation_models import OperationReceipt, UploadReceipt
from election_guide.serialization import canonical_json_bytes
from tests.test_release_promotion import (
    promotion_setup,  # noqa: F401 # pyright: ignore[reportUnusedImport]
)
from tests.test_release_publication import (
    setup_publication,  # noqa: F401 # pyright: ignore[reportUnusedImport]
)

BOT = {"login": "github-actions[bot]", "type": "Bot", "id": 41898282}


class GitHub:
    def __init__(self) -> None:
        self.comments: list[dict[str, Any]] = []
        self.deployments: list[dict[str, Any]] = []
        self.statuses: dict[int, list[dict[str, Any]]] = {}
        self.posted: list[str] = []
        self.fail_after: int | None = None

    def run(self, command: list[str], failure: str) -> str:
        endpoint = command[2]
        if "--method" in command:
            assert command[command.index("--method") + 1] == "POST"
            assert "/comments" in endpoint
            if self.fail_after is not None and len(self.posted) >= self.fail_after:
                raise ValueError("fixture issue write unavailable")
            payload = json.loads(Path(command[command.index("--input") + 1]).read_bytes())
            body = payload["body"]
            self.posted.append(body)
            comment = {"id": len(self.comments) + 1, "user": BOT, "body": body}
            self.comments.append(comment)
            return json.dumps(comment)
        if "--paginate" not in command:
            assert "/deployments/" in endpoint
            deployment_id = int(endpoint.rsplit("/", 1)[1])
            return json.dumps(next(row for row in self.deployments if row["id"] == deployment_id))
        assert "--paginate" in command and "--slurp" in command
        if "/comments" in endpoint:
            rows = self.comments
        elif "/statuses" in endpoint:
            rows = self.statuses[int(endpoint.split("/deployments/")[1].split("/")[0])]
        else:
            assert "/deployments" in endpoint
            rows = self.deployments
        # Deliberately put the relevant records on later pages.
        return json.dumps([[], rows[:1], rows[1:]])


@pytest.fixture
def evidence_setup(
    promotion_setup: tuple[Any, ...],  # noqa: F811
    monkeypatch: pytest.MonkeyPatch,
) -> tuple[Any, ...]:
    from election_guide.release import evidence

    _, resolved, record, _, _, root, publication = promotion_setup
    api = GitHub()
    monkeypatch.setattr(evidence, "run_gh", api.run)
    monkeypatch.chdir(root)
    upload = UploadReceipt(
        publication=publication,
        producer=record.producer,
        github_deployment_id=50,
        deployment_url="https://abc123.example.pages.dev",
        uploaded_at=datetime(2026, 10, 16, tzinfo=UTC),
        source_sha=record.source_sha,
    )
    api.deployments = [
        {
            "id": 50,
            "creator": BOT,
            "environment": "production",
            "sha": upload.source_sha,
            "payload": evidence.deployment_payload(publication),
        }
    ]
    api.statuses[50] = []
    return evidence, api, resolved, publication, upload, root


def operation(publication: Any, **updates: Any) -> OperationReceipt:
    fields: dict[str, Any] = dict(
        phase="publication",
        state="published",
        producer=publication.published.candidate.producer,
        publication=publication,
        upload=None,
        verification_sha256=None,
        error=None,
    )
    fields.update(updates)
    return OperationReceipt(**fields)


def loaded(setup: tuple[Any, ...]) -> tuple[OperationReceipt, ...]:
    evidence, _, _, publication, _, _ = setup
    candidate = publication.published.candidate
    return evidence.load_verified_receipts(
        repository=candidate.producer.repository,
        issue_number=550,
        release_version=candidate.declaration.release_version,
        source_sha=candidate.source_sha,
    )


def test_publication_evidence_required_before_upload(evidence_setup: tuple[Any, ...]) -> None:
    evidence, api, _, publication, _, _ = evidence_setup
    with pytest.raises(ValueError, match="publication evidence"):
        evidence.require_publication_evidence(publication)
    evidence.retain_evidence(operation(publication), issue_number=550, reports={})
    evidence.require_publication_evidence(publication)
    conflict = publication.model_copy(
        update={"published": publication.published.model_copy(update={"asset_id": 999})}
    )
    with pytest.raises(ValueError, match="conflicting"):
        evidence.retain_evidence(operation(conflict), issue_number=550, reports={})
    assert api.posted


def test_receipts_retain_all_identities_and_unicode_reports(
    evidence_setup: tuple[Any, ...],
) -> None:
    evidence, api, _, publication, _, _ = evidence_setup
    receipt = operation(publication)
    report = canonical_json_bytes({"observations": "🗳日本語\n" * 20000})
    ids = evidence.retain_evidence(receipt, issue_number=550, reports={"observations.json": report})
    assert len(ids) > 3
    assert loaded(evidence_setup) == (receipt,)
    assert all(len(body) < 60000 for body in api.posted)
    assert evidence.read_evidence_reports(receipt, issue_number=550)["observations.json"] == report


def test_partial_comment_retry_posts_only_missing_parts(evidence_setup: tuple[Any, ...]) -> None:
    evidence, api, _, publication, _, _ = evidence_setup
    receipt = operation(publication)
    reports = {"large.json": canonical_json_bytes({"text": "é" * 50000})}
    api.comments.append(
        {"id": 1, "user": {"login": "human", "type": "User", "id": 1}, "body": "keep me"}
    )
    api.fail_after = 1
    with pytest.raises(ValueError, match="unavailable"):
        evidence.retain_evidence(receipt, issue_number=550, reports=reports)
    first = api.posted[0]
    assert loaded(evidence_setup) == ()
    api.fail_after = None
    evidence.retain_evidence(receipt, issue_number=550, reports=reports)
    assert api.posted.count(first) == 1
    assert api.comments[0]["body"] == "keep me"
    assert loaded(evidence_setup) == (receipt,)


@pytest.mark.parametrize("damage", ["hash", "truncate", "missing", "duplicate"])
def test_malformed_or_conflicting_owned_parts_fail(
    evidence_setup: tuple[Any, ...], damage: str
) -> None:
    evidence, api, _, publication, _, _ = evidence_setup
    evidence.retain_evidence(operation(publication), issue_number=550, reports={})
    if damage == "hash":
        api.comments[0]["body"] = api.comments[0]["body"].replace("\new", "\neA", 1)
    elif damage == "truncate":
        api.comments[0]["body"] = api.comments[0]["body"][:-8]
    elif damage == "missing":
        api.comments.pop(0)
    else:
        api.comments.append({**api.comments[0], "id": 999})
    with pytest.raises(ValueError):
        loaded(evidence_setup)


def test_human_marker_cannot_supply_publication(evidence_setup: tuple[Any, ...]) -> None:
    evidence, api, _, publication, _, _ = evidence_setup
    evidence.retain_evidence(operation(publication), issue_number=550, reports={})
    for comment in api.comments:
        comment["user"] = {**BOT, "id": 2}
    assert loaded(evidence_setup) == ()
    with pytest.raises(ValueError, match="publication evidence"):
        evidence.require_publication_evidence(publication)


def test_owning_issue_comes_only_from_reviewed_request(evidence_setup: tuple[Any, ...]) -> None:
    evidence, api, _, publication, _, _ = evidence_setup
    with pytest.raises(ValueError, match="issue"):
        evidence.retain_evidence(operation(publication), issue_number=1, reports={})
    assert not api.posted


def test_finalize_retry_never_uploads(
    evidence_setup: tuple[Any, ...], monkeypatch: pytest.MonkeyPatch
) -> None:
    evidence, api, resolved, publication, upload, root = evidence_setup
    from election_guide.hosting.production_wait import ProductionWaitReport
    from tests.test_production_wait import _report  # pyright: ignore[reportPrivateUsage]

    evidence.retain_evidence(operation(publication), issue_number=550, reports={})
    calls: list[Any] = []
    upload_calls: list[list[str]] = []
    original_run = evidence.subprocess.run

    def read_git_only(command: list[str], **kwargs: Any) -> Any:
        if command[:2] != ["git", "show"]:
            upload_calls.append(command)
            raise AssertionError("finalization may only read exact Git objects")
        return original_run(command, **kwargs)

    monkeypatch.setattr(evidence.subprocess, "run", read_git_only)
    declaration_path = root / "config/hosting/site.yaml"
    declaration_path.write_text("# changed checkout formatting\n" + declaration_path.read_text())
    failed = ProductionWaitReport((_report(),), (), timed_out=True)

    def probe(*args: Any, **kwargs: Any) -> ProductionWaitReport:
        calls.append(kwargs)
        assert any(item.upload == upload for item in loaded(evidence_setup))
        return failed

    monkeypatch.setattr(evidence, "wait_for_production", probe)
    producer = upload.producer.model_copy(update={"run_id": 200, "workflow_sha": "f" * 40})
    for _ in range(2):
        result = evidence.finalize_deployment(
            upload, site_manifest=resolved.site, producer=producer, output_dir=root / "out"
        )
        assert result.state == "failed"
        assert result.producer == producer
        assert result.upload == upload
    assert len(calls) == 2
    assert upload_calls == []
    assert (root / "out/production-wait.json").exists()
    # This fixture rejects every write except posting evidence; no uploader/build is imported.
    assert len({body for body in api.posted}) == len(api.posted)


def test_finalize_rejects_changed_manifest_bytes(
    evidence_setup: tuple[Any, ...], monkeypatch: pytest.MonkeyPatch
) -> None:
    evidence, _, resolved, publication, upload, root = evidence_setup
    evidence.retain_evidence(operation(publication), issue_number=550, reports={})
    bad = publication.published.candidate.model_copy(update={"site_manifest_sha256": "0" * 64})
    publication = publication.model_copy(
        update={"published": publication.published.model_copy(update={"candidate": bad})}
    )
    upload = upload.model_copy(update={"publication": publication})

    def forbidden(*args: Any, **kwargs: Any) -> None:
        raise AssertionError("must not probe mismatched trusted bytes")

    monkeypatch.setattr(evidence, "wait_for_production", forbidden)
    with pytest.raises(ValueError):
        evidence.finalize_deployment(
            upload, site_manifest=resolved.site, producer=upload.producer, output_dir=root / "out"
        )
    assert (root / "out/finalization-error.json").exists()


def test_missing_publication_reconstruction_is_explicit(evidence_setup: tuple[Any, ...]) -> None:
    evidence, _, _, publication, _, root = evidence_setup
    from election_guide.release.automation_cli import app

    path = root / "publication.json"
    path.write_bytes(canonical_json_bytes(publication.model_dump(mode="json")))
    result = CliRunner().invoke(app, ["retain-publication", "--publication", str(path)])
    assert result.exit_code == 0, result.output
    evidence.require_publication_evidence(publication)


def test_record_upload_does_not_reconstruct_missing_evidence(
    evidence_setup: tuple[Any, ...],
) -> None:
    _, api, _, publication, upload, root = evidence_setup
    from election_guide.release.automation_cli import app

    path = root / "publication.json"
    path.write_bytes(canonical_json_bytes(publication.model_dump(mode="json")))
    result = CliRunner().invoke(
        app,
        [
            "record-upload",
            "--publication",
            str(path),
            "--github-deployment-id",
            "50",
            "--deployment-url",
            upload.deployment_url,
            "--uploaded-at",
            upload.uploaded_at.isoformat(),
            "--output",
            str(root / "upload.json"),
        ],
    )
    assert result.exit_code == 1
    assert not api.posted


def test_managed_success_requires_final_evidence(evidence_setup: tuple[Any, ...]) -> None:
    evidence, api, _, publication, _, _ = evidence_setup
    payload = evidence.deployment_payload(publication)
    api.deployments = [
        {
            "id": 50,
            "creator": BOT,
            "environment": "production",
            "sha": publication.published.candidate.source_sha,
            "payload": payload,
        }
    ]
    api.statuses[50] = [{"id": 10, "state": "success", "creator": BOT}]
    with pytest.raises(ValueError, match=r"successful.*evidence"):
        evidence.latest_production_receipt("owner/repository")


@pytest.mark.parametrize("state", ["failure", "error", "pending", "queued", "in_progress"])
def test_non_successful_deployments_are_not_verified(
    evidence_setup: tuple[Any, ...], state: str
) -> None:
    evidence, api, _, publication, _, _ = evidence_setup
    api.deployments = [
        {
            "id": 50,
            "creator": BOT,
            "environment": "production",
            "sha": publication.published.candidate.source_sha,
            "payload": evidence.deployment_payload(publication),
        }
    ]
    api.statuses[50] = [{"id": 10, "state": state, "creator": BOT}]
    assert evidence.latest_production_receipt("owner/repository") is None


def test_first_activation_has_no_managed_predecessor(evidence_setup: tuple[Any, ...]) -> None:
    evidence, api, _, _, _, _ = evidence_setup
    api.deployments = [
        {"id": 1, "creator": {"login": "human"}, "payload": {}, "environment": "production"}
    ]
    assert evidence.latest_production_receipt("owner/repository") is None


def provided_report(report: Any, *args: Any, **kwargs: Any) -> Any:
    return report


def successful_report(setup: tuple[Any, ...]) -> Any:
    from election_guide.hosting.models import DeploymentManifest
    from election_guide.hosting.production_check import (
        MANIFEST_CHECK,
        CommitCheck,
        DataFreshnessCheck,
        Observation,
        ProductionCheckReport,
        RouteCheckResult,
        evaluate_archive_index,
        evaluate_deployment_contract,
        plan_publication_route_checks,
        release_manifest_check,
    )
    from election_guide.hosting.production_wait import ProductionWaitReport, complete_strict_report

    _, _, resolved, _, upload, root = setup
    site = resolved.site
    deployed = DeploymentManifest.model_validate_json(
        (root / "dist/site/deployment-manifest.json").read_bytes()
    )
    contract = evaluate_deployment_contract(site, deployed, expected_git_commit=upload.source_sha)
    assert contract.ok
    contract = contract.model_copy(
        update={"representative_race_path": f"/e/{site.current_election_id}/races/alpha/"}
    )
    assert contract.representative_race_path is not None
    routes = tuple(
        RouteCheckResult(
            check=check,
            observed=Observation(
                status=check.expected_status,
                location=check.expected_location,
                raw_location=(check.expected_location_origin + check.expected_location)
                if check.expected_location_origin and check.expected_location
                else None,
            ),
        )
        for check in plan_publication_route_checks(
            site, representative_race_path=contract.representative_race_path
        )
    )
    checked_at = datetime(2026, 10, 16, tzinfo=UTC)
    report = ProductionCheckReport(
        base_url=site.canonical_origin,
        checked_at=checked_at,
        manifest=RouteCheckResult(check=MANIFEST_CHECK, observed=Observation(status=200)),
        release_manifest=RouteCheckResult(
            check=release_manifest_check(site.current_election_id), observed=Observation(status=200)
        ),
        deployment_contract=contract,
        archive_index=evaluate_archive_index(
            site,
            Observation(status=200),
            (
                f'<li><a href="/e/{site.current_election_id}/">Election</a> '
                "<strong>(current)</strong></li>"
            ).encode(),
        ),
        current_election_id=site.current_election_id,
        route_results=routes,
        commit=CommitCheck(expected=upload.source_sha, observed=upload.source_sha),
        data_freshness=DataFreshnessCheck(
            published_at=datetime(2026, 10, 15, tzinfo=UTC), checked_at=checked_at
        ),
    )
    assert report.ok
    assert complete_strict_report(report, site, upload.source_sha, active_window=True)
    return ProductionWaitReport((report, report), (0, 1), timed_out=False)


def test_receipts_retain_all_identities_and_both_probes(
    evidence_setup: tuple[Any, ...], monkeypatch: pytest.MonkeyPatch
) -> None:
    import hashlib

    evidence, api, resolved, publication, upload, root = evidence_setup
    evidence.retain_evidence(operation(publication), issue_number=550, reports={})
    report = successful_report(evidence_setup)
    monkeypatch.setattr(evidence, "wait_for_production", partial(provided_report, report))
    producer = upload.producer.model_copy(update={"run_id": 201, "workflow_sha": "f" * 40})
    result = evidence.finalize_deployment(
        upload, site_manifest=resolved.site, producer=producer, output_dir=root / "out"
    )
    assert result.state == "verified"
    assert result.producer == producer
    assert result.upload == upload
    assert result.publication == publication
    data = evidence.read_evidence_reports(result, issue_number=550)["production-wait.json"]
    assert json.loads(data) == report.model_dump(mode="json")
    assert result.verification_sha256 == hashlib.sha256(data).hexdigest()
    # Reconstruct from the remote parts; no local output files are needed.
    assert loaded(evidence_setup)[-1] == result
    api.deployments = [
        {
            "id": 50,
            "creator": BOT,
            "environment": "production",
            "sha": upload.source_sha,
            "payload": evidence.deployment_payload(publication),
        }
    ]
    api.statuses[50] = [
        {"id": 20, "creator": BOT, "state": "inactive"},
        {"id": 10, "creator": BOT, "state": "success"},
    ]
    assert evidence.latest_production_receipt(producer.repository) == result

    def no_probe(*args: Any, **kwargs: Any) -> None:
        raise AssertionError("durable completed finalization must be reused")

    monkeypatch.setattr(evidence, "wait_for_production", no_probe)
    assert (
        evidence.finalize_deployment(
            upload, site_manifest=resolved.site, producer=producer, output_dir=root / "retry"
        )
        == result
    )


def test_same_run_partial_failed_then_verified_is_resumable(
    evidence_setup: tuple[Any, ...], monkeypatch: pytest.MonkeyPatch
) -> None:
    evidence, api, resolved, publication, upload, root = evidence_setup
    from election_guide.hosting.production_wait import ProductionWaitReport

    good = successful_report(evidence_setup)
    failed = ProductionWaitReport(good.attempts[:1], (), timed_out=True)
    evidence.retain_evidence(operation(publication), issue_number=550, reports={})
    monkeypatch.setattr(evidence, "wait_for_production", partial(provided_report, failed))
    result = evidence.finalize_deployment(
        upload, site_manifest=resolved.site, producer=upload.producer, output_dir=root / "failed"
    )
    assert result.state == "failed"
    monkeypatch.setattr(evidence, "wait_for_production", partial(provided_report, good))
    api.fail_after = len(api.posted) + 1
    with pytest.raises(ValueError, match="unavailable"):
        evidence.finalize_deployment(
            upload,
            site_manifest=resolved.site,
            producer=upload.producer,
            output_dir=root / "partial",
        )
    assert (root / "partial/production-wait.json").exists()
    assert (root / "partial/summary.md").exists()
    assert (root / "partial/finalization-error.json").exists()
    api.fail_after = None
    result = evidence.finalize_deployment(
        upload, site_manifest=resolved.site, producer=upload.producer, output_dir=root / "retry"
    )
    assert result.state == "verified"
    assert {item.state for item in loaded(evidence_setup)} == {"published", "failed", "verified"}
    assert len(set(api.posted)) == len(api.posted)


def test_probe_exception_retains_failed_receipt(
    evidence_setup: tuple[Any, ...], monkeypatch: pytest.MonkeyPatch
) -> None:
    evidence, _, resolved, publication, upload, root = evidence_setup
    evidence.retain_evidence(operation(publication), issue_number=550, reports={})

    def broken(*args: Any, **kwargs: Any) -> None:
        raise ValueError("fixture probe crashed")

    monkeypatch.setattr(evidence, "wait_for_production", broken)
    with pytest.raises(ValueError, match="probe crashed"):
        evidence.finalize_deployment(
            upload, site_manifest=resolved.site, producer=upload.producer, output_dir=root / "out"
        )
    assert loaded(evidence_setup)[-1].state == "failed"
    assert (
        OperationReceipt.model_validate_json(
            (root / "out/operation-receipt.json").read_bytes()
        ).error
        == "fixture probe crashed"
    )


def test_large_report_index_remains_bounded(
    evidence_setup: tuple[Any, ...], monkeypatch: pytest.MonkeyPatch
) -> None:
    evidence, api, _, publication, _, _ = evidence_setup
    monkeypatch.setattr(evidence, "PART_BYTES", 4000)
    report = canonical_json_bytes({"observations": "🗳" * 400000})
    receipt = operation(publication)
    evidence.retain_evidence(receipt, issue_number=550, reports={"large.json": report})
    assert evidence.read_evidence_reports(receipt, issue_number=550)["large.json"] == report
    assert all(len(body) < 60000 for body in api.posted)


@pytest.mark.parametrize("state", ["superseded", "deployment_paused"])
def test_skipped_deployment_truthfully_retains_no_upload(
    evidence_setup: tuple[Any, ...], state: str
) -> None:
    evidence, _, _, publication, _, _ = evidence_setup
    record = operation(publication, phase="deployment", state=state)
    evidence.retain_evidence(record, issue_number=550, reports={})
    assert loaded(evidence_setup) == (record,)


def test_cli_record_upload_and_finalize_are_read_only(
    evidence_setup: tuple[Any, ...], monkeypatch: pytest.MonkeyPatch
) -> None:
    evidence, _, _, publication, upload, root = evidence_setup
    from election_guide.release.automation_cli import app

    evidence.retain_evidence(operation(publication), issue_number=550, reports={})
    for name, value in {
        "GITHUB_REPOSITORY": upload.producer.repository,
        "GITHUB_SHA": upload.producer.workflow_sha,
        "GITHUB_RUN_ID": str(upload.producer.run_id),
        "GITHUB_RUN_ATTEMPT": str(upload.producer.run_attempt),
    }.items():
        monkeypatch.setenv(name, value)
    path = root / "publication.json"
    path.write_bytes(canonical_json_bytes(publication.model_dump(mode="json")))
    out = root / "upload.json"
    result = CliRunner().invoke(
        app,
        [
            "record-upload",
            "--publication",
            str(path),
            "--github-deployment-id",
            "50",
            "--deployment-url",
            upload.deployment_url,
            "--uploaded-at",
            upload.uploaded_at.isoformat(),
            "--output",
            str(out),
        ],
    )
    assert result.exit_code == 0, result.output
    assert UploadReceipt.model_validate_json(out.read_bytes()) == upload
    report = successful_report(evidence_setup)
    monkeypatch.setattr(evidence, "wait_for_production", partial(provided_report, report))
    result = CliRunner().invoke(
        app, ["finalize", "--upload", str(out), "--output-dir", str(root / "out")]
    )
    assert result.exit_code == 0, result.output
    assert loaded(evidence_setup)[-1].state == "verified"


def test_verified_evidence_rejects_incomplete_strict_probes(
    evidence_setup: tuple[Any, ...],
) -> None:
    import hashlib

    evidence, api, _, publication, upload, _ = evidence_setup
    good = successful_report(evidence_setup)
    partial = good.attempts[0].model_copy(
        update={"route_results": good.attempts[0].route_results[:1]}
    )
    from election_guide.hosting.production_wait import ProductionWaitReport

    report = canonical_json_bytes(
        ProductionWaitReport((partial, partial), (0, 1), False).model_dump()
    )
    receipt = operation(
        publication,
        phase="deployment",
        state="verified",
        upload=upload,
        verification_sha256=hashlib.sha256(report).hexdigest(),
    )
    with pytest.raises(ValueError, match="complete strict"):
        evidence.retain_evidence(
            receipt, issue_number=550, reports={"production-wait.json": report}
        )
    assert not api.posted


def test_finalize_cli_failure_always_writes_local_evidence(evidence_setup: tuple[Any, ...]) -> None:
    _, _, _, _, _, root = evidence_setup
    from election_guide.release.automation_cli import app

    path = root / "broken-upload.json"
    path.write_text("{truncated")
    output = root / "out"
    result = CliRunner().invoke(
        app, ["finalize", "--upload", str(path), "--output-dir", str(output)]
    )
    assert result.exit_code == 1
    assert (output / "summary.md").exists()
    assert json.loads((output / "finalization-error.json").read_bytes())["complete"] is False


def test_cli_bootstrap_lookup_and_skipped_operation(evidence_setup: tuple[Any, ...]) -> None:
    _, _, _, publication, _, root = evidence_setup
    from election_guide.release.automation_cli import app

    output = root / "latest.json"
    result = CliRunner().invoke(
        app, ["latest-production", "--repository", "owner/repository", "--output", str(output)]
    )
    assert result.exit_code == 0, result.output
    assert json.loads(output.read_bytes()) is None
    receipt = operation(publication, phase="deployment", state="deployment_paused")
    path = root / "paused.json"
    path.write_bytes(canonical_json_bytes(receipt.model_dump(mode="json")))
    result = CliRunner().invoke(app, ["retain-operation", "--receipt", str(path)])
    assert result.exit_code == 0, result.output
    assert loaded(evidence_setup) == (receipt,)


def test_cli_lookup_failure_never_writes_bootstrap_absence(evidence_setup: tuple[Any, ...]) -> None:
    evidence, api, _, publication, upload, root = evidence_setup
    from election_guide.release.automation_cli import app

    api.deployments = [
        {
            "id": 50,
            "creator": BOT,
            "environment": "production",
            "sha": upload.source_sha,
            "payload": evidence.deployment_payload(publication),
        }
    ]
    api.statuses[50] = [{"id": 1, "creator": BOT, "state": "success"}]
    output = root / "latest.json"
    result = CliRunner().invoke(
        app, ["latest-production", "--repository", "owner/repository", "--output", str(output)]
    )
    assert result.exit_code == 1
    assert not output.exists()


def test_partial_upload_receipt_still_rejects_conflicting_upload(
    evidence_setup: tuple[Any, ...],
) -> None:
    evidence, api, _, publication, upload, _ = evidence_setup
    original = operation(publication, phase="deployment", upload=upload)
    api.fail_after = 1
    with pytest.raises(ValueError, match="unavailable"):
        evidence.retain_evidence(original, issue_number=550, reports={})
    assert loaded(evidence_setup) == ()
    api.fail_after = None
    conflicting = operation(
        publication,
        phase="deployment",
        upload=upload.model_copy(update={"github_deployment_id": 51}),
    )
    with pytest.raises(ValueError, match="conflicting canonical"):
        evidence.retain_evidence(conflicting, issue_number=550, reports={})


@pytest.mark.parametrize(
    "field,value",
    [("sha", "f" * 40), ("environment", "preview"), ("creator", {"id": 1}), ("payload", {})],
)
def test_finalize_rejects_wrong_github_deployment_identity(
    evidence_setup: tuple[Any, ...], monkeypatch: pytest.MonkeyPatch, field: str, value: Any
) -> None:
    evidence, api, resolved, publication, upload, root = evidence_setup
    evidence.retain_evidence(operation(publication), issue_number=550, reports={})
    api.deployments[0][field] = value
    monkeypatch.setattr(
        evidence, "wait_for_production", partial(provided_report, successful_report(evidence_setup))
    )
    with pytest.raises(ValueError, match="deployment identity"):
        evidence.finalize_deployment(
            upload, site_manifest=resolved.site, producer=upload.producer, output_dir=root / "out"
        )
