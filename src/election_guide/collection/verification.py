"""Calendar-derived source obligations and explicit automatic/manual coverage."""

from __future__ import annotations

import re
from datetime import UTC, date, datetime, time, timedelta
from pathlib import Path
from typing import Annotated, Literal
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator

from election_guide.calendar import read_election_calendar
from election_guide.calendar.models import ELECTION_TIMEZONE, ElectionCalendar
from election_guide.collection.adapters import validate_adapter
from election_guide.collection.models import REFRESH_ID_PATTERN, RefreshEvent
from election_guide.collection.refresh import read_adapter_spec
from election_guide.evidence.models import SOURCE_ID_PATTERN, evidence_fingerprint
from election_guide.inventory.importer import read_inventory
from election_guide.inventory.models import Inventory
from election_guide.normalization.matching import eligible_race_ids
from election_guide.serialization import read_json, read_yaml
from election_guide.sources.models import SourceRegistry
from election_guide.sources.registry import read_source_registry


class VerificationModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


RefreshInterval = Annotated[int, Field(strict=True, gt=0)]


class WfpPublicRequest(VerificationModel):
    """The reviewed unauthenticated Washington complete-list request only."""

    url: Literal["https://workingfamilies.org/wp-admin/admin-ajax.php"]
    method: Literal["POST"]
    form: dict[str, str]

    @model_validator(mode="after")
    def validate_form(self) -> WfpPublicRequest:
        if self.form != {"action": "more_candidates", "state": "25", "count": "0"}:
            raise ValueError("WFP request requires the reviewed complete Washington form")
        return self


class SourcePolicy(VerificationModel):
    source_id: str = Field(pattern=SOURCE_ID_PATTERN)
    adapter: Path | None = None
    daily_from_collection: bool = False
    refresh_interval_days: RefreshInterval | None = Field(
        default=None, exclude_if=lambda value: value is None
    )
    limitation: str = Field(default="Manual official-publication review required.", min_length=1)
    index_url: str | None = None
    article_pattern: str | None = None
    index_boundary: str | None = None
    request: WfpPublicRequest | None = None

    @model_validator(mode="after")
    def validate_index(self) -> SourcePolicy:
        if self.refresh_interval_days is not None and self.daily_from_collection:
            raise ValueError("refresh interval cannot combine with daily_from_collection")
        if self.request and (
            self.source_id != "washington-working-families-party"
            or self.adapter is None
            or self.index_url is not None
        ):
            raise ValueError("public form requests require the automatic WFP source only")
        if bool(self.index_url) != bool(self.article_pattern):
            raise ValueError("index URL and article pattern must be declared together")
        if self.index_url and self.adapter is None:
            raise ValueError("article discovery requires an automatic adapter")
        if self.index_url and self.source_id != "seattle-gay-news":
            raise ValueError("this verification tranche supports SGN index discovery only")
        if bool(self.index_url) != bool(self.index_boundary):
            raise ValueError("article discovery requires its reviewed oldest article boundary")
        if self.article_pattern:
            re.compile(self.article_pattern)
        return self


class ElectionPolicy(VerificationModel):
    election_id: str = Field(pattern=SOURCE_ID_PATTERN)
    registry: Path
    inventory: Path
    sources: list[SourcePolicy] = Field(default_factory=list[SourcePolicy])

    @model_validator(mode="after")
    def validate_unique_sources(self) -> ElectionPolicy:
        identifiers = [item.source_id for item in self.sources]
        if len(identifiers) != len(set(identifiers)):
            raise ValueError("verification policy repeats a source")
        return self


class AccessFailurePolicy(VerificationModel):
    """Prospective Pacific task dates; no refresh-interval configuration."""

    effective_from: date
    disposition: Literal["retain_verified"] = "retain_verified"


