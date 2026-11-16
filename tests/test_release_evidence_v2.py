"""Compressed checkpoints preserve original General128 bytes and resumable writes."""

from __future__ import annotations

import copy
import gzip
import hashlib
import json
import random
from datetime import timedelta
from pathlib import Path
from typing import Any

import pytest

from election_guide.hosting.production_check import Observation
from election_guide.hosting.updates import UPDATES_SNAPSHOT
from election_guide.release import evidence, evidence_v2, workflow
from election_guide.release.automation_models import OperationReceipt
from election_guide.serialization import canonical_json_bytes
from tests.test_release_evidence import GitHub

FIXTURE = Path(__file__).parent / "fixtures/release/evidence-general128"
SOURCE = "4f9d09ac39ba09166123500bf3107c1b665ea6dc"
REPOSITORY = "shaug/seattle-election-guide"
CHECKPOINTS = ("publication", "upload", "verified")


def originals() -> list[dict[str, Any]]:
    return json.loads((FIXTURE / "comments.original.json").read_bytes())


def checkpoint(name: str) -> tuple[OperationReceipt, dict[str, bytes]]:
    root = FIXTURE / name
    receipt = OperationReceipt.model_validate_json((root / "receipt.json").read_bytes())
    reports = {p.name: p.read_bytes() for p in root.iterdir() if p.name != "receipt.json"}
    return receipt, reports


def v2_comment(
    operation: OperationReceipt,
    reports: dict[str, bytes],
    comment_id: int,
    *,
    first_part: bool = False,
    **marker_updates: Any,
) -> dict[str, Any]:
    files = {**reports, "receipt.json": canonical_json_bytes(operation.model_dump(mode="json"))}
    payload = evidence_v2.encode_envelope(files)
    raw = gzip.decompress(payload)
    marker = evidence_v2.EnvelopeMarker(
        producer=operation.producer,
        release_version=operation.publication.published.candidate.declaration.release_version,
        phase=operation.phase,
        state=operation.state,
        group=hashlib.sha256(files["receipt.json"]).hexdigest(),
        compressed_bytes=len(payload),
        compressed_sha256=hashlib.sha256(payload).hexdigest(),
        uncompressed_bytes=len(raw),
        uncompressed_sha256=hashlib.sha256(raw).hexdigest(),
        part_sha256=hashlib.sha256(payload).hexdigest(),
    ).model_copy(update=marker_updates)
    if first_part:
        marker, payload = evidence_v2.envelope_parts(marker, payload)[0]
    comment = copy.deepcopy(originals()[0])
    comment.update(
        id=comment_id,
        body=evidence_v2.render_envelope(marker, payload),
        html_url=f"fixture://comments/{comment_id}",
        url=f"fixture://comments/{comment_id}",
        fixture_transport=True,
    )
    return comment


def compressed_comments() -> list[dict[str, Any]]:
    return [v2_comment(*checkpoint(name), 1000000 + i) for i, name in enumerate(CHECKPOINTS)]


def transport(monkeypatch: pytest.MonkeyPatch, comments: list[dict[str, Any]]) -> None:
    deployment = json.loads((FIXTURE / "deployment.original.json").read_bytes())
    statuses = [
        r for page in json.loads((FIXTURE / "statuses.original.json").read_bytes()) for r in page
    ]

    def pages(endpoint: str) -> list[dict[str, Any]]:
        if endpoint == f"repos/{REPOSITORY}/issues/696/comments":
            return comments
        if endpoint == f"repos/{REPOSITORY}/deployments":
            return [deployment]
        if endpoint == f"repos/{REPOSITORY}/deployments/7809440517/statuses":
            return statuses
        raise AssertionError(f"unexpected endpoint or expired artifact request: {endpoint}")

    monkeypatch.setattr(evidence, "_pages", pages)


def loaded() -> tuple[OperationReceipt, ...]:
    return evidence.load_verified_receipts(
        repository=REPOSITORY,
        issue_number=696,
        release_version="2026-general.128",
        source_sha=SOURCE,
    )


