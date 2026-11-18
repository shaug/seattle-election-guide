"""Execute the preview teardown with fixture-backed Cloudflare and Wrangler commands."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import pytest
import yaml

PROJECT_ROOT = Path(__file__).parents[1]


def _deployment(identifier: str, branch: str, environment: str = "preview") -> dict[str, Any]:
    return {
        "id": identifier,
        "environment": environment,
        "deployment_trigger": {"metadata": {"branch": branch}},
    }


def _page(deployments: list[dict[str, Any]]) -> dict[str, Any]:
    return {"success": True, "errors": [], "messages": [], "result": deployments}


def _run_teardown(
    tmp_path: Path,
    pages: Sequence[object],
    *,
    failed_page: int = 0,
    delete_fails: bool = False,
    reject_page_size: bool = False,
) -> tuple[subprocess.CompletedProcess[str], list[dict[str, Any]]]:
    workflow = yaml.load(
        (PROJECT_ROOT / ".github/workflows/deploy-pr-preview.yml").read_text(encoding="utf-8"),
        Loader=yaml.BaseLoader,
    )
    command = next(
        step["run"]
        for step in workflow["jobs"]["teardown"]["steps"]
        if step.get("name") == "Delete this pull request's preview deployments"
    )
    fixtures = tmp_path / "pages.json"
    fixtures.write_text(json.dumps(pages), encoding="utf-8")
    calls = tmp_path / "calls.jsonl"
    commands = tmp_path / "bin"
    commands.mkdir()
    # Replace only the network and destructive boundaries. The workflow's Bash
    # and jq run unchanged, and deletion records are the observable side effect.
    stub = (
        f"#!{sys.executable}\n"
        + """
import json, os, pathlib, sys
args = sys.argv[1:]
pages = json.loads(pathlib.Path(os.environ["FIXTURES"]).read_text())
def record(**entry):
    with open(os.environ["CALLS"], "a") as stream:
        stream.write(json.dumps(entry) + "\\n")
if pathlib.Path(sys.argv[0]).name == "curl":
    query = [args[i + 1] for i, arg in enumerate(args) if arg == "--data-urlencode"]
    assert "env=preview" in query
    assert "Authorization: Bearer fixture-token" in args
    assert ("https://api.cloudflare.com/client/v4/accounts/fixture-account/"
            "pages/projects/seattle-elections/deployments") in args
    page = int(next(value.split("=")[1] for value in query if value.startswith("page=")))
    record(action="list", page=page)
    if os.environ["REJECT_PAGE_SIZE"] == "true" and any(
        value.startswith("per_page=") for value in query
    ):
        print("curl: (22) The requested URL returned error: 400", file=sys.stderr)
        sys.exit(22)
    if page == int(os.environ["FAILED_PAGE"]):
        sys.exit(22)
    payload = pages[page - 1]
    text = payload if isinstance(payload, str) else json.dumps(payload)
    pathlib.Path(args[args.index("--output") + 1]).write_text(text)
elif args[:4] == ["wrangler", "pages", "deployment", "list"]:
    # The old workflow lists only page one, in Wrangler's projected shape.
    print(json.dumps([{"Id": row["id"], "Branch": row["deployment_trigger"]["metadata"]["branch"]}
                      for row in pages[0]["result"]]))
elif args[:4] == ["wrangler", "pages", "deployment", "delete"]:
    assert args[5:] == ["--project-name", "seattle-elections", "--force"]
    record(action="delete", id=args[4])
    if os.environ["DELETE_FAILS"] == "true":
        sys.exit(1)
else:
    raise AssertionError(args)
