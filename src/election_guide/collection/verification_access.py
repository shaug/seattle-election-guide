"""Explicit failed-access observations; no publisher access or inferred review."""

from __future__ import annotations

import subprocess
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Literal
from zoneinfo import ZoneInfo

from pydantic import AwareDatetime, Field, field_validator, model_validator

from election_guide.calendar.models import ELECTION_TIMEZONE
from election_guide.collection.models import AccessFailureDiagnostic, RefreshEvent
from election_guide.collection.refresh import read_refresh_event, record_refresh_failure
from election_guide.collection.verification import (
    CheckRecord,
    RecordedAccessDisposition,
    VerificationModel,
    VerificationPolicy,
    read_checks,
    read_panel,
)
from election_guide.collection.verification_runtime import record_check
from election_guide.evidence.models import evidence_fingerprint
from election_guide.evidence.storage import write_immutable_record
from election_guide.serialization import canonical_json_bytes, read_json
from election_guide.validation import validated_http_url

_REPOSITORY_ROOT = Path(__file__).resolve().parents[3]


def utc_now() -> datetime:
    return datetime.now(UTC)


def record_manual_access_failure(
    policy: VerificationPolicy,
    state_root: Path,
    election_id: str,
    source_id: str,
    scheduled_for: date,
    checked_at: datetime,
    reviewer: str,
    evidence: str,
    diagnostic: AccessFailureDiagnostic,
) -> CheckRecord:
    """Record an operator's actual failed attempt, never a successful acknowledgement."""
    recorded_at = utc_now()
    if checked_at.tzinfo is None or checked_at > recorded_at:
        raise ValueError("access observation requires an actual past timezone-aware check time")
    if scheduled_for > checked_at.astimezone(ZoneInfo(ELECTION_TIMEZONE)).date():
        raise ValueError("failed access cannot precede its scheduled Pacific date")
    if not reviewer.strip() or not evidence.strip():
        raise ValueError("failed access requires its actual observer and durable evidence")
    election = next(item for item in policy.elections if item.election_id == election_id)
    if any(item.source_id == source_id and item.adapter for item in election.sources):
        raise ValueError("automatic sources retain their normal automatic attempts")
    root = state_root / election_id
    checks = read_checks(root)
    if not any(
        item.source_id == source_id
        and item.scheduled_for == scheduled_for
        and item.status == "manual_due"
        for item in checks
    ):
        raise ValueError("failed manual access requires an existing dated manual obligation")
    reference = f"{reviewer.strip()}: {evidence.strip()}"
    for check in checks:
        if check.source_id == source_id and check.checked_at == checked_at and check.event_id:
            event = read_refresh_event(root / "refreshes" / f"{check.event_id}.json")
            if (
                check.scheduled_for != scheduled_for
                or check.mode != "human"
                or check.status != "failed"
                or check.evidence != reference
                or event.access_failure != diagnostic
            ):
                raise ValueError("access observation conflicts with an immutable prior check")
            return check
    event = record_refresh_failure(
        source_id,
        checked_at,
        "Manual source access failed; observation evidence is in its scheduled check.",
        root / "refreshes",
        extraction_dir=root / "extractions",
        access_failure=diagnostic,
    )
    check = CheckRecord(
        source_id=source_id,
        scheduled_for=scheduled_for,
        checked_at=checked_at,
        recorded_at=recorded_at,
        status="failed",
        event_id=event.id,
        mode="human",
        evidence=reference,
    )
    disposition = new_access_disposition(policy, root, check, event)
    if disposition:
        check = check.model_copy(update={"access_disposition": disposition})
    record_check(root, check)
    return check


# Qualification records are explicit reviewed attestations, not inferred from a
# CheckRecord, successful fetch, extractor flag or collector baseline approval.


