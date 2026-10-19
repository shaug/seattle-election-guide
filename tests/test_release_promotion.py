"""Exact-source recovery and last-moment promotion admission (issue #550)."""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any

import pytest
from typer.testing import CliRunner

from election_guide.hosting.pages import read_site_manifest
from election_guide.release.automation_models import (
    OperationReceipt,
    PublicationResult,
    PublishedArchive,
)
from election_guide.release.declaration import ReleaseInputs, ResolvedRelease
from tests.test_release_candidate import _artifact, _git  # pyright: ignore[reportPrivateUsage]
from tests.test_release_publication import (
    setup_publication,  # noqa: F401  # pyright: ignore[reportUnusedImport]
)


@pytest.fixture
def promotion_setup(setup_publication: tuple[Any, ...]) -> tuple[Any, ...]:  # noqa: F811
    from election_guide.hosting import promotion

    _, resolved, record, archive, bundle, root = setup_publication
    published = PublishedArchive(
        candidate=record,
        candidate_artifact=_artifact(record.producer, "candidate", 12),
        release_id=20,
        asset_id=21,
        asset_name=archive.name,
        archive=record.archive,
        release_manifest_sha256="e" * 64,
        canonical_bundle_sha256=record.bundle_sha256,
        promotion_manifest_sha256=record.deployment_manifest_sha256,
    )
    result = PublicationResult(
        published=published, promotion_artifact=_artifact(record.producer, "promotion", 13)
    )
    return promotion, resolved, record, archive, bundle, root, result


def receipt(publication: PublicationResult) -> OperationReceipt:
    from datetime import UTC, datetime

    from election_guide.release.automation_models import UploadReceipt

    producer = publication.published.candidate.producer
    return OperationReceipt(
        phase="deployment",
        state="verified",
        producer=producer,
        publication=publication,
        upload=UploadReceipt(
            publication=publication,
            producer=producer,
            github_deployment_id=50,
            deployment_url="https://abc123.example.pages.dev",
            uploaded_at=datetime(2026, 10, 16, tzinfo=UTC),
            source_sha=producer.source_sha,
        ),
        verification_sha256="f" * 64,
        error=None,
    )


def test_docs_advance_does_not_supersede_release(promotion_setup: tuple[Any, ...]) -> None:
    promotion, resolved, _, _, _, root, publication = promotion_setup
    (root / "README.md").write_text("Later documentation\n")
    _git(root, "add", "README.md")
    _git(root, "commit", "-qm", "docs: advance main")
    docs_advanced = read_site_manifest(root / "config/hosting/site.yaml")
    assert docs_advanced == resolved.site
    assert (
        promotion.promotion_allowed(
            publication, selected=docs_advanced, latest_verified=receipt(publication)
        )
        is True
    )


def test_newer_declaration_before_upload_supersedes(promotion_setup: tuple[Any, ...]) -> None:
    promotion, resolved, record, _, _, _, publication = promotion_setup
    newer = record.declaration.model_copy(
        update={"release_version": "primary.3", "bundle_id": "wa-2026-primary-primary.3"}
    )
    selected = resolved.site.model_copy(update={"elections": [newer]})
    assert (
        promotion.promotion_allowed(
            publication, selected=selected, latest_verified=receipt(publication)
        )
        is False
    )


@pytest.mark.parametrize("field", ["publication_request", "source_panel_hash"])
def test_same_version_conflicting_selection_fails(
    promotion_setup: tuple[Any, ...], field: str
) -> None:
    promotion, resolved, record, _, _, _, publication = promotion_setup
    request = record.declaration.publication_request
    changed = (
        request.model_copy(update={"issue_number": 999})
        if field == "publication_request"
        else "9" * 64
    )
    selected = resolved.site.model_copy(
        update={"elections": [record.declaration.model_copy(update={field: changed})]}
    )
    with pytest.raises(ValueError, match="conflict"):
        promotion.promotion_allowed(publication, selected=selected, latest_verified=None)


