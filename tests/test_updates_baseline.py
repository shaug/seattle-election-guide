"""Only a successful, still-served production artifact can supply the baseline."""

from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Literal

import pytest

from election_guide.hosting import updates_baseline
from election_guide.hosting.production_check import Observation
from election_guide.hosting.updates import UPDATES_SNAPSHOT, build_updates_snapshot
from election_guide.serialization import canonical_json_bytes
from tests.test_updates_gate import _page, _seal, _write  # pyright: ignore[reportPrivateUsage]
from tests.test_updates_gate import sites as sites


@pytest.fixture
def production(sites: tuple[Path, Path], monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    published = sites[0]
    state: dict[str, Any] = {
        "deployments": [{"id": 9, "sha": "a" * 40}],
        "statuses": [{"state": "success"}],
        "runs": {
            "workflow_runs": [
                {
                    "id": 7,
                    "path": ".github/workflows/ci.yml",
                    "conclusion": "success",
                    "event": "push",
                    "head_sha": "a" * 40,
                }
            ]
        },
        "artifacts": {"artifacts": [{"name": "cloudflare-site", "expired": False}]},
        "live": (published / "deployment-manifest.json").read_bytes(),
        "download": True,
        "calls": [],
        "managed": None,
    }

    def gh(args: list[str], failure: str) -> str:
        state["calls"].append(args)
        if args[1:3] == ["run", "download"]:
            if state["download"]:
                shutil.copytree(published, Path(args[args.index("--dir") + 1]))
            if not state["download"]:
                raise ValueError("missing artifact")
            return ""
        endpoint = args[2]
        if "/deployments?" in endpoint:
            data = state["deployments"]
        elif endpoint.endswith("/statuses"):
            data = state["statuses"]
        elif "/actions/runs?" in endpoint:
            data = state["runs"]
        elif endpoint.endswith("/artifacts"):
            data = state["artifacts"]
        else:
            raise AssertionError(endpoint)
        return json.dumps(data)

    def fetch_manifest(base_url: str, *, timeout: float) -> tuple[Observation, bytes]:
        return Observation(status=200), state["live"]

    def latest(repository: str) -> Any:
        return state["managed"]

    monkeypatch.setattr(updates_baseline, "run_gh", gh)
    monkeypatch.setattr(updates_baseline, "fetch_manifest_body", fetch_manifest)
    monkeypatch.setattr(updates_baseline, "latest_production_receipt", latest, raising=False)
    return state


def test_resolves_exact_successful_production_artifact(
    tmp_path: Path, production: dict[str, Any]
) -> None:
    destination = tmp_path / "download"

    receipt = updates_baseline.resolve_production_baseline(destination)

    assert receipt["deployment_id"] == 9
    assert receipt["git_commit"] == "a" * 40
    assert receipt["ci_run_id"] == 7
    assert (destination / "deployment-manifest.json").is_file()
    download = next(c for c in production["calls"] if c[1:3] == ["run", "download"])
    assert download[3] == "7"


@pytest.mark.parametrize(
    "change, message",
    [
        ({"deployments": []}, "successful production"),
        ({"statuses": [{"state": "failure"}]}, "successful production"),
        ({"artifacts": {"artifacts": [{"name": "cloudflare-site", "expired": True}]}}, "artifact"),
        ({"runs": {"workflow_runs": []}}, "artifact"),
        ({"download": False}, "missing"),
        ({"live": b"{}"}, "manifest"),
    ],
)
def test_missing_or_invalid_baseline_evidence_fails_closed(
    tmp_path: Path, production: dict[str, Any], change: dict[str, Any], message: str
) -> None:
    production.update(change)

    with pytest.raises(ValueError, match=message):
        updates_baseline.resolve_production_baseline(tmp_path / "download")


def test_live_revision_must_match_successful_deployment(
    tmp_path: Path, production: dict[str, Any]
) -> None:
    production["deployments"][0]["sha"] = "d" * 40

    with pytest.raises(ValueError, match=r"served|revision"):
        updates_baseline.resolve_production_baseline(tmp_path / "download")


def test_artifact_manifest_must_match_production(
    tmp_path: Path, production: dict[str, Any]
) -> None:
    live = json.loads(production["live"])
    live["assets"]["e/wa-2026-general/index.html"] = "f" * 64
    production["live"] = json.dumps(live).encode()

    with pytest.raises(ValueError, match="manifest"):
        updates_baseline.resolve_production_baseline(tmp_path / "download")


def test_successful_noop_job_cannot_replace_the_served_baseline(
    tmp_path: Path, production: dict[str, Any]
) -> None:
    production["deployments"].insert(0, {"id": 10, "sha": "d" * 40})

    receipt = updates_baseline.resolve_production_baseline(tmp_path / "download")

    assert receipt["deployment_id"] == 9


def test_managed_upload_uses_its_verified_promotion_artifact(
    tmp_path: Path,
    sites: tuple[Path, Path],
    production: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    artifact = SimpleNamespace(producer=SimpleNamespace(run_id=25))
    production["managed"] = SimpleNamespace(
        upload=SimpleNamespace(github_deployment_id=20, source_sha="a" * 40),
        publication=SimpleNamespace(
            published=SimpleNamespace(
                promotion_manifest_sha256=hashlib.sha256(production["live"]).hexdigest()
            ),
            promotion_artifact=artifact,
        ),
    )
    production["runs"] = {"workflow_runs": []}

    def download(reference: Any, destination: Path) -> None:
        assert reference is artifact
        shutil.copytree(sites[0], destination)

    monkeypatch.setattr(updates_baseline, "download_actions_artifact", download, raising=False)

    receipt = updates_baseline.resolve_production_baseline(tmp_path / "download")

    assert receipt["deployment_id"] == 20
    assert receipt["ci_run_id"] == 25


def test_newer_verified_upload_with_stale_served_revision_blocks_the_gate(
    tmp_path: Path, production: dict[str, Any]
) -> None:
    production["managed"] = SimpleNamespace(
        upload=SimpleNamespace(github_deployment_id=20, source_sha="d" * 40)
    )

    with pytest.raises(ValueError, match=r"served.*revision"):
        updates_baseline.resolve_production_baseline(tmp_path / "download")


@pytest.mark.parametrize("corrupt", [False, True])
def test_durable_snapshot_is_authenticated_without_expiring_artifacts(
    tmp_path: Path,
    sites: tuple[Path, Path],
    production: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
    corrupt: bool,
) -> None:
    snapshot = build_updates_snapshot(sites[0])
    payload = canonical_json_bytes(snapshot.model_dump(mode="json"))
    manifest = json.loads(production["live"])
    manifest["assets"][UPDATES_SNAPSHOT] = hashlib.sha256(payload).hexdigest()
    production["live"] = canonical_json_bytes(manifest)
    production["runs"] = {"workflow_runs": []}
    production["managed"] = SimpleNamespace(
        upload=SimpleNamespace(github_deployment_id=20, source_sha="a" * 40),
        publication=SimpleNamespace(
            published=SimpleNamespace(
                promotion_manifest_sha256=hashlib.sha256(production["live"]).hexdigest()
            ),
            promotion_artifact=SimpleNamespace(producer=SimpleNamespace(run_id=25)),
        ),
    )

    def fetch_asset(base_url: str, path: str, *, timeout: float) -> tuple[Observation, bytes]:
        return Observation(status=200), payload + (b"changed" if corrupt else b"")

    monkeypatch.setattr(updates_baseline, "fetch_asset_body", fetch_asset)

    if corrupt:
        with pytest.raises(ValueError, match="hash"):
            updates_baseline.resolve_production_snapshot(tmp_path / "download")
    else:
        resolved, receipt = updates_baseline.resolve_production_snapshot(tmp_path / "download")
        assert resolved == snapshot
        assert receipt["deployment_id"] == 20
        assert receipt["manifest_sha256"] == hashlib.sha256(production["live"]).hexdigest()
        assert not any(c[1:3] == ["run", "download"] for c in production["calls"])


def test_durable_snapshot_rejects_a_different_manifest_at_the_verified_source(
    tmp_path: Path,
    sites: tuple[Path, Path],
    production: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    snapshot = build_updates_snapshot(sites[0])
    manifest = json.loads(production["live"])
    manifest["assets"][UPDATES_SNAPSHOT] = hashlib.sha256(
        canonical_json_bytes(snapshot.model_dump(mode="json"))
    ).hexdigest()
    verified_manifest = canonical_json_bytes(manifest)
    production["managed"] = SimpleNamespace(
        upload=SimpleNamespace(github_deployment_id=20, source_sha="a" * 40),
        publication=SimpleNamespace(
            published=SimpleNamespace(
                promotion_manifest_sha256=hashlib.sha256(verified_manifest).hexdigest()
            ),
            promotion_artifact=SimpleNamespace(producer=SimpleNamespace(run_id=25)),
        ),
    )
    # A self-consistent replacement snapshot must not become the baseline merely
    # because its manifest still names the verified upload's source revision.
    election = next(iter(snapshot.elections.values()))
    election.pages = dict.fromkeys(election.pages, "0" * 64)
    payload = canonical_json_bytes(snapshot.model_dump(mode="json"))
    manifest["assets"][UPDATES_SNAPSHOT] = hashlib.sha256(payload).hexdigest()
    production["live"] = canonical_json_bytes(manifest)

    def fetch_asset(base_url: str, path: str, *, timeout: float) -> tuple[Observation, bytes]:
        return Observation(status=200), payload

    monkeypatch.setattr(updates_baseline, "fetch_asset_body", fetch_asset)

    with pytest.raises(ValueError, match=r"manifest.*verified upload"):
        updates_baseline.resolve_production_snapshot(tmp_path / "download")


@pytest.mark.parametrize("old_policy", ["1.0", "2.0", "3.0", "4.0"])
@pytest.mark.parametrize("available, changed_source", [(False, False), (True, False), (True, True)])
def test_old_policy_upgrade_requires_the_exact_verified_original_site(
    tmp_path: Path,
    sites: tuple[Path, Path],
    production: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
    available: bool,
    changed_source: bool,
    old_policy: Literal["1.0", "2.0", "3.0", "4.0"],
) -> None:
    original = (
        "https://github.com/shaug/seattle-election-guide/blob/"
        + "a" * 40
        + "/data/evidence/official/sha256/ff/"
        + "f" * 64
    )
    _write(
        sites[0],
        "e/wa-2026-general/index.html",
        _page(
            f'<div class="race-results"><a href="{original}">Evidence</a> A 10 '
            '<span data-preliminary-recency="race-1">'
            "Last checked Nov 7, 5:22:18 a.m. PST</span></div>"
        ),
    )
    _seal(sites[0])
    snapshot = build_updates_snapshot(sites[0], schema_version=old_policy).model_dump(mode="json")
    if old_policy == "1.0":
        for election in snapshot["elections"].values():
            election.pop("information_pages")
    payload = canonical_json_bytes(snapshot)
    (sites[0] / UPDATES_SNAPSHOT).write_bytes(payload)
    _seal(sites[0])
    production["live"] = (sites[0] / "deployment-manifest.json").read_bytes()
    production["download"] = available

    def fetch_asset(base_url: str, path: str, *, timeout: float) -> tuple[Observation, bytes]:
        return Observation(status=200), payload

    monkeypatch.setattr(updates_baseline, "fetch_asset_body", fetch_asset)
    if changed_source:
        resolve = updates_baseline.resolve_production_baseline

        def changed_receipt(destination: Path) -> dict[str, Any]:
            receipt = resolve(destination)
            receipt["git_commit"] = "d" * 40
            return receipt

        monkeypatch.setattr(updates_baseline, "resolve_production_baseline", changed_receipt)
    if not available:
        with pytest.raises(ValueError, match="missing"):
            updates_baseline.resolve_production_snapshot(tmp_path / "download")
    elif changed_source:
        with pytest.raises(ValueError, match="changed during"):
            updates_baseline.resolve_production_snapshot(tmp_path / "download")
    else:
        resolved, receipt = updates_baseline.resolve_production_snapshot(tmp_path / "download")
        assert resolved.schema_version == "5.0"
        assert receipt["policy_upgrade_from"] == old_policy
        assert receipt["git_commit"] == "a" * 40
        assert resolved == build_updates_snapshot(sites[0])
        if old_policy in {"2.0", "3.0"}:
            assert (
                resolved.elections["wa-2026-general"].information_pages
                != snapshot["elections"]["wa-2026-general"]["information_pages"]
            )
