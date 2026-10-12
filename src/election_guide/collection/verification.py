"""Calendar-derived source obligations and explicit automatic/manual coverage."""

from __future__ import annotations

import re
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Literal
from urllib.parse import urlsplit

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator

from election_guide.calendar import read_election_calendar
from election_guide.calendar.models import ElectionCalendar
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


class SourcePolicy(VerificationModel):
    source_id: str = Field(pattern=SOURCE_ID_PATTERN)
    adapter: Path | None = None
    daily_from_collection: bool = False
    limitation: str = Field(default="Manual official-publication review required.", min_length=1)
    index_url: str | None = None
    article_pattern: str | None = None
    index_boundary: str | None = None

    @model_validator(mode="after")
    def validate_index(self) -> SourcePolicy:
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


class VerificationPolicy(VerificationModel):
    schema_version: Literal["1.0"] = "1.0"
    calendar: Path
    elections: list[ElectionPolicy] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_unique_elections(self) -> VerificationPolicy:
        identifiers = [item.election_id for item in self.elections]
        if len(identifiers) != len(set(identifiers)):
            raise ValueError("verification policy repeats an election")
        return self


class CheckRecord(VerificationModel):
    source_id: str = Field(pattern=SOURCE_ID_PATTERN)
    scheduled_for: date
    checked_at: AwareDatetime
    status: Literal["created", "updated", "unchanged", "failed", "manual", "manual_due", "missed"]
    event_id: str | None = Field(default=None, pattern=REFRESH_ID_PATTERN)
    evidence: str | None = Field(default=None, max_length=1100)
    mode: Literal["live", "fixture", "human", "watch"]

    @model_validator(mode="after")
    def validate_result(self) -> CheckRecord:
        if (self.status in {"created", "updated", "unchanged", "failed"}) != bool(self.event_id):
            raise ValueError("automatic checks require their refresh event")
        if self.status == "manual" and (self.mode != "human" or not self.evidence):
            raise ValueError("manual success requires human review evidence")
        if self.status == "missed" and self.mode != "watch":
            raise ValueError("missing checks require watcher provenance")
        if self.status not in {"manual", "missed"} and self.mode not in {"live", "fixture"}:
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
    cadence: Literal["weekly", "daily"]
    last_successful_check: datetime | None
    next_due: date
    due: bool
    limitation: str


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


class AutomaticResult(RefreshEvent):
    model_config = ConfigDict(extra="forbid")
    election_id: str = Field(pattern=SOURCE_ID_PATTERN)
    baseline_reviewed: bool
    consecutive_failures: int = Field(ge=0)
    escalated: bool


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


def scheduled_dates(start: date, daily: date, end: date) -> list[date]:
    dates: list[date] = []
    day = start
    while day <= end:
        if day >= daily or (day - start).days % 7 == 0:
            dates.append(day)
        day += timedelta(days=1)
    return dates


def plan_verification(
    policy: VerificationPolicy, state_root: Path, as_of: date
) -> VerificationPlan:
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
        activation = (
            Activation.model_validate(read_json(activation_path)).activated_on
            if activation_path.exists()
            else as_of
        )
        if activation > as_of:
            raise ValueError("verification clock precedes its recorded activation")
        coverage: list[CoverageRecord] = []
        overrides = {source.source_id: source for source in election.sources}
        for source in registry.sources:
            if not eligible_race_ids(source.id, inventory, registry):
                continue
            override = overrides.get(source.id, SourcePolicy(source_id=source.id))
            daily = collection if override.daily_from_collection else issuance
            dates = sorted(
                {
                    activation,
                    *[
                        day
                        for day in scheduled_dates(collection, daily, election_day)
                        if day >= activation
                    ],
                }
            )
            history = sorted(
                (check for check in checks if check.source_id == source.id),
                key=lambda check: check.checked_at,
            )
            observed = {check.scheduled_for for check in history}
            missed_days = {check.scheduled_for for check in history if check.status == "missed"}
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
            coverage.append(
                CoverageRecord(
                    source_id=source.id,
                    lane="automatic" if override.adapter else "manual",
                    cadence="daily" if as_of >= daily else "weekly",
                    last_successful_check=successes[-1].checked_at if successes else None,
                    next_due=as_of
                    if due
                    else (pending[0] if pending else election_day + timedelta(days=1)),
                    due=bool(due) and as_of <= election_day,
                    limitation=override.limitation,
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