@pytest.mark.parametrize("status", ["ahead", "behind", "diverged"])
def test_out_of_order_release_cannot_replace_newer_production(
    promotion_setup: tuple[Any, ...], monkeypatch: pytest.MonkeyPatch, status: str
) -> None:
    promotion, resolved, _, _, _, _, publication = promotion_setup
    prior = receipt(publication)
    payload = prior.model_dump(mode="json")
    # A distinct, previously verified publication at another source.
    for candidate in (
        payload["publication"]["published"]["candidate"],
        payload["upload"]["publication"]["published"]["candidate"],
    ):
        candidate["source_sha"] = "a" * 40
        candidate["producer"]["source_sha"] = "a" * 40
        candidate["producer"]["workflow_sha"] = "a" * 40
        for kind in ("release_artifact", "site_artifact"):
            candidate[kind]["producer"] = candidate["producer"]
    for pub in (payload["publication"], payload["upload"]["publication"]):
        for kind in ("candidate_artifact",):
            pub["published"][kind]["producer"] = pub["published"]["candidate"]["producer"]
        pub["promotion_artifact"]["producer"] = pub["published"]["candidate"]["producer"]
    payload["producer"] = payload["publication"]["published"]["candidate"]["producer"]
    payload["upload"]["producer"] = payload["producer"]
    payload["upload"]["source_sha"] = "a" * 40
    prior = OperationReceipt.model_validate_json(json.dumps(payload))

    def api(command: list[str], failure: str) -> str:
        assert (
            command[2]
            == f"repos/owner/repository/compare/{'a' * 40}..."
            + publication.published.candidate.source_sha
        )
        return json.dumps({"status": status, "merge_base_commit": {"sha": "a" * 40}})

    monkeypatch.setattr(promotion, "run_gh", api)
    if status == "ahead":
        assert promotion.promotion_allowed(
            publication, selected=resolved.site, latest_verified=prior
        )
    else:
        with pytest.raises(ValueError, match="lineage"):
            promotion.promotion_allowed(publication, selected=resolved.site, latest_verified=prior)


def test_allowed_merge_after_final_check_does_not_change_captured_decision(
    promotion_setup: tuple[Any, ...],
) -> None:
    promotion, resolved, _, _, _, _, publication = promotion_setup
    assert promotion.promotion_allowed(publication, selected=resolved.site, latest_verified=None)
    # The lock keeps upload serialization; a later merge is handled by its own queued run.
    changed = resolved.current.model_copy(
        update={"release_version": "primary.3", "bundle_id": "wa-2026-primary-primary.3"}
    )
    next_selection = resolved.site.model_copy(update={"elections": [changed]})
    assert not promotion.promotion_allowed(
        publication, selected=next_selection, latest_verified=None
    )


class AdmissionAPI:
    def __init__(self, sha: str):
        self.sha = sha
        self.prs: list[dict[str, Any]] = [
            {
                "number": 550,
                "merged_at": "2026-10-16T12:00:00Z",
                "merge_commit_sha": sha,
                "base": {"ref": "main", "repo": {"full_name": "owner/repository"}},
            }
        ]
        self.run: dict[str, Any] = {
            "id": 100,
            "run_attempt": 2,
            "head_sha": sha,
            "head_branch": "main",
            "event": "push",
            "path": ".github/workflows/ci.yml",
            "status": "in_progress",
            "conclusion": None,
            "repository": {"full_name": "owner/repository"},
            "run_started_at": "2026-10-16T12:00:00Z",
        }
        self.latest_run: dict[str, Any] | None = None
        self.attempt_runs: dict[int, dict[str, Any]] = {}
        self.jobs: list[dict[str, Any]] = [
            {"name": name, "head_sha": sha, "status": "completed", "conclusion": "success"}
            for name in (
                "Python static checks",
                "Client checks",
                "Repository contracts",
                "pytest (unit)",
                "pytest (integration-comparisons)",
                "pytest (integration-rendering)",
                "pytest (integration-artifacts)",
                "Publication build",
            )
        ]

    def __call__(self, command: list[str], failure: str) -> str:
        endpoint = command[2]
        if endpoint.endswith("/pulls?per_page=100"):
            return json.dumps([self.prs])
        if "/compare/" in endpoint:
            return json.dumps({"status": "ahead", "merge_base_commit": {"sha": self.sha}})
        if endpoint.endswith("/jobs?per_page=100"):
            return json.dumps([{"jobs": self.jobs}])
        if "/attempts/" in endpoint:
            attempt = int(endpoint.rsplit("/", 1)[1])
            return json.dumps(self.attempt_runs.get(attempt, self.run))
        if endpoint.endswith("/actions/runs/100"):
            return json.dumps(self.latest_run if self.latest_run is not None else self.run)
        if "actions/workflows/ci.yml/runs?" in endpoint:
            return json.dumps([{"workflow_runs": [self.run]}])
        raise AssertionError(endpoint)