"""
    )
    for name in ("curl", "npx"):
        path = commands / name
        path.write_text(stub, encoding="utf-8")
        path.chmod(0o755)
    result = subprocess.run(
        ["bash", "--noprofile", "--norc", "-e", "-o", "pipefail", "-c", command],
        cwd=tmp_path,
        env={
            **os.environ,
            "PATH": f"{commands}{os.pathsep}{os.environ['PATH']}",
            "FIXTURES": str(fixtures),
            "CALLS": str(calls),
            "FAILED_PAGE": str(failed_page),
            "DELETE_FAILS": str(delete_fails).lower(),
            "REJECT_PAGE_SIZE": str(reject_page_size).lower(),
            "CLOUDFLARE_ACCOUNT_ID": "fixture-account",
            "CLOUDFLARE_API_TOKEN": "fixture-token",
            "PREVIEW_BRANCH": "pr-269",
        },
        capture_output=True,
        text=True,
        timeout=15,
        check=False,
    )
    observed = (
        [json.loads(line) for line in calls.read_text(encoding="utf-8").splitlines()]
        if calls.exists()
        else []
    )
    return result, observed


def test_teardown_finds_all_matches_after_a_full_page_without_matches(tmp_path: Path) -> None:
    pages = [
        _page([_deployment(f"other-{index}", "pr-270") for index in range(100)]),
        _page([_deployment(f"target-{index}", "pr-269") for index in range(100)]),
        _page(
            [
                _deployment("oldest", "pr-269"),
                _deployment("production", "pr-269", "production"),
                _deployment("other-branch", "pr-2690"),
            ]
        ),
        _page([]),
    ]
    result, calls = _run_teardown(tmp_path, pages)

    assert result.returncode == 0, result.stderr
    assert calls == [
        {"action": "list", "page": 1},
        {"action": "list", "page": 2},
        {"action": "list", "page": 3},
        {"action": "list", "page": 4},
        *[{"action": "delete", "id": f"target-{index}"} for index in range(100)],
        {"action": "delete", "id": "oldest"},
    ]


@pytest.mark.parametrize("full_page", [False, True])
def test_teardown_no_matches_is_success_only_after_enumeration(
    tmp_path: Path, full_page: bool
) -> None:
    pages = [_page([_deployment(f"other-{i}", "pr-270") for i in range(100)])] if full_page else []
    pages.append(_page([]))
    result, calls = _run_teardown(tmp_path, pages)

    assert result.returncode == 0, result.stderr
    assert "No preview deployments found for pr-269." in result.stdout
    assert calls == [{"action": "list", "page": i + 1} for i in range(len(pages))]


@pytest.mark.parametrize(
    "bad_page",
    [
        {"success": False, "errors": [{"code": 10000, "message": "Authentication error"}]},
        {"success": True},
        {"success": True, "result": {}},
        _page([{"id": "missing-branch", "environment": "preview"}]),
        _page([{"Id": "projection", "Branch": "pr-269"}]),
        _page([_deployment("", "pr-269")]),
        "invalid JSON",
    ],
)
def test_teardown_rejects_failed_or_malformed_enumeration(tmp_path: Path, bad_page: object) -> None:
    first_page = _page([_deployment(f"target-{i}", "pr-269") for i in range(100)])
    result, calls = _run_teardown(tmp_path, [first_page, bad_page])

    assert result.returncode != 0
    assert "No preview deployments found" not in result.stdout
    assert calls == [{"action": "list", "page": 1}, {"action": "list", "page": 2}]


def test_teardown_fails_when_a_later_http_request_fails(tmp_path: Path) -> None:
    first_page = _page([_deployment(f"target-{i}", "pr-269") for i in range(100)])
    result, calls = _run_teardown(tmp_path, [first_page], failed_page=2)

    assert result.returncode != 0
    assert calls == [{"action": "list", "page": 1}, {"action": "list", "page": 2}]


def test_teardown_propagates_deletion_failure(tmp_path: Path) -> None:
    result, calls = _run_teardown(
        tmp_path, [_page([_deployment("target", "pr-269")]), _page([])], delete_fails=True
    )

    assert result.returncode != 0
    assert calls == [
        {"action": "list", "page": 1},
        {"action": "list", "page": 2},
        {"action": "delete", "id": "target"},
    ]


def test_teardown_enumerates_server_sized_pages_until_empty(tmp_path: Path) -> None:
    # Cloudflare's SDK advances until an empty page; a short nonempty page is
    # not evidence that every deployment has been enumerated.
    pages = [
        _page([_deployment("other-first-page", "pr-270")]),
        _page([_deployment("target-later-page", "pr-269")]),
        _page(
            [
                _deployment("target-oldest", "pr-269"),
                _deployment("production", "pr-269", "production"),
                _deployment("branch-prefix", "pr-2690"),
            ]
        ),
        _page([]),
    ]
    result, calls = _run_teardown(tmp_path, pages)

    assert result.returncode == 0, result.stderr
    assert calls == [
        {"action": "list", "page": 1},
        {"action": "list", "page": 2},
        {"action": "list", "page": 3},
        {"action": "list", "page": 4},
        {"action": "delete", "id": "target-later-page"},
        {"action": "delete", "id": "target-oldest"},
    ]


def test_teardown_works_when_server_rejects_a_page_size_override(tmp_path: Path) -> None:
    result, calls = _run_teardown(
        tmp_path,
        [_page([_deployment("target", "pr-269")]), _page([])],
        reject_page_size=True,
    )

    assert result.returncode == 0, result.stderr
    assert calls == [
        {"action": "list", "page": 1},
        {"action": "list", "page": 2},
        {"action": "delete", "id": "target"},
    ]


def _pr_state(
    *, state: str = "open", labels: tuple[str, ...] = ("deploy preview",), sha: str = "a" * 40
) -> dict[str, Any]:
    return {
        "number": 269,
        "state": state,
        "head": {"sha": sha, "repo": {"full_name": "shaug/seattle-election-guide"}},
        "base": {"repo": {"full_name": "shaug/seattle-election-guide"}},
        "labels": [{"name": label} for label in labels],
    }


def _read_preview_state(
    tmp_path: Path, payload: object, *, expected_head: str = "", api_fails: bool = False
) -> tuple[subprocess.CompletedProcess[str], dict[str, str]]:
    workflow = yaml.load(
        (PROJECT_ROOT / ".github/workflows/deploy-pr-preview.yml").read_text(encoding="utf-8"),
        Loader=yaml.BaseLoader,
    )
    step = next(
        (step for step in workflow["jobs"]["admission"]["steps"] if step.get("id") == "admit"),
        None,
    )
    assert step is not None, "preview must read current PR state before any deployment"
    commands = tmp_path / "state-bin"
    commands.mkdir()
    fixture = tmp_path / "pr.json"
    fixture.write_text(json.dumps(payload), encoding="utf-8")
    gh = commands / "gh"
    gh.write_text(
        f"#!{sys.executable}\n"
        "import os, pathlib, sys\n"
        'assert sys.argv[1:] == ["api", "--method", "GET", '
        '"repos/shaug/seattle-election-guide/pulls/269"]\n'
        'if os.environ["API_FAILS"] == "true": sys.exit(1)\n'
        'print(pathlib.Path(os.environ["PR_FIXTURE"]).read_text())\n',
        encoding="utf-8",
    )
    gh.chmod(0o755)
    output = tmp_path / "outputs"
    result = subprocess.run(
        ["bash", "--noprofile", "--norc", "-e", "-o", "pipefail", "-c", step["run"]],
        cwd=tmp_path,
        env={
            **os.environ,
            "PATH": f"{commands}{os.pathsep}{os.environ['PATH']}",
            "PR_FIXTURE": str(fixture),
            "API_FAILS": str(api_fails).lower(),
            "GITHUB_OUTPUT": str(output),
            "GITHUB_REPOSITORY": "shaug/seattle-election-guide",
            "PR_NUMBER": "269",
            "EXPECTED_HEAD": expected_head,
        },
        capture_output=True,
        text=True,
        timeout=15,
        check=False,
    )
    outputs = (
        dict(line.split("=", 1) for line in output.read_text().splitlines())
        if (output.exists())
        else {}
    )
    return result, outputs


@pytest.mark.parametrize(
    "state,labels,deploy,cleanup",
    [
        ("open", (), "false", "true"),
        ("open", ("unrelated",), "false", "true"),
        ("open", ("deploy preview",), "true", "false"),
        ("open", ("deploy preview", "unrelated"), "true", "false"),
        ("closed", (), "false", "true"),
        ("closed", ("deploy preview",), "false", "true"),
    ],
)
def test_preview_current_state_controls_deployment_and_cleanup(
    tmp_path: Path, state: str, labels: tuple[str, ...], deploy: str, cleanup: str
) -> None:
    result, outputs = _read_preview_state(tmp_path, _pr_state(state=state, labels=labels))
    assert result.returncode == 0, result.stderr
    assert outputs == {"head_sha": "a" * 40, "deploy": deploy, "cleanup": cleanup}


def test_preview_label_readded_before_cleanup_keeps_the_current_preview(tmp_path: Path) -> None:
    # A delayed unlabeled event may observe an already re-added label. The fresh
    # policy must protect the preview, independent of that old event's contents.
    result, outputs = _read_preview_state(tmp_path, _pr_state())
    assert result.returncode == 0, result.stderr
    assert outputs["cleanup"] == "false"


def test_preview_removed_during_build_is_deleted_without_touching_production(
    tmp_path: Path,
) -> None:
    state_dir = tmp_path / "state"
    state_dir.mkdir()
    result, outputs = _read_preview_state(state_dir, _pr_state(labels=()), expected_head="a" * 40)
    assert result.returncode == 0, result.stderr
    assert outputs["deploy"] == "false"
    assert outputs["cleanup"] == "true"
    result, calls = _run_teardown(
        tmp_path,
        [
            _page(
                [
                    _deployment("ours", "pr-269"),
                    _deployment("other", "pr-270"),
                    _deployment("prod", "main", "production"),
                ]
            ),
            _page([]),
        ],
    )
    assert result.returncode == 0, result.stderr
    assert [call for call in calls if call["action"] == "delete"] == [
        {"action": "delete", "id": "ours"}
    ]


def test_preview_changed_head_cannot_upload_stale_build(tmp_path: Path) -> None:
    result, outputs = _read_preview_state(tmp_path, _pr_state(sha="b" * 40), expected_head="a" * 40)
    assert result.returncode == 0, result.stderr
    assert outputs == {"head_sha": "b" * 40, "deploy": "false", "cleanup": "false"}


@pytest.mark.parametrize("change", ["number", "repo", "sha", "labels", "state"])
def test_preview_rejects_invalid_or_wrong_pr_identity(tmp_path: Path, change: str) -> None:
    data = _pr_state()
    if change == "number":
        data["number"] = 270
    elif change == "repo":
        data["head"]["repo"]["full_name"] = "other/fork"
    elif change == "sha":
        data["head"]["sha"] = "not-a-sha"
    elif change == "labels":
        data["labels"] = None
    else:
        data["state"] = "unknown"
    result, outputs = _read_preview_state(tmp_path, data)
    assert result.returncode != 0
    assert outputs == {}


def test_preview_failed_read_does_not_authorize_either_mutation(tmp_path: Path) -> None:
    result, outputs = _read_preview_state(tmp_path, _pr_state(), api_fails=True)
    assert result.returncode != 0
    assert outputs == {}


def test_preview_lifecycle_serializes_reconciliation_and_rechecks_before_upload() -> None:
    workflow = yaml.load(
        (PROJECT_ROOT / ".github/workflows/deploy-pr-preview.yml").read_text(encoding="utf-8"),
        Loader=yaml.BaseLoader,
    )
    assert "unlabeled" in workflow["on"]["pull_request"]["types"]
    assert workflow["concurrency"] == {
        "group": "pages-preview-pr-${{ github.event.pull_request.number }}",
        "cancel-in-progress": "false",
    }
    deploy = workflow["jobs"]["deploy"]
    teardown = workflow["jobs"]["teardown"]
    assert "concurrency" not in deploy and "concurrency" not in teardown
    assert teardown["needs"] == ["admission", "deploy"]
    assert "always()" in teardown["if"]
    assert "github.event.action == 'closed'" not in teardown["if"]
    steps = deploy["steps"]
    upload = next(step for step in steps if step.get("id") == "deploy")
    recheck = next(step for step in steps if step.get("id") == "recheck")
    admit = workflow["jobs"]["admission"]["steps"][0]
    cleanup = next(step for step in teardown["steps"] if step.get("id") == "current")
    assert admit["run"] == recheck["run"] == cleanup["run"]
    assert admit["id"] == "admit"
    assert steps.index(recheck) + 1 == steps.index(upload)
    assert recheck["env"]["EXPECTED_HEAD"] == "${{ needs.admission.outputs.head_sha }}"
    assert upload["if"] == "steps.recheck.outputs.deploy == 'true'"
    for step in teardown["steps"][1:]:
        assert step["if"] == "steps.current.outputs.cleanup == 'true'"


def test_preview_opt_out_does_not_create_a_github_deployment_environment() -> None:
    workflow = yaml.load(
        (PROJECT_ROOT / ".github/workflows/deploy-pr-preview.yml").read_text(encoding="utf-8"),
        Loader=yaml.BaseLoader,
    )
    admission = workflow["jobs"].get("admission")
    assert admission is not None, "live admission must precede the environment-bearing job"
    assert "environment" not in admission
    assert all("uses" not in step for step in admission["steps"])
    assert workflow["jobs"]["deploy"]["needs"] == "admission"
    assert "needs.admission.outputs.deploy == 'true'" in workflow["jobs"]["deploy"]["if"]