class VerificationPolicy(VerificationModel):
    schema_version: Literal["1.0", "1.1", "1.2"] = "1.0"
    calendar: Path
    elections: list[ElectionPolicy] = Field(min_length=1)
    access_failures: AccessFailurePolicy | None = Field(
        default=None, exclude_if=lambda value: value is None
    )

    @model_validator(mode="after")
    def validate_unique_elections(self) -> VerificationPolicy:
        if self.access_failures and self.schema_version == "1.0":
            raise ValueError("access-failure disposition requires policy schema 1.1")
        if self.schema_version != "1.2" and any(
            explicit_intervals(election) for election in self.elections
        ):
            raise ValueError("refresh intervals require policy schema 1.2")
        identifiers = [item.election_id for item in self.elections]
        if len(identifiers) != len(set(identifiers)):
            raise ValueError("verification policy repeats an election")
        return self


class RecordedAccessDisposition(VerificationModel):
    disposition: Literal["retained_verified_with_limitation"] = "retained_verified_with_limitation"
    qualification_id: str = Field(pattern=r"^[0-9a-f]{64}$")
    policy_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    effective_from: date


CHECK_EVIDENCE_MAX_LENGTH = 1100


class CheckRecord(VerificationModel):
    source_id: str = Field(pattern=SOURCE_ID_PATTERN)
    scheduled_for: date
    checked_at: AwareDatetime
    status: Literal["created", "updated", "unchanged", "failed", "manual", "manual_due", "missed"]
    event_id: str | None = Field(default=None, pattern=REFRESH_ID_PATTERN)
    evidence: str | None = Field(default=None, max_length=CHECK_EVIDENCE_MAX_LENGTH)
    mode: Literal["live", "fixture", "human", "watch"]
    recorded_at: AwareDatetime | None = Field(default=None, exclude_if=lambda value: value is None)
    access_disposition: RecordedAccessDisposition | None = Field(
        default=None, exclude_if=lambda value: value is None
    )

    @model_validator(mode="after")
    def validate_result(self) -> CheckRecord:
        if self.access_disposition and (self.status != "failed" or self.mode == "fixture"):
            raise ValueError("retained-access limitation requires a real failed observation")
        if (self.status in {"created", "updated", "unchanged", "failed"}) != bool(self.event_id):
            raise ValueError("automatic or failed checks require their refresh event")
        if self.status == "manual" and (self.mode != "human" or not self.evidence):
            raise ValueError("manual success requires human review evidence")
        if self.status == "missed" and self.mode != "watch":
            raise ValueError("missing checks require watcher provenance")
        manual_failure = self.status == "failed" and self.mode == "human"
        if manual_failure and (not self.evidence or self.recorded_at is None):
            raise ValueError("manual failed access requires its actor, evidence and recording time")
        if (
            self.status not in {"manual", "missed"}
            and self.mode not in {"live", "fixture"}
            and not manual_failure
        ):
            raise ValueError("automatic observations require live or fixture provenance")
        return self


class BaselineApproval(VerificationModel):
    snapshot_id: str
    reviewer: str = Field(min_length=1, max_length=100)
    reviewed_at: AwareDatetime
    evidence: str = Field(min_length=1, max_length=1000)


def baseline_reviewed(root: Path, snapshot_id: str | None) -> bool:
    if not snapshot_id:
        return False
    path = root / "approvals" / f"{snapshot_id}.json"
    if not path.exists():
        return False
    approval = BaselineApproval.model_validate(read_json(path))
    if approval.snapshot_id != snapshot_id:
        raise ValueError("baseline approval belongs to another snapshot")
    return True


class CoverageRecord(VerificationModel):
    source_id: str
    lane: Literal["automatic", "manual"]
    cadence: Literal["weekly", "daily", "interval"]
    last_successful_check: datetime | None
    next_due: date
    due: bool
    limitation: str
    refresh_interval_days: RefreshInterval | None = Field(
        default=None, exclude_if=lambda value: value is None
    )
    scheduled_for: date | None = Field(default=None, exclude_if=lambda value: value is None)
    freshness_due_at: AwareDatetime | None = Field(
        default=None, exclude_if=lambda value: value is None
    )
    freshness_due: bool | None = Field(default=None, exclude_if=lambda value: value is None)
    freshness_overdue: bool | None = Field(default=None, exclude_if=lambda value: value is None)
    freshness_evaluated_at: AwareDatetime | None = Field(
        default=None, exclude_if=lambda value: value is None
    )
    latest_attempt: CheckRecord | None = Field(default=None, exclude_if=lambda value: value is None)
    freshness: Literal["never_verified", "current", "access_limited", "review_required"] | None = (
        Field(default=None, exclude_if=lambda value: value is None)
    )