@pytest.fixture
def admission(promotion_setup: tuple[Any, ...], monkeypatch: pytest.MonkeyPatch) -> tuple[Any, ...]:
    promotion, _, record, _, _, root, _ = promotion_setup
    _git(root, "remote", "add", "origin", "https://github.com/owner/repository.git")
    api = AdmissionAPI(record.source_sha)
    monkeypatch.setattr(promotion, "run_gh", api)
    monkeypatch.setenv("GITHUB_RUN_ID", "100")
    monkeypatch.setenv("GITHUB_RUN_ATTEMPT", "2")
    monkeypatch.setenv("GITHUB_SHA", record.source_sha)
    monkeypatch.setenv("GITHUB_REF", "refs/heads/main")
    monkeypatch.delenv("RELEASE_SOURCE_SHA", raising=False)
    return promotion, record, root, api


def test_same_workflow_admission_uses_successful_lanes_while_run_is_active(
    admission: tuple[Any, ...],
) -> None:
    promotion, record, root, _ = admission
    assert promotion.verify_merged_release_source(root, source_sha=record.source_sha) == 550


@pytest.mark.parametrize(
    "case",
    [
        "pr-ref",
        "branch",
        "missing",
        "ambiguous",
        "wrong-merge",
        "not-merged",
        "failed-ci",
        "missing-lane",
        "wrong-source",
    ],
)
def test_source_requires_merged_main_pr(admission: tuple[Any, ...], case: str) -> None:
    promotion, record, root, api = admission
    sha = record.source_sha
    if case == "pr-ref":
        sha = "refs/pull/550/merge"
    elif case == "branch":
        api.prs[0]["base"]["ref"] = "feature"
    elif case == "missing":
        api.prs.clear()
    elif case == "ambiguous":
        api.prs.append({**api.prs[0], "number": 551})
    elif case == "wrong-merge":
        api.prs[0]["merge_commit_sha"] = "a" * 40
    elif case == "not-merged":
        api.prs[0]["merged_at"] = None
    elif case == "failed-ci":
        api.jobs[0]["conclusion"] = "failure"
    elif case == "missing-lane":
        api.jobs.pop()
    else:
        api.run["head_sha"] = "a" * 40
    with pytest.raises(ValueError):
        promotion.verify_merged_release_source(root, source_sha=sha)


def artifact_metadata(record: Any, artifact: Any) -> dict[str, Any]:
    return {
        "id": artifact.id,
        "name": artifact.name,
        "size_in_bytes": artifact.digest.size,
        "digest": "sha256:" + artifact.digest.sha256,
        "expired": True,
        "created_at": "2026-10-16T12:30:00Z",
        "workflow_run": {
            "id": record.producer.run_id,
            "head_sha": record.producer.workflow_sha,
            "head_branch": "main",
        },
    }


