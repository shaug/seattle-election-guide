"""Reviewed publication requests bind bytes and a monotonic election version."""

from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
from pathlib import Path
from typing import Any, cast

import pytest
from typer.testing import CliRunner

from election_guide.cli import app
from election_guide.hosting.pages import read_site_manifest
from election_guide.release.declaration import (
    ResolvedRelease,
    hash_release_inputs,
    prepare_release,
    resolve_release,
    validate_release_request,
)

ROOT = Path(__file__).resolve().parents[1]
SITE = Path("config/hosting/site.yaml")


def git(repo: Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=repo, check=True, text=True, capture_output=True
    ).stdout.strip()


@pytest.fixture
def repository(tmp_path: Path) -> Path:
    paths = [
        SITE,
        Path("data/releases/wa-2026-general/source-decisions.yaml"),
        Path("data/normalized/wa-2026-general-inventory.json"),
        Path("data/normalized/wa-2026-general-canonical-dataset.json"),
        Path("config/sources/wa-2026-general.yaml"),
    ]
    for path in paths:
        target = tmp_path / path
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / path, target)
    for name in ("snapshots", "manifests"):
        (tmp_path / "data/releases/wa-2026-general" / name).mkdir()
        (tmp_path / "data/releases/wa-2026-general" / name / ".gitkeep").touch()
    # Give version-policy fixtures an explicit legacy base independent of activation.
    site = read_site_manifest(tmp_path / SITE)
    site.elections[0].release_version = "2026-general.8"
    site.elections[0].bundle_id = "wa-2026-general-2026-general.8"
    site.elections[0].publication_request = None
    (tmp_path / SITE).write_text(site.model_dump_json())
    git(tmp_path, "init", "-b", "main")
    git(tmp_path, "add", ".")
    git(
        tmp_path,
        "-c",
        "user.name=Test",
        "-c",
        "user.email=test@example.org",
        "commit",
        "-m",
        "base",
    )
    return tmp_path


def prepare(repo: Path, **kwargs: Any) -> ResolvedRelease:
    base = read_site_manifest(repo / SITE)
    return prepare_release(
        SITE,
        repository=repo,
        issue_number=550,
        main_manifest=kwargs.pop("main_manifest", base),
        occupied_versions=kwargs.pop("occupied_versions", frozenset()),
        previous_release_sha=kwargs.pop("previous_release_sha", git(repo, "rev-parse", "HEAD")),
        **kwargs,
    )


def test_resolve_current_identity(repository: Path) -> None:
    resolved = resolve_release(SITE, repository=repository)
    assert resolved.current.release_version == "2026-general.8"
    assert resolved.current.bundle_id == "wa-2026-general-2026-general.8"
    assert resolved.archive_name == "seattle-election-guide-2026-general.8.zip"
    assert (
        resolved.inputs.ledger == repository / "data/releases/wa-2026-general/source-decisions.yaml"
    )
    assert resolved.inputs.snapshots == resolved.inputs.ledger.parent / "snapshots"
    assert resolved.current.publication_request is None


def test_prepare_refreshes_same_unpublished_proposal(repository: Path) -> None:
    base = resolve_release(SITE, repository=repository).site
    archived = base.elections[1].model_dump()
    first = prepare(repository, main_manifest=base)
    first.inputs.ledger.write_text(first.inputs.ledger.read_text() + "\n# reviewed refresh\n")
    second = prepare(repository, main_manifest=base)
    assert first.current.release_version == "2026-general.9"
    assert second.current.release_version == first.current.release_version
    assert second.current.publication_request is not None
    assert second.current.publication_request.inputs == hash_release_inputs(second.inputs)
    assert (
        second.current.publication_request.inputs.ledger_sha256
        == hashlib.sha256(second.inputs.ledger.read_bytes()).hexdigest()
    )
    assert second.site.elections[1].model_dump() == archived