class InitialReviewQualification(VerificationModel):
    """One explicit complete-review attestation, accepted by normal protected review."""

    election_id: str = Field(pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
    source_id: str = Field(pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
    scope: Literal["complete_official_publication_and_mappings"]
    official_urls: list[str] = Field(min_length=1)
    checked_at: AwareDatetime
    original_reviewer: str = Field(min_length=1, max_length=200)
    reviewed_at: AwareDatetime
    evidence: str = Field(min_length=1, max_length=1000)
    recorded_by: str = Field(min_length=1, max_length=200)
    recorded_at: AwareDatetime

    @field_validator("official_urls")
    @classmethod
    def validate_urls(cls, value: list[str]) -> list[str]:
        if len(set(value)) != len(value):
            raise ValueError("attestation repeats an official publication URL")
        return [validated_http_url(url) for url in value]

    @model_validator(mode="after")
    def validate_review(self) -> InitialReviewQualification:
        if not all(
            value.strip() for value in (self.original_reviewer, self.evidence, self.recorded_by)
        ):
            raise ValueError("attestation requires actual reviewer, evidence and recording actor")
        if not self.checked_at <= self.reviewed_at <= self.recorded_at:
            raise ValueError("attestation must preserve actual check, review and recording order")
        return self


def qualify_initial_review(
    policy: VerificationPolicy,
    root: Path,
    source_id: str,
    scope: str,
    official_urls: list[str],
    checked_at: datetime,
    reviewer: str,
    reviewed_at: datetime,
    evidence: str,
    recorded_by: str,
) -> InitialReviewQualification:
    election = next(item for item in policy.elections if item.election_id == root.name)
    registry, _ = read_panel(election)
    if not any(source.id == source_id for source in registry.sources):
        raise ValueError("attestation requires a registered source for this election")
    qualification = InitialReviewQualification.model_validate(
        {
            "election_id": election.election_id,
            "source_id": source_id,
            "scope": scope,
            "official_urls": official_urls,
            "checked_at": checked_at,
            "original_reviewer": reviewer,
            "reviewed_at": reviewed_at,
            "evidence": evidence,
            "recorded_by": recorded_by,
            "recorded_at": utc_now(),
        }
    )
    payload = qualification.model_dump(mode="json")
    write_immutable_record(
        root / "source-reviews" / f"{evidence_fingerprint(payload)}.json",
        canonical_json_bytes(payload),
    )
    return qualification


def _admitted_qualification(root: Path, identity: str, election_id: str) -> bool:
    """Use the already available normal main snapshot; never fetch or trust pending state."""
    path = f"data/verification/{election_id}/source-reviews/{identity}.json"
    try:
        admitted = subprocess.run(
            [
                "git",
                "--no-lazy-fetch",
                "-C",
                str(_REPOSITORY_ROOT),
                "show",
                f"refs/remotes/origin/main:{path}",
            ],
            capture_output=True,
            check=False,
        )
    except OSError:
        return False
    return (
        admitted.returncode == 0
        and admitted.stdout == (root / "source-reviews" / f"{identity}.json").read_bytes()
    )


def read_qualifications(
    root: Path, *, election_id: str | None = None
) -> dict[str, InitialReviewQualification]:
    result: dict[str, InitialReviewQualification] = {}
    for path in sorted(root.glob("source-reviews/*.json")):
        record = InitialReviewQualification.model_validate(read_json(path))
        if path.stem != evidence_fingerprint(
            record.model_dump(mode="json")
        ) or record.election_id != (election_id or root.name):
            raise ValueError("qualification identity/election contradicts its immutable record")
        result[path.stem] = record
    return result


def new_access_disposition(
    policy: VerificationPolicy,
    root: Path,
    check: CheckRecord,
    event: RefreshEvent,
    *,
    election_id: str | None = None,
) -> RecordedAccessDisposition | None:
    """Called only while appending a NEW check; readers never backfill a disposition."""
    setting = policy.access_failures
    if (
        setting is None
        or check.mode == "fixture"
        or check.status != "failed"
        or check.scheduled_for < setting.effective_from
        or event.access_failure is None
        or event.capture_id is not None
        or event.content_changed is not None
    ):
        return None
    for identity, review in sorted(
        read_qualifications(root, election_id=election_id).items(),
        key=lambda item: item[1].recorded_at,
        reverse=True,
    ):
        if review.source_id != check.source_id or review.recorded_at > check.checked_at:
            continue
        if not _admitted_qualification(root, identity, review.election_id):
            continue
        # A known changed publication, parse/completeness/conflict failure or
        # unknown diagnostic after this accepted review needs review, not an
        # access exception. A later explicit complete qualification can supersede it.
        intervening = [
            read_refresh_event(root / "refreshes" / f"{prior.event_id}.json")
            for prior in read_checks(root)
            if prior.source_id == check.source_id
            and prior.event_id
            and review.reviewed_at < prior.checked_at < check.checked_at
        ]
        if any(
            item.content_changed or (item.status == "failed" and item.access_failure is None)
            for item in intervening
        ):
            continue
        return RecordedAccessDisposition(
            qualification_id=identity,
            policy_fingerprint=evidence_fingerprint(policy.model_dump(mode="json")),
            effective_from=setting.effective_from,
        )
    return None


def validate_access_disposition(
    root: Path, check: CheckRecord, event: RefreshEvent
) -> InitialReviewQualification:
    disposition = check.access_disposition
    assert disposition is not None
    review = read_qualifications(root).get(disposition.qualification_id)
    if (
        review is None
        or review.source_id != check.source_id
        or review.recorded_at > check.checked_at
        or check.scheduled_for < disposition.effective_from
        or event.access_failure is None
        or event.capture_id is not None
        or event.content_changed is not None
    ):
        raise ValueError("recorded access limitation lacks its prospective complete-review proof")
    return review
