"""Historical compatibility exports immutable operations, never a new upload."""

from __future__ import annotations

import copy
import importlib
import json
import subprocess
from pathlib import Path
from typing import Any

import pytest

from election_guide.release import evidence, evidence_v2, workflow
from election_guide.release.automation_models import PublicationResult
from tests.test_release_evidence import (
    evidence_setup,  # noqa: F401 # pyright: ignore[reportUnusedImport]
    operation,
    promotion_setup,  # noqa: F401 # pyright: ignore[reportUnusedImport]
    setup_publication,  # noqa: F401 # pyright: ignore[reportUnusedImport]
)
from tests.test_release_evidence_v2 import (
    CHECKPOINTS,
    FIXTURE,
    checkpoint,
    compressed_comments,
    v2_comment,
)

REPOSITORY = "shaug/seattle-election-guide"


def compat() -> Any:
    return importlib.import_module("election_guide.release.evidence_compat")


def trust_current_workflow(monkeypatch: pytest.MonkeyPatch) -> str:
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"], capture_output=True, text=True, check=True
    )
    sha = result.stdout.strip()
    for key, value in {
        "GITHUB_ACTIONS": "true",
        "GITHUB_REF": "refs/heads/main",
        "GITHUB_REPOSITORY": REPOSITORY,
        "GITHUB_SHA": sha,
        "GITHUB_RUN_ID": "9001000",
        "GITHUB_RUN_ATTEMPT": "1",
    }.items():
        monkeypatch.setenv(key, value)
    return sha


class IssueStore:
    """Only complete issue/deployment reads and append-only bot comments exist."""

    def __init__(self, comments: list[dict[str, Any]]) -> None:
        self.issues = {696: copy.deepcopy(comments)}
        self.deployments = [json.loads((FIXTURE / "deployment.original.json").read_bytes())]
        self.posted: list[dict[str, Any]] = []
        self.fail_after: int | None = None
        self.next_id = 2000000

    def run(self, command: list[str], failure: str) -> str:
        assert command[:2] == ["gh", "api"]
        endpoint = command[2]
        if "/issues/" in endpoint and "/comments" in endpoint:
            issue = int(endpoint.split("/issues/")[1].split("/")[0])
            rows = self.issues[issue]
            if "--method" in command:
                assert command[command.index("--method") + 1] == "POST"
                if self.fail_after is not None and len(self.posted) >= self.fail_after:
                    raise ValueError("fixture comment transport interrupted")
                payload = json.loads(Path(command[command.index("--input") + 1]).read_bytes())
                row = copy.deepcopy(
                    json.loads((FIXTURE / "comments.original.json").read_bytes())[0]
                )
                row.update(id=self.next_id, body=payload["body"], fixture_transport=True)
                self.next_id += 1
                rows.append(row)
                self.posted.append(row)
                return json.dumps(row)
            assert "--paginate" in command and "--slurp" in command
            return json.dumps([rows])
        if endpoint.startswith(f"repos/{REPOSITORY}/deployments"):
            assert "--method" not in command
            assert "--paginate" in command and "--slurp" in command
            assert "/statuses" not in endpoint
            return json.dumps([self.deployments])
        raise AssertionError(f"unexpected artifact/provider/deployment-write endpoint: {endpoint}")


def install(monkeypatch: pytest.MonkeyPatch, store: IssueStore) -> str:
    sha = trust_current_workflow(monkeypatch)
    monkeypatch.setattr(evidence, "run_gh", store.run)
    monkeypatch.setattr(workflow, "run_gh", store.run)
    return sha


