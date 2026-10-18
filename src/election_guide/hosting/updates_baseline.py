"""Resolve the exact successful production site used by the Updates gate."""

import hashlib
import json
from pathlib import Path
from typing import Any

from election_guide.github_cli import run_gh
from election_guide.hosting.models import DeploymentManifest
from election_guide.hosting.production_probe import fetch_asset_body, fetch_manifest_body
from election_guide.hosting.promotion import download_actions_artifact
from election_guide.hosting.updates import (
    UPDATES_SNAPSHOT,
    UpdatesSnapshot,
    build_updates_snapshot,
    read_verified_deployment,
)
from election_guide.release.evidence import latest_production_receipt

REPOSITORY = "shaug/seattle-election-guide"
PRODUCTION_ORIGIN = "https://seattleelections.guide"


def _gh(*arguments: str) -> str:
    return run_gh(["gh", *arguments], "cannot resolve production baseline")


def _api(endpoint: str) -> Any:
    return json.loads(_gh("api", f"repos/{REPOSITORY}/{endpoint}"))


def _served_manifest() -> tuple[DeploymentManifest, str]:
    observation, body = fetch_manifest_body(PRODUCTION_ORIGIN, timeout=20)
    if observation.status != 200 or body is None:
        raise ValueError(f"cannot read production manifest: {observation}")
    try:
        return DeploymentManifest.model_validate_json(body), hashlib.sha256(body).hexdigest()
    except ValueError as error:
        raise ValueError(f"invalid production manifest: {error}") from error


def _successful_deployment(served: DeploymentManifest) -> dict[str, Any]:
    # Deployment records, rather than the newest successful build or release
    # tag, identify what actually reached production. Never fall back to main.
    current = next(e for e in served.elections if e.election_id == served.current_election_id)
    managed = latest_production_receipt(REPOSITORY)
    if managed is not None:
        if managed.upload is None or managed.upload.source_sha != current.git_commit:
            raise ValueError("served production revision differs from last verified upload")
        return {
            "id": managed.upload.github_deployment_id,
            "sha": managed.upload.source_sha,
            "promotion_artifact": managed.publication.promotion_artifact,
        }
    # Legacy bootstrap: later successful no-op environment envelopes do not
    # identify an upload. Only the served revision's exact artifact can qualify.
    deployment = next(
        (
            row
            for row in _api("deployments?environment=production&per_page=100")
            if row["sha"] == current.git_commit
            and any(
                status["state"] == "success" for status in _api(f"deployments/{row['id']}/statuses")
            )
        ),
        None,
    )
    if deployment is None:
        raise ValueError("cannot find a successful production deployment for the served revision")
    return deployment


def resolve_production_baseline(destination: Path) -> dict[str, Any]:
    """Bootstrap from the legacy production artifact, before snapshots existed."""
    served, manifest_sha256 = _served_manifest()
    deployment = _successful_deployment(served)
    current = next(e for e in served.elections if e.election_id == served.current_election_id)
    if "promotion_artifact" in deployment:
        reference = deployment["promotion_artifact"]
        download_actions_artifact(reference, destination)
        run_id = reference.producer.run_id
    else:
        run_id = _download_legacy_site(current.git_commit, destination)
    downloaded = read_verified_deployment(destination)
    if downloaded != served:
        raise ValueError("baseline artifact manifest differs from served production manifest")
    if _served_manifest()[0] != served:
        raise ValueError("production manifest changed while resolving baseline; run the gate again")
    return {
        "repository": REPOSITORY,
        "deployment_id": deployment["id"],
        "git_commit": current.git_commit,
        "ci_run_id": run_id,
        "production_origin": PRODUCTION_ORIGIN,
        "manifest_sha256": manifest_sha256,
    }


def _download_legacy_site(git_commit: str, destination: Path) -> int:
    runs = _api(f"actions/runs?head_sha={git_commit}&per_page=100")["workflow_runs"]
    run_id = next(
        (
            row["id"]
            for row in runs
            if row["path"] == ".github/workflows/ci.yml"
            and row["head_sha"] == git_commit
            and row["event"] in {"push", "workflow_dispatch"}
            and row["conclusion"] == "success"
            and any(
                artifact["name"] == "cloudflare-site" and not artifact["expired"]
                for artifact in _api(f"actions/runs/{row['id']}/artifacts")["artifacts"]
            )
        ),
        None,
    )
    if run_id is None:
        raise ValueError("successful production site artifact is missing or expired")
    _gh(
        "run",
        "download",
        str(run_id),
        "--repo",
        REPOSITORY,
        "--name",
        "cloudflare-site",
        "--dir",
        str(destination),
    )
    return run_id


def resolve_production_snapshot(destination: Path) -> tuple[UpdatesSnapshot, dict[str, Any]]:
    """Read the durable snapshot, verifying its exact deployed artifact hash."""
    served, manifest_sha256 = _served_manifest()
    if UPDATES_SNAPSHOT not in served.assets:
        receipt = resolve_production_baseline(destination)
        return build_updates_snapshot(destination), receipt
    deployment = _successful_deployment(served)
    observation, body = fetch_asset_body(PRODUCTION_ORIGIN, f"/{UPDATES_SNAPSHOT}", timeout=20)
    if observation.status != 200 or body is None:
        raise ValueError("published Updates snapshot is unavailable")
    if hashlib.sha256(body).hexdigest() != served.assets[UPDATES_SNAPSHOT]:
        raise ValueError("published Updates snapshot hash differs from production manifest")
    snapshot = UpdatesSnapshot.model_validate_json(body)
    if snapshot.canonical_origin != served.canonical_origin or set(snapshot.elections) != {
        e.election_id for e in served.elections
    }:
        raise ValueError("published Updates snapshot election contract differs from manifest")
    if _served_manifest()[0] != served:
        raise ValueError("production manifest changed while resolving baseline; run the gate again")
    return snapshot, {
        "repository": REPOSITORY,
        "deployment_id": deployment["id"],
        "git_commit": deployment["sha"],
        "production_origin": PRODUCTION_ORIGIN,
        "manifest_sha256": manifest_sha256,
        "snapshot_sha256": hashlib.sha256(body).hexdigest(),
    }
