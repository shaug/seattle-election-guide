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
    tmp_path: Path, pages: Sequence[object], *, failed_page: int = 0, delete_fails: bool = False
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
    assert "env=preview" in query and "per_page=100" in query
    assert "Authorization: Bearer fixture-token" in args
    assert ("https://api.cloudflare.com/client/v4/accounts/fixture-account/"
            "pages/projects/seattle-elections/deployments") in args
    page = int(next(value.split("=")[1] for value in query if value.startswith("page=")))
    record(action="list", page=page)
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
    ]
    result, calls = _run_teardown(tmp_path, pages)

    assert result.returncode == 0, result.stderr
    assert calls == [
        {"action": "list", "page": 1},
        {"action": "list", "page": 2},
        {"action": "list", "page": 3},
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
        tmp_path, [_page([_deployment("target", "pr-269")])], delete_fails=True
    )

    assert result.returncode != 0
    assert calls == [{"action": "list", "page": 1}, {"action": "delete", "id": "target"}]
