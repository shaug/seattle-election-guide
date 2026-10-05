"""Human attestations are separate from automatic comparison state."""

from datetime import date, datetime
from pathlib import Path

from election_guide.collection.refresh import read_extraction_snapshot
from election_guide.collection.verification import BaselineApproval, CheckRecord, read_checks
from election_guide.collection.verification_runtime import record_check
from election_guide.evidence.storage import write_immutable_record
from election_guide.serialization import canonical_json_bytes


def approve_baseline(
    root: Path, snapshot_id: str, reviewer: str, reviewed_at: datetime, evidence: str
) -> None:
    # The ID is checked by reading a real identified snapshot before it becomes
    # a destination path. A fixture run can never become a trusted live check.
    if not snapshot_id.startswith("extraction-") or Path(snapshot_id).name != snapshot_id:
        raise ValueError("invalid baseline snapshot identity")
    snapshot = read_extraction_snapshot(root / "extractions" / f"{snapshot_id}.json")
    checks = read_checks(root)
    from election_guide.collection.refresh import read_refresh_event

    if not any(
        check.mode == "live"
        and check.event_id
        and read_refresh_event(root / "refreshes" / f"{check.event_id}.json").snapshot_id
        == snapshot.id
        for check in checks
    ):
        raise ValueError("only an executed live baseline can receive human approval")
    if reviewed_at < snapshot.extracted_at:
        raise ValueError("baseline review cannot precede extraction")
    approval = BaselineApproval(
        snapshot_id=snapshot.id, reviewer=reviewer, reviewed_at=reviewed_at, evidence=evidence
    )
    write_immutable_record(
        root / "approvals" / f"{snapshot.id}.json",
        canonical_json_bytes(approval.model_dump(mode="json")),
    )


def acknowledge_manual(
    root: Path,
    source_id: str,
    scheduled_for: date,
    reviewer: str,
    reviewed_at: datetime,
    evidence: str,
) -> None:
    if not reviewer.strip() or not evidence.strip():
        raise ValueError("manual verification requires a reviewer and evidence reference")
    if not any(
        check.source_id == source_id
        and check.scheduled_for == scheduled_for
        and check.status == "manual_due"
        for check in read_checks(root)
    ):
        raise ValueError("manual review must acknowledge an existing source obligation")
    record_check(
        root,
        CheckRecord(
            source_id=source_id,
            scheduled_for=scheduled_for,
            checked_at=reviewed_at,
            status="manual",
            mode="human",
            evidence=f"{reviewer}: {evidence}",
        ),
    )