class ElectionPlan(VerificationModel):
    election_id: str
    cadence: Literal["weekly", "daily"]
    coverage: list[CoverageRecord]


class MissedCheck(VerificationModel):
    election_id: str
    source_id: str
    scheduled_for: date


class VerificationPlan(VerificationModel):
    as_of: date
    elections: list[ElectionPlan]
    missed: list[MissedCheck]


class Activation(VerificationModel):
    activated_on: date
    revision: str = Field(pattern=r"^[a-f0-9]{40}$")
    refresh_intervals: dict[str, RefreshInterval] | None = Field(
        default=None, exclude_if=lambda value: value is None
    )


def explicit_intervals(election: ElectionPolicy) -> dict[str, int]:
    return {
        source.source_id: source.refresh_interval_days
        for source in election.sources
        if source.refresh_interval_days is not None
    }


def validate_interval_pin(activation: Activation, election: ElectionPolicy) -> None:
    if (activation.refresh_intervals or {}) != explicit_intervals(election):
        raise ValueError("refresh intervals differ from immutable activation; use a new cycle")


class AutomaticResult(RefreshEvent):
    model_config = ConfigDict(extra="forbid")
    election_id: str = Field(pattern=SOURCE_ID_PATTERN)
    baseline_reviewed: bool
    consecutive_failures: int = Field(ge=0)
    escalated: bool
    access_disposition: RecordedAccessDisposition | None = Field(
        default=None, exclude_if=lambda value: value is None
    )


class ManualObligation(VerificationModel):
    election_id: str = Field(pattern=SOURCE_ID_PATTERN)
    source_id: str = Field(pattern=SOURCE_ID_PATTERN)
    due: date
    limitation: str = Field(min_length=1, max_length=2000)


class RunAudit(VerificationModel):
    revision: str = Field(pattern=r"^[a-f0-9]{40}$")
    source_tree_dirty: bool
    policy_fingerprint: str = Field(pattern=r"^[a-f0-9]{64}$")
    checked_at: AwareDatetime
    mode: Literal["live", "fixture"]
    automatic: list[AutomaticResult]
    manual: list[ManualObligation]
    missed: list[MissedCheck]
    coverage: VerificationPlan


def read_policy(path: Path) -> VerificationPolicy:
    policy = VerificationPolicy.model_validate(read_yaml(path))
    calendar = read_election_calendar(policy.calendar)
    for election in policy.elections:
        collection, issuance, election_day = calendar_window(calendar, election.election_id)
        if not collection <= issuance <= election_day:
            raise ValueError("verification calendar anchors contradict their collection window")
        registry, inventory = read_panel(election)
        known = {source.id for source in registry.sources}
        for source in election.sources:
            if source.source_id not in known:
                raise ValueError(f"verification policy has unknown source {source.source_id!r}")
            if not eligible_race_ids(source.source_id, inventory, registry):
                raise ValueError("verification source is outside active-panel eligibility")
            if source.adapter:
                spec = read_adapter_spec(source.adapter)
                if spec.source_id != source.source_id:
                    raise ValueError("verification adapter belongs to another source")
                validate_adapter(spec, inventory, registry)
            if source.index_url:
                official = next(item for item in registry.sources if item.id == source.source_id)
                declared = urlsplit(source.index_url)
                original = urlsplit(official.discovery.requested_url)
                if declared.scheme != "https" or declared.netloc != original.netloc:
                    raise ValueError(
                        "discovery index must use the official publication's HTTPS host"
                    )
                boundary = urlsplit(source.index_boundary or "")
                if (
                    boundary.scheme != "https"
                    or boundary.netloc != original.netloc
                    or not re.fullmatch(r"/story/[0-9]+/", boundary.path)
                ):
                    raise ValueError("index boundary must identify an official article")
    return policy