@pytest.mark.parametrize("condition", ["expired", "missing", "failed-gate"])
def test_expired_artifact_rebuilds_original_sha(
    promotion_setup: tuple[Any, ...], monkeypatch: pytest.MonkeyPatch, condition: str
) -> None:
    promotion, resolved, record, archive, original_bundle, root, _ = promotion_setup
    from election_guide.release import candidate

    (root / "README.md").write_text("main advanced\n")
    _git(root, "add", "README.md")
    _git(root, "commit", "-qm", "docs: newer main")
    rebuilt_source_shas: list[str] = []
    commands: list[list[str]] = []

    def run(command: list[str], *, repository: Path) -> None:
        assert _git(repository, "rev-parse", "HEAD") == record.source_sha
        assert _git(repository, "rev-parse", "--abbrev-ref", "HEAD") == "HEAD"
        commands.append(command)
        if condition == "failed-gate" and command == ["make", "check"]:
            raise ValueError("fresh source checks failed")
        if "build" in command:
            output = Path(command[command.index("--output-dir") + 1])
            candidate.build_current_candidate(
                resolve(Path("config/hosting/site.yaml"), repository=repository),
                repository=repository,
                output_dir=output,
                source_sha=command[command.index("--source-sha") + 1],
            )

    def resolve(_path: Path, *, repository: Path) -> ResolvedRelease:
        assert _git(repository, "rev-parse", "HEAD") == record.source_sha
        return ResolvedRelease(
            read_site_manifest(repository / "config/hosting/site.yaml"),
            resolved.current,
            ReleaseInputs(
                *(
                    repository / name
                    for name in (
                        "ledger",
                        "inventory",
                        "registry",
                        "dataset",
                        "snapshots",
                        "manifests",
                    )
                )
            ),
            archive.name,
        )

    _git(root, "remote", "add", "origin", "https://github.com/owner/repository.git")
    admission_api = AdmissionAPI(record.source_sha)

    def api(command: list[str], failure: str) -> str:
        if "/actions/artifacts/" in command[2]:
            if condition == "missing":
                raise ValueError("could not read release admission: Not Found (HTTP 404)")
            artifact = (
                record.release_artifact if command[2].endswith("/10") else record.site_artifact
            )
            return json.dumps(artifact_metadata(record, artifact))
        return admission_api(command, failure)

    def build_release(**kwargs: Any) -> None:
        rebuilt_source_shas.append(kwargs["git_commit"])
        assert _git(kwargs["repository_root"], "rev-parse", "HEAD") == record.source_sha
        output = kwargs["output_dir"]
        shutil.copytree(original_bundle, output / "bundle")
        shutil.copy2(archive, output / archive.name)

    def history(repository: Path, **kwargs: Any) -> None:
        assert _git(repository, "rev-parse", "HEAD") == record.source_sha
        assert kwargs["source_sha"] == record.source_sha

    monkeypatch.setattr(candidate, "build_release", build_release)
    monkeypatch.setattr(candidate, "generate_software_history", history)
    monkeypatch.setattr(promotion, "run_gh", api)
    monkeypatch.setattr(promotion, "_run", run)
    monkeypatch.setattr(promotion, "resolve_release", resolve)
    monkeypatch.setattr(candidate, "resolve_release", resolve)
    output = root / "dist/recovery"
    if condition == "failed-gate":
        with pytest.raises(ValueError, match="fresh source checks failed"):
            promotion.recover_candidate(record, repository=root, work_dir=output)
        assert not (output / "source").exists()
        assert not (output / "reproducibility-a").exists()
        assert (output / "original-candidate.json").is_file()
        return
    rebuilt = promotion.recover_candidate(record, repository=root, work_dir=output)
    assert rebuilt.read_bytes() == archive.read_bytes()
    assert rebuilt_source_shas == [record.source_sha, record.source_sha]
    assert commands[:3] == [["uv", "sync", "--frozen"], ["npm", "ci"], ["make", "check"]]
    assert json.loads((output / "original-candidate.json").read_bytes())[
        "producer"
    ] == record.producer.model_dump(mode="json")
    assert _git(root, "rev-parse", "HEAD") != record.source_sha


@pytest.mark.parametrize("changed", ["id", "name", "digest", "producer"])
def test_wrong_existing_artifact_never_silently_recovers(
    promotion_setup: tuple[Any, ...], monkeypatch: pytest.MonkeyPatch, changed: str
) -> None:
    promotion, _, record, _, _, root, _ = promotion_setup
    metadata = artifact_metadata(record, record.release_artifact)
    metadata["expired"] = False
    if changed == "producer":
        metadata["workflow_run"]["head_sha"] = "a" * 40
    else:
        metadata[changed] = {"id": 99, "name": "release-other", "digest": "sha256:" + "0" * 64}[
            changed
        ]

    def api(command: list[str], failure: str) -> str:
        return json.dumps(metadata)

    monkeypatch.setattr(promotion, "run_gh", api)
    with pytest.raises(ValueError, match="artifact"):
        promotion.recover_candidate(record, repository=root, work_dir=root / "dist/recovery")


