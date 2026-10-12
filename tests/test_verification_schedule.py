"""Public scheduling results use the declared ballot dates and explicit coverage."""

import json
from pathlib import Path
from typing import Any, cast

import yaml
from typer.testing import CliRunner

from election_guide.cli import app

ROOT = Path(__file__).parents[1]
runner = CliRunner()


def _policy(tmp_path: Path, **changes: object) -> Path:
    election: dict[str, object] = {
        "election_id": "wa-2026-general",
        "registry": str(ROOT / "config/sources/wa-2026-general.yaml"),
        "inventory": str(ROOT / "data/normalized/wa-2026-general-inventory.json"),
        "sources": [],
    }
    election.update(changes)
    path = tmp_path / "policy.yaml"
    path.write_text(
        yaml.safe_dump(
            {
                "schema_version": "1.0",
                "calendar": str(ROOT / "config/calendar/elections.yaml"),
                "elections": [election],
            }
        )
    )
    return path


def _plan(policy: Path, state: Path, as_of: str) -> dict[str, Any]:
    result = runner.invoke(
        app, ["verification", "plan", str(policy), "--state-root", str(state), "--as-of", as_of]
    )
    assert result.exit_code == 0, result.output
    return cast(dict[str, Any], json.loads(result.output))


def test_weekly_and_daily_responsibility_follow_regular_issuance_not_domestic_mail(
    tmp_path: Path,
) -> None:
    policy = _policy(tmp_path)
    early = _plan(policy, tmp_path / "state", "2026-09-10")
    assert early["elections"][0]["cadence"] == "weekly"
    daily = _plan(policy, tmp_path / "state", "2026-09-18")
    assert daily["elections"][0]["cadence"] == "daily"
    current = _plan(policy, tmp_path / "state", "2026-10-05")
    sources = current["elections"][0]["coverage"]
    assert {s["lane"] for s in sources} == {"manual"}
    assert all(s["next_due"] == "2026-10-05" for s in sources)
    assert all(s["last_successful_check"] is None for s in sources)
    assert _plan(policy, tmp_path / "state", "2026-11-04")["elections"] == []
    assert _plan(policy, tmp_path / "state", "2026-09-07")["elections"] == []


def test_current_start_creates_current_obligations_without_historical_backlog(
    tmp_path: Path,
) -> None:
    policy = _policy(tmp_path)
    report = _plan(policy, tmp_path / "state", "2026-10-05")
    assert report["missed"] == []
    assert not (tmp_path / "state").exists()


def test_source_daily_override_and_unknown_source_are_validated(tmp_path: Path) -> None:
    policy = _policy(
        tmp_path,
        sources=[
            {
                "source_id": "seattle-gay-news",
                "daily_from_collection": True,
                "limitation": "Manual publication review pending adapter installation.",
            }
        ],
    )
    report = _plan(policy, tmp_path / "state", "2026-09-10")
    sources = report["elections"][0]["coverage"]
    assert next(s for s in sources if s["source_id"] == "seattle-gay-news")["cadence"] == "daily"
    policy = _policy(tmp_path, sources=[{"source_id": "invented-publisher"}])
    result = runner.invoke(app, ["verification", "plan", str(policy), "--as-of", "2026-10-05"])
    assert result.exit_code != 0
    assert "unknown source" in result.output


def test_policy_cannot_override_the_calendar_with_a_second_hard_coded_date(tmp_path: Path) -> None:
    policy = _policy(tmp_path, election_day="2026-11-04")
    result = runner.invoke(app, ["verification", "plan", str(policy), "--as-of", "2026-10-05"])
    assert result.exit_code != 0
    assert "election_day" in result.output