def read_panel(election: ElectionPolicy) -> tuple[SourceRegistry, Inventory]:
    registry = read_source_registry(election.registry)
    inventory = read_inventory(election.inventory)
    if (
        registry.election_id != election.election_id
        or inventory.election.id != election.election_id
    ):
        raise ValueError("verification inputs belong to another election")
    return registry, inventory


def calendar_window(calendar: ElectionCalendar, election_id: str) -> tuple[date, date, date]:
    milestones = calendar.election_milestones(election_id)
    anchors: list[date] = []
    for kind in ("collection_opens", "overseas_service_ballots_mail", "election_day"):
        matches = [
            item for item in milestones if item.kind == kind and item.date_status == "planned"
        ]
        if len(matches) != 1:
            raise ValueError(f"verification requires one planned {kind} anchor for {election_id}")
        anchors.append(calendar.scheduled_date(matches[0]))
    return anchors[0], anchors[1], anchors[2]


def read_checks(root: Path) -> list[CheckRecord]:
    checks: list[CheckRecord] = []
    for path in sorted(root.glob("checks/*.json")):
        check = CheckRecord.model_validate(read_json(path))
        if path.stem != evidence_fingerprint(check.model_dump(mode="json")):
            raise ValueError("check filename does not match its content")
        checks.append(check)
    return checks


def check_order(check: CheckRecord) -> tuple[datetime, int, datetime]:
    # Administrative markers cannot replace actual outcomes at the same clock precision.
    rank = {"manual_due": 0, "missed": 1, "failed": 2}.get(check.status, 3)
    return check.checked_at, rank, check.recorded_at or check.checked_at


def scheduled_dates(
    start: date, daily: date, end: date, *, interval_days: int | None = None
) -> list[date]:
    dates: list[date] = []
    day = start
    while day <= end:
        anchor = daily if day >= daily else start
        interval = interval_days or (1 if day >= daily else 7)
        if (day - anchor).days % interval == 0:
            dates.append(day)
        day += timedelta(days=1)
    return dates


def source_scheduled_dates(
    collection: date, issuance: date, election_day: date, activation: date, source: SourcePolicy
) -> list[date]:
    daily = collection if source.daily_from_collection else issuance
    mandatory = {activation}
    if source.refresh_interval_days is not None:
        mandatory.update({issuance, election_day})
    return sorted(
        day
        for day in mandatory
        | set(
            scheduled_dates(
                collection, daily, election_day, interval_days=source.refresh_interval_days
            )
        )
        if day >= activation
    )


def freshness_deadline(
    success: datetime | None, source: SourcePolicy, daily: date, as_of: date
) -> datetime | None:
    """Elapsed UTC age is distinct from a finite Pacific attempt obligation."""
    if success is None:
        return None
    success = success.astimezone(UTC)
    try:
        if source.refresh_interval_days is not None:
            return success + timedelta(days=source.refresh_interval_days)
        weekly = success + timedelta(days=7)
        if as_of < daily:
            return weekly
        daily_start = datetime.combine(daily, time(), ZoneInfo(ELECTION_TIMEZONE)).astimezone(UTC)
        elapsed_day = success + timedelta(days=1)
        if success >= daily_start:
            return elapsed_day
        return min(weekly, max(daily_start, elapsed_day))
    except OverflowError as error:
        raise ValueError(
            "refresh interval produces an unrepresentable freshness deadline"
        ) from error