def test_cli_promotion_check_writes_superseded_state(
    promotion_setup: tuple[Any, ...], monkeypatch: pytest.MonkeyPatch
) -> None:
    from election_guide.release import automation_cli

    _, resolved, record, _, _, root, publication = promotion_setup
    selected = resolved.site.model_copy(
        update={
            "elections": [
                record.declaration.model_copy(
                    update={
                        "release_version": "primary.3",
                        "bundle_id": "wa-2026-primary-primary.3",
                    }
                )
            ]
        }
    )

    def selected_main(repository: Path) -> Any:
        return selected

    monkeypatch.setattr(automation_cli, "_selected_main", selected_main)
    monkeypatch.setattr(automation_cli, "_repository", lambda: root)
    path, output = root / "dist/publication.json", root / "dist/guard.json"
    path.write_text(publication.model_dump_json())
    result = CliRunner().invoke(
        automation_cli.app, ["promotion-check", "--publication", str(path), "--output", str(output)]
    )
    assert result.exit_code == 0, result.output
    assert json.loads(output.read_bytes()) == {"eligible": False, "state": "superseded"}


@pytest.mark.parametrize("changed", ["producer-source", "missing-request", "request-inputs"])
def test_promotion_rejects_conflicting_trusted_record(
    promotion_setup: tuple[Any, ...], changed: str
) -> None:
    promotion, resolved, _, _, _, _, publication = promotion_setup
    prior = receipt(publication)
    if changed == "producer-source":
        producer = prior.producer.model_copy(update={"source_sha": "a" * 40})
        assert prior.upload is not None
        prior = prior.model_copy(
            update={
                "producer": producer,
                "upload": prior.upload.model_copy(update={"producer": producer}),
            }
        )
    else:
        candidate = publication.published.candidate
        declaration = candidate.declaration
        if changed == "missing-request":
            declaration = declaration.model_copy(update={"publication_request": None})
        else:
            candidate = candidate.model_copy(
                update={"inputs": candidate.inputs.model_copy(update={"ledger_sha256": "0" * 64})}
            )
        candidate = candidate.model_copy(update={"declaration": declaration})
        publication = publication.model_copy(
            update={"published": publication.published.model_copy(update={"candidate": candidate})}
        )
        resolved = ResolvedRelease(
            resolved.site.model_copy(update={"elections": [declaration]}),
            declaration,
            resolved.inputs,
            resolved.archive_name,
        )
        prior = None
    with pytest.raises(ValueError):
        promotion.promotion_allowed(publication, selected=resolved.site, latest_verified=prior)


def test_malformed_artifact_producer_is_a_failed_admission(
    promotion_setup: tuple[Any, ...], monkeypatch: pytest.MonkeyPatch
) -> None:
    promotion, _, record, _, _, root, _ = promotion_setup
    metadata = artifact_metadata(record, record.release_artifact)
    metadata["workflow_run"] = None

    def api(command: list[str], failure: str) -> str:
        return json.dumps(metadata)

    monkeypatch.setattr(promotion, "run_gh", api)
    with pytest.raises(ValueError, match="artifact"):
        promotion.recover_candidate(record, repository=root, work_dir=root / "dist/recovery")


