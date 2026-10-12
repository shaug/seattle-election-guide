"""Execute due source checks, retaining encrypted captures and immutable observations."""

from __future__ import annotations

import shutil
import subprocess
import tempfile
from datetime import date, datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from election_guide.calendar.models import ELECTION_TIMEZONE
from election_guide.collection.discovery import discover_publication
from election_guide.collection.http import fetch_http
from election_guide.collection.models import RefreshEvent
from election_guide.collection.refresh import (
    read_adapter_spec,
    record_refresh_failure,
    refresh_source,
)
from election_guide.collection.vault import read_key, restore_store, seal_store
from election_guide.collection.verification import (
    CheckRecord,
    ElectionPolicy,
    SourcePolicy,
    VerificationPolicy,
    baseline_reviewed,
    plan_verification,
    read_checks,
    read_panel,
)
from election_guide.evidence.models import CaptureRequest, evidence_fingerprint
from election_guide.evidence.storage import write_immutable_record
from election_guide.serialization import canonical_json_bytes


def record_check(root: Path, check: CheckRecord) -> None:
    payload = check.model_dump(mode="json")
    identity = evidence_fingerprint(payload)
    write_immutable_record(root / "checks" / f"{identity}.json", canonical_json_bytes(payload))


def consecutive_failures(
    root: Path, source_id: str, through: date | None = None, missing: set[date] | None = None
) -> int:
    latest: dict[str, CheckRecord] = {}
    for check in sorted(read_checks(root), key=lambda item: item.checked_at):
        if check.source_id == source_id and (through is None or check.scheduled_for <= through):
            latest[check.scheduled_for.isoformat()] = check
    missing_days = {
        day.isoformat() for day in missing or set() if through is None or day <= through
    }
    count = 0
    for day in sorted(set(latest) | missing_days, reverse=True):
        if day not in missing_days and latest[day].status not in {"failed", "missed"}:
            break
        count += 1
    return count