def test_prepare_new_version_clears_current_release_pins(repository: Path) -> None:
    site = read_site_manifest(repository / SITE)
    site.elections[0].git_commit = git(repository, "rev-parse", "HEAD")
    site.elections[0].release_manifest_sha256 = "b" * 64
    site.elections[0].bundle_sha256 = "c" * 64
    (repository / SITE).write_text(site.model_dump_json())
    archived = site.elections[1].model_dump()

    prepared = prepare(repository, main_manifest=site)

    assert prepared.current.release_version == "2026-general.9"
    assert prepared.current.git_commit is None
    assert prepared.current.release_manifest_sha256 is None
    assert prepared.current.bundle_sha256 is None
    assert prepared.site.elections[1].model_dump() == archived
    persisted = resolve_release(SITE, repository=repository)
    assert persisted.current == prepared.current
    assert persisted.site.elections[1].model_dump() == archived


def test_prepare_skips_remote_tag_and_draft_collisions(repository: Path) -> None:
    resolved = prepare(
        repository, occupied_versions=frozenset({"2026-general.9", "2026-general.11"})
    )
    assert resolved.current.release_version == "2026-general.12"


def test_concurrent_proposal_requires_refresh(repository: Path) -> None:
    base = resolve_release(SITE, repository=repository).site
    proposal = prepare(repository, main_manifest=base)
    concurrent = base.model_copy(deep=True)
    concurrent.elections[0].release_version = "2026-general.9"
    concurrent.elections[0].bundle_id = "wa-2026-general-2026-general.9"
    with pytest.raises(ValueError, match="version"):
        validate_release_request(proposal, base=concurrent, changed_paths=(str(SITE),))
    refreshed = prepare(repository, main_manifest=concurrent)
    assert refreshed.current.release_version == "2026-general.10"


@pytest.mark.parametrize("changed", ["ledger", "dataset", "registry", "src/runtime.py", "none"])
def test_request_admission(repository: Path, changed: str) -> None:
    base = resolve_release(SITE, repository=repository).site
    docs_only = resolve_release(SITE, repository=repository)
    assert (
        validate_release_request(docs_only, base=base, changed_paths=("docs/HOSTING.md",)) is False
    )
    if changed == "src/runtime.py":
        with pytest.raises(ValueError, match=r"fresh|request"):
            validate_release_request(docs_only, base=base, changed_paths=(changed,))
        return
    proposal = prepare(repository, main_manifest=base)
    if changed != "none":
        path = getattr(proposal.inputs, changed)
        path.write_bytes(path.read_bytes() + b"\n")
        with pytest.raises(ValueError, match="binding"):
            validate_release_request(proposal, base=base, changed_paths=(str(SITE),))
    else:
        assert validate_release_request(proposal, base=base, changed_paths=(str(SITE),)) is True


@pytest.mark.parametrize("field", ["ledger", "dataset", "inventory", "registry"])
def test_resolver_rejects_different_election(repository: Path, field: str) -> None:
    inputs = resolve_release(SITE, repository=repository).inputs
    path = getattr(inputs, field)
    if field == "dataset":
        raw = json.loads(path.read_text())
        raw["inventory"]["election"]["id"] = "wa-2027-general"
        path.write_text(json.dumps(raw))
    elif field == "registry":
        path.write_text(
            path.read_text().replace("election_id: wa-2026-general", "election_id: wa-2027-general")
        )
    else:
        path.write_text(path.read_text().replace("wa-2026-general", "wa-2027-general"))
    with pytest.raises(ValueError, match=r"election|belongs"):
        resolve_release(SITE, repository=repository)


def test_prepare_rejects_nonancestor_boundary(repository: Path) -> None:
    with pytest.raises(ValueError, match=r"ancestor|commit"):
        prepare(repository, previous_release_sha="f" * 40)
    assert resolve_release(SITE, repository=repository).current.release_version == "2026-general.8"