def test_general128_three_v2_comments_restore_exact_original_reports(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    comments = compressed_comments()
    assert len(comments) == 3 and all(len(row["body"]) < 60000 for row in comments)
    transport(monkeypatch, comments)
    receipts = loaded()
    assert receipts == tuple(checkpoint(name)[0] for name in CHECKPOINTS)
    for name, receipt in zip(CHECKPOINTS, receipts, strict=True):
        assert (
            canonical_json_bytes(receipt.model_dump(mode="json"))
            == (FIXTURE / name / "receipt.json").read_bytes()
        )
        assert evidence.read_evidence_reports(receipt, issue_number=696) == checkpoint(name)[1]
    report = evidence.read_evidence_reports(receipts[-1], issue_number=696)["production-wait.json"]
    assert len(report) == 141815
    assert hashlib.sha256(report).hexdigest() == (
        "bb0830237f7099bbdd71c76b5affb63dabb8df250ef200040e774d9ff19b348e"
    )


def test_mixed_representations_deduplicate_only_identical_bytes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    before = originals()
    comments = copy.deepcopy(before) + compressed_comments()
    transport(monkeypatch, comments)
    assert loaded() == tuple(checkpoint(name)[0] for name in CHECKPOINTS)
    assert comments[:15] == before


def test_conflicting_cross_format_report_sets_fail_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    publication, _ = checkpoint("publication")
    extra = {"observations.json": canonical_json_bytes({"unexpected": "additional report"})}
    transport(monkeypatch, [*originals(), v2_comment(publication, extra, 1000001)])
    with pytest.raises(ValueError, match="conflict"):
        loaded()


@pytest.mark.parametrize("damage", ["source", "workflow", "release", "phase", "repository"])
def test_v2_marker_must_bind_original_receipt_identity(
    damage: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    operation, reports = checkpoint("publication")
    changes: dict[str, Any] = {}
    if damage in {"source", "workflow", "repository"}:
        key = {"source": "source_sha", "workflow": "workflow_sha", "repository": "repository"}[
            damage
        ]
        changes["producer"] = operation.producer.model_copy(
            update={key: "other/project" if damage == "repository" else "f" * 40}
        )
    else:
        changes["release_version" if damage == "release" else "phase"] = (
            "2026-general.999" if damage == "release" else "deployment"
        )
    transport(monkeypatch, [v2_comment(operation, reports, 1000001, **changes)])
    with pytest.raises(ValueError):
        loaded()


def test_unowned_v2_comment_cannot_supply_publication(monkeypatch: pytest.MonkeyPatch) -> None:
    comments = compressed_comments()
    for row in comments:
        row["user"] = {**row["user"], "id": 7}
    transport(monkeypatch, comments)
    assert loaded() == ()
    with pytest.raises(ValueError, match="publication evidence"):
        evidence.require_publication_evidence(checkpoint("publication")[0].publication)


def test_duplicate_owned_atomic_comments_are_ambiguous(monkeypatch: pytest.MonkeyPatch) -> None:
    first = compressed_comments()[0]
    duplicate = {**first, "id": 1000099}
    transport(monkeypatch, [first, duplicate])
    with pytest.raises(ValueError, match="duplicate"):
        loaded()


@pytest.mark.parametrize("name", ["publication", "upload"])
def test_incomplete_v2_blocks_preupload_disposition(
    name: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    comment = compressed_comments()[CHECKPOINTS.index(name)]
    marker, payload = evidence_v2.decode_comment(comment["body"])
    monkeypatch.setattr(evidence_v2, "MAX_COMMENT_CHARS", 2300)
    monkeypatch.setattr(evidence_v2, "PART_BYTES", 512)
    pieces = evidence_v2.envelope_parts(marker, payload)
    assert len(pieces) > 1
    pending = {**comment, "body": evidence_v2.render_envelope(*pieces[0])}
    # Only the publication's original v1 group and one unsealed v2 upload part.
    transport(monkeypatch, [*originals()[:3], pending])
    with pytest.raises(ValueError, match="incomplete"):
        evidence.read_preupload_evidence(checkpoint("publication")[0].publication)


def test_complete_v2_does_not_hide_an_incomplete_v1_group(monkeypatch: pytest.MonkeyPatch) -> None:
    transport(monkeypatch, originals()[:1] + compressed_comments()[:1])
    with pytest.raises(ValueError, match="incomplete"):
        evidence.read_preupload_evidence(checkpoint("publication")[0].publication)


def test_unsealed_v2_parts_cannot_disagree_about_the_producer(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    comment = compressed_comments()[1]
    marker, payload = evidence_v2.decode_comment(comment["body"])
    monkeypatch.setattr(evidence_v2, "MAX_COMMENT_CHARS", 2300)
    monkeypatch.setattr(evidence_v2, "PART_BYTES", 512)
    pieces = evidence_v2.envelope_parts(marker, payload)
    altered = pieces[1][0].model_copy(
        update={"producer": marker.producer.model_copy(update={"workflow_sha": "f" * 40})}
    )
    comments = [
        {**comment, "id": 1000001, "body": evidence_v2.render_envelope(*pieces[0])},
        {**comment, "id": 1000002, "body": evidence_v2.render_envelope(altered, pieces[1][1])},
    ]
    transport(monkeypatch, comments)
    with pytest.raises(ValueError, match="conflict"):
        loaded()


def test_partial_v1_receipt_cannot_be_contradicted_by_v2_upload(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    upload, _ = checkpoint("upload")
    assert upload.upload is not None
    changed = upload.model_copy(
        update={
            "upload": upload.upload.model_copy(
                update={"uploaded_at": upload.upload.uploaded_at + timedelta(seconds=1)}
            )
        }
    )
    transport(monkeypatch, [originals()[3], v2_comment(changed, {}, 1000001)])
    with pytest.raises(ValueError, match="conflict"):
        loaded()


def test_v2_supports_current_admission_latest_updates_and_expired_artifact_recovery(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    transport(monkeypatch, compressed_comments())
    publication = checkpoint("publication")[0].publication
    verified = checkpoint("verified")[0]
    evidence.require_publication_evidence(publication)
    assert evidence.latest_production_receipt(REPOSITORY) == verified

    def no_artifacts(*args: Any, **kwargs: Any) -> Any:
        raise AssertionError("expired Actions artifacts must not be requested")

    monkeypatch.setattr(workflow, "read_rows", no_artifacts)
    assert (
        workflow.recover_upload(
            repository=REPOSITORY,
            issue=696,
            release_version="2026-general.128",
            source_sha=SOURCE,
            run_id=43755212223,
            run_attempt=1,
        )
        == verified.upload
    )

    from election_guide.hosting import updates_baseline

    def fetch_manifest(origin: str, *, timeout: float) -> tuple[Observation, bytes]:
        return Observation(status=200), (FIXTURE / "deployment-manifest.json").read_bytes()

    def fetch_snapshot(origin: str, path: str, *, timeout: float) -> tuple[Observation, bytes]:
        assert path == "/" + UPDATES_SNAPSHOT
        return Observation(status=200), (FIXTURE / "updates-snapshot.json").read_bytes()

    monkeypatch.setattr(updates_baseline, "fetch_manifest_body", fetch_manifest)
    monkeypatch.setattr(updates_baseline, "fetch_asset_body", fetch_snapshot)
    snapshot, baseline = updates_baseline.resolve_production_snapshot(tmp_path / "baseline")
    assert snapshot.schema_version == "7.0"
    assert baseline["deployment_id"] == 7809440517 and baseline["git_commit"] == SOURCE


def test_explicit_legacy_writer_keeps_v1_wire_contract(monkeypatch: pytest.MonkeyPatch) -> None:
    api = GitHub()
    monkeypatch.setattr(evidence, "run_gh", api.run)
    operation, reports = checkpoint("publication")
    evidence.retain_v1_evidence(operation, issue_number=696, reports=reports)
    assert len(api.posted) == 3
    assert all(evidence.MARKER in body and evidence_v2.MARKER not in body for body in api.posted)


def test_ordinary_release_retains_exactly_three_comments(monkeypatch: pytest.MonkeyPatch) -> None:
    api = GitHub()
    monkeypatch.setattr(evidence, "run_gh", api.run)
    for name in CHECKPOINTS:
        operation, reports = checkpoint(name)
        ids = evidence.retain_evidence(operation, issue_number=696, reports=reports)
        assert ids == (api.comments[-1]["id"],)
        assert evidence.read_evidence_reports(operation, issue_number=696) == reports
        assert evidence.retain_evidence(operation, issue_number=696, reports=reports) == ids
    assert len(api.posted) == 3
    assert all(evidence_v2.MARKER in body and len(body) < 60000 for body in api.posted)
    assert loaded() == tuple(checkpoint(name)[0] for name in CHECKPOINTS)


class UncertainGitHub(GitHub):
    """A single normal POST may store successfully while its response is unusable."""

    def __init__(self, *, reply: str, kind: str | None = None) -> None:
        super().__init__()
        self.reply = reply
        self.kind = kind
        self.armed = True
        self.post_calls = 0
        self.comment_reads = 0

    def run(self, command: list[str], failure: str) -> str:
        if "--method" not in command:
            if "/comments" in command[2]:
                self.comment_reads += 1
            return super().run(command, failure)
        self.post_calls += 1
        body = json.loads(Path(command[command.index("--input") + 1]).read_bytes())["body"]
        matches = self.kind is None or (
            evidence_v2.MARKER in body and evidence_v2.decode_comment(body)[0].kind == self.kind
        )
        if not self.armed or not matches:
            return super().run(command, failure)
        self.armed = False
        if self.reply == "missing":
            raise ValueError("fixture issue write unavailable")
        result = super().run(command, failure)
        if self.reply == "foreign-stored":
            self.comments[-1]["user"] = {**self.comments[-1]["user"], "id": 7}
            raise ValueError("fixture response lost after storage")
        if self.reply == "duplicate":
            self.comments.append({**self.comments[-1], "id": len(self.comments) + 1})
        if self.reply in {"lost", "duplicate"}:
            raise ValueError("fixture response lost after storage")
        if self.reply == "malformed":
            return "{truncated"
        row = json.loads(result)
        row["user"] = {**row["user"], "id": 7}
        return json.dumps(row)


@pytest.mark.parametrize("reply", ["lost", "malformed", "wrong-owner-reply"])
def test_ambiguous_successful_post_is_reused_after_reread(
    reply: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    api = UncertainGitHub(reply=reply)
    monkeypatch.setattr(evidence, "run_gh", api.run)
    operation, reports = checkpoint("publication")
    ids = evidence.retain_evidence(operation, issue_number=696, reports=reports)
    assert ids == (1,) and api.post_calls == 1 and api.comment_reads >= 2
    assert evidence.read_evidence_reports(operation, issue_number=696) == reports
    assert evidence.retain_evidence(operation, issue_number=696, reports=reports) == ids
    assert api.post_calls == 1


def test_missing_ambiguous_post_stays_nonzero(monkeypatch: pytest.MonkeyPatch) -> None:
    api = UncertainGitHub(reply="missing")
    monkeypatch.setattr(evidence, "run_gh", api.run)
    operation, reports = checkpoint("publication")
    with pytest.raises(ValueError, match="unavailable"):
        evidence.retain_evidence(operation, issue_number=696, reports=reports)
    assert api.post_calls == 1 and api.comment_reads >= 2 and not api.comments


def large_reports() -> dict[str, bytes]:
    # High entropy triggers the real body/chunk bounds without changing production limits.
    return {
        "large.json": canonical_json_bytes(
            {"observations": random.Random(762).randbytes(90000).hex()}
        )
    }


def test_multipart_retry_posts_only_missing_records(monkeypatch: pytest.MonkeyPatch) -> None:
    api = GitHub()
    api.fail_after = 1
    monkeypatch.setattr(evidence, "run_gh", api.run)
    operation, _ = checkpoint("publication")
    reports = large_reports()
    with pytest.raises(ValueError, match="unavailable"):
        evidence.retain_evidence(operation, issue_number=696, reports=reports)
    first = copy.deepcopy(api.comments[0])
    assert evidence_v2.decode_comment(first["body"])[0].kind == "v2-part"
    assert loaded() == ()
    api.fail_after = None
    ids = evidence.retain_evidence(operation, issue_number=696, reports=reports)
    assert api.comments[0] == first and api.posted.count(first["body"]) == 1
    markers = [evidence_v2.decode_comment(row["body"])[0] for row in api.comments]
    assert all(marker.kind == "v2-part" for marker in markers[:-1])
    assert markers[-1].kind == "v2-seal"
    assert ids == tuple(row["id"] for row in api.comments)
    assert evidence.read_evidence_reports(operation, issue_number=696) == reports
    assert evidence.retain_evidence(operation, issue_number=696, reports=reports) == ids
    assert len(api.posted) == len(ids) and all(len(body) < 60000 for body in api.posted)


@pytest.mark.parametrize("kind", ["v2-part", "v2-seal"])
def test_ambiguous_multipart_post_reuses_stored_record(
    kind: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    api = UncertainGitHub(reply="lost", kind=kind)
    monkeypatch.setattr(evidence, "run_gh", api.run)
    operation, _ = checkpoint("publication")
    reports = large_reports()
    ids = evidence.retain_evidence(operation, issue_number=696, reports=reports)
    assert not api.armed and api.post_calls == len(ids) and api.comment_reads >= 2
    assert evidence.read_evidence_reports(operation, issue_number=696) == reports
    assert len(set(api.posted)) == len(ids)


def test_ambiguous_duplicate_post_fails_before_another_write(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    api = UncertainGitHub(reply="duplicate")
    monkeypatch.setattr(evidence, "run_gh", api.run)
    operation, reports = checkpoint("publication")
    with pytest.raises(ValueError, match="duplicate"):
        evidence.retain_evidence(operation, issue_number=696, reports=reports)
    assert api.post_calls == 1 and api.comment_reads >= 2


def test_unowned_ambiguous_record_cannot_complete_a_write(monkeypatch: pytest.MonkeyPatch) -> None:
    api = UncertainGitHub(reply="foreign-stored")
    monkeypatch.setattr(evidence, "run_gh", api.run)
    operation, reports = checkpoint("publication")
    with pytest.raises(ValueError, match="lost"):
        evidence.retain_evidence(operation, issue_number=696, reports=reports)
    assert api.post_calls == 1 and api.comment_reads >= 2
    assert loaded() == ()


def test_legacy_continuation_reconciles_an_ambiguous_post(monkeypatch: pytest.MonkeyPatch) -> None:
    api = UncertainGitHub(reply="lost")
    monkeypatch.setattr(evidence, "run_gh", api.run)
    operation, reports = checkpoint("publication")
    ids = evidence.retain_v1_evidence(operation, issue_number=696, reports=reports)
    assert ids == (1, 2, 3) and api.post_calls == 3 and api.comment_reads >= 2
    assert evidence.read_evidence_reports(operation, issue_number=696) == reports


@pytest.mark.parametrize("complete", [True, False])
def test_existing_compressed_reports_conflict_before_any_post(
    complete: bool, monkeypatch: pytest.MonkeyPatch
) -> None:
    api = GitHub()
    operation, reports = checkpoint("publication")
    original = v2_comment(
        operation, reports if complete else large_reports(), 1, first_part=not complete
    )
    api.comments = [original]
    before = copy.deepcopy(api.comments)
    monkeypatch.setattr(evidence, "run_gh", api.run)
    with pytest.raises(ValueError, match="conflict"):
        evidence.retain_evidence(
            operation, issue_number=696, reports={"different.json": canonical_json_bytes({"x": 1})}
        )
    assert api.comments == before and not api.posted


def test_existing_partial_v1_remains_v1_after_cutover(monkeypatch: pytest.MonkeyPatch) -> None:
    api = GitHub()
    monkeypatch.setattr(evidence, "run_gh", api.run)
    operation, reports = checkpoint("publication")
    api.fail_after = 1
    with pytest.raises(ValueError, match="unavailable"):
        evidence.retain_v1_evidence(operation, issue_number=696, reports=reports)
    before = copy.deepcopy(api.comments)
    api.fail_after = None
    ids = evidence.retain_evidence(operation, issue_number=696, reports=reports)
    assert api.comments[:1] == before and ids[0] == before[0]["id"]
    assert len(api.posted) == 3 and all(evidence.MARKER in body for body in api.posted)
    assert evidence.read_evidence_reports(operation, issue_number=696) == reports
    assert evidence.retain_evidence(operation, issue_number=696, reports=reports) == ids
    assert len(api.posted) == 3


def test_explicit_v1_retention_coexists_with_compressed_operations(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    api = GitHub()
    api.comments = compressed_comments()
    before = copy.deepcopy(api.comments)
    monkeypatch.setattr(evidence, "run_gh", api.run)
    operation, reports = checkpoint("publication")
    ids = evidence.retain_v1_evidence(operation, issue_number=696, reports=reports)
    assert len(ids) == 3 and len(api.posted) == 3
    assert api.comments[:3] == before
    assert loaded() == tuple(checkpoint(name)[0] for name in CHECKPOINTS)
    assert evidence.retain_v1_evidence(operation, issue_number=696, reports=reports) == ids
    assert len(api.posted) == 3