def test_compatibility_export_keeps_original_producer_and_records_exporter(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    store = IssueStore(compressed_comments())
    before = copy.deepcopy(store.issues[696])
    reader_sha = install(monkeypatch, store)
    report = compat().prepare_historical_evidence(REPOSITORY, 696, tmp_path / "compat")
    assert report["complete"] is True
    assert report["exporter"]["workflow_sha"] == reader_sha
    assert len(store.posted) == 15
    assert store.issues[696][:3] == before
    assert all(
        evidence.MARKER in row["body"] and evidence_v2.MARKER not in row["body"]
        for row in store.posted
    )
    legacy = [row for row in store.issues[696] if evidence.MARKER in row["body"]]
    store.issues[696] = legacy
    receipts = evidence.load_verified_receipts(
        repository=REPOSITORY,
        issue_number=696,
        release_version="2026-general.128",
        source_sha="4f9d09ac39ba09166123500bf3107c1b665ea6dc",
    )
    assert receipts == tuple(checkpoint(name)[0] for name in CHECKPOINTS)
    for operation_receipt, name in zip(receipts, CHECKPOINTS, strict=True):
        assert (
            evidence.read_evidence_reports(operation_receipt, issue_number=696)
            == checkpoint(name)[1]
        )
        assert operation_receipt.producer == checkpoint(name)[0].producer


def test_compatibility_export_reuses_complete_v1_without_another_post(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    originals = json.loads((FIXTURE / "comments.original.json").read_bytes())
    store = IssueStore([*originals, *compressed_comments()])
    before = copy.deepcopy(store.issues)
    install(monkeypatch, store)
    result = compat().prepare_historical_evidence(REPOSITORY, 696, tmp_path / "compat")
    assert result["complete"] is True
    assert store.issues == before and store.posted == []


def test_compatibility_export_resumes_original_v1_ids(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    store = IssueStore(compressed_comments())
    install(monkeypatch, store)
    store.fail_after = 1
    with pytest.raises(ValueError, match="interrupted"):
        compat().prepare_historical_evidence(REPOSITORY, 696, tmp_path / "interrupted")
    original_part = copy.deepcopy(store.posted[0])
    assert (
        json.loads((tmp_path / "interrupted/compatibility-report.json").read_bytes())["complete"]
        is False
    )
    store.fail_after = None
    result = compat().prepare_historical_evidence(REPOSITORY, 696, tmp_path / "resumed")
    assert result["complete"] is True
    assert store.posted[0] == original_part and len(store.posted) == 15
    assert sum(row["body"] == original_part["body"] for row in store.issues[696]) == 1


def test_compatibility_preparation_covers_global_managed_intents(
    request: pytest.FixtureRequest,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _, _, _, publication, _, _ = request.getfixturevalue("evidence_setup")
    store = IssueStore(compressed_comments())
    # This second publication is generated test data, not an authenticated
    # historical operation. Put all of its simulated refs in the same repository.
    synthetic = json.dumps(publication.model_dump(mode="json")).replace(
        publication.published.candidate.producer.repository, REPOSITORY
    )
    publication = PublicationResult.model_validate_json(synthetic)
    other = operation(publication)
    store.issues[550] = [v2_comment(other, {}, 1000900)]
    store.deployments.append(
        {
            "id": 50,
            "creator": evidence.BOT,
            "sha": other.producer.source_sha,
            "environment": "production",
            "payload": evidence.deployment_payload(publication),
        }
    )
    before = copy.deepcopy(store.issues)
    install(monkeypatch, store)
    result = compat().prepare_historical_evidence(REPOSITORY, 696, tmp_path / "global")
    assert result["complete"] is True and result["issues"] == [550, 696]
    assert store.issues[550][0] == before[550][0] and len(store.issues[550]) == 4
    assert len(store.issues[696]) == 18
    assert evidence.load_verified_receipts(
        repository=REPOSITORY,
        issue_number=550,
        release_version=publication.published.candidate.declaration.release_version,
        source_sha=other.producer.source_sha,
    ) == (other,)


@pytest.mark.parametrize("damage", ["hash", "duplicate", "incomplete"])
def test_invalid_compressed_group_fails_before_any_compatibility_post(
    damage: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    comments = compressed_comments()
    if damage == "hash":
        comments[-1]["body"] = comments[-1]["body"].replace("gzip+base64", "invalid")
    elif damage == "duplicate":
        comments.append({**comments[0], "id": 1000099})
    else:
        marker, payload = evidence_v2.decode_comment(comments[1]["body"])
        monkeypatch.setattr(evidence_v2, "MAX_COMMENT_CHARS", 2300)
        monkeypatch.setattr(evidence_v2, "PART_BYTES", 512)
        pieces = evidence_v2.envelope_parts(marker, payload)
        comments = [{**comments[1], "body": evidence_v2.render_envelope(*pieces[0])}]
    store = IssueStore(comments)
    before = copy.deepcopy(store.issues)
    install(monkeypatch, store)
    with pytest.raises(ValueError):
        compat().prepare_historical_evidence(REPOSITORY, 696, tmp_path / "invalid")
    assert store.issues == before and store.posted == []
    assert (
        json.loads((tmp_path / "invalid/compatibility-report.json").read_bytes())["complete"]
        is False
    )


def test_compatibility_comment_budget_fails_visibly_and_can_resume(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    store = IssueStore(compressed_comments())
    install(monkeypatch, store)
    monkeypatch.setattr(compat(), "MAX_NEW_COMMENTS", 1)
    with pytest.raises(ValueError, match="budget"):
        compat().prepare_historical_evidence(REPOSITORY, 696, tmp_path / "limited")
    assert len(store.posted) == 1
    failed = json.loads((tmp_path / "limited/compatibility-report.json").read_bytes())
    assert failed["complete"] is False
    assert (tmp_path / "limited/finalization-error.json").is_file()
    first = copy.deepcopy(store.posted[0])
    monkeypatch.setenv("GITHUB_RUN_ID", "9001001")
    monkeypatch.setattr(compat(), "MAX_NEW_COMMENTS", 256)
    assert compat().prepare_historical_evidence(REPOSITORY, 696, tmp_path / "resumed")["complete"]
    assert store.posted[0] == first and len(store.posted) == 15


def test_compatibility_export_rereads_a_stored_post_after_lost_response(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    store = IssueStore(compressed_comments())
    install(monkeypatch, store)
    lost = False

    def ambiguous(command: list[str], failure: str) -> str:
        nonlocal lost
        result = store.run(command, failure)
        if "--method" in command and not lost:
            lost = True
            raise ValueError("fixture response lost after POST stored")
        return result

    monkeypatch.setattr(evidence, "run_gh", ambiguous)
    with pytest.raises(ValueError, match="response lost"):
        compat().prepare_historical_evidence(REPOSITORY, 696, tmp_path / "ambiguous")
    assert len(store.posted) == 1
    first = copy.deepcopy(store.posted[0])
    report = json.loads((tmp_path / "ambiguous/compatibility-report.json").read_bytes())
    assert report["complete"] is False
    assert report["observed_new_comment_ids"] == [first["id"]]
    result = compat().prepare_historical_evidence(REPOSITORY, 696, tmp_path / "resumed")
    assert result["complete"] is True
    assert len(store.posted) == 15 and store.posted[0] == first


def test_preparation_rejects_non_main_execution_before_any_api(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    store = IssueStore(compressed_comments())
    install(monkeypatch, store)
    monkeypatch.setenv("GITHUB_REF", "refs/heads/feature")
    before = copy.deepcopy(store.issues)

    def no_api(*args: Any, **kwargs: Any) -> str:
        raise AssertionError("non-main preparation must not call any API")

    monkeypatch.setattr(evidence, "run_gh", no_api)
    monkeypatch.setattr(workflow, "run_gh", no_api)
    with pytest.raises(ValueError, match="main"):
        compat().prepare_historical_evidence(REPOSITORY, 696, tmp_path / "unauthorized")
    assert store.issues == before and not store.posted


def test_preparation_requires_actions_execution(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    store = IssueStore(compressed_comments())
    install(monkeypatch, store)
    monkeypatch.setenv("GITHUB_ACTIONS", "false")
    with pytest.raises(ValueError, match="Actions"):
        compat().prepare_historical_evidence(REPOSITORY, 696, tmp_path / "not-actions")
    assert store.posted == []


@pytest.mark.parametrize("fails", [False, True])
def test_preparation_cli_preserves_nonzero_and_never_runs_verification(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, fails: bool
) -> None:
    from typer.testing import CliRunner

    from election_guide.cli import app

    calls: list[tuple[str, int, Path]] = []

    def prepare(repository: str, issue_number: int, output_dir: Path) -> dict[str, Any]:
        calls.append((repository, issue_number, output_dir))
        if fails:
            raise ValueError("incomplete compatibility evidence")
        return {"complete": True}

    monkeypatch.setattr(compat(), "prepare_historical_evidence", prepare)
    output = tmp_path / "compat"
    result = CliRunner().invoke(
        app,
        [
            "release",
            "automation",
            "prepare-historical-evidence",
            "--repository",
            REPOSITORY,
            "--issue",
            "696",
            "--output-dir",
            str(output),
        ],
    )
    assert result.exit_code == (1 if fails else 0), result.output
    assert calls == [(REPOSITORY, 696, output)]
    assert ("incomplete compatibility evidence" in result.output) == fails