def test_preflight_waits_for_ci_before_claiming_publication_eligibility(
    admission: tuple[Any, ...], monkeypatch: pytest.MonkeyPatch
) -> None:
    import yaml

    from election_guide.release import automation_cli, publication

    promotion, _, root, _ = admission
    path = root / "config/hosting/site.yaml"
    base = read_site_manifest(path)
    declaration = base.elections[0].model_copy(
        update={"release_version": "2026-primary.2", "bundle_id": "wa-2026-primary-2026-primary.2"}
    )
    base = base.model_copy(update={"elections": [declaration]})
    path.write_text(yaml.safe_dump(base.model_dump(mode="json")))
    _git(root, "add", ".")
    _git(root, "commit", "-qm", "feat: base declaration")
    base_sha = _git(root, "rev-parse", "HEAD")
    _git(root, "tag", "2026-primary.2")
    assert declaration.publication_request is not None
    request = declaration.publication_request.model_copy(
        update={"issue_number": 551, "previous_release_sha": base_sha}
    )
    declaration = declaration.model_copy(
        update={
            "release_version": "2026-primary.3",
            "bundle_id": "wa-2026-primary-2026-primary.3",
            "publication_request": request,
        }
    )
    selected = base.model_copy(update={"elections": [declaration]})
    path.write_text(yaml.safe_dump(selected.model_dump(mode="json")))
    _git(root, "add", ".")
    _git(root, "commit", "-qm", "feat: next reviewed release")
    sha = _git(root, "rev-parse", "HEAD")
    api = AdmissionAPI(sha)
    api.jobs[-1]["status"] = "in_progress"
    api.jobs[-1]["conclusion"] = None

    def published_base(command: list[str], failure: str) -> str:
        endpoint = command[2]
        if endpoint.endswith("/tags?per_page=100"):
            return json.dumps([[{"name": "2026-primary.2"}]])
        if endpoint.endswith("/releases?per_page=100"):
            return json.dumps(
                [
                    [
                        {
                            "id": 20,
                            "tag_name": "2026-primary.2",
                            "draft": False,
                            "prerelease": False,
                        }
                    ]
                ]
            )
        if endpoint.endswith("/git/ref/tags/2026-primary.2"):
            return json.dumps({"object": {"type": "commit", "sha": base_sha}})
        raise AssertionError((command, failure))

    monkeypatch.setattr(automation_cli, "run_gh", published_base)
    monkeypatch.setattr(publication, "run_gh", published_base)
    monkeypatch.setattr(promotion, "run_gh", api)
    monkeypatch.setenv("GITHUB_SHA", sha)
    monkeypatch.setattr(automation_cli, "_repository", lambda: root)

    def resolve(site_path: Path, *, repository: Path) -> ResolvedRelease:
        return ResolvedRelease(
            read_site_manifest(repository / site_path),
            declaration,
            ReleaseInputs(
                *(
                    repository / name
                    for name in (
                        "ledger",
                        "inventory",
                        "registry",
                        "dataset",
                        "snapshots",
                        "manifests",
                    )
                )
            ),
            "unused.zip",
        )

    monkeypatch.setattr(automation_cli, "resolve_release", resolve)
    args = ["admit", "--source-sha", sha, "--base-sha", base_sha]
    preflight = CliRunner().invoke(automation_cli.app, [*args, "--preflight"])
    assert preflight.exit_code == 0, preflight.output
    payload = json.loads(preflight.stdout)
    assert payload["requests_release"] is True
    assert payload["eligible"] is False
    assert payload["ci_verified"] is False
    assert payload["state"] == "pending_ci"
    final = CliRunner().invoke(automation_cli.app, args)
    assert final.exit_code == 1
    assert json.loads(final.stdout)["state"] == "failed"
    api.jobs[-1]["status"], api.jobs[-1]["conclusion"] = "completed", "success"
    final = CliRunner().invoke(automation_cli.app, args)
    assert final.exit_code == 0, final.output
    payload = json.loads(final.stdout)
    assert payload["eligible"] is True
    assert payload["ci_verified"] is True
    assert payload["state"] == "eligible"


@pytest.mark.parametrize(
    "case",
    [
        "valid",
        "wrong-source",
        "wrong-workflow",
        "wrong-run",
        "wrong-attempt",
        "non-main",
        "push",
        "foreign-repository",
        "foreign-workflow",
    ],
)
def test_recovery_admission_requires_current_dispatch_and_fresh_lanes(
    admission: tuple[Any, ...], monkeypatch: pytest.MonkeyPatch, case: str
) -> None:
    promotion, record, root, api = admission
    workflow_sha = "b" * 40
    monkeypatch.setenv("GITHUB_SHA", workflow_sha)
    monkeypatch.setenv("RELEASE_SOURCE_SHA", record.source_sha)
    monkeypatch.setenv("GITHUB_REF", "refs/heads/main")
    api.run.update(head_sha=workflow_sha, event="workflow_dispatch")
    for job in api.jobs:
        job["head_sha"] = workflow_sha
    if case == "wrong-source":
        monkeypatch.setenv("RELEASE_SOURCE_SHA", "a" * 40)
    elif case == "wrong-workflow":
        api.run["head_sha"] = "c" * 40
    elif case == "wrong-run":
        api.run["id"] = 101
    elif case == "wrong-attempt":
        api.run["run_attempt"] = 1
    elif case == "non-main":
        monkeypatch.setenv("GITHUB_REF", "refs/heads/feature")
    elif case == "push":
        api.run["event"] = "push"
    elif case == "foreign-repository":
        api.run["repository"]["full_name"] = "stranger/repository"
    elif case == "foreign-workflow":
        api.run["path"] = ".github/workflows/other.yml"
    if case == "valid":
        assert promotion.verify_merged_release_source(root, source_sha=record.source_sha) == 550
    else:
        with pytest.raises(ValueError):
            promotion.verify_merged_release_source(root, source_sha=record.source_sha)