def run_verification(
    policy: VerificationPolicy,
    state_root: Path,
    checked_at: datetime,
    *,
    live: bool,
    fixtures: Path | None,
) -> dict[str, Any]:
    if live == (fixtures is not None):
        raise ValueError("choose exactly one of --live or --fixtures")
    if checked_at.tzinfo is None:
        raise ValueError("verification check time must include a timezone")
    as_of = checked_at.astimezone(ZoneInfo(ELECTION_TIMEZONE)).date()
    plan = plan_verification(policy, state_root, as_of)
    code_root = Path(__file__).resolve().parents[3]
    revision = subprocess.run(
        ["git", "-C", str(code_root), "rev-parse", "HEAD"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    source_tree_dirty = bool(
        subprocess.run(
            [
                "git",
                "-C",
                str(code_root),
                "status",
                "--porcelain",
                "--",
                "src",
                "config",
                "pyproject.toml",
                "uv.lock",
            ],
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()
    )
    report: dict[str, Any] = {
        "revision": revision,
        "source_tree_dirty": source_tree_dirty,
        "policy_fingerprint": evidence_fingerprint(policy.model_dump(mode="json")),
        "checked_at": checked_at.isoformat(),
        "automatic": [],
        "manual": [],
        "missed": [item.model_dump(mode="json") for item in plan.missed],
    }
    if not any(item.due for election in plan.elections for item in election.coverage):
        return {
            **report,
            "mode": "live" if live else "fixture",
            "coverage": plan.model_dump(mode="json"),
        }
    key = read_key()
    policies = {item.election_id: item for item in policy.elections}
    for election_plan in plan.elections:
        root = state_root / election_plan.election_id
        election = policies[election_plan.election_id]
        overrides = {item.source_id: item for item in election.sources}
        due = [item for item in election_plan.coverage if item.due]
        if not due:
            continue
        # A private transaction keeps interrupted checks from publishing an
        # extraction whose original bytes have not been sealed successfully.
        with tempfile.TemporaryDirectory(prefix="endorsement-verification-") as temporary:
            private = Path(temporary)
            working = private / "state"
            if root.exists():
                shutil.copytree(root, working)
            working.mkdir(parents=True, exist_ok=True)
            storage = private / "captures"
            restore_store(working / "vault", storage, key)
            activation = working / "activation.json"
            if not activation.exists():
                write_immutable_record(
                    activation,
                    canonical_json_bytes({"activated_on": as_of.isoformat(), "revision": revision}),
                )
            for missed in plan.missed:
                if missed.election_id == election.election_id and not any(
                    item.source_id == missed.source_id
                    and item.scheduled_for == missed.scheduled_for
                    for item in read_checks(working)
                ):
                    record_check(
                        working,
                        CheckRecord(
                            source_id=missed.source_id,
                            scheduled_for=missed.scheduled_for,
                            checked_at=checked_at,
                            status="missed",
                            mode="watch",
                        ),
                    )
            for obligation in due:
                source_policy = overrides.get(
                    obligation.source_id, SourcePolicy(source_id=obligation.source_id)
                )
                if source_policy.adapter is None:
                    record_check(
                        working,
                        CheckRecord(
                            source_id=obligation.source_id,
                            scheduled_for=as_of,
                            checked_at=checked_at,
                            status="manual_due",
                            mode="live" if live else "fixture",
                        ),
                    )
                    report["manual"].append(
                        {
                            "election_id": election.election_id,
                            "source_id": obligation.source_id,
                            "due": as_of.isoformat(),
                            "limitation": obligation.limitation,
                        }
                    )
                    continue
                event = _refresh(
                    election,
                    source_policy,
                    working,
                    storage,
                    private,
                    checked_at,
                    live=live,
                    fixtures=fixtures,
                )
                record_check(
                    working,
                    CheckRecord(
                        source_id=obligation.source_id,
                        scheduled_for=as_of,
                        checked_at=checked_at,
                        status=event.status,
                        event_id=event.id,
                        mode="live" if live else "fixture",
                    ),
                )
                failures = consecutive_failures(working, obligation.source_id)
                reviewed = baseline_reviewed(working, event.snapshot_id)
                report["automatic"].append(
                    {
                        "election_id": election.election_id,
                        **event.model_dump(mode="json"),
                        "baseline_reviewed": reviewed,
                        "consecutive_failures": failures,
                        "escalated": failures >= 3,
                    }
                )
            seal_store(storage, working / "vault", key)
            # Immutable bytes first, observations last. Git publishes the
            # resulting set as one commit; a partial local set is never success.
            for path in sorted(
                working.rglob("*.json"), key=lambda p: (p.parent.name == "checks", str(p))
            ):
                write_immutable_record(root / path.relative_to(working), path.read_bytes())
    report["mode"] = "live" if live else "fixture"
    report["coverage"] = plan_verification(policy, state_root, as_of).model_dump(mode="json")
    write_immutable_record(
        state_root / "runs" / f"{evidence_fingerprint(report)}.json", canonical_json_bytes(report)
    )
    return report


def _refresh(
    election: ElectionPolicy,
    policy: SourcePolicy,
    root: Path,
    storage: Path,
    private: Path,
    checked_at: datetime,
    *,
    live: bool,
    fixtures: Path | None,
) -> RefreshEvent:
    if policy.adapter is None:
        raise ValueError("automatic source has no adapter")
    registry, _ = read_panel(election)
    source = next(item for item in registry.sources if item.id == policy.source_id)
    try:
        if live:
            if policy.index_url:
                raw = discover_publication(policy, root, storage, checked_at)
                request = CaptureRequest(
                    source_id=source.id,
                    requested_url=policy.index_url,
                    canonical_url=policy.index_url,
                    title="Derived article-heading comparison; inputs linked by discovery record",
                    retrieved_at=checked_at,
                    media_type="text/html",
                    capture_method="manual_upload",
                    redistribution="restricted",
                    redistribution_note=(
                        "Generated comparison; original HTTP inputs are committed encrypted."
                    ),
                )
            else:
                artifact = fetch_http(source.discovery.requested_url)
                raw = artifact.content
                request = CaptureRequest(
                    source_id=source.id,
                    requested_url=source.discovery.requested_url,
                    canonical_url=artifact.canonical_url,
                    title=f"Official {election.election_id} endorsement publication",
                    retrieved_at=checked_at,
                    media_type=artifact.media_type,
                    capture_method="static_html",
                    http_status=artifact.status,
                    redirect_chain=artifact.redirect_chain,
                    redistribution="restricted",
                    redistribution_note="Original bytes retained in the committed encrypted vault.",
                )
        else:
            if fixtures is None:
                raise ValueError("offline checking requires a fixture directory")
            raw = (fixtures / f"{source.id}.html").read_bytes()
            media_type = "text/html"
            request = CaptureRequest(
                source_id=source.id,
                requested_url=source.discovery.requested_url,
                canonical_url=source.discovery.requested_url,
                title=f"Offline {election.election_id} verification fixture",
                retrieved_at=checked_at,
                media_type=media_type,
                capture_method="manual_upload",
                redistribution="restricted",
                redistribution_note="Offline fixture; no HTTP response or live check is claimed.",
            )
        input_path = private / "input.html"
        input_path.write_bytes(raw)
        return refresh_source(
            read_adapter_spec(policy.adapter),
            request,
            input_path,
            storage_root=storage,
            manifest_dir=root / "manifests",
            extraction_dir=root / "extractions",
            refresh_dir=root / "refreshes",
        )
    except (OSError, ValueError) as error:
        # Filesystem paths and response bodies are private. Public failures name
        # the error category; detailed diagnosis remains a local operator step.
        return record_refresh_failure(
            source.id,
            checked_at,
            f"Source check failed ({type(error).__name__}); inspect official access and adapter.",
            root / "refreshes",
            extraction_dir=root / "extractions",
        )