def plan_verification(
    policy: VerificationPolicy, state_root: Path, as_of: date, *, as_of_at: datetime | None = None
) -> VerificationPlan:
    if as_of_at is not None:
        if as_of_at.tzinfo is None or as_of_at.utcoffset() is None:
            raise ValueError("freshness evaluation clock must include a timezone")
        if as_of_at.astimezone(ZoneInfo(ELECTION_TIMEZONE)).date() != as_of:
            raise ValueError("freshness evaluation clock differs from its Pacific date")
        as_of_at = as_of_at.astimezone(UTC)
    calendar = read_election_calendar(policy.calendar)
    elections: list[ElectionPlan] = []
    missed: list[MissedCheck] = []
    for election in policy.elections:
        collection, issuance, election_day = calendar_window(calendar, election.election_id)
        root = state_root / election.election_id
        activation_path = root / "activation.json"
        if as_of < collection or (as_of > election_day and not activation_path.exists()):
            continue
        registry, inventory = read_panel(election)
        checks = read_checks(root)
        # Until activation, only today's obligations exist: no fabricated history.
        activation = as_of
        if activation_path.exists():
            recorded_activation = Activation.model_validate(read_json(activation_path))
            validate_interval_pin(recorded_activation, election)
            activation = recorded_activation.activated_on
        if activation > as_of:
            raise ValueError("verification clock precedes its recorded activation")
        coverage: list[CoverageRecord] = []
        overrides = {source.source_id: source for source in election.sources}
        for source in registry.sources:
            if not eligible_race_ids(source.id, inventory, registry):
                continue
            override = overrides.get(source.id, SourcePolicy(source_id=source.id))
            daily = collection if override.daily_from_collection else issuance
            dates = source_scheduled_dates(collection, issuance, election_day, activation, override)
            history = sorted(
                (check for check in checks if check.source_id == source.id),
                key=check_order,
            )
            observed = {check.scheduled_for for check in history}
            missed_days = {check.scheduled_for for check in history if check.status == "missed"}
            attempts = [check for check in history if check.status != "manual_due"]
            pending = [day for day in dates if day not in observed]
            due = [day for day in pending if day <= as_of]
            from election_guide.collection.refresh import read_refresh_event

            successes = [
                check
                for check in history
                if check.status == "manual"
                or (
                    check.mode == "live"
                    and check.status in {"created", "updated", "unchanged"}
                    and check.event_id
                    and baseline_reviewed(
                        root,
                        read_refresh_event(
                            root / "refreshes" / f"{check.event_id}.json"
                        ).snapshot_id,
                    )
                )
            ]
            last_success = successes[-1].checked_at if successes else None
            deadline = freshness_deadline(last_success, override, daily, as_of)
            coverage.append(
                CoverageRecord(
                    source_id=source.id,
                    lane="automatic" if override.adapter else "manual",
                    cadence="interval"
                    if override.refresh_interval_days is not None
                    else "daily"
                    if as_of >= daily
                    else "weekly",
                    last_successful_check=last_success,
                    next_due=as_of
                    if due
                    else (pending[0] if pending else election_day + timedelta(days=1)),
                    due=bool(due) and as_of <= election_day,
                    limitation=override.limitation,
                    refresh_interval_days=override.refresh_interval_days,
                    scheduled_for=due[-1]
                    if due and override.refresh_interval_days is not None
                    else None,
                    freshness_due_at=deadline,
                    freshness_due=as_of_at >= deadline
                    if as_of_at is not None and deadline is not None
                    else None,
                    freshness_overdue=as_of_at > deadline
                    if as_of_at is not None and deadline is not None
                    else None,
                    freshness_evaluated_at=as_of_at,
                    latest_attempt=attempts[-1] if attempts else None,
                    freshness=(
                        "access_limited"
                        if attempts and attempts[-1].access_disposition
                        else "current"
                        if successes and attempts[-1] == successes[-1]
                        else "review_required"
                        if attempts
                        else "never_verified"
                    ),
                )
            )
            for day in sorted(set(due) | missed_days):
                if day < as_of:
                    missed.append(
                        MissedCheck(
                            election_id=election.election_id, source_id=source.id, scheduled_for=day
                        )
                    )
        if as_of <= election_day or any(
            item.election_id == election.election_id for item in missed
        ):
            elections.append(
                ElectionPlan(
                    election_id=election.election_id,
                    cadence="daily" if as_of >= issuance else "weekly",
                    coverage=coverage,
                )
            )
    return VerificationPlan(as_of=as_of, elections=elections, missed=missed)