def test_no_historical_success_substitutes_for_captured_current_run(
    admission: tuple[Any, ...], monkeypatch: pytest.MonkeyPatch
) -> None:
    promotion, record, root, api = admission
    monkeypatch.delenv("GITHUB_RUN_ID")
    api.run["status"], api.run["conclusion"] = "completed", "success"
    with pytest.raises(ValueError, match="current"):
        promotion.verify_merged_release_source(root, source_sha=record.source_sha)


@pytest.mark.parametrize(
    "condition",
    [
        "healthy",
        "wrong-download",
        "wrong-attempt",
        "service-failure",
        "earlier-attempt-artifact",
        "later-attempt-artifact",
        "lower-bound",
        "upper-inside",
        "created-missing",
        "created-naive",
        "created-malformed",
        "started-missing",
        "started-naive",
        "next-started-missing",
        "next-before-current",
        "latest-before-claimed",
        "latest-start-conflict",
    ],
)
def test_captured_artifact_download_is_verified_without_fallback(
    promotion_setup: tuple[Any, ...], monkeypatch: pytest.MonkeyPatch, condition: str
) -> None:
    import hashlib
    import io
    import zipfile

    from election_guide.release import candidate
    from election_guide.release.automation_models import FileDigest

    promotion, resolved, record, archive, _, root, _ = promotion_setup
    wrappers: dict[int, bytes] = {}
    for ref, files in (
        (record.release_artifact, {archive.name: archive.read_bytes()}),
        (
            record.site_artifact,
            {
                path.relative_to(root / "dist/site").as_posix(): path.read_bytes()
                for path in (root / "dist/site").rglob("*")
                if path.is_file()
            },
        ),
    ):
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w") as wrapper:
            for name, content in files.items():
                wrapper.writestr(name, content)
        wrappers[ref.id] = buffer.getvalue()
    refs = {
        ref.id: ref.model_copy(
            update={
                "digest": FileDigest(
                    sha256=hashlib.sha256(wrappers[ref.id]).hexdigest(), size=len(wrappers[ref.id])
                )
            }
        )
        for ref in (record.release_artifact, record.site_artifact)
    }
    record = record.model_copy(update={"release_artifact": refs[10], "site_artifact": refs[11]})
    _git(root, "remote", "add", "origin", "https://github.com/owner/repository.git")
    admission_api = AdmissionAPI(record.source_sha)
    if condition == "wrong-attempt":
        admission_api.run["run_attempt"] = 1
    admission_api.attempt_runs[1] = {
        **admission_api.run,
        "run_attempt": 1,
        "run_started_at": "2026-10-16T11:00:00Z",
    }
    if condition in {
        "later-attempt-artifact",
        "upper-inside",
        "next-started-missing",
        "next-before-current",
    }:
        third = {**admission_api.run, "run_attempt": 3, "run_started_at": "2026-10-16T13:00:00Z"}
        admission_api.latest_run = third.copy()
        admission_api.attempt_runs[3] = third
        if condition == "next-started-missing":
            third.pop("run_started_at")
        elif condition == "next-before-current":
            third["run_started_at"] = "2026-10-16T11:00:00Z"
    elif condition == "latest-before-claimed":
        admission_api.latest_run = admission_api.attempt_runs[1]
    elif condition == "latest-start-conflict":
        admission_api.latest_run = {**admission_api.run, "run_started_at": "2026-10-16T11:59:00Z"}
    if condition == "started-missing":
        admission_api.run.pop("run_started_at")
    elif condition == "started-naive":
        admission_api.run["run_started_at"] = "2026-10-16T12:00:00"
    allowed = {"healthy", "lower-bound", "upper-inside"}
    time_failures = {
        "earlier-attempt-artifact",
        "later-attempt-artifact",
        "created-missing",
        "created-naive",
        "created-malformed",
        "started-missing",
        "started-naive",
        "next-started-missing",
        "next-before-current",
        "latest-before-claimed",
        "latest-start-conflict",
    }

    def api(command: list[str], failure: str) -> str:
        if "/actions/artifacts/" in command[2]:
            if condition == "service-failure":
                raise ValueError("could not read release admission: unavailable (HTTP 503)")
            metadata = artifact_metadata(record, refs[int(command[2].rsplit("/", 1)[1])])
            metadata["expired"] = False
            if condition == "earlier-attempt-artifact":
                metadata["created_at"] = "2026-10-16T11:30:00Z"
            elif condition == "later-attempt-artifact":
                metadata["created_at"] = "2026-10-16T13:00:00Z"
            elif condition == "lower-bound":
                metadata["created_at"] = "2026-10-16T12:00:00Z"
            elif condition == "upper-inside":
                metadata["created_at"] = "2026-10-16T12:59:59Z"
            elif condition == "created-missing":
                metadata.pop("created_at")
            elif condition == "created-naive":
                metadata["created_at"] = "2026-10-16T12:30:00"
            elif condition == "created-malformed":
                metadata["created_at"] = "not a timestamp"
            return json.dumps(metadata)
        return admission_api(command, failure)

    def download(command: list[str], destination: Path, failure: str) -> None:
        if condition in time_failures:
            pytest.fail("attempt-conflicting artifacts must be rejected before downloads")
        artifact_id = int(command[2].split("/")[-2])
        destination.write_bytes(
            b"wrong bytes" if condition == "wrong-download" else wrappers[artifact_id]
        )

    def resolve(_path: Path, *, repository: Path) -> ResolvedRelease:
        return ResolvedRelease(
            read_site_manifest(repository / "config/hosting/site.yaml"),
            resolved.current,
            ReleaseInputs(
                *(
                    repository / name
                    for name in (
                        "ledger",
                        "inventory",
                        "registry",
                        "dataset",
                        "snapshots",
                        "manifests",
                    )
                )
            ),
            archive.name,
        )

    def no_build(command: list[str], *, repository: Path) -> None:
        pytest.fail("a healthy or conflicting artifact must never trigger fallback build")

    monkeypatch.setattr(promotion, "run_gh", api)
    monkeypatch.setattr(promotion, "download_gh", download)
    monkeypatch.setattr(promotion, "resolve_release", resolve)
    monkeypatch.setattr(candidate, "resolve_release", resolve)
    monkeypatch.setattr(promotion, "_run", no_build)
    output = root / "dist/recovery"
    if condition in allowed:
        recovered = promotion.recover_candidate(record, repository=root, work_dir=output)
        assert recovered.read_bytes() == archive.read_bytes()
        assert (output / "cloudflare-site/deployment-manifest.json").read_bytes() == (
            root / "dist/site/deployment-manifest.json"
        ).read_bytes()
        assert not (output / "source").exists()
    else:
        with pytest.raises(ValueError):
            promotion.recover_candidate(record, repository=root, work_dir=output)
        assert not (output / "source").exists()


