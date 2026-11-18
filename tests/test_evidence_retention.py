import json
from pathlib import Path
from typing import Any

import pytest
from typer.testing import CliRunner

from election_guide.cli import app


def inventory() -> dict[str, Any]:
    return {
        "schema_version": "1",
        "elections": {"wa-2026-general": {"phase": "active", "closeout_receipts": []}},
        "artifacts": [
            {
                "id": "run-1-log",
                "path": "runs/run-1/output.jsonl",
                "kind": "operational",
                "elections": ["wa-2026-general"],
                "run_state": "completed",
                "owner": "run-1",
                "completion_receipt": "receipts/run-1.json",
                "active_consumers": [],
                "hold": None,
                "bytes": 1000,
            }
        ],
    }


def invoke(tmp_path: Path, data: dict[str, Any]):
    path = tmp_path / "inventory.json"
    path.write_text(json.dumps(data))
    return CliRunner().invoke(app, ["evidence", "retention-plan", str(path)])


def test_completed_operational_payload_is_candidate_not_deletion_authority(tmp_path: Path) -> None:
    result = invoke(tmp_path, inventory())
    assert result.exit_code == 0, result.stdout
    report = json.loads(result.stdout)
    assert report["deletion_authorized"] is False
    assert report["entries"][0]["disposition"] == "candidate"
    assert report["candidate_bytes"] == 1000
    assert sorted(p.name for p in tmp_path.iterdir()) == ["inventory.json"]


@pytest.mark.parametrize("kind", ["source", "published", "receipt", "checkpoint", "unknown"])
def test_protected_material_is_retained(tmp_path: Path, kind: str) -> None:
    data = inventory()
    data["artifacts"][0]["kind"] = kind
    result = invoke(tmp_path, data)
    assert result.exit_code == 0
    assert json.loads(result.stdout)["entries"][0]["disposition"] == "retain"


@pytest.mark.parametrize(
    "field,value",
    [
        ("owner", ""),
        ("completion_receipt", None),
        ("run_state", "active"),
        ("active_consumers", ["worker"]),
        ("hold", "investigation"),
    ],
)
def test_incomplete_or_live_operational_work_is_held(
    tmp_path: Path, field: str, value: object
) -> None:
    data = inventory()
    data["artifacts"][0][field] = value
    result = invoke(tmp_path, data)
    assert result.exit_code == 0
    assert json.loads(result.stdout)["entries"][0]["disposition"] == "retain"


def test_election_archive_requires_all_referencing_elections_closed(tmp_path: Path) -> None:
    data = inventory()
    data["artifacts"][0]["kind"] = "election-operational"
    assert json.loads(invoke(tmp_path, data).stdout)["entries"][0]["disposition"] == "retain"
    data["elections"]["wa-2026-general"] = {
        "phase": "closed",
        "closeout_receipts": [
            "certified-ingest",
            "accepted-release",
            "retrospective",
        ],
    }
    assert json.loads(invoke(tmp_path, data).stdout)["entries"][0]["disposition"] == "candidate"
    data["artifacts"][0]["elections"].append("wa-2027-primary")
    assert json.loads(invoke(tmp_path, data).stdout)["entries"][0]["disposition"] == "retain"


def test_closed_label_without_receipts_does_not_close_election(tmp_path: Path) -> None:
    data = inventory()
    data["elections"]["wa-2026-general"]["phase"] = "closed"
    data["artifacts"][0]["kind"] = "election-operational"
    assert json.loads(invoke(tmp_path, data).stdout)["entries"][0]["disposition"] == "retain"


@pytest.mark.parametrize("path", ["../data", "/data", "a/../data", ".git/objects", "data/source"])
def test_unsafe_or_authoritative_paths_are_rejected(tmp_path: Path, path: str) -> None:
    data = inventory()
    data["artifacts"][0]["path"] = path
    assert invoke(tmp_path, data).exit_code != 0


@pytest.mark.parametrize("field", ["id", "path"])
def test_duplicate_inventory_identity_is_rejected(tmp_path: Path, field: str) -> None:
    data = inventory()
    second = dict(data["artifacts"][0])
    second["id"] = "run-2-log"
    second["path"] = "runs/run-2/output.jsonl"
    second[field] = data["artifacts"][0][field]
    data["artifacts"].append(second)
    assert invoke(tmp_path, data).exit_code != 0


def test_typo_in_field_is_rejected_instead_of_silently_ignored(tmp_path: Path) -> None:
    data = inventory()
    data["artifacts"][0]["hold_reason"] = "still investigating"
    assert invoke(tmp_path, data).exit_code != 0


def test_overlapping_parent_cannot_hide_protected_child(tmp_path: Path) -> None:
    data = inventory()
    data["artifacts"][0]["path"] = "runs/run-1/directory"
    child = dict(data["artifacts"][0])
    child.update(id="source-child", path="runs/run-1/directory/source.pdf", kind="source")
    data["artifacts"].append(child)
    assert invoke(tmp_path, data).exit_code != 0


def test_known_active_election_holds_shared_archive(tmp_path: Path) -> None:
    data = inventory()
    data["artifacts"][0]["kind"] = "election-operational"
    data["elections"]["wa-2026-general"] = {
        "phase": "closed",
        "closeout_receipts": ["certified-ingest", "accepted-release", "retrospective"],
    }
    data["elections"]["wa-2027-primary"] = {"phase": "active", "closeout_receipts": []}
    data["artifacts"][0]["elections"].append("wa-2027-primary")
    result = invoke(tmp_path, data)
    assert result.exit_code == 0
    assert json.loads(result.stdout)["entries"][0]["disposition"] == "retain"


def test_contradictory_path_owner_cannot_become_a_removal_candidate(tmp_path: Path) -> None:
    data = inventory()
    data["artifacts"][0]["path"] = "runs/another-owner/output.jsonl"
    result = invoke(tmp_path, data)
    assert result.exit_code == 0, result.stdout
    report = json.loads(result.stdout)
    assert report["deletion_authorized"] is False
    assert report["candidate_bytes"] == 0
    assert report["entries"][0]["disposition"] == "retain"