def test_cli_resolve_and_stale_binding(repository: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(repository)
    result = CliRunner().invoke(app, ["release", "automation", "resolve"])
    assert result.exit_code == 0, result.output
    assert json.loads(result.stdout)["current"]["release_version"] == "2026-general.8"
    base_sha = git(repository, "rev-parse", "HEAD")
    proposal = prepare(repository)
    proposal.inputs.registry.write_bytes(proposal.inputs.registry.read_bytes() + b"\n")
    git(repository, "add", ".")
    git(
        repository,
        "-c",
        "user.name=Test",
        "-c",
        "user.email=test@example.org",
        "commit",
        "-m",
        "stale",
    )
    result = CliRunner().invoke(
        app, ["release", "automation", "validate-request", "--base-sha", base_sha]
    )
    assert result.exit_code == 1
    assert "binding" in result.output


@pytest.mark.parametrize("annotated", [False, True])
def test_cli_preparation_reads_all_remote_names(
    repository: Path, monkeypatch: pytest.MonkeyPatch, annotated: bool
) -> None:
    monkeypatch.chdir(repository)
    git(repository, "tag", "2026-general.8")

    remote_main = read_site_manifest(repository / SITE)
    remote_main.elections[0].release_version = "2026-general.20"
    remote_main.elections[0].bundle_id = "wa-2026-general-2026-general.20"
    sha = git(repository, "rev-parse", "HEAD")

    def remote(command: list[str], failure: str) -> str:
        endpoint = command[2]
        if endpoint.endswith("/git/ref/heads/main"):
            return json.dumps({"object": {"sha": sha, "type": "commit"}})
        if "/contents/" in endpoint:
            assert endpoint.endswith(f"?ref={sha}")
            return remote_main.model_dump_json()
        if endpoint.endswith("/git/ref/tags/2026-general.20"):
            return json.dumps(
                {
                    "object": {
                        "sha": "a" * 40 if annotated else sha,
                        "type": "tag" if annotated else "commit",
                    }
                }
            )
        if endpoint.endswith("/git/tags/" + "a" * 40):
            return json.dumps({"object": {"sha": sha, "type": "commit"}})
        assert "--paginate" in command and "--slurp" in command
        if "/tags?" in endpoint:
            return json.dumps(
                [
                    [{"name": "2026-general.9"}],
                    [{"name": "2026-general.10"}, {"name": "2026-general.20"}],
                ]
            )
        if "/releases?" in endpoint:
            return json.dumps(
                [
                    [
                        {"tag_name": "2026-general.12", "draft": True},
                        {
                            "id": 20,
                            "tag_name": "2026-general.20",
                            "draft": False,
                            "prerelease": False,
                        },
                    ]
                ]
            )
        raise AssertionError((command, failure))

    monkeypatch.setattr("election_guide.release.automation_cli.run_gh", remote)
    monkeypatch.setattr("election_guide.release.publication.run_gh", remote)
    result = CliRunner().invoke(app, ["release", "automation", "prepare", "--issue", "550"])
    assert result.exit_code == 0, result.output
    assert resolve_release(SITE, repository=repository).current.release_version == "2026-general.21"


def test_cli_preparation_rejects_incomplete_remote_query(
    repository: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(repository)

    def incomplete(command: list[str], failure: str) -> str:
        return '{"message":"failure"}'

    monkeypatch.setattr("election_guide.release.automation_cli.run_gh", incomplete)
    result = CliRunner().invoke(app, ["release", "automation", "prepare", "--issue", "550"])
    assert result.exit_code == 1
    assert resolve_release(SITE, repository=repository).current.release_version == "2026-general.8"


def test_cli_admission_rejects_dirty_tracked_input(
    repository: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(repository)
    base_sha = git(repository, "rev-parse", "HEAD")
    ledger = resolve_release(SITE, repository=repository).inputs.ledger
    ledger.write_bytes(ledger.read_bytes() + b"\n")
    result = CliRunner().invoke(
        app, ["release", "automation", "validate-request", "--base-sha", base_sha]
    )
    assert result.exit_code == 1
    assert "clean" in result.output


def test_prepare_refreshes_derived_registry_identity(repository: Path) -> None:
    base = resolve_release(SITE, repository=repository).site
    path = repository / "config/sources/wa-2026-general.yaml"
    path.write_text(
        path.read_text().replace("notes:\n", "notes:\n  - Reviewed discovery metadata update.\n", 1)
    )
    with pytest.raises(ValueError, match="registry semantic identity"):
        resolve_release(SITE, repository=repository)
    refreshed = prepare(repository, main_manifest=base)
    assert refreshed.current.source_registry_hash != base.elections[0].source_registry_hash
    assert refreshed.current.source_panel_hash == base.elections[0].source_panel_hash
    assert resolve_release(SITE, repository=repository).current == refreshed.current


def test_primary_resolves_legacy_input_locations(tmp_path: Path) -> None:
    site = read_site_manifest(ROOT / SITE)
    primary = site.elections[1]
    historical = site.model_copy(
        update={"current_election_id": primary.election_id, "elections": [primary]}
    )
    manifest = tmp_path / "primary.yaml"
    manifest.write_text(historical.model_dump_json())
    resolved = resolve_release(manifest, repository=ROOT)
    assert resolved.inputs.registry == ROOT / "config/sources/default.yaml"
    assert resolved.inputs.dataset == ROOT / "data/normalized/canonical-dataset.json"
    assert resolved.archive_name == f"seattle-election-guide-{primary.release_version}.zip"


def test_all_release_affecting_paths_require_fresh_request(repository: Path) -> None:
    resolved = resolve_release(SITE, repository=repository)
    for path in (
        "src/runtime.py",
        "data/new.json",
        "config/new.yaml",
        "scripts/tool.sh",
        ".github/workflows/check.yml",
        "Makefile",
        "cliff.toml",
        "pyproject.toml",
        "uv.lock",
        "package.json",
        "package-lock.json",
        "wrangler.jsonc",
        "wrangler.toml",
    ):
        with pytest.raises(ValueError, match="fresh publication request"):
            validate_release_request(resolved, base=resolved.site, changed_paths=(path,))


def test_cli_admission_rejects_release_file_renamed_into_docs(
    repository: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(repository)
    (repository / "Makefile").write_text("# production build\n")
    git(repository, "add", ".")
    git(
        repository,
        "-c",
        "user.name=Test",
        "-c",
        "user.email=test@example.org",
        "commit",
        "-m",
        "build",
    )
    base_sha = git(repository, "rev-parse", "HEAD")
    (repository / "docs").mkdir()
    git(repository, "mv", "Makefile", "docs/old-build.txt")
    git(
        repository,
        "-c",
        "user.name=Test",
        "-c",
        "user.email=test@example.org",
        "commit",
        "-m",
        "move",
    )
    result = CliRunner().invoke(
        app, ["release", "automation", "validate-request", "--base-sha", base_sha]
    )
    assert result.exit_code == 1
    assert "fresh publication request" in result.output


def test_cli_admits_reviewed_commit_and_ignores_unchanged_docs(
    repository: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(repository)
    base_sha = git(repository, "rev-parse", "HEAD")
    git(repository, "tag", "2026-general.8")
    proposal = prepare(repository)
    with pytest.raises(ValueError, match="version increment"):
        validate_release_request(proposal, base=proposal.site, changed_paths=("src/runtime.py",))
    git(repository, "add", ".")
    git(
        repository,
        "-c",
        "user.name=Test",
        "-c",
        "user.email=test@example.org",
        "commit",
        "-m",
        "proposal",
    )
    result = CliRunner().invoke(
        app, ["release", "automation", "validate-request", "--base-sha", base_sha]
    )
    assert result.exit_code == 0, result.output
    assert json.loads(result.stdout) == {"requests_release": True}
    base_sha = git(repository, "rev-parse", "HEAD")
    (repository / "README.md").write_text("Documentation only.\n")
    git(repository, "add", ".")
    git(
        repository,
        "-c",
        "user.name=Test",
        "-c",
        "user.email=test@example.org",
        "commit",
        "-m",
        "docs",
    )
    result = CliRunner().invoke(
        app, ["release", "automation", "validate-request", "--base-sha", base_sha]
    )
    assert result.exit_code == 0, result.output
    assert json.loads(result.stdout) == {"requests_release": False}


def commit_fixture(repo: Path, message: str) -> str:
    git(repo, "add", ".")
    git(repo, "-c", "user.name=Test", "-c", "user.email=test@example.org", "commit", "-m", message)
    return git(repo, "rev-parse", "HEAD")


@pytest.mark.parametrize("command", ["prepare", "validate-request", "admit", "preflight"])
@pytest.mark.parametrize(
    "case",
    [
        "healthy",
        "published-base",
        "tag-reservation",
        "draft-reservation",
        "wrong-owner",
        "wrong-tag",
        "prior-draft",
        "prior-missing",
        "wrong-prior-version",
        "wrong-prior-election",
        "missing-prior-object",
        "nonancestor-base",
        "api-error",
        "malformed-pages",
        "partial-pages",
        "malformed-release",
        "same-version",
        "stale-inputs",
    ],
)
def test_cli_failed_main_recovery_requires_verified_unpublished_base(
    repository: Path, monkeypatch: pytest.MonkeyPatch, command: str, case: str
) -> None:
    from election_guide.hosting import promotion
    from election_guide.release import automation_cli, publication
    from tests.test_release_promotion import AdmissionAPI

    monkeypatch.chdir(repository)
    prior_sha = git(repository, "rev-parse", "HEAD")
    original_sha = prior_sha
    if case == "nonancestor-base":
        git(repository, "checkout", "-b", "published-line")
        (repository / "prior-lineage.txt").write_text("Published predecessor on a separate line.\n")
        prior_sha = commit_fixture(repository, "fixture: separately published predecessor")
        git(repository, "checkout", "main")
    prior = read_site_manifest(repository / SITE)
    if case in {"wrong-prior-version", "wrong-prior-election"}:
        if case == "wrong-prior-version":
            prior.elections[0].release_version = "2026-general.9"
            prior.elections[0].bundle_id = "wa-2026-general-2026-general.9"
        else:
            prior.elections = [prior.elections[1]]
            prior.current_election_id = prior.elections[0].election_id
        (repository / SITE).write_text(prior.model_dump_json())
        prior_sha = commit_fixture(repository, "fixture: invalid predecessor declaration")
        # The selected failed declaration still belongs to the general election.
        original = read_site_manifest(ROOT / SITE)
        original.elections[0].release_version = "2026-general.8"
        original.elections[0].bundle_id = "wa-2026-general-2026-general.8"
        original.elections[0].publication_request = None
        (repository / SITE).write_text(original.model_dump_json())
    failed = prepare(
        repository, previous_release_sha=original_sha if case == "nonancestor-base" else prior_sha
    )
    if case == "wrong-prior-version":
        failed.current.release_version = "2026-general.9"
        failed.current.bundle_id = "wa-2026-general-2026-general.9"
    if case == "nonancestor-base":
        assert failed.current.publication_request is not None
        failed.current.publication_request.previous_release_sha = prior_sha
    if case == "missing-prior-object":
        assert failed.current.publication_request is not None
        failed.current.publication_request.previous_release_sha = "f" * 40
    (repository / SITE).write_text(failed.site.model_dump_json())
    failed_sha = commit_fixture(repository, "fixture: failed automatic release")
    if case == "nonancestor-base":
        git(
            repository,
            "-c",
            "user.name=Test",
            "-c",
            "user.email=test@example.org",
            "merge",
            "--no-ff",
            "published-line",
            "-m",
            "fixture: bring predecessor into HEAD",
        )
        # HEAD now includes the predecessor; the exact failed base still does not.
        assert git(repository, "merge-base", prior_sha, "HEAD") == prior_sha
        assert git(repository, "merge-base", prior_sha, failed_sha) == original_sha
    failed = resolve_release(SITE, repository=repository)
    version = failed.current.release_version
    if command != "prepare":
        proposal = prepare(repository, main_manifest=failed.site, previous_release_sha=prior_sha)
        if case == "same-version":
            proposal.current.release_version = version
            proposal.current.bundle_id = failed.current.bundle_id
        if case == "wrong-owner":
            assert proposal.current.publication_request is not None
            proposal.current.publication_request.issue_number = 551
        (repository / SITE).write_text(proposal.site.model_dump_json())
        if case == "stale-inputs":
            proposal.inputs.ledger.write_bytes(proposal.inputs.ledger.read_bytes() + b"\n")
        (repository / "src").mkdir(exist_ok=True)
        (repository / "src/runtime.py").write_text("# corrected implementation fixture\n")
        source_sha = commit_fixture(repository, "fix: corrected release")
    else:
        source_sha = failed_sha
    tags: list[dict[str, Any]] = [{"name": "2026-general.8"}]
    releases: list[dict[str, Any]] = [
        {
            "id": 1,
            "tag_name": "2026-general.8",
            "draft": False,
            "prerelease": False,
        }
    ]
    if case == "tag-reservation":
        tags.append({"name": version})
    if case == "published-base":
        tags.append({"name": version})
        releases.append({"id": 2, "tag_name": version, "draft": False, "prerelease": False})
        git(repository, "tag", version, failed_sha)
    if case == "draft-reservation":
        releases.append({"id": 2, "tag_name": version, "draft": True, "prerelease": False})
    if case == "prior-draft":
        releases[0]["draft"] = True
    if case == "prior-missing":
        releases.clear()
    if case == "malformed-release":
        releases.append({"id": 3, "draft": True})
    api = AdmissionAPI(source_sha)
    git(repository, "remote", "add", "origin", "https://github.com/owner/repository.git")
    for key, value in {
        "GITHUB_SHA": source_sha,
        "GITHUB_RUN_ID": "100",
        "GITHUB_RUN_ATTEMPT": "2",
        "GITHUB_REF": "refs/heads/main",
    }.items():
        monkeypatch.setenv(key, value)

    def remote(args: list[str], failure: str) -> str:
        endpoint = args[2]
        if endpoint.endswith("/git/ref/heads/main"):
            return json.dumps({"object": {"sha": failed_sha, "type": "commit"}})
        if "/contents/" in endpoint:
            assert endpoint.endswith(f"?ref={failed_sha}")
            return failed.site.model_dump_json()
        if "/tags?" in endpoint or "/releases?" in endpoint:
            assert "--paginate" in args and "--slurp" in args
            if case == "api-error":
                raise ValueError("fixture service unavailable (HTTP 503)")
            if case == "malformed-pages":
                return '{"message":"denied"}'
            if case == "partial-pages":
                return json.dumps([tags, {"message": "second page denied"}])
            return json.dumps([tags if "/tags?" in endpoint else releases])
        if "/git/ref/tags/" in endpoint:
            tag = endpoint.rsplit("/", 1)[1]
            if tag == "2026-general.8":
                sha = failed_sha if case == "wrong-tag" else prior_sha
                return json.dumps({"object": {"sha": sha, "type": "commit"}})
            if tag == version and case == "published-base":
                return json.dumps({"object": {"sha": failed_sha, "type": "commit"}})
            raise ValueError("fixture tag missing (HTTP 404)")
        return api(args, failure)

    monkeypatch.setattr(automation_cli, "run_gh", remote)
    monkeypatch.setattr(publication, "run_gh", remote)
    monkeypatch.setattr(promotion, "run_gh", remote)
    real_run = subprocess.run

    def fixture_git(args: list[str], **kwargs: Any) -> Any:
        if args[:3] == ["git", "fetch", "--no-tags"]:
            return subprocess.CompletedProcess(args, 1, stdout="", stderr="fixture object absent")
        return cast(Any, real_run(args, **kwargs))

    monkeypatch.setattr(subprocess, "run", fixture_git)
    before = (repository / SITE).read_bytes()
    args = ["prepare", "--issue", "551" if case == "wrong-owner" else "550"]
    if command == "validate-request":
        args = [command, "--base-sha", failed_sha]
    elif command in {"admit", "preflight"}:
        args = ["admit", "--source-sha", source_sha, "--base-sha", failed_sha]
        if command == "preflight":
            args.append("--preflight")
    result = CliRunner().invoke(automation_cli.app, args)
    # Same-version/stale mutations apply to admission, not preparation's refresh.
    allowed = case == "healthy" or (
        command == "prepare" and case in {"same-version", "stale-inputs", "published-base"}
    )
    if allowed:
        assert result.exit_code == 0, result.output
        if command == "prepare":
            recovered = resolve_release(SITE, repository=repository)
            assert recovered.current.release_version == "2026-general.10"
            assert recovered.current.publication_request is not None
            if case == "published-base":
                assert recovered.current.publication_request.previous_release_sha == failed_sha
                assert recovered.current.publication_request != failed.current.publication_request
            else:
                assert recovered.current.publication_request == failed.current.publication_request
            assert recovered.site.elections[1:] == failed.site.elections[1:]
        else:
            assert json.loads(result.stdout)["requests_release"] is True
    else:
        assert result.exit_code == 1, result.output
        assert (repository / SITE).read_bytes() == before