def test_prior_verified_receipt_allows_new_finalizer_run(promotion_setup: tuple[Any, ...]) -> None:
    promotion, resolved, _, _, _, _, publication = promotion_setup
    prior = receipt(publication)
    prior = prior.model_copy(
        update={
            "producer": prior.producer.model_copy(update={"run_id": 200, "workflow_sha": "f" * 40})
        }
    )
    assert promotion.promotion_allowed(publication, selected=resolved.site, latest_verified=prior)


@pytest.mark.parametrize(
    "identity", ["finalizer_repository", "finalizer_source", "upload_repository", "upload_source"]
)
def test_prior_verified_receipt_rejects_foreign_identity(
    promotion_setup: tuple[Any, ...], identity: str
) -> None:
    promotion, resolved, _, _, _, _, publication = promotion_setup
    prior = receipt(publication)
    field = "repository" if identity.endswith("repository") else "source_sha"
    value = "other/repository" if field == "repository" else "f" * 40
    if identity.startswith("finalizer"):
        prior = prior.model_copy(
            update={"producer": prior.producer.model_copy(update={field: value})}
        )
    else:
        assert prior.upload is not None
        prior = prior.model_copy(
            update={
                "upload": prior.upload.model_copy(
                    update={"producer": prior.upload.producer.model_copy(update={field: value})}
                )
            }
        )
    with pytest.raises(ValueError, match="unverifiable"):
        promotion.promotion_allowed(publication, selected=resolved.site, latest_verified=prior)
