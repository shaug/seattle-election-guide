"""Scheduling cannot bypass source holds or protected publication."""

from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).parents[1]


def test_preliminary_schedule_is_opt_in_and_serialized() -> None:
    path = ROOT / ".github/workflows/preliminary-results.yml"
    assert path.exists(), "the autonomous preparation schedule is missing"
    workflow = yaml.safe_load(path.read_text())
    assert workflow["permissions"] == {"contents": "read", "actions": "read"}
    assert workflow["concurrency"]["cancel-in-progress"] is False
    job = workflow["jobs"]["prepare"]
    assert "PRELIMINARY_RESULTS_REFRESH_ENABLED" in job["if"]
    assert "== 'true'" in job["if"]
    triggers = workflow.get("on", workflow.get(True))
    assert triggers["schedule"] == [{"cron": "17 * * * *"}]


def test_preliminary_job_persists_intent_and_uses_only_scoped_app_writes() -> None:
    path = ROOT / ".github/workflows/preliminary-results.yml"
    assert path.exists(), "the autonomous preparation schedule is missing"
    workflow = yaml.safe_load(path.read_text())
    steps = workflow["jobs"]["prepare"]["steps"]
    intent = next(i for i, step in enumerate(steps) if step.get("id") == "intent")
    capture = next(i for i, step in enumerate(steps) if step.get("id") == "refresh")
    assert intent < capture
    assert steps[intent]["uses"] == "actions/upload-artifact@v4"
    assert steps[intent]["with"]["if-no-files-found"] == "error"
    assert "prepare-refresh" in steps[capture]["run"] and "--live" in steps[capture]["run"]
    body = path.read_text()
    app = next((step for step in steps if step.get("id") == "app-token"), None)
    assert app is not None, "the approved hourly publication capability is missing"
    assert app["uses"] == "actions/create-github-app-token@v3"
    assert app["with"]["permission-contents"] == "write"
    assert app["with"]["permission-pull-requests"] == "write"
    assert "permission-workflows" not in app["with"]
    assert "gh pr create" in body and "--draft" in body
    assert "gh pr merge" not in body and "--admin" not in body
    assert "CACHE_HIT" in body and "recover that run" in body
    assert "rerun" not in body and "--force" not in body


def test_missing_prior_completion_state_stops_before_source_work(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    workflow = yaml.safe_load((ROOT / ".github/workflows/preliminary-results.yml").read_text())
    step = next(
        s
        for s in workflow["jobs"]["prepare"]["steps"]
        if s.get("name") == "Validate state before any publisher request"
    )
    code = step["run"].split("<<'PY'\n", 1)[1].rsplit("\nPY", 1)[0]
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("PRIOR_RUN", "42")
    monkeypatch.setenv("CACHE_HIT", "false")
    with pytest.raises(SystemExit, match="Prior outcome/state unavailable"):
        exec(compile(code, "preliminary-state-guard", "exec"), {})
    assert not (tmp_path / "data").exists()


def test_every_embedded_workflow_python_program_compiles() -> None:
    workflow = yaml.safe_load((ROOT / ".github/workflows/preliminary-results.yml").read_text())
    for step in workflow["jobs"]["prepare"]["steps"]:
        run = step.get("run", "")
        if "<<'PY'\n" in run:
            code = run.split("<<'PY'\n", 1)[1].rsplit("\nPY", 1)[0]
            compile(code, step["name"], "exec")


def test_pending_candidate_suppresses_source_work_and_normal_gates_precede_push() -> None:
    workflow = yaml.safe_load((ROOT / ".github/workflows/preliminary-results.yml").read_text())
    steps = workflow["jobs"]["prepare"]["steps"]
    ids = {s.get("id"): i for i, s in enumerate(steps) if s.get("id")}
    assert "candidate" in ids, "existing candidate recovery is missing"
    assert ids["candidate"] < ids["intent"] < ids["refresh"]
    assert "pending" in steps[ids["refresh"]].get("if", "")
    check = next((i for i, s in enumerate(steps) if s.get("run", "").strip() == "make check"), None)
    push = next((i for i, s in enumerate(steps) if "git push" in s.get("run", "")), None)
    assert check is not None and push is not None and check < push
    assert "stage_preliminary_publication" in steps[push]["run"]
    assert any("release automation prepare --issue 696" in s.get("run", "") for s in steps[:check])
